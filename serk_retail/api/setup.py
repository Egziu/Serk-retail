# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Company setup (v1): company, stores, registers, staff — the SERK way.

Everything is created through ERPNext's own documents (Company builds its chart of accounts,
warehouses and cost centre). SERK adds the retail defaults on top: fiscal year, VAT template,
price list, walk-in customer, cash tender, registers with assigned cashiers, SERK roles and the
company brand. Every action is audited.
"""

import secrets

import frappe
from frappe import _
from frappe.utils import add_days, add_years, getdate, nowdate

from serk_retail.core import authz
from serk_retail.core.audit import log_event
from serk_retail.core.errors import InvalidRequest

ROLE_BY_LABEL = {
	"Cashier": [authz.CASHIER],
	"Shift Supervisor": [authz.SUPERVISOR],
	"Store Manager": [authz.MANAGER, authz.SUPERVISOR],
	"Goods Receiver": [authz.RECEIVER],
}
WALK_IN = "Walk-in Customer"


def _require_admin():
	authz.require_any_role(("System Manager",), "set up companies and users")


def _require_manager():
	authz.require_any_role(("System Manager", authz.MANAGER), "set up stores and registers")


def _clean(s, n=140):
	return (s or "").strip()[:n]


# ------------------------------------------------------------------ state


@frappe.whitelist(methods=["GET"])
def state() -> dict:
	_require_manager()
	companies = frappe.get_all("Company", fields=["name", "abbr", "default_currency", "country", "tax_id"], order_by="creation")
	# ERPNext creates internal locations with every company; they are not shops.
	internal = ("Work In Progress", "Finished Goods", "Goods In Transit")
	used = set(frappe.get_all("POS Profile", pluck="warehouse"))
	stores = [w for w in frappe.get_all("Warehouse", filters={"is_group": 0, "disabled": 0},
										fields=["name", "warehouse_name", "company"], order_by="company, warehouse_name")
			  if w.warehouse_name not in internal or w.name in used]
	registers = []
	for p in frappe.get_all("POS Profile", fields=["name", "company", "warehouse", "taxes_and_charges", "disabled"], order_by="name"):
		p["cashiers"] = frappe.get_all("POS Profile User", filters={"parent": p.name}, pluck="user")
		registers.append(p)
	staff = frappe.db.sql(
		"""select u.name, u.full_name, u.enabled, group_concat(distinct hr.role order by hr.role separator ', ') roles
		from `tabUser` u join `tabHas Role` hr on hr.parent = u.name and hr.parenttype = 'User'
		where hr.role in %(roles)s group by u.name, u.full_name, u.enabled order by u.full_name""",
		{"roles": authz.SERK_ROLES}, as_dict=True)
	taxes = frappe.get_all("Sales Taxes and Charges Template", fields=["name", "company"], order_by="name")
	brand_done = bool(frappe.db.get_single_value("SERK Brand Settings", "company_display_name")
					  or frappe.db.get_single_value("SERK Brand Settings", "legal_name"))
	has_fy = bool(frappe.db.sql("select 1 from `tabFiscal Year` where %s between year_start_date and year_end_date", nowdate()))
	checklist = [
		{"key": "company", "label": _("Company created"), "done": bool(companies)},
		{"key": "fiscal_year", "label": _("Fiscal year covers today"), "done": has_fy},
		{"key": "brand", "label": _("Brand: name, logo, colours"), "done": brand_done},
		{"key": "stores", "label": _("At least one store"), "done": bool(stores)},
		{"key": "registers", "label": _("Registers with cashiers"), "done": any(r["cashiers"] for r in registers)},
		{"key": "staff", "label": _("Staff with SERK roles"), "done": bool(staff)},
		{"key": "ai", "label": _("AI analyst connected"), "done": _ai_ready()},
	]
	return {"companies": companies, "stores": stores, "registers": registers, "staff": staff, "taxes": taxes,
			"checklist": checklist, "role_options": list(ROLE_BY_LABEL), "is_admin": "System Manager" in frappe.get_roles()}


def _ai_ready() -> bool:
	from serk_retail.ai.service import status

	return bool(status().get("available"))


# ------------------------------------------------------------------ company


def _ensure_fiscal_year(calendar: str):
	today = getdate(nowdate())
	if frappe.db.sql("select 1 from `tabFiscal Year` where %s between year_start_date and year_end_date", today):
		return None
	if calendar == "Ethiopian (Hamle 1 – Sene 30)":  # noqa: RUF001 -- intentional typography in user-facing text
		# Hamle 1 is 8 July (9 July before an Ethiopian leap year; the 8 July convention is used here).
		start = getdate(f"{today.year}-07-08")
		if today < start:
			start = getdate(f"{today.year - 1}-07-08")
	else:
		start = getdate(f"{today.year}-01-01")
	end = add_days(add_years(start, 1), -1)
	name = f"{start.year}-{end.year}" if start.year != end.year else str(start.year)
	if frappe.db.exists("Fiscal Year", name):
		name = f"{name} (SERK)"
	frappe.get_doc({"doctype": "Fiscal Year", "year": name, "year_start_date": start, "year_end_date": end}).insert(
		ignore_permissions=True)
	return name


def _vat_template(company, abbr, rate: float, cost_center):
	if rate <= 0:
		return None
	parent = frappe.db.get_value("Account", {"company": company, "account_name": "Duties and Taxes", "is_group": 1})
	if not parent:
		parent = frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "is_group": 1})
	label = f"Output VAT {rate:g}%"
	account = f"{label} - {abbr}"
	if not frappe.db.exists("Account", account):
		frappe.get_doc({"doctype": "Account", "account_name": label, "parent_account": parent, "company": company,
						"account_type": "Tax", "tax_rate": rate}).insert(ignore_permissions=True)
	title = f"VAT {rate:g}% Exclusive"
	name = f"{title} - {abbr}"
	if not frappe.db.exists("Sales Taxes and Charges Template", name):
		frappe.get_doc({"doctype": "Sales Taxes and Charges Template", "title": title, "company": company,
						"taxes": [{"charge_type": "On Net Total", "account_head": account, "rate": rate,
								   "description": f"VAT {rate:g}%", "cost_center": cost_center}]}).insert(ignore_permissions=True)
	return name


def _retail_defaults(company_doc):
	company, cur = company_doc.name, company_doc.default_currency
	price_list = f"{company_doc.abbr} Retail {cur}"
	if not frappe.db.exists("Price List", price_list):
		frappe.get_doc({"doctype": "Price List", "price_list_name": price_list, "currency": cur, "selling": 1,
						"enabled": 1}).insert(ignore_permissions=True)
	if not frappe.db.exists("Customer", WALK_IN):
		frappe.get_doc({"doctype": "Customer", "customer_name": WALK_IN, "customer_type": "Individual",
						"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}) or "All Customer Groups",
						"territory": frappe.db.get_value("Territory", {"is_group": 0}) or "All Territories"}).insert(
			ignore_permissions=True)
	cash_account = company_doc.default_cash_account or frappe.db.get_value(
		"Account", {"company": company, "account_type": "Cash", "is_group": 0})
	if frappe.db.exists("Mode of Payment", "Cash") and cash_account:
		mop = frappe.get_doc("Mode of Payment", "Cash")
		if not any(a.company == company for a in mop.accounts):
			mop.append("accounts", {"company": company, "default_account": cash_account})
			mop.save(ignore_permissions=True)
	return price_list


@frappe.whitelist(methods=["POST"])
def create_company(
	company_name: str,
	abbr: str,
	currency: str = "ETB",
	country: str = "Ethiopia",
	tax_id: str | None = None,
	vat_registration: str | None = None,
	vat_rate: float = 15,
	fiscal_calendar: str = "Ethiopian (Hamle 1 – Sene 30)",  # noqa: RUF001 -- intentional typography in user-facing text
	first_store: str = "Main Store",
	legal_name: str | None = None,
	motto: str | None = None,
	address: str | None = None,
	phone: str | None = None,
	email: str | None = None,
	website: str | None = None,
	set_as_brand: int = 1,
) -> dict:
	_require_admin()
	company_name, abbr = _clean(company_name), _clean(abbr, 10).upper()
	if not company_name or not abbr or not abbr.isalnum():
		raise InvalidRequest(_("Company name and a short alphanumeric abbreviation are required."))
	if frappe.db.exists("Company", company_name) or frappe.db.exists("Company", {"abbr": abbr}):
		raise InvalidRequest(_("A company with that name or abbreviation already exists."))
	if not frappe.db.exists("Currency", currency):
		raise InvalidRequest(_("Unknown currency {0}.").format(currency))
	frappe.db.set_value("Currency", currency, "enabled", 1)
	fy = _ensure_fiscal_year(fiscal_calendar)
	doc = frappe.get_doc({"doctype": "Company", "company_name": company_name, "abbr": abbr, "default_currency": currency,
						  "country": country, "tax_id": _clean(tax_id, 40), "phone_no": _clean(phone, 40),
						  "email": _clean(email), "website": _clean(website),
						  "create_chart_of_accounts_based_on": "Standard Template", "chart_of_accounts": "Standard"})
	doc.insert(ignore_permissions=True)
	doc.reload()
	price_list = _retail_defaults(doc)
	tax = _vat_template(doc.name, abbr, float(vat_rate or 0), doc.cost_center)
	store = _create_store(doc.name, first_store or "Main Store")["warehouse"]
	if int(set_as_brand or 0):
		brand = frappe.get_single("SERK Brand Settings")
		brand.company_display_name = company_name
		brand.legal_name = _clean(legal_name) or company_name
		for field, value in (("motto", motto), ("address", address), ("phone", phone), ("email", email),
							 ("website", website), ("tin", tax_id), ("vat_registration", vat_registration)):
			if value:
				brand.set(field, _clean(value, 500))
		brand.flags.ignore_permissions = True
		brand.save()
	if not frappe.db.get_single_value("Global Defaults", "default_company"):
		frappe.db.set_single_value("Global Defaults", "default_company", doc.name)
	log_event("setup.company_created", reference_doctype="Company", reference_name=doc.name, company=doc.name,
			  details={"currency": currency, "vat_rate": vat_rate, "fiscal_year": fy, "store": store})
	return {"company": doc.name, "abbr": abbr, "store": store, "price_list": price_list, "tax_template": tax,
			"fiscal_year_created": fy}


@frappe.whitelist(methods=["POST"])
def create_store(company: str, store_name: str) -> dict:
	_require_manager()
	return _create_store(company, store_name)


def _create_store(company: str, store_name: str) -> dict:
	store_name = _clean(store_name, 100)
	if not store_name or not frappe.db.exists("Company", company):
		raise InvalidRequest(_("Choose a company and enter a store name."))
	abbr = frappe.get_cached_value("Company", company, "abbr")
	name = f"{store_name} - {abbr}"
	if not frappe.db.exists("Warehouse", name):
		parent = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ["in", ["", None]]}) \
			or frappe.db.get_value("Warehouse", {"company": company, "is_group": 1})
		frappe.get_doc({"doctype": "Warehouse", "warehouse_name": store_name, "company": company,
						"parent_warehouse": parent, "is_group": 0}).insert(ignore_permissions=True)
		log_event("setup.store_created", reference_doctype="Warehouse", reference_name=name, company=company)
	return {"warehouse": name}


@frappe.whitelist(methods=["POST"])
def create_register(company: str, warehouse: str, register_name: str, cashiers: list | None = None,
					tax_template: str | None = None, rounding: str = "Exact") -> dict:
	_require_manager()
	register_name = _clean(register_name, 100)
	if not register_name:
		raise InvalidRequest(_("Enter a register name, e.g. Lane 1."))
	if frappe.db.get_value("Warehouse", warehouse, "company") != company:
		raise InvalidRequest(_("Store {0} does not belong to {1}.").format(warehouse, company))
	if frappe.db.exists("POS Profile", register_name):
		raise InvalidRequest(_("A register named {0} already exists.").format(register_name))
	if tax_template and frappe.db.get_value("Sales Taxes and Charges Template", tax_template, "company") != company:
		raise InvalidRequest(_("Tax template belongs to another company."))
	cashiers = [c for c in (cashiers or []) if isinstance(c, str) and frappe.db.exists("User", c)]
	company_doc = frappe.get_doc("Company", company)
	price_list = _retail_defaults(company_doc)
	cost_center = company_doc.cost_center
	write_off = company_doc.write_off_account or frappe.db.get_value("Account", {"company": company, "account_name": "Write Off"})
	doc = frappe.get_doc({
		"doctype": "POS Profile", "__newname": register_name, "company": company, "warehouse": warehouse,
		"customer": WALK_IN, "selling_price_list": price_list, "currency": company_doc.default_currency,
		"update_stock": 1, "disable_rounded_total": 1 if rounding == "Exact" else 0,
		"write_off_account": write_off, "write_off_cost_center": cost_center, "cost_center": cost_center,
		"taxes_and_charges": tax_template, "payments": [{"mode_of_payment": "Cash", "default": 1}],
		"applicable_for_users": [{"user": u, "default": 1} for u in cashiers],
	})
	doc.insert(ignore_permissions=True)
	log_event("setup.register_created", reference_doctype="POS Profile", reference_name=doc.name, company=company,
			  pos_profile=doc.name, details={"cashiers": len(cashiers)})
	return {"register": doc.name}


@frappe.whitelist(methods=["POST"])
def create_staff(email: str, full_name: str, role: str, registers: list | None = None) -> dict:
	_require_admin()
	email = _clean(email).lower()
	if "@" not in email or role not in ROLE_BY_LABEL:
		raise InvalidRequest(_("Enter a valid email and choose a role."))
	if frappe.db.exists("User", email):
		raise InvalidRequest(_("{0} already exists.").format(email))
	parts = _clean(full_name).split(" ", 1)
	user = frappe.get_doc({"doctype": "User", "email": email, "first_name": parts[0] or email,
						   "last_name": parts[1] if len(parts) > 1 else "", "send_welcome_email": 0, "user_type": "System User"})
	user.insert(ignore_permissions=True)
	user.add_roles(*ROLE_BY_LABEL[role])
	temp = "Serk-" + secrets.token_urlsafe(10)
	from frappe.utils.password import update_password

	update_password(email, temp)
	assigned = []
	for reg in registers or []:
		if isinstance(reg, str) and frappe.db.exists("POS Profile", reg):
			p = frappe.get_doc("POS Profile", reg)
			if not any(r.user == email for r in p.applicable_for_users):
				p.append("applicable_for_users", {"user": email, "default": 0 if assigned else 1})
				p.save(ignore_permissions=True)
			assigned.append(reg)
	log_event("setup.staff_created", reference_doctype="User", reference_name=email, details={"role": role, "registers": assigned})
	# The temporary password is returned once, to the administrator, and never logged.
	return {"user": email, "role": role, "registers": assigned, "temporary_password": temp}
