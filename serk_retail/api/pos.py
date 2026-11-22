# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""SERK POS API (v1): open shift -> sell -> receipt -> return -> close -> reconcile.

Accounting/stock authority stays with ERPNext: every sale and refund is a submitted ERPNext
Sales Invoice in "Sales Invoice" POS mode (is_pos=1, update_stock=1), which posts GL and stock
ledger entries at submit through ERPNext's own posting rules. SERK never writes ledger tables.

Versioning: these endpoints are `serk_retail.api.pos.*` v1. Breaking changes get a new module.
"""

import frappe
from erpnext.accounts.doctype.sales_invoice.services.pos import POSService
from frappe import _
from frappe.utils import cint, flt, now_datetime, nowdate

from serk_retail.core import authz, receipts
from serk_retail.core.audit import log_event, log_refusal_and_raise
from serk_retail.core.errors import (
	InsufficientPayment,
	InvalidRequest,
	NotAuthorized,
	RefundExceedsEntitlement,
	ShiftStateError,
)
from serk_retail.core.idempotency import run_idempotent

MAX_LINES = 500


# ----------------------------------------------------------------------------- helpers


def _get_open_shift(pos_opening_entry: str):
	opening = frappe.db.get_value(
		"POS Opening Entry",
		pos_opening_entry,
		["name", "status", "docstatus", "user", "pos_profile", "company", "period_start_date"],
		as_dict=True,
		for_update=True,
	)
	if not opening:
		raise ShiftStateError(_("Shift {0} does not exist.").format(pos_opening_entry))
	if opening.docstatus != 1 or opening.status != "Open":
		raise ShiftStateError(_("Shift {0} is not open (status: {1}).").format(opening.name, opening.status))
	return opening


def _assert_shift_owner(opening):
	if opening.user != frappe.session.user:
		raise NotAuthorized(_("Shift {0} belongs to another cashier.").format(opening.name))


def _resolve_item(line: dict) -> str:
	"""Barcode or item code -> item code. Barcodes are strings; leading zeros are preserved."""
	barcode = line.get("barcode")
	if barcode is not None:
		if not isinstance(barcode, str):
			raise InvalidRequest(_("Barcode must be sent as a string to preserve leading zeros."))
		item_code = frappe.db.get_value("Item Barcode", {"barcode": barcode}, "parent")
		if not item_code:
			raise InvalidRequest(_("Unknown barcode {0}. Look the product up by name or set it aside.").format(barcode))
		return item_code
	item_code = line.get("item_code")
	if not item_code or not frappe.db.exists("Item", {"name": item_code, "disabled": 0, "is_sales_item": 1}):
		raise InvalidRequest(_("Unknown or unsellable item {0}.").format(item_code))
	return item_code


def _qty(line: dict) -> float:
	try:
		qty = flt(line.get("qty"))
	except Exception:
		raise InvalidRequest(_("Quantity must be a number."))
	if qty <= 0:
		raise InvalidRequest(_("Quantity must be greater than zero."))
	return qty


def _validate_lines(items):
	if not isinstance(items, list) or not items:
		raise InvalidRequest(_("A sale needs at least one line."))
	if len(items) > MAX_LINES:
		raise InvalidRequest(_("Too many lines in one basket (max {0}).").format(MAX_LINES))
	for line in items:
		if not isinstance(line, dict):
			raise InvalidRequest(_("Each line must be an object."))
		if "rate" in line or "price" in line or "discount" in line:
			# Prices come from the price list; overrides need a supervised workflow (planned, RET-PRC-002).
			raise InvalidRequest(_("Client-supplied prices are not accepted."))


def _apply_payments(si, payments):
	if not isinstance(payments, list) or not payments:
		raise InvalidRequest(_("At least one tender is required."))
	POSService(si).reset_mode_of_payments()
	by_mode = {p.mode_of_payment: p for p in si.payments}
	seen = set()
	for p in payments:
		mode = p.get("mode_of_payment")
		amount = flt(p.get("amount"))
		if mode not in by_mode:
			raise InvalidRequest(_("Tender {0} is not enabled on this register.").format(mode))
		if mode in seen:
			raise InvalidRequest(_("Tender {0} listed twice.").format(mode))
		if amount <= 0:
			raise InvalidRequest(_("Tender amounts must be positive."))
		seen.add(mode)
		by_mode[mode].amount = amount
	si.set("payments", [p for p in si.payments if flt(p.amount)])


def _sale_response(si, print_job, operation):
	return {
		"operation": operation,
		"reference_doctype": "Sales Invoice",
		"reference_name": si.name,
		"sales_invoice": si.name,
		"currency": si.currency,
		"grand_total": flt(si.grand_total),
		"paid_amount": flt(si.paid_amount),
		"change_amount": flt(si.change_amount),
		"print_job": print_job,
		"status": "completed",
	}


# ----------------------------------------------------------------------------- shift


@frappe.whitelist(methods=["POST"])
def open_shift(
	pos_profile: str, opening_cash: float, idempotency_key: str, device_id: str | None = None
) -> dict:
	authz.require_any_role((authz.CASHIER, authz.SUPERVISOR), "open a shift")
	try:
		authz.require_register_assignment(pos_profile)
	except NotAuthorized as e:
		log_refusal_and_raise(e, "shift.open", pos_profile=pos_profile, device_id=device_id)
	if flt(opening_cash) < 0:
		raise InvalidRequest(_("Opening float cannot be negative."))

	payload = {"pos_profile": pos_profile, "opening_cash": flt(opening_cash)}

	def do():
		profile = frappe.get_cached_doc("POS Profile", pos_profile)
		cash_mode = _cash_mode(profile)
		oe = frappe.get_doc(
			{
				"doctype": "POS Opening Entry",
				"period_start_date": now_datetime(),
				"posting_date": nowdate(),
				"company": profile.company,
				"pos_profile": pos_profile,
				"user": frappe.session.user,
				"balance_details": [{"mode_of_payment": cash_mode, "opening_amount": flt(opening_cash)}],
			}
		)
		oe.flags.ignore_permissions = True
		oe.insert()
		oe.submit()
		log_event(
			"shift.opened",
			reference_doctype="POS Opening Entry",
			reference_name=oe.name,
			company=profile.company,
			pos_profile=pos_profile,
			device_id=device_id,
			details={"opening_cash": flt(opening_cash)},
		)
		return {
			"reference_doctype": "POS Opening Entry",
			"reference_name": oe.name,
			"pos_opening_entry": oe.name,
			"status": "open",
		}

	return run_idempotent("shift.open", f"{frappe.session.user}|{pos_profile}", idempotency_key, payload, do)


def _cash_mode(profile) -> str:
	for row in profile.payments:
		if frappe.get_cached_value("Mode of Payment", row.mode_of_payment, "type") == "Cash":
			return row.mode_of_payment
	raise InvalidRequest(_("Register {0} has no Cash tender configured.").format(profile.name))


# ----------------------------------------------------------------------------- sale


@frappe.whitelist(methods=["POST"])
def submit_sale(
	pos_opening_entry: str,
	items: list,
	payments: list,
	idempotency_key: str,
	customer: str | None = None,
	device_id: str | None = None,
) -> dict:
	authz.require_any_role((authz.CASHIER,), "sell")
	opening = _get_open_shift(pos_opening_entry)
	try:
		_assert_shift_owner(opening)
		authz.require_register_assignment(opening.pos_profile)
	except NotAuthorized as e:
		log_refusal_and_raise(e, "sale.submit", pos_profile=opening.pos_profile, device_id=device_id)
	_validate_lines(items)

	payload = {"opening": opening.name, "items": items, "payments": payments, "customer": customer}

	def do():
		profile = frappe.get_cached_doc("POS Profile", opening.pos_profile)
		si = frappe.new_doc("Sales Invoice")
		si.update(
			{
				"is_pos": 1,
				"is_created_using_pos": 1,
				"pos_profile": profile.name,
				"company": profile.company,
				"customer": customer or profile.customer,
				"update_stock": 1,
				"set_warehouse": profile.warehouse,
				# Rounding policy is the register profile's, explicitly (ERPNext does not copy it).
				"disable_rounded_total": cint(profile.disable_rounded_total),
			}
		)
		for line in items:
			si.append(
				"items",
				{"item_code": _resolve_item(line), "qty": _qty(line), "warehouse": profile.warehouse},
			)
		si.set_missing_values()
		_apply_payments(si, payments)
		si.calculate_taxes_and_totals()
		due = flt(si.rounded_total) or flt(si.grand_total)
		if flt(si.paid_amount, si.precision("paid_amount")) < flt(due, si.precision("grand_total")):
			raise InsufficientPayment(
				_("Tendered {0} is less than the total {1}. Collect the balance or remove items.").format(
					flt(si.paid_amount), due
				)
			)
		si.flags.ignore_permissions = True
		si.insert()
		si.submit()
		has_cash = any(
			frappe.get_cached_value("Mode of Payment", p.mode_of_payment, "type") == "Cash" for p in si.payments
		)
		job = receipts.create_print_job(si, drawer_pulse=has_cash)
		log_event(
			"sale.completed",
			reference_doctype="Sales Invoice",
			reference_name=si.name,
			company=si.company,
			pos_profile=si.pos_profile,
			device_id=device_id,
			details={"grand_total": flt(si.grand_total), "lines": len(si.items), "print_job": job},
		)
		receipts.enqueue_print(job)
		return _sale_response(si, job, "sale")

	return run_idempotent("sale.submit", opening.name, idempotency_key, payload, do)


# ----------------------------------------------------------------------------- return


def _refundable(original_name: str) -> dict:
	"""Remaining refundable quantity per original line (stock qty), from submitted returns."""
	orig = frappe.get_all(
		"Sales Invoice Item", filters={"parent": original_name}, fields=["name", "item_code", "qty"]
	)
	returned_map = {}
	if orig:
		# Locking read: under REPEATABLE READ a plain SELECT could use a snapshot taken before we
		# waited on the original-invoice lock and miss a refund committed meanwhile.
		for row, qty in frappe.db.sql(
			"""select sales_invoice_item, sum(qty) from `tabSales Invoice Item`
			where docstatus = 1 and sales_invoice_item in %(rows)s group by sales_invoice_item
			for update""",
			{"rows": tuple(r.name for r in orig)},
		):
			returned_map[row] = -flt(qty)  # return lines carry negative qty
	return {r.name: {"item_code": r.item_code, "remaining": flt(r.qty) - returned_map.get(r.name, 0)} for r in orig}


@frappe.whitelist(methods=["POST"])
def submit_return(
	pos_opening_entry: str,
	return_against: str,
	items: list,
	reason: str,
	idempotency_key: str,
	approver: str | None = None,
	approver_password: str | None = None,
	device_id: str | None = None,
) -> dict:
	"""Partial or full refund against an original sale, at the original line prices and taxes.

	items: [{"original_line": <Sales Invoice Item name>, "qty": 1}] or [{"item_code": ..., "qty": ...}]
	"""
	authz.require_any_role((authz.CASHIER,), "process a refund")
	opening = _get_open_shift(pos_opening_entry)
	ctx = {"pos_profile": opening.pos_profile, "device_id": device_id,
		   "reference_doctype": "Sales Invoice", "reference_name": return_against}
	try:
		_assert_shift_owner(opening)
		if cint(frappe.db.get_single_value("SERK Retail Settings", "require_approval_for_returns")):
			authz.verify_approver(approver, approver_password, frappe.session.user)
	except NotAuthorized as e:
		log_refusal_and_raise(e, "return.submit", approver=approver, **ctx)
	if not (reason or "").strip():
		raise InvalidRequest(_("A refund reason is required."))
	if not isinstance(items, list) or not items:
		raise InvalidRequest(_("Select at least one line to refund."))

	payload = {"opening": opening.name, "return_against": return_against, "items": items, "reason": reason}

	def do():
		# Serialize refunds against the same original sale (prevents concurrent over-refund).
		original = frappe.db.get_value(
			"Sales Invoice", return_against, ["name", "docstatus", "is_return", "company", "is_pos"],
			as_dict=True, for_update=True,
		)
		if not original or original.docstatus != 1 or original.is_return or not original.is_pos:
			raise InvalidRequest(_("{0} is not a completed POS sale.").format(return_against))
		if original.company != opening.company:
			raise NotAuthorized(_("Refunds across companies are not allowed."))

		remaining = _refundable(return_against)
		wanted = {}
		for line in items:
			qty = _qty(line)
			row = line.get("original_line")
			if not row:
				candidates = [n for n, r in remaining.items() if r["item_code"] == line.get("item_code")]
				row = candidates[0] if candidates else None
			if row not in remaining:
				raise InvalidRequest(_("Line {0} is not on sale {1}.").format(line, return_against))
			wanted[row] = wanted.get(row, 0) + qty
		for row, qty in wanted.items():
			if qty - remaining[row]["remaining"] > 1e-9:
				raise RefundExceedsEntitlement(
					_("Cannot refund {0} of {1}: only {2} remain refundable.").format(
						qty, remaining[row]["item_code"], remaining[row]["remaining"]
					)
				)

		from erpnext.accounts.doctype.sales_invoice.mapper import make_sales_return

		with authz.system_context_for_pure_mapping():
			ret = make_sales_return(return_against)
		ret.set("items", [it for it in ret.items if it.sales_invoice_item in wanted])
		for it in ret.items:
			it.qty = -wanted[it.sales_invoice_item]
		ret.update(
			{
				"is_pos": 1,
				"is_created_using_pos": 1,
				"pos_profile": opening.pos_profile,
				"update_stock": 1,
				"remarks": f"Refund: {reason}"[:1000],
			}
		)
		ret.set_posting_time = 0
		ret.posting_date = nowdate()
		ret.calculate_taxes_and_totals()
		# Refund in cash on this shift; original-tender refund routing is planned (RET-POS-014).
		profile = frappe.get_cached_doc("POS Profile", opening.pos_profile)
		POSService(ret).reset_mode_of_payments()
		cash = _cash_mode(profile)
		ret.set("payments", [p for p in ret.payments if p.mode_of_payment == cash])
		ret.payments[0].amount = flt(ret.rounded_total) or flt(ret.grand_total)
		ret.calculate_taxes_and_totals()
		ret.flags.ignore_permissions = True
		ret.insert()
		ret.submit()
		job = receipts.create_print_job(ret, drawer_pulse=True)
		log_event(
			"return.completed",
			reference_doctype="Sales Invoice",
			reference_name=ret.name,
			company=ret.company,
			pos_profile=ret.pos_profile,
			device_id=device_id,
			approver=approver,
			reason=reason,
			details={"return_against": return_against, "grand_total": flt(ret.grand_total),
					 "lines": {k: v for k, v in wanted.items()}},
		)
		receipts.enqueue_print(job)
		return _sale_response(ret, job, "return")

	return run_idempotent("return.submit", opening.name, idempotency_key, payload, do)


# ----------------------------------------------------------------------------- receipts


@frappe.whitelist(methods=["POST"])
def reprint_receipt(sales_invoice: str, reason: str, device_id: str | None = None) -> dict:
	authz.require_any_role((authz.CASHIER, authz.SUPERVISOR, authz.MANAGER), "reprint receipts")
	si = frappe.get_doc("Sales Invoice", sales_invoice)
	if si.docstatus != 1 or not si.is_pos:
		raise InvalidRequest(_("Only completed POS receipts can be reprinted."))
	if authz.has_any_role((authz.CASHIER,)) and not authz.has_any_role((authz.SUPERVISOR, authz.MANAGER)):
		authz.require_register_assignment(si.pos_profile)
	if not (reason or "").strip():
		raise InvalidRequest(_("A reprint reason is required."))
	job = receipts.create_print_job(si, is_copy=True, reason=reason)
	log_event("receipt.reprint_requested", reference_doctype="Sales Invoice", reference_name=si.name,
			  pos_profile=si.pos_profile, device_id=device_id, reason=reason, details={"print_job": job})
	receipts.enqueue_print(job)
	return {"print_job": job, "status": "queued"}


@frappe.whitelist(methods=["POST"])
def retry_print_job(print_job: str) -> dict:
	authz.require_any_role((authz.CASHIER, authz.SUPERVISOR, authz.MANAGER), "retry printing")
	return receipts.retry_failed_job(print_job)


# ----------------------------------------------------------------------------- close


@frappe.whitelist(methods=["POST"])
def close_shift(
	pos_opening_entry: str,
	counted: list,
	idempotency_key: str,
	variance_reason: str | None = None,
	device_id: str | None = None,
) -> dict:
	"""Blind close: the cashier submits counted amounts per tender without being shown the
	expected figure first. Variance above tolerance requires a reason."""
	authz.require_any_role((authz.CASHIER, authz.SUPERVISOR), "close a shift")
	opening = _get_open_shift(pos_opening_entry)
	if opening.user != frappe.session.user and not authz.has_any_role((authz.SUPERVISOR,)):
		log_refusal_and_raise(NotAuthorized(_("Only the shift owner or a supervisor can close it.")),
							  "shift.close", pos_profile=opening.pos_profile, device_id=device_id)
	if not isinstance(counted, list):
		raise InvalidRequest(_("counted must be a list of {mode_of_payment, amount}."))

	payload = {"opening": opening.name, "counted": counted, "variance_reason": variance_reason}

	def do():
		from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import (
			make_closing_entry_from_opening,
		)

		oe = frappe.get_doc("POS Opening Entry", opening.name)
		ce = make_closing_entry_from_opening(oe)
		counted_map = {}
		for c in counted:
			if flt(c.get("amount")) < 0:
				raise InvalidRequest(_("Counted amounts cannot be negative."))
			counted_map[c.get("mode_of_payment")] = flt(c.get("amount"))
		opening_map = {d.mode_of_payment: flt(d.opening_amount) for d in oe.balance_details}
		rows = {r.mode_of_payment: r for r in ce.payment_reconciliation}
		for mode in set(opening_map) | set(counted_map):
			if mode not in rows:
				rows[mode] = ce.append("payment_reconciliation", {"mode_of_payment": mode, "expected_amount": 0})
		total_abs_variance = 0.0
		variances = {}
		for mode, r in rows.items():
			r.opening_amount = opening_map.get(mode, 0)
			r.expected_amount = flt(r.expected_amount) + r.opening_amount
			r.closing_amount = counted_map.get(mode, 0)
			r.difference = flt(r.closing_amount - r.expected_amount, 2)
			variances[mode] = r.difference
			total_abs_variance += abs(r.difference)
		tolerance = flt(frappe.db.get_single_value("SERK Retail Settings", "cash_variance_tolerance"))
		if total_abs_variance > tolerance + 1e-9 and not (variance_reason or "").strip():
			raise InvalidRequest(
				_("The count does not match. Recount, or give a reason so a supervisor can review the variance.")
			)
		ce.flags.ignore_permissions = True
		ce.insert()
		ce.submit()
		log_event(
			"shift.closed",
			reference_doctype="POS Closing Entry",
			reference_name=ce.name,
			company=ce.company,
			pos_profile=ce.pos_profile,
			device_id=device_id,
			reason=variance_reason,
			details={"variances": variances, "invoices": len(ce.sales_invoices), "grand_total": flt(ce.grand_total)},
		)
		return {
			"reference_doctype": "POS Closing Entry",
			"reference_name": ce.name,
			"pos_closing_entry": ce.name,
			"variances": variances,
			"invoice_count": len(ce.sales_invoices),
			"grand_total": flt(ce.grand_total),
			"status": "closed",
		}

	return run_idempotent("shift.close", opening.name, idempotency_key, payload, do)


@frappe.whitelist()
def reconcile_shift(pos_closing_entry: str) -> dict:
	authz.require_any_role((authz.SUPERVISOR, authz.MANAGER), "view shift reconciliation")
	from serk_retail.core.reconciliation import reconcile_closing

	return reconcile_closing(pos_closing_entry)
