# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Command-center analytics and AI endpoints (v1). Read-only; managers and supervisors only."""

import frappe
from frappe import _

from serk_retail.ai import provider, service
from serk_retail.analytics.engine import snapshot
from serk_retail.core import authz
from serk_retail.core.errors import InvalidRequest

VIEW_ROLES = (authz.MANAGER, authz.SUPERVISOR, "System Manager")


def _company(company: str | None) -> str:
	authz.require_any_role(VIEW_ROLES, "view retail analytics")
	company = company or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company")
	if not company or not frappe.db.exists("Company", company):
		raise InvalidRequest(_("Choose a company."))
	if not frappe.has_permission("Company", "read", doc=company):
		raise frappe.PermissionError(_("You do not have access to {0}.").format(company))
	return company


@frappe.whitelist(methods=["GET"])
def companies() -> list:
	authz.require_any_role(VIEW_ROLES, "view retail analytics")
	return [c for c in frappe.get_list("Company", fields=["name", "default_currency", "abbr"], order_by="name")]


@frappe.whitelist(methods=["GET"])
def dashboard(company: str | None = None, days: int = 30, horizon: int = 14) -> dict:
	company = _company(company)
	data = snapshot(company, int(days), int(horizon))
	return {**data, "ai": service.status()}


def _ai_error(e: provider.AIError):
	messages = {
		"ai_not_configured": _("AI is not configured. Add an API key in SERK AI Settings or set SERK_AI_API_KEY on the server."),
		"ai_disabled": _("AI is switched off in SERK AI Settings."),
		"ai_auth_failed": _("The AI provider rejected the API key."),
		"ai_rate_limited": _("The AI provider is busy. Try again in a minute."),
		"ai_timeout": _("The AI provider did not answer in time."),
	}
	frappe.throw(messages.get(e.code, _("The AI service failed ({0}).").format(e.code)), title=_("SERK AI"))


@frappe.whitelist(methods=["POST"])
def ai_brief(kind: str, company: str | None = None, days: int = 30, horizon: int = 14, refresh: int = 0) -> dict:
	company = _company(company)
	try:
		return service.brief(kind, company, int(days), int(horizon), bool(int(refresh or 0)))
	except provider.AIError as e:
		_ai_error(e)


@frappe.whitelist(methods=["POST"])
def ai_ask(question: str, company: str | None = None, history: list | None = None, days: int = 30) -> dict:
	company = _company(company)
	try:
		return service.ask(company, question, history or [], int(days))
	except provider.AIError as e:
		_ai_error(e)
