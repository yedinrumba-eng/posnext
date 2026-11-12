import { describe, expect, it } from "vitest"
import { appendWeightKey, needsWeightPrompt, parseWeight } from "./weight"

const fractional = { uom_must_be_whole_number: 0 }

describe("needsWeightPrompt", () => {
	it("asks for the weight in kiosk mode when the UOM accepts fractions", () => {
		expect(needsWeightPrompt(true, { uom_must_be_whole_number: 0 })).toBe(true)
		expect(needsWeightPrompt(true, { uom_must_be_whole_number: "0" })).toBe(true)
	})

	it("never asks when kiosk mode is off", () => {
		expect(needsWeightPrompt(false, fractional)).toBe(false)
		expect(needsWeightPrompt(0, fractional)).toBe(false)
	})

	it("never asks when the UOM must be a whole number", () => {
		expect(needsWeightPrompt(true, { uom_must_be_whole_number: 1 })).toBe(false)
		expect(needsWeightPrompt(true, { uom_must_be_whole_number: "1" })).toBe(false)
	})

	it("does not ask when the flag is missing, null or empty", () => {
		expect(needsWeightPrompt(true, {})).toBe(false)
		expect(needsWeightPrompt(true, { uom_must_be_whole_number: null })).toBe(false)
		expect(needsWeightPrompt(true, { uom_must_be_whole_number: "" })).toBe(false)
		expect(needsWeightPrompt(true, null)).toBe(false)
	})

	it("does not ask for variants, serial or batch items", () => {
		expect(needsWeightPrompt(true, { ...fractional, has_variants: 1 })).toBe(false)
		expect(needsWeightPrompt(true, { ...fractional, has_serial_no: 1 })).toBe(false)
		expect(needsWeightPrompt(true, { ...fractional, has_batch_no: 1 })).toBe(false)
	})
})

describe("appendWeightKey", () => {
	it("ignores a second dot and starts with 0. on an empty text", () => {
		expect(appendWeightKey("1.5", ".")).toBe("1.5")
		expect(appendWeightKey("", ".")).toBe("0.")
	})

	it("ignores a 4th decimal and a 4th integer digit", () => {
		expect(appendWeightKey("1.234", "5")).toBe("1.234")
		expect(appendWeightKey("123", "4")).toBe("123")
		expect(appendWeightKey("123", ".")).toBe("123.")
	})

	it("replaces a lone zero with the next digit", () => {
		expect(appendWeightKey("0", "5")).toBe("5")
	})

	it("handles back and clear, and leaves unknown keys alone", () => {
		expect(appendWeightKey("1.35", "back")).toBe("1.3")
		expect(appendWeightKey("", "back")).toBe("")
		expect(appendWeightKey("1.35", "clear")).toBe("")
		expect(appendWeightKey("1.35", "x")).toBe("1.35")
	})
})

describe("parseWeight", () => {
	it("parses valid weights and rejects the rest", () => {
		expect(parseWeight("1.35")).toBe(1.35)
		expect(parseWeight("1.")).toBe(1)
		expect(parseWeight("0")).toBeNull()
		expect(parseWeight(".")).toBeNull()
		expect(parseWeight("")).toBeNull()
		expect(parseWeight("1.2345")).toBeNull()
	})
})
