# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Mutation check: prove the idempotency tests can fail.

Replaces run_idempotent with a no-op passthrough and runs the retry + concurrency tests.
They MUST fail; if they pass, the tests are not protecting anything.
Run: bench --site serktest.localhost execute serk_retail.tests.mutation_check.run
"""

import unittest

import frappe


def run():
	from serk_retail.api import pos
	from serk_retail.tests import test_m1_flow

	original = pos.run_idempotent
	pos.run_idempotent = lambda operation, scope, key, payload, fn: {**fn(), "idempotent_replay": False}
	frappe.flags.in_test = True
	try:
		suite = unittest.TestSuite()
		for name in ("test_02_retry_with_same_key_returns_same_sale",
					 "test_04_concurrent_duplicate_requests_create_one_sale"):
			suite.addTest(test_m1_flow.TestM1RetailFlow(name))
		result = unittest.TextTestRunner(verbosity=0).run(suite)
	finally:
		pos.run_idempotent = original
	killed = len(result.failures) + len(result.errors)
	print(f"MUTANT {'KILLED' if killed == 2 else 'SURVIVED'}: {killed}/2 tests failed with idempotency disabled")
	return killed
