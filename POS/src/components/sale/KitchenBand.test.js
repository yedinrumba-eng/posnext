import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

// Spec 031b2a. Static checks (node, no DOM) of the band and of how POSSale.vue drives it.
const read = (relative) =>
	readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8").replace(/\r/g, "")
const band = read("./KitchenBand.vue")
const page = read("../../pages/POSSale.vue")

function body(source, name) {
	const start = source.search(new RegExp(`function ${name}\\(`))
	if (start === -1) throw new Error(`function ${name} not found`)
	const open = source.indexOf("{", start)
	return source.slice(open + 1, source.indexOf("\n}", open))
}

describe("KitchenBand.vue busy", () => {
	it("both buttons are disabled while their invoice is in flight", () => {
		for (const emitName of ["retry", "told"]) {
			const match = band.match(new RegExp(`<button\\b[^>]*@click="emit\\('${emitName}'[^>]*>`))
			if (!match) throw new Error(`no ${emitName} button`)
			expect(match[0]).toContain(':disabled="busy.includes(row.invoice)"')
			expect(match[0]).toContain("disabled:opacity-50")
		}
		expect(band).toMatch(/busy:\s*\{\s*type: Array,\s*default: \(\) => \[\]/)
	})
})

describe("POSSale.vue kitchen wiring", () => {
	it("no setup load in onMounted; polling starts after the loading flag", () => {
		expect(page).not.toContain("kitchenBand.loadSetup")
		const loading = page.indexOf("uiStore.setLoading(false)")
		expect(loading).toBeGreaterThan(-1)
		expect(page.indexOf("kitchenBand.startPolling(tick)")).toBeGreaterThan(loading)
	})
	it("guards the unmount: flag set before stopPolling, check between the tick and startPolling", () => {
		const flag = page.indexOf("kitchenUnmounted = true")
		expect(flag).toBeGreaterThan(-1)
		expect(flag).toBeLessThan(page.indexOf("kitchenBand.stopPolling()"))
		const loading = page.indexOf("uiStore.setLoading(false)")
		const start = page.indexOf("kitchenBand.startPolling(tick)")
		const tail = page.slice(loading, start)
		const tickAt = tail.indexOf("await tick()")
		expect(tickAt).toBeGreaterThan(-1)
		expect(tail.indexOf("if (kitchenUnmounted) return")).toBeGreaterThan(tickAt)
	})
	it("handlers skip the rest on a null result and the band gets busy", () => {
		expect(body(page, "handleKitchenRetry")).toContain("if (result === null) return")
		expect(body(page, "handleKitchenTold")).toContain("if (result === null) return")
		expect(page).toContain(':busy="kitchenBand.busy"')
	})
	it("tick guards the offline queue read and polls through the store", () => {
		const fn = body(page, "tick")
		expect(fn).toMatch(/try \{\s*await offlineStore\.loadPendingInvoices\(\)/)
		expect(fn).toContain("kitchenBand.poll(")
	})
})
