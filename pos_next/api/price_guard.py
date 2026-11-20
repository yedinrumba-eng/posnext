# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Server-side price, tax, payment and return enforcement for Sales Invoices.

enforce_pos_prices runs in before_validate, before ERPNext computes totals: for users without
the Dueño or System Manager role the client's rate, tax rows, UOM factor and write-off are thrown
away and rebuilt from the POS Profile. enforce_full_payment runs in before_submit. The rules
live in pos_next.price_rules; the helpers with a "_" prefix are the only ones that touch the DB.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from pos_next.price_rules import (
	HAS_ACTUAL_TAX_MESSAGE,
	PRICE_OVERRIDE_ROLES,
	OriginalInvoice,
	access_violation,
	currency_violation,
	expected_unit_price,
	invoice_discount_violation,
	line_violation,
	payment_violation,
	return_line_violation,
	return_violation,
	tender_violation,
	uom_factor,
)

_RETURN_ROW_FIELDS = (
	"uom",
	"conversion_factor",
	"stock_uom",
	"price_list_rate",
	"discount_percentage",
	"discount_amount",
	"rate",
	"margin_type",
	"margin_rate_or_amount",
	"item_tax_template",
	"item_tax_rate",
	"warehouse",
	"income_account",
	"expense_account",
	"cost_center",
	"mapped_additional_discount_amount",
	"distributed_discount_amount",
)

_RETURN_HEADER_FIELDS = ("taxes_and_charges", "tax_category", "debit_to", "cost_center", "set_warehouse")

_SALE_ROW_CLEARED = (
	"income_account",
	"expense_account",
	"cost_center",
	"target_warehouse",
	"sales_order",
	"so_detail",
	"delivery_note",
	"dn_detail",
)

_SALE_ROW_ZEROED = (
	"allow_zero_valuation_rate",
	"delivered_by_supplier",
	"enable_deferred_revenue",
	"mapped_additional_discount_amount",
	"distributed_discount_amount",
)

_RETURN_TAX_FIELDS = (
	"charge_type",
	"account_head",
	"description",
	"rate",
	"cost_center",
	"included_in_print_rate",
	"row_id",
)


def enforce_pos_prices(doc, method=None):
	"""before_validate hook for Sales Invoice: the server decides price, tax, UOM and returns."""
	if doc.doctype != "Sales Invoice":
		return

	if _is_override():
		_check_owner_return(doc)
		return

	profile = _profile(doc.pos_profile)
	error = access_violation(
		bool(cint(doc.is_pos)),
		doc.pos_profile or "",
		profile,
		_is_profile_user(doc.pos_profile),
		doc.company,
	)
	if error:
		frappe.throw(error, title=_("POS check"))

	settings = _settings(doc.pos_profile)
	if _guard_off(settings):
		return

	doc.write_off_amount = 0
	doc.base_write_off_amount = 0
	doc.write_off_outstanding_amount_automatically = 0

	if cint(doc.is_return):
		_enforce_return(doc, profile, settings)
	else:
		_enforce_sale(doc, profile, settings)


def enforce_full_payment(doc, method=None):
	"""before_submit hook for Sales Invoice: the payment must cover the total unless credit is allowed."""
	if doc.doctype != "Sales Invoice" or cint(doc.is_return):
		return

	settings = _settings(doc.pos_profile)
	if _guard_off(settings):
		return

	due = flt(doc.get("rounded_total")) or flt(doc.grand_total)
	rows = doc.get("payments") or []
	types = _mode_of_payment_types(sorted({r.mode_of_payment for r in rows if r.mode_of_payment}))
	cash = [flt(r.amount) for r in rows if types.get(r.mode_of_payment) == "Cash"]
	non_cash = [flt(r.amount) for r in rows if types.get(r.mode_of_payment) != "Cash"]
	error = tender_violation(cash, non_cash, due, flt(doc.get("change_amount")))
	if error:
		frappe.throw(error, title=_("Payment check"))

	if _is_override():
		return

	error = invoice_discount_violation(
		flt(doc.additional_discount_percentage),
		flt(doc.discount_amount),
		flt(doc.total),
		_flag(settings, "allow_user_to_edit_additional_discount"),
		flt(settings.get("max_discount_allowed")) if settings else 0.0,
		False,
	)
	if error:
		frappe.throw(error, title=_("Price check"))

	error = payment_violation(
		[flt(row.amount) for row in doc.get("payments") or []],
		due,
		_flag(settings, "allow_partial_payment"),
		_flag(settings, "allow_credit_sale"),
	)
	if error:
		frappe.throw(error, title=_("Payment check"))


