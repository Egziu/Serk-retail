# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Append-oriented audit trail for material business actions."""

import hashlib
import json

import frappe
from frappe.utils import now_datetime


def _canonical(obj) -> str:
	return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def correlation_id() -> str:
	"""Per-request correlation id (header X-Correlation-ID if supplied, else generated)."""
	if not getattr(frappe.local, "serk_correlation_id", None):
		header = None
		if getattr(frappe.local, "request", None) is not None:
			header = frappe.local.request.headers.get("X-Correlation-ID")
		frappe.local.serk_correlation_id = (header or frappe.generate_hash(length=20))[:64]
	return frappe.local.serk_correlation_id


def log_event(
	event_type: str,
	outcome: str = "Success",
	*,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	company: str | None = None,
	pos_profile: str | None = None,
	device_id: str | None = None,
	approver: str | None = None,
	reason: str | None = None,
	details: dict | None = None,
) -> str:
	user = frappe.session.user
	content = {
		"event_type": event_type,
		"outcome": outcome,
		"actor": user,
		"approver": approver,
		"company": company,
		"pos_profile": pos_profile,
		"device_id": device_id,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"reason": reason,
		"details": details or {},
		"correlation_id": correlation_id(),
		"event_time": now_datetime(),
	}
	doc = frappe.get_doc(
		{
			"doctype": "SERK Audit Event",
			**{k: v for k, v in content.items() if k != "details"},
			"actor_roles": ", ".join(sorted(r for r in frappe.get_roles(user) if r.startswith("SERK"))),
			"details": _canonical(details or {}),
			"content_hash": hashlib.sha256(_canonical(content).encode()).hexdigest(),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def log_refusal_and_raise(exc: Exception, event_type: str, **kwargs):
	"""Persist a refusal even though the request will roll back.

	Called only *before* any business write in the request, so the rollback discards nothing
	but our own pending work; the audit row is then committed on its own.
	"""
	frappe.db.rollback()
	log_event(event_type, "Refused", reason=str(exc)[:500], **kwargs)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- refusal audit must survive the rollback
	raise exc


def on_financial_cancel(doc, method=None):
	"""Cancellation is the only reversal path ERPNext allows for submitted documents; record it."""
	log_event(
		f"{doc.doctype.lower().replace(' ', '_')}.cancelled",
		reference_doctype=doc.doctype,
		reference_name=doc.name,
		company=doc.get("company"),
		pos_profile=doc.get("pos_profile"),
		details={"grand_total": doc.get("grand_total")},
	)
