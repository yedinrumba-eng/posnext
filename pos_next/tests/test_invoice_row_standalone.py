"""S10.3 - D31.49 / D31.55 on a real bench: loose Sales Invoice rows and update-after-submit.

Bench only (IntegrationTestCase); not part of the pure local suites.
"""

import frappe
from frappe.tests import IntegrationTestCase

from pos_next.api import invoice_row_guard

ROWS = (
	("Sales Invoice Item", "items"),
	("Sales Invoice Payment", "payments"),
	("Sales Taxes and Charges", "taxes"),
)


class TestInvoiceRowStandalone(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.user = f"_test_rowguard_{frappe.generate_hash(length=8)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": self.user,
				"first_name": "Row Guard",
				"send_welcome_email": 0,
				"roles": [{"role": "Accounts User"}],
			}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		if frappe.db.exists("User", self.user):
			frappe.delete_doc("User", self.user, force=True)

	def test_1_a_loose_invoice_row_is_rejected(self):
		for doctype, field in ROWS:
			with self.subTest(doctype=doctype):
				frappe.set_user(self.user)
				row = frappe.get_doc(
					{
						"doctype": doctype,
						"parenttype": "Sales Invoice",
						"parent": "_test_missing_invoice",
						"parentfield": field,
					}
				)
				with self.assertRaises(frappe.PermissionError):
					row.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
				frappe.set_user("Administrator")
				self.assertFalse(frappe.db.exists(doctype, {"parent": "_test_missing_invoice"}))

	def test_2_update_after_submit_needs_the_override_roles(self):
		doc = frappe._dict(doctype="Sales Invoice", name="_test_missing_invoice")
		frappe.set_user(self.user)
		with self.assertRaises(frappe.PermissionError):
			invoice_row_guard.block_update_after_submit(doc)
		frappe.set_user("Administrator")
		invoice_row_guard.block_update_after_submit(doc)
