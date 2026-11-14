"""S10.3 - the server-side price/tax/payment/return guard, tested without a bench.

frappe is stubbed (tests.frappe_stub); every DB-facing helper of price_guard and frappe.throw are
patched, so the tests exercise the decisions of enforce_pos_prices / enforce_full_payment /
require_pos_flag against a fixed world.
"""

import importlib
import unittest
from unittest import mock

from pos_next.tests import frappe_stub

module = None


def setUpModule():
	global module
	frappe_stub.install()
	module = importlib.import_module("pos_next.api.price_guard")


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


TEMPLATES = {
	"NY Tax - C1": [
		{
			"charge_type": "On Net Total",
			"account_head": "Sales Tax - C1",
			"description": "NY Tax",
			"rate": 8.875,
			"cost_center": "Main - C1",
			"included_in_print_rate": 0,
			"row_id": None,
		}
	]
}

PROFILES = {
	"P1": {
		"company": "C1",
		"disabled": 0,
		"selling_price_list": "Std",
		"taxes_and_charges": "NY Tax - C1",
		"currency": "USD",
		"tax_category": "",
		"warehouse": "Stores - C1",
	},
	"P2": {
		"company": "C1",
		"disabled": 0,
		"selling_price_list": "Std",
		"taxes_and_charges": "",
		"currency": "USD",
		"tax_category": "",
		"warehouse": "Stores - C1",
	},
}

SETTINGS_OFF = {
	"allow_user_to_edit_item_discount": 0,
	"allow_user_to_edit_additional_discount": 0,
	"max_discount_allowed": 0,
	"allow_partial_payment": 0,
	"allow_credit_sale": 0,
	"allow_return": 0,
	"enforce_server_guard": 1,
	"disable_rounded_total": 1,
	"allow_change_posting_date": 0,
}

PRICES = {"SODA": {"Nos": 1.99}, "HAM": {"Lb": 6.0}}
STOCK_UOMS = {"SODA": "Nos", "HAM": "Lb"}
CONVERSIONS = {"SODA": {"Nos": 1.0}, "HAM": {"Lb": 1.0, "Oz": 0.0625}}
ACCOUNTS = {"Cash": "Cash - C1", "EBT/SNAP": "EBT - C1", "Wire": "Bank - C1"}
PROFILE_MODES = {"Cash": True, "EBT/SNAP": False, "Gift": True}


def _tax_row():
	return Row(TEMPLATES["NY Tax - C1"][0])


def _snap_row():
	return Row(
		charge_type="Actual",
		account_head="Sales Tax - C1",
		description="SNAP tax exemption",
		tax_amount=-0.89,
		cost_center="Main - C1",
	)


def _row1():
	return Row(
		name="row1",
		item_code="SODA",
		uom="Nos",
		conversion_factor=1.0,
		stock_uom="Nos",
		price_list_rate=1.99,
		discount_percentage=0,
		discount_amount=0,
		rate=1.99,
		margin_type="",
		margin_rate_or_amount=0,
		item_tax_template=None,
		item_tax_rate=None,
		warehouse="Stores - C1",
		income_account="Sales - C1",
		expense_account="COGS - C1",
		cost_center="Main - C1",
		mapped_additional_discount_amount=0,
		distributed_discount_amount=0,
	)


class FakeOriginal:
	def __init__(self, extra_taxes=(), currency="USD"):
		self.docstatus = 1
		self.is_return = 0
		self.company = "C1"
		self.discount_amount = 0
		self.currency = currency
		self.taxes_and_charges = "NY Tax - C1"
		self.tax_category = "Orig Cat"
		self.debit_to = "Debtors - C1"
		self.cost_center = "Main - C1"
		self.set_warehouse = "Stores - C1"
		self.items = [_row1()]
		self.taxes = [_tax_row(), *extra_taxes]

	def get(self, name, default=None):
		return getattr(self, name, default)


ORIGINALS = {
	"SINV-1": FakeOriginal,
	"SINV-SNAP": lambda: FakeOriginal(extra_taxes=(_snap_row(),)),
	"SINV-EUR": lambda: FakeOriginal(currency="EUR"),
}


