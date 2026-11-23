# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Sales Invoice Override
Handles wallet payments that require party information for Receivable accounts.

"""

import frappe
from frappe.utils import cint, flt
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.accounts.utils import get_account_currency
from pos_next.price_rules import PRICE_OVERRIDE_ROLES

SHIFT_MISSING_MESSAGE = "POS sales and returns need an open POS Opening Shift"


def subtract_change_once(payments, account, change: float, precision: int) -> None:
	"""Take the change off the rows paid into `account`, last row first, exactly once, rounded to precision."""
	matching = [row for row in payments if row.account == account]
	if change <= 0 or not matching:
		return
	remaining = flt(change, precision)
	for row in reversed(matching):
		take = min(remaining, max(flt(row.base_amount), 0.0))
		row.base_amount = flt(flt(row.base_amount) - take, precision)
		remaining = flt(remaining - take, precision)
	if remaining > 0:
		matching[-1].base_amount = flt(matching[-1].base_amount - remaining, precision)


def sale_shift_violation(
	shift: dict | None,
	session_user: str,
	roles: set,
	pos_profile: str,
	company: str,
	in_close: bool,
	can_read_shift: bool,
) -> str | None:
	"""Return why a POS sale cannot use this shift, or None when it can."""
	if "System Manager" in roles:
		return None
	if not shift:
		return SHIFT_MISSING_MESSAGE
	name = shift["name"]
	if cint(shift["docstatus"]) != 1 or shift["status"] != "Open":
		return f"POS Opening Shift {name} is not open. Open a shift and try again"
	if shift["pos_profile"] != pos_profile or shift["company"] != company:
		return f"POS Opening Shift {name} belongs to another POS Profile or Company"
	if shift["user"] != session_user and not (in_close and roles & PRICE_OVERRIDE_ROLES and can_read_shift):
		return f"POS Opening Shift {name} belongs to another user"
	return None


def offline_sale_shift(
	name: str | None,
	shift: dict | None,
	session_user: str,
	pos_profile: str,
	open_shift: str | None,
) -> str | None:
	"""Return the open shift a late offline sale joins, or its own shift when it cannot move."""
	if (
		shift
		and shift["status"] == "Closed"
		and shift["user"] == session_user
		and shift["pos_profile"] == pos_profile
		and open_shift is not None
	):
		return open_shift
	return name


def _shift_row(name: str | None, for_update: bool = False) -> dict | None:
	"""Read the POS Opening Shift fields the sale rule needs; lock the row when for_update."""
	if not name:
		return None
	return frappe.db.get_value(
		"POS Opening Shift",
		name,
		["name", "user", "status", "docstatus", "pos_profile", "company"],
		as_dict=True,
		for_update=for_update,
	)


def resolve_offline_shift(name: str | None, pos_profile: str) -> str | None:
	"""Move a sale whose shift is closed to the open shift of the same cashier, if there is one."""
	shift = _shift_row(name)
	open_shift = None
	if shift and shift["status"] == "Closed":
		found = frappe.get_list(
			"POS Opening Shift",
			filters={
				"user": frappe.session.user,
				"pos_profile": pos_profile,
				"company": shift["company"],
				"docstatus": 1,
				"status": "Open",
			},
			pluck="name",
			order_by="period_start_date desc",
			limit_page_length=1,
		)
		open_shift = found[0] if found else None
	return offline_sale_shift(name, shift, frappe.session.user, pos_profile, open_shift)


class CustomSalesInvoice(SalesInvoice):
	"""
	Custom Sales Invoice class that handles wallet payments correctly.

	When a wallet payment is made using a Receivable account, ERPNext requires
	party information in the GL entry. This override adds party_type and party
	for wallet payment methods marked with is_wallet_payment.
	"""

	def validate(self):
		self.enforce_pos_shift()
		super().validate()

	def enforce_pos_shift(self):
		"""Reject a POS sale or return without an open shift of the user who rings it."""
		if not cint(self.is_pos):
			# korvex fork: a shift counts POS money only (spec 047).
			if self.get("posa_pos_opening_shift"):
				frappe.throw(
					frappe._("Only POS sales and returns carry a POS Opening Shift"),
					title=frappe._("Shift check"),
				)
			return
		name = self.get("posa_pos_opening_shift")
		# korvex fork: hold the shift row until this sale commits; a close waits for it (spec 047).
		shift = _shift_row(name, for_update=True)
		user = frappe.session.user
		can_read = bool(
			shift and shift["user"] != user and frappe.has_permission("POS Opening Shift", "read", doc=name)
		)
		error = sale_shift_violation(
			shift,
			user,
			set(frappe.get_roles()),
			self.pos_profile,
			self.company,
			bool(self.flags.get("from_closing_shift")),
			can_read,
		)
		if error:
			frappe.throw(frappe._(error), title=frappe._("Shift check"))

	def make_pos_gl_entries(self, gl_entries):
		"""
		Override to add party information for wallet payment accounts.

		The standard ERPNext implementation doesn't set party_type/party for
		payment mode accounts, which causes validation errors for Receivable
		accounts (like wallet accounts).
		"""
		if cint(self.is_pos):
			# korvex fork fix: ERPNext v16 moved this field from Accounts
			# Settings to POS Settings (patches.v16_0.
			# set_post_change_gl_entries_on_pos_settings); this override
			# still read the old location, which raised ValidationError
			# on every POS Sales Invoice submit under v16.
			skip_change_gl_entries = not cint(
				frappe.db.get_single_value("POS Settings", "post_change_gl_entries")
			)

			# korvex fork fix: one row per tap; the change leaves the drawer once (spec 034).
			precision = self.precision("base_amount", "payments")
			if skip_change_gl_entries:
				subtract_change_once(
					self.payments, self.account_for_change_amount, flt(self.change_amount), precision
				)

			for payment_mode in self.payments:
				if flt(payment_mode.base_amount, precision):
					# POS, make payment entries
					# Credit entry to debit_to (customer receivable)
					gl_entries.append(
						self.get_gl_dict(
							{
								"account": self.debit_to,
								"party_type": "Customer",
								"party": self.customer,
								"against": payment_mode.account,
								"credit": payment_mode.base_amount,
								"credit_in_account_currency": payment_mode.base_amount
								if self.party_account_currency == self.company_currency
								else payment_mode.amount,
								"against_voucher": self.return_against
								if cint(self.is_return) and self.return_against
								else self.name,
								"against_voucher_type": self.doctype,
								"cost_center": self.cost_center,
							},
							self.party_account_currency,
							item=self,
						)
					)

					# Debit entry to payment mode account
					payment_mode_account_currency = get_account_currency(payment_mode.account)

					# Get party info for wallet payments
					party_type, party = self.get_party_and_party_type_for_pos_gl_entry(
						payment_mode.mode_of_payment, payment_mode.account
					)

					gl_entries.append(
						self.get_gl_dict(
							{
								"account": payment_mode.account,
								"party_type": party_type,
								"party": party,
								"against": self.customer,
								"debit": payment_mode.base_amount,
								"debit_in_account_currency": payment_mode.base_amount
								if payment_mode_account_currency == self.company_currency
								else payment_mode.amount,
								"cost_center": self.cost_center,
							},
							payment_mode_account_currency,
							item=self,
						)
					)

			if not skip_change_gl_entries:
				self.make_gle_for_change_amount(gl_entries)

	def get_party_and_party_type_for_pos_gl_entry(self, mode_of_payment, account):
		"""
		Get party type and party for wallet payment GL entries.

		For wallet payments (Mode of Payment with is_wallet_payment=1),
		returns Customer as party_type and the invoice customer as party.
		For regular payments, returns empty strings.
		"""
		is_wallet_mode_of_payment = frappe.db.get_value(
			"Mode of Payment", mode_of_payment, "is_wallet_payment"
		)

		party_type, party = "", ""
		if is_wallet_mode_of_payment:
			party_type, party = "Customer", self.customer

		return party_type, party
