# M1 test evidence

Site `serktest.localhost` (disposable) · MariaDB 10.11.14 · Python 3.14.6 · Frappe `fdb29e69` ·
ERPNext `20b97fa8` · 2 vCPU / 7 GB RAM Linux VM · run 2026-11-22.
Command: `bench --site serktest.localhost run-tests --module serk_retail.tests.test_m1_flow --junit-xml-output m1_final.xml`

**Result: 13 passed, 0 failed, 0 skipped — 8.3 s** (also passed on two earlier runs over
accumulated data, so the suite is repeatable against a non-empty database).

| Test | Requirement(s) | What is proven |
|---|---|---|
| test_01 | RET-M1-001, INV-001, POS-001/004/008/012, PRC-001, HW-001 | Receive 24 + 10.5 kg (GL 1,266.00 Dr = Cr) → sale of 3 scanned waters + 1.25 kg teff + 2 injera: net 370.00, VAT 55.50, total 425.50, change 574.50 (values computed independently in the test) → receipt Acknowledged, 1 drawer pulse → supervisor-approved partial return 1 water + 0.25 kg at original price/tax (−69.00) → blind close counted 856.50, variance 0 → reconciliation: all ≥ 8 independent checks pass → company GL Dr = Cr |
| test_02 | POS-005 | Same key twice → same invoice, `idempotent_replay` true, one audit event |
| test_03 | POS-006 | Same key, different basket → `IdempotencyConflict`, no new invoice |
| test_04 | POS-007 | 4 concurrent threads, separate DB connections, same key → exactly 1 invoice |
| test_05 | POS-010 | Refund 3 of 2 refused; refund 2 ok; further refund 1 refused; net returned −2 |
| test_06 | SEC-002/003 | Self-approval, non-supervisor approver, wrong password, missing approval → all refused; 4 `Refused` audit rows persisted; no return created |
| test_07 | SEC-001 | Other cashier's shift, unassigned register, supervisor selling → refused |
| test_08 | HW-002/003/004 | Paper-out → Failed, sale intact, 1 pulse; retry → Acknowledged, still 1 pulse; COPY reprint → still 1 pulse; timeout → Delivery Unknown, resend refused |
| test_09 | POS-002/003/009 | Barcode without leading zeros unknown; numeric barcode refused; client rate refused; qty 0 refused; 57.49 for 57.50 refused; 57.50 accepted |
| test_10 | POS-013 | Stock shortfall → nothing persisted, not even the idempotency record |
| test_11 | POS-008 | Variance −7.50 without reason refused; with reason accepted, recorded, reconciliation still consistent |
| test_12 | SEC-005 | Audit event update and delete refused |
| test_13 | POS-011 | 3 concurrent full refunds of the same line → exactly 1 succeeds, 2 `RefundExceedsEntitlement` |

## Mutation check (do the tests protect anything?)

`bench --site serktest.localhost execute serk_retail.tests.mutation_check.run` replaces the
idempotency guard with a passthrough and runs test_02 and test_04:

```
FAIL test_02 ... AssertionError: 'ACC-SINV-2026-00059' != 'ACC-SINV-2026-00060'
FAIL test_04 ... AssertionError: 4 != 1
MUTANT KILLED: 2/2 tests failed with idempotency disabled
```

## Defects found and fixed during M1 (root causes, not weakened assertions)

1. Change 574.00 instead of 574.50 — ERPNext rounded to whole birr because the profile's
   `disable_rounded_total` is not copied server-side. Fixed in SERK (W-01); assertion unchanged.
2. Shift close PermissionError for a least-privilege cashier — upstream saves the opening entry
   with permission checks and update-after-submit requires `submit`. Narrow grant (W-02).
3. Return mapper PermissionError — `create` check without bypass. Write-guarded mapping context (W-03).
4. `make_sales_return` moved to `sales_invoice/mapper.py` in this version. Import fixed.
5. Refund remaining-quantity read could use a stale REPEATABLE READ snapshot under concurrency.
   Changed to a locking read; test_13 added.

## Not covered (explicitly)

Physical hardware · offline/crash-recovery · non-cash tenders · promotions/loyalty · batches/expiry ·
tax-inclusive pricing · load/performance · cross-tenant isolation · cashier UI/accessibility ·
multilingual receipts · backup/restore · upgrade rehearsal.

## HTTP smoke (real request path)

`scripts/http_smoke.sh serk.localhost http://127.0.0.1:8000` against `bench serve` — session login,
JSON request bodies, Frappe type validation, commit-before-response. Output:
[`evidence/http_smoke.txt`](evidence/http_smoke.txt). Same-key retry over HTTP returned the
same invoice with `idempotent_replay: true`; client-supplied price refused; blind close variance 0.
A first attempt (before stock was received on the dev site) correctly failed with
`NegativeStockError` and left no partial state.
