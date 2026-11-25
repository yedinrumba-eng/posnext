"""Spec 054 - SQL functions in query fields use dict syntax (Frappe v16 rejects strings).

frappe is stubbed (tests.frappe_stub); the two query functions run over fakes, and two ast sweeps
guard the whole package against SQL functions written as strings in fields or filter keys.
"""

import ast
import importlib
import re
import types
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

from pos_next.tests import frappe_stub

items = None
invoices = None

ns = types.SimpleNamespace
FUNC_RE = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*\(", re.ASCII)
QUERY_CALLS = {"get_all", "get_list", "get_value", "get_values", "get_single_value", "get_cached_value"}
POSITIONAL_FIELD_CALLS = {"get_value", "get_values", "get_cached_value"}
FIELD_KEYWORDS = {"fields", "fieldname", "pluck"}
ROOT = Path(__file__).resolve().parents[1]
SUM_FIELDS = [{"SUM": "actual_qty", "as": "actual_qty"}]


def setUpModule():
	global items, invoices
	frappe_stub.install()
	items = importlib.import_module("pos_next.api.items")
	invoices = importlib.import_module("pos_next.api.invoices")


def tearDownModule():
	frappe_stub.uninstall()


def _package_files():
	for path in sorted(ROOT.rglob("*.py")):
		if "tests" not in path.relative_to(ROOT).parts:
			yield path, ast.parse(path.read_text(encoding="utf-8"))


def _call_name(node):
	func = node.func
	return getattr(func, "attr", None) or getattr(func, "id", None)


def _strings(nodes):
	for node in nodes:
		for sub in ast.walk(node):
			if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
				yield sub


class StockAvailabilityCase(unittest.TestCase):
	def setUp(self):
		self.frappe = MagicMock()
		for name, value in (("frappe", self.frappe), ("flt", lambda v: float(v or 0))):
			patcher = mock.patch.object(items, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_stock_leaf_warehouse_uses_dict_sum(self):
		self.frappe.db.get_value.return_value = 0
		self.frappe.get_all.return_value = [ns(actual_qty=7.5)]
		self.assertEqual(items.get_stock_availability("I1", "W1"), 7.5)
		self.frappe.get_all.assert_called_once_with(
			"Bin",
			fields=SUM_FIELDS,
			filters={"item_code": "I1", "warehouse": ["in", ["W1"]]},
		)

	def test_stock_group_warehouse_uses_descendants(self):
		self.frappe.db.get_value.return_value = 1
		self.frappe.db.get_descendants.return_value = ["W2", "W3"]
		self.frappe.get_all.return_value = [ns(actual_qty=None)]
		self.assertEqual(items.get_stock_availability("I1", "G1"), 0.0)
		kwargs = self.frappe.get_all.call_args.kwargs
		self.assertEqual(kwargs["filters"]["warehouse"], ["in", ["W2", "W3"]])
		self.assertEqual(kwargs["fields"], SUM_FIELDS)

	def test_stock_empty_and_no_warehouse(self):
		self.frappe.db.get_value.return_value = 0
		self.frappe.get_all.return_value = []
		empty = items.get_stock_availability("I1", "W1")
		self.frappe.get_all.reset_mock()
		missing = items.get_stock_availability("I1", None)
		self.assertEqual((empty, missing), (0.0, 0.0))
		self.assertIsInstance(empty, float)
		self.assertIsInstance(missing, float)
		self.frappe.get_all.assert_not_called()


class ReturnSearchCase(unittest.TestCase):
	def test_return_search_counts_with_dict(self):
		fake = MagicMock()
		fake.get_list.side_effect = [[ns(total_count=0)], []]
		with mock.patch.object(invoices, "frappe", fake, create=True):
			result = invoices.search_invoices_for_return(invoice_name="X")
		self.assertEqual(result, {"invoices": [], "has_more": False})
		self.assertEqual(fake.get_list.call_args_list[0].kwargs["fields"], [{"COUNT": "name", "as": "total_count"}])


class SweepCase(unittest.TestCase):
	def test_no_sql_function_strings_in_query_fields(self):
		hits = []
		for path, tree in _package_files():
			for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
				name = _call_name(call)
				if name not in QUERY_CALLS:
					continue
				nodes = [kw.value for kw in call.keywords if kw.arg in FIELD_KEYWORDS]
				if name in POSITIONAL_FIELD_CALLS and len(call.args) > 2:
					nodes.append(call.args[2])
				for const in _strings(nodes):
					if FUNC_RE.match(const.value):
						hits.append(f"{path.relative_to(ROOT.parent)}:{const.lineno}: {const.value}")
		self.assertEqual(hits, [], "SQL function strings in query fields:\n" + "\n".join(hits))

	def test_no_sql_function_filter_keys(self):
		hits = []
		for path, tree in _package_files():
			for node in ast.walk(tree):
				keys = []
				if isinstance(node, ast.Dict):
					keys = [k for k in node.keys if k is not None]
				elif isinstance(node, ast.Subscript):
					keys = [node.slice]
				for key in keys:
					if isinstance(key, ast.Constant) and isinstance(key.value, str) and FUNC_RE.match(key.value):
						hits.append(f"{path.relative_to(ROOT.parent)}:{key.lineno}: {key.value}")
		self.assertEqual(hits, [], "SQL function filter keys:\n" + "\n".join(hits))