class FakeDoc:
	doctype = "Sales Invoice"

	def __init__(self, items=(), **values):
		self.is_pos = 1
		self.pos_profile = "P1"
		self.company = "C1"
		self.is_return = 0
		self.return_against = ""
		self.taxes_and_charges = ""
		self.selling_price_list = ""
		self.taxes = []
		self.items = list(items)
		self.flags = {}
		self.write_off_amount = 0
		self.base_write_off_amount = 0
		self.write_off_outstanding_amount_automatically = 0
		self.additional_discount_percentage = 0
		self.discount_amount = 0
		self.paid_amount = 0
		self.grand_total = 0
		self.customer = "Walk-In"
		self.currency = "USD"
		self.conversion_rate = 1
		self.price_list_currency = "USD"
		self.plc_conversion_rate = 1
		self.is_consolidated = 0
		self.redeem_loyalty_points = 0
		self.loyalty_points = 0
		self.loyalty_amount = 0
		self.tax_category = ""
		self.ignore_pricing_rule = 0
		self.disable_rounded_total = 0
		self.update_stock = 0
		self.is_opening = "No"
		self.set_posting_time = 0
		self.debit_to = ""
		self.cost_center = ""
		self.account_for_change_amount = ""
		self.set_warehouse = ""
		self.set_target_warehouse = ""
		self.is_debit_note = 0
		self.allocate_advances_automatically = 0
		self.advances = []
		self.payments = []
		self.rounded_total = 0
		self.total = 0
		self.apply_tds = 0
		self.override_tax_withholding_entries = 0
		self.tax_withholding_group = None
		self.tax_withholding_entries = []
		self.__dict__.update(values)

	def get(self, name, default=None):
		return getattr(self, name, default)

	def set(self, name, value):
		setattr(self, name, list(value))

	def append(self, table, values):
		row = Row(values)
		getattr(self, table).append(row)
		return row

	def append_taxes_from_master(self, master):
		self.taxes.extend(Row(row) for row in TEMPLATES[self.taxes_and_charges])


def _soda(**changes):
	row = Row(
		item_code="SODA",
		qty=2,
		rate=0.5,
		uom="Nos",
		conversion_factor=1.0,
		discount_percentage=0,
		item_tax_template="Bogus Tax",
		item_tax_rate='{"Sales Tax - C1": 0}',
	)
	row.update(changes)
	return row


class GuardCase(unittest.TestCase):
	def setUp(self):
		self.override = False
		self.members = {"P1"}
		self.settings = {"P1": dict(SETTINGS_OFF)}
		self.profiles = {k: dict(v) for k, v in PROFILES.items()}
		self.price_list_currency = "USD"
		patches = [
			mock.patch.object(module, "_is_override", side_effect=lambda: self.override),
			mock.patch.object(module, "_is_profile_user", side_effect=lambda p: p in self.members),
			mock.patch.object(module, "_profile", side_effect=lambda p: self.profiles.get(p)),
			mock.patch.object(module, "_settings", side_effect=lambda p: self.settings.get(p)),
			mock.patch.object(module, "_default_tax_template", return_value=None),
			mock.patch.object(module, "_load_prices", return_value=PRICES),
			mock.patch.object(module, "_load_stock_uoms", return_value=STOCK_UOMS),
			mock.patch.object(module, "_load_uom_conversions", return_value=CONVERSIONS),
			mock.patch.object(
				module,
				"_original_invoice",
				side_effect=lambda name: ORIGINALS[name]() if name in ORIGINALS else None,
			),
			mock.patch.object(module, "_company_currency", return_value="USD"),
			mock.patch.object(
				module, "_price_list_currency", side_effect=lambda price_list: self.price_list_currency
			),
			mock.patch.object(
				module, "_is_internal_customer", side_effect=lambda customer: customer == "INT"
			),
			mock.patch.object(
				module, "_profile_payment_modes", side_effect=lambda profile: dict(PROFILE_MODES)
			),
			mock.patch.object(
				module,
				"_mode_of_payment_accounts",
				side_effect=lambda company, modes: {m: ACCOUNTS[m] for m in modes if m in ACCOUNTS},
			),
			mock.patch.object(module, "_", new=lambda text: text),
			mock.patch.object(module, "flt", side_effect=_flt),
			mock.patch.object(module, "cint", side_effect=_cint),
		]
		for patch in patches:
			patch.start()
			self.addCleanup(patch.stop)
		throw_patch = mock.patch.object(module.frappe, "throw", side_effect=_throw)
		self.throw = throw_patch.start()
		self.addCleanup(throw_patch.stop)

	def assertThrows(self, fn, doc, text):
		with self.assertRaises(RuntimeError) as ctx:
			fn(doc)
		self.assertIn(text, str(ctx.exception))

	def assertNoThrow(self, fn, doc):
		self.throw.reset_mock()
		fn(doc)
		self.throw.assert_not_called()


