# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""FICTIONAL trading history for the SERK Demo Mart demo site.

Generates a realistic supermarket history so the Command Center, forecasts and AI have something
to analyse: an Ethiopian grocery catalogue, weekday and hourly demand, a gentle growth trend,
items bought together, a holiday spike, an outage dip and a few refunds. Every sale is a real
ERPNext Sales Invoice (update_stock) posted after a real Purchase Receipt, so margins and stock
come from the ledger. Deterministic (seeded) and idempotent: it refuses to run twice.

Never run on a site with real data. Usage (demo site only):
    bench --site <site> execute serk_retail.setup.demo_history.generate --kwargs '{"days": 75}'
"""

from __future__ import annotations

import datetime as dt
import random

import frappe
from frappe.utils import add_days, flt, getdate, nowdate

from serk_retail.setup import demo

MARKER = "SERK demo history"
# code, name, group, uom, price, cost, daily_units, cover_factor (weekly top-up to 14 x factor days of cover)
CATALOG = [
	("SERK-WATER-500", "Bottled Water 500 ml", "Beverages", "Nos", 25, 12, 30, 1.6),
	("SERK-WATER-2L", "Bottled Water 2 L", "Beverages", "Nos", 55, 34, 9, 1.6),
	("SERK-AMBO-500", "Sparkling Mineral Water 500 ml", "Beverages", "Nos", 35, 22, 10, 1.6),
	("SERK-COLA-500", "Cola 500 ml", "Beverages", "Nos", 45, 31, 14, 1.6),
	("SERK-JUICE-1L", "Mango Juice 1 L", "Beverages", "Nos", 120, 84, 4, 7.0),
	("SERK-COFFEE-500", "Roasted Coffee Beans 500 g", "Coffee & Tea", "Nos", 420, 300, 5, 0.85),
	("SERK-TEA-100", "Black Tea Leaves 100 g", "Coffee & Tea", "Nos", 85, 55, 4, 1.6),
	("SERK-SUGAR-1KG", "Sugar 1 kg", "Grocery", "Nos", 150, 118, 9, 0.9),
	("SERK-INJERA-5", "Injera pack of 5", "Bakery & Injera", "Nos", 60, 38, 26, 1.6),
	("SERK-BREAD", "Bread Loaf", "Bakery & Injera", "Nos", 45, 28, 18, 1.6),
	("SERK-DABOKOLO", "Dabo Kolo 250 g", "Bakery & Injera", "Nos", 70, 42, 5, 1.6),
	("SERK-BISCUIT", "Biscuits", "Snacks", "Nos", 40, 26, 8, 1.6),
	("SERK-TEFF-KG", "White Teff Flour (per kg)", "Grains & Flour", "Kg", 140, 105, 12, 0.95),
	("SERK-WHEAT-5KG", "Wheat Flour 5 kg", "Grains & Flour", "Nos", 520, 430, 2, 1.6),
	("SERK-RICE-1KG", "Rice 1 kg", "Grains & Flour", "Nos", 165, 128, 4, 1.6),
	("SERK-MISIR-1KG", "Red Lentils (Misir) 1 kg", "Grains & Flour", "Nos", 190, 150, 4, 1.6),
	("SERK-SHIRO-500", "Shiro Powder 500 g", "Spices & Pulses", "Nos", 160, 110, 8, 0.5),
	("SERK-PASTA-500", "Pasta 500 g", "Grains & Flour", "Nos", 75, 55, 7, 1.6),
	("SERK-MILK-1L", "Fresh Milk 1 L", "Dairy & Eggs", "Nos", 95, 70, 11, 0.55),
	("SERK-YOGHURT", "Yoghurt 500 ml", "Dairy & Eggs", "Nos", 85, 58, 5, 1.6),
	("SERK-EGGS-12", "Eggs (12)", "Dairy & Eggs", "Nos", 150, 115, 6, 1.6),
	("SERK-KIBE-250", "Spiced Butter (Kibe) 250 g", "Dairy & Eggs", "Nos", 260, 190, 3, 1.6),
	("SERK-OIL-1L", "Cooking Oil 1 L", "Cooking Essentials", "Nos", 210, 172, 8, 1.6),
	("SERK-OIL-5L", "Cooking Oil 5 L", "Cooking Essentials", "Nos", 980, 840, 1.5, 6.5),
	("SERK-BERBERE", "Berbere 250 g", "Spices & Pulses", "Nos", 120, 78, 5, 1.6),
	("SERK-SALT", "Salt 1 kg", "Cooking Essentials", "Nos", 30, 18, 4, 7.5),
	("SERK-ONION-KG", "Red Onion (per kg)", "Fresh Produce", "Kg", 60, 38, 10, 1.0),
	("SERK-TOMATO-KG", "Tomato (per kg)", "Fresh Produce", "Kg", 55, 34, 8, 1.6),
	("SERK-DETERGENT", "Detergent Powder 1 kg", "Household", "Nos", 175, 128, 4, 1.6),
	("SERK-DISHSOAP", "Dish Soap 500 ml", "Household", "Nos", 95, 62, 3, 1.6),
	("SERK-TISSUE-4", "Toilet Tissue 4-pack", "Household", "Nos", 120, 85, 5, 1.6),
	("SERK-SOAP", "Bath Soap", "Personal Care", "Nos", 45, 30, 7, 1.6),
	("SERK-TOOTHPASTE", "Toothpaste", "Personal Care", "Nos", 90, 62, 3, 4.0),
	("SERK-KOLO", "Roasted Barley (Kolo) 250 g", "Snacks", "Nos", 55, 34, 6, 1.6),
	("SERK-PEANUT", "Roasted Peanuts 250 g", "Snacks", "Nos", 65, 42, 4, 1.6),
	("SERK-CHOC", "Chocolate Bar", "Snacks", "Nos", 60, 40, 5, 1.6),
]
PAIRS = [
	("SERK-COFFEE-500", "SERK-SUGAR-1KG", 0.55), ("SERK-INJERA-5", "SERK-SHIRO-500", 0.32),
	("SERK-BREAD", "SERK-MILK-1L", 0.35), ("SERK-PASTA-500", "SERK-TOMATO-KG", 0.45),
	("SERK-OIL-1L", "SERK-ONION-KG", 0.4), ("SERK-BERBERE", "SERK-ONION-KG", 0.5),
	("SERK-TEA-100", "SERK-SUGAR-1KG", 0.45), ("SERK-EGGS-12", "SERK-BREAD", 0.4),
	("SERK-KOLO", "SERK-COLA-500", 0.3), ("SERK-TEFF-KG", "SERK-SHIRO-500", 0.25),
]
WEEKDAY = [0.92, 0.88, 0.95, 0.97, 1.08, 1.32, 1.12]
HOURS = [(7, 3), (8, 9), (9, 6), (10, 5), (11, 6), (12, 9), (13, 8), (14, 5), (15, 5), (16, 6), (17, 9), (18, 11), (19, 9), (20, 5), (21, 2)]


def _groups():
	root = "All Item Groups"
	for g in {c[2] for c in CATALOG}:
		if not frappe.db.exists("Item Group", g):
			frappe.get_doc({"doctype": "Item Group", "item_group_name": g, "parent_item_group": root, "is_group": 0}).insert(
				ignore_permissions=True)


def _items(valid_from):
	for code, name, group, uom, price, _cost, _d, _f in CATALOG:
		if not frappe.db.exists("Item", code):
			frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": name, "item_group": group, "stock_uom": uom,
							"is_stock_item": 1, "is_sales_item": 1, "is_purchase_item": 1, "valuation_method": "FIFO"}).insert(
				ignore_permissions=True)
		else:
			frappe.db.set_value("Item", code, "item_group", group)
		# Item Price.valid_from defaults to today; backdated sales need the price valid from before.
		ip = frappe.db.get_value("Item Price", {"item_code": code, "price_list": demo.PRICE_LIST})
		if ip:
			frappe.db.set_value("Item Price", ip, {"price_list_rate": price, "valid_from": valid_from})
		else:
			frappe.get_doc({"doctype": "Item Price", "item_code": code, "price_list": demo.PRICE_LIST,
							"price_list_rate": price, "currency": "ETB", "valid_from": valid_from}).insert(ignore_permissions=True)


def _invoice(profile, cashier, date, time, lines, rng):
	frappe.set_user(cashier)
	si = frappe.new_doc("Sales Invoice")
	si.update({"is_pos": 1, "pos_profile": profile.name, "company": profile.company, "customer": profile.customer,
			   "update_stock": 1, "set_warehouse": profile.warehouse, "set_posting_time": 1, "posting_date": date,
			   "posting_time": time, "disable_rounded_total": 1, "remarks": MARKER})
	for code, qty in lines:
		si.append("items", {"item_code": code, "qty": qty, "warehouse": profile.warehouse})
	si.set_missing_values()
	si.set("payments", [])
	si.append("payments", {"mode_of_payment": "Cash", "amount": 0})
	si.calculate_taxes_and_totals()
	total = flt(si.grand_total)
	tendered = total if rng.random() < 0.35 else (int(total / 50) + 1) * 50
	si.payments[0].amount = tendered
	si.calculate_taxes_and_totals()
	if flt(si.grand_total) <= 0:
		frappe.throw(f"Demo history: zero-priced basket on {date} ({[c for c, _ in lines]}); check Item Price validity.")
	si.flags.ignore_permissions = True
	si.insert()
	si.submit()
	return si


def generate(days: int = 75, seed: int = 2026, base_invoices: int = 34) -> dict:
	if frappe.db.exists("Sales Invoice", {"remarks": MARKER}):
		return {"skipped": "demo history already present"}
	if not frappe.db.exists("Company", demo.COMPANY):
		frappe.throw("Run serk_retail.setup.demo.seed first.")
	frappe.set_user("Administrator")
	rng = random.Random(seed)
	today = getdate(nowdate())
	_groups()
	_items(add_days(today, -(days + 2)))
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- long generator, commit per stage

	start = add_days(today, -days)
	end = add_days(today, -1)
	profiles = [frappe.get_doc("POS Profile", lane) for lane in demo.LANES]
	cashier_of = {lane: user for lane, user in demo.LANES.items()}
	warehouse = profiles[0].warehouse
	info = {c[0]: c for c in CATALOG}
	codes = [c[0] for c in CATALOG]
	weights = [c[6] for c in CATALOG]

	remaining = {c[0]: flt(frappe.db.get_value("Bin", {"item_code": c[0], "warehouse": warehouse}, "actual_qty")) for c in CATALOG}
	sold_week = {c[0]: 0.0 for c in CATALOG}
	receipts = 0
	holiday = add_days(start, int(days * 0.55))  # festive spike
	outage = add_days(start, int(days * 0.8))  # power outage dip
	created, returns = 0, 0
	recent, to_refund = [], []
	day = getdate(start)
	while day <= getdate(end):
		i = (day - getdate(start)).days
		factor = WEEKDAY[day.weekday()] * (1 + 0.0045 * i) * rng.uniform(0.9, 1.1)
		if day == getdate(holiday):
			factor *= 1.85
		if day == getdate(outage):
			factor *= 0.45
		# Weekly replenishment (Mondays and the first day): top up to 14 x cover_factor days of demand,
		# estimated from last week's sales, like a store's standing order.
		if i == 0 or day.weekday() == 0:
			order = {}
			for c in CATALOG:
				daily = sold_week[c[0]] / 7 if i else c[6] * 0.55
				target = max(daily, 0.3) * 14 * c[7]
				qty = target - remaining[c[0]]
				if qty > 0.5:
					order[c[0]] = round(qty + 0.49) if c[3] != "Kg" else round(qty, 1)
			if order:
				_receive(warehouse, day, order, info)
				for code, qty in order.items():
					remaining[code] += qty
				receipts += 1
			sold_week = {c[0]: 0.0 for c in CATALOG}
		n = max(round(base_invoices * factor), 3)
		times = sorted(
			dt.time(h, rng.randrange(60), rng.randrange(60))
			for h in rng.choices([h for h, _ in HOURS], weights=[w for _, w in HOURS], k=n)
		)
		for t in times:
			basket = {}
			anchors = rng.choices(codes, weights=weights, k=rng.choice([1, 1, 2, 2, 3, 3, 4, 5]))
			for code in anchors:
				basket[code] = basket.get(code, 0) + 1
				for a, b, p in PAIRS:
					if code in (a, b) and rng.random() < p:
						other = b if code == a else a
						basket.setdefault(other, 1)
			lines = []
			for code, units in basket.items():
				qty = round(rng.uniform(0.5, 2.5), 1) if info[code][3] == "Kg" else units * rng.choice([1, 1, 1, 2])
				if remaining[code] >= qty:
					remaining[code] -= qty
					sold_week[code] += qty
					lines.append((code, qty))
			if not lines:
				continue
			lane = rng.choice(list(demo.LANES)) if rng.random() < 0.5 else next(iter(demo.LANES))
			profile = next(p for p in profiles if p.name == lane)
			si = _invoice(profile, cashier_of[lane], day, t, lines, rng)
			created += 1
			recent.append(si.name)
			if rng.random() < 0.012:
				to_refund.append((si, cashier_of[lane]))
		# Refunds are posted after the day's last sale so every return follows its original.
		for si, cashier in to_refund:
			_return(si, cashier, day)
			returns += 1
		to_refund = []
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- one day per commit keeps the job resumable
		day = add_days(day, 1)
	frappe.set_user("Administrator")
	frappe.cache.delete_keys("serk_analytics:")
	return {"invoices": created, "returns": returns, "receipts": receipts, "from": str(start), "to": str(end)}


def _receive(warehouse, day, order: dict, info: dict):
	frappe.set_user("receiver@serk.test")
	pr = frappe.get_doc({"doctype": "Purchase Receipt", "company": demo.COMPANY, "supplier": demo.SUPPLIER,
						 "set_posting_time": 1, "posting_date": day, "posting_time": "06:30:00",
						 "set_warehouse": warehouse, "remarks": MARKER,
						 "items": [{"item_code": code, "qty": qty, "rate": info[code][5], "warehouse": warehouse}
								   for code, qty in order.items()]})
	pr.flags.ignore_permissions = True
	pr.insert()
	pr.submit()
	frappe.set_user("Administrator")


def _return(si, cashier, day):
	from erpnext.accounts.doctype.sales_invoice.mapper import make_sales_return

	frappe.set_user("Administrator")
	ret = make_sales_return(si.name)  # mapper needs create rights; the refund is saved as the cashier
	ret.set("items", ret.items[:1])
	ret.items[0].qty = -min(abs(ret.items[0].qty), 1)
	ret.set_posting_time = 1
	ret.posting_date = day
	ret.posting_time = "23:30:00"
	ret.remarks = MARKER + " (refund)"
	ret.calculate_taxes_and_totals()
	ret.set("payments", [p for p in ret.payments if p.mode_of_payment == "Cash"][:1] or ret.payments[:1])
	if ret.payments:
		ret.payments[0].amount = flt(ret.grand_total)
	frappe.set_user(cashier)
	ret.flags.ignore_permissions = True
	ret.insert()
	ret.submit()
	frappe.set_user("Administrator")


def enqueue(days: int = 75):
	"""Background job for container boots: long-running, so it never blocks the web server."""
	frappe.enqueue("serk_retail.setup.demo_history.generate", queue="long", timeout=7200, days=days,
				   job_id="serk_demo_history", deduplicate=True)
