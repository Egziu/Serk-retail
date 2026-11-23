# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""SERK Retail brand: one source of truth for name, logo, colours and contacts.

Everything visible is re-labelled through documented Frappe extension points only (no core
patches): Website/Navbar/System Settings values, the `extend_bootinfo` and
`update_website_context` hooks, and app templates that take precedence over upstream ones.
"""

import re

import frappe

MARK = "/assets/serk_retail/images/serk-retail-mark.svg"
BACK_OFFICE_MARK = "/assets/serk_retail/images/serk-back-office.svg"
SYSTEM_MARK = "/assets/serk_retail/images/serk-system.svg"
FAVICON = "/assets/serk_retail/images/serk-favicon.svg"
HOME_ROUTE = "/desk/serk-command-center"

DEFAULTS = {
	"product_name": "SERK Retail",
	"company_display_name": "",
	"legal_name": "",
	"motto": "Innovation with Integrity",
	"login_tagline": "Retail operations, live insight and AI forecasting in one place.",
	"logo": "",
	"favicon": "",
	"primary_color": "#166453",
	"accent_color": "#61AD98",
	"sidebar_color": "#153335",
	"background_color": "#F6F8F7",
	"sidebar_style": "Dark",
	"corner_style": "Rounded",
	"chart_palette": "#166453,#61AD98,#E0A526,#2F6FB5,#C2553D,#7A5AA6",
	"address": "",
	"phone": "",
	"email": "",
	"website": "",
	"tin": "",
	"vat_registration": "",
	"footer_text": "",
	"show_contact_in_footer": 1,
}
COLOR_FIELDS = ("primary_color", "accent_color", "sidebar_color", "background_color")
CACHE_KEY = "serk_brand"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def valid_hex(value) -> bool:
	return isinstance(value, str) and bool(_HEX.match(value))


def _load() -> dict:
	brand = dict(DEFAULTS)
	if frappe.db.exists("DocType", "SERK Brand Settings"):
		for key in DEFAULTS:
			value = frappe.db.get_single_value("SERK Brand Settings", key)
			if value not in (None, ""):
				brand[key] = value
	for key in COLOR_FIELDS:
		if not valid_hex(brand[key]):
			brand[key] = DEFAULTS[key]
	palette = [c.strip() for c in str(brand["chart_palette"] or "").split(",") if valid_hex(c.strip())]
	default_palette = DEFAULTS["chart_palette"].split(",")
	if not palette or [c.upper() for c in palette] == [c.upper() for c in default_palette]:
		# Palette not customised: lead with the brand's own colours so charts follow the brand.
		palette = [brand["primary_color"], brand["accent_color"]] + [
			c for c in default_palette[2:] if c.upper() not in (brand["primary_color"].upper(), brand["accent_color"].upper())]
	brand["chart_colors"] = palette
	brand["logo_url"] = brand["logo"] or MARK
	brand["favicon_url"] = brand["favicon"] or brand["logo"] or FAVICON
	brand["display_name"] = brand["company_display_name"] or brand["legal_name"] or brand["product_name"]
	return brand


def get_brand() -> dict:
	brand = frappe.cache.get_value(CACHE_KEY)
	if not brand:
		brand = _load()
		frappe.cache.set_value(CACHE_KEY, brand)
	return brand


PUBLIC_KEYS = (
	"product_name", "display_name", "motto", "login_tagline", "logo_url", "favicon_url", "primary_color",
	"accent_color", "sidebar_color", "background_color", "sidebar_style", "corner_style", "chart_colors",
)


def public_brand_dict() -> dict:
	"""Only presentation values; safe for guests (login page)."""
	brand = get_brand()
	return {k: brand[k] for k in PUBLIC_KEYS}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def public_brand() -> dict:
	return public_brand_dict()


def footer_line(brand: dict | None = None) -> str:
	brand = brand or get_brand()
	parts = [brand["footer_text"] or brand["legal_name"] or brand["display_name"]]
	if int(brand.get("show_contact_in_footer") or 0):
		parts += [brand["address"], brand["phone"], brand["email"], brand["website"]]
	return " · ".join(p for p in parts if p)


def apply_brand():
	"""Push the brand into the upstream settings that the login page, navbar and emails read."""
	brand = _load()
	frappe.cache.delete_value(CACHE_KEY)
	ws = frappe.get_single("Website Settings")
	ws.app_name = brand["product_name"]
	ws.app_logo = brand["logo_url"]
	ws.favicon = brand["favicon_url"]
	ws.splash_image = brand["logo_url"]
	ws.copyright = brand["legal_name"] or brand["display_name"]
	ws.footer_powered = footer_line(brand)
	ws.flags.ignore_permissions = True
	ws.flags.ignore_mandatory = True
	ws.save()
	frappe.db.set_single_value("Navbar Settings", "app_logo", brand["logo_url"])
	frappe.db.set_single_value("System Settings", "app_name", brand["product_name"])
	frappe.clear_cache()


def _ensure_default_app():
	if not frappe.db.get_single_value("System Settings", "default_app"):
		frappe.db.set_single_value("System Settings", "default_app", "serk_retail")


# ------------------------------------------------------------------ hooks


def extend_bootinfo(bootinfo):
	brand = get_brand()
	bootinfo.serk_brand = public_brand_dict()
	bootinfo.app_logo_url = brand["logo_url"]
	for app in bootinfo.get("app_data") or []:
		name = app.get("app_name")
		if name == "erpnext":
			app["app_title"] = "Back Office"
			app["app_logo_url"] = BACK_OFFICE_MARK
			app["sequence_id"] = 2
		elif name == "frappe":
			app["app_title"] = "System"
			app["app_logo_url"] = SYSTEM_MARK
			app["module_icons"] = []
		elif name == "serk_retail":
			app["app_title"] = brand["product_name"]
			app["app_logo_url"] = brand["logo_url"]
			app["sequence_id"] = 1


def update_website_context(context):
	brand = get_brand()
	return {
		"favicon": brand["favicon_url"],
		"splash_image": brand["logo_url"],
		"footer_powered": footer_line(brand),
		"serk_brand": public_brand_dict(),
		"app_name": brand["product_name"],
	}


def check_app_permission() -> bool:
	return frappe.session.user != "Guest"


def serk_footer_line() -> str:
	"""Jinja method (hooks.jinja) used by the email and web footer templates."""
	return footer_line()
