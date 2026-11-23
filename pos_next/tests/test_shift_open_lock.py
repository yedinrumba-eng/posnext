"""Spec 049 - opening a shift takes a lock, is only for oneself, and a reopen leaves one open shift.

frappe is stubbed (tests.frappe_stub); the DocType methods run over fake documents.
"""

import importlib
import unittest
from unittest import mock

from pos_next.tests import frappe_stub
from pos_next.tests.test_opening_shift_guard import FakeShift, Row

opening = None
closing = None


def setUpModule():
	global opening, closing
	frappe_stub.install()
	opening = importlib.import_module("pos_next.pos_next.doctype.pos_opening_shift.pos_opening_shift")
	closing = importlib.import_module("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift")


def tearDownModule():
	frappe_stub.uninstall()


def _throw(message, *args, **kwargs):
	raise RuntimeError(message)


def _patch_opening(case):
	fake_frappe = mock.MagicMock()
	fake_frappe.throw.side_effect = _throw
	fake_frappe.session.user = "u1"
	for patch in (
		mock.patch.object(opening, "frappe", new=fake_frappe),
		mock.patch.object(opening, "_", new=lambda text: text),
		mock.patch.object(opening, "cint", new=int),
	):
		patch.start()
		case.addCleanup(patch.stop)
	return fake_frappe


class OpeningOwnerCase(unittest.TestCase):
	def setUp(self):
		self.fake_frappe = _patch_opening(self)

	def test_cashier_opens_only_for_herself(self):
		self.assertIsNone(opening.shift_owner_violation("u1", "u1", {"Cajero"}))
		self.assertEqual(
			opening.shift_owner_violation("u2", "u1", {"Cajero"}),
			"You can open a POS Opening Shift only for yourself",
		)

	def test_owner_and_system_manager_open_for_others(self):
		self.assertIsNone(opening.shift_owner_violation("u2", "o", {"Dueño"}))
		self.assertIsNone(opening.shift_owner_violation("u2", "o", {"System Manager"}))

	def test_profile_check_rejects_a_shift_for_another_user(self):
		fake = FakeShift()
		values = {"POS Profile": "C1", "User": 1}
		self.fake_frappe.db.get_value.side_effect = lambda doctype, *args, **kwargs: values[doctype]
		self.fake_frappe.has_permission.return_value = True
		self.fake_frappe.session.user = "u2"
		self.fake_frappe.get_roles.return_value = ["Cajero"]
		with self.assertRaisesRegex(RuntimeError, "only for yourself"):
			opening.POSOpeningShift.validate_pos_profile_and_cashier(fake)
		self.assertIs(self.fake_frappe.throw.call_args.args[1], self.fake_frappe.PermissionError)

	def test_open_shifts_lock_the_user_first(self):
		calls = mock.MagicMock()
		self.fake_frappe.db.get_value = calls.user
		self.fake_frappe.db.get_values = calls.shifts
		calls.shifts.return_value = ["OS-2"]
		self.assertEqual(opening.open_shifts_of("u1", "OS-1"), ["OS-2"])
		self.assertEqual(
			calls.mock_calls,
			[
				mock.call.user("User", "u1", "name", for_update=True),
				mock.call.shifts(
					"POS Opening Shift",
					{"user": "u1", "docstatus": 1, "status": "Open", "name": ["!=", "OS-1"]},
					"name",
					for_update=True,
					pluck=True,
				),
			],
		)

	def test_no_open_shift_is_an_empty_list(self):
		self.fake_frappe.db.get_values.return_value = None
		self.assertEqual(opening.open_shifts_of("u1"), [])
		filters = self.fake_frappe.db.get_values.call_args.args[1]
		self.assertEqual(filters["name"], ["!=", ""])


class ClosingCancelCase(unittest.TestCase):
	def setUp(self):
		self.fake_frappe = mock.MagicMock()
		self.fake_frappe.throw.side_effect = _throw
		self.fake_frappe.db.exists.return_value = True
		self.shift = mock.MagicMock()
		self.shift.user = "u1"
		self.shift.name = "OS-1"
		self.shift.pos_closing_shift = "CS-1"
		self.shift.flags = Row()
		self.fake_frappe.get_doc.return_value = self.shift
		patch = mock.patch.object(closing, "frappe", new=self.fake_frappe)
		patch.start()
		self.addCleanup(patch.stop)
		patch = mock.patch.object(closing, "_", new=lambda text: text)
		patch.start()
		self.addCleanup(patch.stop)
		patch = mock.patch.object(closing, "open_shifts_of", create=True)
		self.open_shifts = patch.start()
		self.addCleanup(patch.stop)
		self.fake = mock.MagicMock()
		self.fake.name = "CS-1"

	def test_cancel_refuses_to_reopen_next_to_another_open_shift(self):
		self.open_shifts.return_value = ["OS-2"]
		message = "User u1 already has an open POS Opening Shift OS-2. Close it before cancelling this closing"
		with self.assertRaisesRegex(RuntimeError, message):
			closing.POSClosingShift.on_cancel(self.fake)
		self.shift.save.assert_not_called()
		self.fake._clear_closing_entry_invoices.assert_not_called()

	def test_cancel_reopens_when_the_user_has_no_other_shift(self):
		self.open_shifts.return_value = []
		closing.POSClosingShift.on_cancel(self.fake)
		self.shift.save.assert_called_once_with()
		self.open_shifts.assert_called_once_with("u1", "OS-1")

	def test_cancel_of_an_old_closing_skips_the_check(self):
		self.shift.pos_closing_shift = "CS-9"
		closing.POSClosingShift.on_cancel(self.fake)
		self.open_shifts.assert_not_called()
		self.shift.save.assert_not_called()


if __name__ == "__main__":
	unittest.main()
