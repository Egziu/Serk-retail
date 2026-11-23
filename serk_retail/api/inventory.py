# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Receiving API (v1). Posts an ERPNext Purchase Receipt, which creates stock ledger entries and
(with perpetual inventory) GL entries: Stock In Hand Dr / Stock Received But Not Billed Cr."""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from serk_retail.core import authz
from serk_retail.core.audit import log_event
from serk_retail.core.errors import InvalidRequest
from serk_retail.core.idempotency import run_idempotent


@frappe.whitelist(methods=["POST"])
def receive_stock(
	company: str,
	supplier: str,
	warehouse: str,
	items: list,
	idempotency_key: str,
	supplier_delivery_note: str | None = None,
	device_id: str | None = None,
) -> dict:
	authz.require_any_role((authz.RECEIVER, authz.MANAGER), "receive stock")
	if not isinstance(items, list) or not items:
		raise InvalidRequest(_("Receiving needs at least one line."))
	if frappe.db.get_value("Warehouse", warehouse, "company") != company:
		raise InvalidRequest(_("Warehouse {0} does not belong to {1}.").format(warehouse, company))
	for line in items:
		if not isinstance(line, dict) or not line.get("item_code"):
			raise InvalidRequest(_("Each received line needs an item_code."))
		if not frappe.db.exists("Item", {"name": line["item_code"], "is_stock_item": 1}):
			raise InvalidRequest(_("Unknown stock item {0}.").format(line["item_code"]))
		if flt(line.get("qty")) <= 0 or flt(line.get("rate")) < 0:
			raise InvalidRequest(_("Received quantity must be positive and cost cannot be negative."))

	payload = {"company": company, "supplier": supplier, "warehouse": warehouse, "items": items,
			   "supplier_delivery_note": supplier_delivery_note}

	def do():
		pr = frappe.get_doc(
			{
				"doctype": "Purchase Receipt",
				"company": company,
				"supplier": supplier,
				"posting_date": nowdate(),
				"set_warehouse": warehouse,
				"supplier_delivery_note": supplier_delivery_note,
				"items": [
					{"item_code": l["item_code"], "qty": flt(l["qty"]), "rate": flt(l["rate"]),
					 "warehouse": warehouse}
					for l in items
				],
			}
		)
		pr.flags.ignore_permissions = True
		pr.insert()
		pr.submit()
		log_event("stock.received", reference_doctype="Purchase Receipt", reference_name=pr.name,
				  company=company, device_id=device_id,
				  details={"lines": len(pr.items), "grand_total": flt(pr.grand_total)})
		return {"reference_doctype": "Purchase Receipt", "reference_name": pr.name,
				"purchase_receipt": pr.name, "grand_total": flt(pr.grand_total), "status": "received"}

	return run_idempotent("stock.receive", company, idempotency_key, payload, do)
