import { mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"

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

vi.mock("../data/session", () => ({
	session: {
		isLoggedIn: false,
		login: {
			error: null,
			loading: false,
			reset: mocks.resetLogin,
			submit: mocks.submitLogin,
		},
	},
}))

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

import Login from "./Login.vue"

const InputStub = {
	props: ["disabled", "label", "modelValue", "name", "placeholder", "type"],
	emits: ["update:modelValue"],
	template: `
		<label>
			<span>{{ label }}</span>
			<input
				:disabled="disabled"
				:name="name"
				:placeholder="placeholder"
				:type="type"
				:value="modelValue"
				@input="$emit('update:modelValue', $event.target.value)"
			/>
		</label>
	`,
}

const ButtonStub = {
	props: ["disabled", "loading", "type"],
	template: '<button :disabled="disabled" :type="type"><slot /></button>',
}

function mountLogin() {
	return mount(Login, {
		global: {
			components: {
				Button: ButtonStub,
				Input: InputStub,
			},
			config: {
				globalProperties: {
					__: (message) => message,
				},
			},
			stubs: {
				ShiftOpeningDialog: true,
			},
		},
	})
}

describe("Korvex POS login", () => {
	beforeEach(() => {
		vi.clearAllMocks()
	})

	it("identifies Korvex POS and submits the entered credentials", async () => {
		const wrapper = mountLogin()

		expect(wrapper.get("h1").text()).toBe("Korvex POS")
		expect(wrapper.text()).toContain("Punto de venta")

		const email = wrapper.get('input[name="email"]')
		const password = wrapper.get('input[name="password"]')
		expect(email.element.labels[0].textContent).toContain("Usuario o correo")
		expect(password.element.labels[0].textContent).toContain("Contraseña")

		await email.setValue("  cashier@example.com  ")
		await password.setValue("secret passphrase")
		await wrapper.get("form").trigger("submit")

		expect(mocks.submitLogin).toHaveBeenCalledOnce()
		expect(mocks.submitLogin).toHaveBeenCalledWith({
			email: "cashier@example.com",
			password: "secret passphrase",
		})
	})
})
