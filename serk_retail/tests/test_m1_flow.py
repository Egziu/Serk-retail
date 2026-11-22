# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""M1 acceptance tests on a real MariaDB-backed ERPNext site.

These tests COMMIT (they exercise request boundaries and real concurrency), so run them only on
a disposable site:  bench --site serktest.localhost run-tests --module serk_retail.tests.test_m1_flow

Expected monetary values are computed here from the synthetic price list and the 15% VAT
assumption, independently of the implementation.
"""

import threading
import unittest
import uuid
from contextlib import contextmanager
from decimal import ROUND_HALF_UP, Decimal

import frappe
from frappe.utils import flt

from serk_retail.api import inventory, pos
from serk_retail.core.errors import (
	IdempotencyConflict,
	InsufficientPayment,
	InvalidRequest,
	NotAuthorized,
	RefundExceedsEntitlement,
)
from serk_retail.core.receipts import process_print_job, retry_failed_job
from serk_retail.devices.printer import simulator
from serk_retail.setup import demo

PRICE = {"SERK-WATER-500": Decimal("25"), "SERK-INJERA-5": Decimal("60"), "SERK-TEFF-KG": Decimal("140")}
VAT = Decimal("0.15")
LANE1, LANE2 = "SDM Lane 1", "SDM Lane 2"
C1, C2, SUP = "cashier1@serk.test", "cashier2@serk.test", "supervisor@serk.test"
WATER_BARCODE = "0012345678905"


def money(d: Decimal) -> float:
	return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def expected_total(lines):
	net = sum(PRICE[i] * Decimal(str(q)) for i, q in lines)
	tax = (net * VAT).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	return money(net), money(tax), money(net + tax)


def key():
	return str(uuid.uuid4())


@contextmanager
def as_user(user):
	old = frappe.session.user
	frappe.set_user(user)
	try:
		yield
	finally:
		frappe.set_user(old)


def call(user, fn, **kwargs):
	"""One API call = one request: commit on success, roll back on error (like Frappe's handler)."""
	with as_user(user):
		try:
			res = fn(**kwargs)
			frappe.db.commit()
			return res
		except Exception:
			frappe.db.rollback()
			raise


def stock_qty(item):
	return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": "Stores - SDM"}, "actual_qty"))


class TestM1RetailFlow(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.seed = demo.seed(write_credentials=False)
		cls.pw = cls.seed["credentials"]
		frappe.db.set_single_value("SERK Retail Settings", {"printer_adapter": "Simulated ESC/POS",
															"cash_variance_tolerance": 0, "require_approval_for_returns": 1,
															"receipt_width_chars": "48"})
		frappe.clear_document_cache("SERK Retail Settings", "SERK Retail Settings")
		frappe.db.commit()
		for lane in (LANE1, LANE2):
			cls._force_close_open_shifts(lane)
		# Plenty of stock for the suite (the full-cycle test also receives explicitly).
		call("receiver@serk.test", inventory.receive_stock, company=demo.COMPANY, supplier=demo.SUPPLIER,
			 warehouse="Stores - SDM", idempotency_key=key(),
			 items=[{"item_code": "SERK-WATER-500", "qty": 500, "rate": 12},
					{"item_code": "SERK-INJERA-5", "qty": 200, "rate": 35},
					{"item_code": "SERK-TEFF-KG", "qty": 100, "rate": 90}])

	@classmethod
	def _force_close_open_shifts(cls, lane):
		for oe in frappe.get_all("POS Opening Entry", {"pos_profile": lane, "status": "Open", "docstatus": 1},
								 ["name", "user"]):
			try:
				call(oe.user, pos.close_shift, pos_opening_entry=oe.name, counted=[], idempotency_key=key(),
					 variance_reason="test suite cleanup of a previous run")
			except Exception:
				frappe.db.rollback()

	def setUp(self):
		sim = simulator()
		sim.fault = None
		sim.sent.clear()

	def tearDown(self):
		frappe.db.rollback()
		frappe.set_user("Administrator")

	@contextmanager
	def shift(self, lane, cashier, float_=500):
		oe = call(cashier, pos.open_shift, pos_profile=lane, opening_cash=float_, idempotency_key=key())["pos_opening_entry"]
		try:
			yield oe
		finally:
			if frappe.db.get_value("POS Opening Entry", oe, "status") == "Open":
				self._force_close_open_shifts(lane)

	def sell(self, cashier, oe, lines, cash, k=None):
		return call(cashier, pos.submit_sale, pos_opening_entry=oe, items=lines,
					payments=[{"mode_of_payment": "Cash", "amount": cash}], idempotency_key=k or key())

	# ------------------------------------------------------------------ RET-M1-001 full cycle
	def test_01_receive_sell_receipt_return_close_reconcile(self):
		water0, teff0 = stock_qty("SERK-WATER-500"), stock_qty("SERK-TEFF-KG")
		pr = call("receiver@serk.test", inventory.receive_stock, company=demo.COMPANY, supplier=demo.SUPPLIER,
				  warehouse="Stores - SDM", idempotency_key=key(), supplier_delivery_note="DN-SYN-001",
				  items=[{"item_code": "SERK-WATER-500", "qty": 24, "rate": 12.5},
						 {"item_code": "SERK-TEFF-KG", "qty": 10.5, "rate": 92}])
		self.assertEqual(frappe.db.get_value("Purchase Receipt", pr["purchase_receipt"], "docstatus"), 1)
		self.assertAlmostEqual(stock_qty("SERK-WATER-500"), water0 + 24)
		self.assertAlmostEqual(stock_qty("SERK-TEFF-KG"), teff0 + 10.5)
		gl = frappe.db.sql("""select sum(debit), sum(credit) from `tabGL Entry` where voucher_no=%s and is_cancelled=0""",
						   pr["purchase_receipt"])[0]
		self.assertAlmostEqual(flt(gl[0]), 24 * 12.5 + 10.5 * 92)  # stock value received
		self.assertAlmostEqual(flt(gl[0]), flt(gl[1]))

		water1, teff1 = stock_qty("SERK-WATER-500"), stock_qty("SERK-TEFF-KG")
		with self.shift(LANE1, C1, float_=500) as oe:
			lines = [{"barcode": WATER_BARCODE, "qty": 1}, {"barcode": WATER_BARCODE, "qty": 1},
					 {"barcode": WATER_BARCODE, "qty": 1}, {"item_code": "SERK-TEFF-KG", "qty": 1.25},
					 {"barcode": "INJ5", "qty": 2}]
			net, tax, total = expected_total([("SERK-WATER-500", 3), ("SERK-TEFF-KG", 1.25), ("SERK-INJERA-5", 2)])
			self.assertEqual((net, tax, total), (370.0, 55.5, 425.5))
			sale = self.sell(C1, oe, lines, cash=1000)
			si = frappe.get_doc("Sales Invoice", sale["sales_invoice"])
			self.assertEqual(si.docstatus, 1)
			self.assertEqual(si.owner, C1)
			self.assertAlmostEqual(si.net_total, net)
			self.assertAlmostEqual(si.total_taxes_and_charges, tax)
			self.assertAlmostEqual(sale["grand_total"], total)
			self.assertAlmostEqual(sale["change_amount"], 1000 - total)
			self.assertAlmostEqual(stock_qty("SERK-WATER-500"), water1 - 3)
			self.assertAlmostEqual(stock_qty("SERK-TEFF-KG"), teff1 - 1.25)

			# Receipt is printed after commit; drawer pulses exactly once.
			pj = call(C1, process_print_job, job_name=sale["print_job"])
			self.assertEqual(pj["status"], "Acknowledged")
			self.assertEqual(simulator().drawer_pulses, 1)
			text = frappe.db.get_value("SERK Print Job", sale["print_job"], "rendered_text")
			self.assertIn("TOTAL", text)
			self.assertIn(si.name, text)
			self.assertNotIn("COPY", text)

			# Partial return of a weighted + packaged line, supervisor-approved, original price/tax.
			water_row = next(i.name for i in si.items if i.item_code == "SERK-WATER-500")
			teff_row = next(i.name for i in si.items if i.item_code == "SERK-TEFF-KG")
			ret = call(C1, pos.submit_return, pos_opening_entry=oe, return_against=si.name,
					   items=[{"original_line": water_row, "qty": 1}, {"original_line": teff_row, "qty": 0.25}],
					   reason="Customer changed mind", approver=SUP, approver_password=self.pw[SUP],
					   idempotency_key=key())
			_rnet, rtax, rtotal = expected_total([("SERK-WATER-500", 1), ("SERK-TEFF-KG", 0.25)])
			self.assertAlmostEqual(ret["grand_total"], -rtotal)
			rsi = frappe.get_doc("Sales Invoice", ret["sales_invoice"])
			self.assertEqual((rsi.is_return, rsi.return_against, rsi.docstatus), (1, si.name, 1))
			self.assertAlmostEqual(rsi.total_taxes_and_charges, -rtax)
			self.assertAlmostEqual(stock_qty("SERK-WATER-500"), water1 - 2)
			self.assertAlmostEqual(stock_qty("SERK-TEFF-KG"), teff1 - 1.0)

			# Blind close with an exact count.
			counted = 500 + total - rtotal
			close = call(C1, pos.close_shift, pos_opening_entry=oe, counted=[{"mode_of_payment": "Cash", "amount": counted}],
						 idempotency_key=key())
			self.assertEqual(close["variances"], {"Cash": 0.0})
			self.assertEqual(close["invoice_count"], 2)
			self.assertAlmostEqual(close["grand_total"], total - rtotal)
			self.assertEqual(frappe.db.get_value("POS Opening Entry", oe, "status"), "Closed")

			rec = call(SUP, pos.reconcile_shift, pos_closing_entry=close["pos_closing_entry"])
			failed = [c for c in rec["checks"] if not c["ok"]]
			self.assertTrue(rec["ok"], failed)
			self.assertGreaterEqual(len(rec["checks"]), 8)

		# Whole-company ledger stays balanced.
		dr, cr = frappe.db.sql("""select sum(debit), sum(credit) from `tabGL Entry` where company=%s and is_cancelled=0""",
							   demo.COMPANY)[0]
		self.assertAlmostEqual(flt(dr), flt(cr), places=2)

	# ------------------------------------------------------------------ RET-POS-005 idempotency
	def test_02_retry_with_same_key_returns_same_sale(self):
		with self.shift(LANE2, C2) as oe:
			k = key()
			a = self.sell(C2, oe, [{"item_code": "SERK-WATER-500", "qty": 2}], 100, k=k)
			b = self.sell(C2, oe, [{"item_code": "SERK-WATER-500", "qty": 2}], 100, k=k)
			self.assertEqual(a["sales_invoice"], b["sales_invoice"])
			self.assertFalse(a["idempotent_replay"])
			self.assertTrue(b["idempotent_replay"])
			self.assertEqual(frappe.db.count("SERK Audit Event", {"reference_name": a["sales_invoice"], "event_type": "sale.completed"}), 1)

	def test_03_same_key_different_payload_is_rejected(self):
		with self.shift(LANE2, C2) as oe:
			k = key()
			self.sell(C2, oe, [{"item_code": "SERK-WATER-500", "qty": 1}], 50, k=k)
			before = frappe.db.count("Sales Invoice", {"docstatus": 1})
			with self.assertRaises(IdempotencyConflict):
				self.sell(C2, oe, [{"item_code": "SERK-WATER-500", "qty": 5}], 200, k=k)
			self.assertEqual(frappe.db.count("Sales Invoice", {"docstatus": 1}), before)

	def test_04_concurrent_duplicate_requests_create_one_sale(self):
		with self.shift(LANE2, C2) as oe:
			k = key()
			site, sites_path = frappe.local.site, frappe.local.sites_path
			before = frappe.db.count("Sales Invoice", {"docstatus": 1, "pos_profile": LANE2})
			results, errors = [], []

			def worker():
				frappe.init(site=site, sites_path=sites_path)
				frappe.connect()
				frappe.flags.in_test = True
				try:
					frappe.set_user(C2)
					r = pos.submit_sale(pos_opening_entry=oe, items=[{"item_code": "SERK-INJERA-5", "qty": 1}],
										payments=[{"mode_of_payment": "Cash", "amount": 100}], idempotency_key=k)
					frappe.db.commit()
					results.append(r["sales_invoice"])
				except Exception as e:  # recorded, asserted below
					frappe.db.rollback()
					errors.append(repr(e))
				finally:
					frappe.destroy()

			threads = [threading.Thread(target=worker) for _ in range(4)]
			for t in threads:
				t.start()
			for t in threads:
				t.join(60)
			frappe.db.rollback()  # refresh snapshot
			after = frappe.db.count("Sales Invoice", {"docstatus": 1, "pos_profile": LANE2})
			self.assertEqual(after - before, 1, errors)
			self.assertEqual(len(set(results)), 1, (results, errors))
			# Every caller either got the same sale or a retryable in-progress error; none failed silently.
			for e in errors:
				self.assertIn("IdempotencyInProgress", e)

	# ------------------------------------------------------------------ RET-POS-010 refunds
	def test_05_refund_cannot_exceed_remaining_entitlement(self):
		with self.shift(LANE2, C2) as oe:
			sale = self.sell(C2, oe, [{"item_code": "SERK-WATER-500", "qty": 2}], 100)
			row = frappe.db.get_value("Sales Invoice Item", {"parent": sale["sales_invoice"]}, "name")
			args = dict(pos_opening_entry=oe, return_against=sale["sales_invoice"], reason="damaged",
						approver=SUP, approver_password=self.pw[SUP])
			with self.assertRaises(RefundExceedsEntitlement):
				call(C2, pos.submit_return, items=[{"original_line": row, "qty": 3}], idempotency_key=key(), **args)
			call(C2, pos.submit_return, items=[{"original_line": row, "qty": 2}], idempotency_key=key(), **args)
			with self.assertRaises(RefundExceedsEntitlement):
				call(C2, pos.submit_return, items=[{"original_line": row, "qty": 1}], idempotency_key=key(), **args)
			returned = frappe.db.sql("""select sum(qty) from `tabSales Invoice Item` where sales_invoice_item=%s and docstatus=1""", row)[0][0]
			self.assertAlmostEqual(flt(returned), -2)

	# ------------------------------------------------------------------ RET-SEC-002 separation of duties
	def test_06_cashier_cannot_self_approve_or_use_bad_approval(self):
		with self.shift(LANE2, C2) as oe:
			sale = self.sell(C2, oe, [{"item_code": "SERK-WATER-500", "qty": 1}], 50)
			base = dict(pos_opening_entry=oe, return_against=sale["sales_invoice"], reason="x",
						items=[{"item_code": "SERK-WATER-500", "qty": 1}])
			refused0 = frappe.db.count("SERK Audit Event", {"event_type": "return.submit", "outcome": "Refused"})
			with self.assertRaises(NotAuthorized):
				call(C2, pos.submit_return, approver=C2, approver_password=self.pw[C2], idempotency_key=key(), **base)
			with self.assertRaises(NotAuthorized):
				call(C2, pos.submit_return, approver=C1, approver_password=self.pw[C1], idempotency_key=key(), **base)
			with self.assertRaises(NotAuthorized):
				call(C2, pos.submit_return, approver=SUP, approver_password="wrong-password-123", idempotency_key=key(), **base)
			with self.assertRaises(NotAuthorized):
				call(C2, pos.submit_return, idempotency_key=key(), **base)
			self.assertEqual(frappe.db.count("SERK Audit Event", {"event_type": "return.submit", "outcome": "Refused"}), refused0 + 4)
			self.assertEqual(frappe.db.count("Sales Invoice", {"return_against": sale["sales_invoice"]}), 0)

	def test_07_cashier_cannot_use_another_cashiers_shift_or_register(self):
		with self.shift(LANE2, C2) as oe:
			with self.assertRaises(NotAuthorized):
				self.sell(C1, oe, [{"item_code": "SERK-WATER-500", "qty": 1}], 50)
		with self.assertRaises(NotAuthorized):
			call(C1, pos.open_shift, pos_profile=LANE2, opening_cash=0, idempotency_key=key())
		with self.assertRaises(frappe.PermissionError):
			call(SUP, pos.submit_sale, pos_opening_entry="x", items=[{"item_code": "SERK-WATER-500", "qty": 1}],
				 payments=[], idempotency_key=key())

	# ------------------------------------------------------------------ RET-HW-003 print failure
	def test_08_print_failure_keeps_sale_and_never_pulses_drawer_twice(self):
		with self.shift(LANE2, C2) as oe:
			sale = self.sell(C2, oe, [{"item_code": "SERK-INJERA-5", "qty": 1}], 100)
			sim = simulator()
			sim.fault = "paper_out"
			r1 = call(C2, process_print_job, job_name=sale["print_job"])
			self.assertEqual(r1["status"], "Failed")
			self.assertEqual(frappe.db.get_value("Sales Invoice", sale["sales_invoice"], "docstatus"), 1)
			self.assertEqual(sim.drawer_pulses, 1)
			sim.fault = None
			r2 = call(C2, retry_failed_job, job_name=sale["print_job"])
			self.assertEqual(r2["status"], "Acknowledged")
			self.assertEqual(sim.drawer_pulses, 1, "retry must not re-open the drawer")
			cp = call(C2, pos.reprint_receipt, sales_invoice=sale["sales_invoice"], reason="customer asked")
			call(C2, process_print_job, job_name=cp["print_job"])
			self.assertIn("COPY 1", frappe.db.get_value("SERK Print Job", cp["print_job"], "rendered_text"))
			self.assertEqual(sim.drawer_pulses, 1, "reprint must not open the drawer")
			self.assertEqual(frappe.db.count("Sales Invoice", {"name": sale["sales_invoice"]}), 1)

			sale2 = self.sell(C2, oe, [{"item_code": "SERK-INJERA-5", "qty": 1}], 100)
			sim.fault = "timeout"
			self.assertEqual(call(C2, process_print_job, job_name=sale2["print_job"])["status"], "Delivery Unknown")
			with self.assertRaises(InvalidRequest):
				call(C2, retry_failed_job, job_name=sale2["print_job"])

	# ------------------------------------------------------------------ RET-POS-002/003 input validation
	def test_09_barcode_price_and_payment_validation(self):
		with self.shift(LANE2, C2) as oe:
			with self.assertRaises(InvalidRequest):  # leading zeros are significant
				self.sell(C2, oe, [{"barcode": "12345678905", "qty": 1}], 50)
			with self.assertRaises(InvalidRequest):  # barcode must be a string
				self.sell(C2, oe, [{"barcode": 12345678905, "qty": 1}], 50)
			with self.assertRaises(InvalidRequest):  # client price not trusted
				self.sell(C2, oe, [{"item_code": "SERK-WATER-500", "qty": 1, "rate": 1}], 50)
			with self.assertRaises(InvalidRequest):
				self.sell(C2, oe, [{"item_code": "SERK-WATER-500", "qty": 0}], 50)
			with self.assertRaises(InsufficientPayment):
				self.sell(C2, oe, [{"item_code": "SERK-WATER-500", "qty": 2}], 57.49)  # due 57.50
			ok = self.sell(C2, oe, [{"item_code": "SERK-WATER-500", "qty": 2}], 57.50)
			self.assertAlmostEqual(ok["change_amount"], 0)

	def test_10_stock_shortfall_is_atomic(self):
		with self.shift(LANE2, C2) as oe:
			k = key()
			before = frappe.db.count("Sales Invoice", {"docstatus": 1})
			with self.assertRaises(frappe.ValidationError):
				self.sell(C2, oe, [{"item_code": "SERK-TEFF-KG", "qty": 100000}], 100000000, k=k)
			self.assertEqual(frappe.db.count("Sales Invoice", {"docstatus": 1}), before)
			from serk_retail.core.idempotency import record_name
			self.assertFalse(frappe.db.exists("SERK Idempotency Record", record_name("sale.submit", oe, k)))

	# ------------------------------------------------------------------ RET-POS-008 shift close
	def test_11_variance_requires_reason_and_is_recorded(self):
		with self.shift(LANE2, C2, float_=200) as oe:
			self.sell(C2, oe, [{"item_code": "SERK-WATER-500", "qty": 2}], 57.5)
			with self.assertRaises(InvalidRequest):
				call(C2, pos.close_shift, pos_opening_entry=oe, counted=[{"mode_of_payment": "Cash", "amount": 250}],
					 idempotency_key=key())
			res = call(C2, pos.close_shift, pos_opening_entry=oe, counted=[{"mode_of_payment": "Cash", "amount": 250}],
					   idempotency_key=key(), variance_reason="7.50 short; recount pending")
			self.assertAlmostEqual(res["variances"]["Cash"], -7.5)
			rec = call(SUP, pos.reconcile_shift, pos_closing_entry=res["pos_closing_entry"])
			self.assertTrue(rec["ok"], [c for c in rec["checks"] if not c["ok"]])
			self.assertTrue(frappe.db.exists("SERK Audit Event", {"event_type": "shift.closed", "reference_name": res["pos_closing_entry"],
																  "reason": "7.50 short; recount pending"}))

	# ------------------------------------------------------------------ RET-SEC-005 audit integrity
	def test_12_audit_events_are_append_only(self):
		name = frappe.get_all("SERK Audit Event", limit=1, pluck="name")[0]
		doc = frappe.get_doc("SERK Audit Event", name)
		doc.reason = "tampered"
		with self.assertRaises(frappe.PermissionError):
			doc.save(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc("SERK Audit Event", name, ignore_permissions=True)

	# ------------------------------------------------------------------ RET-POS-011 concurrent refunds
	def test_13_concurrent_refunds_cannot_exceed_entitlement(self):
		with self.shift(LANE2, C2) as oe:
			sale = self.sell(C2, oe, [{"item_code": "SERK-WATER-500", "qty": 2}], 100)
			row = frappe.db.get_value("Sales Invoice Item", {"parent": sale["sales_invoice"]}, "name")
			site, sites_path, pw = frappe.local.site, frappe.local.sites_path, self.pw[SUP]
			ok, errors = [], []

			def worker():
				frappe.init(site=site, sites_path=sites_path)
				frappe.connect()
				frappe.flags.in_test = True
				try:
					frappe.set_user(C2)
					r = pos.submit_return(pos_opening_entry=oe, return_against=sale["sales_invoice"],
										  items=[{"original_line": row, "qty": 2}], reason="concurrency test",
										  approver=SUP, approver_password=pw, idempotency_key=key())
					frappe.db.commit()
					ok.append(r["sales_invoice"])
				except Exception as e:
					frappe.db.rollback()
					errors.append(type(e).__name__)
				finally:
					frappe.destroy()

			threads = [threading.Thread(target=worker) for _ in range(3)]
			for t in threads:
				t.start()
			for t in threads:
				t.join(60)
			frappe.db.rollback()
			self.assertEqual(len(ok), 1, (ok, errors))
			self.assertEqual(sorted(errors), ["RefundExceedsEntitlement"] * 2)
			returned = frappe.db.sql("""select sum(qty) from `tabSales Invoice Item` where sales_invoice_item=%s and docstatus=1""", row)[0][0]
			self.assertAlmostEqual(flt(returned), -2)
