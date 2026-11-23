"""Spec 050 - nobody but Administrator renames shifts or sales, and an owner's Desk return joins the only open shift.

frappe is stubbed (tests.frappe_stub); the override and the guard run with their frappe module replaced.
"""

import importlib
import unittest
from unittest import mock

from pos_next.tests import frappe_stub
from pos_next.tests.test_invoice_row_guard import _doc_events
from pos_next.tests.test_sale_shift_guard import FakeInvoice, Row, S, _fake_frappe

override = None


def setUpModule():
	global override
	frappe_stub.install()
	override = importlib.import_module("pos_next.overrides.sales_invoice")


def tearDownModule():
	frappe_stub.uninstall()


class RenameCase(unittest.TestCase):
	def setUp(self):
		self.guard = importlib.import_module("pos_next.api.rename_guard")
		self.actor = "owner@example.com"
		self.frappe = _fake_frappe()
		for patch in (
			mock.patch.object(self.guard, "frappe", self.frappe),
			mock.patch.object(self.guard, "_", new=lambda text: text),
			mock.patch.object(self.guard, "_actor", side_effect=lambda: self.actor),
		):
			patch.start()
			self.addCleanup(patch.stop)

	def test_rename_blocked_for_everyone_but_administrator(self):
		for doctype in self.guard.RENAME_LOCKED_DOCTYPES:
			with self.subTest(doctype=doctype):
				with self.assertRaisesRegex(RuntimeError, f"^{doctype} X-1 cannot be renamed$"):
					self.guard.block_rename(Row(doctype=doctype, name="X-1"))
				self.assertEqual(self.frappe.throw.call_args.args[1], self.frappe.PermissionError)

	def test_administrator_can_rename(self):
		self.actor = "Administrator"
		for doctype in self.guard.RENAME_LOCKED_DOCTYPES:
			with self.subTest(doctype=doctype):
				self.guard.block_rename(Row(doctype=doctype, name="X-1"))
		self.frappe.throw.assert_not_called()

	def test_hooks_send_every_rename_to_the_guard(self):
		self.assertEqual(_doc_events()["*"]["before_rename"], "pos_next.api.rename_guard.block_rename")
		expected = {"POS Opening Shift", "POS Closing Shift", "Sales Invoice"}
		expected |= set(self.guard.INVOICE_ROW_DOCTYPES) | set(self.guard.SHIFT_ROW_DOCTYPES)
		self.assertEqual(set(self.guard.RENAME_LOCKED_DOCTYPES), expected)
		self.assertEqual(len(self.guard.RENAME_LOCKED_DOCTYPES), 11)

	def test_other_doctypes_rename_as_today(self):
		for doctype in ("Customer", "User", "Item"):
			with self.subTest(doctype=doctype):
				self.guard.block_rename(Row(doctype=doctype, name="X-1"))
		self.frappe.throw.assert_not_called()


class ReturnCase(unittest.TestCase):
	def setUp(self):
		self.frappe = _fake_frappe()
		self.frappe.session.user = "o"
		self.frappe.get_roles.return_value = ["Dueño"]
		for patch in (
			mock.patch.object(override, "frappe", self.frappe),
			mock.patch.object(override, "cint", side_effect=lambda value: int(value or 0)),
		):
			patch.start()
			self.addCleanup(patch.stop)

	def _doc(self, **changes):
		doc = Row(is_return=1, pos_profile="P1", company="C1", posa_pos_opening_shift=None, flags=Row())
		doc.update(changes)
		return doc

	def test_owner_return_links_the_only_open_shift(self):
		self.frappe.get_list.return_value = ["OS-9"]
		doc = self._doc()
		self.assertTrue(override.link_owner_return(doc))
		self.assertEqual(doc.posa_pos_opening_shift, "OS-9")
		filters = {"pos_profile": "P1", "company": "C1", "docstatus": 1, "status": "Open"}
		self.frappe.get_list.assert_called_once_with(
			"POS Opening Shift", filters=filters, pluck="name", order_by="name asc", limit_page_length=2
		)

	def test_owner_return_needs_exactly_one_open_shift(self):
		cases = (
			([], "No open POS Opening Shift on POS Profile P1"),
			(["OS-1", "OS-2"], "More than one open POS Opening Shift on POS Profile P1"),
		)
		for found, message in cases:
			with self.subTest(found=found):
				self.frappe.get_list.return_value = found
				doc = self._doc()
				with self.assertRaisesRegex(RuntimeError, f"^{message}"):
					override.link_owner_return(doc)
				self.assertIsNone(doc.posa_pos_opening_shift)

	def test_only_an_owner_desk_return_links(self):
		cases = (
			("cashier", {}, ["Cajero"]),
			("system manager", {}, ["Dueño", "System Manager"]),
			("sale, not return", {"is_return": 0}, ["Dueño"]),
			("pos api", {"flags": Row(pos_next_api=True)}, ["Dueño"]),
			("closing shift", {"flags": Row(from_closing_shift=True)}, ["Dueño"]),
			("no profile", {"pos_profile": ""}, ["Dueño"]),
		)
		for label, changes, roles in cases:
			with self.subTest(label):
				self.frappe.get_roles.return_value = roles
				self.assertFalse(override.link_owner_return(self._doc(**changes)))
		self.frappe.get_list.assert_not_called()
		self.frappe.db.get_value.assert_not_called()

	def test_owner_keeps_his_own_shift(self):
		self.frappe.db.get_value.return_value = "o"
		doc = self._doc(posa_pos_opening_shift="OS-1")
		self.assertFalse(override.link_owner_return(doc))
		self.frappe.db.get_value.assert_called_once_with("POS Opening Shift", "OS-1", "user")
		self.frappe.get_list.assert_not_called()

	def test_owner_return_moves_off_a_cashier_shift(self):
		self.frappe.db.get_value.return_value = "a"
		self.frappe.get_list.return_value = ["OS-2"]
		doc = self._doc(posa_pos_opening_shift="OS-1")
		self.assertTrue(override.link_owner_return(doc))
		self.assertEqual(doc.posa_pos_opening_shift, "OS-2")

	def test_a_linked_owner_return_may_use_the_cashier_shift(self):
		self.frappe.db.get_value.return_value = S
		self.frappe.has_permission.return_value = True
		enforce = override.CustomSalesInvoice.enforce_pos_shift
		with mock.patch.object(override, "link_owner_return", return_value=True):
			enforce(FakeInvoice(shift="S1"))
		with mock.patch.object(override, "link_owner_return", return_value=False):
			with self.assertRaisesRegex(RuntimeError, "belongs to another user"):
				enforce(FakeInvoice(shift="S1"))
