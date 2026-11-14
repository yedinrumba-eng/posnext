# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Allowlist of the document types the POS invoice endpoints may save and submit.

update_invoice and submit_invoice take the doctype from the client and save with
ignore_permissions, so without this list a cashier could create any document (a Journal Entry).
"""

import frappe
from frappe import _
from frappe.utils import cint

ALLOWED_POS_DOCTYPES = frozenset({"Sales Invoice", "Sales Order"})


def check_pos_doctype(doctype, pos_profile):
	"""Throw PermissionError unless the POS may save this doctype for this user and profile."""
	if doctype not in ALLOWED_POS_DOCTYPES:
		frappe.throw(
			_("Document type {0} is not allowed in POS").format(doctype), frappe.PermissionError
		)
	if doctype == "Sales Order" and not (_allow_sales_order(pos_profile) and _can_create_sales_order()):
		frappe.throw(
			_("Sales Orders are not allowed for this user or POS Profile"), frappe.PermissionError
		)


def _allow_sales_order(pos_profile):
	if not pos_profile:
		return False
	return bool(
		cint(
			frappe.db.get_value(
				"POS Settings", {"pos_profile": pos_profile, "enabled": 1}, "allow_sales_order"
			)
		)
	)


def _can_create_sales_order():
	return bool(frappe.has_permission("Sales Order", "create"))
