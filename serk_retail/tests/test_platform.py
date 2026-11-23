# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Platform tests: brand, company setup, analytics/forecasting and AI grounding.

Like the M1 suite these COMMIT (setup creates real ERPNext documents): run on a disposable site.
    bench --site serktest.localhost run-tests --module serk_retail.tests.test_platform
"""

import json
import unittest
import uuid
from unittest import mock

import frappe
import numpy as np

from serk_retail import branding
from serk_retail.ai import provider, service
from serk_retail.analytics import engine
from serk_retail.analytics import forecast as fc
from serk_retail.api import insights, setup
from serk_retail.core.errors import NotAuthorized
from serk_retail.setup import demo


def as_user(user):
	class _Ctx:
		def __enter__(self):
			self.old = frappe.session.user
			frappe.set_user(user)

		def __exit__(self, *a):
			frappe.set_user(self.old)

	return _Ctx()


class TestForecastMath(unittest.TestCase):
	def test_recovers_trend_and_weekday_pattern(self):
		rng = np.random.default_rng(1)
		n = 84
		wd = np.arange(n) % 7
		season = np.array([0.9, 0.85, 0.95, 0.9, 1.05, 1.3, 1.05])
		y = (1000 + 6 * np.arange(n)) * season[wd] * rng.normal(1, 0.05, n)
		f = fc.forecast_daily(y, wd, 14, int((wd[-1] + 1) % 7))
		truth = (1000 + 6 * np.arange(n, n + 14)) * season[np.arange(n, n + 14) % 7]
		mape = float(np.mean(np.abs(np.array(f.values) - truth) / truth))
		self.assertLess(mape, 0.08)
		self.assertGreater(f.weekday_index[5], f.weekday_index[1])  # Saturday above Tuesday
		self.assertIsNotNone(f.mape)
		self.assertTrue(all(lo <= v <= hi for lo, v, hi in zip(f.lower, f.values, f.upper, strict=False)))

	def test_short_history_falls_back(self):
		f = fc.forecast_daily([10, 12, 11], [0, 1, 2], 5, 3)
		self.assertEqual(f.method, "recent average")
		self.assertEqual(len(f.values), 5)

	def test_reorder_and_abc_and_lift(self):
		self.assertEqual(fc.reorder_advice(30, 5, 2)["status"], "critical")
		self.assertEqual(fc.reorder_advice(1000, 2, 1)["status"], "overstock")
		self.assertEqual(fc.reorder_advice(0, 0, 0)["status"], "no recent demand")
		self.assertEqual(fc.abc_classes({"a": 800, "b": 100, "c": 60, "d": 40}), {"a": "A", "b": "B", "c": "B", "d": "C"})
		baskets = [{"x", "y"}] * 30 + [{"x"}] * 20 + [{"y"}] * 10 + [{"z"}] * 60
		top = fc.pair_lift(baskets)
		self.assertEqual((top[0]["a"], top[0]["b"]), ("x", "y"))
		self.assertGreater(top[0]["lift"], 1)


class TestPlatform(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.creds = demo.seed(write_credentials=False)["credentials"]
		frappe.db.commit()

	def tearDown(self):
		frappe.db.rollback()
		frappe.set_user("Administrator")

	# ---------------------------------------------------------------- brand
	def test_brand_replaces_upstream_identity(self):
		boot = frappe._dict(app_data=[{"app_name": "erpnext", "app_title": "ERPNext", "app_logo_url": "/x.svg"},
									  {"app_name": "frappe", "app_title": "Framework", "module_icons": [1]}])
		branding.extend_bootinfo(boot)
		titles = {a["app_name"]: a["app_title"] for a in boot.app_data}
		self.assertEqual(titles["erpnext"], "Back Office")
		self.assertEqual(titles["frappe"], "System")
		self.assertNotIn("erpnext", json.dumps(boot.serk_brand).lower())
		ctx = branding.update_website_context(frappe._dict())
		self.assertNotIn("ERPNext", ctx["footer_powered"])
		html = frappe.render_template("templates/emails/email_footer.html", {"default_mail_footer": ["Sent via ERPNext"]})
		self.assertNotIn("ERPNext", html)

	def test_brand_colours_validated(self):
		doc = frappe.get_single("SERK Brand Settings")
		doc.primary_color = "green"
		self.assertRaises(frappe.ValidationError, doc.validate)

	# ---------------------------------------------------------------- setup
	def test_company_setup_creates_a_working_retail_company(self):
		suffix = uuid.uuid4().hex[:4].upper()
		name = f"SERK Test Market {suffix}"
		res = setup.create_company(company_name=name, abbr=f"T{suffix}", vat_rate=15, first_store="Kebele 14",
								   set_as_brand=0)
		frappe.db.commit()
		self.assertTrue(frappe.db.exists("Warehouse", res["store"]))
		self.assertTrue(frappe.db.exists("Sales Taxes and Charges Template", res["tax_template"]))
		reg = setup.create_register(company=name, warehouse=res["store"], register_name=f"{suffix} Lane 1",
									cashiers=["cashier1@serk.test"], tax_template=res["tax_template"])
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("POS Profile", reg["register"], "warehouse"), res["store"])
		staff = setup.create_staff(email=f"c{suffix.lower()}@serk.test", full_name="Test Cashier", role="Cashier",
								   registers=[reg["register"]])
		frappe.db.commit()
		self.assertIn("SERK Cashier", frappe.get_roles(staff["user"]))
		self.assertTrue(staff["temporary_password"].startswith("Serk-"))
		self.assertTrue(frappe.db.exists("SERK Audit Event", {"event_type": "setup.company_created", "reference_name": name}))

	def test_setup_is_role_gated(self):
		with as_user("cashier1@serk.test"):
			self.assertRaises(NotAuthorized, setup.state)
			self.assertRaises(NotAuthorized, setup.create_company, company_name="X", abbr="XX")
		with as_user("manager@serk.test"):
			setup.state()  # managers may view and add stores/registers
			self.assertRaises(NotAuthorized, setup.create_staff, email="z@serk.test", full_name="Z", role="Cashier")

	# ---------------------------------------------------------------- analytics + AI
	def test_dashboard_is_manager_only_and_complete(self):
		with as_user("cashier1@serk.test"):
			self.assertRaises(NotAuthorized, insights.dashboard, company=demo.COMPANY)
		with as_user("manager@serk.test"):
			d = insights.dashboard(company=demo.COMPANY, days=30, horizon=14)
		for key in ("kpis", "daily", "forecast", "heatmap", "top_items", "categories", "stock", "affinity", "insights", "ai"):
			self.assertIn(key, d)
		self.assertEqual(len(d["forecast"]["values"]), 14)
		self.assertEqual(len(d["heatmap"]["values"]), 7)

	def test_model_payload_never_leaks_people(self):
		data = engine.snapshot(demo.COMPANY, 30, 14)
		data = dict(data)
		data["cashiers"] = [{"user": "cashier1@serk.test", "name": "Cashier One", "revenue": 10, "transactions": 1,
							 "returns": 0, "refund_rate_pct": 0, "refund_z": 0, "avg_basket": 10}]
		blob = json.dumps(service.model_payload(data))
		self.assertNotIn("@serk.test", blob)
		self.assertNotIn("Cashier One", blob)
		self.assertIn("Cashier A", blob)
		no_names = json.dumps(service.model_payload(data, share_names=False))
		self.assertNotIn('"item_name"', no_names)

	def test_ai_brief_uses_provider_and_is_audited(self):
		cfg = provider.Config("anthropic", "claude-sonnet-5-5", "k", "", 800, "environment")
		seen = {}

		def fake_complete(c, system, messages, max_tokens=None):
			seen["system"], seen["user"] = system, messages[-1]["content"]
			return {"text": "## Headline\nAll good.", "usage": {"input_tokens": 10, "output_tokens": 5}}

		before = frappe.db.count("SERK Audit Event", {"event_type": "ai.insights"})
		with mock.patch.object(provider, "get_config", return_value=cfg), mock.patch.object(provider, "complete", fake_complete):
			with as_user("manager@serk.test"):
				out = insights.ai_brief(kind="insights", company=demo.COMPANY, refresh=1)
		frappe.db.commit()
		self.assertIn("Headline", out["text"])
		self.assertIn("Use ONLY the figures in the DATA block", seen["system"])
		self.assertIn('"kpis"', seen["user"])
		self.assertEqual(frappe.db.count("SERK Audit Event", {"event_type": "ai.insights"}), before + 1)

	def test_ai_not_configured_is_a_clear_error(self):
		with mock.patch.object(provider, "get_config", side_effect=provider.AIError("ai_not_configured")):
			with as_user("manager@serk.test"):
				self.assertRaises(frappe.ValidationError, insights.ai_ask, question="hi", company=demo.COMPANY)

	def test_chat_history_is_normalised(self):
		captured = {}

		def fake_call(kind, company, prompt, data, history=None):
			captured["history"] = history
			return {"text": "ok"}

		with mock.patch.object(service, "_call", fake_call):
			service.ask(demo.COMPANY, "q", [{"role": "assistant", "content": "x"}, {"role": "user", "content": "a"},
											{"role": "assistant", "content": "b"}, {"role": "user", "content": "dangling"},
											{"role": "system", "content": "evil"}])
		roles = [t["role"] for t in captured["history"]]
		self.assertEqual(roles, ["user", "assistant"])
