# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Server-side authorization for SERK APIs.

SERK cashier roles deliberately do NOT receive broad ERPNext doctype permissions (e.g. Accounts
User), which would let a cashier edit or cancel any invoice from the desk. Instead, SERK APIs
check role + register assignment + shift ownership here, then perform the upstream document
operation with ignore_permissions while the cashier remains the document owner.
See docs/security/ROLE_MATRIX.md and ADR-003.
"""

from contextlib import contextmanager

import frappe
from frappe.utils.password import check_password

from serk_retail.core.errors import NotAuthorized

CASHIER = "SERK Cashier"
SUPERVISOR = "SERK Shift Supervisor"
MANAGER = "SERK Store Manager"
RECEIVER = "SERK Receiver"

SERK_ROLES = (CASHIER, SUPERVISOR, MANAGER, RECEIVER)


@contextmanager
def system_context_for_pure_mapping():
	"""Run a NON-WRITING upstream helper (e.g. ERPNext's return mapper, which checks 'create' on
	Sales Invoice and has no ignore_permissions parameter) as Administrator, then restore the
	caller. Must never wrap insert/submit/save — those run as the real user so ownership,
	audit and closing selection stay truthful. Registered in CORE_PATCH_REGISTER as a workaround."""
	user = frappe.session.user
	writes_before = frappe.db.transaction_writes
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(user)
	if frappe.db.transaction_writes != writes_before:
		raise RuntimeError("system_context_for_pure_mapping wrapped a database write")


def has_any_role(roles, user=None) -> bool:
	user_roles = set(frappe.get_roles(user or frappe.session.user))
	return bool(user_roles.intersection(roles))


def require_any_role(roles, action: str):
	if not has_any_role(roles):
		raise NotAuthorized(f"You are not permitted to {action}.")


def require_register_assignment(pos_profile: str, user=None):
	user = user or frappe.session.user
	if not frappe.db.exists("POS Profile User", {"parent": pos_profile, "user": user}):
		raise NotAuthorized(f"You are not assigned to register {pos_profile}.")


def verify_approver(approver: str, approver_password: str, actor: str, roles=(SUPERVISOR, MANAGER)):
	"""Supervisor override at the register: a different user with an approving role re-enters
	their own password.

	Brute-force protection (RISK_REGISTER R-08): failed approvals are counted per approver in Redis
	(Frappe's LoginAttemptTracker, separate key from desk logins). After APPROVAL_MAX_FAILURES
	failures inside APPROVAL_LOCK_SECONDS the approver is locked for approvals until the window
	expires, even with the right password. The counter lives in Redis, so it survives the request
	rollback that log_refusal_and_raise performs."""
	if not approver or not approver_password:
		raise NotAuthorized("Supervisor approval is required.")
	if approver == actor:
		raise NotAuthorized("You cannot approve your own restricted action.")
	tracker = approval_tracker(approver)
	if not tracker.is_user_allowed():
		raise NotAuthorized("Too many failed approvals for this supervisor. Try again later.")
	if not frappe.db.get_value("User", approver, "enabled"):
		tracker.add_failure_attempt()
		raise NotAuthorized("Approver is not an active user.")
	if not has_any_role(roles, user=approver):
		tracker.add_failure_attempt()
		raise NotAuthorized("Approver does not hold a supervisor role.")
	try:
		check_password(approver, approver_password, delete_tracker_cache=False)
	except frappe.AuthenticationError:
		tracker.add_failure_attempt()
		raise NotAuthorized("Supervisor approval failed.")
	tracker.add_success_attempt()


APPROVAL_MAX_FAILURES = 5
APPROVAL_LOCK_SECONDS = 15 * 60


def approval_tracker(approver: str):
	from frappe.auth import LoginAttemptTracker

	# is_user_allowed() allows while failures <= max, so max - 1 yields a lock on the Nth failure.
	return LoginAttemptTracker(
		f"serk_approval:{approver}",
		max_consecutive_login_attempts=APPROVAL_MAX_FAILURES - 1,
		lock_interval=APPROVAL_LOCK_SECONDS,
	)
