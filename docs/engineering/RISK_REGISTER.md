# Risk register

Likelihood/Impact: L/M/H. Owner "SERK Eng" unless stated.

| ID | Risk | L | I | Mitigation / status |
|---|---|---|---|---|
| R-01 | Building on ERPNext/Frappe **develop** (pre-release) — APIs and schemas can change daily | H | H | Pin commits (done). Before pilot, rebase onto a supported stable line and rerun all suites. |
| R-02 | Frappe commit is a time-based pairing, not an official pin | M | M | Baseline tests passed on the pairing; re-verify on every bump. |
| R-03 | No fiscal/tax approval for Ethiopia; VAT 15% exclusive is a synthetic test assumption | H | H | **Blocked** pending fiscal requirements and authority guidance. No production sales. |
| R-04 | No physical hardware qualified | H | H | Simulator only; HARDWARE_COMPATIBILITY.md lists none as supported. |
| R-05 | No offline operation: a server or LAN outage stops checkout | H | H | M2 branch-continuity design; until then pilot needs store-local server + UPS. |
| R-06 | Workarounds for upstream least-privilege defects (G-10, G-11) may break on upgrade | M | M | Recorded in CORE_PATCH_REGISTER; tests fail loudly if behaviour changes. |
| R-07 | Refusal audit uses rollback-then-commit; safe only because checks precede writes | M | M | Enforced by code review rule in `audit.py`; add a static check later. |
| R-08 | Supervisor password at the register: no rate limit/lockout, shoulder-surfing risk | M | H | Planned: per-approver lockout, PIN/badge with separate secret, audit alerting. |
| R-09 | Audit table is tamper-*resistant* only through the app; DB admins can alter rows | M | M | Planned: export to independently controlled sink; content_hash verification job. |
| R-10 | Idempotency records grow without bound | L | M | Retention/purge policy design pending (must outlive replay window and backups). |
| R-11 | Amharic/Tigrinya glyphs unsupported in ESC/POS text mode | H | M | M1 ASCII receipts; validated raster rendering needed. |
| R-12 | Shifts cannot cross midnight (G-07) | M | M | Operational rule for pilot: close before midnight. |
| R-13 | Upstream `islands/yarn.lock` incomplete at this commit; `yarn install` rewrites it | M | L | Reverted; reproducible frontend builds need a lockfile strategy. |
| R-14 | Tests commit to the DB; running them on a real site would add synthetic sales | L | H | Documented; dedicated disposable site; future: guard that refuses non-test sites. |
| R-15 | Synthetic cash-only scope: card/mobile money unknown-outcome handling not yet exercised | H | H | Blocked on provider specs; design in ADR-004 already separates payment state. |
| R-16 | `developer_mode` returns full server tracebacks in API errors (observed in HTTP smoke on the dev site) | M | M | Dev only. Production profile must disable developer_mode; SERK error contract to return code + safe message only. |
