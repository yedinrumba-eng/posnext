<template>
	<main class="korvex-login">
		<div class="korvex-login__scene" aria-hidden="true">
			<span class="korvex-login__halo korvex-login__halo--blue" />
			<span class="korvex-login__halo korvex-login__halo--cyan" />
			<span class="korvex-login__halo korvex-login__halo--green" />
			<span class="korvex-login__orbit korvex-login__orbit--outer" />
			<span class="korvex-login__orbit korvex-login__orbit--middle" />
			<span class="korvex-login__orbit korvex-login__orbit--inner" />
			<span class="korvex-login__star korvex-login__star--one" />
			<span class="korvex-login__star korvex-login__star--two" />
			<span class="korvex-login__star korvex-login__star--three" />
		</div>

		<section class="korvex-login__card" aria-labelledby="login-title">
			<header class="korvex-login__brand">
				<img
					class="korvex-login__brand-mark"
					src="../assets/korvexcio-mark.svg"
					alt=""
					aria-hidden="true"
				/>
				<div class="korvex-login__brand-copy">
					<h1>{{ __("KORVEXCIO") }}</h1>
					<span>{{ __("Punto de venta") }}</span>
				</div>
			</header>

			<div class="korvex-login__intro">
				<h2 id="login-title">{{ __("Iniciar sesión") }}</h2>
				<p>{{ __("Accede a tu espacio de caja para continuar.") }}</p>
			</div>

			<form class="korvex-login__form" @submit.prevent="submit">
				<div v-if="session.login.error" class="korvex-login__error" role="alert">
					<FeatherIcon name="alert-circle" aria-hidden="true" :stroke-width="2" />
					<div>
						<strong>{{ __("No pudimos iniciar sesión") }}</strong>
						<p>{{ session.login.error.messages.join("\n") }}</p>
					</div>
				</div>

				<div class="korvex-login__field">
					<label for="korvex-login-email">{{ __("Usuario o correo") }}</label>
					<input
						id="korvex-login-email"
						v-model="loginForm.email"
						required
						autocomplete="username"
						name="email"
						type="text"
						:placeholder="__('Escribe tu usuario o correo')"
						:disabled="session.login.loading"
					/>
				</div>

				<div class="korvex-login__field">
					<label for="korvex-login-password">{{ __("Contraseña") }}</label>
					<span class="korvex-login__password">
						<input
							id="korvex-login-password"
							v-model="loginForm.password"
							required
							autocomplete="current-password"
							name="password"
							:type="showPassword ? 'text' : 'password'"
							:placeholder="__('Escribe tu contraseña')"
							:disabled="session.login.loading"
						/>
						<button
							type="button"
							class="korvex-login__password-toggle"
							:disabled="session.login.loading"
							:aria-label="showPassword ? __('Ocultar contraseña') : __('Mostrar contraseña')"
							@click="showPassword = !showPassword"
						>
							<FeatherIcon :name="showPassword ? 'eye-off' : 'eye'" aria-hidden="true" :stroke-width="2" />
						</button>
					</span>
				</div>

				<button
					type="submit"
					class="korvex-login__submit"
					:disabled="session.login.loading"
				>
					<span v-if="session.login.loading" class="korvex-login__spinner" aria-hidden="true" />
					{{ session.login.loading ? __("Iniciando sesión...") : __("Iniciar sesión") }}
				</button>
			</form>

			<footer>{{ __("Acceso autorizado para personal Korvex.") }}</footer>
		</section>

		<ShiftOpeningDialog
			v-model="showShiftDialog"
			@shift-opened="handleShiftOpened"
			@dialog-closed="handleDialogClosed"
		/>
	</main>
</template>

<script setup>
import { usePOSCartStore } from "@/stores/posCart"
import { usePOSUIStore } from "@/stores/posUI"
import { FeatherIcon } from "frappe-ui"
import { onMounted, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import ShiftOpeningDialog from "../components/ShiftOpeningDialog.vue"
import { useShift } from "../composables/useShift"
import { session } from "../data/session"
import { ensureCSRFToken } from "../utils/csrf"
import { offlineWorker } from "../utils/offline/workerClient"

const router = useRouter()
const { shiftState } = useShift()
const cartStore = usePOSCartStore()
const uiStore = usePOSUIStore()

const loginForm = reactive({
	email: "",
	password: "",
})

const showShiftDialog = ref(false)
const showPassword = ref(false)

// Reset state when login page mounts
onMounted(() => {
	// Clear login form
	loginForm.email = ""
	loginForm.password = ""
	showPassword.value = false

	// Clear any login errors
	if (session.login.error) {
		session.login.reset()
	}

	// Only clear state if user is NOT logged in
	// If user is already logged in (e.g., after successful login), don't clear their session
	if (!session.isLoggedIn) {
		showShiftDialog.value = false
		cartStore.clearCart()
		uiStore.resetAllDialogs()

		// Clear any stale shift state
		shiftState.value = {
			pos_opening_shift: null,
			pos_profile: null,
			company: null,
			isOpen: false,
		}
		localStorage.removeItem("pos_shift_data")
	}
})

function submit() {
	if (!loginForm.email || !loginForm.password) {
		return
	}

	session.login.submit({
		email: loginForm.email.trim(),
		password: loginForm.password,
	})
}

// Watch for successful login
watch(
	() => session.isLoggedIn,
	async (isLoggedIn) => {
		if (isLoggedIn) {
			// Initialize CSRF token after successful login
			try {
				console.log("User logged in, initializing CSRF token...")
				await ensureCSRFToken()

				// Sync CSRF token to worker for background API calls
				if (window.csrf_token) {
					await offlineWorker.setCSRFToken(window.csrf_token)
				}
			} catch (error) {
				console.error("Failed to initialize CSRF token after login:", error)
			}

			// Show shift opening dialog after successful login
			showShiftDialog.value = true
		}
	},
)

// Watch for dialog being closed via X button (v-model update)
// When user closes dialog without action, navigate to POSSale
watch(showShiftDialog, (isOpen, wasOpen) => {
	// Only navigate if dialog was open and is now closed, and user is logged in
	if (wasOpen === true && isOpen === false && session.isLoggedIn) {
		router.push({ name: "POSSale" })
	}
})

function handleShiftOpened() {
	// Navigate to POS sale after shift is opened
	router.push({ name: "POSSale" })
}

function handleDialogClosed({ reason }) {
	// Navigate to /pos when dialog is cancelled or resumed
	// "cancelled" means user closed dialog without action
	// "resumed" means user chose to resume existing shift
	// In both cases, navigate to POSSale (existing shift will be active)
	if (reason === "cancelled" || reason === "resumed") {
		router.push({ name: "POSSale" })
	}
}

// Clear error when user starts typing
watch([() => loginForm.email, () => loginForm.password], () => {
	if (session.login.error) {
		session.login.reset()
	}
})
</script>

<style scoped src="../styles/login-scene.css"></style>
<style scoped src="../styles/login.css"></style>
