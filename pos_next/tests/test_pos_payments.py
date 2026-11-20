"""Spec 029 - the payments the cashier requested survive set_missing_values(), tested without a bench.

frappe is stubbed (tests.frappe_stub); frappe.throw is patched to raise, so the tests exercise
requested_payments / restore_requested_payments against a fixed POS Profile template.
"""

import ast
import importlib
import pathlib
import unittest
from unittest import mock

from pos_next.tests import frappe_stub

module = None


def setUpModule():
	global module
	frappe_stub.install()
	module = importlib.import_module("pos_next.api.pos_payments")


def tearDownModule():
	frappe_stub.uninstall()


def _flt(value, precision=None):
	number = float(value or 0)
	return round(number, precision) if precision is not None else number


def _throw(message, *args, **kwargs):
	raise RuntimeError(message)


class Row(dict):
	"""Child-row stand-in: attribute access like a Frappe row, .get like a dict."""

	def __getattr__(self, name):
		return self.get(name)

	def __setattr__(self, name, value):
		self[name] = value


def _template():
	return [
		Row(mode_of_payment="Cash", account="Cash - C1", type="Cash", default=1, amount=0),
		Row(mode_of_payment="Credit Card", account="Card - C1", type="Bank", default=0, amount=0),
	]


class FakeDoc:
	def __init__(self):
		self.pos_profile = "P1"
		self.payments = _template()

	def get(self, name, default=None):
		return getattr(self, name, default)

	def set(self, name, value):
		setattr(self, name, list(value))

	def append(self, table, values):
		row = Row(values)
		getattr(self, table).append(row)
		return row


class TestPosPayments(unittest.TestCase):
	def setUp(self):
		patches = [
			mock.patch.object(module, "_", new=lambda text: text),
			mock.patch.object(module, "flt", side_effect=_flt),
		]
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)
		throw_patch = mock.patch.object(module.frappe, "throw", side_effect=_throw)
		self.throw = throw_patch.start()
		self.addCleanup(throw_patch.stop)

	def test_requested_payments_keeps_mode_and_amount(self):
		rows = [
			Row(mode_of_payment="Cash", amount=5, type="Cash", account="X", default=1),
			Row(mode_of_payment="", amount=9),
			Row(mode_of_payment="Credit Card", amount=None),
			Row(mode_of_payment="Cash", amount=7.5),
		]
		result = module.requested_payments(rows)
		self.assertEqual(
			[
				{"mode_of_payment": "Cash", "amount": 5.0},
				{"mode_of_payment": "Credit Card", "amount": 0.0},
				{"mode_of_payment": "Cash", "amount": 7.5},
			],
			result,
		)
		for item in result:
			self.assertEqual({"mode_of_payment", "amount"}, set(item))
		self.assertEqual([], module.requested_payments(None))

	def test_restore_sets_requested_amount(self):
		doc = FakeDoc()
		module.restore_requested_payments(doc, [{"mode_of_payment": "Cash", "amount": 10.60}])
		self.assertEqual(1, len(doc.payments))
		row = doc.payments[0]
		self.assertEqual(
			("Cash", 10.60, "Cash - C1", "Cash", 1),
			(row.mode_of_payment, row.amount, row.account, row.type, row.default),
		)

	def test_restore_ignores_client_type_and_account(self):
		doc = FakeDoc()
		client = [Row(mode_of_payment="Credit Card", amount=20, type="Cash", account="Evil")]
		module.restore_requested_payments(doc, module.requested_payments(client))
		self.assertEqual(1, len(doc.payments))
		row = doc.payments[0]
		self.assertEqual(("Credit Card", 20.0), (row.mode_of_payment, row.amount))
		self.assertEqual("Bank", row.type)
		self.assertEqual("Card - C1", row.account)

	def test_restore_keeps_duplicates_and_negatives(self):
		doc = FakeDoc()
		requested = [
			{"mode_of_payment": "Cash", "amount": -5.0},
			{"mode_of_payment": "Cash", "amount": 15.60},
		]
		module.restore_requested_payments(doc, requested)
		self.assertEqual(
			[("Cash", -5.0), ("Cash", 15.60)],
			[(row.mode_of_payment, row.amount) for row in doc.payments],
		)

	def test_restore_rejects_mode_outside_profile(self):
		doc = FakeDoc()
		with self.assertRaises(RuntimeError) as ctx:
			module.restore_requested_payments(doc, [{"mode_of_payment": "Wire Transfer", "amount": 10.60}])
		self.assertIn("Mode of payment Wire Transfer is not set up in POS Profile P1", str(ctx.exception))
		self.assertEqual(_template(), doc.payments)

	def test_restore_without_request_keeps_profile_rows(self):
		doc = FakeDoc()
		module.restore_requested_payments(doc, [])
		self.assertEqual(_template(), doc.payments)

	def test_update_invoice_call_order(self):
		path = pathlib.Path(__file__).resolve().parents[1] / "api" / "invoices.py"
		tree = ast.parse(path.read_text(encoding="utf-8"))
		func = next(
			node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "update_invoice"
		)
		calls = {}
		for node in ast.walk(func):
			if not isinstance(node, ast.Call):
				continue
			target = node.func
			name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
			calls.setdefault(name, []).append(node)
		missing = calls.get("set_missing_values", [])
		self.assertEqual(1, len(missing))
		self.assertEqual([], missing[0].args)
		self.assertEqual([], missing[0].keywords)
		restore = calls["restore_requested_payments"][0].lineno
		totals = min(node.lineno for node in calls["calculate_taxes_and_totals"])
		self.assertLess(missing[0].lineno, restore)
		self.assertLess(restore, totals)


if __name__ == "__main__":
	unittest.main()
