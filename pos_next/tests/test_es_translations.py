# -*- coding: utf-8 -*-
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt
"""Spec 059: the POS ships a Spanish locale (es.csv) covering every translatable string.

Pure test: no frappe import, no stubs. Reads the CSVs and the POS/src sources directly.
"""

import csv
import re
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ES = ROOT / "pos_next/translations/es.csv"
CSV_SOURCES = ("ar.csv", "pt-br.csv", "id.csv")
CALL_RE = re.compile(r"""__\(\s*(["'])((?:\\.|(?!\1).)*)\1""")
SKIP_FILE = "POS/src/utils/translation.ts"

SUPPORTED_ES_BLOCK = (
	"\tes: {\n"
	'\t\tname: "Spanish",\n'
	'\t\tnativeName: "Español",\n'
	'\t\tcountryCode: "do",\n'
	'\t\tdir: "ltr",\n'
	"\t},\n"
)

REVIEW_KEYS = (
	"Open Shift", "Close Shift", "Opening Amount", "Expected Amount", "Difference",
	"New Sale", "Search products...", "Item", "Out of Stock", "Qty",
	"Payment Method", "Grand Total", "Discount", "Hold", "Clear Cart",
	"Customer", "Walk-in Customer", "Checkout", "Pay", "Cash",
	"Paid Amount", "Change Due", "Charge on EBT", "Print Receipt", "Return Invoice",
	"Draft Invoices", "Invoice", "Sync offline sales before closing",
	"Did not reach the kitchen", "Sign Out",
)

GLOSSARY = (
	("Shift", "turno"),
	("Invoice", "factura"),
	("Invoices", "factura"),
	("Customer", "cliente"),
	("Customers", "cliente"),
	("Discount", "descuento"),
	("Cart", "carrito"),
	("Coupon", "cupón"),
	("Warehouse", "almacén"),
	("Draft", "borrador"),
	("Cash", "efectivo"),
	("Hold", "espera"),
)

INDIRECT = (
	("POS/src/utils/kitchenOrder.js", "kitchenReasonText", 9),
	("POS/src/utils/appOrders.js", "fulfillmentText", 3),
	("POS/src/utils/appOrders.js", "paymentText", 4),
	("POS/src/utils/appOrders.js", "syncWarningText", 2),
)
RETURN_RE = re.compile(r"""\breturn\s+(["'])((?:\\.|(?!\1).)*)\1""")
CALLEE_RE = re.compile(r"__\(\s*([A-Za-z_$][\w$]*)\s*\(")
REVIEWED = {
	"Clear": "Borrar",
	"Dismiss": "Ocultar",
	"On Account": "A cuenta",
	"You have an active shift open. Would you like to:": "Tiene un turno activo abierto. Elija una opción:",
}

PLACEHOLDER_RE = re.compile(r"\{\d+\}")
TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
LITERALS = ("\\n", "${", "POS Next", "ERPNext", "Frappe", "EBT", "SNAP", "Verifone")


def _read_rows(path):
	with open(path, encoding="utf-8", newline="") as handle:
		return [row for row in csv.reader(handle)]


def _unescape(text):
	return text.replace("\\'", "'").replace('\\"', '"')


def indirect_literals():
	"""Return literals per INDIRECT function: the return "..." strings of its body."""
	found = {}
	for rel, name, _count in INDIRECT:
		text = (ROOT / rel).read_text(encoding="utf-8")
		start = text.find(f"export function {name}(")
		if start == -1:
			raise AssertionError(f"{name} not found")
		end = text.find("\n}\n", start)
		if end == -1:
			raise AssertionError(f"{name} not found")
		body = text[start:end]
		found[name] = [_unescape(m.group(2)) for m in RETURN_RE.finditer(body)]
	return found


def expected_keys():
	"""Every key the POS can ask to translate: the 3 CSVs plus every __() in POS/src."""
	keys = set()
	for name in CSV_SOURCES:
		for row in _read_rows(ROOT / "pos_next/translations" / name):
			if row:
				keys.add(row[0])
	for path in (ROOT / "POS/src").rglob("*"):
		if path.suffix not in (".vue", ".js", ".ts") or ".test." in path.name:
			continue
		if path.relative_to(ROOT).as_posix() == SKIP_FILE:
			continue
		text = path.read_text(encoding="utf-8")
		for match in CALL_RE.finditer(text):
			key = match.group(2).replace("\\'", "'").replace('\\"', '"')
			if "&lt;" in key:
				continue
			keys.add(key)
	for literals in indirect_literals().values():
		keys.update(literals)
	return keys


