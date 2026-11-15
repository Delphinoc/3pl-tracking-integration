"""One test per acceptance criterion in docs/PRD.md section 7."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tracking.state_machine import (
    Outcome, Parcel, Status, TrackingEvent, apply_event, load_mapping,
)

ROOT = Path(__file__).resolve().parents[1]
MAPPING = load_mapping(ROOT / "docs" / "status-mapping.csv")
T0 = datetime(2026, 11, 11, 8, 0)
NOW = T0 + timedelta(days=3)


def ev(code, minutes, event_id=None, partner="SLX", tracking="TRK001", market="SG"):
    return TrackingEvent(
        event_id=event_id or f"{partner}-{code}-{minutes}",
        partner_id=partner, tracking_no=tracking, partner_status_code=code,
        event_time=T0 + timedelta(minutes=minutes), market=market,
    )


def run(parcel, events):
    return [apply_event(parcel, e, MAPPING, NOW) for e in events]


@pytest.fixture
def parcel():
    return Parcel(tracking_no="TRK001", market="SG")


HAPPY_PATH = [("PU", 10), ("HUB_IN", 60), ("HUB_OUT", 120), ("HUB_IN", 300),
              ("OFD", 600), ("DLV", 700)]


def test_ac01_happy_path_updates_status_in_order(parcel):
    outcomes = run(parcel, [ev(c, m) for c, m in HAPPY_PATH])
    assert outcomes == [Outcome.APPLIED] * len(HAPPY_PATH)
    assert parcel.status == Status.DELIVERED
    assert len(parcel.history) == len(HAPPY_PATH)


def test_ac02_duplicate_event_id_is_a_no_op(parcel):
    first = ev("PU", 10, event_id="E1")
    assert run(parcel, [first, first]) == [Outcome.APPLIED, Outcome.DUPLICATE]
    assert len(parcel.history) == 1


def test_ac03_older_event_is_stored_but_does_not_roll_back_status(parcel):
    run(parcel, [ev("PU", 10), ev("HUB_IN", 60), ev("OFD", 600)])
    late = ev("HUB_OUT", 120)          # arrives after OFD but happened before it
    assert apply_event(parcel, late, MAPPING, NOW) == Outcome.HISTORY_ONLY
    assert parcel.status == Status.OUT_FOR_DELIVERY
    assert parcel.history[-1][2] == Outcome.HISTORY_ONLY


def test_ac04_invalid_transition_is_flagged_for_review(parcel):
    run(parcel, [ev("PU", 10)])
    assert apply_event(parcel, ev("DLV", 20), MAPPING, NOW) == Outcome.NEEDS_REVIEW
    assert parcel.status == Status.PICKED_UP
    assert "invalid:PICKED_UP->DELIVERED" in parcel.review_flags


def test_ac05_unmapped_partner_code_is_quarantined(parcel):
    assert apply_event(parcel, ev("WEIRD", 10), MAPPING, NOW) == Outcome.QUARANTINED
    assert parcel.status == Status.CREATED
    assert "unmapped:SLX:WEIRD" in parcel.review_flags


def test_ac06_no_change_after_terminal_status(parcel):
    run(parcel, [ev(c, m) for c, m in HAPPY_PATH])
    assert apply_event(parcel, ev("DF_NA", 800), MAPPING, NOW) == Outcome.NEEDS_REVIEW
    assert parcel.status == Status.DELIVERED


@pytest.mark.parametrize("market,max_attempts", [("SG", 3), ("VN", 2)])
def test_ac07_reattempts_capped_by_market(market, max_attempts):
    p = Parcel(tracking_no="TRK001", market=market)
    run(p, [ev("PU", 1, market=market), ev("HUB_IN", 2, market=market)])
    minute = 10
    for attempt in range(max_attempts):
        assert apply_event(p, ev("OFD", minute, market=market), MAPPING, NOW) == Outcome.APPLIED
        assert apply_event(p, ev("DF_NA", minute + 1, market=market), MAPPING, NOW) == Outcome.APPLIED
        minute += 10
    assert p.failed_attempts == max_attempts
    assert apply_event(p, ev("OFD", minute, market=market), MAPPING, NOW) == Outcome.NEEDS_REVIEW
    assert "max_attempts_exceeded" in p.review_flags
    # Return to sender is still allowed after the cap.
    assert apply_event(p, ev("RTS", minute + 1, market=market), MAPPING, NOW) == Outcome.APPLIED


def test_ac08_future_event_beyond_clock_skew_is_rejected(parcel):
    future = TrackingEvent("F1", "SLX", "TRK001", "PU", NOW + timedelta(minutes=16), "SG")
    within = TrackingEvent("F2", "SLX", "TRK001", "PU", NOW + timedelta(minutes=14), "SG")
    assert apply_event(parcel, future, MAPPING, NOW) == Outcome.REJECTED
    assert parcel.history == []
    assert apply_event(parcel, within, MAPPING, NOW) == Outcome.APPLIED


def test_ac09_mismatched_tracking_number_or_market_is_rejected(parcel):
    assert apply_event(parcel, ev("PU", 10, tracking="OTHER"), MAPPING, NOW) == Outcome.REJECTED
    assert apply_event(parcel, ev("PU", 10, market="MY"), MAPPING, NOW) == Outcome.REJECTED
    assert parcel.status == Status.CREATED


def test_ac10_two_partners_map_to_same_canonical_journey():
    slx = Parcel("TRK001", "SG")
    kgn = Parcel("TRK001", "SG")
    run(slx, [ev(c, m) for c, m in HAPPY_PATH])
    run(kgn, [ev(c, m, partner="KGN") for c, m in
              [("20", 10), ("30", 60), ("35", 120), ("30", 300), ("40", 600), ("51", 700)]])
    canon = lambda p: [h[1] for h in p.history]
    assert canon(slx) == canon(kgn)


def test_ac11_lost_allowed_from_any_non_terminal_status(parcel):
    run(parcel, [ev("PU", 10), ev("HUB_IN", 60)])
    assert apply_event(parcel, ev("LOST", 90), MAPPING, NOW) == Outcome.APPLIED
    assert parcel.status == Status.LOST


def test_ac12_cancel_only_before_pickup(parcel):
    run(parcel, [ev("PU", 10)])
    assert apply_event(parcel, ev("CXL", 20), MAPPING, NOW) == Outcome.NEEDS_REVIEW
    fresh = Parcel("TRK001", "SG")
    assert apply_event(fresh, ev("CXL", 5), MAPPING, NOW) == Outcome.APPLIED
