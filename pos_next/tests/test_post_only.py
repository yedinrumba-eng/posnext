"""S10.4b - every whitelisted method that changes data must require POST.

Reads the source with ``ast``; no frappe, no bench. The two sets below are the whole
whitelist of pos_next: adding a whitelisted function forces a decision here.
"""

import ast
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent

MUST_POST = {
    "api/branding.py::validate_branding",
    "api/branding.py::log_client_event",
    "api/credit_sales.py::redeem_customer_credit",
    "api/credit_sales.py::cancel_credit_journal_entries",
    "api/customers.py::create_customer",
    "api/invoices.py::update_invoice",
    "api/invoices.py::submit_invoice",
    "api/invoices.py::delete_invoice",
    "api/invoices.py::cleanup_old_drafts",
    "api/localization.py::change_user_language",
    "api/partial_payments.py::add_payment_to_partial_invoice",
    "api/pos_profile.py::update_warehouse",
    "api/pos_profile.py::create_pos_profile",
    "api/pos_profile.py::update_pos_profile",
    "api/pos_profile.py::delete_pos_profile",
    "api/promotions.py::create_promotion",
    "api/promotions.py::update_promotion",
    "api/promotions.py::toggle_promotion",
    "api/promotions.py::delete_promotion",
    "api/promotions.py::create_coupon",
    "api/promotions.py::update_coupon",
    "api/promotions.py::toggle_coupon",
    "api/promotions.py::delete_coupon",
    "api/promotions.py::apply_referral_code",
    "api/shifts.py::create_opening_shift",
    "api/shifts.py::submit_closing_shift",
    "api/wallet.py::get_or_create_wallet",
    "api/wallet.py::create_manual_wallet_credit",
    "pos_next/doctype/brainwise_branding/brainwise_branding.py::validate_branding",
    "pos_next/doctype/brainwise_branding/brainwise_branding.py::log_client_event",
    "pos_next/doctype/pos_closing_shift/pos_closing_shift.py::submit_closing_shift",
    "pos_next/doctype/pos_settings/pos_settings.py::update_pos_settings",
    "pos_next/doctype/wallet/wallet.py::create_customer_wallet",
    "pos_next/doctype/wallet/wallet.py::get_or_create_wallet",
    "pos_next/doctype/wallet_transaction/wallet_transaction.py::create_wallet_credit",
    "pos_next/doctype/wallet_transaction/wallet_transaction.py::credit_loyalty_points_to_wallet",
}

