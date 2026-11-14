"""S10.10 - the POS invoice endpoints only accept Sales Invoice and (with permission) Sales Order.

frappe is stubbed; the two DB-facing helpers and frappe.throw are patched. The last test reads
invoices.py with ``ast`` to prove the check runs before anything is loaded or saved.
"""

import ast
import importlib
import unittest
from pathlib import Path
from unittest import mock

from pos_next.tests import frappe_stub

module = None

INVOICES = Path(__file__).resolve().parent.parent / "api" / "invoices.py"


def setUpModule():
	global module
	frappe_stub.install()
	module = importlib.import_module("pos_next.api.pos_doctypes")


def tearDownModule():
	frappe_stub.uninstall()


def _throw(message, *args, **kwargs):
	raise RuntimeError(message)


class TestCheckPosDoctype(unittest.TestCase):
	def setUp(self):
		self.allow = mock.patch.object(module, "_allow_sales_order", return_value=False)
		self.can = mock.patch.object(module, "_can_create_sales_order", return_value=False)
		self.allow_mock = self.allow.start()
		self.can_mock = self.can.start()
		self.addCleanup(self.allow.stop)
		self.addCleanup(self.can.stop)
		underscore = mock.patch.object(module, "_", new=lambda text: text)
		underscore.start()
		self.addCleanup(underscore.stop)
		throw = mock.patch.object(module.frappe, "throw", side_effect=_throw)
		self.throw = throw.start()
		self.addCleanup(throw.stop)

	def test_foreign_doctype_is_rejected_before_any_lookup(self):
		with self.assertRaises(RuntimeError) as ctx:
			module.check_pos_doctype("Journal Entry", "P1")
		self.assertIn("Document type Journal Entry is not allowed in POS", str(ctx.exception))
		self.assertEqual(module.frappe.PermissionError, self.throw.call_args.args[1])
		self.allow_mock.assert_not_called()

	def test_pos_invoice_is_always_rejected(self):
		self.allow_mock.return_value = True
		self.can_mock.return_value = True
		with self.assertRaises(RuntimeError):
			module.check_pos_doctype("POS Invoice", "P1")

	def test_sales_invoice_passes(self):
		module.check_pos_doctype("Sales Invoice", "P1")
		self.throw.assert_not_called()

	def test_sales_order_needs_the_flag_and_the_permission(self):
		for flag, permission in ((False, True), (True, False), (False, False)):
			self.allow_mock.return_value = flag
			self.can_mock.return_value = permission
			with self.assertRaises(RuntimeError, msg=f"flag={flag} permission={permission}"):
				module.check_pos_doctype("Sales Order", "P1")
		self.throw.reset_mock()
		self.allow_mock.return_value = True
		self.can_mock.return_value = True
		module.check_pos_doctype("Sales Order", "P1")
		self.throw.assert_not_called()

	def test_invoices_check_the_doctype_before_loading_anything(self):
		tree = ast.parse(INVOICES.read_text(encoding="utf-8"))
		loaders = {"frappe.get_doc", "frappe.db.exists", "_handle_offline_deduplication"}
		for name in ("update_invoice", "submit_invoice"):
			function = next(
				node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name
			)
			check_lines = []
			loader_lines = []
			for node in ast.walk(function):
				if isinstance(node, ast.Call):
					called = ast.unparse(node.func)
					if called == "check_pos_doctype":
						check_lines.append(node.lineno)
					elif called in loaders:
						loader_lines.append(node.lineno)
			self.assertTrue(check_lines, f"{name} never calls check_pos_doctype")
			self.assertLess(min(check_lines), min(loader_lines), name)


if __name__ == "__main__":
	unittest.main()
