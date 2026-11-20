# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Pure price and discount rules for POS invoices (pure Python, unit-testable).

The server decides the price: the client's rate is ignored and only an allowed discount
percentage survives. See pos_next.api.price_guard for the hook that applies these rules.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Roles allowed to sell off-list prices and to discount past the POS Settings limits.
PRICE_OVERRIDE_ROLES = frozenset({"Dueño", "System Manager"})

_EPSILON = 1e-6

NON_FINITE_PAYMENT_MESSAGE = "Payment amounts must be finite numbers"


def expected_unit_price(
	prices: Mapping[str, float], uom: str, stock_uom: str, conversion_factor: float
) -> float | None:
	"""Price list rate of one unit in `uom`, or None when the list has no usable price.

	Order: the exact UOM, then the stock UOM price times the conversion factor, then the
	UOM-less price (key "") times the conversion factor.
	"""
	if uom in prices:
		return prices[uom]
	if stock_uom in prices:
		return prices[stock_uom] * conversion_factor
	if "" in prices:
		return prices[""] * conversion_factor
	return None


def line_violation(
	item_code: str,
	expected: float | None,
	discount_percentage: float,
	allow_item_discount: bool,
	max_discount: float,
	override: bool,
) -> str | None:
	"""Why this invoice line is not allowed, or None. `max_discount` 0 means no limit."""
	if discount_percentage < 0 or discount_percentage > 100:
		return f"{item_code}: discount {discount_percentage}% is outside 0-100"
	if expected is None and not override:
		return f"{item_code}: no price in the POS price list"
	if discount_percentage > 0 and not override:
		if not allow_item_discount:
			return f"{item_code}: item discounts are not allowed"
		if max_discount > 0 and discount_percentage > max_discount + _EPSILON:
			return f"{item_code}: discount {discount_percentage}% is over the {max_discount}% limit"
	return None


def invoice_discount_violation(
	additional_pct: float,
	discount_amount: float,
	base_total: float,
	allow_additional: bool,
	max_discount: float,
	override: bool,
) -> str | None:
	"""Why the invoice-level discount is not allowed, or None. `max_discount` 0 means no limit."""
	if override or (additional_pct <= 0 and discount_amount <= 0):
		return None
	if not allow_additional:
		return "Additional discount is not allowed"
	if max_discount > 0:
		if additional_pct > 0:
			pct = additional_pct
		elif base_total <= 0:
			return "Additional discount cannot be checked against an empty total"
		else:
			pct = discount_amount / base_total * 100
		if pct > max_discount + _EPSILON:
			return f"Additional discount {round(pct, 3)}% is over the {max_discount}% limit"
	return None


def uom_factor(uom: str, stock_uom: str, conversions: Mapping[str, float]) -> float | None:
	"""Conversion factor of `uom` to the stock UOM, or None when the Item has no such UOM."""
	if uom == stock_uom:
		return 1.0
	if conversions.get(uom, 0) > 0:
		return conversions[uom]
	return None


def access_violation(
	is_pos: bool,
	pos_profile: str,
	profile: Mapping | None,
	is_profile_user: bool,
	company: str,
) -> str | None:
	"""Why this user may not save this invoice under this POS Profile, or None. First failure wins."""
	if not is_pos:
		return "Only POS sales are allowed for this user"
	if not pos_profile:
		return "POS Profile is required"
	if profile is None:
		return f"POS Profile {pos_profile} does not exist"
	if profile["disabled"]:
		return f"POS Profile {pos_profile} is disabled"
	if not is_profile_user:
		return f"You are not a user of POS Profile {pos_profile}"
	if profile["company"] != company:
		return f"POS Profile {pos_profile} belongs to another company"
	return None


def currency_violation(
	company_currency: str,
	profile_currency: str,
	price_list_currency: str,
	original_currency: str | None,
) -> str | None:
	"""Why the invoice cannot be booked in the company currency, or None. First failure wins."""
	if profile_currency and profile_currency != company_currency:
		return f"POS Profile currency {profile_currency} is not the company currency {company_currency}"
	if price_list_currency and price_list_currency != company_currency:
		return (
			f"Price list currency {price_list_currency} is not the company currency {company_currency}"
		)
	if original_currency is not None and original_currency != company_currency:
		return (
			f"Original invoice currency {original_currency} is not the company currency "
			f"{company_currency}: the owner returns it from Desk"
		)
	return None


def payment_violation(
	payments: Sequence[float], due: float, allow_partial: bool, allow_credit: bool
) -> str | None:
	"""Why the payment rows do not cover the invoice, or None. Either flag allows a short payment."""
	if not all(math.isfinite(amount) for amount in [*payments, due]):
		return NON_FINITE_PAYMENT_MESSAGE
	if any(amount < 0 for amount in payments):
		return "Payment amounts cannot be negative on a sale"
	if allow_partial or allow_credit:
		return None
	paid = sum(payments)
	if paid < due - 0.005:
		return f"Payment {paid:.2f} is less than the invoice total {due:.2f}"
	return None


def tender_violation(
	cash: Sequence[float], non_cash: Sequence[float], due: float, change: float
) -> str | None:
	"""Why this split of cash and non-cash tender is not allowed, or None. First failure wins."""
	if not all(math.isfinite(value) for value in [*cash, *non_cash, due, change]):
		return NON_FINITE_PAYMENT_MESSAGE
	if sum(non_cash) > due + 0.005:
		return (
			f"Card and other non-cash payments {sum(non_cash):.2f} are more than the invoice total "
			f"{due:.2f}"
		)
	if change > sum(cash) + 0.005:
		return f"Change {change:.2f} is more than the cash received {sum(cash):.2f}"
	return None


HAS_ACTUAL_TAX_MESSAGE = (
	"Invoice {0} has a SNAP tax exemption or another fixed tax row: the owner returns it from Desk"
)


@dataclass(frozen=True, slots=True)
class OriginalInvoice:
	"""The facts about the invoice being returned that the return rules need."""

	docstatus: int
	is_return: bool
	company: str
	has_actual_tax: bool
	discount_amount: float


def return_violation(
	return_against: str, allow_return: bool, original: OriginalInvoice | None, company: str
) -> str | None:
	"""Why this return is not allowed for the cashier, or None. First failure wins."""
	if not return_against:
		return "A return needs the original invoice (return_against)"
	if not allow_return:
		return "Returns are not allowed for this POS Profile"
	if original is None:
		return f"Original invoice {return_against} does not exist"
	if original.docstatus != 1 or original.is_return:
		return f"Original invoice {return_against} is not a submitted sale"
	if original.company != company:
		return f"Original invoice {return_against} belongs to another company"
	if original.has_actual_tax:
		return HAS_ACTUAL_TAX_MESSAGE.format(return_against)
	if original.discount_amount > 0:
		return f"Invoice {return_against} has an invoice discount: the owner returns it from Desk"
	return None


def return_line_violation(item_code: str, qty: float, original_item_code: str | None) -> str | None:
	"""Why this return line is not allowed, or None."""
	if qty >= 0:
		return f"{item_code}: a return line needs a negative quantity"
	if original_item_code is None:
		return f"{item_code}: the line is not on the original invoice"
	if original_item_code != item_code:
		return f"{item_code}: the original line is for {original_item_code}"
	return None
