# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Typed errors so clients can show the next safe action instead of 'something went wrong'."""

import frappe


class SERKError(frappe.ValidationError):
	code = "SERK_ERROR"


class IdempotencyConflict(SERKError):
	"""Same idempotency key reused with a different payload. Never retried automatically."""

	code = "IDEMPOTENCY_CONFLICT"


class IdempotencyInProgress(SERKError):
	code = "IDEMPOTENCY_IN_PROGRESS"


class InvalidRequest(SERKError):
	code = "INVALID_REQUEST"


class InsufficientPayment(SERKError):
	code = "INSUFFICIENT_PAYMENT"


class RefundExceedsEntitlement(SERKError):
	code = "REFUND_EXCEEDS_ENTITLEMENT"


class ShiftStateError(SERKError):
	code = "SHIFT_STATE"


class NotAuthorized(frappe.PermissionError):
	code = "NOT_AUTHORIZED"
