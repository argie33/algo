#!/usr/bin/env python3
"""Comprehensive audit of which SEC concepts and data fields are missing.

Systematically checks which specific inputs are blocking each factor from being computed,
ranked by impact (symbols affected). Helps identify which loaders need concept fallbacks.
"""

import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from utils.db.context import DatabaseContext  # noqa: E402
from utils.infrastructure.timezone import EASTERN_TZ  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def audit_roic_pct_gaps() -> None:
    """Find why roic_pct is missing (missing_sec_data reason)."""
    print("\n" + "=" * 80)
    print("ROIC_PCT GAPS (missing_sec_data)")
    print("=" * 80)

    with DatabaseContext("read") as cur:
        # Check what balance sheet data is actually available for missing roic symbols
        cur.execute("""
            SELECT
                COUNT(DISTINCT q.symbol) as symbol_count,
                COUNT(DISTINCT CASE WHEN bs.stockholders_equity IS NOT NULL THEN q.symbol END) as has_equity,
                COUNT(DISTINCT CASE WHEN bs.cash_and_equivalents IS NOT NULL THEN q.symbol END) as has_cash,
                COUNT(DISTINCT CASE WHEN is_stmt.operating_income IS NOT NULL THEN q.symbol END) as has_oi,
                COUNT(DISTINCT CASE WHEN sv.total_debt IS NOT NULL THEN q.symbol END) as has_total_debt,
                COUNT(DISTINCT CASE WHEN bs.long_term_debt IS NOT NULL THEN q.symbol END) as has_ltd
            FROM quality_metrics q
            LEFT JOIN annual_balance_sheet bs ON bs.symbol = q.symbol AND bs.fiscal_year = (
                SELECT fiscal_year FROM annual_balance_sheet WHERE symbol=q.symbol ORDER BY fiscal_year DESC LIMIT 1
            )
            LEFT JOIN annual_income_statement is_stmt ON is_stmt.symbol = q.symbol AND is_stmt.fiscal_year = (
                SELECT fiscal_year FROM annual_income_statement WHERE symbol=q.symbol ORDER BY fiscal_year DESC LIMIT 1
            )
            LEFT JOIN sec_valuations sv ON sv.symbol = q.symbol
            WHERE q.roic_pct_unavailable_reason = 'missing_sec_data'
        """)
        row = cur.fetchone()
        if row:
            symbols, has_eq, has_cash, has_oi, has_debt, has_ltd = row
            print(f"  Symbols with roic_pct missing: {symbols}")
            print(f"  - Have stockholders_equity: {has_eq} ({100 * has_eq / symbols:.1f}%)")
            print(f"  - Have cash_and_equivalents: {has_cash} ({100 * has_cash / symbols:.1f}%)")
            print(f"  - Have operating_income: {has_oi} ({100 * has_oi / symbols:.1f}%)")
            print(f"  - Have total_debt (sec_valuations): {has_debt} ({100 * has_debt / symbols:.1f}%)")
            print(f"  - Have long_term_debt: {has_ltd} ({100 * has_ltd / symbols:.1f}%)")

        # Sample symbols and why they're missing
        print("\n  Sample symbols and missing inputs:")
        cur.execute("""
            SELECT
                q.symbol,
                CASE
                    WHEN bs.stockholders_equity IS NULL THEN 'NO_EQUITY'
                    WHEN bs.cash_and_equivalents IS NULL THEN 'NO_CASH'
                    WHEN is_stmt.operating_income IS NULL THEN 'NO_OI'
                    WHEN sv.total_debt IS NULL AND bs.long_term_debt IS NULL THEN 'NO_DEBT'
                    ELSE 'OTHER'
                END as reason
            FROM quality_metrics q
            LEFT JOIN annual_balance_sheet bs ON bs.symbol = q.symbol
                AND bs.fiscal_year = (SELECT fiscal_year FROM annual_balance_sheet WHERE symbol=q.symbol ORDER BY fiscal_year DESC LIMIT 1)
            LEFT JOIN annual_income_statement is_stmt ON is_stmt.symbol = q.symbol
                AND is_stmt.fiscal_year = (SELECT fiscal_year FROM annual_income_statement WHERE symbol=q.symbol ORDER BY fiscal_year DESC LIMIT 1)
            LEFT JOIN sec_valuations sv ON sv.symbol = q.symbol
            WHERE q.roic_pct_unavailable_reason = 'missing_sec_data'
            LIMIT 30
        """)

        reasons_count: defaultdict[str, int] = defaultdict(int)
        for symbol, reason in cur.fetchall():
            reasons_count[reason] += 1
            if reasons_count[reason] <= 5:
                print(f"    {symbol}: {reason}")

        print("\n  Missing input distribution:")
        for reason, count in sorted(reasons_count.items(), key=lambda x: -x[1]):
            print(f"    {reason}: {count} symbols")


