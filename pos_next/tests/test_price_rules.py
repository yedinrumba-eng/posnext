import unittest

from pos_next.price_rules import (
	OriginalInvoice,
	access_violation,
	currency_violation,
	expected_unit_price,
	invoice_discount_violation,
	line_violation,
	payment_violation,
	return_line_violation,
	return_violation,
	uom_factor,
)


class TestExpectedUnitPrice(unittest.TestCase):
	def test_exact_uom_wins(self):
		self.assertEqual(5.0, expected_unit_price({"Box": 5.0, "Nos": 1.0}, "Box", "Nos", 12))

	def test_stock_uom_times_conversion_factor(self):
		self.assertEqual(12.0, expected_unit_price({"Nos": 1.0}, "Box", "Nos", 12))

	def test_no_price_is_none(self):
		self.assertIsNone(expected_unit_price({}, "Nos", "Nos", 1))


class TestLineViolation(unittest.TestCase):
	def test_discount_not_allowed(self):
		self.assertIsNotNone(line_violation("SODA", 1.99, 5, False, 0, False))
		self.assertIsNone(line_violation("SODA", 1.99, 0, False, 0, False))

	def test_discount_over_limit(self):
		self.assertIsNotNone(line_violation("SODA", 1.99, 15, True, 10, False))
		self.assertIsNone(line_violation("SODA", 1.99, 10, True, 10, False))
		self.assertIsNone(line_violation("SODA", 1.99, 50, True, 0, False))  # 0 = no limit

	def test_override_passes_but_out_of_range_still_fails(self):
		self.assertIsNone(line_violation("SODA", None, 30, False, 10, True))
		self.assertIsNotNone(line_violation("SODA", 1.99, 120, True, 0, True))
		self.assertIsNotNone(line_violation("SODA", None, 0, True, 0, False))


class TestInvoiceDiscountViolation(unittest.TestCase):
	def test_not_allowed(self):
		self.assertIsNotNone(invoice_discount_violation(5, 0, 100, False, 0, False))
		self.assertIsNone(invoice_discount_violation(0, 0, 100, False, 0, False))

	def test_amount_converted_to_percentage_over_limit(self):
		self.assertIsNotNone(invoice_discount_violation(0, 20, 100, True, 10, False))
		self.assertIsNone(invoice_discount_violation(0, 10, 100, True, 10, False))


class TestUomFactor(unittest.TestCase):
	def test_same_uom_is_one(self):
		self.assertEqual(1.0, uom_factor("Lb", "Lb", {}))

	def test_uom_in_the_table_gives_its_factor(self):
		self.assertEqual(0.0625, uom_factor("Oz", "Lb", {"Lb": 1.0, "Oz": 0.0625}))

	def test_missing_or_not_positive_is_none(self):
		self.assertIsNone(uom_factor("Gram", "Lb", {"Lb": 1.0}))
		self.assertIsNone(uom_factor("Oz", "Lb", {"Oz": 0}))
		self.assertIsNone(uom_factor("Oz", "Lb", {"Oz": -1}))


PROFILE = {"company": "C1", "disabled": 0}


class TestAccessViolation(unittest.TestCase):
	def test_each_condition_gives_its_message_in_order(self):
		self.assertEqual(
			"Only POS sales are allowed for this user",
			access_violation(False, "", None, False, "C1"),
		)
		self.assertEqual("POS Profile is required", access_violation(True, "", None, False, "C1"))
		self.assertEqual(
			"POS Profile P1 does not exist", access_violation(True, "P1", None, False, "C1")
		)
		self.assertEqual(
			"POS Profile P1 is disabled",
			access_violation(True, "P1", {"company": "C1", "disabled": 1}, False, "C1"),
		)
		self.assertEqual(
			"You are not a user of POS Profile P1",
			access_violation(True, "P1", PROFILE, False, "C2"),
		)
		self.assertEqual(
			"POS Profile P1 belongs to another company",
			access_violation(True, "P1", PROFILE, True, "C2"),
		)

	def test_valid_access_is_none(self):
		self.assertIsNone(access_violation(True, "P1", PROFILE, True, "C1"))


