# 3PL Tracking Integration: PRD, API Spec and State Machine

A product-management portfolio project. It specifies how a regional e-commerce marketplace could take tracking events from many third-party logistics partners (3PLs) through **one standard integration**, and proves the business rules with executable acceptance tests.

> All companies, partners, numbers and targets are fictional or illustrative. No proprietary data is used.

## The problem

Each 3PL sends tracking updates in its own codes and timing. Buyers see stale or out-of-order tracking, every new partner is a custom build, and operations can't compare partners like-for-like.

## What's in the repo

| File | What it is |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | Requirements: problem, KPIs, scope, business rules and edge cases, 12 acceptance criteria, rollout milestones, risks |
| [`docs/openapi.yaml`](docs/openapi.yaml) | OpenAPI 3.0 spec: partner push endpoint (batched, signed, idempotent) and an internal read endpoint |
| [`docs/state-machine.md`](docs/state-machine.md) | Canonical parcel statuses from first-mile pickup through sorting, line-haul and last-mile, with allowed transitions |
| [`docs/status-mapping.csv`](docs/status-mapping.csv) | Partner status codes → canonical statuses for two fictional partners |
| [`docs/uat-scenarios.md`](docs/uat-scenarios.md) | 14 UAT scenarios for a pilot market, with entry/exit criteria and a defect log |
| `src/tracking/state_machine.py` | Reference implementation of the rules |
| `tests/` | 18 pytest tests: one per acceptance criterion, plus checks that the spec, mapping and state machine stay consistent |

## Key design decisions

- **Mapping is config, not code.** A new partner is new rows in `status-mapping.csv`; the state machine doesn't change (AC-10).
- **Never let bad data reach the buyer.** Out-of-order events are stored but don't roll status back; invalid transitions and unknown codes go to a review queue.
- **Accept, then quarantine.** Unknown codes return `quarantined` rather than an error, so partners don't retry forever.
- **Per-event outcomes in a batch (HTTP 207).** One bad event never fails the other 499.

## Run the tests

```bash
pip install -r requirements.txt
python -m pytest -q   # 18 passed
```

## Limitations

- Push only; partners that need polling are out of scope.
- No persistence, queueing or auth implementation. The code models business rules, not a production service.
- Market rules (attempt caps, clock skew) are illustrative assumptions.
