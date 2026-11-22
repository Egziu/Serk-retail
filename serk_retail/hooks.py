# SERK Retail — Frappe app hooks.
# Copyright (c) 2026 SERK Technologies Group. Licensed GPL-3.0 (see license.txt).
# Extends ERPNext (GPL-3.0, Frappe Technologies Pvt Ltd) through documented hooks only;
# no ERPNext/Frappe core files are patched. See docs/architecture/CORE_PATCH_REGISTER.md.

app_name = "serk_retail"
app_title = "SERK Retail"
app_publisher = "SERK Technologies Group"
app_description = "SERK Retail supermarket and retail operations on ERPNext"
app_email = "dev@serk.invalid"
app_license = "gpl-3.0"

required_apps = ["erpnext"]

use_json_request_body = True
export_python_type_annotations = True
require_type_annotated_api_methods = True

after_install = "serk_retail.setup.install.after_install"
after_migrate = "serk_retail.setup.install.after_migrate"

# Material business events on upstream documents are mirrored into the SERK audit trail.
doc_events = {
	"Sales Invoice": {
		"on_cancel": "serk_retail.core.audit.on_financial_cancel",
	},
	"Purchase Receipt": {
		"on_cancel": "serk_retail.core.audit.on_financial_cancel",
	},
	"POS Closing Entry": {
		"on_cancel": "serk_retail.core.audit.on_financial_cancel",
	},
}
