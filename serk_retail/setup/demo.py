# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Synthetic pilot seed. ALL DATA IS FICTIONAL.

Pilot assumptions (labelled, revisable — not the user's real deployment):
* one company "SERK Demo Mart" (Ethiopia, ETB), one store warehouse, two lanes
* fiscal year 2026-07-08 .. 2027-07-07 (Ethiopian Hamle 1 - Sene 30, synthetic)
* VAT 15% tax-exclusive on the receipt — a TEST ASSUMPTION, not tax advice or fiscal approval
* passwords are generated per run and written only to a 0600 file outside the repository

Usage: bench --site <site> execute serk_retail.setup.demo.seed
"""

import os
import secrets

import frappe
from frappe.utils import flt

COMPANY = "SERK Demo Mart"
ABBR = "SDM"
PRICE_LIST = "SERK Retail ETB"
TAX_TEMPLATE = f"SERK VAT 15% Exclusive (synthetic) - {ABBR}"
CUSTOMER = "Walk-in Customer (SERK)"
SUPPLIER = "SERK Synthetic Supplier PLC"

ITEMS = [
	# code, name, uom, whole_number, price, barcodes
	("SERK-WATER-500", "Bottled Water 500 ml", "Nos", 1, 25.0, ["0012345678905"]),
	("SERK-INJERA-5", "Injera pack of 5", "Nos", 1, 60.0, ["2000000000015", "INJ5"]),
	("SERK-TEFF-KG", "White Teff Flour (per kg)", "Kg", 0, 140.0, []),
]

USERS = {
	"cashier1@serk.test": ("Cashier One", ["SERK Cashier"]),
	"cashier2@serk.test": ("Cashier Two", ["SERK Cashier"]),
	"supervisor@serk.test": ("Shift Supervisor", ["SERK Shift Supervisor"]),
	"manager@serk.test": ("Store Manager", ["SERK Store Manager", "SERK Shift Supervisor"]),
	"receiver@serk.test": ("Goods Receiver", ["SERK Receiver"]),
}

LANES = {f"{ABBR} Lane 1": "cashier1@serk.test", f"{ABBR} Lane 2": "cashier2@serk.test"}


def _setup_wizard():
	if frappe.db.exists("Company", COMPANY):
		return
	if frappe.is_setup_complete():
		# Site already set up (e.g. upstream test site): add our company directly.
		frappe.get_doc(
			{"doctype": "Company", "company_name": COMPANY, "abbr": ABBR, "default_currency": "ETB",
			 "country": "Ethiopia", "create_chart_of_accounts_based_on": "Standard Template",
			 "chart_of_accounts": "Standard"}
		).insert(ignore_permissions=True)
		_ensure_fiscal_year()
		return
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	frappe.db.set_value("Currency", "ETB", "enabled", 1)
	setup_complete(
		{
			"language": "English",
			"country": "Ethiopia",
			"timezone": "Africa/Addis_Ababa",
			"currency": "ETB",
			"full_name": "SERK Admin",
			"email": "admin@serk.test",
			"company_name": COMPANY,
			"company_abbr": ABBR,
			"chart_of_accounts": "Standard",
			"fy_start_date": "2026-07-08",
			"fy_end_date": "2027-07-07",
			"setup_demo": 0,
		}
	)


def _ensure_fiscal_year():
	if not frappe.db.sql("select name from `tabFiscal Year` where %s between year_start_date and year_end_date", frappe.utils.nowdate()):
		frappe.get_doc({"doctype": "Fiscal Year", "year": "2026-2027 (SERK)", "year_start_date": "2026-07-08",
						"year_end_date": "2027-07-07"}).insert(ignore_permissions=True)


def _ensure(doctype, name, values):
	if frappe.db.exists(doctype, name):
		return frappe.get_doc(doctype, name)
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.insert(ignore_permissions=True)
	return doc


def _users(write_credentials: bool):
	creds = {}
	for email, (full_name, roles) in USERS.items():
		pwd = secrets.token_urlsafe(18)
		if not frappe.db.exists("User", email):
			u = frappe.get_doc({"doctype": "User", "email": email, "first_name": full_name,
								"send_welcome_email": 0, "user_type": "System User"})
			u.insert(ignore_permissions=True)
		u = frappe.get_doc("User", email)
		u.add_roles(*roles)
		from frappe.utils.password import update_password

		update_password(email, pwd)
		creds[email] = pwd
	if write_credentials:
		path = os.path.expanduser("~/.serk_demo_credentials")
		with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
			for k, v in creds.items():
				fh.write(f"{k}\t{v}\n")
	return creds


def seed(write_credentials: bool = True) -> dict:
	from serk_retail.setup.install import after_install

	_setup_wizard()
	after_install()
	frappe.db.set_value("Currency", "ETB", "enabled", 1)
	company = frappe.get_doc("Company", COMPANY)
	warehouse = frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 0, "warehouse_name": "Stores"}) \
		or frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 0})
	cost_center = company.cost_center or frappe.db.get_value("Cost Center", {"company": COMPANY, "is_group": 0})

	frappe.db.set_value("UOM", "Kg", "must_be_whole_number", 0)

	_ensure("Price List", PRICE_LIST, {"price_list_name": PRICE_LIST, "currency": "ETB", "selling": 1, "enabled": 1})
	for code, name, uom, _whole, price, barcodes in ITEMS:
		if not frappe.db.exists("Item", code):
			frappe.get_doc(
				{"doctype": "Item", "item_code": code, "item_name": name, "stock_uom": uom,
				 "item_group": frappe.db.get_value("Item Group", {"is_group": 0}) or "All Item Groups",
				 "is_stock_item": 1, "is_sales_item": 1, "is_purchase_item": 1, "valuation_method": "FIFO",
				 "barcodes": [{"barcode": b} for b in barcodes]}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Item Price", {"item_code": code, "price_list": PRICE_LIST}):
			frappe.get_doc({"doctype": "Item Price", "item_code": code, "price_list": PRICE_LIST,
							"price_list_rate": price, "currency": "ETB"}).insert(ignore_permissions=True)

	parent_tax = frappe.db.get_value("Account", {"company": COMPANY, "account_name": "Duties and Taxes", "is_group": 1})
	vat_account = f"SERK Output VAT 15 - {ABBR}"
	_ensure("Account", vat_account, {"account_name": "SERK Output VAT 15", "parent_account": parent_tax,
									 "company": COMPANY, "account_type": "Tax", "tax_rate": 15})
	_ensure("Sales Taxes and Charges Template", TAX_TEMPLATE,
			{"title": "SERK VAT 15% Exclusive (synthetic)", "company": COMPANY,
			 "taxes": [{"charge_type": "On Net Total", "account_head": vat_account, "rate": 15,
						"description": "VAT 15% (synthetic)", "cost_center": cost_center}]})

	_ensure("Customer", CUSTOMER, {"customer_name": CUSTOMER, "customer_type": "Individual",
								   "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}) or "All Customer Groups",
								   "territory": frappe.db.get_value("Territory", {"is_group": 0}) or "All Territories"})
	_ensure("Supplier", SUPPLIER, {"supplier_name": SUPPLIER,
								   "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}) or "All Supplier Groups"})

	cash_account = company.default_cash_account or frappe.db.get_value("Account", {"company": COMPANY, "account_type": "Cash", "is_group": 0})
	mop = frappe.get_doc("Mode of Payment", "Cash")
	if not any(a.company == COMPANY for a in mop.accounts):
		mop.append("accounts", {"company": COMPANY, "default_account": cash_account})
		mop.save(ignore_permissions=True)

	creds = _users(write_credentials)

	for lane, cashier in LANES.items():
		if not frappe.db.exists("POS Profile", lane):
			frappe.get_doc(
				{"doctype": "POS Profile", "name": lane, "__newname": lane, "company": COMPANY,
				 "warehouse": warehouse, "customer": CUSTOMER, "selling_price_list": PRICE_LIST,
				 "currency": "ETB", "update_stock": 1, "disable_rounded_total": 1,
				 "write_off_account": company.write_off_account or frappe.db.get_value("Account", {"company": COMPANY, "account_name": "Write Off"}),
				 "write_off_cost_center": cost_center, "cost_center": cost_center,
				 "taxes_and_charges": TAX_TEMPLATE,
				 "payments": [{"mode_of_payment": "Cash", "default": 1}],
				 "applicable_for_users": [{"user": cashier, "default": 1}]}
			).insert(ignore_permissions=True)

	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- seed script
	return {"company": COMPANY, "warehouse": warehouse, "lanes": list(LANES), "credentials": creds,
			"price_list": PRICE_LIST, "supplier": SUPPLIER, "customer": CUSTOMER}