class TestSale(GuardCase):
	def test_1_list_sale_of_the_cashier_passes(self):
		without_key = {k: v for k, v in SETTINGS_OFF.items() if k != "enforce_server_guard"}
		for settings in (dict(SETTINGS_OFF), without_key):
			self.settings["P1"] = settings
			doc = FakeDoc(items=[_soda()])
			self.assertNoThrow(module.enforce_pos_prices, doc)
			row = doc.items[0]
			self.assertEqual(1.99, row.price_list_rate)
			self.assertEqual(0, row.rate)
			self.assertEqual(0, row.discount_amount)
			self.assertEqual(1.0, row.conversion_factor)
			self.assertIsNone(row.item_tax_template)
			self.assertIsNone(row.item_tax_rate)
			self.assertEqual("Std", doc.selling_price_list)

	def test_2_client_actual_tax_row_is_replaced_by_the_template(self):
		bad = Row(charge_type="Actual", account_head="Sales Tax - C1", tax_amount=-50)
		doc = FakeDoc(items=[_soda()], taxes_and_charges="NY Tax - C1", taxes=[bad])
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual(1, len(doc.taxes))
		self.assertEqual("On Net Total", doc.taxes[0].charge_type)
		self.assertEqual(8.875, doc.taxes[0].rate)

	def test_3_zero_percent_tax_row_is_replaced_and_template_filled(self):
		zero = Row(charge_type="On Net Total", account_head="Sales Tax - C1", rate=0)
		doc = FakeDoc(items=[_soda()], taxes_and_charges="", taxes=[zero])
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual("NY Tax - C1", doc.taxes_and_charges)
		self.assertEqual(1, len(doc.taxes))
		self.assertEqual(8.875, doc.taxes[0].rate)

	def test_4_write_off_is_zeroed_and_a_cent_payment_is_rejected(self):
		doc = FakeDoc(
			items=[_soda()],
			write_off_amount=9.99,
			base_write_off_amount=9.99,
			write_off_outstanding_amount_automatically=1,
		)
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual(0, doc.write_off_amount)
		self.assertEqual(0, doc.base_write_off_amount)
		self.assertEqual(0, doc.write_off_outstanding_amount_automatically)
		pay = FakeDoc(payments=[Row(mode_of_payment="Cash", amount=0.01)], grand_total=10)
		self.assertThrows(
			module.enforce_full_payment, pay, "Payment 0.01 is less than the invoice total 10.00"
		)

	def test_5_not_pos_sale_is_rejected_and_taxes_stay(self):
		row = _snap_row()
		doc = FakeDoc(items=[_soda()], is_pos=0, taxes=[row])
		self.assertThrows(module.enforce_pos_prices, doc, "Only POS sales are allowed for this user")
		self.assertEqual([row], doc.taxes)

	def test_6_pos_sale_without_profile_is_rejected(self):
		doc = FakeDoc(items=[_soda()], pos_profile="")
		self.assertThrows(module.enforce_pos_prices, doc, "POS Profile is required")

	def test_7_profile_of_someone_else_is_rejected(self):
		doc = FakeDoc(items=[_soda()], pos_profile="P2")
		self.assertThrows(module.enforce_pos_prices, doc, "You are not a user of POS Profile P2")

	def test_8_uom_factor_comes_from_the_item_table(self):
		line = Row(item_code="HAM", qty=1, rate=0.01, uom="Lb", conversion_factor=0.01)
		doc = FakeDoc(items=[line])
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual(1.0, doc.items[0].conversion_factor)
		self.assertEqual(6.0, doc.items[0].price_list_rate)
		gram = FakeDoc(items=[Row(item_code="HAM", qty=1, uom="Gram", conversion_factor=1)])
		self.assertThrows(module.enforce_pos_prices, gram, "UOM Gram is not set up")

	def test_17_currency_is_forced_and_foreign_profile_or_list_is_rejected(self):
		doc = FakeDoc(
			items=[_soda()],
			currency="EUR",
			conversion_rate=0.0001,
			plc_conversion_rate=0.0001,
			price_list_currency="EUR",
		)
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual("USD", doc.currency)
		self.assertEqual(1, doc.conversion_rate)
		self.assertEqual(1, doc.plc_conversion_rate)
		self.assertEqual("USD", doc.price_list_currency)
		self.profiles["P1"]["currency"] = "EUR"
		self.assertThrows(
			module.enforce_pos_prices,
			FakeDoc(items=[_soda()]),
			"POS Profile currency EUR is not the company currency USD",
		)
		self.profiles["P1"]["currency"] = "USD"
		self.price_list_currency = "EUR"
		self.assertThrows(module.enforce_pos_prices, FakeDoc(items=[_soda()]), "Price list currency EUR")

	def test_18_loyalty_is_zeroed_and_loyalty_amount_does_not_count_as_payment(self):
		doc = FakeDoc(items=[_soda()], redeem_loyalty_points=1, loyalty_points=0, loyalty_amount=9.99)
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual((0, 0, 0), (doc.redeem_loyalty_points, doc.loyalty_points, doc.loyalty_amount))
		pay = FakeDoc(
			payments=[Row(mode_of_payment="Cash", amount=0.01)],
			paid_amount=10.0,
			loyalty_amount=9.99,
			redeem_loyalty_points=1,
			grand_total=10,
		)
		self.assertThrows(
			module.enforce_full_payment, pay, "Payment 0.01 is less than the invoice total 10.00"
		)

	def test_19_consolidated_flag_is_cleared(self):
		doc = FakeDoc(items=[_soda()], is_consolidated=1)
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual(0, doc.is_consolidated)

	def test_20_tax_category_comes_from_the_profile(self):
		doc = FakeDoc(items=[_soda()], tax_category="Exempt")
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual("", doc.tax_category)
		self.profiles["P1"]["tax_category"] = "NY Retail"
		doc = FakeDoc(items=[_soda()], tax_category="Exempt")
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual("NY Retail", doc.tax_category)

	def test_21_header_switches_are_forced(self):
		doc = FakeDoc(
			items=[_soda()], ignore_pricing_rule=0, update_stock=0, is_opening="Yes", set_posting_time=1
		)
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual(1, doc.ignore_pricing_rule)
		self.assertEqual(1, doc.update_stock)
		self.assertEqual("No", doc.is_opening)
		self.assertEqual(0, doc.set_posting_time)
		self.assertEqual(1, doc.disable_rounded_total)

		self.settings["P1"]["allow_change_posting_date"] = 1
		self.settings["P1"]["disable_rounded_total"] = 0
		doc = FakeDoc(items=[_soda()], set_posting_time=1)
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual(1, doc.set_posting_time)
		self.assertEqual(0, doc.disable_rounded_total)

		self.settings["P1"] = None
		doc = FakeDoc(items=[_soda()], set_posting_time=1)
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual(1, doc.disable_rounded_total)
		self.assertEqual(0, doc.set_posting_time)

	def test_22_ledger_accounts_warehouses_and_links_are_cleared(self):
		line = _soda(
			warehouse="W2",
			income_account="Other - C1",
			expense_account="Other - C1",
			cost_center="X - C1",
			target_warehouse="W3",
			sales_order="SO-1",
			so_detail="SOD-1",
			delivery_note="DN-1",
			dn_detail="DND-1",
			allow_zero_valuation_rate=1,
			delivered_by_supplier=1,
			enable_deferred_revenue=1,
		)
		doc = FakeDoc(
			items=[line],
			debit_to="Other - C1",
			cost_center="X - C1",
			account_for_change_amount="Bank - C1",
			set_warehouse="W2",
			set_target_warehouse="W3",
			is_debit_note=1,
			allocate_advances_automatically=1,
			advances=[Row(reference_name="PE-1")],
		)
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual(("", "", ""), (doc.debit_to, doc.cost_center, doc.account_for_change_amount))
		self.assertEqual("Stores - C1", doc.set_warehouse)
		self.assertEqual("", doc.set_target_warehouse)
		self.assertEqual(0, doc.is_debit_note)
		self.assertEqual(0, doc.allocate_advances_automatically)
		self.assertEqual([], doc.advances)
		row = doc.items[0]
		self.assertEqual("Stores - C1", row.warehouse)
		for field in (
			"income_account",
			"expense_account",
			"cost_center",
			"target_warehouse",
			"sales_order",
			"so_detail",
			"delivery_note",
			"dn_detail",
		):
			self.assertIsNone(row[field], field)
		for field in ("allow_zero_valuation_rate", "delivered_by_supplier", "enable_deferred_revenue"):
			self.assertEqual(0, row[field], field)

	def test_23_payment_rows_are_checked_against_the_profile_and_get_the_server_account(self):
		doc = FakeDoc(
			items=[_soda()],
			payments=[Row(mode_of_payment="Cash", account="Expense - C1", amount=5)],
		)
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual("Cash - C1", doc.payments[0].account)
		gift = FakeDoc(items=[_soda()], payments=[Row(mode_of_payment="Gift", amount=1)])
		self.assertThrows(
			module.enforce_pos_prices, gift, "Mode of payment Gift has no account for company C1"
		)
		wire = FakeDoc(items=[_soda()], payments=[Row(mode_of_payment="Wire", amount=1)])
		self.assertThrows(
			module.enforce_pos_prices, wire, "Mode of payment Wire is not set up in POS Profile P1"
		)

	def test_26_internal_customer_is_rejected(self):
		doc = FakeDoc(items=[_soda()], customer="INT")
		self.assertThrows(
			module.enforce_pos_prices, doc, "Internal customers are not allowed for this user"
		)

	def test_15_guard_off_leaves_the_client_price_but_keeps_the_access_check(self):
		self.settings["P1"]["enforce_server_guard"] = 0
		doc = FakeDoc(items=[_soda()])
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual(0.5, doc.items[0].rate)
		other = FakeDoc(items=[_soda()], pos_profile="P2")
		self.assertThrows(module.enforce_pos_prices, other, "You are not a user of POS Profile P2")

	def test_28_mapped_and_distributed_discounts_are_zeroed_on_a_sale_and_copied_on_a_return(self):
		doc = FakeDoc(
			items=[_soda(mapped_additional_discount_amount=1.98, distributed_discount_amount=1.98)]
		)
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual(0, doc.items[0].mapped_additional_discount_amount)
		self.assertEqual(0, doc.items[0].distributed_discount_amount)

		self.settings["P1"]["allow_return"] = 1
		line = Row(item_code="SODA", qty=-1, sales_invoice_item="row1", rate=50, price_list_rate=50)
		line.mapped_additional_discount_amount = 1.98
		line.distributed_discount_amount = 1.98
		returned = FakeDoc(items=[line], is_return=1, return_against="SINV-1")
		self.assertNoThrow(module.enforce_pos_prices, returned)
		self.assertEqual(0, returned.items[0].mapped_additional_discount_amount)
		self.assertEqual(0, returned.items[0].distributed_discount_amount)

	def test_30_tax_withholding_is_switched_off_on_the_header_and_the_rows(self):
		doc = FakeDoc(
			items=[_soda(apply_tds=1, tax_withholding_category="TDS-X")],
			apply_tds=1,
			override_tax_withholding_entries=1,
			tax_withholding_group="TWG",
			tax_withholding_entries=[Row(tax_withholding_category="TDS-X", withholding_amount=5)],
		)
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual(0, doc.apply_tds)
		self.assertEqual(0, doc.override_tax_withholding_entries)
		self.assertIsNone(doc.tax_withholding_group)
		self.assertEqual([], doc.tax_withholding_entries)
		self.assertEqual(0, doc.items[0].apply_tds)
		self.assertIsNone(doc.items[0].tax_withholding_category)


