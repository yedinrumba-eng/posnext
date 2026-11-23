import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

// Static checks (the vitest environment is node, there is no DOM): closing a shift must wait for
// this shift's offline sales to reach the server (spec 048).
const read = (relative) => readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8")
const dialog = read("./ShiftClosingDialog.vue")

const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")

// The opening tag of the element whose @click is `handler`.
function tag(source, element, handler) {
	const match = source.match(new RegExp(`<${element}\\b[^>]*@click="${escape(handler)}"[^>]*>`))
	if (!match) throw new Error(`no <${element}> with @click="${handler}"`)
	return match[0]
}

// Body of `function NAME(`: from its opening brace to the first closing brace at column 0.
function body(source, name) {
	const start = source.search(new RegExp(`function ${name}\\(`))
	if (start === -1) throw new Error(`function ${name} not found`)
	const open = source.indexOf("{", start)
	const close = source.indexOf("\n}", open)
	return source.slice(open + 1, close)
}

// Text from `start` to the next "\n})".
function block(source, start) {
	const from = source.indexOf(start)
	if (from === -1) throw new Error(`${start} not found`)
	return source.slice(from, source.indexOf("\n})", from))
}

const increasing = (...indexes) =>
	indexes[0] > -1 && indexes.every((index, i) => i === 0 || index > indexes[i - 1])

describe("ShiftClosingDialog offline gate", () => {
	it("canSubmit is false first while offline sales block", () => {
		const lines = block(dialog, "const canSubmit = computed(() => {").split("\n")
		expect(lines.slice(1).join("\n").trimStart().startsWith("if (offlineBlock.value) return false")).toBe(true)
	})

	it("submitClosing re-reads the queue before the server call", () => {
		const text = body(dialog, "submitClosing")
		expect(
			increasing(
				text.indexOf("await syncStore.loadPendingInvoices()"),
				text.indexOf("if (offlineBlock.value) return"),
				text.indexOf("submitResource.submit("),
			),
		).toBe(true)
	})

	it("opening the dialog loads the queue before the shift data", () => {
		const text = block(dialog, "watch(open,")
		expect(
			increasing(text.indexOf("await syncStore.loadPendingInvoices()"), text.indexOf("loadClosingData()")),
		).toBe(true)
	})

	it("Sync now syncs, then reloads the queue and the shift data", () => {
		const button = tag(dialog, "Button", "syncNow")
		expect(button).toContain(':disabled="isOffline || isSyncing"')
		expect(button).toContain(':loading="isSyncing"')
		const text = body(dialog, "syncNow")
		expect(
			increasing(
				text.indexOf("syncStore.syncAllPending()"),
				text.indexOf("syncStore.loadPendingInvoices()"),
				text.indexOf("loadClosingData()"),
			),
		).toBe(true)
		expect(dialog).toContain('v-if="offlineBlock && !showSuccessReport"')
	})

	it("Sync now treats a returned failure as a failed sync", () => {
		const text = body(dialog, "syncNow")
		expect(
			increasing(
				text.indexOf("const result = await syncStore.syncAllPending()"),
				text.indexOf("if (result?.failed > 0) failed = true"),
				text.indexOf("} catch (error) {"),
			),
		).toBe(true)
		expect(text.split("failed = true").length - 1).toBe(2)
	})

	it("Sync now drops the stale shift data before reloading it", () => {
		const text = body(dialog, "syncNow")
		expect(
			increasing(
				text.indexOf("await syncStore.loadPendingInvoices()"),
				text.indexOf("closingData.value = null"),
				text.indexOf("await loadClosingData()"),
				text.indexOf("if (failed) {"),
			),
		).toBe(true)
		expect(
			increasing(
				dialog.indexOf('v-else-if="closingData"'),
				dialog.indexOf('v-else-if="closingDataResource.error || errorMessage"'),
			),
		).toBe(true)
	})

	it("a second Close Shift click while the queue is read does nothing", () => {
		expect(dialog).toContain("let closingLock = false")
		const text = body(dialog, "submitClosing")
		expect(
			increasing(
				text.indexOf("if (!closingData.value || closingLock) return"),
				text.indexOf("closingLock = true"),
				text.indexOf("await syncStore.loadPendingInvoices()"),
				text.indexOf("} finally {"),
				text.indexOf("closingLock = false"),
				text.indexOf("submitResource.submit("),
			),
		).toBe(true)
	})
})
