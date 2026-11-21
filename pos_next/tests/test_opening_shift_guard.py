"""Spec 040 - the shift status changes only through its close, and openings come clean.

frappe is stubbed (tests.frappe_stub). The pure rules run for real; the DocType methods run over
fake documents with ``frappe`` patched in the module under test.
"""

import importlib
import unittest
from unittest import mock

from pos_next.tests import frappe_stub

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


class Row(dict):
	"""Child-row stand-in: attribute access like a Frappe row, .get like a dict."""

	def __getattr__(self, name):
		return self.get(name)

	def __setattr__(self, name, value):
		self[name] = value


class FakeShift:
	"""What the POS Opening Shift hooks read on the document."""

	def __init__(self, rows=None):
		self.flags = {}
		self.balance_details = rows or []
		self.company = "C1"
		self.pos_profile = "P1"
		self.user = "u1"
		self.pos_closing_shift = ""
		self.docstatus = 0
		self.name = "OS-1"
		self.is_new = mock.MagicMock(return_value=False)
		self.validate_pos_profile_and_cashier = mock.MagicMock()
		self.set_status = mock.MagicMock()

	def get(self, name, default=None):
		return getattr(self, name, default)


def _snapshot(values):
	snapshot = mock.MagicMock()
	snapshot.as_dict.return_value = values
	return snapshot


def _patch_opening(case):
	fake_frappe = mock.MagicMock()
	fake_frappe.throw.side_effect = _throw
	for patch in (
		mock.patch.object(opening, "frappe", new=fake_frappe),
		mock.patch.object(opening, "_", new=lambda text: text),
		mock.patch.object(opening, "cint", new=int),
	):
		patch.start()
		case.addCleanup(patch.stop)
	return fake_frappe


class LockedFieldsCase(unittest.TestCase):
	def setUp(self):
		self.fake_frappe = _patch_opening(self)

	def _fake(self, flags, before, after):
		fake = FakeShift()
		fake.flags = flags
		fake.as_dict = lambda: after
		fake.get_doc_before_save = lambda: before
		return fake

	def test_locked_fields_detect_changes(self):
		before = {"status": "Open", "pos_closing_shift": None}
		after = {"status": "Closed", "pos_closing_shift": "x"}
		self.assertEqual(opening.changed_locked_fields(before, after), ["status", "pos_closing_shift"])

	def test_locked_fields_ignore_empty_and_other_fields(self):
		before = {"status": "Open", "pos_closing_shift": None, "company": "A"}
		after = {"status": "Open", "pos_closing_shift": "", "company": "B"}
		self.assertEqual(opening.changed_locked_fields(before, after), [])

	def test_zero_link_counts_as_change(self):
		for zero in (0, 0.0):
			changed = opening.changed_locked_fields({"pos_closing_shift": None}, {"pos_closing_shift": zero})
			self.assertEqual(changed, ["pos_closing_shift"])

	def test_false_link_counts_as_change(self):
		changed = opening.changed_locked_fields({"pos_closing_shift": None}, {"pos_closing_shift": False})
		self.assertEqual(changed, ["pos_closing_shift"])

	def test_text_zero_link_counts_as_change(self):
		changed = opening.changed_locked_fields({"pos_closing_shift": None}, {"pos_closing_shift": "0"})
		self.assertEqual(changed, ["pos_closing_shift"])

	def test_hand_change_after_submit_is_rejected(self):
		before = _snapshot({"status": "Open", "pos_closing_shift": ""})
		fake = self._fake({}, before, {"status": "Closed", "pos_closing_shift": "x"})
		with self.assertRaisesRegex(RuntimeError, "change only through a POS Closing Shift"):
			opening.POSOpeningShift.before_update_after_submit(fake)

	def test_closing_flag_allows_the_change(self):
		before = _snapshot({"status": "Open", "pos_closing_shift": ""})
		fake = self._fake({"from_closing_shift": True}, before, {"status": "Closed", "pos_closing_shift": "x"})
		opening.POSOpeningShift.before_update_after_submit(fake)

	def test_missing_snapshot_fails_closed(self):
		fake = self._fake({}, None, {"status": "Open", "pos_closing_shift": ""})
		with self.assertRaisesRegex(RuntimeError, "change only through a POS Closing Shift"):
			opening.POSOpeningShift.before_update_after_submit(fake)


	def test_missing_snapshot_fails_closed_without_changes(self):
		fake = self._fake({}, None, {})
		with self.assertRaisesRegex(RuntimeError, "change only through a POS Closing Shift"):
			opening.POSOpeningShift.before_update_after_submit(fake)