class TestCurrencyViolation(unittest.TestCase):
	def test_each_condition_in_order(self):
		self.assertEqual(
			"POS Profile currency EUR is not the company currency USD",
			currency_violation("USD", "EUR", "EUR", "EUR"),
		)
		self.assertEqual(
			"Price list currency EUR is not the company currency USD",
			currency_violation("USD", "USD", "EUR", "EUR"),
		)
		self.assertEqual(
			"Original invoice currency EUR is not the company currency USD: the owner returns it from Desk",
			currency_violation("USD", "USD", "USD", "EUR"),
		)
		self.assertIsNone(currency_violation("USD", "", "", None))
		self.assertIsNone(currency_violation("USD", "USD", "USD", "USD"))


class TestPaymentViolation(unittest.TestCase):
	def test_short_payment_is_an_error(self):
		self.assertEqual(
			"Payment 5.00 is less than the invoice total 10.00",
			payment_violation([5.0], 10, False, False),
		)
		self.assertIsNotNone(payment_violation([9.0, 0.99], 10, False, False))

	def test_flag_or_tiny_gap_passes(self):
		self.assertIsNone(payment_violation([5.0], 10, True, False))
		self.assertIsNone(payment_violation([5.0], 10, False, True))
		self.assertIsNone(payment_violation([9.995], 10, False, False))
		self.assertIsNone(payment_violation([4.0, 6.0], 10, False, False))

	def test_negative_row_is_an_error_even_with_flags(self):
		message = "Payment amounts cannot be negative on a sale"
		self.assertEqual(message, payment_violation([30.0, -20.0], 10, False, False))
		self.assertEqual(message, payment_violation([30.0, -20.0], 10, True, True))


class TestReturnViolation(unittest.TestCase):
	def _original(self, **changes):
		values = {
			"docstatus": 1,
			"is_return": False,
			"company": "C1",
			"has_actual_tax": False,
			"discount_amount": 0.0,
		}
		values.update(changes)
		return OriginalInvoice(**values)

	def test_the_seven_messages_in_order(self):
		self.assertEqual(
			"A return needs the original invoice (return_against)",
			return_violation("", False, None, "C1"),
		)
		self.assertEqual(
			"Returns are not allowed for this POS Profile",
			return_violation("X", False, None, "C1"),
		)
		self.assertEqual("Original invoice X does not exist", return_violation("X", True, None, "C1"))
		self.assertEqual(
			"Original invoice X is not a submitted sale",
			return_violation("X", True, self._original(docstatus=0), "C1"),
		)
		self.assertEqual(
			"Original invoice X is not a submitted sale",
			return_violation("X", True, self._original(is_return=True), "C1"),
		)
		self.assertEqual(
			"Original invoice X belongs to another company",
			return_violation("X", True, self._original(), "C2"),
		)
		self.assertEqual(
			"Invoice X has a SNAP tax exemption or another fixed tax row: the owner returns it from Desk",
			return_violation("X", True, self._original(has_actual_tax=True), "C1"),
		)
		self.assertEqual(
			"Invoice X has an invoice discount: the owner returns it from Desk",
			return_violation("X", True, self._original(discount_amount=1.0), "C1"),
		)
		self.assertIsNone(return_violation("X", True, self._original(), "C1"))


class TestReturnLineViolation(unittest.TestCase):
	def test_three_cases(self):
		self.assertEqual(
			"SODA: a return line needs a negative quantity", return_line_violation("SODA", 1, "SODA")
		)
		self.assertEqual(
			"SODA: the line is not on the original invoice", return_line_violation("SODA", -1, None)
		)
		self.assertEqual(
			"SODA: the original line is for HAM", return_line_violation("SODA", -1, "HAM")
		)
		self.assertIsNone(return_line_violation("SODA", -1, "SODA"))


if __name__ == "__main__":
	unittest.main()
