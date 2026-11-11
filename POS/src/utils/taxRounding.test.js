import { describe, expect, it } from "vitest"
import { cartTaxTotals, normalizeRoundingMethod, roundCurrency } from "./taxRounding"

const BANKERS = "Banker's Rounding"
const LEGACY = "Banker's Rounding (legacy)"
const COMMERCIAL = "Commercial Rounding"

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
})
