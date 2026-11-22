# Upstream map (ERPNext @ 20b97fa8, Frappe @ fdb29e69)

Scale: 540 doctypes, 3,143 Python files, 584 test files, 585 registered patches, 21 modules
(Accounts, CRM, Buying, Projects, Selling, Setup, Manufacturing, Stock, Support, Utilities,
Assets, Portal, Maintenance, Regional, ERPNext Integrations, Quality Management, Communication,
Telephony, Bulk Transaction, Subcontracting, EDI).

## Boot and runtime

* `bench start` → gunicorn (web), RQ workers (`short`/`default`/`long`), scheduler,
  socket.io (Node), Redis cache + queue, MariaDB (or PostgreSQL; ERPNext CI tests both).
* App hooks: `erpnext/hooks.py` (`doc_events`, `scheduler_events` every 15 min and others,
  `after_install = erpnext.setup.install.after_install`).
* Setup: `frappe.desk.page.setup_wizard.setup_wizard.setup_complete` → ERPNext stages
  `stage_fixtures`, `setup_company`, `setup_defaults` (`erpnext/setup/setup_wizard/`).

## Retail-relevant flows SERK builds on

| Concern | Upstream location | How SERK uses it |
|---|---|---|
| POS mode switch | `accounts/doctype/pos_settings` (`invoice_type`: Sales Invoice / POS Invoice) | SERK sets **Sales Invoice** mode (ADR-002) |
| Sale posting | `accounts/doctype/sales_invoice` + `services/pos.py` (`POSService`) | API builds an `is_pos=1, update_stock=1` Sales Invoice; ERPNext posts GL + SLE |
| Register/session | `pos_profile`, `pos_opening_entry`, `pos_closing_entry` | 1 register = 1 POS Profile; shift = opening entry |
| Session invoice selection | `pos_closing_entry.build_invoice_query` (owner == cashier, profile, time window, `is_created_using_pos`, no closing) | SERK keeps the cashier as document owner |
| One open shift per profile | `POSService.validate_pos_opening_entry` | Enforced upstream; also requires same calendar day |
| Returns | `sales_invoice/mapper.make_sales_return` → `controllers/sales_and_purchase_return.make_return_doc`, `validate_returned_items` | Mapper keeps original rate/tax; SERK pre-checks remaining qty under a row lock |
| Receiving | `stock/doctype/purchase_receipt` | Wrapped by `receive_stock` |
| Stock ledger | `stock/stock_ledger.py`, `Bin`, `Stock Ledger Entry` | Read-only in reconciliation |
| GL | `accounts/general_ledger.py`, `GL Entry` | Read-only in reconciliation |
| Barcodes | `stock/doctype/item_barcode` | Lookup by exact string |
| Pricing/promotions | `pricing_rule`, `promotional_scheme`, `coupon_code`, `loyalty_program` | Applied by ERPNext during `set_missing_values`; SERK-specific explainability is M3 |
| Batches/serials | `batch`, `serial_no`, `serial_and_batch_bundle` | Not used in M1 |
| POS desk UI | `selling/page/point_of_sale/*.js` | Not modified; SERK cashier UI is future work |
| Permissions | Frappe role/DocPerm + `has_permission` hooks (e.g. `company_restriction.has_inherited_permission`) | SERK API gateway pattern (ADR-003) |
| Regional | `regional/` has AU, IT, ZA, TR, AE, US — **no Ethiopia** | Ethiopian VAT/fiscal device work is a gap |

## Behaviours discovered by execution (not visible from reading alone)

1. `POS Profile.disable_rounded_total` is **not copied** to a Sales Invoice built server-side;
   ETB default rounding produced a whole-birr total (425.50 → 426.00). SERK sets it explicitly.
2. `POS Closing Entry.on_submit → update_opening_entry()` saves the opening entry **with**
   permission checks, and update-after-submit requires the **submit** right.
3. `make_return_doc` → `get_mapped_doc` checks **create** on Sales Invoice with no bypass parameter.
4. `bench init` exits silently when run as root under a non-interactive shell.
5. Frappe develop requires Node ≥ 24 and Python 3.14.
