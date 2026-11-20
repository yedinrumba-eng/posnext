"""Spec 041 - every POS sale carries an open shift of the user who rings it, no bench needed.

frappe is stubbed (tests.frappe_stub). The pure rules run for real; the override and the closing
helper run over fakes with their frappe module replaced.
"""

import importlib
import unittest
from unittest import mock

from pos_next.tests import frappe_stub

override = None
closing = None

S = {"name": "S1", "user": "a", "status": "Open", "docstatus": 1, "pos_profile": "P1", "company": "C1"}


def setUpModule():
	global override, closing
	frappe_stub.install()
	override = importlib.import_module("pos_next.overrides.sales_invoice")
	closing = importlib.import_module("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift")
	override.cint = int


def tearDownModule():
	frappe_stub.uninstall()


def _throw(message, *args, **kwargs):
	raise RuntimeError(message)


class Row(dict):
	"""Child-row stand-in: attribute access like a Frappe row, .get like a dict."""

	def __getattr__(self, name):
		return self.get(name)

	def __setattr__(self, name, value):
		self[name] = value


def _fake_frappe():
	fake = mock.MagicMock()
	fake.throw.side_effect = _throw
	fake._ = lambda text: text
	return fake


def _violation(shift, user="a", roles=("Cajero",), profile="P1", company="C1", in_close=False, can_read=False):
	return override.sale_shift_violation(shift, user, set(roles), profile, company, in_close, can_read)


class ShiftViolationCase(unittest.TestCase):
	def test_own_open_shift_passes(self):
		self.assertIsNone(override.sale_shift_violation(S, "a", {"Cajero"}, "P1", "C1", False, False))

	def test_missing_shift_is_rejected(self):
		for roles in ({"Cajero"}, {"Dueño"}):
			self.assertEqual(
				override.sale_shift_violation(None, "a", roles, "P1", "C1", False, False),
				"POS sales and returns need an open POS Opening Shift",
			)

	def test_closed_or_draft_shift_is_rejected(self):
		for change in ({"status": "Closed"}, {"docstatus": 0}):
			message = _violation(dict(S, **change))
			self.assertEqual(message, "POS Opening Shift S1 is not open. Open a shift and try again")

	def test_other_profile_or_company_is_rejected(self):
		for args in ({"profile": "P2"}, {"company": "C2"}):
			self.assertEqual(
				_violation(S, **args), "POS Opening Shift S1 belongs to another POS Profile or Company"
			)

	def test_other_users_shift_is_rejected(self):
		expected = "POS Opening Shift S1 belongs to another user"
		self.assertEqual(_violation(S, user="b"), expected)
		self.assertEqual(_violation(S, user="o", roles=("Dueño",), can_read=True, in_close=False), expected)

	def test_owner_submits_during_close_only(self):
		expected = "POS Opening Shift S1 belongs to another user"
		self.assertIsNone(_violation(S, user="o", roles=("Dueño",), in_close=True, can_read=True))
		self.assertEqual(_violation(S, user="o", roles=("Dueño",), in_close=True, can_read=False), expected)
		self.assertEqual(_violation(S, user="b", roles=("Cajero",), in_close=True, can_read=True), expected)

	def test_system_manager_is_exempt(self):
		self.assertIsNone(_violation(None, user="admin", roles=("System Manager",)))
		closed_of_other = dict(S, status="Closed", user="b")
		self.assertIsNone(_violation(closed_of_other, user="admin", roles=("System Manager",)))

	def test_offline_sale_moves_to_open_shift(self):
		closed = dict(S, status="Closed")
		self.assertEqual(override.offline_sale_shift("S1", closed, "a", "P1", "S2"), "S2")
		self.assertEqual(override.offline_sale_shift("S1", closed, "a", "P1", None), "S1")
		self.assertEqual(override.offline_sale_shift("S1", dict(closed, user="b"), "a", "P1", "S2"), "S1")
		self.assertEqual(override.offline_sale_shift("S1", S, "a", "P1", "S2"), "S1")
		self.assertEqual(override.offline_sale_shift("S1", closed, "a", "P2", "S2"), "S1")
		self.assertEqual(override.offline_sale_shift("X", None, "a", "P1", "S2"), "X")


class FakeInvoice:
	"""Every attribute enforce_pos_shift reads."""

	def __init__(self, is_pos=1, shift=None, flags=None):
		self.is_pos = is_pos
		self.is_return = 1
		self.pos_profile = "P1"
		self.company = "C1"
		self.flags = flags or {}
		self._shift = shift

	def get(self, name, default=None):
		return self._shift if name == "posa_pos_opening_shift" else default


class EnforceCase(unittest.TestCase):
	def setUp(self):
		self.frappe = _fake_frappe()
		self.frappe.session.user = "a"
		self.frappe.get_roles.return_value = ["Cajero"]
		for patch in (
			mock.patch.object(override, "frappe", self.frappe),
			mock.patch.object(override, "cint", side_effect=lambda value: int(value or 0)),
		):
			patch.start()
			self.addCleanup(patch.stop)

	def test_rule_runs_only_for_pos(self):
		self.frappe.db.get_value.return_value = None
		with self.assertRaisesRegex(RuntimeError, "need an open POS Opening Shift"):
			override.CustomSalesInvoice.enforce_pos_shift(FakeInvoice(is_pos=1))
		self.frappe.db.get_value.reset_mock()
		override.CustomSalesInvoice.enforce_pos_shift(FakeInvoice(is_pos=0))
		self.frappe.db.get_value.assert_not_called()

	def test_close_flag_reaches_the_rule(self):
		self.frappe.session.user = "o"
		self.frappe.get_roles.return_value = ["Dueño"]
		self.frappe.db.get_value.return_value = S
		self.frappe.has_permission.return_value = True
		fake = FakeInvoice(shift="S1", flags={"from_closing_shift": True})
		override.CustomSalesInvoice.enforce_pos_shift(fake)
		self.frappe.has_permission.assert_called_once_with("POS Opening Shift", "read", doc="S1")


class PrintedDraftsCase(unittest.TestCase):
	def test_printed_drafts_submit_with_close_flag(self):
		seen = []
		invoice = mock.MagicMock()
		invoice.flags = Row()
		invoice.submit.side_effect = lambda: seen.append(invoice.flags.from_closing_shift)
		fake_frappe = mock.MagicMock()
		fake_frappe.get_all.return_value = [Row(name="SINV-1")]
		fake_frappe.get_doc.return_value = invoice
		with mock.patch.object(closing, "frappe", fake_frappe):
			closing.submit_printed_invoices("S1", "Sales Invoice")
		self.assertEqual(seen, [True])


if __name__ == "__main__":
	unittest.main()
