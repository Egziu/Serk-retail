# M0 baseline (2026-11-22)

## Skills requested by the brief

The brief asks to discover and apply "REA" and "Replica" skills. **Neither is installed in this
session** (the available skill list was checked; no skill with either name exists). Their meaning
was not guessed. Work proceeded with explicit source analysis, execution-based workflow
observation (UPSTREAM_MAP "behaviours discovered by execution"), and behaviour-driven tests.

## Environment

| Item | Value |
|---|---|
| Host | Linux 6.18 x86_64 VM, 2 vCPU, 7 GB RAM, cloud workspace |
| OS packages | MariaDB 10.11.14 (Ubuntu 24.04), redis-server, libmariadb-dev |
| Python | 3.14.6 (uv-managed CPython), bench 5.31.1 |
| Node / Yarn | 24.22.3 / 1.22.22 |
| Run-as | dedicated non-root `frappe` user |
| Frappe | `fdb29e69` (local branch `serk-pin-fdb29e69`) |
| ERPNext | `20b97fa8` (local branch `serk-pin-20b97fa8`) |
| Assets | **not built** (`--skip-assets`); desk UI was not exercised |

## Startup evidence

| Step | Result | Duration |
|---|---|---|
| `bench init` (root) | silently exited 1 → re-run as non-root user | — |
| `bench init` (Node 22) | failed: Frappe requires Node ≥ 24 | — |
| `bench init` (Node 24, pinned branch) | success | ~1.5 min |
| `bench get-app erpnext` | success (rewrote `islands/yarn.lock`; reverted) | ~1 min |
| `bench new-site serk.localhost --install-app erpnext` | success | 84 s |
| `bench new-site test.localhost` (upstream tests) | success | ~85 s |
| `bench new-site serktest.localhost --install-app erpnext --install-app serk_retail` | success | ~90 s |
| `serk_retail.setup.demo.seed` (setup wizard Ethiopia/ETB, company, items, registers, users) | success | < 1 min |

## Upstream baseline tests (before SERK code was exercised; site `test.localhost`)

| Module | Run 1 | Run 2 (after installing `freezegun`) |
|---|---|---|
| pos_opening_entry | 12 passed (23 s) | — |
| pos_invoice | 50 passed (142 s) | — |
| pos_invoice_merge | 3 passed (10 s) | — |
| pos_closing_entry | 28 passed (106 s) | — |
| purchase_receipt | 223 passed, **3 errors** (`ModuleNotFoundError: freezegun`) | **226 passed** (241 s) |
| erpnext.tests.test_point_of_sale | — | 3 passed (2 s) |
| sales_invoice | — | **179 passed** (189 s) |
| **Total** | | **501 passed, 0 failed, 0 skipped** |

The 3 run-1 errors were an environment gap (missing dev dependency), not product defects. Full
ERPNext suite (584 test files) **not executed** — only retail-relevant modules. PostgreSQL
not tested. Logs: `~/baseline/*.log` on the build host (not committed; large).

## Commands

```bash
bench --site test.localhost run-tests --module erpnext.accounts.doctype.pos_invoice.test_pos_invoice --junit-xml-output <file>
# (same pattern for each module above)
```
