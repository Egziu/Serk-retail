# Role matrix (M1)

Enforced server-side in `serk_retail/core/authz.py` and the API functions. ERPNext doctype
permissions for SERK roles are read-only except the narrow grants noted (ADR-003).

| Action | Cashier | Shift Supervisor | Store Manager | Receiver | Test |
|---|---|---|---|---|---|
| Receive stock | – | – | ✓ | ✓ | test_01 |
| Open shift on assigned register | ✓ | ✓ | – | – | test_07 |
| Open shift on unassigned register | ✗ refused + audited | ✗ | – | – | test_07 |
| Sell on own open shift | ✓ | – | – | – | test_01 |
| Sell on another cashier's shift | ✗ refused + audited | – | – | – | test_07 |
| Refund (needs a *different* supervisor's live approval) | ✓ requests | approves | approves | – | test_05, test_06 |
| Approve own refund | ✗ | ✗ | ✗ | – | test_06 |
| Reprint receipt (COPY, reason required) | ✓ own register | ✓ | ✓ | – | test_08 |
| Close own shift | ✓ | ✓ any | – | – | test_01, test_11 |
| View reconciliation | – | ✓ | ✓ | – | test_01 |
| Edit/delete audit events | ✗ (nobody, incl. System Manager via the app) | | | | test_12 |
| Supply prices/discounts from the client | ✗ (nobody in M1) | | | | test_09 |

## Narrow upstream grants (and why)

| DocType | Role | Rights | Reason |
|---|---|---|---|
| POS Opening Entry | SERK Cashier | write + submit, **if_owner**, no create | ERPNext closing saves the opening entry with permission checks (W-02) |
| POS Opening Entry | SERK Shift Supervisor | write + submit, no create | Supervisor closes another cashier's shift |

## Known gaps

No rate limit/lockout on supervisor approval (R-08). No device identity/enrollment yet
(`device_id` is advisory and recorded only). No MFA policy configured for privileged roles.
