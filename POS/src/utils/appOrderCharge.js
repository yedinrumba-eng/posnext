import { ref } from "vue"
import { cartPlan } from "./appOrders"

// Charges one app order into the empty cart, one at a time (spec 031a4a).
// No toasts and no translations: it returns the outcome and the page says it.
export const CHARGE_TIMEOUT_MS = 20000

const TIMED_OUT = Symbol("timed_out")

export function createAppOrderCharger(deps, options = {}) {
	const busy = ref(false)
	const timeoutMs =
		typeof options.timeoutMs === "number" && options.timeoutMs > 0
			? options.timeoutMs
			: CHARGE_TIMEOUT_MS

	async function resolve(code) {
		try {
			return await deps.resolveItem(code)
		} catch (error) {
			return null
		}
	}

	async function charge(orderId) {
		if (busy.value) return "busy"
		if (!deps.isCartEmpty()) return "cart_not_empty"
		busy.value = true
		// One deadline for the whole call: every await races against this timer.
		let timer = null
		const deadline = new Promise((done) => {
			timer = setTimeout(() => done(TIMED_OUT), timeoutMs)
		})
		const within = (promise) => Promise.race([promise, deadline])
		try {
			deps.setUnresolved(null)

			let order = null
			try {
				order = await within(deps.loadOrder(orderId))
			} catch (error) {
				order = null
			}
			if (order === TIMED_OUT) return "timeout"
			if (!order) return "load_failed"
			if (order.chargeable !== true) {
				await within(deps.refresh())
				return "not_chargeable"
			}

			const plan = cartPlan(
				order.lines,
				order.delivery_cents,
				deps.deliveryFeeItem(),
			)
			const missing = []
			const resolved = []
			for (const entry of plan.entries) {
				const item = await within(resolve(entry.code))
				if (item === TIMED_OUT) return "timeout"
				if (item) resolved.push({ entry, item })
				else missing.push(entry.code)
			}

			if (!deps.isCartEmpty()) return "cart_not_empty"

			let added = 0
			for (const { entry, item } of resolved) {
				if (entry.kind !== "line") continue
				try {
					deps.addItem(item, entry.qty)
					added++
				} catch (error) {
					missing.push(entry.code)
				}
			}
			const isDelivery = order.fulfillment === "delivery"
			const fee = resolved.find(({ entry }) => entry.kind === "fee")
			let feeAdded = false
			if (fee && (added > 0 || isDelivery)) {
				try {
					deps.addItem(fee.item, fee.entry.qty)
					feeAdded = true
				} catch (error) {
					missing.push(fee.entry.code)
				}
			}

			if (added === 0) {
				const lineCodes = plan.entries
					.filter((entry) => entry.kind === "line")
					.map((entry) => entry.code)
				if (feeAdded) {
					deps.setAppOrder({
						order_id: order.order_id,
						short_code: order.short_code,
						fulfillment: order.fulfillment,
						total_cents: order.total_cents,
						tip_cents: order.tip_cents,
					})
					deps.setMissing(lineCodes)
					return "fee_only"
				}
				const codes = [...lineCodes]
				if (order.delivery_cents > 0) codes.push("delivery fee")
				deps.setUnresolved({
					order_id: order.order_id,
					codes,
					action: isDelivery ? "close_in_desk" : "sell_as_normal",
				})
				deps.setMissing([])
				return "nothing_resolved"
			}

			if (plan.missingFee) missing.push("delivery fee")
			deps.setAppOrder({
				order_id: order.order_id,
				short_code: order.short_code,
				fulfillment: order.fulfillment,
				total_cents: order.total_cents,
				tip_cents: order.tip_cents,
			})
			deps.setMissing(missing)
			return "charged"
		} finally {
			clearTimeout(timer)
			busy.value = false
		}
	}

	return { busy, charge }
}
