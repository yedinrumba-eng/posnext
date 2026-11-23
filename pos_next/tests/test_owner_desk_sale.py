"""Spec 052 - an owner's Desk POS sale joins the only open shift of its POS Profile.

frappe is stubbed (tests.frappe_stub); the override runs with its frappe module replaced.
"""

import importlib
import unittest
from unittest import mock

from pos_next.tests import frappe_stub
from pos_next.tests.test_sale_shift_guard import FakeInvoice, Row, S, _fake_frappe

override = None
FIELDS = ["user", "status", "docstatus"]


def setUpModule():
	global override
	frappe_stub.install()
	override = importlib.import_module("pos_next.overrides.sales_invoice")


def tearDownModule():
	frappe_stub.uninstall()


class OwnerSaleCase(unittest.TestCase):
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
		doc = Row(is_return=0, is_pos=1, pos_profile="P1", company="C1", posa_pos_opening_shift=None, flags=Row())
		doc.update(changes)
		return doc

	def test_owner_desk_sale_links_the_only_open_shift(self):
		self.frappe.get_list.return_value = ["OS-9"]
		doc = self._doc()
		self.assertTrue(override.link_owner_desk_shift(doc))
		self.assertEqual(doc.posa_pos_opening_shift, "OS-9")
		filters = {"pos_profile": "P1", "company": "C1", "docstatus": 1, "status": "Open"}
		self.frappe.get_list.assert_called_once_with(
			"POS Opening Shift", filters=filters, pluck="name", order_by="name asc", limit_page_length=2
		)
		self.frappe.db.get_value.assert_not_called()

	def test_owner_desk_sale_needs_exactly_one_open_shift(self):
		cases = (
			([], r"^No open POS Opening Shift on POS Profile P1\. Open the register shift before this sale or return$"),
			(
				["OS-1", "OS-2"],
				r"^More than one open POS Opening Shift on POS Profile P1\. Close the extra shifts before this sale or return$",
			),
		)
		for found, message in cases:
			with self.subTest(found=found):
				self.frappe.get_list.return_value = found
				doc = self._doc()
				with self.assertRaisesRegex(RuntimeError, message):
					override.link_owner_desk_shift(doc)
				self.assertIsNone(doc.posa_pos_opening_shift)

	def test_only_an_owner_desk_sale_links(self):
		cases = (
			("cashier", {}, ["Cajero"]),
			("system manager", {}, ["Dueño", "System Manager"]),
			("pos api", {"flags": Row(pos_next_api=True)}, ["Dueño"]),
			("closing shift", {"flags": Row(from_closing_shift=True)}, ["Dueño"]),
			("no profile", {"pos_profile": ""}, ["Dueño"]),
		)
		for label, changes, roles in cases:
			with self.subTest(label):
				self.frappe.get_roles.return_value = roles
				self.assertFalse(override.link_owner_desk_shift(self._doc(**changes)))
		self.frappe.get_list.assert_not_called()
		self.frappe.db.get_value.assert_not_called()

	def test_owner_keeps_his_own_open_shift(self):
		self.frappe.db.get_value.return_value = Row(user="o", status="Open", docstatus=1)
		doc = self._doc(posa_pos_opening_shift="OS-1")
		self.assertFalse(override.link_owner_desk_shift(doc))
		self.assertEqual(doc.posa_pos_opening_shift, "OS-1")
		self.frappe.db.get_value.assert_called_once_with("POS Opening Shift", "OS-1", FIELDS, as_dict=True)
		self.frappe.get_list.assert_not_called()

	def test_owner_leaves_a_shift_that_is_no_longer_open(self):
		cases = (
			Row(user="o", status="Closed", docstatus=1),
			Row(user="o", status="Draft", docstatus=0),
			Row(user="o", status="Cancelled", docstatus=2),
			None,
		)
		for row in cases:
			with self.subTest(row=row):
				self.frappe.db.get_value.return_value = row
				self.frappe.get_list.return_value = ["OS-2"]
				doc = self._doc(posa_pos_opening_shift="OS-1")
				self.assertTrue(override.link_owner_desk_shift(doc))
				self.assertEqual(doc.posa_pos_opening_shift, "OS-2")

	def test_enforce_links_an_owner_desk_sale(self):
		self.frappe.db.get_value.return_value = S
		self.frappe.has_permission.return_value = True
		enforce = override.CustomSalesInvoice.enforce_pos_shift
		inv = FakeInvoice(shift="S1")
		inv.is_return = 0
		with mock.patch.object(override, "link_owner_desk_shift", return_value=True) as link:
			enforce(inv)
		link.assert_called_once_with(inv)

	def test_non_pos_invoice_never_links(self):
		enforce = override.CustomSalesInvoice.enforce_pos_shift
		with mock.patch.object(override, "link_owner_desk_shift", return_value=True) as link:
			enforce(FakeInvoice(is_pos=0))
		link.assert_not_called()
