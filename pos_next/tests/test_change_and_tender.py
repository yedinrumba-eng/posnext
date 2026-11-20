"""Spec 034 - the change leaves the drawer once and non-cash tender is capped, no bench needed.

frappe is stubbed (tests.frappe_stub). The override is exercised with a fake invoice that carries
only what make_pos_gl_entries reads; the guard with the DB-facing helpers of price_guard patched.
"""

import importlib
import unittest
from unittest import mock

from pos_next.tests import frappe_stub

override = None
rules = None
guard = None

NOT_FINITE = ("nan", "inf", "-inf", "1e999")


def setUpModule():
	global override, rules, guard
	frappe_stub.install()
	override = importlib.import_module("pos_next.overrides.sales_invoice")
	rules = importlib.import_module("pos_next.price_rules")
	guard = importlib.import_module("pos_next.api.price_guard")


def tearDownModule():
	frappe_stub.uninstall()


def _flt(value, precision=None):
	number = float(value or 0)
	return round(number, precision) if precision is not None else number


def _cint(value):
	return int(value or 0)


def _throw(message, *args, **kwargs):
	raise RuntimeError(message)


class Row(dict):
	"""Child-row stand-in: attribute access like a Frappe row, .get like a dict."""

	def __getattr__(self, name):
		return self.get(name)

	def __setattr__(self, name, value):
		self[name] = value


def _pay(mode, account, amount):
	return Row(mode_of_payment=mode, account=account, amount=amount, base_amount=amount)


def _net(gl, account):
	return sum(e.get("debit", 0) - e.get("credit", 0) for e in gl if e["account"] == account)


class FakeInvoice:
	"""Every attribute make_pos_gl_entries reads."""

	def __init__(self, payments, change_amount):
		self.is_pos = 1
		self.is_return = 0
		self.return_against = ""
		self.name = "SINV-1"
		self.doctype = "Sales Invoice"
		self.customer = "Walk-In"
		self.cost_center = "Main - C1"
		self.debit_to = "Debtors - C1"
		self.party_account_currency = "USD"
		self.company_currency = "USD"
		self.account_for_change_amount = "Cash - C1"
		self.change_amount = change_amount
		self.payments = payments
		self.precision = lambda *args: 2
		self.get_gl_dict = lambda args, *a, **kw: dict(args)
		self.get_party_and_party_type_for_pos_gl_entry = lambda mode, account: ("", "")


class ChangeOnceCase(unittest.TestCase):
	def setUp(self):
		fake_frappe = mock.MagicMock()
		fake_frappe.db.get_single_value.return_value = 0
		for patch in (
			mock.patch.object(override, "flt", side_effect=_flt),
			mock.patch.object(override, "cint", side_effect=_cint),
			mock.patch.object(override, "get_account_currency", return_value="USD"),
			mock.patch.object(override, "frappe", fake_frappe),
		):
			patch.start()
			self.addCleanup(patch.stop)

	def post(self, payments, change):
		gl = []
		fake = FakeInvoice(payments, change)
		override.CustomSalesInvoice.make_pos_gl_entries(fake, gl)
		return gl

	def test_two_cash_taps_subtract_change_once(self):
		gl = self.post([_pay("Cash", "Cash - C1", 5), _pay("Cash", "Cash - C1", 20)], 14.40)
		self.assertAlmostEqual(_net(gl, "Cash - C1"), 10.60, places=2)
		self.assertAlmostEqual(_net(gl, "Debtors - C1"), -10.60, places=2)
		for entry in gl:
			self.assertGreaterEqual(entry.get("debit", 0), 0)
			self.assertGreaterEqual(entry.get("credit", 0), 0)

	def test_two_modes_on_one_cash_account_subtract_once(self):
		gl = self.post([_pay("Cash", "Cash - C1", 5), _pay("Cash Bag", "Cash - C1", 20)], 14.40)
		self.assertAlmostEqual(_net(gl, "Cash - C1"), 10.60, places=2)

	def test_single_cash_row_matches_upstream(self):
		gl = self.post([_pay("Cash", "Cash - C1", 20)], 9.40)
		self.assertAlmostEqual(_net(gl, "Cash - C1"), 10.60, places=2)

	def test_row_emptied_by_change_posts_nothing(self):
		gl = self.post([_pay("Cash", "Cash - C1", 10.60), _pay("Cash", "Cash - C1", 14.40)], 14.40)
		self.assertEqual(len(gl), 2)

	def test_card_row_keeps_its_amount(self):
		gl = self.post([_pay("Card", "Card - C1", 5.60), _pay("Cash", "Cash - C1", 20)], 15)
		self.assertAlmostEqual(_net(gl, "Card - C1"), 5.60, places=2)
		self.assertAlmostEqual(_net(gl, "Cash - C1"), 5.00, places=2)

	def test_change_beyond_cash_rows_comes_off_the_last_one(self):
		payments = [_pay("Card", "Card - C1", 30), _pay("Cash", "Cash - C1", 5)]
		override.subtract_change_once(payments, "Cash - C1", 24.40, 2)
		self.assertAlmostEqual(30 + 5 - sum(row.base_amount for row in payments), 24.40, places=2)
		self.assertAlmostEqual(payments[0].base_amount, 30, places=2)


	def test_change_rounding_leaves_no_dust(self):
		payments = [
			_pay("Card", "Card - C1", 10.60),
			_pay("Cash", "Cash - C1", 0.60),
			_pay("Cash", "Cash - C1", 20),
		]
		gl = self.post(payments, 20.60)
		self.assertEqual([p.base_amount for p in payments], [10.6, 0.0, 0.0])
		self.assertEqual(len(gl), 2)

	def test_change_rounding_small_coins(self):
		payments = [
			_pay("Card", "Card - C1", 10.60),
			_pay("Cash", "Cash - C1", 0.10),
			_pay("Cash", "Cash - C1", 0.20),
		]
		gl = self.post(payments, 0.30)
		self.assertEqual([p.base_amount for p in payments], [10.6, 0.0, 0.0])
		self.assertEqual(len(gl), 2)


