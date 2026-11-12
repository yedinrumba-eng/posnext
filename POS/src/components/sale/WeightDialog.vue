<template>
	<Dialog v-model="isOpen" :options="{ title: __('Enter weight'), size: 'sm' }">
		<template #body-content>
			<div class="py-2">
				<div v-if="item" class="mb-4 text-center">
					<h3 class="text-base font-semibold text-gray-900">{{ item.item_name }}</h3>
					<p class="text-sm text-gray-500">
						{{ formatCurrency(item.price_list_rate || item.rate || 0, currency) }} / {{ item.uom }}
					</p>
				</div>

				<div class="mb-4 rounded-lg bg-gray-50 py-3 text-center">
					<span class="text-4xl font-bold text-gray-900">{{ weightText || "0" }}</span>
					<span class="ms-2 text-lg text-gray-500">{{ item?.uom }}</span>
				</div>

				<div class="grid grid-cols-3 gap-2">
					<button
						v-for="key in keys"
						:key="key.value"
						type="button"
						class="min-h-[56px] text-2xl rounded-lg border border-gray-300 bg-white font-medium text-gray-800 active:bg-gray-100"
						@click="press(key.value)"
					>
						{{ key.label }}
					</button>
				</div>

				<div class="mt-3 flex gap-2">
					<Button class="flex-1" variant="subtle" @click="press('clear')">{{ __("Clear") }}</Button>
					<Button class="flex-1" variant="subtle" @click="cancel">{{ __("Cancel") }}</Button>
					<Button class="flex-1" variant="solid" :disabled="parsedWeight === null" @click="confirm">
						{{ __("Add") }}
					</Button>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { formatCurrency } from "@/utils/currency"
import { appendWeightKey, parseWeight } from "@/utils/weight"
import { Button, Dialog } from "frappe-ui"
import { computed, ref, watch } from "vue"

const props = defineProps({
	modelValue: Boolean,
	item: { type: Object, default: null },
	currency: String,
})

const emit = defineEmits(["update:modelValue", "confirm"])

const keys = [
	{ value: "1", label: "1" },
	{ value: "2", label: "2" },
	{ value: "3", label: "3" },
	{ value: "4", label: "4" },
	{ value: "5", label: "5" },
	{ value: "6", label: "6" },
	{ value: "7", label: "7" },
	{ value: "8", label: "8" },
	{ value: "9", label: "9" },
	{ value: ".", label: "." },
	{ value: "0", label: "0" },
	{ value: "back", label: "⌫" },
]

const weightText = ref("")

const isOpen = computed({
	get: () => props.modelValue,
	set: (value) => emit("update:modelValue", value),
})

const parsedWeight = computed(() => parseWeight(weightText.value))

watch(
	() => props.modelValue,
	(open) => {
		if (open) weightText.value = ""
	},
)

function press(key) {
	weightText.value = appendWeightKey(weightText.value, key)
}

function cancel() {
	isOpen.value = false
}

function confirm() {
	const weight = parsedWeight.value
	if (weight === null) return
	emit("confirm", weight)
	isOpen.value = false
}
</script>
