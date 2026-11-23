import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { createPinia, setActivePinia } from "pinia"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
	CONFLICT_REASON,
	DEFAULT_ORDER_TYPE,
	ORDER_TYPES,
	hasKitchenLines,
	kitchenReasonText,
	offlineKitchenRows,
	serverKitchenRows,
} from "./kitchenOrder"

// Spec 031b2 / 031b2a. The store is tested with fake `call` and `callGet` (no network); the .vue files and the invoice
// composable are checked statically because vitest runs in node without a DOM.
const callMock = vi.fn()
const getMock = vi.fn()
vi.mock("@/utils/apiWrapper", () => ({
	call: (...args) => callMock(...args),
	callGet: (...args) => getMock(...args),
}))

const { useKitchenBandStore } = await import("../stores/kitchenBand")

const read = (relative) =>
	readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8").replace(/\r\n/g, "\n")
const payment = read("../components/sale/PaymentDialog.vue")
const invoice = read("../composables/useInvoice.js")
const cart = read("../stores/posCart.js")
const page = read("../pages/POSSale.vue")
const band = read("../components/sale/KitchenBand.vue")

const METHOD = "korvexcio.bodega.counter_orders."

// Body of `function NAME(`: from its opening brace to the first closing brace at column 0 or, for
// a function nested one tab deep (the stores), at one tab.
function body(source, name, indent = "") {
	const start = source.search(new RegExp(`function ${name}\\(`))
	if (start === -1) throw new Error(`function ${name} not found`)
	const open = source.indexOf("{", start)
	const close = source.indexOf(`\n${indent}}`, open)
	return source.slice(open + 1, close)
}

describe("constants", () => {
	it("fixes the order types", () => {
		expect(ORDER_TYPES).toEqual(["to_go", "dine_in"])
		expect(DEFAULT_ORDER_TYPE).toBe("to_go")
		expect(CONFLICT_REASON).toBe("http_409_idempotency_conflict")
	})
})

describe("hasKitchenLines", () => {
	it("is true when an item group is a kitchen group (exact match)", () => {
		const items = [{ item_group: "Drinks" }, { item_group: "Hot Food" }]
		expect(hasKitchenLines(items, ["Hot Food"])).toBe(true)
	})
	it("is false without a match, without groups or with bad input", () => {
		const items = [{ item_group: "Drinks" }]
		expect(hasKitchenLines(items, ["Hot Food"])).toBe(false)
		expect(hasKitchenLines([{ item_group: "hot food" }], ["Hot Food"])).toBe(false)
		expect(hasKitchenLines(items, [])).toBe(false)
		expect(hasKitchenLines(items, null)).toBe(false)
		expect(hasKitchenLines(undefined, ["Hot Food"])).toBe(false)
	})
})

describe("offlineKitchenRows", () => {
	it("makes a row for each queued sale that carries an order type", () => {
		const entries = [
			{ offline_id: "a", timestamp: 1, data: { korvex_order_type: "dine_in" } },
			{ offline_id: "b", timestamp: 2, data: { items: [] } },
			{ offline_id: "c", timestamp: 3, data: { korvex_order_type: "bogus" } },
			{ offline_id: "d", timestamp: 4, data: { korvex_order_type: "to_go" } },
		]
		expect(offlineKitchenRows(entries)).toEqual([
			{ key: "a", kind: "offline", at: 1 },
			{ key: "d", kind: "offline", at: 4 },
		])
	})
	it("survives a missing list or entries without data", () => {
		expect(offlineKitchenRows(undefined)).toEqual([])
		expect(offlineKitchenRows([{ offline_id: "x" }])).toEqual([])
	})
})

