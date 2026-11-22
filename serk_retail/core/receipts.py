# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Receipt rendering and print-job lifecycle.

Rules enforced here:
* A print job never changes the sale. Print failure leaves the submitted invoice intact.
* The cash drawer pulse is attempted at most once per sale (first original job), never on a
  retry or a reprint.
* Reprints are labelled COPY and audited. Reprinting never re-submits the sale.
* A job whose delivery is unknown is not silently re-sent; the operator issues a COPY.
"""

import hashlib

import frappe
from frappe.utils import flt, fmt_money, now_datetime

from serk_retail.core.audit import log_event
from serk_retail.core.errors import InvalidRequest
from serk_retail.devices.printer import get_printer


def _settings():
	return frappe.get_cached_doc("SERK Retail Settings")


def _row(left: str, right: str, width: int) -> str:
	left = left[: max(1, width - len(right) - 1)]
	return left + " " * (width - len(left) - len(right)) + right


def render_receipt(si, width: int, is_copy: bool = False, copy_number: int = 0) -> str:
	s = _settings()
	cur = si.currency

	def money(v):
		return fmt_money(flt(v), currency=cur)

	lines = []
	center = lambda t: t[:width].center(width).rstrip()  # noqa: E731
	if is_copy:
		lines.append(center(f"*** COPY {copy_number} - NOT AN ORIGINAL ***"))
	lines.append(center(s.store_display_name or si.company))
	lines.append(center("RETURN / REFUND" if si.is_return else "SALES RECEIPT"))
	lines.append("-" * width)
	lines.append(_row("Receipt", si.name, width))
	if si.is_return:
		lines.append(_row("Against", si.return_against, width))
	lines.append(_row("Date", f"{si.posting_date} {str(si.posting_time)[:8]}", width))
	lines.append(_row("Register", si.pos_profile or "", width))
	lines.append(_row("Cashier", si.owner, width))
	lines.append("-" * width)
	for it in si.items:
		lines.append((it.item_name or it.item_code)[:width])
		lines.append(_row(f"  {flt(it.qty):g} x {money(it.rate)}", money(it.amount), width))
	lines.append("-" * width)
	lines.append(_row("Net total", money(si.net_total), width))
	for tx in si.taxes:
		lines.append(_row((tx.description or tx.account_head)[:24], money(tx.tax_amount_after_discount_amount), width))
	if flt(si.discount_amount):
		lines.append(_row("Discount", money(-flt(si.discount_amount)), width))
	lines.append(_row("TOTAL", money(si.grand_total), width))
	for p in si.payments:
		if flt(p.amount):
			lines.append(_row(p.mode_of_payment, money(p.amount), width))
	if flt(si.change_amount):
		lines.append(_row("Change", money(si.change_amount), width))
	lines.append("-" * width)
	if s.receipt_footer:
		lines.append(center(s.receipt_footer))
	return "\n".join(lines)


def create_print_job(si, *, is_copy=False, reason=None, drawer_pulse=False) -> str:
	width = int(_settings().receipt_width_chars or 48)
	copy_number = 0
	if is_copy:
		copy_number = frappe.db.count("SERK Print Job", {"sales_invoice": si.name, "is_copy": 1}) + 1
	text = render_receipt(si, width, is_copy=is_copy, copy_number=copy_number)
	job = frappe.get_doc(
		{
			"doctype": "SERK Print Job",
			"sales_invoice": si.name,
			"pos_profile": si.pos_profile,
			"status": "Queued",
			"is_copy": int(is_copy),
			"copy_number": copy_number,
			"adapter": _settings().printer_adapter,
			"receipt_width": width,
			"drawer_pulse_requested": int(bool(drawer_pulse) and not is_copy),
			"rendered_text": text,
			"payload_hash": hashlib.sha256(text.encode()).hexdigest(),
			"requested_by": frappe.session.user,
			"reason": reason,
		}
	)
	job.flags.ignore_permissions = True
	job.insert()
	return job.name


def enqueue_print(job_name: str):
	"""Print only after the sale commits. In tests the caller drives printing explicitly."""
	if frappe.flags.in_test:
		return
	frappe.enqueue(
		"serk_retail.core.receipts.process_print_job",
		job_name=job_name,
		queue="short",
		enqueue_after_commit=True,
	)


def process_print_job(job_name: str) -> dict:
	# Row lock prevents two workers from sending the same job concurrently.
	frappe.db.get_value("SERK Print Job", job_name, "name", for_update=True)
	job = frappe.get_doc("SERK Print Job", job_name)
	if job.status in ("Acknowledged", "Spooled", "Delivery Unknown"):
		return {"print_job": job.name, "status": job.status, "skipped": True}

	open_drawer = bool(job.drawer_pulse_requested) and not job.drawer_pulse_attempted_at and not job.is_copy
	if open_drawer:
		# Mark BEFORE sending: if the process dies mid-send, we never pulse a second time.
		job.db_set("drawer_pulse_attempted_at", now_datetime(), update_modified=False)

	result = get_printer(job.adapter).send(job.rendered_text, open_drawer=open_drawer)
	job.db_set(
		{
			"status": result.status,
			"attempts": (job.attempts or 0) + 1,
			"last_error": result.error,
		}
	)
	log_event(
		"print.attempt",
		"Success" if result.status in ("Acknowledged", "Spooled") else "Failed",
		reference_doctype="SERK Print Job",
		reference_name=job.name,
		pos_profile=job.pos_profile,
		details={
			"sales_invoice": job.sales_invoice,
			"status": result.status,
			"is_copy": job.is_copy,
			"drawer_pulse_sent": result.drawer_pulse_sent,
			"error": result.error,
		},
	)
	return {"print_job": job.name, "status": result.status, "error": result.error}


def retry_failed_job(job_name: str) -> dict:
	job = frappe.get_doc("SERK Print Job", job_name)
	if job.status == "Delivery Unknown":
		raise InvalidRequest(
			"The printer may already have printed this receipt. Issue a labelled COPY instead of resending."
		)
	if job.status != "Failed":
		raise InvalidRequest(f"Only failed print jobs can be retried (current status: {job.status}).")
	job.db_set("status", "Queued")
	return process_print_job(job_name)
