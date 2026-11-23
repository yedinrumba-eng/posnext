"""Spec 052a - the POS cleanup deletes only drafts the POS API saved; Desk drafts survive.

frappe is stubbed (tests.frappe_stub); the override, the cleanup and the close run over fakes.
"""

import ast
import importlib
import json
import pathlib
import unittest
from unittest import mock

from pos_next.tests import frappe_stub
from pos_next.tests.test_sale_shift_guard import Row, _fake_frappe

override = None
invoices = None
closing = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIELD = "Sales Invoice-posa_saved_by_pos_api"


def setUpModule():
	global override, invoices, closing
	frappe_stub.install()
	override = importlib.import_module("pos_next.overrides.sales_invoice")
	invoices = importlib.import_module("pos_next.api.invoices")
	closing = importlib.import_module("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift")


def tearDownModule():
	frappe_stub.uninstall()


class MarkCase(unittest.TestCase):
	def test_mark_follows_the_pos_api_flag(self):
		for flags, before, after in (
			(Row(pos_next_api=True), 0, 1),
			(Row(), 1, 0),
			(Row(from_closing_shift=True), 1, 0),
		):
			with self.subTest(flags=flags):
				doc = Row(flags=flags, posa_saved_by_pos_api=before)
				override.mark_pos_api_save(doc)
				self.assertEqual(doc.posa_saved_by_pos_api, after)

	def test_validate_marks_before_anything_else(self):
		tree = ast.parse((ROOT / "overrides" / "sales_invoice.py").read_text(encoding="utf-8"))
		cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CustomSalesInvoice")
		validate = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "validate")
		first = validate.body[0]
		self.assertIsInstance(first, ast.Expr)
		self.assertIsInstance(first.value, ast.Call)
		self.assertEqual(first.value.func.id, "mark_pos_api_save")
		self.assertEqual([arg.id for arg in first.value.args], ["self"])


class CleanupCase(unittest.TestCase):
	def setUp(self):
		self.fake = _fake_frappe()
		self.fake.session.user = "o"
		for patcher in (
			mock.patch.object(invoices, "frappe", self.fake),
			mock.patch.object(invoices, "cint", lambda v: int(v or 0)),
			mock.patch("pos_next.api.partial_payments._has_pos_profile_access", return_value=True),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_cleanup_asks_only_for_pos_drafts(self):
		self.fake.get_all.return_value = []
		invoices.cleanup_old_drafts(pos_profile="P1", max_age_hours=1)
		self.fake.get_all.assert_called_once_with(
			"Sales Invoice",
			filters={
				"docstatus": 0,
				"modified": ["<", mock.ANY],
				"owner": "o",
				"pos_profile": "P1",
				"posa_saved_by_pos_api": 1,
			},
			fields=["name", "modified"],
			limit_page_length=100,
		)

	def test_cleanup_keeps_its_delete_call(self):
		self.fake.get_all.return_value = [{"name": "SI-1", "modified": "x"}]
		result = invoices.cleanup_old_drafts(pos_profile="P1", max_age_hours=1)
		self.assertEqual(result["deleted"], 1)
		self.fake.delete_doc.assert_called_once_with("Sales Invoice", "SI-1", force=True, ignore_permissions=True)


class CloseCase(unittest.TestCase):
	def setUp(self):
		self.fake = _fake_frappe()
		patcher = mock.patch.object(closing, "frappe", self.fake)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.shift = Row(pos_profile="P1", pos_opening_shift="OS-1")

	def test_close_deletes_only_pos_drafts(self):
		self.fake.get_value.return_value = 1
		self.fake.db.sql.return_value = [Row(name="SI-1")]
		closing.POSClosingShift.delete_draft_invoices(self.shift)
		self.fake.get_value.assert_called_once_with("POS Profile", "P1", "posa_allow_delete")
		query, params = self.fake.db.sql.call_args.args[:2]
		self.assertIn("posa_is_printed = 0", query)
		self.assertIn("posa_saved_by_pos_api = 1", query)
		self.assertEqual(params, "OS-1")
		self.fake.delete_doc.assert_called_once_with("Sales Invoice", "SI-1", force=1)

	def test_close_without_allow_delete_deletes_nothing(self):
		self.fake.get_value.return_value = 0
		closing.POSClosingShift.delete_draft_invoices(self.shift)
		self.fake.db.sql.assert_not_called()
		self.fake.delete_doc.assert_not_called()


class FixtureCase(unittest.TestCase):
	def test_the_mark_ships_as_a_fixture(self):
		fields = json.loads((ROOT / "fixtures" / "custom_field.json").read_text(encoding="utf-8"))
		entry = next(f for f in fields if f.get("name") == FIELD)
		expected = {
			"dt": "Sales Invoice",
			"fieldname": "posa_saved_by_pos_api",
			"fieldtype": "Check",
			"default": "0",
			"hidden": 1,
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"insert_after": "posa_is_printed",
			"module": "POS Next",
		}
		self.assertEqual({k: entry.get(k) for k in expected}, expected)
		hooks = ast.parse((ROOT / "hooks.py").read_text(encoding="utf-8"))
		for node in hooks.body:
			if isinstance(node, ast.Assign) and any(
				isinstance(t, ast.Name) and t.id == "fixtures" for t in node.targets
			):
				first = ast.literal_eval(node.value)[0]
				break
		else:
			raise AssertionError("fixtures not found in hooks.py")
		names = next(f for f in first["filters"] if f[0] == "name" and f[1] == "in")[2]
		self.assertIn(FIELD, names)
