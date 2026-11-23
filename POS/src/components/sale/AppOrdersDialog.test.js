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
		expect(dialog).toContain(':disabled="!cartEmpty || busy"')
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
	it("handleChargeAppOrder: delegates to the charger and shows the four toasts; the page keeps the lookups", () => {
		const handler = body(page, "handleChargeAppOrder")
		expect(handler).toContain("await chargeAppOrder(orderId)")
		expect(handler).toContain("Clear the cart first to charge an app order.")
		expect(handler).toContain("Could not load the app order. Try again.")
		expect(handler).toContain("This app order can no longer be charged.")
		expect(handler).toContain("No item of this order is in the POS catalog. See App orders.")
		expect(page).toContain("itemStore.searchByBarcode(")
		expect(page).toContain("needsWeightPrompt(")
		expect(page).toContain("cartStore.addItem(item, qty, true, shiftStore.currentProfile)")
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

// Spec 031a4a. Static checks of round 2.
describe("round 2 wiring (031a4a)", () => {
	it("T1 B1: loading a draft unlinks the app order before the items are replaced", () => {
		const handler = body(page, "handleLoadDraft")
		const swap = handler.indexOf("cartStore.invoiceItems = draftData.items")
		expect(swap).toBeGreaterThan(-1)
		const unlink = handler.indexOf("cartStore.setAppOrder(null)")
		const clear = handler.indexOf("appOrders.missing = []")
		expect(unlink).toBeGreaterThan(-1)
		expect(unlink).toBeLessThan(swap)
		expect(clear).toBeGreaterThan(-1)
		expect(clear).toBeLessThan(swap)
	})
	it("T2: the page replaces the items in one place; editing offline clears the cart first", () => {
		expect(page.match(/cartStore\.invoiceItems = /g)).toHaveLength(1)
		const edit = body(page, "handleEditOfflineInvoice")
		expect(edit).toContain("clearCart()")
		expect(edit.indexOf("clearCart()")).toBeLessThan(edit.indexOf("addItem("))
	})
	it("T3: the charge button is guarded by busy and the page wires the charger", () => {
		expect(dialog).toContain(':disabled="!cartEmpty || busy"')
		expect(page).toContain(':busy="appOrderBusy"')
		expect(page).toContain(':to-charge-total="appOrders.toChargeTotal"')
		expect(page).toContain(':truncated="appOrders.toChargeTruncated"')
		expect(page).toContain(':unresolved="appOrders.unresolved"')
		expect(page).toContain("createAppOrderCharger(")
		expect(page).not.toContain("cartPlan")
	})
	it("T4: the dialog says when the list is cut and what is missing; the menu counts the total", () => {
		expect(dialog).toContain('v-if="truncated"')
		expect(dialog).toContain('__("Showing {0} of {1} orders", [toCharge.length, toChargeTotal])')
		expect(dialog).toContain("Not in the POS catalog: {0}. Sell it as a normal sale. The order stays in this list until the owner closes it in Desk.")
		expect(dialog).toContain("unresolved.order_id === order.order_id")
		expect(page).toContain('v-if="appOrders.toChargeTotal > 0"')
		expect(page).toContain("{{ appOrders.toChargeTotal }}")
	})
	it("T5: the payment dialog picks and guards methods from the shown list", () => {
		expect(payment).not.toContain("paymentMethods.value.find(")
		expect(payment.match(/pickDefaultMethod\(filteredPaymentMethods\.value\)/g)).toHaveLength(3)
		expect(body(payment, "addCustomPayment")).toContain("isShownMethod(")
		expect(body(payment, "quickAddPayment")).toContain("isShownMethod(")
		expect(payment).toContain("Register total before tax {1}")
		expect(payment).not.toContain("Register total {1}.")
	})
})

// Spec 031a4b. Static checks of round 3.
describe("round 3 wiring (031a4b)", () => {
	it("T6 B8: the dialog says Loading... when busy and each action has its text", () => {
		expect(dialog).toContain('v-if="busy"')
		expect(dialog).toContain('__("Loading...")')
		expect(dialog).toContain("unresolved.action === 'close_in_desk'")
		expect(dialog).toContain("Do not charge it here. Ask the owner to close it in Desk.")
		expect(dialog).toContain("Sell it as a normal sale. The order stays in this list until the owner closes it in Desk.")
		expect(dialog).not.toContain("Add them by hand and charge as a normal sale")
	})
	it("T7: the page handles fee_only and timeout", () => {
		const handler = body(page, "handleChargeAppOrder")
		expect(handler).toContain('"fee_only"')
		expect(handler).toContain('"timeout"')
		expect(handler).toContain("Only the delivery fee was added. Add the products by hand, then charge.")
		expect(handler).toContain("The app order took too long to load. Try again.")
	})
})
