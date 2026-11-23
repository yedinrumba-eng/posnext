import { describe, expect, it } from "vitest"
import {
	appTotalMismatch,
	cartPlan,
	daysOld,
	fulfillmentText,
	paymentText,
	syncWarningText,
	visiblePaymentMethods,
} from "./appOrders"

// Spec 031a4. Pure rules of the app orders in the POS.
const METHODS = [
	{ mode_of_payment: "Cash" },
	{ mode_of_payment: "Card (Driver)" },
	{ mode_of_payment: "Card" },
]

describe("visiblePaymentMethods", () => {
	it("B1: hides Card (Driver) unless the cart comes from a delivery order", () => {
		const none = visiblePaymentMethods(METHODS, "Card (Driver)", null)
		expect(none.map((m) => m.mode_of_payment)).toEqual(["Cash", "Card"])
		const pickup = visiblePaymentMethods(METHODS, "Card (Driver)", { fulfillment: "pickup" })
		expect(pickup.map((m) => m.mode_of_payment)).toEqual(["Cash", "Card"])
		const delivery = visiblePaymentMethods(METHODS, "Card (Driver)", { fulfillment: "delivery" })
		expect(delivery).toEqual(METHODS)
	})
	it("B2: without driverCardMode the methods do not change", () => {
		expect(visiblePaymentMethods(METHODS, null, null)).toEqual(METHODS)
		expect(visiblePaymentMethods(METHODS, null, { fulfillment: "pickup" })).toEqual(METHODS)
	})
})

describe("appTotalMismatch", () => {
	it("B3: 32.49 minus 0.50 against 3199 cents is fine, 3200 is a mismatch", () => {
		expect(appTotalMismatch(32.49, 0.5, 3199)).toBe(false)
		expect(appTotalMismatch(32.49, 0.5, 3200)).toBe(true)
	})
	it("is false when the app total is not an integer", () => {
		expect(appTotalMismatch(10, 0, null)).toBe(false)
		expect(appTotalMismatch(10, 0, undefined)).toBe(false)
		expect(appTotalMismatch(10, 0, 10.5)).toBe(false)
		expect(appTotalMismatch(10, 0, "1000")).toBe(false)
	})
})

describe("cartPlan", () => {
	const lines = [
		{ line_no: 2, product_id: "B", qty: 3 },
		{ line_no: 1, product_id: "A", qty: 1 },
	]
	it("orders lines by line_no", () => {
		const plan = cartPlan(lines, 0, "DELIVERY")
		expect(plan.entries).toEqual([
			{ code: "A", qty: 1, kind: "line" },
			{ code: "B", qty: 3, kind: "line" },
		])
		expect(plan.missingFee).toBe(false)
	})
	it("B4: delivery 0 has no fee line; delivery 300 without item is missingFee", () => {
		expect(cartPlan(lines, 0, null).entries.some((e) => e.kind === "fee")).toBe(false)
		const noItem = cartPlan(lines, 300, null)
		expect(noItem.missingFee).toBe(true)
		expect(noItem.entries.some((e) => e.kind === "fee")).toBe(false)
	})
	it("D-031a.10: delivery with item adds one fee line, qty 1, at the end", () => {
		const plan = cartPlan(lines, 300, "DELIVERY")
		expect(plan.entries[plan.entries.length - 1]).toEqual({ code: "DELIVERY", qty: 1, kind: "fee" })
		expect(plan.missingFee).toBe(false)
	})
	it("does not mutate the input", () => {
		const copy = JSON.parse(JSON.stringify(lines))
		cartPlan(lines, 0, null)
		expect(lines).toEqual(copy)
	})
})

describe("daysOld", () => {
	it("counts whole days", () => {
		expect(daysOld("2026-11-20", "2026-11-23")).toBe(3)
		expect(daysOld("2026-11-23", "2026-11-23")).toBe(0)
		expect(daysOld("2026-10-31", "2026-11-02")).toBe(2)
	})
	it("invalid or negative is 0", () => {
		expect(daysOld("nope", "2026-11-23")).toBe(0)
		expect(daysOld(null, "2026-11-23")).toBe(0)
		expect(daysOld("2026-11-25", "2026-11-23")).toBe(0)
	})
})

describe("texts", () => {
	it("fulfillmentText", () => {
		expect(fulfillmentText("delivery")).toBe("Delivery")
		expect(fulfillmentText("pickup")).toBe("Pickup")
		expect(fulfillmentText("x")).toBe("Unknown")
	})
	it("paymentText", () => {
		expect(paymentText("cash")).toBe("Pays cash")
		expect(paymentText("terminal")).toBe("Pays by card")
		expect(paymentText("online_card")).toBe("Paid online")
		expect(paymentText("x")).toBe("Payment not known")
	})
	it("syncWarningText", () => {
		expect(syncWarningText({ ok: true })).toBeNull()
		expect(syncWarningText({ ok: false, stopped: 1 })).toBe("App orders stopped syncing. Tell the owner.")
		expect(syncWarningText({ ok: false, stopped: 0 })).toBe(
			"App orders are not up to date. Tell the owner if this stays.",
		)
		expect(syncWarningText(null)).toBe("App orders are not up to date. Tell the owner if this stays.")
	})
})
