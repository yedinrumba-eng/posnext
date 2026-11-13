import { describe, expect, it } from "vitest"
import { lineAmounts } from "./lineMath"

const COMMERCIAL = "Commercial Rounding"
const BANKERS = "Banker's Rounding"

describe("lineAmounts", () => {
	it("rounds the unit discount and unit rate before multiplying (7 x 1.99 at 10%)", () => {
		const a = lineAmounts({ priceListRate: 1.99, qty: 7, discountPercentage: 10, method: COMMERCIAL })
		expect(a.unitDiscount).toBe(0.2)
		expect(a.unitRate).toBe(1.79)
		expect(a.net).toBe(12.53)
		expect(a.lineDiscount).toBe(1.4)
	})

	it("rounds a fractional quantity line to cents (1.350 x 4.99)", () => {
		const a = lineAmounts({ priceListRate: 4.99, qty: 1.35, discountPercentage: 0, method: COMMERCIAL })
		expect(a.unitDiscount).toBe(0)
		expect(a.net).toBe(6.74)
		expect(a.lineDiscount).toBe(0)
	})

	it("a 100% discount leaves a zero rate", () => {
		const a = lineAmounts({ priceListRate: 4.99, qty: 3, discountPercentage: 100, method: COMMERCIAL })
		expect(a.unitRate).toBe(0)
		expect(a.net).toBe(0)
	})

	it("depends on the rounding method at exact ties (2.25 at 10%)", () => {
		const commercial = lineAmounts({ priceListRate: 2.25, qty: 1, discountPercentage: 10, method: COMMERCIAL })
		expect(commercial.unitDiscount).toBe(0.23)
		expect(commercial.unitRate).toBe(2.02)
		const bankers = lineAmounts({ priceListRate: 2.25, qty: 1, discountPercentage: 10, method: BANKERS })
		expect(bankers.unitDiscount).toBe(0.22)
		expect(bankers.unitRate).toBe(2.03)
	})

	it("rounds the discount percentage to 3 decimals", () => {
		const a = lineAmounts({ priceListRate: 10, qty: 1, discountPercentage: 71.7875, method: COMMERCIAL })
		expect(a.discountPercentage).toBe(71.788)
	})
})
