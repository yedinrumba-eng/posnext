# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Guards for Sales Invoice rows saved on their own and for submitted Sales Invoices.

block_standalone_invoice_row: a row of Sales Invoice (item, payment, tax) is saved only together with
its invoice. When the parent is saved frappe writes the rows with db_insert/db_update and never runs
their hooks, so these hooks only fire on a loose operation (POST/PUT/DELETE on the child doctype).

block_update_after_submit: a submitted Sales Invoice is changed only by the Dueño or a System Manager.
"""

import frappe
from frappe import _

from pos_next.price_rules import PRICE_OVERRIDE_ROLES

INVOICE_ROW_DOCTYPES = ("Sales Invoice Item", "Sales Invoice Payment", "Sales Taxes and Charges")


def block_standalone_invoice_row(doc, method=None) -> None:
	"""before_insert / before_validate / before_submit / before_cancel / before_update_after_submit / on_trash of the child doctypes."""
	if _actor() == "Administrator":
		return
	if canonical_parenttype(doc) != "Sales Invoice":
		return
	frappe.throw(
		_("Rows of Sales Invoice {0} are saved only with the invoice").format(doc.get("parent") or ""),
		frappe.PermissionError,
	)


def canonical_parenttype(doc) -> str:
	"""Name of the DocType the row's parenttype resolves to as the database sees it, or "" if none."""
	parenttype = doc.get("parenttype")
	if parenttype is None or parenttype == "":
		return ""
	if not isinstance(parenttype, str):
		frappe.throw(_("Row parenttype must be text"), frappe.PermissionError)
	try:
		return frappe.get_meta(parenttype).name
	except frappe.DoesNotExistError:
		return ""


def block_update_after_submit(doc, method=None) -> None:
	"""before_update_after_submit of Sales Invoice: only the Dueño or a System Manager."""
	if doc.doctype != "Sales Invoice":
		return
	if _is_override():
		return
	frappe.throw(
		_("Submitted Sales Invoice {0} can only be changed by the Dueño or a System Manager").format(
			doc.name
		),
		frappe.PermissionError,
	)


def _actor() -> str:
	return frappe.session.user


def _is_override() -> bool:
	return bool(PRICE_OVERRIDE_ROLES & set(frappe.get_roles()))