def require_pos_flag(pos_profile, flags):
	"""Gate for endpoints that move money without a permission check: profile user and a flag on."""
	if _is_override():
		return
	if not _is_profile_user(pos_profile):
		frappe.throw(
			_("You are not a user of POS Profile {0}").format(pos_profile or ""),
			frappe.PermissionError,
		)
	settings = _settings(pos_profile)
	if settings is None or not any(cint(settings.get(flag)) == 1 for flag in flags):
		frappe.throw(
			_("{0} is off for POS Profile {1}").format(" / ".join(flags), pos_profile),
			frappe.PermissionError,
		)


def _enforce_header(doc, profile, settings, original):
	"""Currency, loyalty, switches and payment rows: what the client sends there never reaches the ledger."""
	company_currency = _company_currency(doc.company)
	error = currency_violation(
		company_currency,
		profile.get("currency") or "",
		_price_list_currency(profile["selling_price_list"]) or "",
		original.currency if original is not None else None,
	)
	if error:
		frappe.throw(error, title=_("POS check"))

	if _is_internal_customer(doc.customer):
		frappe.throw(_("Internal customers are not allowed for this user"), title=_("POS check"))

	doc.currency = company_currency
	doc.conversion_rate = 1
	doc.price_list_currency = company_currency
	doc.plc_conversion_rate = 1

	doc.is_consolidated = 0
	doc.redeem_loyalty_points = 0
	doc.loyalty_points = 0
	doc.loyalty_amount = 0

	doc.apply_tds = 0
	doc.override_tax_withholding_entries = 0
	doc.tax_withholding_group = None
	doc.set("tax_withholding_entries", [])
	for row in doc.get("items") or []:
		row.apply_tds = 0
		row.tax_withholding_category = None

	doc.ignore_pricing_rule = 1
	rounded = settings.get("disable_rounded_total") if settings else None
	doc.disable_rounded_total = cint(rounded) if rounded is not None else 1
	doc.update_stock = 1
	doc.is_opening = "No"
	if not _flag(settings, "allow_change_posting_date"):
		doc.set_posting_time = 0

	_enforce_payment_rows(doc)


def _enforce_payment_rows(doc):
	rows = [row for row in doc.get("payments") or [] if row.mode_of_payment]
	modes = _profile_payment_modes(doc.pos_profile)
	accounts = _mode_of_payment_accounts(doc.company, sorted({row.mode_of_payment for row in rows}))
	is_return = bool(cint(doc.is_return))

	errors = []
	for row in rows:
		mode = row.mode_of_payment
		if mode not in modes:
			errors.append(f"Mode of payment {mode} is not set up in POS Profile {doc.pos_profile}")
		elif is_return and not modes[mode]:
			errors.append(
				f"Mode of payment {mode} is not allowed in returns for POS Profile {doc.pos_profile}"
			)
		elif mode not in accounts:
			errors.append(f"Mode of payment {mode} has no account for company {doc.company}")
		else:
			row.account = accounts[mode]

	if errors:
		frappe.throw("<br>".join(errors), title=_("Payment check"))


