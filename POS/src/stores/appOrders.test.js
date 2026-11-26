import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

// Spec 031a4. `call` (POST) and `callGet` (GET) are faked and note which verb each method used.
const calls = []
const impl = { post: vi.fn(), get: vi.fn() }
vi.mock("@/utils/apiWrapper", () => ({
	call: (method, params) => {
		calls.push(["POST", method.split(".").pop()])
		return impl.post(method, params)
	},
	callGet: (method, params) => {
		calls.push(["GET", method.split(".").pop()])
		return impl.get(method, params)
	},
}))

const { useAppOrdersStore } = await import("./appOrders")

const KEY = "korvexcio_app_orders_setup"
const SETUP_OK = { enabled: true, driver_card_mode: "Card (Driver)", delivery_fee_item: "DELIVERY" }
const LIST_OK = {
	enabled: true,
	to_charge: [{ order_id: "a", short_code: "A1" }],
	cancelled_after_charge: [{ order_id: "b", short_code: "B2", charged_invoice: "ACC-1" }],
	sync: { ok: true, stopped: 0, reason: null, last_success_at: "2026-11-23 10:00:00" },
}

let storage
beforeEach(() => {
	setActivePinia(createPinia())
	calls.length = 0
	impl.post.mockReset()
	impl.get.mockReset()
	storage = new Map()
	globalThis.localStorage = {
		getItem: (k) => (storage.has(k) ? storage.get(k) : null),
		setItem: (k, v) => storage.set(k, String(v)),
		removeItem: (k) => storage.delete(k),
	}
})

