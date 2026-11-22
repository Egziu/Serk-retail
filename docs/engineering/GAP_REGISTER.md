# Gap register (evidence-based)

Status vocabulary: **Present** (works as-is, verified) · **Configurable** · **Extendable** (needs
SERK code on documented extension points) · **Missing** · **Defective** · **Unsupported** ·
**Not verified**. "Verified" means exercised by a test in this repo or the upstream baseline.

| ID | Capability | Status | Evidence / location | SERK action |
|---|---|---|---|---|
| G-01 | Double-entry GL posting for POS sales | Present (verified) | `sales_invoice` posting; `test_01` GL balanced; reconciliation `gl.vouchers_balanced` | Reuse |
| G-02 | Perpetual stock ledger on sale/receipt | Present (verified) | `test_01` Bin deltas; `stock.sle_vs_invoice_qty` | Reuse |
| G-03 | Server-side idempotency for POS submission | **Missing** | No idempotency key in `point_of_sale.py` / Sales Invoice; grep found none | **Built** (`core/idempotency.py`), mutation-tested |
| G-04 | Return quantity cap | Present | `validate_returned_items` | Reused + SERK pre-check under row lock for clear errors / concurrent refunds |
| G-05 | Supervisor approval / separation of duties for refunds | Missing | Upstream relies on role permissions only | **Built** (`verify_approver`) |
| G-06 | Blind count shift close with variance reason | Extendable | `POS Closing Entry Detail` has `closing_amount`/`difference`; no blind/tolerance policy | **Built** (`close_shift`) |
| G-07 | Shifts crossing midnight | **Unsupported** | `validate_pos_opening_entry` requires opening date == today | Open: business-date design (RET-POS-020) |
| G-08 | Multiple open shifts per register | Unsupported by design | one open entry per POS Profile | Accept: register = profile (ADR-005) |
| G-09 | Profile rounding copied to server-built invoices | **Defective (for server use)** | `disable_rounded_total` not copied; 425.50→426 observed | Worked around in SERK; candidate upstream issue |
| G-10 | Least-privilege cashier closing a shift | **Defective (for least privilege)** | `update_opening_entry()` saves with permission check | Narrow if_owner grant (ADR-003); candidate upstream fix |
| G-11 | Return mapper usable without create right | Defective (for least privilege) | `make_return_doc` has no `ignore_permissions` | Scoped non-writing system context, write-guarded |
| G-12 | Receipt print lifecycle, drawer-pulse safety | Missing | Upstream prints via browser print formats | **Built** (simulator only) |
| G-13 | Physical receipt printer / scale / drawer integration | Missing | — | Blocked: no hardware available (HARDWARE_COMPATIBILITY.md) |
| G-14 | Append-only audit trail for material actions | Missing (Version log exists, mutable by admins) | Frappe `Version` doctype | **Built** `SERK Audit Event` (limits documented) |
| G-15 | Independent shift reconciliation report | Missing | — | **Built** `reconciliation.py` |
| G-16 | Ethiopian regional (VAT/TOT, fiscal device, e-invoicing) | **Missing** | `regional/` has no Ethiopia | Blocked: needs fiscal/legal requirements and authority approval |
| G-17 | Ethiopian calendar presentation | Missing | — | Planned (RET-L10N-003) |
| G-18 | Amharic/Tigrinya receipts | Not verified | Frappe has translations framework; printers untested | Planned; M1 receipts ASCII-only |
| G-19 | Offline POS with durable journal | Missing in this version | Upstream POS needs the server | Planned M2 (branch continuity) |
| G-20 | Pricing rules / promotions / coupons / loyalty | Present (not verified by SERK) | `pricing_rule`, `promotional_scheme`, `coupon_code`, `loyalty_program` | M3: verify + explainability |
| G-21 | Batches, expiry, FEFO, serials | Present (not verified by SERK) | `batch`, `serial_and_batch_bundle` | M3 |
| G-22 | Weighted goods (decimal qty) | Present (verified) | `test_01` 1.25 kg teff | GS1 variable-measure barcode parsing planned |
| G-23 | Tenant isolation between unrelated customers | Unsupported via multi-company | ERPNext multi-company is not a security boundary | ADR-006: one site/DB per tenant |
| G-24 | Price override with supervisor | Missing in SERK API | client prices rejected | Planned RET-PRC-002 |
| G-25 | Non-cash tenders (mobile money, card) | Missing | — | Blocked: provider specs/credentials |
| G-26 | Approval brute-force protection | Missing | `check_password` used without lockout | Risk R-08 |
| G-27 | Benchmark of other retail platforms | Not started | — | BENCHMARK_MATRIX.md stub |
