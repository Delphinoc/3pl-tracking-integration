# UAT scenarios: SG pilot with partner SLX

Run in the partner sandbox by SG logistics operations (business tester) and the SLX integration engineer. Each scenario lists the AC it covers. Record results in the defect log below.

**Entry criteria:** all automated AC tests pass; sandbox seeded with 20 test parcels; testers trained on the review queue.
**Exit criteria:** every P1/P2 scenario passes; no open P1/P2 defects; business owner signs off.

| ID | Priority | Scenario | Steps | Expected result | AC |
|---|---|---|---|---|---|
| UAT-01 | P1 | Standard delivery | SLX sends PU → HUB_IN → HUB_OUT → HUB_IN → OFD → DLV | Buyer page shows 6 steps in order, final "Delivered"; ops dashboard counts it on time | AC-01 |
| UAT-02 | P1 | Partner retry after timeout | Send OFD, then resend the same `event_id` | Response `duplicate`; buyer timeline shows OFD once | AC-02 |
| UAT-03 | P1 | Late hub scan | Send OFD, then an older HUB_OUT | Status stays "Out for delivery"; HUB_OUT appears in the timeline at its real time | AC-03 |
| UAT-04 | P1 | Failed delivery and reattempt | OFD → DF_NA → OFD → DLV | Attempt count 1; buyer sees "Delivery attempted", then "Delivered" | AC-01, AC-07 |
| UAT-05 | P1 | Attempt cap reached (SG = 3) | Three OFD → DF_NA cycles, then OFD | Fourth OFD lands in the review queue; RTS then accepted | AC-07 |
| UAT-06 | P1 | Unknown status code | Send code `HOLD` (not mapped) | Response `quarantined`; alert to integration support within 5 min; buyer page unchanged | AC-05 |
| UAT-07 | P2 | Skipped last mile | PU, then DLV | Review queue entry "PICKED_UP → DELIVERED"; buyer still sees "Picked up" | AC-04 |
| UAT-08 | P2 | Event after delivery | DLV, then DF_ADDR | Review queue entry; status stays "Delivered" | AC-06 |
| UAT-09 | P2 | Partner clock ahead | Event dated 30 min in the future | Response `rejected` with message; nothing stored | AC-08 |
| UAT-10 | P2 | Wrong market | Event with market `MY` for an SG parcel | Response `rejected` | AC-09 |
| UAT-11 | P2 | Mixed batch | Batch of 50 events, 3 malformed | HTTP 207; 47 processed, 3 rejected with reasons | PRD 6.5 |
| UAT-12 | P2 | Lost parcel | PU → HUB_IN → LOST | Buyer sees "Lost — we're contacting the partner"; refund flow can start | AC-11 |
| UAT-13 | P3 | Cancel after pickup | PU, then CXL | Review queue entry; no cancellation shown to buyer | AC-12 |
| UAT-14 | P3 | Review queue resolution | Ops resolves UAT-07 entry as "accept DELIVERED" | Status updates; action logged with operator ID | PRD 5.4 |

## Defect log template

| Defect ID | UAT ID | Severity (P1–P3) | Steps to reproduce | Expected | Actual | Owner | Status |
|---|---|---|---|---|---|---|---|
| | | | | | | | |
