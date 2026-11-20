"""Spec 038 - the server computes the shift close and only takes what the cashier counted.

frappe is stubbed (tests.frappe_stub). The pure rules run for real; _apply_server_totals runs over a
fake document with the server-side builder patched.
"""

import importlib
import unittest
from unittest import mock

from pos_next.tests import frappe_stub

closing = None


def setUpModule():
	global closing
	frappe_stub.install()
	closing = importlib.import_module("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift")


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


class FakeClosing:
	"""What _apply_server_totals reads and writes on a POS Closing Shift."""

	def __init__(self):
		self.pos_opening_shift = "OS-1"
		self.user = "b"
		self.company = "OTHER"
		self.pos_profile = "OTHER"
		self.grand_total = 0
		self.payment_reconciliation = [Row(mode_of_payment="Cash", expected_amount=40, closing_amount=40)]

	def get(self, name, default=None):
		return getattr(self, name, default)

	def set(self, name, value):
		setattr(self, name, value)


class CanCloseCase(unittest.TestCase):
	def test_cashier_closes_own_shift(self):
		self.assertTrue(closing.can_close_shift("a", "a", {"Cajero"}, False))

	def test_other_cashier_cannot_close(self):
		self.assertFalse(closing.can_close_shift("b", "a", {"Cajero"}, True))

	def test_owner_with_read_closes_cashier_shift(self):
		self.assertTrue(closing.can_close_shift("o", "a", {"Dueño"}, True))
		self.assertTrue(closing.can_close_shift("o", "a", {"System Manager"}, True))

	def test_owner_of_other_company_cannot_close(self):
		self.assertFalse(closing.can_close_shift("o", "a", {"Dueño"}, False))


class CountedAmountsCase(unittest.TestCase):
	def setUp(self):
		fake_frappe = mock.MagicMock()
		fake_frappe.throw.side_effect = _throw
		for patch in (
			mock.patch.object(closing, "flt", new=_flt),
			mock.patch.object(closing, "_", new=lambda text: text),
			mock.patch.object(closing, "frappe", new=fake_frappe),
		):
			patch.start()
			self.addCleanup(patch.stop)

	def test_counted_amounts_keeps_modes(self):
		rows = [Row(mode_of_payment="Cash", closing_amount=40), Row(mode_of_payment="Card", closing_amount=5.60)]
		self.assertEqual(closing.counted_amounts(rows, ["Cash", "Card"]), {"Cash": 40.0, "Card": 5.6})
		self.assertEqual(closing.counted_amounts([], ["Cash", "Card"]), {})

	def test_counted_amounts_allows_zero(self):
		rows = [Row(mode_of_payment="Cash", closing_amount=0)]
		self.assertEqual(closing.counted_amounts(rows, ["Cash"]), {"Cash": 0.0})

	def test_counted_amounts_rejects_unknown_mode(self):
		rows = [Row(mode_of_payment="Wire", closing_amount=1)]
		with self.assertRaisesRegex(RuntimeError, "Mode of payment Wire is not part of this shift"):
			closing.counted_amounts(rows, ["Cash"])

	def test_counted_amounts_rejects_bad_numbers(self):
		for bad in (float("nan"), float("inf"), -1):
			rows = [Row(mode_of_payment="Cash", closing_amount=bad)]
			with self.assertRaisesRegex(
				RuntimeError, "Counted amount for Cash must be a finite number of zero or more"
			):
				closing.counted_amounts(rows, ["Cash"])
		twice = [Row(mode_of_payment="Cash", closing_amount=1), Row(mode_of_payment="Cash", closing_amount=2)]
		with self.assertRaisesRegex(RuntimeError, "Mode of payment Cash is counted twice"):
			closing.counted_amounts(twice, ["Cash"])


class ServerTotalsCase(unittest.TestCase):
	def _apply(self, built) -> FakeClosing:
		opening = mock.MagicMock()
		opening.user = "a"
		opening.as_dict.return_value = {}
		fake_frappe = mock.MagicMock()
		fake_frappe.get_doc.return_value = opening
		fake_frappe.session.user = "a"
		fake_frappe.get_roles.return_value = ["Cajero"]
		fake_frappe.has_permission.return_value = False
		fake_frappe.throw.side_effect = _throw
		fake = FakeClosing()
		with (
			mock.patch.object(closing, "frappe", new=fake_frappe),
			mock.patch.object(closing, "flt", new=_flt),
			mock.patch.object(closing, "_", new=lambda text: text),
			mock.patch.object(closing, "_build_closing_shift", return_value=built),
		):
			closing.POSClosingShift._apply_server_totals(fake)
		return fake

	def test_server_totals_ignore_client_values(self):
		transaction = Row(
			sales_invoice="SINV-1",
			posting_date="2026-11-20",
			grand_total=10.60,
			transaction_currency="USD",
			transaction_amount=10.60,
			customer="Walk-in",
			is_return=0,
		)
		built = Row(
			user="a",
			company="C1",
			pos_profile="P1",
			grand_total=10.60,
			net_total=10.60,
			total_quantity=1,
			payment_reconciliation=[Row(mode_of_payment="Cash", opening_amount=50, expected_amount=60.60)],
			pos_transactions=[transaction],
			taxes=[],
			pos_payments=[],
		)
		fake = self._apply(built)
		self.assertEqual(len(fake.payment_reconciliation), 1)
		cash = fake.payment_reconciliation[0]
		self.assertEqual(cash["mode_of_payment"], "Cash")
		self.assertAlmostEqual(cash["expected_amount"], 60.60, places=2)
		self.assertAlmostEqual(cash["opening_amount"], 50, places=2)
		self.assertAlmostEqual(cash["closing_amount"], 40, places=2)
		self.assertEqual(fake.user, "a")
		self.assertEqual(fake.company, "C1")
		self.assertEqual(fake.pos_profile, "P1")
		self.assertAlmostEqual(fake.grand_total, 10.60, places=2)
		self.assertEqual([t["sales_invoice"] for t in fake.pos_transactions], ["SINV-1"])
		self.assertNotIn("is_return", fake.pos_transactions[0])

	def test_mode_without_client_row_counts_zero(self):
		built = Row(
			user="a",
			company="C1",
			pos_profile="P1",
			grand_total=0,
			net_total=0,
			total_quantity=0,
			payment_reconciliation=[
				Row(mode_of_payment="Cash", opening_amount=50, expected_amount=60.60),
				Row(mode_of_payment="Card", opening_amount=0, expected_amount=5.60),
			],
			pos_transactions=[],
			taxes=[],
			pos_payments=[],
		)
		fake = self._apply(built)
		counted = {row["mode_of_payment"]: row["closing_amount"] for row in fake.payment_reconciliation}
		self.assertEqual(counted, {"Cash": 40, "Card": 0})
		self.assertEqual(fake.payment_reconciliation[1]["closing_amount"], 0)


if __name__ == "__main__":
	unittest.main()