class TestPayment(GuardCase):
	def test_9_payment_must_cover_the_total_unless_a_flag_allows_it(self):
		doc = FakeDoc(payments=[Row(mode_of_payment="Cash", amount=5)], grand_total=10)
		self.assertThrows(
			module.enforce_full_payment, doc, "Payment 5.00 is less than the invoice total 10.00"
		)
		self.settings["P1"] = None
		self.assertThrows(module.enforce_full_payment, doc, "Payment 5.00 is less than")
		self.settings["P1"] = dict(SETTINGS_OFF, allow_partial_payment=1)
		self.assertNoThrow(module.enforce_full_payment, doc)
		self.settings["P1"] = dict(SETTINGS_OFF, allow_credit_sale=1)
		self.assertNoThrow(module.enforce_full_payment, doc)

	def test_24_negative_payment_row_is_rejected_even_with_credit(self):
		doc = FakeDoc(
			payments=[
				Row(mode_of_payment="EBT/SNAP", amount=30),
				Row(mode_of_payment="Cash", amount=-20),
			],
			grand_total=10,
		)
		message = "Payment amounts cannot be negative on a sale"
		self.assertThrows(module.enforce_full_payment, doc, message)
		self.settings["P1"] = dict(SETTINGS_OFF, allow_credit_sale=1)
		self.assertThrows(module.enforce_full_payment, doc, message)

	def test_25_the_due_amount_is_the_rounded_total_when_there_is_one(self):
		doc = FakeDoc(
			payments=[Row(mode_of_payment="Cash", amount=10.0)], grand_total=10.02, rounded_total=10.0
		)
		self.assertNoThrow(module.enforce_full_payment, doc)
		doc.rounded_total = 0
		self.assertThrows(
			module.enforce_full_payment, doc, "Payment 10.00 is less than the invoice total 10.02"
		)

	def test_29_a_materialized_invoice_discount_is_checked_before_submit(self):
		def make(paid=2.0):
			return FakeDoc(
				discount_amount=1.98,
				total=3.98,
				grand_total=2.0,
				payments=[Row(mode_of_payment="Cash", amount=paid)],
			)

		message = "Additional discount is not allowed"
		self.assertThrows(module.enforce_full_payment, make(), message)
		self.assertThrows(module.enforce_full_payment, make(1.0), message)
		self.assertEqual("Price check", self.throw.call_args.kwargs["title"])

		self.settings["P1"] = dict(
			SETTINGS_OFF, allow_user_to_edit_additional_discount=1, max_discount_allowed=10
		)
		self.assertThrows(module.enforce_full_payment, make(), "is over the 10.0% limit")

		self.settings["P1"] = dict(
			SETTINGS_OFF, allow_user_to_edit_additional_discount=1, max_discount_allowed=0
		)
		self.assertNoThrow(module.enforce_full_payment, make())

		self.settings["P1"] = dict(SETTINGS_OFF)
		self.override = True
		self.assertNoThrow(module.enforce_full_payment, make())


