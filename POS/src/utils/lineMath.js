import { roundCurrency } from "./taxRounding"

/**
 * Amounts of one cart line, rounded the way ERPNext rounds them (taxes_and_totals.py:186-196):
 * the discount percentage to 3 decimals, the unit discount and the unit rate to cents, and the
 * line net and line discount from those unit amounts. The server recomputes the rate from the
 * price list rate and the percentage, so these must give the same cents.
 *
 * @param {{priceListRate: number, qty: number, discountPercentage: number, method: string}} args
 * @returns {{discountPercentage: number, unitDiscount: number, unitRate: number, net: number, lineDiscount: number}}
 */
export function lineAmounts({ priceListRate, qty, discountPercentage, method }) {
	const plr = Number(priceListRate) || 0
	const quantity = Number(qty) || 0
	const pct = roundCurrency(Number(discountPercentage) || 0, 3, method)

	const unitDiscount = pct > 0 ? roundCurrency((plr * pct) / 100, 2, method) : 0
	const unitRate = roundCurrency(plr - unitDiscount, 2, method)
	const net = roundCurrency(unitRate * quantity, 2, method)
	const lineDiscount = roundCurrency(unitDiscount * quantity, 2, method)

	return { discountPercentage: pct, unitDiscount, unitRate, net, lineDiscount }
}
