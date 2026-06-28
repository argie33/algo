#!/usr/bin/env python3
"""Diagnose market data availability - identify missing factors that prevent real values display.

Checks what data is actually in the database for computing market factors and identifies
missing sources that cause None scores and blank displays on the markets panel.

Run: python scripts/diagnose_market_data.py
"""

import os
import sys
from typing import Any

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

from utils.db import DatabaseContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def check_table_freshness(table_name: str, date_col: str = "date") -> dict[str, Any]:
    """Check if a table has recent data."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute(f"""
                SELECT
                    COUNT(*) as total_rows,
                    MAX({date_col}) as latest_date,
                    (CURRENT_DATE - MAX({date_col})) as days_stale
                FROM {table_name}
            """)
            row = cur.fetchone()
            if row is None:
                return {"status": "empty", "error": "Table is empty"}

            count, latest, stale = row
            return {
                "status": "ok" if stale is None or int(stale.days) == 0 else "stale",
                "rows": int(count) if count else 0,
                "latest_date": latest,
                "days_stale": int(stale.days) if stale else 0,
            }
    except psycopg2.DatabaseError as e:
        return {"status": "missing", "error": str(e)[:100]}


def check_spy_data() -> dict[str, Any]:
    """Check if SPY price data exists."""
    try:
        with DatabaseContext("read") as cur:
            # Check daily prices
            cur.execute("""
                SELECT COUNT(*) as count, MAX(date) as latest
                FROM price_daily
                WHERE symbol = 'SPY'
            """)
            row = cur.fetchone()
            count, latest = row

            # Check weekly prices
            cur.execute("""
                SELECT COUNT(*) as count, MAX(date) as latest
                FROM price_weekly
                WHERE symbol = 'SPY'
            """)
            row_weekly = cur.fetchone()
            count_w, latest_w = row_weekly

            return {
                "status": "ok" if count and count_w else "missing",
                "daily_prices": int(count) if count else 0,
                "daily_latest": latest,
                "weekly_prices": int(count_w) if count_w else 0,
                "weekly_latest": latest_w,
            }
    except psycopg2.DatabaseError as e:
        return {"status": "missing", "error": str(e)[:100]}


def check_vix_data() -> dict[str, Any]:
    """Check if VIX (^VIX) price data exists - CRITICAL for market factors."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT COUNT(*) as count, MAX(date) as latest
                FROM price_daily
                WHERE symbol = '^VIX'
            """)
            row = cur.fetchone()
            count, latest = row

            if not count:
                return {
                    "status": "missing",
                    "error": "No ^VIX data in price_daily - VIX factor will return None score",
                }

            return {
                "status": "ok",
                "vix_prices": int(count),
                "latest": latest,
            }
    except psycopg2.DatabaseError as e:
        return {"status": "error", "error": str(e)[:100]}


def check_market_health_daily() -> dict[str, Any]:
    """Check market_health_daily for breadth, new highs/lows, put/call, VIX level."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN vix_level IS NOT NULL THEN 1 ELSE 0 END) as vix_count,
                    SUM(CASE WHEN put_call_ratio IS NOT NULL THEN 1 ELSE 0 END) as pcr_count,
                    SUM(CASE WHEN new_highs_count IS NOT NULL THEN 1 ELSE 0 END) as nh_count,
                    MAX(date) as latest
                FROM market_health_daily
            """)
            row = cur.fetchone()
            total, vix_c, pcr_c, nh_c, latest = row

            return {
                "status": "ok" if total else "empty",
                "total_rows": int(total) if total else 0,
                "vix_level_available": int(vix_c) if vix_c else 0,
                "put_call_ratio_available": int(pcr_c) if pcr_c else 0,
                "new_highs_lows_available": int(nh_c) if nh_c else 0,
                "latest": latest,
            }
    except psycopg2.DatabaseError as e:
        return {"status": "missing", "error": str(e)[:100]}


def check_technical_data() -> dict[str, Any]:
    """Check technical_data_daily for breadth calculations."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(DISTINCT symbol) as unique_symbols,
                    SUM(CASE WHEN sma_50 IS NOT NULL THEN 1 ELSE 0 END) as sma50_count,
                    SUM(CASE WHEN sma_200 IS NOT NULL THEN 1 ELSE 0 END) as sma200_count,
                    MAX(date) as latest
                FROM technical_data_daily
            """)
            row = cur.fetchone()
            total, symbols, sma50_c, sma200_c, latest = row

            return {
                "status": "ok" if total else "empty",
                "total_rows": int(total) if total else 0,
                "unique_symbols": int(symbols) if symbols else 0,
                "sma_50_available": int(sma50_c) if sma50_c else 0,
                "sma_200_available": int(sma200_c) if sma200_c else 0,
                "latest": latest,
            }
    except psycopg2.DatabaseError as e:
        return {"status": "missing", "error": str(e)[:100]}


def check_optional_factors() -> dict[str, dict[str, Any]]:
    """Check optional market factors: AAII, NAAIM, credit spreads, A/D line, yield curve."""
    results = {}

    # Check A/D line
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT COUNT(*) as count, MAX(date) as latest
                FROM ad_line_daily
            """)
            row = cur.fetchone()
            count, latest = row
            results["ad_line"] = {
                "status": "ok" if count else "missing",
                "rows": int(count) if count else 0,
                "latest": latest,
            }
    except psycopg2.DatabaseError as e:
        results["ad_line"] = {"status": "error", "error": str(e)[:80]}

    # Check credit spreads
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT COUNT(*) as count, MAX(date) as latest
                FROM credit_spreads
            """)
            row = cur.fetchone()
            count, latest = row
            results["credit_spreads"] = {
                "status": "ok" if count else "missing",
                "rows": int(count) if count else 0,
                "latest": latest,
            }
    except psycopg2.DatabaseError as e:
        results["credit_spreads"] = {"status": "error", "error": str(e)[:80]}

    # Check AAII sentiment
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT COUNT(*) as count, MAX(date) as latest
                FROM aaii_sentiment
            """)
            row = cur.fetchone()
            count, latest = row
            results["aaii_sentiment"] = {
                "status": "ok" if count else "missing",
                "rows": int(count) if count else 0,
                "latest": latest,
            }
    except psycopg2.DatabaseError as e:
        results["aaii_sentiment"] = {"status": "error", "error": str(e)[:80]}

    # Check NAAIM
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT COUNT(*) as count, MAX(date) as latest
                FROM naaim
            """)
            row = cur.fetchone()
            count, latest = row
            results["naaim"] = {
                "status": "ok" if count else "missing",
                "rows": int(count) if count else 0,
                "latest": latest,
            }
    except psycopg2.DatabaseError as e:
        results["naaim"] = {"status": "error", "error": str(e)[:80]}

    return results


def main():
    """Run diagnostics and report findings."""
    logger.info("="*70)
    logger.info("MARKET DATA DIAGNOSTIC - Checking what data exists for market factors")
    logger.info("="*70)

    # Critical data sources
    logger.info("\n[CRITICAL DATA SOURCES] - Required for market factor calculations:")

    spy_data = check_spy_data()
    logger.info(f"  SPY Price Data: {spy_data['status'].upper()}")
    if spy_data['status'] != 'ok':
        logger.warning("    ⚠ Missing SPY price data - trend and momentum factors will fail")
    else:
        logger.info(f"    ✓ {spy_data['daily_prices']} daily prices (latest: {spy_data['daily_latest']})")
        logger.info(f"    ✓ {spy_data['weekly_prices']} weekly prices (latest: {spy_data['weekly_latest']})")

    vix_data = check_vix_data()
    logger.info(f"  VIX (^VIX) Data: {vix_data['status'].upper()}")
    if vix_data['status'] != 'ok':
        logger.error(f"    ✗ {vix_data.get('error', 'VIX data missing')}")
        logger.error("    → VIX FACTOR WILL RETURN NONE SCORE - markets panel won't show VIX regime")
    else:
        logger.info(f"    ✓ {vix_data['vix_prices']} VIX prices (latest: {vix_data['latest']})")

    tech_data = check_technical_data()
    logger.info(f"  Technical Data: {tech_data['status'].upper()}")
    if tech_data['status'] != 'ok':
        logger.warning(f"    ⚠ {tech_data.get('error', 'Technical data missing')}")
        logger.warning("    → BREADTH FACTORS (% > 50/200 DMA) WILL RETURN NONE SCORE")
    else:
        logger.info(f"    ✓ {tech_data['total_rows']} rows, {tech_data['unique_symbols']} symbols (latest: {tech_data['latest']})")
        logger.info(f"    ✓ SMA_50: {tech_data['sma_50_available']} rows, SMA_200: {tech_data['sma_200_available']} rows")

    mh_data = check_market_health_daily()
    logger.info(f"  Market Health Daily: {mh_data['status'].upper()}")
    if mh_data['status'] == 'empty':
        logger.error("    ✗ market_health_daily is empty - all health metrics will be missing")
    else:
        logger.info(f"    ✓ {mh_data['total_rows']} total rows (latest: {mh_data['latest']})")
        logger.info(f"    • VIX Level: {mh_data['vix_level_available']} rows")
        logger.info(f"    • Put/Call Ratio: {mh_data['put_call_ratio_available']} rows")
        logger.info(f"    • New Highs/Lows: {mh_data['new_highs_lows_available']} rows")

    # Optional data sources
    logger.info("\n[OPTIONAL DATA SOURCES] - For enrichment (gracefully degraded if missing):")

    optional = check_optional_factors()
    for name, info in optional.items():
        logger.info(f"  {name.replace('_', ' ').title()}: {info['status'].upper()}")
        if info['status'] == 'ok':
            logger.info(f"    ✓ {info['rows']} rows (latest: {info['latest']})")
        else:
            logger.info("    • Will be skipped if missing (graceful degradation)")

    # Summary and recommendations
    logger.info("\n" + "="*70)
    logger.info("SUMMARY & RECOMMENDATIONS:")
    logger.info("="*70)

    issues = []

    if spy_data['status'] != 'ok':
        issues.append("SPY prices are missing - run: python loaders/load_prices.py --symbols SPY")

    if vix_data['status'] != 'ok':
        issues.append("VIX (^VIX) is missing - run: python loaders/load_prices.py --symbols '^VIX'")

    if tech_data['status'] == 'empty':
        issues.append("Technical data is missing - run: python loaders/load_technical_indicators.py")

    if mh_data['status'] == 'empty':
        issues.append("Market health data is missing - run: python loaders/load_market_health_daily.py")

    if not issues:
        logger.info("✓ ALL CRITICAL DATA IS AVAILABLE - Markets panel should show real values")
        logger.info("\nTo verify the markets panel is working:")
        logger.info("1. Start the frontend dev server: npm run dev (in webapp/frontend)")
        logger.info("2. Navigate to the Markets Health page")
        logger.info("3. All 12 market factors should show with real values (not None scores)")
    else:
        logger.warning(f"\n✗ {len(issues)} CRITICAL DATA SOURCES MISSING:")
        for i, issue in enumerate(issues, 1):
            logger.warning(f"  {i}. {issue}")
        logger.info("\nAfter loading data, restart the orchestrator to populate market factors.")
        logger.info("Then the markets panel will show real values instead of blank fields.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Diagnostic failed: {e}", exc_info=True)
        sys.exit(1)