describe("serverKitchenRows", () => {
	it("maps a pending and a failed row", () => {
		const rows = serverKitchenRows([
			{ invoice: "ACC-1", status: "Pendiente", reason: "network_error", posting_time: "10:00:00" },
			{ invoice: "ACC-2", status: "Fallido", reason: "timeout", posting_time: "10:01:00" },
		])
		expect(rows[0]).toEqual({
			key: "ACC-1",
			kind: "server",
			invoice: "ACC-1",
			status: "Pendiente",
			reason: "network_error",
			at: "10:00:00",
			canRetry: true,
			canMarkTold: true,
		})
		expect(rows[1].canRetry).toBe(true)
	})
	it("serverKitchenRows conflict: a 409 has no Retry but keeps Told", () => {
		const [row] = serverKitchenRows([
			{ invoice: "ACC-3", status: "Fallido", reason: CONFLICT_REASON, posting_time: "10:02:00" },
		])
		expect(row.canRetry).toBe(false)
		expect(row.canMarkTold).toBe(true)
	})
	it("a Pendiente row with reason queued stays in the band with Retry", () => {
		const [row] = serverKitchenRows([
			{ invoice: "ACC-4", status: "Pendiente", reason: "queued", posting_time: "10:03:00" },
		])
		expect(row.canRetry).toBe(true)
		expect(row.canMarkTold).toBe(true)
	})
	it("returns [] for a missing list", () => {
		expect(serverKitchenRows(undefined)).toEqual([])
	})
})

describe("kitchenReasonText", () => {
	const cases = [
		["network_error", "No connection to the kitchen"],
		["timeout", "No connection to the kitchen"],
		["secret_missing", "Kitchen link is not set up. Tell the owner"],
		["http_503_server_misconfigured", "Kitchen link is not set up. Tell the owner"],
		["http_503_ordering_unavailable", "The kitchen panel is closed"],
		["http_429", "Too many orders. Retrying"],
		[CONFLICT_REASON, "Order conflict. Tell the kitchen in person"],
		["http_401", "The kitchen rejected the signature. Tell the owner"],
		["invalid_key", "This sale cannot be sent. Tell the kitchen in person"],
		["invalid_actor", "This sale cannot be sent. Tell the kitchen in person"],
		["invalid_item_code", "This sale cannot be sent. Tell the kitchen in person"],
		["invalid_name", "This sale cannot be sent. Tell the kitchen in person"],
		["qty_out_of_range", "This sale cannot be sent. Tell the kitchen in person"],
		["amount_out_of_range", "This sale cannot be sent. Tell the kitchen in person"],
		["too_many_lines", "This sale cannot be sent. Tell the kitchen in person"],
		["body_too_large", "This sale cannot be sent. Tell the kitchen in person"],
		["missing_body", "This sale cannot be sent. Tell the kitchen in person"],
		["queued", "Sending to the kitchen\u2026"],
		["manual_retry", "Sending to the kitchen\u2026"],
	]
	for (const [reason, text] of cases) {
		it(`${reason} -> ${text}`, () => expect(kitchenReasonText(reason)).toBe(text))
	}
	it("unknown, empty and server-only reasons give the generic text", () => {
		for (const reason of ["something_new", "", null, undefined, "hook_error", "job_error"]) {
			expect(kitchenReasonText(reason)).toBe("Error sending to the kitchen")
		}
	})
})

