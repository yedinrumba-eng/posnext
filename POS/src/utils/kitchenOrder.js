// Pure helpers for the BODEGA counter orders (spec 031b2). No imports on purpose: vitest runs in
// node and the server (korvexcio, spec 031b1) decides what is kitchen and sends the order.

export const ORDER_TYPES = ["to_go", "dine_in"]
export const DEFAULT_ORDER_TYPE = "to_go"
export const CONFLICT_REASON = "http_409_idempotency_conflict"

const CANNOT_SEND_REASONS = [
	"invalid_key",
	"invalid_actor",
	"invalid_item_code",
	"invalid_name",
	"qty_out_of_range",
	"amount_out_of_range",
	"too_many_lines",
	"body_too_large",
	"missing_body",
]

// True when any cart line belongs to a kitchen item group (exact match, same as the server).
export function hasKitchenLines(items, groups) {
	if (!Array.isArray(items) || !Array.isArray(groups) || groups.length === 0)
		return false
	return items.some((item) => groups.includes(item?.item_group))
}

// One row per queued offline sale that carries an order type (those will go to the kitchen on sync).
export function offlineKitchenRows(entries) {
	if (!Array.isArray(entries)) return []
	return entries
		.filter((entry) => ORDER_TYPES.includes(entry?.data?.korvex_order_type))
		.map((entry) => ({
			key: entry.offline_id,
			kind: "offline",
			at: entry.timestamp,
		}))
}

// One row per invoice from get_kitchen_band. A 409 cannot be retried (the kitchen already holds that
// key with another body); every row can be marked as told in person.
export function serverKitchenRows(rows) {
	if (!Array.isArray(rows)) return []
	return rows.map((row) => ({
		key: row.invoice,
		kind: "server",
		invoice: row.invoice,
		status: row.status,
		reason: row.reason,
		at: row.posting_time,
		canRetry:
			row.status === "Pendiente" ||
			(row.status === "Fallido" && row.reason !== CONFLICT_REASON),
		canMarkTold: true,
	}))
}

// English text for a reason; the caller wraps it with __().
export function kitchenReasonText(reason) {
	const text = typeof reason === "string" ? reason : ""
	if (text === "network_error" || text === "timeout")
		return "No connection to the kitchen"
	if (
		text === "secret_missing" ||
		text.startsWith("http_503_server_misconfigured")
	) {
		return "Kitchen link is not set up. Tell the owner"
	}
	if (text.startsWith("http_503_ordering_unavailable"))
		return "The kitchen panel is closed"
	if (text.startsWith("http_429")) return "Too many orders. Retrying"
	if (text === CONFLICT_REASON)
		return "Order conflict. Tell the kitchen in person"
	if (text.startsWith("http_401"))
		return "The kitchen rejected the signature. Tell the owner"
	if (CANNOT_SEND_REASONS.includes(text))
		return "This sale cannot be sent. Tell the kitchen in person"
	if (text === "queued" || text === "manual_retry")
		return "Sending to the kitchen…"
	return "Error sending to the kitchen"
}
