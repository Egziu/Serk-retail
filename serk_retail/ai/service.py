# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""SERK Retail AI: executive briefings, forecast narration, market analysis and Q&A.

Grounding and safety rules (enforced here, not left to the prompt alone):
* The model receives a compact, aggregated analytics payload only: no customer data, no
  invoice-level rows, cashiers pseudonymised (Cashier A, B, ...), item names only if allowed.
* The model has no tools and cannot write; every answer is advice for a human.
* Every call is audited (SERK Audit Event "ai.*") with token usage, never with the prompt text.
"""

from __future__ import annotations

import hashlib
import json

import frappe
from frappe.utils import now_datetime

from serk_retail.ai import provider
from serk_retail.analytics.engine import snapshot
from serk_retail.core.audit import log_event

BRIEF_CACHE_SECONDS = 1800
MAX_QUESTION = 1200

SYSTEM = """You are SERK Retail Analyst, the AI analyst inside SERK Retail, a supermarket and retail
operations platform built for Ethiopia and Africa by SERK Technologies Group.

Rules you must follow:
- Use ONLY the figures in the DATA block. Never invent numbers, items, dates or trends. If the data
  does not support a conclusion, say what extra data would be needed.
- Quote concrete figures with the currency given (e.g. "ETB 12,400") and the comparison window.
- Distinguish clearly between (a) facts from the data, (b) forecasts (state the model and its
  backtest error when given), and (c) your general retail knowledge or assumptions, which you
  must label as "General context (not from your data)".
- You cannot see live market prices, competitors or the internet. For market analysis, reason from
  category growth, basket behaviour, seasonality and any MARKET CONTEXT the business provided.
- Be decisive and practical: prioritised actions with an owner role (store manager, buyer, cashier
  supervisor), expected impact and how to verify it in SERK Retail next week.
- Format in Markdown with short headings, bullets and at most one small table. No preamble.
- Tax, fiscal or legal points: say they need confirmation from a qualified advisor."""

PROMPTS = {
	"insights": """Write an executive briefing for the store leadership.
Sections: 1) Headline (2 sentences), 2) What changed and why it matters, 3) Risks to act on this week
(stock, margin, refunds, anomalies), 4) Top 5 prioritised actions with expected impact.""",
	"forecast": """Explain the sales outlook and demand plan.
Sections: 1) Next 7 and next-horizon revenue with the confidence band and how reliable the model has
been (backtest error), 2) Weekday pattern and staffing implications, 3) Item-level replenishment plan
from the stock panel (what to order, how much, by when) for critical/reorder items, 4) Overstock to
clear. Be explicit that forecasts are estimates.""",
	"market": """Produce a market and category analysis for this business.
