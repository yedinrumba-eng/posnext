import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

// Spec 031a4. Static checks (node, no DOM) of the dialog and of the wiring of app orders.
const read = (relative) =>
	readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8").replace(/\r/g, "")
const dialog = read("./AppOrdersDialog.vue")
const payment = read("./PaymentDialog.vue")
const page = read("../../pages/POSSale.vue")
const invoice = read("../../composables/useInvoice.js")
const cart = read("../../stores/posCart.js")
const ui = read("../../stores/posUI.js")

function body(source, name) {
	const start = source.search(new RegExp(`(async )?function ${name}\\(`))
	if (start === -1) throw new Error(`function ${name} not found`)
	const open = source.indexOf("{", start)
	let depth = 0
	for (let i = open; i < source.length; i++) {
		if (source[i] === "{") depth++
		if (source[i] === "}") {
			depth--
			if (depth === 0) return source.slice(open + 1, i)
		}
	}
	throw new Error("unbalanced")
}

describe("AppOrdersDialog.vue", () => {
	it("Charge button is disabled with a non-empty cart; no v-html", () => {
		expect(dialog).toContain(':disabled="!cartEmpty"')
		expect(dialog).toContain("Clear the cart first to charge an app order.")
		expect(dialog).not.toContain("v-html")
	})
	it("offline text, cancelled box and empty state are there", () => {
		expect(dialog).toContain("Offline: app orders load when the connection returns.")
		expect(dialog).toContain("Refund it with a return. Then it leaves this list.")
		expect(dialog).toContain("Cancelled in the app after it was charged")
		expect(dialog).toContain("No app orders to charge")
		expect(dialog).toContain("$emit('charge'")
	})
})

describe("POSSale.vue app orders wiring", () => {
	it("polls inside tick, after the kitchen band", () => {
		const tick = body(page, "tick")
		expect(tick).toContain("appOrders.poll(")
		expect(tick.indexOf("appOrders.poll(")).toBeGreaterThan(tick.indexOf("kitchenBand.poll("))
	})
	it("B8: emptying the cart unlinks the order", () => {
		const start = page.indexOf("() => cartStore.isEmpty")
		expect(start).toBeGreaterThan(-1)
		const watchBody = page.slice(start, start + 300)
		expect(watchBody).toContain("cartStore.setAppOrder(null)")
		expect(watchBody).toContain("appOrders.missing = []")
	})
	it("B8: the offline branch sets bodega_order_id before saveInvoiceOffline", () => {
		const handler = body(page, "handlePaymentCompleted")
		const set = handler.indexOf("invoiceData.bodega_order_id = cartStore.appOrder.order_id")
		expect(set).toBeGreaterThan(-1)
		expect(set).toBeLessThan(handler.indexOf("saveInvoiceOffline(invoiceData)"))
		expect(handler).toContain("cartStore.appOrder?.order_id")
	})
	it("passes the app order and the driver mode to the payment dialog", () => {
		expect(page).toContain(':app-order="cartStore.appOrder"')
		expect(page).toContain(':driver-card-mode="appOrders.driverCardMode"')
		expect(page).toContain('v-if="appOrders.enabled"')
		expect(page).toContain("uiStore.showAppOrdersDialog = true")
		expect(page).toContain('@charge="handleChargeAppOrder"')
	})
	it("handleChargeAppOrder: empty cart first, uses the cart plan and searchByBarcode", () => {
		const handler = body(page, "handleChargeAppOrder")
		expect(handler).toContain("cartStore.isEmpty")
		expect(handler).toContain("appOrders.loadOrder(")
		expect(handler).toContain("order.chargeable")
		expect(handler).toContain("cartPlan(order.lines, order.delivery_cents, appOrders.deliveryFeeItem)")
		expect(handler).toContain("itemStore.searchByBarcode(")
		expect(handler).toContain("needsWeightPrompt(")
		expect(handler).toContain("cartStore.addItem(item, entry.qty, true, shiftStore.currentProfile)")
	})
	it("no v-html was added to the page or the payment dialog", () => {
		expect(page).not.toContain("v-html")
		expect(payment).not.toContain("v-html")
	})
})

describe("PaymentDialog.vue app orders", () => {
	it("B9: no kitchen choice for an app order", () => {
		const start = payment.indexOf("const showKitchenChoice = computed")
		expect(start).toBeGreaterThan(-1)
		expect(payment.slice(start, start + 250)).toContain("!props.appOrder")
	})
	it("filters the methods and shows the warnings", () => {
		expect(payment).toContain("visiblePaymentMethods(")
		expect(payment).toContain("props.driverCardMode")
		expect(payment).toContain("appTotalMismatch(")
		expect(payment).toContain("Charge the register total.")
		expect(payment).toContain("It is not charged at the register.")
	})
})

describe("payload builders carry bodega_order_id", () => {
	it("B10: useInvoice sets it only inside the Sales Invoice if", () => {
		const fn = body(invoice, "submitInvoice")
		const set = fn.indexOf("invoiceData.bodega_order_id = bodegaOrderId")
		expect(set).toBeGreaterThan(-1)
		const guard = fn.slice(fn.lastIndexOf("if (", set), set)
		expect(guard).toContain('targetDoctype === "Sales Invoice"')
		expect(guard).toContain("bodegaOrderId")
		expect(fn.match(/bodega_order_id/g)).toHaveLength(1)
		expect(invoice).toMatch(/async function submitInvoice\([^)]*bodegaOrderId = null\)/)
		expect(body(invoice, "saveDraft")).not.toContain("bodega_order_id")
	})
	it("posCart holds the app order and passes it to submitInvoice", () => {
		expect(cart).toContain("const appOrder = ref(null)")
		expect(cart).toContain("function setAppOrder(")
		expect(cart).toContain("appOrder.value?.order_id ?? null")
		expect(body(cart, "clearCart")).toContain("appOrder.value = null")
		expect(cart).toMatch(/\n\t\tappOrder,\n\t\tsetAppOrder,/)
	})
	it("posUI registers the dialog and resets it", () => {
		expect(ui).toContain('useDialog("appOrders")')
		expect(ui).toContain("showAppOrdersDialog.value = false")
		expect(ui).toMatch(/\n\t\tshowAppOrdersDialog,/)
	})
})
