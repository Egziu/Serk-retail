# Architecture decisions (M0/M1)

## ADR-001 — Custom Frappe app on unmodified ERPNext; ERPNext is the ledger authority
**Decision.** All SERK code lives in `serk_retail` and uses documented extension points
(`hooks.py`, whitelisted APIs, doctypes, `doc_events`). ERPNext/Frappe trees stay clean
(verified: `git status` empty in both). SERK never writes `GL Entry`, `Stock Ledger Entry`, `Bin`.
**Why.** Preserves ERPNext's tested posting rules and keeps upgrades a rebase of one app.
**Consequence.** Upstream defects are worked around in SERK and logged in CORE_PATCH_REGISTER.

## ADR-002 — POS "Sales Invoice" mode
**Decision.** `POS Settings.invoice_type = Sales Invoice`. Each sale is a submitted Sales Invoice
(`is_pos=1, update_stock=1`) that posts GL and stock immediately.
**Rejected.** POS Invoice mode defers GL to consolidation at closing, so stock and revenue lag and
a failed consolidation leaves the day unposted.
**Trade-off.** One Sales Invoice per basket (more rows); acceptable for pilot volumes, to be
measured under the M4 load profile.

## ADR-003 — API gateway authorization for cashiers
**Decision.** SERK roles get read-only ERPNext permissions (plus the narrow grants listed in
`install.py`). SERK APIs check role, register assignment and shift ownership, then insert/submit
with `ignore_permissions` **as the real user**, so ownership, audit and closing selection remain
truthful.
**Why.** Granting `Accounts User` to cashiers would let them edit/cancel any invoice in the desk.
**Narrow grants.** Cashier write+submit on *own* POS Opening Entry (needed by upstream close);
supervisor write+submit on POS Opening Entry. Non-writing return mapping runs in a write-guarded
system context.

## ADR-004 — Idempotency and payment-state boundaries
**Decision.** Every mutating API takes an `idempotency_key`. Record name =
`sha256(operation|scope|key)`; inserted in the same DB transaction as the business effect;
concurrent duplicates serialize on the InnoDB primary-key lock; same key with a different
payload is rejected. Scope is the shift for sales/returns/closing, user+register for opening,
company for receiving.
**Evidence.** `test_02`, `test_03`, `test_04` (4 concurrent identical requests → 1 invoice) and
the mutation check (with the guard removed the same test produces 4 invoices).
**Payments.** M1 supports cash only. The design for provider tenders (not built) keeps
attempt/authorization/capture/settlement/refund as separate states, treats timeouts as
`pending reconciliation`, and never charges again on retry.

## ADR-005 — Organisational mapping
Company = legal entity. Warehouse = store stock location. **POS Profile = one register/lane**
(ERPNext allows one open shift per profile). POS Opening Entry = shift. A tenant (customer
organisation) = its own Frappe site and database (ADR-006).

## ADR-006 — Tenant isolation by site/database
ERPNext multi-company is a bookkeeping boundary, not a security boundary between unrelated
customers. Each customer tenant gets a separate Frappe site + database, cache namespace, files
path and backups. Company/branch scoping within a tenant is enforced per request. Not yet
load- or penetration-tested.

## ADR-007 — Pilot topology (proposed, not built)
Store-local server (ERPNext + MariaDB + Redis) on UPS with encrypted offsite backups; registers on
the store LAN. Survives internet loss without new software. Does **not** survive store-server
failure — that is the M2 branch-continuity work (durable terminal journal, bounded offline
policy, cash only offline). Chosen as the simplest topology that meets an internet-outage
requirement; revisit when the pilot's real outage profile is known.

## ADR-008 — Receipt printing via persistent jobs and adapters
Print jobs are rows created in the sale transaction and sent after commit (RQ, `short` queue).
Adapters implement `send(text, open_drawer) -> PrintResult`. States: Queued, Spooled,
Acknowledged, Failed, Delivery Unknown. Drawer pulse at most once per sale (marked before send).
Delivery Unknown is never auto-resent; operators issue a labelled COPY. Device Bridge language
decision deferred until real hardware is available (M2).
