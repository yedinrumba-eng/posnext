<template>
	<div v-if="rows.length" class="bg-red-50 border-b border-red-300 px-4 py-2 text-sm text-red-900">
		<div class="flex flex-wrap items-baseline gap-x-2">
			<span class="font-semibold">{{ __("Did not reach the kitchen") }}</span>
			<span>{{ __("Tell the kitchen in person.") }}</span>
		</div>
		<ul class="mt-1 flex flex-col gap-1">
			<li v-for="row in rows" :key="row.key" class="flex flex-wrap items-center gap-2">
				<template v-if="row.kind === 'server'">
					<span class="font-medium">{{ row.invoice }}</span>
					<span>{{ __(kitchenReasonText(row.reason)) }}</span>
					<button
						v-if="row.canRetry"
						type="button"
						class="px-2 py-1 rounded bg-white border border-red-300 text-red-700 font-medium"
						@click="emit('retry', row.invoice)"
					>
						{{ __("Retry") }}
					</button>
					<button
						v-if="row.canMarkTold"
						type="button"
						class="px-2 py-1 rounded bg-white border border-red-300 text-red-700 font-medium"
						@click="emit('told', row.invoice)"
					>
						{{ __("Told the kitchen") }}
					</button>
				</template>
				<span v-else>{{ __("Offline sale: it goes to the kitchen when it syncs") }}</span>
			</li>
		</ul>
	</div>
</template>

<script setup>
import { kitchenReasonText } from "@/utils/kitchenOrder"

defineProps({
	rows: {
		type: Array,
		default: () => [],
	},
})

const emit = defineEmits(["retry", "told"])
</script>
