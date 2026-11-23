// Pure rules of the BODEGA app orders in the POS (spec 031a4). No imports, no DOM.
export const METHOD = "korvexcio.bodega.app_order_api."
export const SETUP_CACHE_KEY = "korvexcio_app_orders_setup"

// Card (Driver) only shows when the cart comes from a delivery order (B1, B2)
export function visiblePaymentMethods(methods, driverCardMode, appOrder) {
	if (!driverCardMode) return methods
	if (appOrder?.fulfillment === "delivery") return methods
	return methods.filter((method) => method.mode_of_payment !== driverCardMode)
}

// True when the register net (before tax) differs from the app total, in cents (D-031a.14)
export function appTotalMismatch(subtotal, discount, appTotalCents) {
	if (!Number.isInteger(appTotalCents)) return false
	return (
		Math.round(subtotal * 100) - Math.round(discount * 100) !== appTotalCents
	)
}

// What goes into the cart: lines by line_no, then one delivery fee line with qty 1 (D-031a.10)
export function cartPlan(lines, deliveryCents, deliveryFeeItem) {
	const entries = [...(lines || [])]
		.sort((a, b) => a.line_no - b.line_no)
		.map((line) => ({ code: line.product_id, qty: line.qty, kind: "line" }))
	const hasFee = deliveryCents > 0
	if (hasFee && deliveryFeeItem) {
		entries.push({ code: deliveryFeeItem, qty: 1, kind: "fee" })
	}
	return { entries, missingFee: hasFee && !deliveryFeeItem }
}

const DAY_RE = /^\d{4}-\d{2}-\d{2}$/

function dayNumber(value) {
	if (typeof value !== "string" || !DAY_RE.test(value)) return null
	const [year, month, day] = value.split("-").map(Number)
	return Math.round(Date.UTC(year, month - 1, day) / 86400000)
}

export function daysOld(serviceDay, today) {
	const from = dayNumber(serviceDay)
	const to = dayNumber(today)
	if (from === null || to === null) return 0
	return Math.max(0, to - from)
}

export function fulfillmentText(value) {
	if (value === "delivery") return "Delivery"
	if (value === "pickup") return "Pickup"
	return "Unknown"
}

export function paymentText(value) {
	if (value === "cash") return "Pays cash"
	if (value === "terminal") return "Pays by card"
	if (value === "online_card") return "Paid online"
	return "Payment not known"
}

export function syncWarningText(sync) {
	if (sync?.ok === true) return null
	if (sync?.stopped) return "App orders stopped syncing. Tell the owner."
	return "App orders are not up to date. Tell the owner if this stays."
}

// The method to preselect from the methods that are shown (031a4a, B7)
export function pickDefaultMethod(methods) {
	if (!Array.isArray(methods) || methods.length === 0) return null
	return methods.find((method) => method.default) || methods[0]
}

// True only when the method is one of the shown methods (031a4a)
export function isShownMethod(methods, method) {
	if (!Array.isArray(methods) || !method) return false
	return methods.some((m) => m.mode_of_payment === method.mode_of_payment)
}
