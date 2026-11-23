import { beforeEach, describe, expect, it, vi } from "vitest"

// Spec 031b2a. frappe-ui is faked: `call` of frappe-ui always POSTs, `frappeRequest` takes a method.
const frappeCallMock = vi.fn()
const frappeRequestMock = vi.fn()
vi.mock("frappe-ui", () => ({
	call: (...args) => frappeCallMock(...args),
	frappeRequest: (...args) => frappeRequestMock(...args),
}))

const { call, callGet } = await import("./apiWrapper")

const SETUP = "korvexcio.bodega.counter_orders.get_kitchen_setup"

describe("callGet", () => {
	beforeEach(() => {
		frappeCallMock.mockReset()
		frappeRequestMock.mockReset()
	})

	it("sends one GET through frappeRequest and returns its value, without touching call", async () => {
		frappeRequestMock.mockResolvedValue({ enabled: false })
		const result = await callGet(SETUP, {})
		expect(frappeRequestMock).toHaveBeenCalledTimes(1)
		expect(frappeRequestMock).toHaveBeenCalledWith({ url: SETUP, method: "GET", params: {} })
		expect(result).toEqual({ enabled: false })
		expect(frappeCallMock).not.toHaveBeenCalled()
	})
})

describe("call", () => {
	beforeEach(() => {
		frappeCallMock.mockReset()
		frappeRequestMock.mockReset()
	})

	it("still goes through frappe-ui call with (method, params) and never frappeRequest", async () => {
		frappeCallMock.mockResolvedValue({ ok: true })
		const result = await call("some.method", { invoice: "ACC-1" })
		expect(frappeCallMock).toHaveBeenCalledWith("some.method", { invoice: "ACC-1" })
		expect(result).toEqual({ ok: true })
		expect(frappeRequestMock).not.toHaveBeenCalled()
	})
})
