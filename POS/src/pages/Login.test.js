// @vitest-environment jsdom
import { enableAutoUnmount, flushPromises, mount } from "@vue/test-utils"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { nextTick } from "vue"

const mocks = vi.hoisted(() => ({
	clearCart: vi.fn(),
	ensureCSRFToken: vi.fn(),
	push: vi.fn(),
	resetAllDialogs: vi.fn(),
	resetLogin: vi.fn(),
	setCSRFToken: vi.fn(),
	submitLogin: vi.fn(),
}))

vi.mock("@/stores/posCart", () => ({
	usePOSCartStore: () => ({ clearCart: mocks.clearCart }),
}))

vi.mock("@/stores/posUI", () => ({
	usePOSUIStore: () => ({ resetAllDialogs: mocks.resetAllDialogs }),
}))

vi.mock("../composables/useShift", async () => {
	const { ref } = await import("vue")
	return {
		useShift: () => ({
			shiftState: ref({
				company: null,
				isOpen: false,
				pos_opening_shift: null,
				pos_profile: null,
			}),
		}),
	}
})

vi.mock("../components/ShiftOpeningDialog.vue", () => ({
	default: {
		name: "ShiftOpeningDialogStub",
		props: ["modelValue"],
		emits: ["update:modelValue", "shift-opened", "dialog-closed"],
		template: "<div />",
	},
}))

vi.mock("../data/session", async () => {
	const { reactive } = await import("vue")
	return {
		session: reactive({
			isLoggedIn: false,
			login: {
				error: null,
				loading: false,
				reset: mocks.resetLogin,
				submit: mocks.submitLogin,
			},
		}),
	}
})

vi.mock("../utils/csrf", () => ({
	ensureCSRFToken: mocks.ensureCSRFToken,
}))

vi.mock("../utils/offline/workerClient", () => ({
	offlineWorker: { setCSRFToken: mocks.setCSRFToken },
}))

vi.mock("vue-router", () => ({
	useRouter: () => ({ push: mocks.push }),
}))

vi.mock("frappe-ui", () => ({
	FeatherIcon: {
		props: ["name"],
		template: '<span aria-hidden="true" />',
	},
}))

import ShiftOpeningDialog from "../components/ShiftOpeningDialog.vue"
import { session } from "../data/session"
import Login from "./Login.vue"

enableAutoUnmount(afterEach)

function mountLogin() {
	return mount(Login, {
		global: {
			config: {
				globalProperties: {
					__: (message) => message,
				},
			},
		},
	})
}

function deferred() {
	let resolve
	const promise = new Promise((resolvePromise) => {
		resolve = resolvePromise
	})
	return { promise, resolve }
}

