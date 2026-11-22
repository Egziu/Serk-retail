# SERK Retail architecture (M1 as built)

## Logical boundaries (one deployable Frappe app today)

| Boundary | M1 module | State |
|---|---|---|
| SERK Retail Core | `core/` (authz, audit, idempotency, errors), `setup/` | Built |
| SERK POS | `api/pos.py`, `core/receipts.py` | API built; cashier UI not built |
| Retail Operations | `api/inventory.py` (receiving) | Receiving only |
| Device Bridge | `devices/printer.py` (adapter contract + simulator) | Simulator only |
| Branch Continuity | — | Planned M2 |
| AI Gateway | — | Planned M5 |
| Analytics | `core/reconciliation.py` (operational check) | Minimal |

## M1 sequence — sale

```mermaid
sequenceDiagram
  participant T as Register client
  participant A as serk_retail.api.pos.submit_sale
  participant I as Idempotency (same txn)
  participant E as ERPNext Sales Invoice
  participant DB as MariaDB
  participant Q as RQ short queue
  participant P as Printer adapter
  T->>A: items, tenders, idempotency_key
  A->>A: role + register + shift-owner checks (refusals audited)
  A->>I: lock/insert record sha256(op|shift|key)
  alt key seen, same payload
    I-->>T: stored response (idempotent_replay=true)
  else key seen, different payload
    I-->>T: IDEMPOTENCY_CONFLICT
  end
  A->>E: build is_pos invoice (price list, VAT), insert, submit
  E->>DB: GL Entry + Stock Ledger Entry (ERPNext posting rules)
  A->>DB: print job (Queued), audit event, record=Completed
  DB-->>A: COMMIT
  A-->>T: sale result (persisted before success)
  Q->>P: after commit: send receipt (drawer pulse once)
  P-->>Q: Acknowledged / Failed / Delivery Unknown (sale unaffected)
```

## Failure paths covered in M1

| Failure | Behaviour | Test |
|---|---|---|
| Double click / retry / concurrent duplicate | One sale; replay returns original | test_02, test_04 |
| Key reuse with different basket | Rejected, nothing written | test_03 |
| Insufficient stock or validation error mid-sale | Whole transaction rolls back incl. idempotency record | test_10 |
| Printer paper-out / offline | Sale stays submitted; retry allowed; no second drawer pulse | test_08 |
| Printer timeout | Delivery Unknown; resend refused; COPY required | test_08 |
| Over-refund (sequential) | Refused with remaining quantity | test_05 |
| Over-refund (concurrent) | Serialized by `FOR UPDATE` on the original invoice | test_13 |
| Unauthorised approver / self-approval | Refused and audited | test_06 |

## Not built (explicitly)

Cashier UI, offline mode, hardware bridge, non-cash tenders, promotions explainability,
multi-branch governance, AI gateway, deployment artifacts beyond the dev script.
