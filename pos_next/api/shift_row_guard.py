# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Guard for the rows of a POS Opening Shift or POS Closing Shift saved on their own.

block_standalone_shift_row: a row of a POS Opening Shift or POS Closing Shift is saved only with its
shift. When the parent is saved frappe writes the rows with db_insert/db_update and never runs their
hooks, so these hooks only fire on a loose operation (POST/PUT/DELETE on the child doctype).
"""

import frappe
from frappe import _

SHIFT_ROW_DOCTYPES = (
	"POS Opening Shift Detail",
	"POS Closing Shift Detail",
	"POS Closing Shift Taxes",
	"Sales Invoice Reference",
	"POS Payment Entry Reference",
)
SHIFT_PARENTS = ("POS Opening Shift", "POS Closing Shift")


def block_standalone_shift_row(doc, method=None) -> None:
	"""before_insert / before_validate / before_update_after_submit / on_trash of the shift child doctypes."""
	if doc.get("parenttype") not in SHIFT_PARENTS:
		return
	if _actor() == "Administrator":
		return
	frappe.throw(
		_("Rows of {0} {1} are saved only with the shift").format(doc.get("parenttype"), doc.get("parent") or ""),
		frappe.PermissionError,
	)


def _actor() -> str:
	return frappe.session.user
