"""Keep the payments the cashier requested through ERPNext set_missing_values().
Only mode and amount come from the client; account, type and default come from the POS Profile."""

import frappe
from frappe import _
from frappe.utils import flt


def requested_payments(rows) -> list[dict]:
	"""Return the cashier's payment rows as plain {mode_of_payment, amount} dicts, in order."""
	return [
		{"mode_of_payment": row.get("mode_of_payment"), "amount": flt(row.get("amount"))}
		for row in (rows or [])
		if row.get("mode_of_payment")
	]


def restore_requested_payments(doc, requested: list[dict]) -> None:
	"""Replace the profile rows ERPNext just rebuilt with the requested amounts."""
	if not requested:
		return

	templates = {}
	for row in doc.get("payments") or []:
		templates.setdefault(row.get("mode_of_payment"), row)

	missing = []
	for item in requested:
		mode = item["mode_of_payment"]
		if mode not in templates and mode not in missing:
			missing.append(mode)
	if missing:
		frappe.throw(
			_("Mode of payment {0} is not set up in POS Profile {1}").format(
				", ".join(missing), doc.pos_profile
			),
			title=_("Payment check"),
		)

	doc.set("payments", [])
	for item in requested:
		template = templates[item["mode_of_payment"]]
		doc.append(
			"payments",
			{
				"mode_of_payment": item["mode_of_payment"],
				"amount": item["amount"],
				"account": template.get("account"),
				"type": template.get("type"),
				"default": template.get("default"),
			},
		)