class TestReturn(GuardCase):
	def setUp(self):
		super().setUp()
		self.settings["P1"]["allow_return"] = 1

	def _return(self, against, **changes):
		line = Row(item_code="SODA", qty=-1, sales_invoice_item="row1", rate=50, price_list_rate=50)
		return FakeDoc(items=[line], is_return=1, return_against=against, **changes)

	def test_10_return_without_original_is_rejected(self):
		self.assertThrows(
			module.enforce_pos_prices, self._return(""), "A return needs the original invoice"
		)

	def test_11_valid_return_takes_price_and_tax_from_the_original(self):
		doc = self._return("SINV-1", discount_amount=5, additional_discount_percentage=3)
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual(1.99, doc.items[0].rate)
		self.assertEqual(1.99, doc.items[0].price_list_rate)
		self.assertEqual(1, len(doc.taxes))
		self.assertEqual("On Net Total", doc.taxes[0].charge_type)
		self.assertEqual("Sales Tax - C1", doc.taxes[0].account_head)
		self.assertEqual(0, doc.discount_amount)
		self.assertEqual(0, doc.additional_discount_percentage)

	def test_27_return_copies_the_ledger_header_and_checks_currency_and_payment_modes(self):
		doc = self._return("SINV-1")
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual("Orig Cat", doc.tax_category)
		self.assertEqual("Debtors - C1", doc.debit_to)
		self.assertEqual("Main - C1", doc.cost_center)
		self.assertEqual("Stores - C1", doc.set_warehouse)
		self.assertEqual("Stores - C1", doc.items[0].warehouse)
		self.assertEqual("Sales - C1", doc.items[0].income_account)
		self.assertEqual("USD", doc.currency)
		self.assertThrows(
			module.enforce_pos_prices, self._return("SINV-EUR"), "Original invoice currency EUR"
		)
		refund = self._return("SINV-1", payments=[Row(mode_of_payment="EBT/SNAP", amount=-1.99)])
		self.assertThrows(
			module.enforce_pos_prices, refund, "Mode of payment EBT/SNAP is not allowed in returns"
		)

	def test_12_cashier_cannot_return_a_snap_invoice(self):
		self.assertThrows(
			module.enforce_pos_prices, self._return("SINV-SNAP"), "the owner returns it from Desk"
		)

	def test_13_owner_through_the_pos_api_cannot_return_a_snap_invoice(self):
		self.override = True
		doc = self._return("SINV-SNAP")
		doc.flags = {"pos_next_api": True}
		self.assertThrows(module.enforce_pos_prices, doc, "the owner returns it from Desk")
		desk = self._return("SINV-SNAP", taxes=[_snap_row()])
		kept = list(desk.taxes)
		self.assertNoThrow(module.enforce_pos_prices, desk)
		self.assertEqual(kept, desk.taxes)


