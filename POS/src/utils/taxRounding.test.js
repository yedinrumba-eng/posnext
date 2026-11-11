import { describe, expect, it } from "vitest"
import { cartTaxTotals, normalizeRoundingMethod, roundCurrency } from "./taxRounding"

const BANKERS = "Banker's Rounding"
const LEGACY = "Banker's Rounding (legacy)"
const COMMERCIAL = "Commercial Rounding"

// Exact oracle of _round_away_from_zero(x, 2) in integer cents, BigInt only (no toFixed, no pyRound). The integer
// oracle of tests 7 and 8 cannot see the float noise of the tax sum, this one can.
function commercialCentsOracle(x) {
	if (x === 0) {
		return 0
	}
	const f64 = new Float64Array(1)
	const b64 = new BigUint64Array(f64.buffer)
	f64[0] = Math.abs(x)
	const bits = b64[0]
	const b = Number(bits >> 52n)
	const f = bits & ((1n << 52n) - 1n)
	const mantissa = b === 0 ? f : f | (1n << 52n)
	const e = (b === 0 ? 1 : b) - 1075
	// |x| = mantissa * 2^e and |x| + ulp(|x|) = (mantissa + 1) * 2^e, both exact
	const n = (mantissa + 1n) * 100n
	let q
	if (e >= 0) {
		q = n << BigInt(e)
	} else {
		const d = 1n << BigInt(-e)
		q = n / d
		const twice = 2n * (n % d)
		if (twice > d || (twice === d && q % 2n === 1n)) {
			q += 1n
		}
	}
	return Math.sign(x) * Number(q)
}

// Integer oracle of the server semantics (Valores fijados E2): tax in cents = exact round of 71 * c / 800.
function expectedTaxCents(c, commercial) {
	const f = Math.floor((71 * c) / 800)
	const r = (71 * c) % 800
	if (r < 400) {
		return f
	}
	if (r > 400) {
		return f + 1
	}
	if (commercial) {
		return f + 1
	}
	return f % 2 === 0 ? f : f + 1
}

describe("roundCurrency", () => {
	it("rounds 1.065, 2.675 and 1.005 like frappe for each method", () => {
		const inputs = [1.065, 2.675, 1.005]
		expect(inputs.map((x) => roundCurrency(x, 2, BANKERS))).toEqual([1.06, 2.68, 1])
		expect(inputs.map((x) => roundCurrency(x, 2, LEGACY))).toEqual([1.07, 2.68, 1.01])
		expect(inputs.map((x) => roundCurrency(x, 2, COMMERCIAL))).toEqual([1.07, 2.68, 1.01])
	})

	it("falls back to Banker's Rounding (legacy) for an empty or unknown method (B28)", () => {
		for (const m of [null, undefined, "", "Foo"]) {
			expect(roundCurrency(1.065, 2, m)).toBe(1.07)
		}
		expect(normalizeRoundingMethod("Foo")).toBe(null)
		expect(normalizeRoundingMethod(COMMERCIAL)).toBe(COMMERCIAL)
	})

	it("handles negatives and zero", () => {
		expect(roundCurrency(-1.065, 2, BANKERS)).toBe(-1.06)
		expect(roundCurrency(-1.065, 2, LEGACY)).toBe(-1.06)
		expect(roundCurrency(-1.065, 2, COMMERCIAL)).toBe(-1.07)
		for (const m of [BANKERS, LEGACY, COMMERCIAL]) {
			expect(roundCurrency(0, 2, m)).toBe(0)
			expect(cartTaxTotals([], m)).toEqual({ netTotal: 0, taxTotal: 0, grandTotal: 0 })
		}
	})
})