describe("appOrders store", () => {
	it("B7: the three reads go by GET and nothing goes by POST", async () => {
		impl.get
			.mockResolvedValueOnce(SETUP_OK)
			.mockResolvedValueOnce(LIST_OK)
			.mockResolvedValueOnce({ order_id: "a", chargeable: true })
		const store = useAppOrdersStore()
		await store.loadSetup()
		await store.refresh()
		await store.loadOrder("a")
		expect(calls).toEqual([
			["GET", "get_app_orders_setup"],
			["GET", "get_app_orders"],
			["GET", "get_app_order"],
		])
		expect(impl.get.mock.calls[2][1]).toEqual({ order_id: "a" })
	})

	it("loadSetup stores the setup and caches it", async () => {
		impl.get.mockResolvedValue(SETUP_OK)
		const store = useAppOrdersStore()
		await store.loadSetup()
		expect(store.enabled).toBe(true)
		expect(store.driverCardMode).toBe("Card (Driver)")
		expect(store.deliveryFeeItem).toBe("DELIVERY")
		expect(JSON.parse(storage.get(KEY)).enabled).toBe(true)
	})

	it("enabled false clears the state and the cache", async () => {
		const store = useAppOrdersStore()
		impl.get.mockResolvedValueOnce(SETUP_OK)
		await store.loadSetup()
		impl.get.mockResolvedValueOnce({ enabled: false })
		await store.loadSetup()
		expect(store.enabled).toBe(false)
		expect(store.driverCardMode).toBeNull()
		expect(storage.has(KEY)).toBe(false)
		impl.get.mockResolvedValueOnce(SETUP_OK)
		await store.loadSetup()
		impl.get.mockResolvedValueOnce({ enabled: false })
		await store.refresh()
		expect(store.enabled).toBe(false)
		expect(store.toCharge).toEqual([])
		expect(storage.has(KEY)).toBe(false)
	})

	it("B5: a failed setup read falls back to the cache", async () => {
		storage.set(KEY, JSON.stringify(SETUP_OK))
		impl.get.mockRejectedValue(new Error("offline"))
		const store = useAppOrdersStore()
		await expect(store.loadSetup()).resolves.toBeUndefined()
		expect(store.enabled).toBe(true)
		expect(store.driverCardMode).toBe("Card (Driver)")
	})

	it("a cache without enabled true or with junk is ignored", () => {
		const store = useAppOrdersStore()
		storage.set(KEY, "{not json")
		store.applyCachedSetup()
		expect(store.enabled).toBe(false)
		storage.set(KEY, JSON.stringify({ enabled: false, driver_card_mode: "X" }))
		store.applyCachedSetup()
		expect(store.enabled).toBe(false)
		expect(store.driverCardMode).toBeNull()
	})

	it("refresh keeps the previous lists when the read fails", async () => {
		impl.get.mockResolvedValueOnce(SETUP_OK).mockResolvedValueOnce(LIST_OK)
		const store = useAppOrdersStore()
		await store.loadSetup()
		await store.refresh()
		expect(store.toCharge).toHaveLength(1)
		expect(store.cancelledAfterCharge).toHaveLength(1)
		expect(store.sync.ok).toBe(true)
		impl.get.mockRejectedValueOnce(new Error("boom"))
		await store.refresh()
		expect(store.toCharge).toHaveLength(1)
	})

	it("B6: poll(true) never calls the server", async () => {
		storage.set(KEY, JSON.stringify(SETUP_OK))
		const store = useAppOrdersStore()
		await store.poll(true)
		expect(calls).toEqual([])
		expect(store.enabled).toBe(true)
	})

	it("poll online: setup then list when off, only the list when on, never throws", async () => {
		impl.get.mockResolvedValueOnce(SETUP_OK).mockResolvedValueOnce(LIST_OK)
		const store = useAppOrdersStore()
		await store.poll(false)
		expect(calls).toEqual([
			["GET", "get_app_orders_setup"],
			["GET", "get_app_orders"],
		])
		calls.length = 0
		impl.get.mockResolvedValueOnce(LIST_OK)
		await store.poll(false)
		expect(calls).toEqual([["GET", "get_app_orders"]])
		impl.get.mockRejectedValue(new Error("x"))
		await expect(store.poll(false)).resolves.toBeUndefined()
	})

	it("poll with the feature off stops after the setup read", async () => {
		impl.get.mockResolvedValue({ enabled: false })
		const store = useAppOrdersStore()
		await store.poll(false)
		expect(calls).toEqual([["GET", "get_app_orders_setup"]])
	})

	it("loadOrder returns null on failure", async () => {
		impl.get.mockRejectedValue(new Error("x"))
		const store = useAppOrdersStore()
		await expect(store.loadOrder("a")).resolves.toBeNull()
	})

	it("S1: refresh reads to_charge_total and to_charge_truncated", async () => {
		impl.get.mockResolvedValue({ ...LIST_OK, to_charge_total: 130, to_charge_truncated: true })
		const store = useAppOrdersStore()
		await store.refresh()
		expect(store.toChargeTotal).toBe(130)
		expect(store.toChargeTruncated).toBe(true)
	})

	it("S2: without those fields it falls back to the length and false", async () => {
		impl.get.mockResolvedValue(LIST_OK)
		const store = useAppOrdersStore()
		await store.refresh()
		expect(store.toChargeTotal).toBe(1)
		expect(store.toChargeTruncated).toBe(false)
	})

	it("S3: enabled false resets total, truncated and unresolved", async () => {
		impl.get.mockResolvedValueOnce({ ...LIST_OK, to_charge_total: 130, to_charge_truncated: true })
		const store = useAppOrdersStore()
		await store.refresh()
		store.unresolved = { order_id: "a", codes: ["x"] }
		impl.get.mockResolvedValueOnce({ enabled: false })
		await store.refresh()
		expect(store.toChargeTotal).toBe(0)
		expect(store.toChargeTruncated).toBe(false)
		expect(store.unresolved).toBeNull()
	})

	it("057a: loads removed lines once", async () => {
		const removed = [
			{ line_no: 1, product_id: "chicken-cutlet", qty: 1, line_cents: 999, removed_at: "2026-11-12T15:05:00.000Z" },
		]
		const LIST = {
			...LIST_OK,
			lines_changed_after_charge: [{ order_id: "c", short_code: "001", charged_invoice: "ACC-2" }],
		}
		const store = useAppOrdersStore()
		impl.get.mockImplementation(async (method) => {
			if (method.endsWith("get_app_orders")) return LIST
			throw new Error("down")
		})
		await store.refresh()
		expect(store.linesChangedAfterCharge).toEqual(LIST.lines_changed_after_charge)
		expect(store.removedLines).not.toHaveProperty("c")
		calls.length = 0
		impl.get.mockImplementation(async (method) => {
			if (method.endsWith("get_app_orders")) return LIST
			return { order_id: "c", removed_lines: removed }
		})
		await store.refresh()
		expect(store.removedLines.c).toEqual(removed)
		expect(calls.filter((c) => c[1] === "get_app_order")).toHaveLength(1)
		calls.length = 0
		await store.refresh()
		expect(calls.filter((c) => c[1] === "get_app_order")).toHaveLength(0)
		expect(calls.filter((c) => c[1] === "get_app_orders")).toHaveLength(1)
	})

	it("057a: old server without the key", async () => {
		impl.get.mockResolvedValue(LIST_OK)
		const store = useAppOrdersStore()
		await store.refresh()
		expect(store.linesChangedAfterCharge).toEqual([])
		expect(store.toCharge).toHaveLength(1)
		expect(calls).toEqual([["GET", "get_app_orders"]])
		impl.get.mockResolvedValueOnce({
			...LIST_OK,
			lines_changed_after_charge: [{ order_id: "c", short_code: "001", charged_invoice: "ACC-2" }],
		})
		impl.get.mockResolvedValueOnce({ order_id: "c", removed_lines: [] })
		await store.refresh()
		expect(store.removedLines.c).toEqual([])
		impl.get.mockResolvedValueOnce({ enabled: false })
		await store.refresh()
		expect(store.linesChangedAfterCharge).toEqual([])
		expect(store.removedLines).toEqual({})
	})

	it("S4: unresolved of an order that left the list is cleared; one still there stays", async () => {
		impl.get.mockResolvedValue(LIST_OK)
		const store = useAppOrdersStore()
		store.unresolved = { order_id: "a", codes: ["x"] }
		await store.refresh()
		expect(store.unresolved).toEqual({ order_id: "a", codes: ["x"] })
		store.unresolved = { order_id: "gone", codes: ["x"] }
		await store.refresh()
		expect(store.unresolved).toBeNull()
	})
})
