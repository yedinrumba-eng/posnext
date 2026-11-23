import { describe, expect, it } from "vitest"
import { closeBlockedByOffline, offlineSalesOfShift } from "./offlineCloseGate"

const sale = (shift, extra = {}) => ({ synced: false, data: { posa_pos_opening_shift: shift }, ...extra })

describe("offlineSalesOfShift", () => {
	it("counts pending and failed sales of the shift, not synced ones", () => {
		const queue = [sale("S1"), sale("S1", { sync_failed: true }), sale("S1", { synced: true })]
		expect(offlineSalesOfShift(queue, "S1")).toEqual({ pending: 1, failed: 1, total: 2 })
	})

	it("ignores sales of another shift", () => {
		const queue = [sale("S2"), sale("S2", { sync_failed: true })]
		expect(offlineSalesOfShift(queue, "S1")).toEqual({ pending: 0, failed: 0, total: 0 })
	})

	it("counts sales without a shift (fails closed)", () => {
		const queue = [{ synced: false, data: {} }, { synced: false }]
		expect(offlineSalesOfShift(queue, "S1")).toEqual({ pending: 2, failed: 0, total: 2 })
	})

	it("returns zeros when the queue is not an array", () => {
		const zero = { pending: 0, failed: 0, total: 0 }
		expect(offlineSalesOfShift([], "S1")).toEqual(zero)
		expect(offlineSalesOfShift(null, "S1")).toEqual(zero)
		expect(offlineSalesOfShift(undefined, "S1")).toEqual(zero)
	})
})

describe("closeBlockedByOffline", () => {
	it("blocks only when total is above zero", () => {
		expect(closeBlockedByOffline({ total: 1 })).toBe(true)
		expect(closeBlockedByOffline({ total: 0 })).toBe(false)
		expect(closeBlockedByOffline(null)).toBe(false)
	})
})
