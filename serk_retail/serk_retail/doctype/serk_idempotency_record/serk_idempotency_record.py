# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
import frappe
from frappe import _
from frappe.model.document import Document


class SERKIdempotencyRecord(Document):
	def on_trash(self):
		# Deduplication state must outlive the business document it protects; retention purge is
		# a separate, documented maintenance job (not implemented in M1).
		frappe.throw(_("Idempotency records cannot be deleted manually."), frappe.PermissionError)
