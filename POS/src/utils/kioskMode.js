/**
 * Pure helpers for the kiosk grid mode (POS Settings: kiosk_mode).
 *
 * No Vue imports on purpose: ItemsSelector.vue only calls these functions,
 * so the rebase against upstream touches as few lines of it as possible.
 * With kiosk mode off every function returns exactly what the component
 * used before, so sites that do not turn it on look the same.
 */

const TAB_KIOSK = "min-h-[44px] px-4 py-2.5 text-base"
const TAB_DEFAULT = "px-2 sm:px-3 py-1.5 sm:py-2 text-[10px] sm:text-xs"

const GRID_KIOSK = "grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3"
const GRID_DEFAULT =
	"grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-1.5 sm:gap-2.5"

const NAME_KIOSK = "text-base font-semibold text-gray-900 line-clamp-2 mb-1 leading-snug"
const NAME_DEFAULT =
	"text-[10px] sm:text-xs font-semibold text-gray-900 truncate mb-0.5 leading-tight"

const PRICE_KIOSK = "text-base text-gray-700 leading-tight"
const PRICE_DEFAULT = "text-[9px] sm:text-[10px] text-gray-500 leading-tight"

export function tabSizeClasses(kiosk) {
	return kiosk ? TAB_KIOSK : TAB_DEFAULT
}

export function gridColsClasses(kiosk) {
	return kiosk ? GRID_KIOSK : GRID_DEFAULT
}

export function itemNameClasses(kiosk) {
	return kiosk ? NAME_KIOSK : NAME_DEFAULT
}

export function itemPriceClasses(kiosk) {
	return kiosk ? PRICE_KIOSK : PRICE_DEFAULT
}

export function longPressEnabled(kiosk) {
	return !kiosk
}

/**
 * In kiosk mode the grid starts on the first Item Group instead of
 * "All Items". Anything the cashier already picked is kept.
 */
export function pickInitialItemGroup(kiosk, groups, current) {
	if (kiosk && current == null && groups.length > 0) {
		return groups[0].item_group
	}
	return current
}

/**
 * Kiosk mode never jumps from the grid to the list view on its own,
 * however many Items the catalog has.
 */
export function shouldAutoSwitchToList({
	kiosk,
	userManuallySetView,
	viewMode,
	itemCount,
	threshold,
}) {
	if (kiosk) {
		return false
	}
	return !userManuallySetView && viewMode === "grid" && itemCount > threshold
}
