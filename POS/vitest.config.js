import vue from "@vitejs/plugin-vue"
import path from "node:path"
import { defineConfig } from "vitest/config"

const WEBSTORAGE_OFF = process.allowedNodeEnvironmentFlags.has("--experimental-webstorage") ? ["--no-experimental-webstorage"] : []

export default defineConfig({
	plugins: [vue()],
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "src"),
		},
	},
	optimizeDeps: {
		exclude: ["frappe-ui"],
	},
	test: {
		environment: "node",
		pool: "forks",
		poolOptions: { forks: { execArgv: WEBSTORAGE_OFF } },
	},
	worker: {
		format: "es",
	},
})