def audit_sustainable_growth_gaps() -> None:
    """Find why sustainable_growth_rate is missing (missing_sec_data reason)."""
    print("\n" + "=" * 80)
    print("SUSTAINABLE_GROWTH_RATE GAPS (missing_sec_data)")
    print("=" * 80)

    with DatabaseContext("read") as cur:
        # Check what income statement data is available
        cur.execute("""
            WITH ni_with_prior AS (
                SELECT symbol, fiscal_year, net_income,
                       lag(net_income) OVER (PARTITION BY symbol ORDER BY fiscal_year) as prior_net_income
                FROM annual_income_statement
            )
            SELECT
                COUNT(DISTINCT q.symbol) as symbol_count,
                COUNT(DISTINCT CASE WHEN is_stmt.net_income IS NOT NULL THEN q.symbol END) as has_ni,
                COUNT(DISTINCT CASE WHEN is_stmt.net_income IS NOT NULL
                                  AND is_stmt.prior_net_income IS NOT NULL
                                  THEN q.symbol END) as has_ni_prior_year
            FROM quality_metrics q
            LEFT JOIN ni_with_prior is_stmt ON is_stmt.symbol = q.symbol
            WHERE q.sustainable_growth_rate_unavailable_reason = 'missing_sec_data'
        """)
        row = cur.fetchone()
        if row:
            symbols, has_ni, has_prior = row
            print(f"  Symbols with sustainable_growth_rate missing: {symbols}")
            print(f"  - Have net_income (current): {has_ni} ({100 * has_ni / symbols:.1f}%)")
            print(f"  - Have net_income (prior year too): {has_prior} ({100 * has_prior / symbols:.1f}%)")


def audit_pb_ratio_gaps() -> None:
    """Find why pb_ratio is missing (missing_sec_data reason)."""
    print("\n" + "=" * 80)
    print("PB_RATIO GAPS (missing_sec_data)")
    print("=" * 80)

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT
                COUNT(DISTINCT v.symbol) as symbol_count,
                COUNT(DISTINCT CASE WHEN bs.stockholders_equity IS NOT NULL THEN v.symbol END) as has_equity,
                COUNT(DISTINCT CASE WHEN sv.shares_outstanding > 100000 THEN v.symbol END) as has_shares
            FROM value_metrics v
            LEFT JOIN annual_balance_sheet bs ON bs.symbol = v.symbol
                AND bs.fiscal_year = (SELECT fiscal_year FROM annual_balance_sheet WHERE symbol=v.symbol
                                      ORDER BY (CASE WHEN stockholders_equity IS NOT NULL THEN 0 ELSE 1 END), fiscal_year DESC LIMIT 1)
            LEFT JOIN sec_valuations sv ON sv.symbol = v.symbol
            WHERE v.pb_ratio_unavailable_reason = 'missing_sec_data'
        """)
        row = cur.fetchone()
        if row:
            symbols, has_eq, has_shares = row
            print(f"  Symbols with pb_ratio missing: {symbols}")
            print(f"  - Have stockholders_equity: {has_eq} ({100 * has_eq / symbols:.1f}%)")
            print(f"  - Have shares_outstanding: {has_shares} ({100 * has_shares / symbols:.1f}%)")


def audit_ps_ratio_gaps() -> None:
    """Find why ps_ratio is missing (missing_sec_data reason)."""
    print("\n" + "=" * 80)
    print("PS_RATIO GAPS (missing_sec_data)")
    print("=" * 80)

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT
                COUNT(DISTINCT v.symbol) as symbol_count,
                COUNT(DISTINCT CASE WHEN is_stmt.revenue IS NOT NULL THEN v.symbol END) as has_revenue,
                COUNT(DISTINCT CASE WHEN sv.shares_outstanding > 100000 THEN v.symbol END) as has_shares
            FROM value_metrics v
            LEFT JOIN annual_income_statement is_stmt ON is_stmt.symbol = v.symbol
                AND is_stmt.fiscal_year = (SELECT fiscal_year FROM annual_income_statement WHERE symbol=v.symbol
                                           ORDER BY (CASE WHEN revenue IS NOT NULL OR earnings_per_share IS NOT NULL THEN 0 ELSE 1 END), fiscal_year DESC LIMIT 1)
            LEFT JOIN sec_valuations sv ON sv.symbol = v.symbol
            WHERE v.ps_ratio_unavailable_reason = 'missing_sec_data'
        """)
        row = cur.fetchone()
        if row:
            symbols, has_rev, has_shares = row
            print(f"  Symbols with ps_ratio missing: {symbols}")
            print(f"  - Have revenue: {has_rev} ({100 * has_rev / symbols:.1f}%)")
            print(f"  - Have shares_outstanding: {has_shares} ({100 * has_shares / symbols:.1f}%)")


