"""Keep the API spec, status mapping and state machine in step."""

import csv
from pathlib import Path

import yaml

from tracking.state_machine import ALLOWED, TERMINAL, Outcome, Status

DOCS = Path(__file__).resolve().parents[1] / "docs"
SPEC = yaml.safe_load((DOCS / "openapi.yaml").read_text())
SCHEMAS = SPEC["components"]["schemas"]


def test_spec_status_enum_matches_state_machine():
    assert set(SCHEMAS["CanonicalStatus"]["enum"]) == {s.value for s in Status}


def test_spec_outcome_enum_matches_state_machine():
    spec_outcomes = SCHEMAS["EventResult"]["properties"]["outcome"]["enum"]
    assert set(spec_outcomes) == {o.value for o in Outcome}


def test_every_partner_maps_every_canonical_status_except_none_missing():
    rows = list(csv.DictReader(open(DOCS / "status-mapping.csv", encoding="utf-8")))
    by_partner = {}
    for r in rows:
        by_partner.setdefault(r["partner_id"], set()).add(r["canonical_status"])
    for partner, statuses in by_partner.items():
        assert statuses == {s.value for s in Status}, partner


def test_no_duplicate_partner_codes():
    rows = list(csv.DictReader(open(DOCS / "status-mapping.csv", encoding="utf-8")))
    keys = [(r["partner_id"], r["partner_status_code"]) for r in rows]
    assert len(keys) == len(set(keys))


def test_terminal_statuses_have_no_exits_and_others_can_reach_delivered_or_returned():
    for s in TERMINAL:
        assert not ALLOWED.get(s)
    # Every non-terminal status can still end in DELIVERED or RETURNED.
    for start in set(Status) - TERMINAL:
        seen, frontier = {start}, [start]
        while frontier:
            for nxt in ALLOWED.get(frontier.pop(), set()):
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append(nxt)
        assert {Status.DELIVERED, Status.RETURNED} & seen, start