describe("kitchenBand store", () => {
	beforeEach(() => {
		setActivePinia(createPinia())
		callMock.mockReset()
		getMock.mockReset()
	})
	afterEach(() => {
		vi.useRealTimers()
	})

	it("starts disabled", () => {
		const store = useKitchenBandStore()
		expect(store.enabled).toBe(false)
		expect(store.kitchenItemGroups).toEqual([])
		expect(store.serverRows).toEqual([])
	})

	it("loadSetup stores the groups when enabled", async () => {
		getMock.mockResolvedValue({ enabled: true, kitchen_item_groups: ["Hot Food"] })
		const store = useKitchenBandStore()
		await store.loadSetup()
		expect(getMock).toHaveBeenCalledWith(`${METHOD}get_kitchen_setup`, {})
		expect(store.enabled).toBe(true)
		expect(store.kitchenItemGroups).toEqual(["Hot Food"])
	})

	it("setup failure: an error, a disabled site or a bad shape leaves it off", async () => {
		const store = useKitchenBandStore()
		getMock.mockRejectedValue(new Error("not whitelisted"))
		await expect(store.loadSetup()).resolves.toBeUndefined()
		expect(store.enabled).toBe(false)
		for (const answer of [{ enabled: false }, { enabled: true }, null, undefined, "x"]) {
			getMock.mockResolvedValue(answer)
			await store.loadSetup()
			expect(store.enabled).toBe(false)
			expect(store.kitchenItemGroups).toEqual([])
		}
		getMock.mockClear()
		await store.refresh("SHIFT-1", false)
		expect(getMock).not.toHaveBeenCalled()
	})

	async function enabledStore() {
		getMock.mockResolvedValue({ enabled: true, kitchen_item_groups: ["Hot Food"] })
		const store = useKitchenBandStore()
		await store.loadSetup()
		getMock.mockReset()
		return store
	}

	it("refresh loads the band rows", async () => {
		const store = await enabledStore()
		const rows = [{ invoice: "ACC-1", status: "Fallido", reason: "timeout", posting_time: "10:00:00" }]
		getMock.mockResolvedValue({ enabled: true, rows })
		await store.refresh("SHIFT-1", false)
		expect(getMock).toHaveBeenCalledWith(`${METHOD}get_kitchen_band`, { pos_opening_shift: "SHIFT-1" })
		expect(store.serverRows).toEqual(rows)
	})

	it("refresh offline: no call, and no call without a shift", async () => {
		const store = await enabledStore()
		await store.refresh("SHIFT-1", true)
		await store.refresh(null, false)
		expect(getMock).not.toHaveBeenCalled()
	})

	it("refresh keeps the previous rows on an error or a bad shape", async () => {
		const store = await enabledStore()
		const rows = [{ invoice: "ACC-1", status: "Fallido", reason: "timeout", posting_time: "10:00:00" }]
		getMock.mockResolvedValue({ enabled: true, rows })
		await store.refresh("SHIFT-1", false)
		getMock.mockRejectedValue(new Error("boom"))
		await store.refresh("SHIFT-1", false)
		expect(store.serverRows).toEqual(rows)
	})

	it("retry and markTold call the server and never throw", async () => {
		const store = await enabledStore()
		callMock.mockResolvedValue({ queued: true })
		expect(await store.retry("ACC-1")).toBe(true)
		expect(callMock).toHaveBeenLastCalledWith(`${METHOD}retry_counter_order`, { invoice: "ACC-1" })
		callMock.mockResolvedValue({ ok: true })
		expect(await store.markTold("ACC-1")).toBe(true)
		expect(callMock).toHaveBeenLastCalledWith(`${METHOD}mark_told_in_person`, { invoice: "ACC-1" })
		callMock.mockRejectedValue(new Error("403"))
		expect(await store.retry("ACC-1")).toBe(false)
		expect(await store.markTold("ACC-1")).toBe(false)
	})

	it("polling: two startPolling calls leave one 60 s interval", () => {
		vi.useFakeTimers()
		const store = useKitchenBandStore()
		const tick = vi.fn()
		store.startPolling(tick)
		store.startPolling(tick)
		vi.advanceTimersByTime(60000)
		expect(tick).toHaveBeenCalledTimes(1)
		vi.advanceTimersByTime(60000)
		expect(tick).toHaveBeenCalledTimes(2)
		store.stopPolling()
		vi.advanceTimersByTime(180000)
		expect(tick).toHaveBeenCalledTimes(2)
		expect(vi.getTimerCount()).toBe(0)
	})
})