describe("cartTaxTotals", () => {
	it("$12.00 at 8.875%: Banker's 1.06 / 13.06, Commercial 1.07 / 13.07 (B26)", () => {
		const lines = [{ net: 12, rate: 8.875 }]
		const b = cartTaxTotals(lines, BANKERS)
		expect([b.taxTotal, b.grandTotal]).toEqual([1.06, 13.06])
		const c = cartTaxTotals(lines, COMMERCIAL)
		expect([c.taxTotal, c.grandTotal]).toEqual([1.07, 13.07])
	})

	it("$92.00 at 8.875%: the total is net + rounded tax (B27)", () => {
		const lines = [{ net: 92, rate: 8.875 }]
		const b = cartTaxTotals(lines, BANKERS)
		expect([b.taxTotal, b.grandTotal]).toEqual([8.16, 100.16])
		const c = cartTaxTotals(lines, COMMERCIAL)
		expect([c.taxTotal, c.grandTotal]).toEqual([8.17, 100.17])
	})

	it("matches the receipt of the smoke sale (Step 12) with the 3 methods", () => {
		const lines = [
			{ net: 10, rate: 0 },
			{ net: 10, rate: 8.875 },
		]
		for (const m of [BANKERS, LEGACY, COMMERCIAL]) {
			expect(cartTaxTotals(lines, m)).toEqual({ netTotal: 20, taxTotal: 0.89, grandTotal: 20.89 })
		}
	})

	it("sweep with Banker's Rounding: 0 differences against the server oracle (B31)", () => {
		let diffs = 0
		for (let c = 1; c <= 30000; c++) {
			const t = expectedTaxCents(c, false)
			const r = cartTaxTotals([{ net: c / 100, rate: 8.875 }], BANKERS)
			if (Math.round(r.taxTotal * 100) !== t || Math.round(r.grandTotal * 100) !== c + t) {
				diffs++
			}
		}
		for (let c = 1; c <= 5000; c++) {
			const t = expectedTaxCents(c, false)
			const r = cartTaxTotals(
				[
					{ net: c / 100, rate: 0 },
					{ net: c / 100, rate: 8.875 },
				],
				BANKERS,
			)
			if (Math.round(r.taxTotal * 100) !== t || Math.round(r.grandTotal * 100) !== 2 * c + t) {
				diffs++
			}
		}
		expect(diffs).toBe(0)
	})

	it("sweep with Commercial Rounding: 0 differences against the server oracle (B31)", () => {
		let diffs = 0
		for (let c = 1; c <= 30000; c++) {
			const t = expectedTaxCents(c, true)
			const r = cartTaxTotals([{ net: c / 100, rate: 8.875 }], COMMERCIAL)
			if (Math.round(r.taxTotal * 100) !== t || Math.round(r.grandTotal * 100) !== c + t) {
				diffs++
			}
		}
		for (let c = 1; c <= 5000; c++) {
			const t = expectedTaxCents(c, true)
			const r = cartTaxTotals(
				[
					{ net: c / 100, rate: 0 },
					{ net: c / 100, rate: 8.875 },
				],
				COMMERCIAL,
			)
			if (Math.round(r.taxTotal * 100) !== t || Math.round(r.grandTotal * 100) !== 2 * c + t) {
				diffs++
			}
		}
		expect(diffs).toBe(0)
	})

	it("$24.99 + $275.01 at 8.875%: the exact tie goes to even like the server (B32)", () => {
		const lines = [
			{ net: 24.99, rate: 8.875 },
			{ net: 275.01, rate: 8.875 },
		]
		expect(cartTaxTotals(lines, COMMERCIAL)).toEqual({ netTotal: 300, taxTotal: 26.62, grandTotal: 326.62 })
		expect(cartTaxTotals(lines, BANKERS)).toEqual({ netTotal: 300, taxTotal: 26.62, grandTotal: 326.62 })
		expect(cartTaxTotals(lines, LEGACY)).toEqual({ netTotal: 300, taxTotal: 26.63, grandTotal: 326.63 })
	})

	it("$35.98 + $264.02 at 8.875% with Commercial Rounding gives 26.62 (B32)", () => {
		const lines = [
			{ net: 35.98, rate: 8.875 },
			{ net: 264.02, rate: 8.875 },
		]
		expect(cartTaxTotals(lines, COMMERCIAL)).toEqual({ netTotal: 300, taxTotal: 26.62, grandTotal: 326.62 })
	})

	it("$699.99 + $0.01 at 8.875% with Commercial Rounding gives 62.12", () => {
		const lines = [
			{ net: 699.99, rate: 8.875 },
			{ net: 0.01, rate: 8.875 },
		]
		expect(cartTaxTotals(lines, COMMERCIAL)).toEqual({ netTotal: 700, taxTotal: 62.12, grandTotal: 762.12 })
	})

	it("a weighed net of 25.624999999999996 rounds to 25.62 with Commercial Rounding (B33)", () => {
		expect(roundCurrency(25.624999999999996, 2, COMMERCIAL)).toBe(25.62)
		const lines = [
			{ net: 10.80469, rate: 0 },
			{ net: 73.02645, rate: 8.875 },
			{ net: 5.06826, rate: 0 },
			{ net: 25.624999999999996, rate: 8.875 },
		]
		expect(cartTaxTotals(lines, COMMERCIAL)).toEqual({ netTotal: 114.52, taxTotal: 8.76, grandTotal: 123.28 })
		expect(cartTaxTotals(lines, BANKERS)).toEqual({ netTotal: 114.52, taxTotal: 8.76, grandTotal: 123.28 })
		expect(cartTaxTotals(lines, LEGACY)).toEqual({ netTotal: 114.53, taxTotal: 8.76, grandTotal: 123.29 })
	})

	it("sweep of two taxed lines that add up to $300 with Commercial Rounding: 0 differences (B32)", () => {
		let diffs = 0
		let low = 0
		let high = 0
		for (let a = 1; a <= 29999; a++) {
			const n1 = commercialCentsOracle(a / 100) / 100
			const n2 = commercialCentsOracle((30000 - a) / 100) / 100
			let tax = 0
			tax += (8.875 / 100) * n1
			tax += (8.875 / 100) * n2
			const t = commercialCentsOracle(tax)
			if (t === 2662) {
				low++
			}
			if (t === 2663) {
				high++
			}
			const r = cartTaxTotals(
				[
					{ net: a / 100, rate: 8.875 },
					{ net: (30000 - a) / 100, rate: 8.875 },
				],
				COMMERCIAL,
			)
			if (r.netTotal !== 300 || Math.round(r.taxTotal * 100) !== t || Math.round(r.grandTotal * 100) !== 30000 + t) {
				diffs++
			}
		}
		expect([diffs, low, high]).toEqual([0, 7128, 22871])
	})
})
