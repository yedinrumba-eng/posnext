import { describe, expect, it } from "vitest"
import { effectiveTaxRate } from "./itemTax"

const RULES = [{ charge_type: "On Net Total", account_head: "A", rate: 8.875 }]

describe("effectiveTaxRate", () => {
	it("uses the template row rate when the Item has no map", () => {
		expect(effectiveTaxRate(RULES, undefined)).toBe(8.875)
		expect(effectiveTaxRate(RULES, null)).toBe(8.875)
		expect(effectiveTaxRate(RULES, {})).toBe(8.875)
	})

	it("uses 0 when the Item map has the account at 0", () => {
		expect(effectiveTaxRate(RULES, { A: 0 })).toBe(0)
	})

	it("treats N/A as 0", () => {
		expect(effectiveTaxRate(RULES, { A: "N/A" })).toBe(0)
	})

	it("ignores a map for another account", () => {
		expect(effectiveTaxRate(RULES, { B: 0 })).toBe(8.875)
	})

	it("does not sum rows that are not On Net Total or On Previous Row Total", () => {
		const rules = [{ charge_type: "Actual", account_head: "A", rate: 8.875 }]
		expect(effectiveTaxRate(rules, undefined)).toBe(0)
	})

	it("accepts the map as a JSON string and ignores an invalid string", () => {
		expect(effectiveTaxRate(RULES, '{"A": 0}')).toBe(0)
		expect(effectiveTaxRate(RULES, "not json")).toBe(8.875)
	})

	it("matches the receipt of the smoke sale (Step 12): tax 0.89, total 20.89", () => {
		const tax = Math.round(10 * effectiveTaxRate(RULES, { A: 0 }) + 10 * effectiveTaxRate(RULES, { A: 8.875 })) / 100
		expect(tax).toBe(0.89)
		expect(Math.round((20 + tax) * 100) / 100).toBe(20.89)
	})
})