class TestOwnerAndFlags(GuardCase):
	def test_14_owner_skips_the_guard(self):
		self.override = True
		row = Row(charge_type="Actual", account_head="Sales Tax - C1", tax_amount=-5)
		doc = FakeDoc(items=[_soda()], is_pos=0, taxes=[row])
		self.assertNoThrow(module.enforce_pos_prices, doc)
		self.assertEqual([row], doc.taxes)
		self.assertEqual(0.5, doc.items[0].rate)

	def test_16_require_pos_flag(self):
		self.override = True
		module.require_pos_flag("P9", ("allow_credit_sale",))
		self.throw.assert_not_called()
		self.override = False

		with self.assertRaises(RuntimeError):
			module.require_pos_flag("P2", ("allow_credit_sale",))
		self.assertEqual(module.frappe.PermissionError, self.throw.call_args.args[1])

		with self.assertRaises(RuntimeError):
			module.require_pos_flag("P1", ("allow_partial_payment", "allow_credit_sale"))
		self.assertEqual(module.frappe.PermissionError, self.throw.call_args.args[1])

		self.throw.reset_mock()
		self.settings["P1"]["allow_credit_sale"] = 1
		module.require_pos_flag("P1", ("allow_credit_sale",))
		self.throw.assert_not_called()


if __name__ == "__main__":
	unittest.main()
