# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Shift reconciliation computed independently from ERPNext's ledgers.

Each check recomputes its expected value from a different source than the figure under test:
* closing totals  vs  sum of submitted invoices
* invoices        vs  GL Entry (balanced per voucher; revenue/tax/cash postings)
* invoice items   vs  Stock Ledger Entry (quantity per item)
* expected cash   vs  GL movement on the register cash account
* idempotency     -> exactly one dedupe record per SERK-created invoice
"""

import frappe
from frappe.utils import flt

TOL = 0.005


def _check(name, expected, actual, ok=None, note=None):
	ok = (abs(flt(expected) - flt(actual)) <= TOL) if ok is None else ok
	return {"check": name, "ok": bool(ok), "expected": expected, "actual": actual, "note": note}


def reconcile_closing(pos_closing_entry: str) -> dict:
	ce = frappe.get_doc("POS Closing Entry", pos_closing_entry)
	invoices = [r.sales_invoice for r in ce.sales_invoices if r.sales_invoice]
	checks = []

	si_rows = frappe.get_all(
		"Sales Invoice",
		filters={"name": ["in", invoices or [""]], "docstatus": 1},
		fields=["name", "grand_total", "net_total", "total_taxes_and_charges", "is_return",
				"paid_amount", "change_amount", "company"],
	)
	checks.append(_check("closing.invoice_count", len(invoices), len(si_rows)))
	checks.append(_check("closing.grand_total_vs_invoices", sum(flt(r.grand_total) for r in si_rows), ce.grand_total))

	# GL: every voucher balanced, and not cancelled.
	unbalanced = []
	for name in invoices:
		dr, cr, n = frappe.db.sql(
			"""select coalesce(sum(debit),0), coalesce(sum(credit),0), count(*) from `tabGL Entry`
			where voucher_type='Sales Invoice' and voucher_no=%s and is_cancelled=0""",
			name,
		)[0]
		if n == 0 or abs(flt(dr) - flt(cr)) > TOL:
			unbalanced.append({"invoice": name, "debit": flt(dr), "credit": flt(cr), "rows": n})
	checks.append(_check("gl.vouchers_balanced", 0, len(unbalanced), note=unbalanced or None))

	# GL: revenue (income accounts) credited net of returns == sum of invoice net totals.
	company = ce.company
	income = frappe.db.sql(
		"""select coalesce(sum(gle.credit - gle.debit),0) from `tabGL Entry` gle
		join `tabAccount` acc on acc.name = gle.account
		where gle.voucher_type='Sales Invoice' and gle.voucher_no in %(v)s and gle.is_cancelled=0
		and acc.root_type='Income'""",
		{"v": tuple(invoices or [""])},
	)[0][0]
	checks.append(_check("gl.income_vs_net_total", sum(flt(r.net_total) for r in si_rows), income))

	tax_gl = frappe.db.sql(
		"""select coalesce(sum(gle.credit - gle.debit),0) from `tabGL Entry` gle
		join `tabSales Taxes and Charges` t on t.parent = gle.voucher_no and t.account_head = gle.account
		where gle.voucher_type='Sales Invoice' and gle.voucher_no in %(v)s and gle.is_cancelled=0""",
		{"v": tuple(invoices or [""])},
	)[0][0]
	checks.append(_check("gl.tax_vs_invoice_taxes", sum(flt(r.total_taxes_and_charges) for r in si_rows), tax_gl))

	# Stock: SLE qty per item == -(invoice stock qty) for stock items.
	expected_qty = {}
	for it in frappe.db.sql(
		"""select sii.item_code, sum(sii.stock_qty) from `tabSales Invoice Item` sii
		join `tabItem` i on i.name = sii.item_code
		where sii.parent in %(v)s and i.is_stock_item = 1 group by sii.item_code""",
		{"v": tuple(invoices or [""])},
	):
		expected_qty[it[0]] = -flt(it[1])
	actual_qty = {
		r[0]: flt(r[1])
		for r in frappe.db.sql(
			"""select item_code, sum(actual_qty) from `tabStock Ledger Entry`
			where voucher_type='Sales Invoice' and voucher_no in %(v)s and is_cancelled=0 group by item_code""",
			{"v": tuple(invoices or [""])},
		)
	}
	stock_diffs = {
		k: {"expected": expected_qty.get(k, 0), "actual": actual_qty.get(k, 0)}
		for k in set(expected_qty) | set(actual_qty)
		if abs(expected_qty.get(k, 0) - actual_qty.get(k, 0)) > 1e-6
	}
	checks.append(_check("stock.sle_vs_invoice_qty", 0, len(stock_diffs), note=stock_diffs or None))

	# Cash: expected per closing vs independent GL movement on each tender's account.
	for row in ce.payment_reconciliation:
		account = frappe.db.get_value(
			"Mode of Payment Account", {"parent": row.mode_of_payment, "company": company}, "default_account"
		)
		gl_move = flt(
			frappe.db.sql(
				"""select coalesce(sum(debit - credit),0) from `tabGL Entry`
				where voucher_type='Sales Invoice' and voucher_no in %(v)s and account=%(a)s and is_cancelled=0""",
				{"v": tuple(invoices or [""]), "a": account},
			)[0][0]
		)
		checks.append(
			_check(f"tender.{row.mode_of_payment}.expected_vs_gl",
				   flt(row.expected_amount) - flt(row.opening_amount), gl_move,
				   note={"account": account, "opening": flt(row.opening_amount)})
		)
		checks.append(
			_check(f"tender.{row.mode_of_payment}.counted_variance", 0, flt(row.difference),
				   ok=True, note="Informational: variance is reported, not auto-corrected.")
		)

	# Dedupe: no invoice referenced by more than one idempotency record.
	dupes = frappe.db.sql(
		"""select reference_name, count(*) c from `tabSERK Idempotency Record`
		where reference_doctype='Sales Invoice' and reference_name in %(v)s
		group by reference_name having c > 1""",
		{"v": tuple(invoices or [""])},
	)
	checks.append(_check("idempotency.single_record_per_invoice", 0, len(dupes)))

	return {
		"pos_closing_entry": ce.name,
		"ok": all(c["ok"] for c in checks),
		"invoice_count": len(invoices),
		"checks": checks,
	}
