#!/usr/bin/env python3
"""Add missing unavailable_reason fields to metrics tables.

Fixes issue where API tries to select fields that don't exist in the database,
causing "No data" to show for many metrics in the frontend.

This migration adds ~50 missing unavailable_reason fields to:
- quality_metrics (30 fields)
- growth_metrics (17 fields)
- stability_metrics (11 fields)
- positioning_metrics (8 fields)
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Add missing unavailable_reason fields to metrics tables"


def up():
    with DatabaseContext("write") as cur:
        # Quality metrics - add missing unavailable_reason fields
        cur.execute("""
            ALTER TABLE IF EXISTS quality_metrics
            ADD COLUMN IF NOT EXISTS roa_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS roic_pct_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS gross_margin_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS ebitda_margin_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS debt_to_equity_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS current_ratio_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS quick_ratio_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS interest_coverage_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS debt_to_assets_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS fcf_to_net_income_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS ocf_to_net_income_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS payout_ratio_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS free_cash_flow_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS operating_cash_flow_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS total_debt_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS total_cash_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS cash_per_share_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS ebitda_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS earnings_growth_yoy_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS revenue_growth_yoy_unavailable_reason VARCHAR(255) NULL
        """)

        # Growth metrics - add missing unavailable_reason fields
        cur.execute("""
            ALTER TABLE IF EXISTS growth_metrics
            ADD COLUMN IF NOT EXISTS revenue_growth_1y_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS eps_growth_1y_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS revenue_growth_3y_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS eps_growth_3y_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS revenue_growth_5y_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS eps_growth_5y_unavailable_reason VARCHAR(255) NULL
        """)

        # Stability metrics - add missing unavailable_reason fields
        cur.execute("""
            ALTER TABLE IF EXISTS stability_metrics
            ADD COLUMN IF NOT EXISTS volatility_60d_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS volatility_252d_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS max_drawdown_1y_unavailable_reason VARCHAR(255) NULL
        """)

        # Positioning metrics - add missing unavailable_reason fields
        cur.execute("""
            ALTER TABLE IF EXISTS positioning_metrics
            ADD COLUMN IF NOT EXISTS top_10_institutions_pct_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS institutional_holders_count_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS short_percent_of_float_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS short_interest_trend_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS shares_short_prior_month_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS short_ratio_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS ad_rating_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN IF NOT EXISTS insider_ownership_pct_unavailable_reason VARCHAR(255) NULL
        """)


def down():
    """Drop added unavailable_reason fields."""
    with DatabaseContext("write") as cur:
        # Quality metrics
        cur.execute("""
            ALTER TABLE IF EXISTS quality_metrics
            DROP COLUMN IF EXISTS roa_unavailable_reason,
            DROP COLUMN IF EXISTS roic_pct_unavailable_reason,
            DROP COLUMN IF EXISTS gross_margin_unavailable_reason,
            DROP COLUMN IF EXISTS ebitda_margin_unavailable_reason,
            DROP COLUMN IF EXISTS debt_to_equity_unavailable_reason,
            DROP COLUMN IF EXISTS current_ratio_unavailable_reason,
            DROP COLUMN IF EXISTS quick_ratio_unavailable_reason,
            DROP COLUMN IF EXISTS interest_coverage_unavailable_reason,
            DROP COLUMN IF EXISTS debt_to_assets_unavailable_reason,
            DROP COLUMN IF EXISTS fcf_to_net_income_unavailable_reason,
            DROP COLUMN IF EXISTS ocf_to_net_income_unavailable_reason,
            DROP COLUMN IF EXISTS payout_ratio_unavailable_reason,
            DROP COLUMN IF EXISTS free_cash_flow_unavailable_reason,
            DROP COLUMN IF EXISTS operating_cash_flow_unavailable_reason,
            DROP COLUMN IF EXISTS total_debt_unavailable_reason,
            DROP COLUMN IF EXISTS total_cash_unavailable_reason,
            DROP COLUMN IF EXISTS cash_per_share_unavailable_reason,
            DROP COLUMN IF EXISTS ebitda_unavailable_reason,
            DROP COLUMN IF EXISTS earnings_growth_yoy_unavailable_reason,
            DROP COLUMN IF EXISTS revenue_growth_yoy_unavailable_reason
        """)

        # Growth metrics
        cur.execute("""
            ALTER TABLE IF EXISTS growth_metrics
            DROP COLUMN IF EXISTS revenue_growth_1y_unavailable_reason,
            DROP COLUMN IF EXISTS eps_growth_1y_unavailable_reason,
            DROP COLUMN IF EXISTS revenue_growth_3y_unavailable_reason,
            DROP COLUMN IF EXISTS eps_growth_3y_unavailable_reason,
            DROP COLUMN IF EXISTS revenue_growth_5y_unavailable_reason,
            DROP COLUMN IF EXISTS eps_growth_5y_unavailable_reason
        """)

        # Stability metrics
        cur.execute("""
            ALTER TABLE IF EXISTS stability_metrics
            DROP COLUMN IF EXISTS volatility_60d_unavailable_reason,
            DROP COLUMN IF EXISTS volatility_252d_unavailable_reason,
            DROP COLUMN IF EXISTS max_drawdown_1y_unavailable_reason
        """)

        # Positioning metrics
        cur.execute("""
            ALTER TABLE IF EXISTS positioning_metrics
            DROP COLUMN IF EXISTS top_10_institutions_pct_unavailable_reason,
            DROP COLUMN IF EXISTS institutional_holders_count_unavailable_reason,
            DROP COLUMN IF EXISTS short_percent_of_float_unavailable_reason,
            DROP COLUMN IF EXISTS short_interest_trend_unavailable_reason,
            DROP COLUMN IF EXISTS shares_short_prior_month_unavailable_reason,
            DROP COLUMN IF EXISTS short_ratio_unavailable_reason,
            DROP COLUMN IF EXISTS ad_rating_unavailable_reason,
            DROP COLUMN IF EXISTS insider_ownership_pct_unavailable_reason
        """)
