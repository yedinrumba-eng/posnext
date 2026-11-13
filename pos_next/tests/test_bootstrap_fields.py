"""S10.8b - the POS must receive the SNAP mode of payment when a shift is open.

With an open shift the POS reads its settings from bootstrap.get_pos_settings, whose field list is
fixed. Reads the source with ``ast`` and ``json``; no frappe, no bench.
"""

import ast
import json
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP = PACKAGE_ROOT / "api" / "bootstrap.py"
POS_SETTINGS_JSON = PACKAGE_ROOT / "pos_next" / "doctype" / "pos_settings" / "pos_settings.json"

FIELD = "snap_tax_exempt_mode_of_payment"


def _function(name):
	tree = ast.parse(BOOTSTRAP.read_text(encoding="utf-8"))
	for node in ast.walk(tree):
		if isinstance(node, ast.FunctionDef) and node.name == name:
			return node
	raise AssertionError(f"{name} not found in bootstrap.py")


def _field_list():
	"""Third positional argument of the frappe.db.get_value call in get_pos_settings."""
	for node in ast.walk(_function("get_pos_settings")):
		if (
			isinstance(node, ast.Call)
			and isinstance(node.func, ast.Attribute)
			and node.func.attr == "get_value"
			and len(node.args) >= 3
		):
			return [item.value for item in node.args[2].elts]
	raise AssertionError("frappe.db.get_value call not found in get_pos_settings")


class TestBootstrapFields(unittest.TestCase):
	def test_get_pos_settings_asks_for_the_snap_field(self):
		self.assertIn(FIELD, _field_list())

	def test_default_settings_carry_the_snap_key_empty(self):
		for node in ast.walk(_function("get_default_pos_settings")):
			if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
				values = {
					key.value: value
					for key, value in zip(node.value.keys, node.value.values, strict=True)
					if isinstance(key, ast.Constant)
				}
				self.assertIn(FIELD, values)
				self.assertEqual("", ast.literal_eval(values[FIELD]))
				return
		self.fail("get_default_pos_settings does not return a dict literal")

	def test_every_requested_field_exists_in_pos_settings(self):
		doctype = json.loads(POS_SETTINGS_JSON.read_text(encoding="utf-8"))
		fieldnames = {field["fieldname"] for field in doctype["fields"]}
		missing = [name for name in _field_list() if name != "name" and name not in fieldnames]
		self.assertEqual([], missing)


if __name__ == "__main__":
	unittest.main()
