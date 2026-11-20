"""Spec 037 - the shift close expects the change once, same rule as the GL, no bench needed.

frappe is stubbed (tests.frappe_stub). _process_invoice runs for real over a fake invoice that
carries only what it reads; flt is patched with a plain float cast.
"""

import importlib
import unittest
from unittest import mock

from pos_next.tests import frappe_stub

closing = None
override = None


def setUpModule():
	global closing, override
	frappe_stub.install()
	closing = importlib.import_module("pos_next.pos_next.doctype.pos_closing_shift.pos_closing_shift")
	override = importlib.import_module("pos_next.overrides.sales_invoice")


def tearDownModule():
	frappe_stub.uninstall()


def _flt(value, precision=None):
	number = float(value or 0)
	return round(number, precision) if precision is not None else number


class Row(dict):
	"""Child-row stand-in: attribute access like a Frappe row, .get like a dict."""

	def __getattr__(self, name):
		return self.get(name)

	def __setattr__(self, name, value):
		self[name] = value


def _pay(mode, account, amount):
	return Row(mode_of_payment=mode, account=account, amount=amount, base_amount=amount)


def _invoice(payments, change, is_return=0, change_account="Cash - C1"):
	return Row(
		name="SINV-1",
		posting_date="2026-11-20",
		customer="Walk-in",
		currency="USD",
		conversion_rate=1,
		is_return=is_return,
		grand_total=10.60,
		base_grand_total=10.60,
		net_total=10.60,
		base_net_total=10.60,
		total_qty=1,
		taxes=[],
		account_for_change_amount=change_account,
		change_amount=change,
		base_change_amount=change,
		payments=payments,
	)


def _summary():
	return {
		"grand_total": 0, "net_total": 0, "total_quantity": 0,
		"returns_total": 0, "returns_count": 0,
		"sales_total": 0, "sales_count": 0,
	}


class TestClosingChange(unittest.TestCase):
	def setUp(self):
		frappe_mock = mock.MagicMock()
		frappe_mock._dict = Row
		frappe_mock.get_precision.return_value = 2
		patches = [
			mock.patch.object(closing, "flt", new=_flt),
			mock.patch.object(override, "flt", new=_flt),
			mock.patch.object(closing, "frappe", new=frappe_mock),
		]
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)

	def _close(self, invoice):
		payments = [Row(mode_of_payment="Cash", opening_amount=50, expected_amount=50)]
		closing._process_invoice(invoice, "sales_invoice", "USD", "Cash", payments, [], _summary())
		return {row.mode_of_payment: row.expected_amount for row in payments}

	def test_closing_two_cash_taps_expect_change_once(self):
		invoice = _invoice([_pay("Cash", "Cash - C1", 5), _pay("Cash", "Cash - C1", 20)], 14.40)
		self.assertAlmostEqual(60.60, self._close(invoice)["Cash"], places=2)

	def test_closing_card_row_keeps_its_amount(self):
		invoice = _invoice([_pay("Card", "Card - C1", 5.60), _pay("Cash", "Cash - C1", 20)], 15)
		result = self._close(invoice)
		self.assertAlmostEqual(55.00, result["Cash"], places=2)
		self.assertAlmostEqual(5.60, result["Card"], places=2)

	def test_closing_return_is_not_reduced(self):
		invoice = _invoice([_pay("Cash", "Cash - C1", -10.60)], 3, is_return=1)
		self.assertAlmostEqual(39.40, self._close(invoice)["Cash"], places=2)

	def test_closing_without_change_account_row_subtracts_nothing(self):
		invoice = _invoice(
			[_pay("Cash", "Cash - C1", 5), _pay("Cash", "Cash - C1", 20)],
			14.40,
			change_account="Other - C1",
		)
		self.assertAlmostEqual(75.00, self._close(invoice)["Cash"], places=2)

	def test_closing_change_rounding_leaves_no_dust(self):
		for cash_rows, change in (((0.60, 20), 20.60), ((0.10, 0.20), 0.30)):
			payments = [_pay("Card", "Card - C1", 10.60)]
			payments += [_pay("Cash", "Cash - C1", amount) for amount in cash_rows]
			result = self._close(_invoice(payments, change))
			self.assertEqual(result["Cash"], 50.0)
			self.assertEqual(result["Card"], 10.6)


if __name__ == "__main__":
	unittest.main()