def _enforce_sale(doc, profile, settings):
	_enforce_header(doc, profile, settings, None)

	items = doc.get("items") or []
	codes = sorted({row.item_code for row in items if row.item_code})

	prices = _load_prices(profile["selling_price_list"], codes)
	stock_uoms = _load_stock_uoms(codes)
	conversions = _load_uom_conversions(codes)
	allow_item_discount = _flag(settings, "allow_user_to_edit_item_discount")
	allow_additional = _flag(settings, "allow_user_to_edit_additional_discount")
	max_discount = flt(settings.get("max_discount_allowed")) if settings else 0.0

	doc.selling_price_list = profile["selling_price_list"]
	doc.taxes_and_charges = profile["taxes_and_charges"] or _default_tax_template(doc.company) or ""
	doc.set("taxes", [])
	if doc.taxes_and_charges:
		doc.append_taxes_from_master("Sales Taxes and Charges Template")
	doc.tax_category = profile.get("tax_category") or ""

	doc.debit_to = ""
	doc.cost_center = ""
	doc.account_for_change_amount = ""
	doc.set_warehouse = profile["warehouse"]
	doc.set_target_warehouse = ""
	doc.is_debit_note = 0
	doc.allocate_advances_automatically = 0
	doc.set("advances", [])

	errors = []
	base_total = 0.0
	for row in items:
		row.item_tax_template = None
		row.item_tax_rate = None
		row.warehouse = profile["warehouse"]
		for field in _SALE_ROW_CLEARED:
			setattr(row, field, None)
		for field in _SALE_ROW_ZEROED:
			setattr(row, field, 0)

		stock_uom = stock_uoms.get(row.item_code) or ""
		row.stock_uom = stock_uom
		uom = row.uom or stock_uom
		factor = uom_factor(uom, stock_uom, conversions.get(row.item_code, {}))
		if factor is None:
			errors.append(f"{row.item_code}: UOM {uom} is not set up for this item")
			continue
		row.uom = uom
		row.conversion_factor = factor

		if flt(row.qty) <= 0:
			errors.append(f"{row.item_code}: quantity must be greater than zero")
			continue

		expected = expected_unit_price(prices.get(row.item_code, {}), uom, stock_uom, factor)
		pct = flt(row.discount_percentage)

		error = line_violation(row.item_code, expected, pct, allow_item_discount, max_discount, False)
		if error:
			errors.append(error)

		if expected is not None:
			row.price_list_rate = expected
			row.rate = 0
			row.discount_amount = 0
			row.margin_type = ""
			row.margin_rate_or_amount = 0
			base_total += flt(row.qty) * expected * (1 - pct / 100)

	error = invoice_discount_violation(
		flt(doc.get("additional_discount_percentage")),
		flt(doc.get("discount_amount")),
		base_total,
		allow_additional,
		max_discount,
		False,
	)
	if error:
		errors.append(error)

	if errors:
		frappe.throw("<br>".join(errors), title=_("Price check"))


def _enforce_return(doc, profile, settings):
	original = _original_invoice(doc.return_against)
	facts = None
	if original is not None:
		facts = OriginalInvoice(
			docstatus=original.docstatus,
			is_return=bool(original.is_return),
			company=original.company,
			has_actual_tax=_has_actual_tax(original),
			discount_amount=flt(original.discount_amount),
		)
	error = return_violation(
		doc.return_against or "", _flag(settings, "allow_return"), facts, doc.company
	)
	if error:
		frappe.throw(error, title=_("Return check"))

	_enforce_header(doc, profile, settings, original)

	original_rows = {row.name: row for row in original.items}
	errors = []
	for row in doc.get("items") or []:
		original_row = original_rows.get(row.sales_invoice_item)
		error = return_line_violation(
			row.item_code, flt(row.qty), original_row.item_code if original_row else None
		)
		if error:
			errors.append(error)
			continue
		for field in _RETURN_ROW_FIELDS:
			setattr(row, field, original_row.get(field))

	if errors:
		frappe.throw("<br>".join(errors), title=_("Return check"))

	for field in _RETURN_HEADER_FIELDS:
		setattr(doc, field, original.get(field))
	doc.set("taxes", [])
	for tax in original.taxes:
		doc.append("taxes", {field: tax.get(field) for field in _RETURN_TAX_FIELDS})
	doc.additional_discount_percentage = 0
	doc.discount_amount = 0


def _check_owner_return(doc):
	"""An owner return that comes through the POS API cannot refund a tax that was never charged."""
	if not cint(doc.is_return) or not doc.flags.get("pos_next_api"):
		return
	original = _original_invoice(doc.return_against)
	if original is not None and _has_actual_tax(original):
		frappe.throw(HAS_ACTUAL_TAX_MESSAGE.format(doc.return_against), title=_("Return check"))


def _has_actual_tax(original):
	return any(tax.charge_type == "Actual" for tax in original.taxes)


def _flag(settings, name):
	"""A POS Settings flag as a bool; no settings record means off."""
	return bool(cint(settings.get(name))) if settings else False


def _guard_off(settings):
	"""True only when the profile's POS Settings explicitly turn the guard off (absent or NULL = on)."""
	if settings is None:
		return False
	value = settings.get("enforce_server_guard")
	return value is not None and cint(value) == 0


def _is_override():
	return bool(PRICE_OVERRIDE_ROLES & set(frappe.get_roles()))


