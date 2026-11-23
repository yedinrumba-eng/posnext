<template>
	<Dialog
		v-model="show"
		:options="{ title: __('App orders'), size: 'lg' }"
	>
		<template #body-content>
			<div class="flex flex-col gap-3">
				<!-- Offline: nothing loads -->
				<div v-if="isOffline" class="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-yellow-800">
					{{ __("Offline: app orders load when the connection returns.") }}
				</div>

				<template v-else>
					<!-- Sync problem -->
					<div v-if="syncWarning" class="bg-red-50 border border-red-200 rounded-lg p-3 text-sm font-medium text-red-700">
						{{ __(syncWarning) }}
					</div>

					<!-- Cancelled in the app after it was charged -->
					<div v-if="cancelledAfterCharge.length > 0" class="bg-red-50 border border-red-200 rounded-lg p-3">
						<p class="text-sm font-semibold text-red-700">{{ __("Cancelled in the app after it was charged") }}</p>
						<div v-for="order in cancelledAfterCharge" :key="order.order_id" class="mt-2">
							<p class="text-sm text-red-700">#{{ order.short_code }} · {{ order.charged_invoice }}</p>
							<p class="text-xs text-red-600">{{ __("Refund it with a return. Then it leaves this list.") }}</p>
						</div>
					</div>

					<p v-if="toCharge.length > 0 && !cartEmpty" class="text-sm text-gray-600">
						{{ __("Clear the cart first to charge an app order.") }}
					</p>

					<p v-if="busy" class="text-sm text-gray-600">{{ __("Loading...") }}</p>

					<p v-if="truncated" class="text-sm font-medium text-yellow-800">
						{{ __("Showing {0} of {1} orders", [toCharge.length, toChargeTotal]) }}
					</p>

					<!-- Empty State -->
					<div v-if="toCharge.length === 0" class="text-center py-8">
						<p class="text-sm font-medium text-gray-900">{{ __("No app orders to charge") }}</p>
					</div>

					<!-- Orders to charge -->
					<div v-else class="flex flex-col gap-2 max-h-96 overflow-y-auto">
						<div
							v-for="order in toCharge"
							:key="order.order_id"
							class="bg-white border border-gray-200 rounded-lg p-3 flex items-center justify-between gap-3"
						>
							<div class="flex-1 min-w-0">
								<h4 class="text-sm font-semibold text-gray-900">
									#{{ order.short_code }} · {{ __(fulfillmentText(order.fulfillment)) }} · {{ order.status }}
								</h4>
								<p v-if="daysOld(order.service_day, today) > 0" class="text-xs text-red-600 mt-0.5">
									{{ __("{0} days old", [daysOld(order.service_day, today)]) }}
								</p>
								<p class="text-xs text-gray-500 mt-0.5">
									{{ formatCurrency(order.total_cents / 100) }} · {{ __(paymentText(order.payment)) }}
								</p>
								<p v-if="order.tip_cents > 0" class="text-xs text-gray-500 mt-0.5">
									{{ __("App tip {0}, not charged here", [formatCurrency(order.tip_cents / 100)]) }}
								</p>
								<p
									v-if="unresolved && unresolved.order_id === order.order_id && unresolved.action === 'close_in_desk'"
									class="text-xs text-red-600 mt-0.5"
								>
									{{ __("Not in the POS catalog: {0}. Do not charge it here. Ask the owner to close it in Desk.", [unresolved.codes.join(", ")]) }}
								</p>
								<p
									v-else-if="unresolved && unresolved.order_id === order.order_id"
									class="text-xs text-red-600 mt-0.5"
								>
									{{ __("Not in the POS catalog: {0}. Sell it as a normal sale. The order stays in this list until the owner closes it in Desk.", [unresolved.codes.join(", ")]) }}
								</p>
							</div>
							<button
								type="button"
								class="px-3 py-1.5 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
								:disabled="!cartEmpty || busy"
								@click="$emit('charge', order.order_id)"
							>
								{{ __("Charge") }}
							</button>
						</div>
					</div>
				</template>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { daysOld, fulfillmentText, paymentText, syncWarningText } from "@/utils/appOrders"
import { formatCurrency as formatCurrencyUtil } from "@/utils/currency"
import { Dialog } from "frappe-ui"
import { computed, ref, watch } from "vue"

const props = defineProps({
	modelValue: Boolean,
	toCharge: {
		type: Array,
		default: () => [],
	},
	cancelledAfterCharge: {
		type: Array,
		default: () => [],
	},
	sync: {
		type: Object,
		default: null,
	},
	isOffline: Boolean,
	cartEmpty: Boolean,
	busy: {
		type: Boolean,
		default: false,
	},
	toChargeTotal: {
		type: Number,
		default: 0,
	},
	truncated: {
		type: Boolean,
		default: false,
	},
	unresolved: {
		type: Object,
		default: null,
	},
	currency: {
		type: String,
		default: "USD",
	},
	today: {
		type: String,
		default: "",
	},
})

const emit = defineEmits(["update:modelValue", "charge"])

const show = ref(props.modelValue)

watch(
	() => props.modelValue,
	(val) => {
		show.value = val
	},
)

watch(show, (val) => {
	emit("update:modelValue", val)
})

const syncWarning = computed(() => syncWarningText(props.sync))

function formatCurrency(amount) {
	return formatCurrencyUtil(Number.parseFloat(amount || 0), props.currency)
}
</script>
