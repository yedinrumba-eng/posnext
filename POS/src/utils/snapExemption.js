import { roundCurrency } from "./taxRounding"

// P1 (Yedin, 12/11/2026): in a mixed payment EBT is applied first to the eligible lines that carry
// tax. UNVERIFIED with the accountant (docs/17, Paso 8). Same constant as ALLOCATION in
// korvexcio/packs/snap_tax_rules.py: the server decides, this only shows the same number.
export const SNAP_ALLOCATION = "taxable_first"

/**
 * Sales tax removed by paying part of a sale with EBT/SNAP (same formula as the server).
 *
 * @param {{lines: Array<{net: number, taxRate: number, snapEligible: boolean}>, ebtPaid: number,
 *   method: string, allocation?: string}} args
 * @returns {{exemption: number, eligibleTotal: number, overLimit: boolean, ebtCap: number,
 *   ebtDue: number}} ebtCap = eligible net (what the cashier charges on EBT); ebtDue = what is left
 *   under that cap after the EBT already entered
 */
export function snapExemption({ lines, ebtPaid, method, allocation = SNAP_ALLOCATION }) {
	const ebt = Number(ebtPaid) || 0
	const eligible = lines.filter((line) => line.snapEligible)
	const eligibleTotal = eligible.reduce((sum, line) => sum + (Number(line.net) || 0), 0)
	const overLimit = ebt > eligibleTotal + 0.005
	const ebtCap = roundCurrency(eligibleTotal, 2, method)
	const ebtDue = roundCurrency(Math.max(0, eligibleTotal - ebt), 2, method)

	const taxable = eligible.filter((line) => Number(line.taxRate) > 0)
	const taxableNet = taxable.reduce((sum, line) => sum + (Number(line.net) || 0), 0)
	if (ebt <= 0 || taxableNet === 0) {
		return { exemption: 0, eligibleTotal, overLimit, ebtCap, ebtDue }
	}

	let covered
	if (allocation === "taxable_first") {
		covered = Math.min(ebt, taxableNet)
	} else if (allocation === "proportional") {
		covered = taxableNet * Math.min(1, ebt / eligibleTotal)
	} else {
		throw new Error(`Unknown SNAP allocation: ${allocation}`)
	}

	const tax = taxable.reduce((sum, line) => sum + ((Number(line.net) || 0) * Number(line.taxRate)) / 100, 0)
	const exemption = roundCurrency((tax * covered) / taxableNet, 2, method)
	return { exemption, eligibleTotal, overLimit, ebtCap, ebtDue }
}
