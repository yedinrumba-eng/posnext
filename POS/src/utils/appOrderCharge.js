import { ref } from "vue"
import { cartPlan } from "./appOrders"

// Charges one app order into the empty cart, one at a time (spec 031a4a).
// No toasts and no translations: it returns the outcome and the page says it.
export function createAppOrderCharger(deps) {
	const busy = ref(false)

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
		try {
			deps.setUnresolved(null)

			let order = null
			try {
				order = await deps.loadOrder(orderId)
			} catch (error) {
				order = null
			}
			if (!order) return "load_failed"
			if (order.chargeable !== true) {
				await deps.refresh()
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
				const item = await resolve(entry.code)
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
			const fee = resolved.find(({ entry }) => entry.kind === "fee")
			if (fee && added > 0) {
				try {
					deps.addItem(fee.item, fee.entry.qty)
				} catch (error) {
					missing.push(fee.entry.code)
				}
			}

			if (added === 0) {
				const codes = plan.entries
					.filter((entry) => entry.kind === "line")
					.map((entry) => entry.code)
				if (order.delivery_cents > 0) codes.push("delivery fee")
				deps.setUnresolved({ order_id: order.order_id, codes })
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
			busy.value = false
		}
	}

	return { busy, charge }
}
