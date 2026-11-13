import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

// Static checks (the vitest environment is node, there is no DOM): the three ways of taking a sale
// out of the offline queue must sit behind the allow_delete_offline_invoice flag (spec 007 S10.15).
const read = (relative) => readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8")
const dialog = read("./OfflineInvoicesDialog.vue")
const page = read("../../pages/POSSale.vue")

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

describe("OfflineInvoicesDialog delete gate", () => {
	it("hides edit and delete unless allowDelete", () => {
		expect(dialog).toMatch(/allowDelete:\s*\{\s*type:\s*Boolean,\s*default:\s*false,\s*\}/)
		expect(tag(dialog, "button", "deleteInvoice(invoice)")).toContain('v-if="allowDelete"')
		expect(tag(dialog, "button", "editInvoice(invoice)")).toContain('v-if="allowDelete"')
		expect(tag(dialog, "button", "viewDetails(invoice)")).not.toContain("v-if")
	})

	it("dialog actions return early without the flag", () => {
		for (const name of ["deleteInvoice", "editInvoice", "confirmDelete"]) {
			expect(body(dialog, name).trimStart().startsWith("if (!props.allowDelete) return")).toBe(true)
		}
	})

	it("POSSale passes the flag and gates every delete path", () => {
		const prop = ':allow-delete="posSettingsStore.allowDeleteOfflineInvoice"'
		expect(page.split(prop).length - 1).toBe(1)
		expect(tag(page, "Button", "handleDeleteFailedInvoice")).toContain(
			"posSettingsStore.allowDeleteOfflineInvoice",
		)
		for (const name of [
			"handleDeleteFailedInvoice",
			"handleEditOfflineInvoice",
			"handleDeleteOfflineInvoice",
		]) {
			expect(
				body(page, name)
					.trimStart()
					.startsWith("if (!posSettingsStore.allowDeleteOfflineInvoice) return;"),
			).toBe(true)
		}
	})

	it("only gated handlers remove a queued sale", () => {
		const call = "offlineStore.deleteOfflineInvoice("
		const gated = ["handleDeleteFailedInvoice", "handleEditOfflineInvoice", "handleDeleteOfflineInvoice"]
		const ranges = gated.map((name) => {
			const start = page.search(new RegExp(`function ${name}\\(`))
			const open = page.indexOf("{", start)
			return [open, page.indexOf("\n}", open)]
		})
		const positions = []
		for (let at = page.indexOf(call); at !== -1; at = page.indexOf(call, at + 1)) positions.push(at)
		expect(positions.length).toBe(3)
		for (const at of positions) {
			expect(ranges.some(([from, to]) => at > from && at < to)).toBe(true)
		}
	})
})