class OpeningCleanCase(unittest.TestCase):
	def setUp(self):
		self.fake_frappe = _patch_opening(self)

	def test_duplicate_modes_lists_each_once(self):
		names = ["Cash", "Card", "Cash", "Cash", "", None, None]
		rows = [Row(mode_of_payment=name) for name in names]
		self.assertEqual(opening.duplicate_modes(rows), ["Cash"])
		self.assertEqual(opening.duplicate_modes(rows[:2]), [])

	def test_validate_rejects_repeated_mode(self):
		twice = FakeShift(
			[Row(mode_of_payment="Cash", opening_amount=50), Row(mode_of_payment="Cash", opening_amount=10)]
		)
		with self.assertRaisesRegex(RuntimeError, "Mode of payment Cash is listed twice in the opening balance"):
			opening.POSOpeningShift.validate(twice)
		twice.set_status.assert_not_called()
		clean = FakeShift(
			[Row(mode_of_payment="Cash", opening_amount=50), Row(mode_of_payment="Card", opening_amount=0)]
		)
		opening.POSOpeningShift.validate(clean)
		clean.set_status.assert_called_once_with()

	def test_validate_always_drops_client_closing_link(self):
		fresh = FakeShift()
		fresh.pos_closing_shift = "x"
		fresh.is_new.return_value = True
		opening.POSOpeningShift.validate(fresh)
		self.assertEqual(fresh.pos_closing_shift, "")
		saved = FakeShift()
		saved.pos_closing_shift = "x"
		opening.POSOpeningShift.validate(saved)
		self.assertEqual(saved.pos_closing_shift, "")

	def test_submit_rejects_a_second_open_shift(self):
		fake = FakeShift()
		fake.docstatus = 1
		fake.name = "OS-2"
		self.fake_frappe.db.exists.return_value = True
		with self.assertRaisesRegex(RuntimeError, "already has an open POS Opening Shift"):
			opening.POSOpeningShift.validate(fake)
		self.fake_frappe.db.exists.assert_called_once_with(
			"POS Opening Shift", {"user": "u1", "docstatus": 1, "status": "Open", "name": ["!=", "OS-2"]}
		)
		fake.set_status.assert_not_called()

	def test_draft_save_skips_the_open_shift_check(self):
		fake = FakeShift()
		opening.POSOpeningShift.validate(fake)
		self.fake_frappe.db.exists.assert_not_called()

	def test_submit_without_another_open_shift_passes(self):
		fake = FakeShift()
		fake.docstatus = 1
		self.fake_frappe.db.exists.return_value = False
		opening.POSOpeningShift.validate(fake)
		fake.set_status.assert_called_once_with()

	def test_put_submit_with_falsy_link_opens_clean(self):
		fake = FakeShift()
		fake.docstatus = 1
		fake.pos_closing_shift = 0
		fake.status = ""
		fake.is_new.return_value = False
		self.fake_frappe.db.exists.return_value = False
		fake.set_status = lambda: opening.POSOpeningShift.set_status(fake)
		opening.POSOpeningShift.validate(fake)
		self.assertEqual(fake.pos_closing_shift, "")
		self.assertEqual(fake.status, "Open")

	def test_shift_user_must_read_the_profile(self):
		fake = FakeShift()
		values = {"POS Profile": "C1", "User": 1}
		self.fake_frappe.db.get_value.side_effect = lambda doctype, *args, **kwargs: values[doctype]
		self.fake_frappe.has_permission.return_value = False
		with self.assertRaisesRegex(RuntimeError, "User u1 cannot use POS Profile P1"):
			opening.POSOpeningShift.validate_pos_profile_and_cashier(fake)
		self.fake_frappe.has_permission.assert_called_once_with("POS Profile", "read", doc="P1", user="u1")
		self.fake_frappe.has_permission.return_value = True
		opening.POSOpeningShift.validate_pos_profile_and_cashier(fake)


