"""S10.12 - the endpoints that move money with ignore_permissions must check the POS flags first.

The first three tests read the source with ``ast``; the last one runs both cancel paths with
frappe stubbed (tests.frappe_stub). No bench.
"""

import ast
import importlib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from pos_next.tests import frappe_stub

API = Path(__file__).resolve().parent.parent / "api"

# (file, function) -> the flags D31.19 requires; one of them has to be on for the POS Profile.
EXPECTED = {
	("credit_sales.py", "redeem_customer_credit"): ("allow_credit_sale",),
	("credit_sales.py", "cancel_credit_journal_entries"): ("allow_credit_sale",),
	("partial_payments.py", "add_payment_to_partial_invoice"): ("allow_partial_payment", "allow_credit_sale"),
}

# The functions that load something after the guard; the cancel entry just delegates (D31.40).
LOAD_CHECKED = {
	("credit_sales.py", "redeem_customer_credit"),
	("partial_payments.py", "add_payment_to_partial_invoice"),
}

LOADERS = {"frappe.get_doc", "frappe.get_all"}


def setUpModule():
	frappe_stub.install()


def tearDownModule():
	frappe_stub.uninstall()


def _function(file_name, function_name):
	tree = ast.parse((API / file_name).read_text(encoding="utf-8"))
	return next(
		node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == function_name
	)


def _calls(file_name, function_name):
	"""(require_pos_flag calls, line numbers of the first-load calls) of one function."""
	guards = []
	loads = []
	for node in ast.walk(_function(file_name, function_name)):
		if isinstance(node, ast.Call):
			called = ast.unparse(node.func)
			if called == "require_pos_flag":
				guards.append(node)
			elif called in LOADERS:
				loads.append(node.lineno)
	return guards, loads


class TestMoneyFlags(unittest.TestCase):
	def test_guard_is_called_once_before_anything_is_loaded(self):
		for file_name, function_name in LOAD_CHECKED:
			guards, loads = _calls(file_name, function_name)
			self.assertEqual(1, len(guards), f"{function_name}: expected one require_pos_flag call")
			self.assertTrue(loads, f"{function_name}: no frappe.get_doc/get_all to compare against")
			self.assertLess(guards[0].lineno, min(loads), function_name)

	def test_guard_gets_the_flags_of_the_spec(self):
		for (file_name, function_name), flags in EXPECTED.items():
			guards, _loads = _calls(file_name, function_name)
			self.assertEqual(flags, ast.literal_eval(guards[0].args[1]), function_name)

	def test_cancel_entry_is_gate_then_internal(self):
		public = _function("credit_sales.py", "cancel_credit_journal_entries")
		body = public.body
		if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
			body = body[1:]
		self.assertEqual(2, len(body))
		self.assertIsInstance(body[0], ast.Expr)
		self.assertEqual("require_pos_flag", ast.unparse(body[0].value.func))
		self.assertIsInstance(body[1], ast.Return)
		self.assertEqual("_cancel_credit_journal_entries", ast.unparse(body[1].value.func))

		internal = _function("credit_sales.py", "_cancel_credit_journal_entries")
		self.assertEqual([], internal.decorator_list)
		self.assertEqual([], _calls("credit_sales.py", "_cancel_credit_journal_entries")[0])

		hook = _function("sales_invoice_hooks.py", "before_cancel")
		called = {ast.unparse(node.func) for node in ast.walk(hook) if isinstance(node, ast.Call)}
		self.assertIn("_cancel_credit_journal_entries", called)
		self.assertNotIn("cancel_credit_journal_entries", called)

	def test_both_cancel_paths_behave(self):
		credit_sales = importlib.import_module("pos_next.api.credit_sales")
		hooks = importlib.import_module("pos_next.api.sales_invoice_hooks")
		with (
			mock.patch.object(credit_sales, "require_pos_flag", side_effect=RuntimeError("gate")) as gate,
			mock.patch.object(credit_sales, "_cancel_credit_journal_entries", return_value=2) as internal,
		):
			hooks.before_cancel(SimpleNamespace(name="SINV-9"))
			internal.assert_called_once_with("SINV-9")
			gate.assert_not_called()

			with self.assertRaises(RuntimeError):
				credit_sales.cancel_credit_journal_entries("SINV-9")
			self.assertEqual(1, internal.call_count)

			gate.side_effect = None
			gate.return_value = None
			self.assertEqual(2, credit_sales.cancel_credit_journal_entries("SINV-9"))
			self.assertEqual(2, internal.call_count)


if __name__ == "__main__":
	unittest.main()
