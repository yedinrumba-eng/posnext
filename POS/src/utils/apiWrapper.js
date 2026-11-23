import { call as frappeCall, frappeRequest } from "frappe-ui"

import { forceRefreshCSRFToken, isCSRFApiError } from "./csrf"

// Wrapped call function with CSRF auto-refresh
export async function call(method, params) {
	try {
		return await frappeCall(method, params)
	} catch (error) {
		if (isCSRFApiError(error)) {
			console.warn(
				"CSRF token error in call(), refreshing token and retrying...",
			)
			const refreshed = await forceRefreshCSRFToken()

			if (refreshed) {
				console.log("Retrying call after CSRF refresh...")
				return await frappeCall(method, params)
			}

			console.warn(
				"Could not refresh CSRF token. Server may have ignore_csrf enabled.",
			)
		}

		throw error
	}
}

// GET twin of call(): frappe-ui's call() always POSTs, and a method published with
// @frappe.whitelist(methods=["GET"]) answers 403 to a POST (spec 031b2a, D-031b.10).
export async function callGet(method, params) {
	const request = () =>
		frappeRequest({ url: method, method: "GET", params: params ?? {} })
	try {
		return await request()
	} catch (error) {
		if (isCSRFApiError(error)) {
			console.warn(
				"CSRF token error in callGet(), refreshing token and retrying...",
			)
			const refreshed = await forceRefreshCSRFToken()

			if (refreshed) {
				return await request()
			}

			console.warn(
				"Could not refresh CSRF token. Server may have ignore_csrf enabled.",
			)
		}

		throw error
	}
}
