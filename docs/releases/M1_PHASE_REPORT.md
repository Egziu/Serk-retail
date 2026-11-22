# Phase report — M0 complete, M1 first slice complete (2026-11-22)

## What works and how it was verified

| Capability | State | Evidence |
|---|---|---|
| Archive provenance | **Verified**: ZIP ≡ `frappe/erpnext@20b97fa8` | SOURCE_PROVENANCE.md |
| Reproducible runtime (Frappe+ERPNext develop, MariaDB, Redis) | **Implemented** | scripts/dev_setup.sh, BASELINE.md |
| Upstream baseline (POS, POS closing/merge, Purchase Receipt, Point of Sale, Sales Invoice) | **Executed** | BASELINE.md |
| Receive → sell → receipt → return → close → reconcile | **Implemented + tested** | M1_TEST_EVIDENCE.md test_01 |
| Idempotent, concurrency-safe sale/return/close | **Implemented + tested + mutation-checked** | test_02–04, 13 |
| Refund cap, separation of duties, refusal audit | **Implemented + tested** | test_05, 06 |
| Receipt print lifecycle, drawer-pulse safety | **Simulated** (no hardware) | test_08 |
| Append-only audit | **Implemented + tested** (limits documented) | test_12, AUDIT.md |

## Incomplete / blocked

| Item | Status | Needed |
|---|---|---|
| Physical printers, drawers, scales, scanners | **Blocked** | Real devices on the target OS |
| Ethiopian fiscal/VAT compliance (incl. fiscal device / e-invoice) | **Blocked** | Requirements + authority guidance; VAT 15% here is synthetic |
| Card / mobile-money tenders | **Blocked** | Provider specs, sandbox credentials |
| Offline checkout (M2) | **Planned** | — |
| Cashier UI | **Planned** | SERK cashier UI not built; upstream desk POS UI not exercised (assets not built in this environment) |
| Benchmark matrix | **Not started** | — |
| CI | **Authored, not executed** | Push to a GitHub repo |
| Production readiness | **No** | M2–M6 gates |

## Material risks

R-01 develop-branch base · R-03 no fiscal approval · R-05 no offline · R-08 approval brute-force.

## Next executable step

M2 slice 1: business-date design for shifts across midnight (G-07) and refund-to-original-tender,
then a durable branch-continuity journal spike; in parallel qualify one real 80 mm ESC/POS
printer + drawer if the hardware is available. Decision needed from the owner: pilot store
hardware list and whether the pilot can run on a store-local server (ADR-007).
