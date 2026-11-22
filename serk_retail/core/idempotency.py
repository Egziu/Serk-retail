# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Scoped, server-side idempotency.

Contract (see docs/architecture/ADR-004-idempotency.md):
* record name = sha256("<operation>|<scope>|<key>") — the primary key is the dedupe guard.
* request_hash = sha256(canonical JSON of the business payload).
* The record is inserted in the SAME transaction as the business effect. Either both commit or
  neither does, so a crash mid-request leaves no half state.
* A concurrent duplicate blocks on the InnoDB primary-key lock until the first transaction
  ends; it then either sees the committed record (returns the stored response) or, if the first
  rolled back, proceeds itself.
* Same key + different payload -> IdempotencyConflict. Never "last write wins".
"""

import hashlib
import json
from collections.abc import Callable

import frappe

from serk_retail.core.errors import IdempotencyConflict, IdempotencyInProgress, InvalidRequest

DOCTYPE = "SERK Idempotency Record"
MAX_KEY_LEN = 128


def canonical_hash(payload) -> str:
	return hashlib.sha256(
		json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
	).hexdigest()


def record_name(operation: str, scope: str, key: str) -> str:
	return hashlib.sha256(f"{operation}|{scope}|{key}".encode()).hexdigest()


def _validate_key(key) -> str:
	if not isinstance(key, str) or not key.strip():
		raise InvalidRequest("idempotency_key is required")
	key = key.strip()
	if len(key) > MAX_KEY_LEN:
		raise InvalidRequest(f"idempotency_key longer than {MAX_KEY_LEN} characters")
	return key


def _replay(existing, request_hash):
	if existing.request_hash != request_hash:
		raise IdempotencyConflict(
			"This idempotency key was already used for a different request. "
			"Do not retry; start a new transaction with a new key."
		)
	if existing.status != "Completed":
		raise IdempotencyInProgress("The original request is still in progress. Retry shortly.")
	result = json.loads(existing.response or "{}")
	result["idempotent_replay"] = True
	return result


def run_idempotent(operation: str, scope: str, key: str, payload, fn: Callable[[], dict]) -> dict:
	key = _validate_key(key)
	request_hash = canonical_hash(payload)
	name = record_name(operation, scope, key)

	# Locking read: sees the latest committed version, not our REPEATABLE READ snapshot.
	existing = frappe.db.get_value(
		DOCTYPE, name, ["request_hash", "status", "response"], as_dict=True, for_update=True
	)
	if existing:
		return _replay(existing, request_hash)

	rec = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"name": name,
			"operation": operation,
			"scope": scope,
			"idempotency_key": key,
			"request_hash": request_hash,
			"status": "Pending",
			"user": frappe.session.user,
		}
	)
	rec.flags.ignore_permissions = True
	try:
		rec.db_insert()
	except frappe.DuplicateEntryError:
		# A concurrent request with the same key committed first while we waited on the lock.
		frappe.clear_messages()  # drop Frappe's generic "already exists" toast
		existing = frappe.db.get_value(
			DOCTYPE, name, ["request_hash", "status", "response"], as_dict=True, for_update=True
		)
		if not existing:
			raise IdempotencyInProgress("Concurrent request in progress. Retry shortly.")
		return _replay(existing, request_hash)

	result = fn()

	frappe.db.set_value(
		DOCTYPE,
		name,
		{
			"status": "Completed",
			"response": json.dumps(result, default=str, sort_keys=True),
			"reference_doctype": result.get("reference_doctype"),
			"reference_name": result.get("reference_name"),
		},
		update_modified=True,
	)
	result["idempotent_replay"] = False
	return result
