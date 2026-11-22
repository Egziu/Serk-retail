# Audit trail and threat notes (M1)

## SERK Audit Event

Written for: `shift.opened`, `sale.completed`, `return.completed`, `shift.closed`,
`stock.received`, `receipt.reprint_requested`, `print.attempt`, `*.cancelled` (doc_events on
Sales Invoice, Purchase Receipt, POS Closing Entry), and **refusals** (`shift.open`,
`sale.submit`, `return.submit`, `shift.close` with outcome `Refused`).

Fields: actor, SERK roles held, approver, company, register, device id (advisory), correlation id
(`X-Correlation-ID` header or generated), reference document, reason, JSON details, event time,
`content_hash` = sha256 of the canonical event content.

Controller refuses update and delete (test_12).

## Limits (stated plainly)

* Tamper-*resistant* through the application only. Anyone with direct database access can alter
  rows and recompute `content_hash`. There is no hash chain and no independent sink yet.
* Refusal audit is committed after rolling back the request, which is only safe because every
  authorization check runs before any business write (R-07).
* Passwords, approval secrets and tokens are never written to audit details.

## M1 threat model slice

| Threat | Control in M1 | Status |
|---|---|---|
| Duplicate submission (double click, retry, replay of the same request) | Idempotency (ADR-004) | Tested |
| Request tampering with prices | Server ignores/rejects client prices | Tested |
| Cashier self-authorising refunds | Different-user supervisor approval with password | Tested |
| Brute-forcing supervisor password at register | — | **Open (R-08)** |
| Cross-shift / cross-register misuse | Ownership + assignment checks | Tested |
| Cross-tenant access | Separate site/DB per tenant (ADR-006) | Design only, untested |
| Malicious localhost/LAN access to a device bridge | No bridge exists yet | N/A |
| Mutable history | Submitted docs reversed only by cancel/credit note; cancels audited | Partly tested |
