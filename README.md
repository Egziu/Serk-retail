# SERK Retail

Supermarket and retail operations on ERPNext — a custom Frappe app by SERK Technologies Group.
*Innovation with Integrity.*

**Status: M1 vertical slice (developer preview). Not production-ready, not fiscally approved,
no physical hardware qualified.** See [`docs/releases/M1_PHASE_REPORT.md`](docs/releases/M1_PHASE_REPORT.md).

## What works today (verified by tests on MariaDB)

Receive stock → open shift → sell (barcode/weighted/decimal, VAT, cash with change) → print
receipt (ESC/POS **simulator**) → supervisor-approved partial return → blind shift close →
independent reconciliation against GL and stock ledgers. Idempotent, concurrency-safe sale
submission; append-only audit trail; print failure never affects the sale; no second drawer pulse.

All accounting and stock posting is done by ERPNext's own Sales Invoice / Purchase Receipt /
POS Closing logic. SERK never writes ledger tables. ERPNext and Frappe are unmodified.

## Prerequisites

| Component | Version used for evidence |
|---|---|
| Frappe | 17.0.0-dev @ `fdb29e69` (develop) |
| ERPNext | 17.0.0-dev @ `20b97fa8` (develop; identical to the supplied ZIP) |
| Python | 3.14.6 (required `>=3.14,<3.15` by this Frappe) |
| Node | 24.22.3 (required `>=24`) |
| MariaDB | 10.11.14 |
| Redis | system `redis-server` |

## Setup, run, test

See [`scripts/dev_setup.sh`](scripts/dev_setup.sh) — the exact command sequence used. In short:

```bash
bench get-app <this repo>
bench --site <site> install-app serk_retail
bench --site <site> execute serk_retail.setup.demo.seed      # synthetic data only
bench --site <disposable-site> run-tests --module serk_retail.tests.test_m1_flow
bench --site <disposable-site> execute serk_retail.tests.mutation_check.run
```

**The M1 tests commit to the database** (they test real request boundaries and concurrency).
Run them only on a disposable site such as `serktest.localhost`.

### Reset synthetic data

```bash
bench drop-site serktest.localhost --db-root-password "$(cat ~/.db_root)" --force
bench new-site serktest.localhost --install-app erpnext --install-app serk_retail ...
```

## API (v1, `POST /api/method/...`, JSON body)

| Method | Role | Purpose |
|---|---|---|
| `serk_retail.api.inventory.receive_stock` | SERK Receiver / Store Manager | Purchase Receipt (stock + GL) |
| `serk_retail.api.pos.open_shift` | SERK Cashier | POS Opening Entry with float |
| `serk_retail.api.pos.submit_sale` | SERK Cashier | Idempotent POS sale |
| `serk_retail.api.pos.submit_return` | SERK Cashier + supervisor approval | Partial/full refund at original price/tax |
| `serk_retail.api.pos.reprint_receipt` | Cashier/Supervisor | Labelled COPY, audited, no drawer pulse |
| `serk_retail.api.pos.retry_print_job` | Cashier/Supervisor | Retry a *definitely failed* job only |
| `serk_retail.api.pos.close_shift` | Cashier (own) / Supervisor | Blind count, variance reason over tolerance |
| `serk_retail.api.pos.reconcile_shift` | Supervisor / Manager | Independent GL/stock/cash checks |

Every mutating call takes an `idempotency_key`. Same key + same payload returns the original
result (`idempotent_replay: true`); same key + different payload is rejected.

## Troubleshooting

* `POS Opening Entry Exists` — ERPNext allows one open shift per register (POS Profile). Close it.
* `Outdated POS Opening Entry` — shifts cannot cross midnight in this ERPNext version (gap G-07).
* `bench init` silently exits as root — run bench as a non-root user.
* `yarn install` engine error — Node ≥ 24 is required.

## Licence

GPL-3.0 (see `license.txt`). This app imports and extends ERPNext (GPL-3.0) and Frappe (MIT),
both © Frappe Technologies Pvt. Ltd. "Frappe" and "ERPNext" are Frappe Technologies trademarks;
SERK Retail is not endorsed by them. See `docs/engineering/SOURCE_PROVENANCE.md`.
