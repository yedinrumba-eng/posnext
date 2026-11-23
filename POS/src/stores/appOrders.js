import { callGet } from "@/utils/apiWrapper"
import { METHOD, SETUP_CACHE_KEY } from "../utils/appOrders"
import { defineStore } from "pinia"
import { ref } from "vue"

// App orders state (spec 031a4). Best effort: no call may throw into the POS.
export const useAppOrdersStore = defineStore("appOrders", () => {
	const enabled = ref(false)
	const driverCardMode = ref(null)
	const deliveryFeeItem = ref(null)
	const toCharge = ref([])
	const cancelledAfterCharge = ref([])
	const sync = ref(null)
	const missing = ref([])
	const toChargeTotal = ref(0)
	const toChargeTruncated = ref(false)
	const unresolved = ref(null)

	function clearState() {
		enabled.value = false
		driverCardMode.value = null
		deliveryFeeItem.value = null
		toCharge.value = []
		cancelledAfterCharge.value = []
		sync.value = null
		toChargeTotal.value = 0
		toChargeTruncated.value = false
		unresolved.value = null
	}

	function removeCache() {
		try {
			localStorage.removeItem(SETUP_CACHE_KEY)
		} catch (error) {
			// no storage: nothing to clear
		}
	}

	// D-031a.15: offline, Card (Driver) stays hidden on carts that are not delivery orders
	function applyCachedSetup() {
		try {
			const cached = JSON.parse(localStorage.getItem(SETUP_CACHE_KEY))
			if (cached?.enabled !== true) return
			enabled.value = true
			driverCardMode.value = cached.driver_card_mode ?? null
			deliveryFeeItem.value = cached.delivery_fee_item ?? null
		} catch (error) {
			// bad or missing cache: the feature stays off
		}
	}

	async function loadSetup() {
		try {
			const setup = await callGet(`${METHOD}get_app_orders_setup`, {})
			if (setup?.enabled === true) {
				enabled.value = true
				driverCardMode.value = setup.driver_card_mode ?? null
				deliveryFeeItem.value = setup.delivery_fee_item ?? null
				try {
					localStorage.setItem(
						SETUP_CACHE_KEY,
						JSON.stringify({
							enabled: true,
							driver_card_mode: driverCardMode.value,
							delivery_fee_item: deliveryFeeItem.value,
						}),
					)
				} catch (error) {
					// no storage: the cache is optional
				}
				return
			}
			if (setup?.enabled === false) {
				clearState()
				removeCache()
				return
			}
			applyCachedSetup()
		} catch (error) {
			applyCachedSetup()
		}
	}

	async function refresh() {
		try {
			const result = await callGet(`${METHOD}get_app_orders`, {})
			if (result?.enabled === false) {
				clearState()
				removeCache()
			} else if (
				Array.isArray(result?.to_charge) &&
				Array.isArray(result?.cancelled_after_charge)
			) {
				toCharge.value = result.to_charge
				cancelledAfterCharge.value = result.cancelled_after_charge
				sync.value = result.sync ?? null
				toChargeTotal.value = Number.isInteger(result.to_charge_total)
					? result.to_charge_total
					: result.to_charge.length
				toChargeTruncated.value = result.to_charge_truncated === true
				if (
					unresolved.value &&
					!result.to_charge.some(
						(order) => order.order_id === unresolved.value.order_id,
					)
				) {
					unresolved.value = null
				}
			}
		} catch (error) {
			// keep the previous lists
		}
	}

	// One polling step, never throws
	async function poll(isOffline) {
		try {
			if (isOffline) {
				if (!enabled.value) applyCachedSetup()
				return
			}
			if (!enabled.value) await loadSetup()
			if (enabled.value) await refresh()
		} catch (error) {
			// best effort: the next tick tries again
		}
	}

	async function loadOrder(orderId) {
		try {
			const order = await callGet(`${METHOD}get_app_order`, {
				order_id: orderId,
			})
			return order ?? null
		} catch (error) {
			return null
		}
	}

	return {
		enabled,
		driverCardMode,
		deliveryFeeItem,
		toCharge,
		cancelledAfterCharge,
		sync,
		missing,
		toChargeTotal,
		toChargeTruncated,
		unresolved,
		loadSetup,
		applyCachedSetup,
		refresh,
		poll,
		loadOrder,
	}
})
