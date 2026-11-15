# PRD: Standard Tracking-Event Integration for 3PL Partners

| | |
|---|---|
| Status | Draft for engineering review (portfolio exercise) |
| Markets | SG, MY, VN (pilot: SG) |
| Partners in scope | SLX (SG/MY), KGN (MY/VN). Both fictional |
| Owner | Delphino Chew (product) |

> Portfolio exercise. The marketplace, partners, numbers and targets are illustrative assumptions, not any real company's data.

## 1. Problem

A regional marketplace hands last-mile and some line-haul volume to 3PL partners. Each partner sends tracking updates in its own format and status codes, through a one-off integration.

What goes wrong today (assumed baseline):
- **Buyers see stale or wrong tracking.** Events arrive late, duplicated or out of order. A late "departed hub" can overwrite "out for delivery".
- **Every new partner is a new build.** Onboarding a 3PL takes weeks of custom mapping and testing per market.
- **Operations can't compare partners.** Status codes differ, so SLA and failed-delivery rates aren't like-for-like.
- **Bad data fails silently.** Unknown codes are dropped and nobody is alerted.

## 2. Goals and success metrics

| Metric | Baseline (assumed) | Target 3 months after go-live |
|---|---|---|
| Tracking freshness: share of in-flight parcels with an event in the last 24 h | 85% | ≥ 97% |
| Status regressions shown to buyers (per 10k parcels) | 40 | < 1 |
| Partner onboarding time (contract signed → live) | 6 weeks | ≤ 2 weeks |
| Partner events mapped to a canonical status | 92% | ≥ 99.5% |
| Buyer "where is my parcel" contacts per 1k orders | 18 | −20% |

**Guardrails:** API p99 latency < 500 ms per batch; no increase in partner-side retries.

## 3. Users

- **3PL partner engineers:** need one documented API and fast feedback on bad events.
- **Buyers:** see one consistent tracking timeline whatever the partner.
- **Logistics operations (per market):** monitor partner SLA, failed deliveries and quarantined events.
- **Partner management / commercial:** compare partners on the same metrics for reviews.

## 4. Scope

**In:** inbound tracking-event API (push), canonical status model and state machine, per-partner status mapping table, review queue for flagged events, read API for internal consumers.

**Out (later phases):** pulling events from partners that can't push, label and booking APIs, proof-of-delivery photos, billing reconciliation, cross-border customs events.

## 5. Solution overview

1. Partners `POST` batches of events to `/v1/partners/{partner_id}/tracking-events` (spec: `openapi.yaml`). Requests are signed with HMAC.
2. Each event is mapped from the partner's code to a **canonical status** using `status-mapping.csv`. The mapping is config, not code, so a new partner is a new set of rows.
3. The mapped event is applied to the parcel through the **state machine** (`state-machine.md`). The API returns a per-event outcome so partners can fix their own errors.
4. Flagged events (invalid transition, unmapped code, attempt cap) go to an operations **review queue**. The buyer view never shows them.

## 6. Business rules and edge cases

### 6.1 Ordering and duplicates
- **Idempotency:** `event_id` is unique per partner. A repeat is a no-op that returns `duplicate`. Partners retry on timeouts, so this happens often.
- **Out-of-order events:** an event older than the parcel's current status time is stored in history but **doesn't change current status** (`history_only`). Example: "departed hub" arriving after "out for delivery".
- **Clock skew:** events more than 15 minutes in the future are rejected. Partner clocks drift, and a future timestamp would block every real event after it.

### 6.2 Invalid data
- **Unmapped partner code:** event is accepted and quarantined (not rejected), status unchanged, and an alert goes to partner integration support. Rejecting would trigger endless partner retries.
- **Invalid transition** (for example PICKED_UP → DELIVERED with no last-mile scan): stored, flagged `needs_review`, status unchanged.
- **Wrong tracking number or market:** rejected with a message; nothing stored.

### 6.3 Terminal statuses
- DELIVERED, RETURNED, LOST and CANCELLED are final. Any later event is flagged for review. A "delivered" correction is a manual operations action, not a partner event.
- CANCELLED is only valid before pickup.
- LOST is allowed from any non-terminal status.

### 6.4 Failed deliveries
- Each DELIVERY_FAILED adds one attempt. Once a parcel reaches its market's maximum (illustrative: SG 3, MY 3, VN 2), another OUT_FOR_DELIVERY is flagged; only return-to-sender is accepted.
- `failure_reason` is optional in v1 but recorded, so operations can split failures into recipient-related and address-related.

### 6.5 Batches
- Up to 500 events per call, each processed independently (HTTP 207 with per-event results). One bad event never fails the batch.

## 7. Acceptance criteria

Each criterion has an automated test in `tests/test_acceptance.py` (same ID).

| ID | Given / When / Then |
|---|---|
| AC-01 | Given a new parcel, when valid events arrive in order through delivery, then each is `applied` and status ends DELIVERED |
| AC-02 | When the same `event_id` is sent twice, then the second returns `duplicate` and history has one entry |
| AC-03 | Given status OUT_FOR_DELIVERY, when an older IN_TRANSIT event arrives, then it's `history_only` and status stays OUT_FOR_DELIVERY |
| AC-04 | Given PICKED_UP, when DELIVERED arrives, then it's `needs_review` and status stays PICKED_UP |
| AC-05 | When a partner code isn't in the mapping, then the event is `quarantined` and flagged with partner and code |
| AC-06 | Given DELIVERED, when any later event arrives, then it's `needs_review` and status stays DELIVERED |
| AC-07 | Given a parcel at its market's attempt cap, when OUT_FOR_DELIVERY arrives, then it's `needs_review`; RETURNING_TO_SENDER is still `applied` |
| AC-08 | When `event_time` is > 15 min in the future, then it's `rejected` and not stored; within 15 min it's accepted |
| AC-09 | When tracking number or market doesn't match the parcel, then it's `rejected` |
| AC-10 | Given the same journey from two partners using different codes, then both produce the same canonical history |
| AC-11 | Given any non-terminal status, when LOST arrives, then it's `applied` |
| AC-12 | CANCELLED is `applied` before pickup and `needs_review` after |

## 8. Rollout

| Milestone | Exit criteria |
|---|---|
| M1 Design sign-off | Engineering lead agrees API spec, state machine and estimates |
| M2 Build + sandbox | All AC tests pass; partner sandbox open; SLX connected in sandbox |
| M3 UAT (SG) | All UAT scenarios (`uat-scenarios.md`) pass with SG operations and SLX; no open P1/P2 defects |
| M4 Pilot go-live | SLX live for 10% of SG volume, then 100% after 1 week if regressions < 1 per 10k |
| M5 Scale | KGN onboarded in MY/VN using mapping rows only, no code change |

**Go-live decision:** product and the SG logistics business owner, based on M3 results and pilot metrics.

**Adoption:** a partner integration guide and sandbox, review-queue training for market operations, and a weekly partner scorecard from the canonical data.

## 9. Risks and open questions

- **Risk:** partners can't change their payloads quickly. *Mitigation:* the mapping table absorbs code differences; only the envelope is fixed.
- **Risk:** the review queue grows faster than operations can clear it. *Mitigation:* alert thresholds per partner; auto-escalate if unmapped codes exceed 0.5% of a partner's daily events.
- **Open:** should buyers see a "delivery attempted" message for every failure, or only after the final attempt?
- **Open:** keep raw partner payloads for how long (storage cost vs dispute handling)?
- **Open:** do any markets need extra statuses, such as "ready for collection" at a pickup point?
