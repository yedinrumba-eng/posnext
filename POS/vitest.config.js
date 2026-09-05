import vue from "@vitejs/plugin-vue"
import path from "node:path"
import { defineConfig } from "vitest/config"

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
		environment: "jsdom",
	},
	worker: {
		format: "es",
	},
})
