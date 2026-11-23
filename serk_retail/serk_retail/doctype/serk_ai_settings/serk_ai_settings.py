# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
import frappe
from frappe import _
from frappe.model.document import Document


class SERKAISettings(Document):
	def validate(self):
		if self.base_url and not self.base_url.startswith("https://"):
			frappe.throw(_("Base URL must use HTTPS."))
		if self.max_tokens and not (200 <= int(self.max_tokens) <= 8000):
			frappe.throw(_("Max output tokens must be between 200 and 8000."))
