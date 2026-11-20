import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const call = vi.fn()
vi.mock("@/utils/apiWrapper", () => ({ call: (...args) => call(...args) }))
vi.mock("@/utils/logger", () => ({
	logger: {
		create: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
	},
}))

import { printInvoiceByName, resolvePrintFormat } from "./printInvoice"

const INVOICE = { doctype: "Sales Invoice", name: "ACC-SINV-2026-00001", pos_profile: "POS Jael Deli" }
let open

// Answers the invoice and the profile the way the server does; `profile` may be an Error to reject.
function respond(invoice, profile) {
	call.mockImplementation(async (method) => {
		if (method === "pos_next.api.invoices.get_invoice") return invoice
		if (method === "frappe.client.get") {
			if (profile instanceof Error) throw profile
			return profile
		}
		throw new Error(`unexpected method ${method}`)
	})
}

const openedUrl = () => open.mock.calls[0][0]

beforeEach(() => {
	open = vi.fn(() => ({}))
	vi.stubGlobal("window", { open })
})

afterEach(() => {
	vi.unstubAllGlobals()
	call.mockReset()
})

describe("resolvePrintFormat", () => {
	it("an explicit format wins over the profile format", () => {
		expect(resolvePrintFormat("Custom Receipt", "POS Receipt US")).toBe("Custom Receipt")
	})

	it("falls back to the profile format when none is explicit", () => {
		expect(resolvePrintFormat(null, "POS Receipt US")).toBe("POS Receipt US")
	})

	it("falls back to the default when both are null, empty or blank", () => {
		expect(resolvePrintFormat(null, null)).toBe("POS Next Receipt")
		expect(resolvePrintFormat("", "")).toBe("POS Next Receipt")
		expect(resolvePrintFormat(undefined, "  ")).toBe("POS Next Receipt")
	})
})

describe("printInvoiceByName", () => {
	it("prints with the print format of the invoice's POS Profile", async () => {
		respond(INVOICE, { name: "POS Jael Deli", print_format: "POS Receipt US", letter_head: null })
		await printInvoiceByName("ACC-SINV-2026-00001")
		expect(open).toHaveBeenCalledTimes(1)
		expect(openedUrl()).toContain("format=POS+Receipt+US")
		expect(openedUrl()).toContain("name=ACC-SINV-2026-00001")
		expect(call).toHaveBeenCalledWith("frappe.client.get", {
			doctype: "POS Profile",
			name: "POS Jael Deli",
		})
	})

	it("uses the default format when the profile has no print_format", async () => {
		respond(INVOICE, { name: "POS Jael Deli", print_format: null, letter_head: null })
		await printInvoiceByName("ACC-SINV-2026-00001")
		expect(openedUrl()).toContain("format=POS+Next+Receipt")
	})

	it("prints with the default format when reading the profile fails", async () => {
		respond(INVOICE, new Error("Not permitted"))
		await expect(printInvoiceByName("ACC-SINV-2026-00001")).resolves.toBe(true)
		expect(openedUrl()).toContain("format=POS+Next+Receipt")
	})

	it("an explicit format wins and the profile is not read", async () => {
		respond(INVOICE, { name: "POS Jael Deli", print_format: "POS Receipt US", letter_head: null })
		await printInvoiceByName("ACC-SINV-2026-00001", "Custom Receipt")
		expect(openedUrl()).toContain("format=Custom+Receipt")
		expect(call).toHaveBeenCalledTimes(1)
	})

	it("does not read a profile when the invoice has none", async () => {
		respond({ doctype: "Sales Invoice", name: "ACC-SINV-2026-00001" }, null)
		await printInvoiceByName("ACC-SINV-2026-00001")
		expect(openedUrl()).toContain("format=POS+Next+Receipt")
		expect(call).toHaveBeenCalledTimes(1)
	})
})

describe("POSSale handlePrintInvoice", () => {
	it("always prints by name, with no branch for full documents", () => {
		const source = readFileSync(fileURLToPath(new URL("../pages/POSSale.vue", import.meta.url)), "utf8")
		const start = source.indexOf("async function handlePrintInvoice(")
		if (start === -1) throw new Error("handlePrintInvoice not found")
		const end = source.indexOf("\n}", start)
		const fn = source.slice(start, end)
		expect(fn).toContain("await printInvoiceByName(invoiceData.name)")
		expect(fn).not.toMatch(/\bprintInvoice\(/)
		expect(fn).not.toContain("invoiceData.items")
		expect(source).toContain('import { printInvoiceByName } from "@/utils/printInvoice";')
	})
})
