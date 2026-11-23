"""Spec 047 - the shift row is locked by the sale and by the close; the close counts POS sales only.

frappe is stubbed (tests.frappe_stub); the override and the closing doctype run over fakes.
"""

import importlib
import unittest
from unittest import mock
from unittest.mock import MagicMock, call

from pos_next.tests import frappe_stub
from pos_next.tests.test_sale_shift_guard import FakeInvoice, Row, _fake_frappe

override = None
closing = None

S = {"name": "S1", "user": "a", "status": "Open", "docstatus": 1, "pos_profile": "P1", "company": "C1"}
F = {"docstatus": 1, "is_pos": 1, "posa_pos_opening_shift": "OS-1", "company": "C1", "pos_profile": "P1"}
FIELDS = ["name", "user", "status", "docstatus", "pos_profile", "company"]


def setUpModule():
	global override, closing
	frappe_stub.install()
	override = importlib.import_module("pos_next.overrides.sales_invoice")
	closing = importlib.import_module("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift")


def tearDownModule():
	frappe_stub.uninstall()


def _patch(case, module):
	fake = _fake_frappe()
	for name, value in (("frappe", fake), ("cint", lambda v: int(v or 0)), ("_", lambda text: text)):
		patcher = mock.patch.object(module, name, value, create=True)
		patcher.start()
		case.addCleanup(patcher.stop)
	return fake


def _closing_fake(**extra):
	fake = Row(name="CS-1", pos_opening_shift="OS-1", user="a", company="C1", pos_profile="P1")
	fake.pos_transactions = [Row(sales_invoice="SINV-1")]
	fake.update(extra)
	return fake


class SaleLockCase(unittest.TestCase):
	def setUp(self):
		self.frappe = _patch(self, override)
		self.frappe.session.user = "a"
		self.frappe.get_roles.return_value = ["Cajero"]

	def test_sale_locks_its_shift(self):
		self.frappe.db.get_value.return_value = S
		override.CustomSalesInvoice.enforce_pos_shift(FakeInvoice(shift="S1"))
		self.frappe.db.get_value.assert_called_once_with(
			"POS Opening Shift", "S1", FIELDS, as_dict=True, for_update=True
		)

	def test_offline_lookup_does_not_lock(self):
		self.frappe.db.get_value.return_value = S
		self.assertEqual(override.resolve_offline_shift("S1", "P1"), "S1")
		self.frappe.db.get_value.assert_called_once_with(
			"POS Opening Shift", "S1", FIELDS, as_dict=True, for_update=False
		)

	def test_non_pos_invoice_cannot_carry_a_shift(self):
		with self.assertRaisesRegex(RuntimeError, "Only POS sales and returns carry a POS Opening Shift"):
			override.CustomSalesInvoice.enforce_pos_shift(FakeInvoice(is_pos=0, shift="S1"))
		self.frappe.db.get_value.assert_not_called()


class CloseLockCase(unittest.TestCase):
	def setUp(self):
		self.frappe = _patch(self, closing)

	def _validate(self, status):
		m = MagicMock()
		m.lock.return_value = status
		self.frappe.db.get_value = m.lock
		self.frappe.get_all.return_value = []
		fake = _closing_fake(_apply_server_totals=m.totals, update_payment_reconciliation=m.update)
		closing.POSClosingShift.validate(fake)
		return m

	def test_validate_locks_the_shift_first(self):
		m = self._validate("Open")
		self.assertEqual(
			m.mock_calls[:2], [call.lock("POS Opening Shift", "OS-1", "status", for_update=True), call.totals()]
		)
		self.assertEqual(m.lock.call_count, 1)

	def test_validate_still_rejects_a_closed_shift(self):
		with self.assertRaisesRegex(RuntimeError, "Selected POS Opening Shift should be open."):
			self._validate("Closed")

	def test_recount_passes_when_nothing_changed(self):
		self.frappe.db.get_values.return_value = ["SINV-1"]
		closing.POSClosingShift._recount_invoices(_closing_fake())
		self.frappe.db.get_values.assert_called_once_with("Sales Invoice", F, "name", for_update=True, pluck=True)

	def test_recount_rejects_a_sale_that_arrived(self):
		self.frappe.db.get_values.return_value = ["SINV-1", "SINV-2"]
		with self.assertRaisesRegex(RuntimeError, "reached this shift while it was closing"):
			closing.POSClosingShift._recount_invoices(_closing_fake())

	def test_on_submit_recounts_after_closing_the_shift(self):
		order = []
		opening = MagicMock()
		opening.save.side_effect = lambda: order.append("save")
		self.frappe.get_doc.return_value = opening
		fake = _closing_fake(
			_recount_invoices=lambda: order.append("recount"),
			_set_closing_entry_invoices=lambda: order.append("links"),
			delete_draft_invoices=lambda: None,
		)
		closing.POSClosingShift.on_submit(fake)
		self.assertEqual(order, ["save", "recount", "links"])


class CountCase(unittest.TestCase):
	def setUp(self):
		self.frappe = _patch(self, closing)
		patcher = mock.patch.object(closing, "submit_printed_invoices")
		self.submit = patcher.start()
		self.addCleanup(patcher.stop)

	def test_close_counts_only_pos_sales_of_the_shift(self):
		self.frappe.db.get_value.return_value = Row(company="C1", pos_profile="P1")
		self.frappe.get_all.return_value = ["SINV-1"]
		self.frappe.get_doc.return_value.as_dict.return_value = {"name": "SINV-1"}
		self.assertEqual(closing.get_pos_invoices("OS-1"), [{"name": "SINV-1"}])
		self.frappe.db.get_value.assert_called_once_with(
			"POS Opening Shift", "OS-1", ["company", "pos_profile"], as_dict=True
		)
		self.submit.assert_called_once_with("OS-1", "Sales Invoice")
		self.frappe.get_all.assert_called_once_with(
			"Sales Invoice", filters=F, pluck="name", order_by="creation asc"
		)
		self.frappe.db.sql.assert_not_called()

	def test_close_reads_only_sales_invoices(self):
		with self.assertRaisesRegex(RuntimeError, "Only Sales Invoice is supported"):
			closing.get_pos_invoices("OS-1", "POS Invoice")
		self.frappe.get_all.assert_not_called()

	def test_missing_shift_counts_nothing(self):
		self.frappe.db.get_value.return_value = None
		self.assertEqual(closing.get_pos_invoices("OS-1"), [])
		self.submit.assert_not_called()
		self.frappe.get_all.assert_not_called()


if __name__ == "__main__":
	unittest.main()
