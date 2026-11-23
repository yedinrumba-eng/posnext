import { call, callGet } from "@/utils/apiWrapper"
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
	const busy = ref([])
	let timer = null

	async function loadSetup() {
		try {
			const setup = await callGet(`${METHOD}get_kitchen_setup`, {})
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
			const result = await callGet(`${METHOD}get_kitchen_band`, {
				pos_opening_shift: shift,
			})
			if (result?.enabled === false) {
				serverRows.value = []
				enabled.value = false
				kitchenItemGroups.value = []
			} else if (Array.isArray(result?.rows)) {
				serverRows.value = result.rows
			}
		} catch (error) {
			// keep the previous rows
		}
	}

	// null = this invoice already has a call in flight, nothing was sent
	async function send(method, invoice) {
		if (busy.value.includes(invoice)) return null
		busy.value = [...busy.value, invoice]
		try {
			await call(`${METHOD}${method}`, { invoice })
			return true
		} catch (error) {
			return false
		} finally {
			busy.value = busy.value.filter((name) => name !== invoice)
		}
	}

	const retry = (invoice) => send("retry_counter_order", invoice)
	const markTold = (invoice) => send("mark_told_in_person", invoice)

	// One polling step, never throws: at most one setup read and one band read per call
	async function poll(shift, isOffline) {
		try {
			if (isOffline) return
			if (!enabled.value) await loadSetup()
			if (!enabled.value) return
			await refresh(shift, isOffline)
		} catch (error) {
			// best effort: the next tick tries again
		}
	}

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
		busy,
		loadSetup,
		refresh,
		retry,
		markTold,
		poll,
		startPolling,
		stopPolling,
	}
})
