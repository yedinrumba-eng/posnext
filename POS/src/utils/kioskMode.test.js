import { describe, expect, it } from "vitest"
import {
	gridColsClasses,
	itemNameClasses,
	itemPriceClasses,
	longPressEnabled,
	pickInitialItemGroup,
	shouldAutoSwitchToList,
	tabSizeClasses,
} from "./kioskMode"

describe("kioskMode", () => {
	it("makes the tabs touch sized in kiosk mode", () => {
		expect(tabSizeClasses(true)).toContain("min-h-[44px]")
		expect(tabSizeClasses(true)).toContain("text-base")
	})

	it("keeps today's classes when kiosk mode is off", () => {
		expect(tabSizeClasses(false)).toBe("px-2 sm:px-3 py-1.5 sm:py-2 text-[10px] sm:text-xs")
		expect(gridColsClasses(false)).toBe(
			"grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-1.5 sm:gap-2.5",
		)
		expect(itemNameClasses(false)).toBe(
			"text-[10px] sm:text-xs font-semibold text-gray-900 truncate mb-0.5 leading-tight",
		)
		expect(itemPriceClasses(false)).toBe("text-[9px] sm:text-[10px] text-gray-500 leading-tight")
		expect(longPressEnabled(false)).toBe(true)
		expect(longPressEnabled(true)).toBe(false)
	})

	it("wraps the item name on two lines in kiosk mode instead of truncating it", () => {
		expect(itemNameClasses(true)).toContain("line-clamp-2")
		expect(itemNameClasses(true)).not.toContain("truncate")
	})

	it("starts on the first Item Group in kiosk mode", () => {
		expect(pickInitialItemGroup(true, [{ item_group: "Beer" }], null)).toBe("Beer")
	})

	it("keeps the Item Group the cashier already picked", () => {
		expect(pickInitialItemGroup(true, [{ item_group: "Beer" }], "Ice")).toBe("Ice")
	})

	it("does not pick a group when kiosk mode is off", () => {
		expect(pickInitialItemGroup(false, [{ item_group: "Beer" }], null)).toBe(null)
	})

	it("picks nothing when there are no groups", () => {
		expect(pickInitialItemGroup(true, [], null)).toBe(null)
	})

	it("never auto-switches to the list in kiosk mode, otherwise keeps the old rule", () => {
		const base = { userManuallySetView: false, viewMode: "grid", threshold: 50 }
		expect(shouldAutoSwitchToList({ ...base, kiosk: true, itemCount: 500 })).toBe(false)
		expect(shouldAutoSwitchToList({ ...base, kiosk: false, itemCount: 51 })).toBe(true)
	})
})
