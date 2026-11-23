"""Nobody but Administrator renames a shift, a sale or their rows (spec 050).
The name is the link between a shift, its closing and its sales; renaming one breaks the others.
"""

import frappe
from frappe import _

from pos_next.api.invoice_row_guard import INVOICE_ROW_DOCTYPES
from pos_next.api.shift_row_guard import SHIFT_ROW_DOCTYPES

RENAME_LOCKED_DOCTYPES = (
	"POS Opening Shift",
	"POS Closing Shift",
	"Sales Invoice",
	*INVOICE_ROW_DOCTYPES,
	*SHIFT_ROW_DOCTYPES,
)


def _actor() -> str:
	return frappe.session.user


def block_rename(doc, method=None, old=None, new=None, merge=False) -> None:
	"""before_rename of every doctype: frappe calls f(doc, method, old, new, merge)."""
	if doc.doctype not in RENAME_LOCKED_DOCTYPES or _actor() == "Administrator":
		return
	frappe.throw(
		_("{0} {1} cannot be renamed").format(doc.doctype, old or doc.name), frappe.PermissionError
	)