def es_rows():
	if not ES.exists():
		return []
	return _read_rows(ES)


def es_keys():
	return {row[0] for row in es_rows()}


def review_lines():
	table = {row[0]: row[1] for row in es_rows()}
	return [f"{key} => {table.get(key)}" for key in REVIEW_KEYS]


class TestSpanishLocale(unittest.TestCase):
	def test_supported_locales_has_es(self):
		text = (ROOT / "POS/src/composables/useLocale.js").read_text(encoding="utf-8")
		self.assertIn(SUPPORTED_ES_BLOCK, text)
		for opener in ("en: {", "ar: {", "id: {", '"pt-br": {'):
			self.assertIn(opener, text)

	def test_es_csv_shape(self):
		self.assertTrue(ES.exists(), "es.csv missing")
		self.assertFalse(ES.read_bytes().startswith(b"\xef\xbb\xbf"), "es.csv starts with BOM")
		rows = es_rows()
		for row in rows:
			self.assertEqual(len(row), 3, row)
			self.assertEqual(row[2], "", row)
		keys = [row[0] for row in rows]
		self.assertEqual(len(keys), len(set(keys)), "duplicate keys in es.csv")

	def test_es_covers_every_key(self):
		self.assertTrue(ES.exists(), "es.csv missing")
		missing = sorted(expected_keys() - es_keys())
		self.assertEqual(missing, [], f"{len(missing)} keys missing, first 10: {missing[:10]}")

	def test_no_empty_translation(self):
		self.assertTrue(ES.exists(), "es.csv missing")
		empty = [row[0] for row in es_rows() if not row[1].strip()]
		self.assertEqual(empty, [], f"empty translations: {empty[:10]}")

	def test_tokens_preserved(self):
		self.assertTrue(ES.exists(), "es.csv missing")
		bad = []
		for key, value, _ in es_rows():
			same = Counter(PLACEHOLDER_RE.findall(key)) == Counter(PLACEHOLDER_RE.findall(value))
			same = same and Counter(TAG_RE.findall(key)) == Counter(TAG_RE.findall(value))
			same = same and all(key.count(tok) == value.count(tok) for tok in LITERALS)
			if not same:
				bad.append(key)
		self.assertEqual(bad, [], f"{len(bad)} rows lost tokens, first 10: {bad[:10]}")

	def test_identical_rows_capped(self):
		self.assertTrue(ES.exists(), "es.csv missing")
		identical = [row[0] for row in es_rows() if row[1] == row[0]]
		self.assertLessEqual(len(identical), 40, identical)

	def test_glossary(self):
		self.assertTrue(ES.exists(), "es.csv missing")
		bad = []
		for key, value, _ in es_rows():
			for word, target in GLOSSARY:
				if re.search(rf"\b{word}\b", key, re.IGNORECASE):
					if target not in value.lower():
						bad.append(f"{key} => {value} (needs {target})")
		self.assertEqual(bad, [], f"{len(bad)} glossary misses, first 10: {bad[:10]}")

	def test_review_sample_present(self):
		self.assertTrue(ES.exists(), "es.csv missing")
		table = {row[0]: row[1] for row in es_rows()}
		for key in REVIEW_KEYS:
			self.assertIn(key, table)
			self.assertNotEqual(table[key], key, key)

	def test_indirect_literals_found(self):
		found = indirect_literals()
		for _rel, name, count in INDIRECT:
			self.assertEqual(len(found[name]), count, f"{name}: {found[name]}")

	def test_indirect_callees_known(self):
		known = {name for _rel, name, _count in INDIRECT}
		callees = set()
		for path in (ROOT / "POS/src").rglob("*"):
			if path.suffix not in (".vue", ".js", ".ts") or ".test." in path.name:
				continue
			if path.relative_to(ROOT).as_posix() == SKIP_FILE:
				continue
			callees.update(CALLEE_RE.findall(path.read_text(encoding="utf-8")))
		self.assertTrue(callees <= known, f"unknown __(f(...)) callees: {sorted(callees - known)}")

	def test_reviewed_wording(self):
		self.assertTrue(ES.exists(), "es.csv missing")
		table = {row[0]: row[1] for row in es_rows()}
		for key, expected in REVIEWED.items():
			self.assertEqual(table.get(key), expected, key)


if __name__ == "__main__":
	unittest.main()
