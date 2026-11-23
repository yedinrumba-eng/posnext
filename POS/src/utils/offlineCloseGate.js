/** Counts the unsynced offline sales of `shift` (or with no shift), split into pending and failed. */
export function offlineSalesOfShift(queue, shift) {
	let pending = 0
	let failed = 0
	if (Array.isArray(queue)) {
		for (const entry of queue) {
			if (entry?.synced === true) continue
			const entryShift = entry?.data?.posa_pos_opening_shift
			if (entryShift && entryShift !== shift) continue
			if (entry?.sync_failed === true) failed += 1
			else pending += 1
		}
	}
	return { pending, failed, total: pending + failed }
}

/** True when the counts say there is at least one offline sale still not on the server. */
export function closeBlockedByOffline(counts) {
	return Boolean(counts && counts.total > 0)
}
