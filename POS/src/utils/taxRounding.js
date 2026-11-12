/**
 * Cart tax rounding that mirrors the server (D28.14).
 *
 * ERPNext rounds with frappe.utils.data.rounded() using System Settings.rounding_method
 * (frappe v16.53.0, frappe/utils/data.py:1242-1335). The three private functions below are a
 * line-by-line port of _bankers_rounding_legacy, _bankers_rounding and _round_away_from_zero.
 * Plain toFixed()/Math.round() are NOT enough: (2.675).toFixed(2) is "2.67" and Frappe gives 2.68.
 *
 * Python -> JS equivalences used (and no others):
 *   round(x, n) with n > 0  -> Number(x.toFixed(n)) (except _round_away_from_zero: pyRound, exact ties to even)
 *   round(x)                -> Math.round(x)  (only reached outside the .5 ties, solved before)
 *   math.ulp(a), a > 0      -> nextUp(a) - a
 *   Decimal(num).quantize(..., ROUND_HALF_UP) -> Number(num.toFixed(precision))
 *   math.copysign(e, num)   -> Math.sign(num) * e
 */

export const ROUNDING_METHODS = Object.freeze(["Banker's Rounding (legacy)", "Banker's Rounding", "Commercial Rounding"])

// Frappe falls back to this one when the setting is empty (data.py:1247).
export const DEFAULT_ROUNDING_METHOD = "Banker's Rounding (legacy)"

export function normalizeRoundingMethod(value) {
	return ROUNDING_METHODS.includes(value) ? value : null
}

const float64 = new Float64Array(1)
const bits64 = new BigUint64Array(float64.buffer)

// math.ulp(a) for a finite a > 0: distance to the next double.
function ulp(a) {
	float64[0] = a
	bits64[0] += BigInt(1)
	return float64[0] - a
}

// _bankers_rounding_legacy (data.py:1263-1279)
function bankersRoundingLegacy(num, precision) {
	const multiplier = 10 ** precision
	num = Number((precision ? num * multiplier : num).toFixed(8))

	const floorNum = Math.floor(num)
	const decimalPart = num - floorNum

	if (!precision && decimalPart === 0.5) {
		num = floorNum % 2 === 0 ? floorNum : floorNum + 1
	} else if (decimalPart === 0.5) {
		num = floorNum + 1
	} else {
		num = Math.round(num)
	}

	return precision ? num / multiplier : num
}

// Python round(x, n), n > 0, on the exact binary value: exact ties go to even, the rest is toFixed.
function pyRound(x, n) {
	const scaled = x * 2 ** (n + 1)
	if (Number.isInteger(scaled) && Math.abs(scaled) % 2 === 1) {
		const lower = Math.floor(Math.abs(x) * 10 ** n)
		const even = lower % 2 === 0 ? lower : lower + 1
		return (Math.sign(x) * even) / 10 ** n
	}
	return Number(x.toFixed(n))
}

// _round_away_from_zero (data.py:1282-1313)
function roundAwayFromZero(num, precision) {
	if (num === 0) {
		return 0
	}

	const epsilon = ulp(Math.abs(num))
	const roundingStep = 10 ** -precision

	if (Number.isFinite(num) && epsilon >= roundingStep / 4) {
		return Number(num.toFixed(precision))
	}

	return pyRound(num + Math.sign(num) * epsilon, precision)
}

// _bankers_rounding (data.py:1316-1335)
function bankersRounding(num, precision) {
	if (num === 0) {
		return 0
	}

	const sign = num < 0 ? -1 : 1
	const multiplier = 10 ** precision
	num = Number((Math.abs(num) * multiplier).toFixed(12))

	if (num === 0) {
		return 0
	}

	const floorNum = Math.floor(num)
	const decimalPart = num - floorNum

	const epsilon = 2.0 ** (Math.log(num) / Math.log(2) - 52.0)

	if (epsilon < 0.5 && Math.abs(decimalPart - 0.5) < epsilon) {
		num = floorNum % 2 === 0 ? floorNum : floorNum + 1
	} else {
		num = Math.round(num)
	}

	return (sign * num) / multiplier
}

/**
 * Same number as frappe.utils.data.rounded(num, precision, method).
 * An empty, null or unknown method rounds as Frappe's fallback (B28).
 */
export function roundCurrency(num, precision, method) {
	const m = normalizeRoundingMethod(method) ?? DEFAULT_ROUNDING_METHOD
	let result
	if (m === "Banker's Rounding") {
		result = bankersRounding(num, precision)
	} else if (m === "Commercial Rounding") {
		result = roundAwayFromZero(num, precision)
	} else {
		result = bankersRoundingLegacy(num, precision)
	}
	// "+ 0" turns a negative zero into 0 (Python has no negative zero for these results).
	return result + 0
}

/**
 * Net total, tax and grand total of a cart, rounded the way ERPNext does it (taxes_and_totals.py:
 * 239, 512, 643, 672, 762-771, 825): the net of each line is rounded, the tax is the ordered sum of
 * (rate / 100) * net rounded ONCE, and the grand total is round(net total + rounded tax).
 *
 * @param {Array<{net: number, rate: number}>} lines
 * @param {string|null|undefined} method - System Settings.rounding_method
 * @param {number} precision
 * @returns {{netTotal: number, taxTotal: number, grandTotal: number}}
 */
export function cartTaxTotals(lines, method, precision = 2) {
	const m = normalizeRoundingMethod(method) ?? DEFAULT_ROUNDING_METHOD
	const nets = lines.map((line) => roundCurrency(Number(line.net) || 0, precision, m))

	let tax = 0
	let netSum = 0
	for (let i = 0; i < lines.length; i++) {
		const rate = Number(lines[i].rate) || 0
		tax += (rate / 100) * nets[i]
		netSum += nets[i]
	}

	const taxTotal = roundCurrency(tax, precision, m)
	const netTotal = roundCurrency(netSum, precision, m)
	const grandTotal = roundCurrency(netTotal + taxTotal, precision, m)
	return { netTotal, taxTotal, grandTotal }
}
