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

# ---------------------------------------------------------------- identity (SERK, not upstream)
app_logo_url = "/assets/serk_retail/images/serk-retail-mark.svg"
app_home = "/desk/serk-command-center"
add_to_apps_screen = [
	{
		"name": "serk_retail",
		"logo": "/assets/serk_retail/images/serk-retail-mark.svg",
		"title": "SERK Retail",
		"route": "/desk/serk-command-center",
		"has_permission": "serk_retail.branding.check_app_permission",
		"sequence_id": 1,
	}
]

# Theme + brand runtime (colours come from SERK Brand Settings at boot).
app_include_css = ["/assets/serk_retail/css/serk_desk.css", "/assets/serk_retail/css/serk_command_center.css"]
app_include_js = ["/assets/serk_retail/js/serk_theme.js"]
web_include_css = ["/assets/serk_retail/css/serk_web.css"]
web_include_js = ["/assets/serk_retail/js/serk_web.js"]

extend_bootinfo = ["serk_retail.branding.extend_bootinfo"]
update_website_context = ["serk_retail.branding.update_website_context"]
website_context = {
	"favicon": "/assets/serk_retail/images/serk-favicon.svg",
	"splash_image": "/assets/serk_retail/images/serk-retail-mark.svg",
}
email_brand_image = "assets/serk_retail/images/serk-retail-mark.svg"
jinja = {"methods": ["serk_retail.branding.serk_footer_line"]}

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
