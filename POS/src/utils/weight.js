// Weight entry helpers for the typed-weight prompt (S9.1). No imports on purpose.

export const MAX_WEIGHT_DECIMALS = 3

const WEIGHT_PATTERN = /^\d{1,3}(\.\d{0,3})?$/

/**
 * True only in kiosk mode, for an item whose UOM accepts fractions
 * and that is not a variant template, serial item or batch item.
 */
export function needsWeightPrompt(kiosk, item) {
	if (!Boolean(kiosk) || !item) return false
	const whole = item.uom_must_be_whole_number
	if (whole !== 0 && whole !== "0") return false
	return !item.has_variants && !item.has_serial_no && !item.has_batch_no
}

/**
 * Applies one key press of the on-screen keypad to the typed weight text.
 * Keys: "0"-"9", ".", "back", "clear".
 */
export function appendWeightKey(current, key) {
	if (key === "clear") return ""
	if (key === "back") return current.slice(0, -1)
	if (key === ".") {
		if (current.includes(".")) return current
		return current === "" ? "0." : `${current}.`
	}
	if (typeof key === "string" && /^[0-9]$/.test(key)) {
		const dot = current.indexOf(".")
		if (dot >= 0) {
			if (current.length - dot - 1 >= MAX_WEIGHT_DECIMALS) return current
		} else {
			if (current === "0") return key
			if (current.length >= 3) return current
		}
		return current + key
	}
	return current
}

/** Returns the weight as a number, or null when the text is not a valid weight. */
export function parseWeight(text) {
	if (typeof text !== "string" || !WEIGHT_PATTERN.test(text)) return null
	const value = Number(text)
	return value > 0 ? value : null
}