def _is_profile_user(pos_profile):
	return bool(pos_profile) and bool(
		frappe.db.exists(
			"POS Profile User",
			{"parent": pos_profile, "parenttype": "POS Profile", "user": frappe.session.user},
		)
	)


def _profile(pos_profile):
	if not pos_profile:
		return None
	return frappe.db.get_value(
		"POS Profile",
		pos_profile,
		[
			"company",
			"disabled",
			"selling_price_list",
			"taxes_and_charges",
			"currency",
			"tax_category",
			"warehouse",
		],
		as_dict=True,
	)


def _settings(pos_profile):
	"""Enabled POS Settings of the profile (the record the POS itself loads), or None."""
	fields = [
		"allow_user_to_edit_item_discount",
		"allow_user_to_edit_additional_discount",
		"max_discount_allowed",
		"allow_partial_payment",
		"allow_credit_sale",
		"allow_return",
		"disable_rounded_total",
		"allow_change_posting_date",
	]
	if frappe.get_meta("POS Settings").has_field("enforce_server_guard"):
		fields.append("enforce_server_guard")
	return frappe.db.get_value(
		"POS Settings", {"pos_profile": pos_profile, "enabled": 1}, fields, as_dict=True
	)


def _company_currency(company):
	return frappe.get_cached_value("Company", company, "default_currency")


def _price_list_currency(price_list):
	if not price_list:
		return None
	return frappe.db.get_value("Price List", price_list, "currency")


def _is_internal_customer(customer):
	return bool(customer) and bool(cint(frappe.db.get_value("Customer", customer, "is_internal_customer")))


def _profile_payment_modes(pos_profile):
	"""{mode_of_payment: allowed in returns} of the POS Profile."""
	rows = frappe.get_all(
		"POS Payment Method",
		filters={"parent": pos_profile, "parenttype": "POS Profile"},
		fields=["mode_of_payment", "allow_in_returns"],
	)
	return {row.mode_of_payment: bool(cint(row.allow_in_returns)) for row in rows}


def _mode_of_payment_accounts(company, modes):
	"""{mode_of_payment: default_account} for the company; modes without an account are left out."""
	if not modes:
		return {}
	rows = frappe.get_all(
		"Mode of Payment Account",
		filters={"parent": ["in", modes], "company": company},
		fields=["parent", "default_account"],
	)
	return {row.parent: row.default_account for row in rows if row.default_account}


def _mode_of_payment_types(modes):
	"""{mode_of_payment: type} read from the database; the client's row type is never used."""
	if not modes:
		return {}
	rows = frappe.get_all("Mode of Payment", filters={"name": ["in", modes]}, fields=["name", "type"])
	return {row.name: row.type for row in rows}


def _default_tax_template(company):
	return frappe.db.get_value(
		"Sales Taxes and Charges Template", {"is_default": 1, "company": company}, "name"
	)


def _original_invoice(name):
	if name and frappe.db.exists("Sales Invoice", name):
		return frappe.get_doc("Sales Invoice", name)
	return None


def _load_prices(price_list, codes):
	"""{item_code: {uom or "": price_list_rate}}; the latest Item Price per uom wins."""
	prices = {}
	if not price_list or not codes:
		return prices
	rows = frappe.get_all(
		"Item Price",
		filters={"price_list": price_list, "item_code": ["in", codes]},
		fields=["item_code", "uom", "price_list_rate"],
		order_by="creation asc",
	)
	for row in rows:
		prices.setdefault(row.item_code, {})[row.uom or ""] = flt(row.price_list_rate)
	return prices


def _load_stock_uoms(codes):
	if not codes:
		return {}
	rows = frappe.get_all("Item", filters={"name": ["in", codes]}, fields=["name", "stock_uom"])
	return {row.name: row.stock_uom for row in rows}


def _load_uom_conversions(codes):
	"""{item_code: {uom: conversion_factor}} from the Item's UOM table."""
	conversions = {}
	if not codes:
		return conversions
	rows = frappe.get_all(
		"UOM Conversion Detail",
		filters={"parenttype": "Item", "parent": ["in", codes]},
		fields=["parent", "uom", "conversion_factor"],
	)
	for row in rows:
		conversions.setdefault(row.parent, {})[row.uom] = flt(row.conversion_factor)
	return conversions
