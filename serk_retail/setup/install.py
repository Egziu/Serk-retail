# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
import frappe

from serk_retail.core.authz import SERK_ROLES

# Read-only access the SERK roles need for ERPNext's own pricing/stock lookups during API calls.
# Write access to financial doctypes is intentionally NOT granted (ADR-003).
READ_DOCTYPES = (
	"Item", "Item Price", "Item Barcode", "Price List", "Customer", "POS Profile", "Mode of Payment",
	"Warehouse", "UOM", "Item Group", "Company", "Currency", "Sales Taxes and Charges Template",
	"Account", "Cost Center", "Supplier", "Sales Invoice", "POS Opening Entry", "POS Closing Entry",
	"Purchase Receipt", "Batch", "Serial No", "Pricing Rule",
)


# Narrow write grants required by upstream code paths that save with permission checks.
# ERPNext POS Closing Entry.update_opening_entry() calls opening_entry.save() without
# ignore_permissions; on a submitted document only allow-on-submit fields (status,
# pos_closing_entry) can change. Frappe checks the "submit" right for update-after-submit, so
# both write and submit are granted. Cashiers get them for their OWN entries only and still
# cannot create opening entries from the desk (create = 0).
WRITE_GRANTS = (
	("POS Opening Entry", "SERK Cashier", 1),  # if_owner
	("POS Opening Entry", "SERK Shift Supervisor", 0),
)


def after_install():
	ensure_roles()
	ensure_permissions()
	configure_pos_mode()


def after_migrate():
	ensure_roles()
	ensure_permissions()


def ensure_roles():
	for role in SERK_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def ensure_permissions():
	from frappe.permissions import add_permission, update_permission_property

	for role in SERK_ROLES:
		for dt in READ_DOCTYPES:
			if not frappe.db.exists("DocType", dt):
				continue
			if not frappe.db.exists("Custom DocPerm", {"parent": dt, "role": role, "permlevel": 0}):
				add_permission(dt, role, 0)
				for prop in ("write", "create", "delete", "submit", "cancel", "amend", "share", "export", "print", "email"):
					update_permission_property(dt, role, 0, prop, 0, validate=False)
				update_permission_property(dt, role, 0, "read", 1, validate=False)
	for dt, role, if_owner in WRITE_GRANTS:
		update_permission_property(dt, role, 0, "write", 1, validate=False)
		update_permission_property(dt, role, 0, "submit", 1, validate=False)
		update_permission_property(dt, role, 0, "if_owner", if_owner, validate=False)
	frappe.clear_cache()


def configure_pos_mode():
	"""ADR-002: Sales Invoice mode posts GL + stock at each sale (no end-of-day consolidation lag)."""
	frappe.db.set_single_value("POS Settings", "invoice_type", "Sales Invoice")
