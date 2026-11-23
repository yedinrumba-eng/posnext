# -*- coding: utf-8 -*-
# Copyright (c) 2020, Youssef Restom and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import cint
from frappe.model.document import Document

from pos_next.price_rules import PRICE_OVERRIDE_ROLES


LOCKED_FIELDS = ("status", "pos_closing_shift")
LOCKED_FIELDS_MESSAGE = "Shift status and its closing link change only through a POS Closing Shift"
OWN_SHIFT_MESSAGE = "You can open a POS Opening Shift only for yourself"


def _blank_if_none(value):
    """Return "" for None and the value untouched otherwise, so 0 and False stay changes."""
    return "" if value is None else value


def changed_locked_fields(before: dict, after: dict) -> list:
    """Return the locked fields whose value differs between the two snapshots."""
    return [f for f in LOCKED_FIELDS if _blank_if_none(before.get(f)) != _blank_if_none(after.get(f))]


def duplicate_modes(rows) -> list:
    """Return the modes of payment listed more than once, each one once, in first-seen order."""
    seen = set()
    dupes = []
    for row in rows:
        mode = row.get("mode_of_payment")
        if not mode:
            continue
        if mode in seen and mode not in dupes:
            dupes.append(mode)
        seen.add(mode)
    return dupes


def shift_owner_violation(shift_user: str, session_user: str, roles: set) -> str | None:
    """Return the error text unless the shift is for the session user or the roles may open for others."""
    if shift_user == session_user or roles & PRICE_OVERRIDE_ROLES:
        return None
    return OWN_SHIFT_MESSAGE


def open_shifts_of(user: str, exclude: str | None = None) -> list:
    """Return the names of the user's submitted Open shifts, read under lock, except `exclude`."""
    # korvex fork: one lock per user serializes opening and reopening (spec 049).
    frappe.db.get_value("User", user, "name", for_update=True)
    return (
        frappe.db.get_values(
            "POS Opening Shift",
            {"user": user, "docstatus": 1, "status": "Open", "name": ["!=", exclude or ""]},
            "name",
            for_update=True,
            pluck=True,
        )
        or []
    )


class POSOpeningShift(Document):
    def validate(self):
        # korvex fork: the closing link is written only by the close, never through validate (spec 042).
        self.pos_closing_shift = ""
        self.validate_pos_profile_and_cashier()
        dupes = duplicate_modes(self.get("balance_details") or [])
        if dupes:
            frappe.throw(
                _("Mode of payment {0} is listed twice in the opening balance").format(
                    ", ".join(str(m) for m in dupes)
                ),
                title=_("Opening check"),
            )
        # korvex fork: one open shift per cashier on every route, read under lock (specs 042, 049).
        if self.docstatus == 1 and open_shifts_of(self.user, self.name):
            frappe.throw(
                _("This cashier already has an open POS Opening Shift. Close it before opening another"),
                title=_("Opening check"),
            )
        self.set_status()

    def before_update_after_submit(self):
        if self.flags.get("from_closing_shift"):
            return
        before = self.get_doc_before_save()
        if before is None:
            frappe.throw(_(LOCKED_FIELDS_MESSAGE), frappe.PermissionError)
        changed = changed_locked_fields(before.as_dict(), self.as_dict())
        if changed:
            frappe.throw(_(LOCKED_FIELDS_MESSAGE), frappe.PermissionError)

    def validate_pos_profile_and_cashier(self):
        if self.company != frappe.db.get_value("POS Profile", self.pos_profile, "company"):
            frappe.throw(
                _("POS Profile {} does not belongs to company {}".format(self.pos_profile, self.company))
            )

        if not cint(frappe.db.get_value("User", self.user, "enabled")):
            frappe.throw(_("User {} has been disabled. Please select valid user/cashier".format(self.user)))

        if not frappe.has_permission("POS Profile", "read", doc=self.pos_profile, user=self.user):
            frappe.throw(
                _("User {0} cannot use POS Profile {1}").format(self.user, self.pos_profile),
                frappe.PermissionError,
            )

        error = shift_owner_violation(self.user, frappe.session.user, set(frappe.get_roles()))
        if error:
            frappe.throw(_(error), frappe.PermissionError)

    def on_submit(self):
        self.set_status(update=True)

    def set_status(self, update=False):
        """Set the status of the opening shift"""
        if self.docstatus == 0:
            status = "Draft"
        elif self.docstatus == 1:
            if self.pos_closing_shift:
                status = "Closed"
            else:
                status = "Open"
        else:
            status = "Cancelled"

        if update:
            frappe.db.set_value("POS Opening Shift", self.name, "status", status)
        else:
            self.status = status
