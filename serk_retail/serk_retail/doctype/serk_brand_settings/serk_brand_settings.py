# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
import frappe
from frappe import _
from frappe.model.document import Document

from serk_retail.branding import COLOR_FIELDS, apply_brand, valid_hex


class SERKBrandSettings(Document):
	def validate(self):
		for field in COLOR_FIELDS:
			value = (self.get(field) or "").strip()
			if not valid_hex(value):
				frappe.throw(_("{0} must be a colour like #166453.").format(self.meta.get_label(field)))
			self.set(field, value.upper())
		bad = [c for c in (self.chart_palette or "").split(",") if c.strip() and not valid_hex(c.strip())]
		if bad:
			frappe.throw(_("Chart palette has invalid colours: {0}").format(", ".join(bad)))

	def on_update(self):
		apply_brand()