describe("PaymentDialog static checks", () => {
	it("shows the choice only for a Sales Invoice with kitchen lines (C2)", () => {
		expect(payment).toMatch(
			/showKitchenChoice\s*=\s*computed\(\(\)\s*=>\s*props\.targetDoctype === "Sales Invoice"\s*&&\s*hasKitchenLines\(props\.items, props\.kitchenItemGroups\)/,
		)
		expect(payment).toMatch(/kitchenItemGroups:\s*\{\s*type: Array,\s*default: \(\) => \[\]/)
	})
	it("resets the choice when the dialog opens", () => {
		const watchBlock = payment.slice(payment.indexOf("watch(() => props.modelValue, (isOpen) => {"))
		expect(watchBlock.slice(0, 400)).toContain("kitchenOrderType.value = DEFAULT_ORDER_TYPE")
	})
	it("puts the buttons before both completion buttons, on one ref", () => {
		const choice = [...payment.matchAll(/v-if="showKitchenChoice"/g)].map((m) => m.index)
		expect(choice).toHaveLength(2)
		expect(choice[0]).toBeLessThan(payment.indexOf("<!-- Complete Payment Button -->"))
		expect(choice[1]).toBeLessThan(payment.indexOf("<!-- Complete/Partial Payment Button -->"))
		expect(payment).toContain("__('To go')")
		expect(payment).toContain("__('Dine in')")
	})
	it("both paymentData carry kitchen_order_type, null when there is no choice (C1)", () => {
		const expected = "kitchen_order_type: showKitchenChoice.value ? kitchenOrderType.value : null"
		expect(body(payment, "addCreditAccountPayment")).toContain(expected)
		expect(body(payment, "completePayment")).toContain(expected)
	})
})

describe("useInvoice and posCart static checks", () => {
	it("submitInvoice sets korvex_order_type only for a Sales Invoice with a valid type", () => {
		expect(invoice).toContain(
			'async function submitInvoice(targetDoctype = "Sales Invoice", deliveryDate = null, kitchenOrderType = null)',
		)
		expect(invoice).toMatch(
			/if \(targetDoctype === "Sales Invoice" && ORDER_TYPES\.includes\(kitchenOrderType\)\) \{\s*invoiceData\.korvex_order_type = kitchenOrderType/,
		)
	})
	it("saveDraft never sends the order type", () => {
		const draft = invoice.slice(invoice.indexOf("async function saveDraft"), invoice.indexOf("async function submitInvoice"))
		expect(draft.length).toBeGreaterThan(100)
		expect(draft).not.toContain("korvex_order_type")
	})
	it("posCart keeps, passes, clears and exports the type", () => {
		expect(cart).toContain("const kitchenOrderType = ref(null)")
		expect(cart).toMatch(/function setKitchenOrderType\(value\)/)
		expect(cart).toContain("baseSubmitInvoice(targetDoctype.value, deliveryDate.value, kitchenOrderType.value)")
		expect(body(cart, "clearCart", "\t")).toContain("kitchenOrderType.value = null")
		expect(cart).toMatch(/\n\t\tkitchenOrderType,\n\t\tsetKitchenOrderType,/)
	})
})

describe("POSSale static checks", () => {
	it("handlePaymentCompleted sets the type first and the offline payload carries it only when chosen (C4)", () => {
		const fn = body(page, "handlePaymentCompleted")
		expect(fn).toContain("cartStore.setKitchenOrderType(paymentData.kitchen_order_type ?? null)")
		expect(fn.indexOf("cartStore.setKitchenOrderType(")).toBeLessThan(fn.indexOf("const customerValue"))
		expect(fn).toMatch(
			/if \(paymentData\.kitchen_order_type\) \{\s*invoiceData\.korvex_order_type = paymentData\.kitchen_order_type/,
		)
		expect(fn.indexOf("await offlineStore.saveInvoiceOffline(invoiceData)")).toBeLessThan(fn.indexOf("tick()"))
	})
	it("a sale without kitchen lines has no korvex_order_type in the literal payload", () => {
		const fn = body(page, "handlePaymentCompleted")
		const from = fn.indexOf("const invoiceData = {")
		const literal = fn.slice(from, fn.indexOf("};", from))
		expect(literal.length).toBeGreaterThan(100)
		expect(literal).not.toContain("korvex_order_type")
	})
	it("wires the band, the polling and the dialog prop", () => {
		expect(page).toContain("<KitchenBand")
		expect(page.indexOf("</POSHeader>")).toBeLessThan(page.indexOf("<KitchenBand"))
		expect(page.indexOf("<KitchenBand")).toBeLessThan(page.indexOf("<!-- Main Content: Responsive Layout -->"))
		expect(page).toContain(':kitchen-item-groups="kitchenBand.kitchenItemGroups"')
		expect(page).toContain("kitchenBand.startPolling(tick)")
		expect(page).toContain("kitchenBand.stopPolling()")
		expect(page).toContain("kitchenBand.poll(cartStore.posOpeningShift, offlineStore.isOffline)")
		expect(page).toContain("offlineStore.pendingInvoicesCount")
		expect(page).toContain('__("Could not update. Tell the kitchen in person")')
	})
})

describe("KitchenBand.vue static checks", () => {
	it("renders nothing without rows and has the texts and buttons", () => {
		expect(band).toContain('v-if="rows.length"')
		expect(band).toContain("bg-red-50 border-b border-red-300")
		for (const text of [
			"Did not reach the kitchen",
			"Tell the kitchen in person.",
			"Retry",
			"Told the kitchen",
			"Offline sale: it goes to the kitchen when it syncs",
		]) {
			expect(band).toContain(`__("${text}")`)
		}
		expect(band).toContain('v-if="row.canRetry"')
		expect(band).toContain('v-if="row.canMarkTold"')
		expect(band).toContain("__(kitchenReasonText(row.reason))")
	})
})
