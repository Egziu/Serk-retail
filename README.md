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

## SERK platform layer (2026-11-23)

* **SERK identity everywhere** — login, apps screen, rail, favicon, splash, tab titles, web and
  email footers show the company's brand, never upstream product names. Configured in
  **SERK Brand Settings** (name, legal name, motto, logo, favicon, primary/accent/sidebar/background
  colours, sidebar style, corner style, chart palette, contacts). Defaults follow the SERK family
  palette shared with SERK Finance (`#166453` primary, `#153335` sidebar). Done through documented
  extension points only (settings, `extend_bootinfo`, `update_website_context`, template precedence).
* **Command Center** (`/desk/serk-command-center`) — live KPIs with deltas and sparklines; revenue
  history plus a 14/30-day forecast (Holt trend + weekday seasonality) with an 80% band and a
  holdout-backtest accuracy figure; weekday x hour heatmap; category momentum; product ABC and
  ledger margins; stock intelligence (days of cover, stock-out, order-up-to at 95% service);
  basket affinity (lift); register and cashier performance with refund-rate outliers; anomaly
  detection; a rule-based insight feed that works without AI.
* **AI Analyst** (`/desk/serk-ai-analyst`, also embedded in the Command Center) — executive
  briefing, forecast & demand plan, market & category analysis, and grounded Q&A. Anthropic or
  OpenAI, configured exactly like SERK Finance (`SERK_AI_PROVIDER`, `SERK_AI_MODEL`,
  `SERK_AI_API_KEY`, `SERK_AI_BASE_URL`, or **SERK AI Settings**). The model receives aggregated
  figures only (no customer data; cashiers pseudonymised), has no tools, cannot write, and every
  call is audited. It has no live internet data: market analysis uses your category/basket trends
  plus the market context you enter.
* **Company Setup** (`/desk/serk-setup`) — progress checklist and guided creation of companies
  (chart of accounts, Ethiopian or Gregorian fiscal year, VAT template, price list, walk-in
  customer, cash tender, first store, brand), stores, registers with cashiers, and staff logins
  with SERK roles (temporary password shown once). All actions audited.

Upstream copyright and licence notices remain in the source (GPL-3.0 / MIT); only the user
interface carries the SERK brand.

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
bench --site <disposable-site> run-tests --module serk_retail.tests.test_platform
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
| `serk_retail.api.insights.dashboard` (GET) | Supervisor / Manager | Command Center analytics snapshot |
| `serk_retail.api.insights.ai_brief` | Supervisor / Manager | AI briefing: `insights`, `forecast`, `market` |
| `serk_retail.api.insights.ai_ask` | Supervisor / Manager | Grounded AI Q&A |
| `serk_retail.api.setup.state` (GET) | Manager / System Manager | Setup checklist and inventory |
| `serk_retail.api.setup.create_company` | System Manager | Company + retail defaults |
| `serk_retail.api.setup.create_store` / `create_register` | Manager / System Manager | Stores and registers |
| `serk_retail.api.setup.create_staff` | System Manager | Staff login with SERK role |

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