READ_ONLY = {
    "api/__init__.py::ping",
    "api/bootstrap.py::get_initial_data",
    "api/branding.py::get_branding_config",
    "api/branding.py::get_tampering_stats",
    "api/credit_sales.py::get_customer_balance",
    "api/credit_sales.py::get_available_credit",
    "api/credit_sales.py::get_credit_sale_summary",
    "api/credit_sales.py::get_credit_invoices",
    "api/customers.py::get_customers",
    "api/customers.py::get_customer_details",
    "api/invoices.py::validate_cart_items",
    "api/invoices.py::validate_return_items",
    "api/invoices.py::check_offline_invoice_synced",
    "api/invoices.py::get_invoice",
    "api/invoices.py::get_invoices",
    "api/invoices.py::get_draft_invoices",
    "api/invoices.py::get_returnable_invoices",
    "api/invoices.py::get_invoice_for_return",
    "api/invoices.py::search_invoices_for_return",
    "api/invoices.py::apply_offers",
    "api/items.py::search_by_barcode",
    "api/items.py::get_item_stock",
    "api/items.py::get_batch_serial_details",
    "api/items.py::get_item_variants",
    "api/items.py::get_items",
    "api/items.py::get_item_details",
    "api/items.py::get_item_groups",
    "api/items.py::get_stock_quantities",
    "api/items.py::get_item_warehouse_availability",
    "api/items.py::get_product_bundle_availability",
    "api/localization.py::get_app_translations",
    "api/localization.py::get_user_language",
    "api/localization.py::get_allowed_locales",
    "api/offers.py::get_offers",
    "api/offers.py::get_active_coupons",
    "api/offers.py::validate_coupon",
    "api/partial_payments.py::get_partial_paid_invoices",
    "api/partial_payments.py::get_unpaid_invoices",
    "api/partial_payments.py::get_partial_payment_details",
    "api/partial_payments.py::get_partial_payment_summary",
    "api/partial_payments.py::get_unpaid_summary",
    "api/pos_profile.py::get_pos_profiles",
    "api/pos_profile.py::get_pos_profile_data",
    "api/pos_profile.py::get_pos_settings",
    "api/pos_profile.py::get_payment_methods",
    "api/pos_profile.py::get_taxes",
    "api/pos_profile.py::get_warehouses",
    "api/pos_profile.py::get_default_customer",
    "api/pos_profile.py::get_sales_persons",
    "api/pos_profile.py::get_create_pos_profile",
    "api/promotions.py::get_promotions",
    "api/promotions.py::get_promotion_details",
    "api/promotions.py::get_item_groups",
    "api/promotions.py::get_brands",
    "api/promotions.py::search_items",
    "api/promotions.py::get_coupons",
    "api/promotions.py::get_coupon_details",
    "api/promotions.py::get_referral_codes",
    "api/promotions.py::get_referral_details",
    "api/shifts.py::get_opening_dialog_data",
    "api/shifts.py::check_opening_shift",
    "api/shifts.py::get_closing_shift_data",
    "api/utilities.py::get_csrf_token",
    "api/wallet.py::get_customer_wallet_balance",
    "api/wallet.py::get_customer_wallet",
    "api/wallet.py::get_wallet_payment_methods",
    "api/wallet.py::get_wallet_info",
    "pos_next/doctype/brainwise_branding/brainwise_branding.py::get_branding_config",
    "pos_next/doctype/brainwise_branding/brainwise_branding.py::verify_master_key",
    "pos_next/doctype/brainwise_branding/brainwise_branding.py::generate_new_master_key",
    "pos_next/doctype/pos_closing_shift/pos_closing_shift.py::get_cashiers",
    "pos_next/doctype/pos_closing_shift/pos_closing_shift.py::get_pos_invoices",
    "pos_next/doctype/pos_closing_shift/pos_closing_shift.py::get_payments_entries",
    "pos_next/doctype/pos_closing_shift/pos_closing_shift.py::make_closing_shift_from_opening",
    "pos_next/doctype/pos_settings/pos_settings.py::get_pos_settings",
    "pos_next/doctype/wallet/wallet.py::get_customer_wallet",
    "pos_next/doctype/wallet/wallet.py::get_customer_wallet_balance",
    "validations.py::item_query",
}


def _is_whitelist(node: ast.expr) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    return (
        isinstance(target, ast.Attribute)
        and target.attr == "whitelist"
        and isinstance(target.value, ast.Name)
        and target.value.id == "frappe"
    )


def _whitelisted() -> dict[str, ast.expr]:
    """Module-level functions decorated with @frappe.whitelist -> their decorator node."""
    found = {}
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for decorator in node.decorator_list:
                    if _is_whitelist(decorator):
                        found[f"{path.relative_to(PACKAGE_ROOT).as_posix()}::{node.name}"] = decorator
    return found


def _methods_literal(decorator: ast.expr):
    if not isinstance(decorator, ast.Call):
        return None
    for keyword in decorator.keywords:
        if keyword.arg == "methods":
            try:
                return ast.literal_eval(keyword.value)
            except ValueError:
                return None
    return None


class TestPostOnly(unittest.TestCase):
    def test_mutating_methods_require_post(self):
        found = _whitelisted()
        for key in sorted(MUST_POST):
            self.assertIn(key, found, f"{key} is not whitelisted")
            self.assertEqual(["POST"], _methods_literal(found[key]), key)

    def test_whitelist_is_exactly_the_known_set(self):
        self.assertEqual(sorted(MUST_POST | READ_ONLY), sorted(_whitelisted()))


if __name__ == "__main__":
    unittest.main()
