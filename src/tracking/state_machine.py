"""Canonical parcel state machine for 3PL tracking events.

Each partner (3PL) sends tracking events in its own status codes. The
integration layer maps them to canonical statuses (see
docs/status-mapping.csv) and applies them to a parcel with the rules in
docs/PRD.md section 6. Acceptance criteria IDs (AC-xx) are noted where a
rule is enforced, and each one has a test in tests/test_acceptance.py.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path


class Status(str, Enum):
    CREATED = "CREATED"
    PICKED_UP = "PICKED_UP"                    # first mile
    AT_SORT_CENTRE = "AT_SORT_CENTRE"          # sorting
    IN_TRANSIT = "IN_TRANSIT"                  # line-haul
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"      # last mile
    DELIVERED = "DELIVERED"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    RETURNING_TO_SENDER = "RETURNING_TO_SENDER"
    RETURNED = "RETURNED"
    LOST = "LOST"
    CANCELLED = "CANCELLED"


TERMINAL = {Status.DELIVERED, Status.RETURNED, Status.LOST, Status.CANCELLED}

ALLOWED: dict[Status, set[Status]] = {
    Status.CREATED: {Status.PICKED_UP, Status.CANCELLED},
    Status.PICKED_UP: {Status.AT_SORT_CENTRE, Status.IN_TRANSIT},
    Status.AT_SORT_CENTRE: {Status.IN_TRANSIT, Status.OUT_FOR_DELIVERY},
    Status.IN_TRANSIT: {Status.AT_SORT_CENTRE, Status.OUT_FOR_DELIVERY},
    Status.OUT_FOR_DELIVERY: {Status.DELIVERED, Status.DELIVERY_FAILED},
    Status.DELIVERY_FAILED: {
        Status.OUT_FOR_DELIVERY,      # reattempt
        Status.AT_SORT_CENTRE,        # back to station
        Status.RETURNING_TO_SENDER,
    },
    Status.RETURNING_TO_SENDER: {Status.IN_TRANSIT, Status.RETURNED},
}
# Any non-terminal parcel can be declared lost by the partner.
for _s in Status:
    if _s not in TERMINAL:
        ALLOWED.setdefault(_s, set()).add(Status.LOST)

# Illustrative market configuration (PRD section 6.4).
MAX_DELIVERY_ATTEMPTS = {"SG": 3, "MY": 3, "VN": 2}
MAX_CLOCK_SKEW = timedelta(minutes=15)


class Outcome(str, Enum):
    APPLIED = "applied"              # current status changed
    DUPLICATE = "duplicate"          # same event_id seen before, no-op
    HISTORY_ONLY = "history_only"    # older than current status, stored only
    NEEDS_REVIEW = "needs_review"    # invalid transition, stored and flagged
    QUARANTINED = "quarantined"      # unmapped partner code
    REJECTED = "rejected"            # malformed: not stored


@dataclass
class TrackingEvent:
    event_id: str
    partner_id: str
    tracking_no: str
    partner_status_code: str
    event_time: datetime
    market: str
    location: str | None = None


@dataclass
class Parcel:
    tracking_no: str
    market: str
    status: Status = Status.CREATED
    status_time: datetime | None = None
    failed_attempts: int = 0
    history: list[tuple[TrackingEvent, Status | None, Outcome]] = field(default_factory=list)
    seen_event_ids: set[str] = field(default_factory=set)
    review_flags: list[str] = field(default_factory=list)


def load_mapping(path: str | Path) -> dict[tuple[str, str], Status]:
    """Read (partner_id, partner_status_code) -> canonical Status."""
    mapping: dict[tuple[str, str], Status] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mapping[(row["partner_id"], row["partner_status_code"])] = Status(row["canonical_status"])
    return mapping


def apply_event(parcel: Parcel, event: TrackingEvent,
                mapping: dict[tuple[str, str], Status], now: datetime) -> Outcome:
    # AC-08: reject events from the future beyond allowed clock skew.
    if event.event_time > now + MAX_CLOCK_SKEW:
        return Outcome.REJECTED
    # AC-09: tracking number and market must match the parcel.
    if event.tracking_no != parcel.tracking_no or event.market != parcel.market:
        return Outcome.REJECTED

    # AC-02: idempotency on event_id.
    if event.event_id in parcel.seen_event_ids:
        return Outcome.DUPLICATE
    parcel.seen_event_ids.add(event.event_id)

    # AC-05: unmapped partner code is quarantined, status unchanged.
    target = mapping.get((event.partner_id, event.partner_status_code))
    if target is None:
        parcel.history.append((event, None, Outcome.QUARANTINED))
        parcel.review_flags.append(f"unmapped:{event.partner_id}:{event.partner_status_code}")
        return Outcome.QUARANTINED

    # AC-03: out-of-order (older) events go to history only.
    if parcel.status_time is not None and event.event_time < parcel.status_time:
        parcel.history.append((event, target, Outcome.HISTORY_ONLY))
        return Outcome.HISTORY_ONLY

    # AC-04 / AC-06: invalid transition, including anything after a terminal status.
    if target not in ALLOWED.get(parcel.status, set()):
        parcel.history.append((event, target, Outcome.NEEDS_REVIEW))
        parcel.review_flags.append(f"invalid:{parcel.status.value}->{target.value}")
        return Outcome.NEEDS_REVIEW

    # AC-07: no reattempt beyond the market's maximum delivery attempts.
    max_attempts = MAX_DELIVERY_ATTEMPTS.get(parcel.market, 3)
    if (parcel.status == Status.DELIVERY_FAILED and target == Status.OUT_FOR_DELIVERY
            and parcel.failed_attempts >= max_attempts):
        parcel.history.append((event, target, Outcome.NEEDS_REVIEW))
        parcel.review_flags.append("max_attempts_exceeded")
        return Outcome.NEEDS_REVIEW

    # AC-01: valid, in-order event updates the current status.
    if target == Status.DELIVERY_FAILED:
        parcel.failed_attempts += 1
    parcel.status = target
    parcel.status_time = event.event_time
    parcel.history.append((event, target, Outcome.APPLIED))
    return Outcome.APPLIED
