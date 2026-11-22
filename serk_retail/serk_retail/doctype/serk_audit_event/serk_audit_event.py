# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
import frappe
from frappe import _
from frappe.model.document import Document


class SERKAuditEvent(Document):
	"""Append-only. Limits: this is row-level tamper *resistance* through the application only.
	A database administrator who controls storage can still alter rows; content_hash detects
	edits to a row only if the hash is checked against an independent copy. See
	docs/security/AUDIT.md."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Audit events are append-only and cannot be modified."), frappe.PermissionError)

	def on_trash(self):
		frappe.throw(_("Audit events are append-only and cannot be deleted."), frappe.PermissionError)
