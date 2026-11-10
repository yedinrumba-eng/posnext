/**
 * Effective tax rate of one Item (D28.13).
 *
 * ERPNext rule (erpnext/controllers/taxes_and_totals.py): for each tax row, if the Item's
 * item_tax_rate has the row's account_head, that value is the rate ("N/A" = 0); otherwise the
 * rate of the row itself. Only the row types the cart sums today are counted.
 *
 * @param {Array|null|undefined} taxRules - rows of the POS Profile tax template
 * @param {Object|string|null|undefined} itemTaxMap - Item.item_tax_rate (object or JSON string)
 * @returns {number} total rate in percent
 */
export function effectiveTaxRate(taxRules, itemTaxMap) {
	if (!taxRules || taxRules.length === 0) {
		return 0
	}

	let map = itemTaxMap
	if (typeof map === "string") {
		try {
			map = JSON.parse(map)
		} catch {
			map = {}
		}
	}
	if (map === null || typeof map !== "object") {
		map = {}
	}

	let totalRate = 0
	for (const rule of taxRules) {
		if (rule.charge_type !== "On Net Total" && rule.charge_type !== "On Previous Row Total") {
			continue
		}
		if (Object.hasOwn(map, rule.account_head)) {
			const value = map[rule.account_head]
			totalRate += value === "N/A" ? 0 : Number(value) || 0
		} else {
			totalRate += Number(rule.rate) || 0
		}
	}
	return totalRate
}