class ClosingFlagsCase(unittest.TestCase):
	def setUp(self):
		self.fake_frappe = mock.MagicMock()
		self.fake_frappe.throw.side_effect = _throw
		patch = mock.patch.object(closing, "frappe", new=self.fake_frappe)
		patch.start()
		self.addCleanup(patch.stop)
		self.flags_at_save = []
		self.shift = mock.MagicMock()
		self.shift.flags = Row()
		self.shift.save.side_effect = lambda: self.flags_at_save.append(self.shift.flags.from_closing_shift)
		self.fake_frappe.get_doc.return_value = self.shift
		self.fake = mock.MagicMock()
		self.fake.name = "CS-1"

	def test_closing_submit_flags_the_shift(self):
		closing.POSClosingShift.on_submit(self.fake)
		self.assertEqual(self.flags_at_save, [True])
		self.assertEqual(self.shift.pos_closing_shift, "CS-1")

	def test_closing_cancel_flags_the_shift(self):
		self.fake_frappe.db.exists.return_value = True
		self.shift.pos_closing_shift = self.fake.name
		closing.POSClosingShift.on_cancel(self.fake)
		self.assertEqual(self.flags_at_save, [True])
		self.assertEqual(self.shift.pos_closing_shift, "")


class ShiftRowGuardCase(unittest.TestCase):
	def setUp(self):
		self.guard = importlib.import_module("pos_next.api.shift_row_guard")
		self.actor = "cashier@example.com"
		fake_frappe = mock.MagicMock()
		fake_frappe.throw.side_effect = _throw
		for patch in (
			mock.patch.object(self.guard, "frappe", new=fake_frappe),
			mock.patch.object(self.guard, "_", new=lambda text: text),
			mock.patch.object(self.guard, "_actor", new=lambda: self.actor),
			mock.patch.object(self.guard, "canonical_parenttype", create=True, new=lambda doc: doc.get("parenttype") or ""),
		):
			patch.start()
			self.addCleanup(patch.stop)

	def test_loose_opening_row_is_rejected(self):
		row = Row(doctype="POS Opening Shift Detail", parenttype="POS Opening Shift", parent="OS-1")
		with self.assertRaisesRegex(RuntimeError, "Rows of POS Opening Shift OS-1 are saved only with the shift"):
			self.guard.block_standalone_shift_row(row)

	def test_loose_closing_rows_are_rejected(self):
		for doctype in self.guard.SHIFT_ROW_DOCTYPES[1:]:
			with self.subTest(doctype=doctype):
				row = Row(doctype=doctype, parenttype="POS Closing Shift", parent="CS-1")
				with self.assertRaisesRegex(RuntimeError, "Rows of POS Closing Shift CS-1"):
					self.guard.block_standalone_shift_row(row)

	def test_administrator_and_other_parents_pass(self):
		self.actor = "Administrator"
		self.guard.block_standalone_shift_row(
			Row(doctype="POS Opening Shift Detail", parenttype="POS Opening Shift", parent="OS-1")
		)
		self.actor = "cashier@example.com"
		self.guard.block_standalone_shift_row(
			Row(doctype="Sales Invoice Reference", parenttype="POS Closing Entry", parent="PCE-1")
		)

	def test_hooks_point_at_the_shift_row_guard(self):
		from pos_next.tests.test_invoice_row_guard import _doc_events

		events = _doc_events()
		for doctype in self.guard.SHIFT_ROW_DOCTYPES:
			with self.subTest(doctype=doctype):
				self.assertEqual(
					{"before_insert", "before_validate", "before_update_after_submit", "before_submit", "before_cancel", "on_trash"},
					set(events[doctype]),
				)
				for path in events[doctype].values():
					self.assertEqual("pos_next.api.shift_row_guard.block_standalone_shift_row", path)


if __name__ == "__main__":
	unittest.main()