class TenderRulesCase(unittest.TestCase):
	def test_non_cash_over_total_is_rejected(self):
		message = rules.tender_violation([0.01], [1000], 10.60, 0)
		self.assertIn("1000.00", message)
		self.assertIn("10.60", message)
		self.assertIsNotNone(rules.tender_violation([0.01], [10.61], 10.60, 0))
		self.assertIsNone(rules.tender_violation([0.01], [10.604], 10.60, 0))

	def test_change_over_cash_rule(self):
		self.assertEqual(
			rules.tender_violation([5.0], [5.60], 10.60, 6.0),
			"Change 6.00 is more than the cash received 5.00",
		)

	def test_split_within_limits_passes(self):
		self.assertIsNone(rules.tender_violation([20], [5.60], 10.60, 15))
		self.assertIsNone(rules.tender_violation([], [10.60], 10.60, 0))

	def test_non_finite_amounts_are_rejected(self):
		message = rules.NON_FINITE_PAYMENT_MESSAGE
		for raw in NOT_FINITE:
			bad = float(raw)
			self.assertEqual(rules.tender_violation([bad], [1], 10.60, 0), message, raw)
			self.assertEqual(rules.tender_violation([1], [bad], 10.60, 0), message, raw)
			self.assertEqual(rules.tender_violation([1], [1], bad, 0), message, raw)
			self.assertEqual(rules.tender_violation([1], [1], 10.60, bad), message, raw)
			for flags in ((0, 0), (1, 1)):
				self.assertEqual(rules.payment_violation([bad], 10.60, *flags), message, raw)
				self.assertEqual(rules.payment_violation([10.60], bad, *flags), message, raw)


class FakeDoc:
	doctype = "Sales Invoice"

	def __init__(self):
		self.is_return = 0
		self.pos_profile = "P1"
		self.grand_total = 10.60
		self.rounded_total = 0
		self.change_amount = 989.41
		self.additional_discount_percentage = 0
		self.discount_amount = 0
		self.total = 10.60
		self.payments = [
			Row(mode_of_payment="Card", amount=1000, type="Cash"),
			Row(mode_of_payment="Cash", amount=0.01, type="Cash"),
		]

	def get(self, name, default=None):
		return getattr(self, name, default)


class GuardCapCase(unittest.TestCase):
	def setUp(self):
		self.override = False
		self.settings = None
		for patch in (
			mock.patch.object(guard, "_settings", side_effect=lambda p: self.settings),
			mock.patch.object(guard, "_is_override", side_effect=lambda: self.override),
			mock.patch.object(
				guard, "_mode_of_payment_types", return_value={"Cash": "Cash", "Card": "Bank"}
			),
			mock.patch.object(guard, "flt", side_effect=_flt),
			mock.patch.object(guard, "cint", side_effect=_cint),
			mock.patch.object(guard, "_", new=lambda text: text),
			mock.patch.object(guard.frappe, "throw", side_effect=_throw),
		):
			patch.start()
			self.addCleanup(patch.stop)

	def test_guard_counts_cash_by_server_type(self):
		with self.assertRaisesRegex(RuntimeError, "non-cash payments 1000.00 are more than the invoice"):
			guard.enforce_full_payment(FakeDoc())

	def test_owner_is_capped_too(self):
		self.override = True
		with self.assertRaisesRegex(RuntimeError, "non-cash payments 1000.00 are more than the invoice"):
			guard.enforce_full_payment(FakeDoc())

	def test_guard_off_skips_the_cap(self):
		self.settings = {"enforce_server_guard": 0}
		guard.enforce_full_payment(FakeDoc())


if __name__ == "__main__":
	unittest.main()
