import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const here = dirname(fileURLToPath(import.meta.url))
const pos = resolve(here, "../..")
const read = (rel) => readFileSync(resolve(pos, rel), "utf8")

const BANNED = ["POS Next", "POSNext", "4F46E5"]

const SPANISH_LOGIN_KEYS = [
	"Punto de venta",
	"Iniciar sesión",
	"Accede a tu espacio de caja para continuar.",
	"No pudimos iniciar sesión",
	"Usuario o correo",
	"Escribe tu usuario o correo",
	"Contraseña",
	"Escribe tu contraseña",
	"Ocultar contraseña",
	"Mostrar contraseña",
	"Iniciando sesión...",
	"Acceso autorizado para personal Korvex.",
]

describe("KORVEXCIO branding (spec 058b)", () => {
	it("index.html carries the KORVEXCIO identity", () => {
		const html = read("index.html")
		expect(html).toContain("<title>KORVEXCIO</title>")
		expect(html).toContain('content="KORVEXCIO"')
		expect(html).toContain('content="#2b44e6"')
		expect(html).toContain("/assets/pos_next/pos/icon.svg")
		for (const word of ["POSNext", "POS Next", "4F46E5"]) {
			expect(html).not.toContain(word)
		}
	})

	for (const file of [
		"src/components/pos/POSHeader.vue",
		"src/pages/Home.vue",
		"src/components/common/InstallAppBadge.vue",
		"src/pages/Login.vue",
	]) {
		it(`${file} has no legacy brand`, () => {
			const source = read(file)
			for (const word of BANNED) {
				expect(source).not.toContain(word)
			}
		})
	}

	for (const file of [
		"src/components/pos/POSHeader.vue",
		"src/pages/Home.vue",
		"src/components/common/InstallAppBadge.vue",
	]) {
		it(`${file} mentions KORVEXCIO`, () => {
			expect(read(file)).toContain("KORVEXCIO")
		})
	}

	it("manifest is named KORVEXCIO", () => {
		const config = read("vite.config.js")
		expect(config).toContain('name: "KORVEXCIO"')
		expect(config).toContain('short_name: "KORVEXCIO"')
		expect(config).toContain('theme_color: "#2b44e6"')
	})

	it("Login.vue uses English source keys only", () => {
		const login = read("src/pages/Login.vue")
		for (const key of SPANISH_LOGIN_KEYS) {
			expect(login).not.toContain(key)
		}
	})

	it("public icon is the KORVEXCIO mark", () => {
		expect(read("public/icon.svg")).toBe(read("src/assets/korvexcio-mark.svg"))
	})
})
