import { describe, expect, it } from "vitest"
import { createAppOrderCharger } from "./appOrderCharge"

// Spec 031a4a. The charger with fake deps that note their calls in order.
const ORDER = {
	order_id: "o1",
	short_code: "A1",
	fulfillment: "pickup",
	total_cents: 1000,
	tip_cents: 0,
	delivery_cents: 0,
	chargeable: true,
	lines: [{ line_no: 1, product_id: "BURGER", qty: 2 }],
}

function deferred() {
	let resolve
	const promise = new Promise((r) => {
		resolve = r
	})
	return { promise, resolve }
}

function setup(overrides = {}) {
	const log = []
	const state = { empty: true }
	const deps = {
		isCartEmpty: () => state.empty,
		loadOrder: async (id) => {
			log.push(["loadOrder", id])
			return ORDER
		},
		refresh: async () => {
			log.push(["refresh"])
		},
		deliveryFeeItem: () => "DELIVERY",
		resolveItem: async (code) => ({ item_code: code }),
		addItem: (item, qty) => {
			log.push(["addItem", item.item_code, qty])
		},
		setAppOrder: (value) => log.push(["setAppOrder", value]),
		setMissing: (codes) => log.push(["setMissing", codes]),
		setUnresolved: (value) => log.push(["setUnresolved", value]),
		...overrides,
	}
	return { charger: createAppOrderCharger(deps), log, state }
}

const names = (log, name) => log.filter((entry) => entry[0] === name)

describe("createAppOrderCharger", () => {
	it("C1 (B2): a second tap on the same order while the first is in flight gives busy", async () => {
		const gate = deferred()
		const { charger, log } = setup({
			loadOrder: async (id) => {
				log.push(["loadOrder", id])
				await gate.promise
				return ORDER
			},
		})
		const first = charger.charge("o1")
		expect(charger.busy.value).toBe(true)
		expect(await charger.charge("o1")).toBe("busy")
		gate.resolve()
		expect(await first).toBe("charged")
		expect(names(log, "loadOrder")).toHaveLength(1)
		expect(charger.busy.value).toBe(false)
	})

	it("C2 (B2): a tap on another order in flight gives busy and only the first order is charged", async () => {
		const gate = deferred()
		const { charger, log } = setup({
			loadOrder: async (id) => {
				log.push(["loadOrder", id])
				await gate.promise
				return { ...ORDER, order_id: id, lines: [{ line_no: 1, product_id: `ITEM-${id}`, qty: 1 }] }
			},
		})
		const first = charger.charge("o1")
		expect(await charger.charge("o2")).toBe("busy")
		gate.resolve()
		await first
		expect(names(log, "loadOrder")).toEqual([["loadOrder", "o1"]])
		expect(names(log, "addItem")).toEqual([["addItem", "ITEM-o1", 1]])
		expect(names(log, "setAppOrder")).toHaveLength(1)
		expect(names(log, "setAppOrder")[0][1].order_id).toBe("o1")
	})

	it("C3 (B3): loadOrder null or throwing gives load_failed and busy goes back to false", async () => {
		const a = setup({ loadOrder: async () => null })
		expect(await a.charger.charge("o1")).toBe("load_failed")
		expect(a.charger.busy.value).toBe(false)
		const b = setup({
			loadOrder: async () => {
				throw new Error("boom")
			},
		})
		expect(await b.charger.charge("o1")).toBe("load_failed")
		expect(b.charger.busy.value).toBe(false)
		expect(names(b.log, "setAppOrder")).toHaveLength(0)
	})

	it("C4: a cart that is not empty at the start gives cart_not_empty without loading", async () => {
		const { charger, log, state } = setup()
		state.empty = false
		expect(await charger.charge("o1")).toBe("cart_not_empty")
		expect(log).toEqual([])
		expect(charger.busy.value).toBe(false)
	})

	it("C5 (B4): a cart filled while the lines resolve adds and links nothing", async () => {
		const { charger, log, state } = setup({
			resolveItem: async (code) => {
				state.empty = false
				return { item_code: code }
			},
		})
		expect(await charger.charge("o1")).toBe("cart_not_empty")
		expect(names(log, "addItem")).toHaveLength(0)
		expect(names(log, "setAppOrder")).toHaveLength(0)
		expect(charger.busy.value).toBe(false)
	})

	it("C6: a not chargeable order refreshes once and links nothing", async () => {
		const { charger, log } = setup({
			loadOrder: async () => ({ ...ORDER, chargeable: false }),
		})
		expect(await charger.charge("o1")).toBe("not_chargeable")
		expect(names(log, "refresh")).toHaveLength(1)
		expect(names(log, "setAppOrder")).toHaveLength(0)
		expect(names(log, "addItem")).toHaveLength(0)
	})

	it("C7 (B5): no line resolves, even if the fee does: nothing added, nothing linked, unresolved set", async () => {
		const { charger, log } = setup({
			loadOrder: async () => ({
				...ORDER,
				delivery_cents: 300,
				lines: [{ line_no: 1, product_id: "bacon-egg-cheese", qty: 1 }],
			}),
			resolveItem: async (code) => (code === "DELIVERY" ? { item_code: code } : null),
		})
		expect(await charger.charge("o1")).toBe("nothing_resolved")
		expect(names(log, "addItem")).toHaveLength(0)
		expect(names(log, "setAppOrder")).toHaveLength(0)
		expect(names(log, "setUnresolved").at(-1)).toEqual([
			"setUnresolved",
			{ order_id: "o1", codes: ["bacon-egg-cheese", "delivery fee"] },
		])
		expect(names(log, "setMissing").at(-1)).toEqual(["setMissing", []])
		expect(charger.busy.value).toBe(false)
	})

	it("C8 (B6): when every addItem throws the fee is not added and nothing is linked", async () => {
		const { charger, log } = setup({
			loadOrder: async () => ({
				...ORDER,
				delivery_cents: 300,
				lines: [
					{ line_no: 1, product_id: "A", qty: 1 },
					{ line_no: 2, product_id: "B", qty: 1 },
				],
			}),
			addItem: (item) => {
				log.push(["addItem", item.item_code])
				throw new Error("cannot add")
			},
		})
		expect(await charger.charge("o1")).toBe("nothing_resolved")
		expect(names(log, "addItem").map((entry) => entry[1])).toEqual(["A", "B"])
		expect(names(log, "setAppOrder")).toHaveLength(0)
		expect(names(log, "setUnresolved").at(-1)[1].codes).toEqual(["A", "B", "delivery fee"])
	})

	it("C9: one of two lines resolves: charged, linked after the last addItem, the other goes to missing", async () => {
		const { charger, log } = setup({
			loadOrder: async () => ({
				...ORDER,
				lines: [
					{ line_no: 1, product_id: "BURGER", qty: 2 },
					{ line_no: 2, product_id: "bacon-egg-cheese", qty: 1 },
				],
			}),
			resolveItem: async (code) => (code === "bacon-egg-cheese" ? null : { item_code: code }),
		})
		expect(await charger.charge("o1")).toBe("charged")
		const order = log.map((entry) => entry[0])
		expect(order.lastIndexOf("addItem")).toBeLessThan(order.indexOf("setAppOrder"))
		expect(names(log, "setAppOrder")[0][1]).toEqual({
			order_id: "o1",
			short_code: "A1",
			fulfillment: "pickup",
			total_cents: 1000,
			tip_cents: 0,
		})
		expect(names(log, "setMissing").at(-1)).toEqual(["setMissing", ["bacon-egg-cheese"]])
	})
})