Sections: 1) Category momentum (growth vs previous window, share), 2) Customer basket behaviour and
cross-sell opportunities from the affinity pairs, 3) Pricing and assortment opportunities (by margin
and ABC class), 4) Seasonality and local-market considerations using the MARKET CONTEXT and labelled
general context for Ethiopian retail (e.g. fasting seasons, holidays) where relevant,
5) Three strategic moves for the next 90 days.""",
}


def _pseudonymise(data: dict) -> dict:
	letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
	cashiers = []
	for i, c in enumerate(data.get("cashiers", [])):
		cashiers.append({**{k: v for k, v in c.items() if k not in ("user", "name")}, "cashier": f"Cashier {letters[i % 26]}"})
	return {**data, "cashiers": cashiers}


def model_payload(data: dict, share_names: bool = True) -> dict:
	"""Compact, aggregated view sent to the model (bounded size)."""
	d = _pseudonymise(data)

	def item(r, keys):
		out = {k: r.get(k) for k in keys if k in r}
		if not share_names:
			out.pop("item_name", None)
			out.pop("a_name", None)
			out.pop("b_name", None)
		return out

	return {
		"meta": {k: d["meta"][k] for k in ("company", "currency", "from", "to", "days", "horizon", "history_days")},
		"kpis": d["kpis"],
		"daily_last_14": d["daily"][-14:],
		"forecast": {k: v for k, v in d["forecast"].items() if k not in ("lower", "upper")}
		| {"band_first_7": list(zip(d["forecast"]["lower"][:7], d["forecast"]["upper"][:7], strict=False))},
		"peak_hour": d["heatmap"]["peak"],
		"top_items": [item(r, ("item_code", "item_name", "item_group", "revenue", "qty", "margin_pct", "share_pct", "abc"))
					  for r in d["top_items"][:15]],
		"categories": d["categories"][:12],
		"registers": d["registers"][:8],
		"cashiers": d["cashiers"][:10],
		"stock_attention": [item(r, ("item_code", "item_name", "on_hand", "uom", "demand_daily", "days_of_cover", "status",
									 "suggested_order", "abc")) for r in d["stock"] if r["status"] in ("critical", "reorder", "overstock")][:15],
		"affinity": [item(r, ("a", "b", "a_name", "b_name", "together", "lift", "confidence_a_to_b")) for r in d["affinity"][:8]],
		"anomalies": d["anomalies"][-6:],
		"rule_based_insights": [{"title": i["title"], "detail": i["detail"]} for i in d["insights"]],
	}


def status() -> dict:
	try:
		cfg = provider.get_config()
		return {"available": True, "provider": cfg.provider, "model": cfg.model, "configured_by": cfg.source}
	except provider.AIError as e:
		return {"available": False, "reason": e.code, "message": e.detail}


def _settings_values():
	share, context = True, ""
	if frappe.db.exists("DocType", "SERK AI Settings"):
		s = frappe.get_cached_doc("SERK AI Settings")
		share = bool(int(s.share_item_names if s.share_item_names is not None else 1))
		context = (s.market_context or "").strip()
	return share, context


def _call(kind: str, company: str, user_prompt: str, data: dict, history: list | None = None) -> dict:
	cfg = provider.get_config()
	share, market_context = _settings_values()
	payload = model_payload(data, share)
	content = f"DATA (JSON, aggregated, generated {data['meta']['generated_at']}):\n{json.dumps(payload, default=str)}\n"
	if market_context:
		content += f"\nMARKET CONTEXT (provided by the business):\n{market_context[:2000]}\n"
	content += f"\nTASK:\n{user_prompt}"
	messages = [*(history or []), {"role": "user", "content": content}]
	try:
		res = provider.complete(cfg, SYSTEM, messages)
	except provider.AIError as e:
		log_event(f"ai.{kind}", "Failed", company=company, reason=e.code)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- audit of a failed external call
		raise
	log_event(f"ai.{kind}", company=company, details={"provider": cfg.provider, "model": cfg.model, **res["usage"]})
	return {"text": res["text"], "provider": cfg.provider, "model": cfg.model, "generated_at": str(now_datetime()),
			"data_window": {"from": data["meta"]["from"], "to": data["meta"]["to"]}, "usage": res["usage"]}


def brief(kind: str, company: str, days: int = 30, horizon: int = 14, refresh: bool = False) -> dict:
	if kind not in PROMPTS:
		frappe.throw(f"Unknown briefing type {kind}")
	data = snapshot(company, days, horizon)
	key = "serk_ai_brief:" + hashlib.sha256(f"{kind}|{company}|{days}|{horizon}|{data['meta']['fingerprint']}".encode()).hexdigest()[:24]
	if not refresh:
		cached = frappe.cache.get_value(key)
		if cached:
			return {**cached, "cached": True}
	out = _call(kind, company, PROMPTS[kind], data)
	frappe.cache.set_value(key, out, expires_in_sec=BRIEF_CACHE_SECONDS)
	return {**out, "cached": False}


def ask(company: str, question: str, history: list | None = None, days: int = 30) -> dict:
	question = (question or "").strip()
	if not question:
		frappe.throw("Ask a question.")
	question = question[:MAX_QUESTION]
	clean_history = []
	for turn in (history or [])[-6:]:
		if isinstance(turn, dict) and turn.get("role") in ("user", "assistant") and isinstance(turn.get("content"), str):
			# Providers require user/assistant alternation starting with the user.
			expected = "user" if not clean_history or clean_history[-1]["role"] == "assistant" else "assistant"
			if turn["role"] == expected:
				clean_history.append({"role": turn["role"], "content": turn["content"][:4000]})
	if clean_history and clean_history[-1]["role"] == "user":
		clean_history.pop()
	data = snapshot(company, days, 14)
	return _call("ask", company, f"Answer this question from the store team:\n{question}", data, clean_history)