def audit_positioning_gaps() -> None:
    """Find why institutional holdings are missing for no_resolved_13f_holdings symbols.

    Note: company_profile has no cusip column, and sec_13f_cusip_crosswalk is keyed by
    OUR ticker (populated only on successful resolution) - a symbol with
    no_resolved_13f_holdings by definition has no row there, so there is no CUSIP source
    in our own DB to look up for these symbols. This audit can only report whether a
    symbol is unexpectedly ALREADY present in the crosswalk despite being marked
    unresolved (a real bug signal - stale reason not cleared after resolution), not
    classify the true root cause of unresolved symbols (that needs a live OpenFIGI/13F
    bulk-data lookup, out of scope for a read-only DB audit).
    """
    print("\n" + "=" * 80)
    print("INSTITUTIONAL HOLDINGS GAPS (no_resolved_13f_holdings)")
    print("=" * 80)

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT
                COUNT(DISTINCT i.symbol) as with_13f_holding,
                COUNT(DISTINCT CASE WHEN s.ticker IS NOT NULL THEN i.symbol END) as unexpectedly_in_crosswalk
            FROM institutional_holdings_13f i
            LEFT JOIN sec_13f_cusip_crosswalk s ON s.ticker = i.symbol
            WHERE i.reason = 'no_resolved_13f_holdings'
        """)
        row = cur.fetchone()
        if row:
            with_13f, unexpectedly_resolved = row
            print(f"  Symbols with no_resolved_13f_holdings: {with_13f}")
            print(f"  - Unexpectedly already in sec_13f_cusip_crosswalk: {unexpectedly_resolved}")
            if unexpectedly_resolved:
                print("    -> real bug: reason not cleared after resolution succeeded, investigate")
            print("\n  To classify true root causes (OpenFIGI unresolved vs foreign-only listing vs")
            print("  ticker not in universe), a live OpenFIGI lookup against the SEC bulk 13F CUSIP")
            print("  is needed - there is no CUSIP source for unresolved symbols in our own DB.")


def main() -> int:
    """Run comprehensive data gap audit."""
    now = datetime.now(EASTERN_TZ)
    print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] Starting comprehensive data gap audit...")

    try:
        audit_roic_pct_gaps()
        audit_sustainable_growth_gaps()
        audit_pb_ratio_gaps()
        audit_ps_ratio_gaps()
        audit_positioning_gaps()

        print("\n" + "=" * 80)
        print("AUDIT DONE")
        print("=" * 80)
        print("""
Read the per-metric breakdowns above for the CURRENT missing-input distribution - do not
assume prior sessions' numbers still hold, they drift as fixes land and backfills run.
For each metric, cross-reference "Missing input distribution" against that metric's actual
compute-gating logic in loaders/load_value_quality_growth_metrics.py (or load_sec_valuations.py
for pb_ratio/ps_ratio) - a field showing up as "missing" here only tells you which DB column
was NULL for the picked anchor fiscal year, not whether the loader's own fallback/lookback
logic could have recovered it from a different year. Confirm against the loader's real anchor-
selection query before concluding something is a bug vs already-handled.
        """)

    except Exception as e:
        logger.error(f"Audit failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
