import { describe, expect, it } from "vitest"
import { SNAP_ALLOCATION, snapExemption } from "./snapExemption"

const METHOD = "Commercial Rounding"
// A 10.00 taxable eligible, B 5.00 taxable eligible, C 20.00 exempt eligible, D 4.00 taxable not eligible
const LINES = [
	{ net: 10, taxRate: 8.875, snapEligible: true },
	{ net: 5, taxRate: 8.875, snapEligible: true },
	{ net: 20, taxRate: 0, snapEligible: true },
	{ net: 4, taxRate: 8.875, snapEligible: false },
]

describe("snapExemption", () => {
	it("defaults to taxable_first (P1)", () => {
		expect(SNAP_ALLOCATION).toBe("taxable_first")
	})

	it("EBT covering every taxable eligible line removes all of their tax", () => {
		const r = snapExemption({ lines: LINES, ebtPaid: 35, method: METHOD })
		expect(r.exemption).toBe(1.33)
		expect(r.eligibleTotal).toBe(35)
		expect(r.overLimit).toBe(false)
	})

	it("partial EBT, taxable first", () => {
		expect(snapExemption({ lines: LINES, ebtPaid: 10, method: METHOD }).exemption).toBe(0.89)
	})

	it("partial EBT, proportional", () => {
		const r = snapExemption({ lines: LINES, ebtPaid: 10, method: METHOD, allocation: "proportional" })
		expect(r.exemption).toBe(0.38)
	})

	it("no EBT, or nothing taxable, removes nothing", () => {
		expect(snapExemption({ lines: LINES, ebtPaid: 0, method: METHOD }).exemption).toBe(0)
		expect(snapExemption({ lines: [LINES[2]], ebtPaid: 20, method: METHOD }).exemption).toBe(0)
	})

	it("flags EBT above the eligible total", () => {
		const r = snapExemption({ lines: LINES, ebtPaid: 40, method: METHOD })
		expect(r.overLimit).toBe(true)
		expect(r.eligibleTotal).toBe(35)
	})
})
