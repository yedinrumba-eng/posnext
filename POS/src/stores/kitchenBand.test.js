import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

// Spec 031b2a. `call` (POST) and `callGet` (GET) are faked and note which verb each method used.
const calls = []
const impl = { post: vi.fn(), get: vi.fn() }
vi.mock("@/utils/apiWrapper", () => ({
	call: (method, params) => {
		calls.push(["POST", method.split(".").pop()])
		return impl.post(method, params)
	},
	callGet: (method, params) => {
		calls.push(["GET", method.split(".").pop()])
		return impl.get(method, params)
	},
}))

const { useKitchenBandStore } = await import("./kitchenBand")

const SETUP_OK = { enabled: true, kitchen_item_groups: ["Hot Food"] }

beforeEach(() => {
	setActivePinia(createPinia())
	calls.length = 0
	impl.post.mockReset()
	impl.get.mockReset()
})

async function enabledStore() {
	impl.get.mockResolvedValue(SETUP_OK)
	const store = useKitchenBandStore()
	await store.loadSetup()
	calls.length = 0
	impl.get.mockReset()
	return store
}

describe("kitchenBand store verbs", () => {
	it("verbs: reads go by GET, retry and told by POST", async () => {
		impl.get.mockResolvedValueOnce(SETUP_OK).mockResolvedValueOnce({ enabled: true, rows: [] })
		impl.post.mockResolvedValue({ ok: true })
		const store = useKitchenBandStore()
		await store.loadSetup()
		await store.refresh("SHIFT-1", false)
		await store.retry("ACC-1")
		await store.markTold("ACC-1")
		expect(calls).toEqual([
			["GET", "get_kitchen_setup"],
			["GET", "get_kitchen_band"],
			["POST", "retry_counter_order"],
			["POST", "mark_told_in_person"],
		])
	})
})

describe("kitchenBand store poll", () => {
	it("poll offline: no call at all", async () => {
		const store = useKitchenBandStore()
		await store.poll("SHIFT-1", true)
		expect(calls).toEqual([])
	})

	it("poll retries setup once: two polls, two setups, no band", async () => {
		impl.get.mockRejectedValue(new Error("boom"))
		const store = useKitchenBandStore()
		await expect(store.poll("SHIFT-1", false)).resolves.toBeUndefined()
		await store.poll("SHIFT-1", false)
		expect(calls).toEqual([
			["GET", "get_kitchen_setup"],
			["GET", "get_kitchen_setup"],
		])
	})

	it("poll after enabled asks for the band and not the setup", async () => {
		const store = await enabledStore()
		impl.get.mockResolvedValue({ enabled: true, rows: [] })
		await store.poll("SHIFT-1", false)
		expect(calls).toEqual([["GET", "get_kitchen_band"]])
	})
})

describe("kitchenBand store band disabled", () => {
	it("band disabled: empty rows, enabled false and no groups", async () => {
		const store = await enabledStore()
		const rows = [{ invoice: "ACC-1", status: "Fallido", reason: "timeout", posting_time: "10:00:00" }]
		impl.get.mockResolvedValue({ enabled: true, rows })
		await store.refresh("SHIFT-1", false)
		expect(store.serverRows).toEqual(rows)
		impl.get.mockResolvedValue({ enabled: false })
		await store.refresh("SHIFT-1", false)
		expect(store.serverRows).toEqual([])
		expect(store.enabled).toBe(false)
		expect(store.kitchenItemGroups).toEqual([])
	})
})

describe("kitchenBand store busy", () => {
	it("busy: a second tap on the same row makes no call and returns null", async () => {
		const store = await enabledStore()
		let release
		impl.post.mockImplementation(
			() =>
				new Promise((resolve) => {
					release = resolve
				}),
		)
		const first = store.retry("ACC-1")
		expect(store.busy).toEqual(["ACC-1"])
		const second = await store.retry("ACC-1")
		expect(second).toBeNull()
		expect(impl.post).toHaveBeenCalledTimes(1)
		release({ queued: true })
		expect(await first).toBe(true)
		expect(store.busy).toEqual([])
		impl.post.mockResolvedValue({ queued: true })
		expect(await store.retry("ACC-1")).toBe(true)
		expect(impl.post).toHaveBeenCalledTimes(2)
	})

	it("busy per row: another invoice calls while the first is in flight", async () => {
		const store = await enabledStore()
		let release
		impl.post.mockImplementationOnce(
			() =>
				new Promise((resolve) => {
					release = resolve
				}),
		)
		const first = store.markTold("ACC-1")
		impl.post.mockResolvedValue({ ok: true })
		expect(await store.markTold("ACC-2")).toBe(true)
		expect(impl.post).toHaveBeenCalledTimes(2)
		release({ ok: true })
		await first
		expect(store.busy).toEqual([])
	})
})
