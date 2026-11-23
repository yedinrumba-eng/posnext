import { call } from "@/utils/apiWrapper"
import { defineStore } from "pinia"
import { ref } from "vue"

// Kitchen band state (spec 031b2). Everything here is best effort: a sale never waits for the kitchen
// and no call may throw into the POS.
const METHOD = "korvexcio.bodega.counter_orders."
const POLL_MS = 60000

export const useKitchenBandStore = defineStore("kitchenBand", () => {
	const enabled = ref(false)
	const kitchenItemGroups = ref([])
	const serverRows = ref([])
	let timer = null

	async function loadSetup() {
		try {
			const setup = await call(`${METHOD}get_kitchen_setup`, {})
			if (setup?.enabled === true && Array.isArray(setup.kitchen_item_groups)) {
				enabled.value = true
				kitchenItemGroups.value = setup.kitchen_item_groups
				return
			}
		} catch (error) {
			// not installed or not whitelisted on this site: the feature stays off
		}
		enabled.value = false
		kitchenItemGroups.value = []
	}

	async function refresh(shift, isOffline) {
		if (!enabled.value || !shift || isOffline) return
		try {
			const result = await call(`${METHOD}get_kitchen_band`, {
				pos_opening_shift: shift,
			})
			if (Array.isArray(result?.rows)) serverRows.value = result.rows
		} catch (error) {
			// keep the previous rows
		}
	}

	async function send(method, invoice) {
		try {
			await call(`${METHOD}${method}`, { invoice })
			return true
		} catch (error) {
			return false
		}
	}

	const retry = (invoice) => send("retry_counter_order", invoice)
	const markTold = (invoice) => send("mark_told_in_person", invoice)

	function startPolling(tick) {
		if (timer !== null) return
		timer = setInterval(tick, POLL_MS)
	}

	function stopPolling() {
		if (timer === null) return
		clearInterval(timer)
		timer = null
	}

	return {
		enabled,
		kitchenItemGroups,
		serverRows,
		loadSetup,
		refresh,
		retry,
		markTold,
		startPolling,
		stopPolling,
	}
})
