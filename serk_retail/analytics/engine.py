# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Retail analytics snapshot, computed from ERPNext's posted documents and ledgers (read-only).

Sources: submitted Sales Invoices (lines, returns, register, cashier, time), Stock Ledger Entry
(cost of goods sold, so margins are the ledger's, not list prices) and Bin (stock on hand).
Nothing here writes to the database. Results are cached briefly per company/window.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json

import frappe
import numpy as np
from frappe.utils import add_days, flt, getdate, now_datetime, nowdate

from serk_retail.analytics import forecast as fc

CACHE_SECONDS = 300
HISTORY_DAYS = 120
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _pct(a, b):
	return round((a - b) / b * 100, 1) if b else None


def _date_range(start: dt.date, end: dt.date):
	d = start
	while d <= end:
		yield d
		d += dt.timedelta(days=1)


def _invoices(company, start, end):
	return frappe.db.sql(
		"""select name, posting_date, posting_time, net_total, grand_total, is_return, pos_profile, owner
		from `tabSales Invoice`
		where docstatus = 1 and company = %(c)s and posting_date between %(s)s and %(e)s""",
		{"c": company, "s": start, "e": end},
		as_dict=True,
	)


def _lines(company, start, end):
	return frappe.db.sql(
		"""select sii.parent, sii.name, sii.item_code, sii.item_name, sii.item_group, sii.stock_qty,
			sii.net_amount, si.posting_date, si.is_return, sii.stock_uom, coalesce(-c.v, 0) as cogs
		from `tabSales Invoice Item` sii join `tabSales Invoice` si on si.name = sii.parent
		left join (
			select voucher_detail_no, sum(stock_value_difference) as v from `tabStock Ledger Entry`
			where voucher_type = 'Sales Invoice' and is_cancelled = 0 and company = %(c)s
				and posting_date between %(s)s and %(e)s
			group by voucher_detail_no
		) c on c.voucher_detail_no = sii.name
		where si.docstatus = 1 and si.company = %(c)s and si.posting_date between %(s)s and %(e)s""",
		{"c": company, "s": start, "e": end},
		as_dict=True,
	)


def _stock(company):
	return frappe.db.sql(
		"""select b.item_code, sum(b.actual_qty) as on_hand, sum(b.stock_value) as stock_value,
			i.item_name, i.item_group, i.stock_uom
		from `tabBin` b join `tabWarehouse` w on w.name = b.warehouse join `tabItem` i on i.name = b.item_code
		where w.company = %(c)s group by b.item_code, i.item_name, i.item_group, i.stock_uom""",
		{"c": company},
		as_dict=True,
	)


def _people(emails):
	if not emails:
		return {}
	rows = frappe.get_all("User", filters={"name": ["in", list(emails)]}, fields=["name", "full_name"])
	return {r.name: (r.full_name or r.name.split("@")[0]) for r in rows}


def snapshot(company: str, days: int = 30, horizon: int = 14) -> dict:
	days = min(max(int(days or 30), 7), 365)
	horizon = min(max(int(horizon or 14), 1), 60)
	key = f"serk_analytics:{company}:{days}:{horizon}:{nowdate()}"
	cached = frappe.cache.get_value(key)
	if cached:
		return cached
	data = _compute(company, days, horizon)
	frappe.cache.set_value(key, data, expires_in_sec=CACHE_SECONDS)
	return data


def _compute(company, days, horizon):
	today = getdate(nowdate())
	start = add_days(today, -(days - 1))
	prev_start, prev_end = add_days(start, -days), add_days(start, -1)
	hist_start = add_days(today, -(max(HISTORY_DAYS, days * 2) - 1))
	currency = frappe.get_cached_value("Company", company, "default_currency")

	invoices = _invoices(company, hist_start, today)
	lines = _lines(company, add_days(today, -(max(days * 2, 90) - 1)), today)
	cur = [i for i in invoices if getdate(i.posting_date) >= getdate(start)]
	prev = [i for i in invoices if getdate(prev_start) <= getdate(i.posting_date) <= getdate(prev_end)]

	# ---------------- KPIs
	def agg(rows):
		sales = [r for r in rows if not r.is_return]
		returns = [r for r in rows if r.is_return]
		revenue = sum(flt(r.net_total) for r in rows)
		gross = sum(flt(r.grand_total) for r in rows)
		return {
			"revenue": round(revenue, 2),
			"gross_with_tax": round(gross, 2),
			"transactions": len(sales),
			"returns": len(returns),
			"refund_amount": round(-sum(flt(r.net_total) for r in returns), 2),
		}

	k, kp = agg(cur), agg(prev)
	cur_lines = [ln for ln in lines if getdate(ln.posting_date) >= getdate(start)]
	prev_lines = [ln for ln in lines if getdate(prev_start) <= getdate(ln.posting_date) <= getdate(prev_end)]
	cogs = sum(flt(ln.cogs) for ln in cur_lines)
	cogs_prev = sum(flt(ln.cogs) for ln in prev_lines)
	units = sum(flt(ln.stock_qty) for ln in cur_lines if not ln.is_return)
	margin_pct = round((k["revenue"] - cogs) / k["revenue"] * 100, 1) if k["revenue"] else None
	margin_prev = round((kp["revenue"] - cogs_prev) / kp["revenue"] * 100, 1) if kp["revenue"] else None
	avg_basket = round(k["revenue"] / k["transactions"], 2) if k["transactions"] else 0
	avg_basket_prev = round(kp["revenue"] / kp["transactions"], 2) if kp["transactions"] else 0
	kpis = {
		**k,
		"revenue_prev": kp["revenue"],
		"revenue_change_pct": _pct(k["revenue"], kp["revenue"]),
		"transactions_prev": kp["transactions"],
		"transactions_change_pct": _pct(k["transactions"], kp["transactions"]),
		"avg_basket": avg_basket,
		"avg_basket_change_pct": _pct(avg_basket, avg_basket_prev),
		"gross_profit": round(k["revenue"] - cogs, 2),
		"gross_margin_pct": margin_pct,
		"gross_margin_change_pts": round(margin_pct - margin_prev, 1) if margin_pct is not None and margin_prev is not None else None,
		"units": round(units, 2),
		"items_per_basket": round(units / k["transactions"], 2) if k["transactions"] else 0,
		"returns_rate_pct": round(k["returns"] / k["transactions"] * 100, 2) if k["transactions"] else 0,
	}

	# ---------------- daily series + forecast (full history for the model)
	by_day = {}
	tx_day = {}
	for r in invoices:
		d = getdate(r.posting_date)
		by_day[d] = by_day.get(d, 0) + flt(r.net_total)
		if not r.is_return:
			tx_day[d] = tx_day.get(d, 0) + 1
	first = min(by_day) if by_day else today
	series_dates = list(_date_range(max(first, getdate(hist_start)), today))
	# Today is partial: model on completed days only.
	model_dates = [d for d in series_dates if d < today]
	y = [by_day.get(d, 0.0) for d in model_dates]
	wd = [d.weekday() for d in model_dates]
	f = fc.forecast_daily(y, wd, horizon, today.weekday()) if model_dates else fc.forecast_daily([], [], horizon, 0)
	f_dates = [str(add_days(today, h)) for h in range(horizon)]
	# Completed days only: today is still trading, the forecast line starts at today.
	daily = [{"date": str(d), "revenue": round(by_day.get(d, 0.0), 2), "transactions": tx_day.get(d, 0)}
			 for d in _date_range(getdate(start), add_days(today, -1))]
	kpis["today_so_far"] = round(by_day.get(today, 0.0), 2)

	# Anomalies: residual vs weekday-seasonal level over the window.
	anomalies = []
	if len(y) >= 21:
		idx = np.asarray(f.weekday_index)
		window = [(d, by_day.get(d, 0.0)) for d in model_dates if d >= getdate(start)]
		if window:
			base = np.mean([v / idx[d.weekday()] for d, v in window])
			resid = [v - base * idx[d.weekday()] for d, v in window]
			for (d, v), z in zip(window, fc.zscores(resid), strict=False):
				if abs(z) >= 2.0:
					anomalies.append({"date": str(d), "weekday": WEEKDAYS[d.weekday()], "revenue": round(v, 2),
									  "expected": round(base * idx[d.weekday()], 2), "z": z,
									  "direction": "spike" if z > 0 else "dip"})

	# ---------------- hourly heatmap (weekday x hour), window only
	heat = [[0.0] * 24 for _ in range(7)]
	for r in cur:
		if r.is_return or r.posting_time is None:
			continue
		hour = int(str(r.posting_time).split(":")[0]) % 24
		heat[getdate(r.posting_date).weekday()][hour] += flt(r.net_total)
	n_weeks = max(days / 7, 1)
	heat = [[round(v / n_weeks, 2) for v in row] for row in heat]
	peak = max(((d, h, heat[d][h]) for d in range(7) for h in range(24)), key=lambda t: t[2], default=(0, 0, 0))

	# ---------------- items, categories
	items: dict = {}
	for ln in cur_lines:
		it = items.setdefault(ln.item_code, {"item_code": ln.item_code, "item_name": ln.item_name,
											 "item_group": ln.item_group, "revenue": 0.0, "qty": 0.0, "cogs": 0.0})
		it["revenue"] += flt(ln.net_amount)
		it["qty"] += flt(ln.stock_qty)
		it["cogs"] += flt(ln.cogs)
	abc = fc.abc_classes({c: v["revenue"] for c, v in items.items()})
	total_rev = sum(v["revenue"] for v in items.values()) or 1
	top_items = []
	for c, v in sorted(items.items(), key=lambda kv: kv[1]["revenue"], reverse=True):
		top_items.append({**v, "revenue": round(v["revenue"], 2), "qty": round(v["qty"], 2),
						  "margin_pct": round((v["revenue"] - v["cogs"]) / v["revenue"] * 100, 1) if v["revenue"] else None,
						  "share_pct": round(v["revenue"] / total_rev * 100, 1), "abc": abc.get(c, "C")})
		top_items[-1].pop("cogs")

	cats: dict = {}
	for ln in cur_lines:
		cats.setdefault(ln.item_group or "Other", [0.0, 0.0])[0] += flt(ln.net_amount)
	for ln in prev_lines:
		cats.setdefault(ln.item_group or "Other", [0.0, 0.0])[1] += flt(ln.net_amount)
	categories = sorted(
		({"group": g, "revenue": round(a, 2), "prev_revenue": round(b, 2), "growth_pct": _pct(a, b),
		  "share_pct": round(a / total_rev * 100, 1)} for g, (a, b) in cats.items()),
		key=lambda r: r["revenue"], reverse=True)

	# ---------------- registers and cashiers
	regs: dict = {}
	cash: dict = {}
	for r in cur:
		for bucket, key2 in ((regs, r.pos_profile or "Back office"), (cash, r.owner)):
			b = bucket.setdefault(key2, {"revenue": 0.0, "transactions": 0, "returns": 0})
			b["revenue"] += flt(r.net_total)
			b["returns" if r.is_return else "transactions"] += 1
	registers = [{"register": n, "revenue": round(v["revenue"], 2), "transactions": v["transactions"],
				  "returns": v["returns"], "avg_basket": round(v["revenue"] / v["transactions"], 2) if v["transactions"] else 0}
				 for n, v in sorted(regs.items(), key=lambda kv: kv[1]["revenue"], reverse=True)]
	names = _people(cash.keys())
	rates = {u: (v["returns"] / v["transactions"] if v["transactions"] else 0) for u, v in cash.items()}
	zs = dict(zip(rates.keys(), fc.zscores(list(rates.values())), strict=False))
	cashiers = [{"user": u, "name": names.get(u, u), "revenue": round(v["revenue"], 2), "transactions": v["transactions"],
				 "returns": v["returns"], "refund_rate_pct": round(rates[u] * 100, 2), "refund_z": zs.get(u, 0),
				 "avg_basket": round(v["revenue"] / v["transactions"], 2) if v["transactions"] else 0}
				for u, v in sorted(cash.items(), key=lambda kv: kv[1]["revenue"], reverse=True)]

	# ---------------- stock intelligence
	demand_start = add_days(today, -27)
	qty_by_item_day: dict = {}
	for ln in lines:
		d = getdate(ln.posting_date)
		if d >= getdate(demand_start) and d < today:
			qty_by_item_day.setdefault(ln.item_code, {}).setdefault(d, 0.0)
			qty_by_item_day[ln.item_code][d] += flt(ln.stock_qty)
	demand_days = [d for d in _date_range(getdate(demand_start), add_days(today, -1))]
	stock = []
	for s in _stock(company):
		series = [qty_by_item_day.get(s.item_code, {}).get(d, 0.0) for d in demand_days]
		dem = fc.item_demand(series, [d.weekday() for d in demand_days], horizon, today.weekday(), f.weekday_index)
		adv = fc.reorder_advice(flt(s.on_hand), dem["daily_mean"], dem["daily_sd"])
		stock.append({"item_code": s.item_code, "item_name": s.item_name, "item_group": s.item_group, "uom": s.stock_uom,
					  "on_hand": round(flt(s.on_hand), 2), "stock_value": round(flt(s.stock_value), 2),
					  "abc": abc.get(s.item_code, "C"), "demand_daily": dem["daily_mean"],
					  "demand_horizon": dem["expected"], **adv})
	order = {"critical": 0, "reorder": 1, "overstock": 2, "healthy": 3, "no recent demand": 4}
	stock.sort(key=lambda r: (order.get(r["status"], 9), r["days_of_cover"] if r["days_of_cover"] is not None else 1e9))

	# ---------------- basket affinity (last 90 days)
	baskets: dict = {}
	for ln in lines:
		if not ln.is_return:
			baskets.setdefault(ln.parent, set()).add(ln.item_code)
	name_of = {ln.item_code: ln.item_name for ln in lines}
	affinity = fc.pair_lift([b for b in baskets.values() if len(b) > 1], min_support_count=max(3, len(baskets) // 400))
	for p in affinity:
		p["a_name"], p["b_name"] = name_of.get(p["a"], p["a"]), name_of.get(p["b"], p["b"])

	data = {
		"meta": {"company": company, "currency": currency, "from": str(start), "to": str(today), "days": days,
				 "horizon": horizon, "generated_at": str(now_datetime()), "invoices_in_window": len(cur),
				 "history_days": len(model_dates)},
		"kpis": kpis,
		"daily": daily,
		"forecast": {"dates": f_dates, "values": f.values, "lower": f.lower, "upper": f.upper, "method": f.method,
					 "backtest_mape_pct": round(f.mape * 100, 1) if f.mape is not None else None,
					 "trend_per_day": f.trend_per_day, "weekday_index": dict(zip(WEEKDAYS, f.weekday_index, strict=False)),
					 "next7_total": round(sum(f.values[:7]), 2), "next_horizon_total": round(sum(f.values), 2),
					 "next7_vs_last7_pct": _pct(sum(f.values[:7]), sum(y[-7:]) if y else 0)},
		"heatmap": {"weekdays": WEEKDAYS, "hours": list(range(24)), "values": heat,
					"peak": {"weekday": WEEKDAYS[peak[0]], "hour": peak[1], "avg_revenue": peak[2]}},
		"top_items": top_items[:25],
		"categories": categories,
		"registers": registers,
		"cashiers": cashiers,
		"stock": stock,
		"affinity": affinity,
		"anomalies": anomalies,
	}
	data["insights"] = derive_insights(data)
	data["meta"]["fingerprint"] = hashlib.sha256(json.dumps(data["kpis"], sort_keys=True, default=str).encode()).hexdigest()[:16]
	return data


def _money(v, cur):
	return f"{cur} {v:,.0f}"


def derive_insights(d: dict) -> list[dict]:
	"""Deterministic, explainable insights (always available, AI or not)."""
	k, cur, out = d["kpis"], d["meta"]["currency"], []

	def add(kind, severity, title, detail, metric=None):
		out.append({"kind": kind, "severity": severity, "title": title, "detail": detail, "metric": metric})

	if k["revenue_change_pct"] is not None:
		up = k["revenue_change_pct"] >= 0
		add("trend", "good" if up else "warn",
			f"Revenue {'up' if up else 'down'} {abs(k['revenue_change_pct'])}% vs previous {d['meta']['days']} days",
			f"{_money(k['revenue'], cur)} net vs {_money(k['revenue_prev'], cur)}. Basket {_money(k['avg_basket'], cur)}"
			+ (f" ({k['avg_basket_change_pct']:+.1f}%)" if k["avg_basket_change_pct"] is not None else "") + ".",
			k["revenue_change_pct"])
	f = d["forecast"]
	if f["next7_total"]:
		add("forecast", "info", f"Next 7 days forecast: {_money(f['next7_total'], cur)}",
			f"{f['method']}"
			+ (f"; backtest error {f['backtest_mape_pct']}% on the last 14 days." if f["backtest_mape_pct"] is not None else ".")
			+ (f" That is {f['next7_vs_last7_pct']:+.1f}% vs the last 7 days." if f["next7_vs_last7_pct"] is not None else ""),
			f["next7_total"])
	hp = d["heatmap"]["peak"]
	if hp["avg_revenue"]:
		add("operations", "info", f"Peak trading: {hp['weekday']} {hp['hour']:02d}:00–{(hp['hour'] + 1) % 24:02d}:00",  # noqa: RUF001 -- intentional typography in user-facing text
			f"Averages {_money(hp['avg_revenue'], cur)} in that hour. Schedule full lanes and replenish shelves before it.")
	crit = [s for s in d["stock"] if s["status"] == "critical"]
	reo = [s for s in d["stock"] if s["status"] == "reorder"]
	if crit or reo:
		names = ", ".join(f"{s['item_name']} ({s['days_of_cover']}d)" for s in (crit + reo)[:4])
		parts = []
		if crit:
			parts.append(f"{len(crit)} item{'s' if len(crit) > 1 else ''} will run out within the supplier lead time")
		if reo:
			parts.append(f"{len(reo)} item{'s' if len(reo) > 1 else ''} need{'' if len(reo) > 1 else 's'} reordering")
		add("stock", "danger" if crit else "warn", "; ".join(parts).capitalize(),
			f"Lowest cover: {names}. Suggested orders are on the stock panel (95% service level).", len(crit) + len(reo))
	over = [s for s in d["stock"] if s["status"] == "overstock"]
	if over:
		val = sum(s["stock_value"] for s in over)
		add("stock", "warn", f"{len(over)} item(s) overstocked (>90 days of cover)",
			f"{_money(val, cur)} of cash tied up. Consider promotions or smaller orders.", val)
	if d["affinity"]:
		p = d["affinity"][0]
		add("basket", "good", f"{p['a_name']} + {p['b_name']} sell together {p['lift']}× more than chance",  # noqa: RUF001 -- intentional typography in user-facing text
			f"Seen in {p['together']} baskets. Place them together or bundle them.", p["lift"])
	if k["gross_margin_pct"] is not None:
		low = [i for i in d["top_items"][:15] if i["margin_pct"] is not None and i["margin_pct"] < 10]
		add("margin", "warn" if low else "good", f"Gross margin {k['gross_margin_pct']}%"
			+ (f" ({k['gross_margin_change_pts']:+.1f} pts)" if k["gross_margin_change_pts"] is not None else ""),
			("Thin-margin best sellers: " + ", ".join(f"{i['item_name']} {i['margin_pct']}%" for i in low[:3]) + ".")
			if low else "Computed from ledger cost of goods sold, not list prices.", k["gross_margin_pct"])
	grow = [c for c in d["categories"] if c["growth_pct"] is not None and c["prev_revenue"] > 0]
	if grow:
		best = max(grow, key=lambda c: c["growth_pct"])
		worst = min(grow, key=lambda c: c["growth_pct"])
		add("market", "info", f"Fastest-growing category: {best['group']} ({best['growth_pct']:+.1f}%)",
			f"Weakest: {worst['group']} ({worst['growth_pct']:+.1f}%). Shift shelf space and buying toward momentum.")
	for c in d["cashiers"]:
		if c["refund_z"] >= 2 and c["returns"] >= 3:
			add("risk", "danger", f"Refund rate outlier: {c['name']} at {c['refund_rate_pct']}%",
				"More than 2 standard deviations above other cashiers. Review approvals in the audit trail.")
	for a in d["anomalies"][-3:]:
		add("anomaly", "warn" if a["direction"] == "dip" else "info",
			f"Unusual {a['direction']} on {a['weekday']} {a['date']}",
			f"{_money(a['revenue'], cur)} vs about {_money(a['expected'], cur)} expected (z = {a['z']}).")
	if k["returns_rate_pct"] > 3:
		add("risk", "warn", f"Returns at {k['returns_rate_pct']}% of sales",
			f"{_money(k['refund_amount'], cur)} refunded. Check product quality and refund reasons.")
	return out