describe("KORVEXCIO point-of-sale login", () => {
	beforeEach(() => {
		vi.resetAllMocks()
		session.isLoggedIn = false
		session.login.error = null
		session.login.loading = false
		mocks.resetLogin.mockImplementation(() => {
			session.login.error = null
		})
		window.csrf_token = undefined
	})

	afterEach(() => {
		window.csrf_token = undefined
	})

	it("identifies Korvexcio and submits the entered credentials", async () => {
		const wrapper = mountLogin()

		expect(wrapper.get("h1").text()).toBe("KORVEXCIO")
		expect(wrapper.text()).toContain("Point of sale")

		const email = wrapper.get('input[name="email"]')
		const password = wrapper.get('input[name="password"]')
		expect(email.element.labels[0].textContent).toContain("Username or email")
		expect(password.element.labels[0].textContent).toContain("Password")

		await email.setValue("  cashier@example.com  ")
		await password.setValue("secret passphrase")
		await wrapper.get("form").trigger("submit")

		expect(mocks.submitLogin).toHaveBeenCalledOnce()
		expect(mocks.submitLogin).toHaveBeenCalledWith({
			email: "cashier@example.com",
			password: "secret passphrase",
		})
	})

	it("disables editing and submission while login is pending", async () => {
		const wrapper = mountLogin()
		session.login.loading = true
		await nextTick()

		for (const control of wrapper.findAll("input, button")) {
			expect(control.element.disabled).toBe(true)
		}
		expect(wrapper.get('button[type="submit"]').text()).toContain(
			"Signing in",
		)

		session.login.loading = false
		await nextTick()
		for (const control of wrapper.findAll("input, button")) {
			expect(control.element.disabled).toBe(false)
		}
	})

	it("announces login errors and clears them when credentials change", async () => {
		const wrapper = mountLogin()
		session.login.error = { messages: ["Credenciales inválidas"] }
		await nextTick()

		expect(wrapper.get('[role="alert"]').text()).toContain(
			"Credenciales inválidas",
		)
		await wrapper.get('input[name="email"]').setValue("cashier@example.com")
		expect(wrapper.find('[role="alert"]').exists()).toBe(false)
		expect(mocks.submitLogin).not.toHaveBeenCalled()
	})

	it("toggles password visibility without submitting or changing its value", async () => {
		const wrapper = mountLogin()
		const password = wrapper.get('input[name="password"]')
		await password.setValue("secret passphrase")

		await wrapper
			.get('button[aria-label="Show password"]')
			.trigger("click")
		expect(password.attributes("type")).toBe("text")
		expect(password.element.value).toBe("secret passphrase")

		await wrapper
			.get('button[aria-label="Hide password"]')
			.trigger("click")
		expect(password.attributes("type")).toBe("password")
		expect(password.element.value).toBe("secret passphrase")
		expect(mocks.submitLogin).not.toHaveBeenCalled()
	})

	it("waits for CSRF and worker synchronization before opening the shift dialog", async () => {
		const csrf = deferred()
		const worker = deferred()
		mocks.ensureCSRFToken.mockImplementation(async () => {
			await csrf.promise
			window.csrf_token = "test-only-csrf"
		})
		mocks.setCSRFToken.mockReturnValue(worker.promise)
		const wrapper = mountLogin()
		const dialog = wrapper.getComponent(ShiftOpeningDialog)

		session.isLoggedIn = true
		await nextTick()
		expect(mocks.ensureCSRFToken).toHaveBeenCalledOnce()
		expect(mocks.setCSRFToken).not.toHaveBeenCalled()
		expect(dialog.props("modelValue")).toBe(false)

		csrf.resolve()
		await flushPromises()
		expect(mocks.setCSRFToken).toHaveBeenCalledOnce()
		expect(mocks.setCSRFToken).toHaveBeenCalledWith("test-only-csrf")
		expect(dialog.props("modelValue")).toBe(false)
		expect(mocks.push).not.toHaveBeenCalled()

		worker.resolve()
		await flushPromises()
		expect(dialog.props("modelValue")).toBe(true)
		expect(mocks.push).not.toHaveBeenCalled()

		dialog.vm.$emit("shift-opened")
		await nextTick()
		expect(mocks.push).toHaveBeenCalledWith({ name: "POSSale" })
	})

	it.each(["cancelled", "resumed"])(
		"navigates to the sale when the shift dialog reports %s",
		async (reason) => {
			const wrapper = mountLogin()
			session.isLoggedIn = true
			await flushPromises()
			const dialog = wrapper.getComponent(ShiftOpeningDialog)

			dialog.vm.$emit("dialog-closed", { reason })
			await nextTick()
			expect(mocks.push).toHaveBeenCalledWith({ name: "POSSale" })
		},
	)

	it("navigates to the sale when an authenticated user dismisses the open dialog", async () => {
		const wrapper = mountLogin()
		session.isLoggedIn = true
		await flushPromises()
		const dialog = wrapper.getComponent(ShiftOpeningDialog)
		expect(dialog.props("modelValue")).toBe(true)

		dialog.vm.$emit("update:modelValue", false)
		await nextTick()
		expect(dialog.props("modelValue")).toBe(false)
		expect(mocks.push).toHaveBeenCalledWith({ name: "POSSale" })
	})
})
