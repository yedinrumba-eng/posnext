"""S10.3 - the Sales Invoice row guard (D31.49) and the update-after-submit guard (D31.55), no bench.

frappe is stubbed; _actor and _is_override are patched, frappe.throw raises RuntimeError.
"""

import ast
import importlib
import pathlib
import unittest
from unittest import mock

from pos_next.tests import frappe_stub
from pos_next.tests.test_price_guard import Row

module = None


def setUpModule():
	global module
	frappe_stub.install()
	module = importlib.import_module("pos_next.api.invoice_row_guard")


def tearDownModule():
	frappe_stub.uninstall()


def _throw(message, *args, **kwargs):
	raise RuntimeError(message)


KNOWN_DOCTYPES = (
	"Sales Invoice",
	"POS Opening Shift",
	"POS Closing Shift",
	"POS Closing Entry",
	"Sales Taxes and Charges Template",
)


def _fake_get_meta(parenttype):
	for name in KNOWN_DOCTYPES:
		if name.casefold() == parenttype.rstrip().casefold():
			meta = mock.Mock()
			meta.name = name
			return meta
	raise module.frappe.DoesNotExistError(parenttype)


def _doc_events():
	path = pathlib.Path(__file__).resolve().parents[1] / "hooks.py"
	for node in ast.parse(path.read_text(encoding="utf-8")).body:
		if isinstance(node, ast.Assign) and any(
			isinstance(target, ast.Name) and target.id == "doc_events" for target in node.targets
		):
			return ast.literal_eval(node.value)
	raise AssertionError("doc_events not found in hooks.py")


class GuardCase(unittest.TestCase):
	def setUp(self):
		self.actor = "cashier@example.com"
		self.override = False
		patches = [
			mock.patch.object(module, "_actor", side_effect=lambda: self.actor),
			mock.patch.object(module, "_is_override", side_effect=lambda: self.override),
			mock.patch.object(module, "_", new=lambda text: text),
			mock.patch.object(module.frappe, "get_meta", side_effect=_fake_get_meta),
		]
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)
		throw_patch = mock.patch.object(module.frappe, "throw", side_effect=_throw)
		self.throw = throw_patch.start()
		self.addCleanup(throw_patch.stop)


class TestInvoiceRowGuard(GuardCase):
	def test_1_a_cashier_cannot_save_a_loose_invoice_row(self):
		for doctype in module.INVOICE_ROW_DOCTYPES:
			with self.subTest(doctype=doctype):
				row = Row(doctype=doctype, parenttype="Sales Invoice", parent="SINV-1")
				with self.assertRaises(RuntimeError) as ctx:
					module.block_standalone_invoice_row(row)
				self.assertIn(
					"Rows of Sales Invoice SINV-1 are saved only with the invoice", str(ctx.exception)
				)
				self.assertEqual(module.frappe.PermissionError, self.throw.call_args.args[1])

	def test_2_administrator_and_other_parents_pass(self):
		self.actor = "Administrator"
		row = Row(doctype="Sales Invoice Payment", parenttype="Sales Invoice", parent="SINV-1")
		self.throw.reset_mock()
		module.block_standalone_invoice_row(row)
		self.throw.assert_not_called()

		self.actor = "cashier@example.com"
		other = Row(
			doctype="Sales Taxes and Charges",
			parenttype="Sales Taxes and Charges Template",
			parent="NY Tax",
		)
		module.block_standalone_invoice_row(other)
		self.throw.assert_not_called()

	def test_5_odd_parenttype_spelling_is_rejected(self):
		for parenttype in ("sales invoice", "Sales Invoice ", "SALES invoice"):
			with self.subTest(parenttype=parenttype):
				row = Row(doctype="Sales Invoice Payment", parenttype=parenttype, parent="SINV-1")
				with self.assertRaisesRegex(RuntimeError, "Rows of Sales Invoice SINV-1"):
					module.block_standalone_invoice_row(row)

	def test_6_unknown_or_empty_parenttype_passes(self):
		module.block_standalone_invoice_row(
			Row(doctype="Sales Invoice Payment", parenttype="No Such DocType", parent="X-1")
		)
		self.throw.assert_not_called()
		module.frappe.get_meta.reset_mock()
		module.block_standalone_invoice_row(Row(doctype="Sales Invoice Payment", parenttype=None, parent="X-1"))
		self.throw.assert_not_called()
		module.frappe.get_meta.assert_not_called()

	def test_7_shift_guard_resolves_parenttype(self):
		guard = importlib.import_module("pos_next.api.shift_row_guard")
		for patch in (
			mock.patch.object(guard, "_", new=lambda text: text),
			mock.patch.object(guard, "_actor", new=lambda: self.actor),
		):
			patch.start()
			self.addCleanup(patch.stop)
		cases = (
			("pos closing shift", "Rows of POS Closing Shift CS-1"),
			("POS Closing Shift ", "Rows of POS Closing Shift CS-1"),
			("Pos Opening SHIFT", "Rows of POS Opening Shift"),
		)
		for parenttype, message in cases:
			with self.subTest(parenttype=parenttype):
				row = Row(doctype="POS Closing Shift Detail", parenttype=parenttype, parent="CS-1")
				with self.assertRaisesRegex(RuntimeError, message):
					guard.block_standalone_shift_row(row)

	def test_3_a_submitted_invoice_changes_only_with_override(self):
		doc = Row(doctype="Sales Invoice", name="SINV-1")
		with self.assertRaises(RuntimeError) as ctx:
			module.block_update_after_submit(doc)
		self.assertIn(
			"Submitted Sales Invoice SINV-1 can only be changed by the Dueño or a System Manager",
			str(ctx.exception),
		)
		self.assertEqual(module.frappe.PermissionError, self.throw.call_args.args[1])

		self.throw.reset_mock()
		self.override = True
		module.block_update_after_submit(doc)
		self.throw.assert_not_called()

		self.override = False
		module.block_update_after_submit(Row(doctype="Sales Order", name="SO-1"))
		self.throw.assert_not_called()

	def test_4_hooks_point_at_the_guards(self):
		events = _doc_events()
		invoice = events["Sales Invoice"]
		self.assertEqual("pos_next.api.price_guard.enforce_pos_prices", invoice["before_validate"])
		self.assertEqual(
			"pos_next.api.invoice_row_guard.block_update_after_submit",
			invoice["before_update_after_submit"],
		)
		for doctype in module.INVOICE_ROW_DOCTYPES:
			with self.subTest(doctype=doctype):
				self.assertEqual(
					{
						"before_insert",
						"before_validate",
						"before_update_after_submit",
						"before_submit",
						"before_cancel",
						"on_trash",
					},
					set(events[doctype]),
				)
				for event, path in events[doctype].items():
					self.assertEqual(
						"pos_next.api.invoice_row_guard.block_standalone_invoice_row", path, event
					)


if __name__ == "__main__":
	unittest.main()
