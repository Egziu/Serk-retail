# Core patch register

**Core patches applied: none.** `apps/erpnext` = `20b97fa8`, `apps/frappe` = `fdb29e69`, both with
an empty `git status` at the M1 checkpoint.

## Workarounds for upstream behaviour (in SERK code, not core)

| ID | Upstream behaviour | Workaround | Location | Upstream alternative |
|---|---|---|---|---|
| W-01 | Server-built POS Sales Invoice ignores `POS Profile.disable_rounded_total` | Copy explicitly | `api/pos.py` `submit_sale` | Copy field in `POSService._copy_pos_profile_fields` |
| W-02 | `POS Closing Entry.update_opening_entry()` saves with permission check | if_owner write+submit grant on POS Opening Entry | `setup/install.py` `WRITE_GRANTS` | `opening_entry.save(ignore_permissions=True)` or `db_set` upstream |
| W-03 | `make_return_doc` checks `create` on Sales Invoice, no bypass arg | Run mapping only in `system_context_for_pure_mapping`, which raises if any DB write occurs | `core/authz.py`, `api/pos.py` | Accept `ignore_permissions` in `make_return_doc` |

Each workaround is covered by `test_01`/`test_05`/`test_11`; an upstream change will surface
as a test failure rather than silent behaviour drift.
