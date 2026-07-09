#!/usr/bin/env python3
"""Comprehensive loader and orchestrator diagnostic and fix script.

Identifies why loaders aren't running automatically and provides fixes.
"""

import sys
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db.context import DatabaseContext

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def check_loader_freshness():
    """Check if loader data is fresh and identify what's stale."""
    logger.info("\n" + "="*80)
    logger.info("LOADER FRESHNESS AUDIT")
    logger.info("="*80)

    critical_loaders = [
        'price_daily',
        'technical_data_daily',
        'market_exposure_daily',
        'market_health_daily',
        'quality_metrics',
        'growth_metrics',
        'value_metrics',
        'positioning_metrics',
        'stability_metrics',
        'stock_scores',
        'buy_sell_daily',
    ]

    fresh_threshold = 2  # hours - prices should be 2h old max
    metrics_threshold = 24  # hours - metrics can be 1d old

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT table_name, last_updated, completion_pct, reason
            FROM data_loader_status
            ORDER BY last_updated DESC
        """)
        loaders = {row[0]: (row[1], row[2], row[3]) for row in cur.fetchall()}

    now = datetime.now(timezone.utc)
    issues = []

    for loader_name in critical_loaders:
        if loader_name not in loaders:
            logger.warning(f"  ⚠️  {loader_name:30} - NOT IN DATABASE (never ran?)")
            issues.append((loader_name, "never_ran"))
            continue

        last_run, completion, reason = loaders[loader_name]
        age = (now - last_run.replace(tzinfo=timezone.utc)).total_seconds() / 3600  # hours

        if loader_name in ['price_daily', 'technical_data_daily', 'market_exposure_daily']:
            threshold = fresh_threshold
        else:
            threshold = metrics_threshold

        if age > threshold:
            status = "🔴 STALE"
            issues.append((loader_name, f"stale_{age:.1f}h"))
        elif age > threshold * 0.5:
            status = "🟡 AGING"
        else:
            status = "✅ FRESH"

        logger.info(f"  {status} {loader_name:30} ({age:.1f}h old, {completion:.0f}% complete)")
        if reason:
            logger.info(f"       Reason: {reason}")

    return issues


def check_orchestrator_runs():
    """Check if orchestrator has run recently."""
    logger.info("\n" + "="*80)
    logger.info("ORCHESTRATOR EXECUTION AUDIT")
    logger.info("="*80)

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT run_id, started_at, completed_at, overall_status
            FROM algo_orchestrator_runs
            ORDER BY started_at DESC
            LIMIT 5
        """)
        runs = cur.fetchall()

    if not runs:
        logger.warning("  ❌ NO ORCHESTRATOR RUNS FOUND")
        return False

    now = datetime.now(timezone.utc)
    for run_id, started_at, completed_at, overall_status in runs:
        age = (now - started_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        status = "✅ SUCCESS" if overall_status == "success" else "❌ FAILED"
        logger.info(f"  {status} {run_id:30} ({age:.1f}h ago)")

    latest_run = runs[0]
    age_hours = (now - latest_run[1].replace(tzinfo=timezone.utc)).total_seconds() / 3600

    if age_hours > 4:
        logger.warning(f"  ⚠️  ORCHESTRATOR STALE: Last run {age_hours:.1f}h ago (max acceptable: 4h)")
        return False

    return True


def check_trading_signals():
    """Check if signal generation is working."""
    logger.info("\n" + "="*80)
    logger.info("TRADING SIGNAL GENERATION AUDIT")
    logger.info("="*80)

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT signal_triggered_date as sig_date, COUNT(*) as signal_count
            FROM buy_sell_daily
            WHERE signal_type = 'BUY'
            GROUP BY signal_triggered_date
            ORDER BY signal_triggered_date DESC
            LIMIT 5
        """)
        signals = cur.fetchall()

    if not signals:
        logger.warning("  ❌ NO BUY SIGNALS GENERATED")
        return False

    for sig_date, count in signals:
        logger.info(f"  {sig_date}: {count:4d} BUY signals")

    return signals[0][1] > 0


def check_data_completeness():
    """Check if data completeness is sufficient for trading."""
    logger.info("\n" + "="*80)
    logger.info("DATA COMPLETENESS AUDIT")
    logger.info("="*80)

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN composite_score IS NULL THEN 1 ELSE 0 END) as missing_composite,
                   SUM(CASE WHEN composite_score > 0 THEN 1 ELSE 0 END) as tradeable
            FROM stock_scores
            WHERE updated_at > NOW() - INTERVAL '1 day'
        """)
        total, missing, tradeable = cur.fetchone()

    if total is None or total == 0:
        logger.warning("  ❌ NO STOCK SCORES")
        return False

    pct_tradeable = (tradeable / total * 100) if total > 0 else 0
    logger.info(f"  Total stocks scored: {total:,}")
    logger.info(f"  Tradeable (score > 0): {tradeable:,} ({pct_tradeable:.1f}%)")
    logger.info(f"  Missing composite: {missing:,} ({missing/total*100:.1f}%)")

    return pct_tradeable >= 50  # At least 50% tradeable


def run_diagnostic():
    """Run complete diagnostic."""
    logger.info("\n" + "🔍 " * 40)
    logger.info("COMPLETE SYSTEM DIAGNOSTIC")
    logger.info("🔍 " * 40 + "\n")

    try:
        issues = check_loader_freshness()
        orchest_ok = check_orchestrator_runs()
        signals_ok = check_trading_signals()
        data_ok = check_data_completeness()

        logger.info("\n" + "="*80)
        logger.info("SUMMARY & RECOMMENDATIONS")
        logger.info("="*80)

        if issues:
            logger.warning(f"\n❌ {len(issues)} LOADER(S) STALE:")
            for loader, issue_type in issues:
                logger.warning(f"  - {loader}: {issue_type}")
            logger.info("\nFIX: Run: python3 scripts/trigger_loader.py --loader <loader_name>")
            logger.info("Or deploy via: gh workflow run run-loader.yml -f loader_name=load_stock_scores")
        else:
            logger.info("\n✅ All loaders are fresh")

        if not orchest_ok:
            logger.warning("\n❌ ORCHESTRATOR NOT RUNNING")
            logger.info("FIX: python3 scripts/trigger_orchestrator.py --run morning --mode paper")

        if not signals_ok:
            logger.warning("\n❌ NO TRADING SIGNALS")
            logger.info("FIX: Ensure buy_sell_daily loader has run with fresh data")

        if not data_ok:
            logger.warning("\n❌ INSUFFICIENT DATA QUALITY")
            logger.info("FIX: Run metric loaders: load_quality_metrics, load_growth_metrics, etc.")

        if issues or not orchest_ok or not signals_ok or not data_ok:
            logger.error("\n⚠️  SYSTEM NOT PRODUCTION READY")
            return False
        else:
            logger.info("\n✅ SYSTEM IS PRODUCTION READY")
            return True

    except Exception as e:
        logger.error(f"\n❌ DIAGNOSTIC FAILED: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = run_diagnostic()
    sys.exit(0 if success else 1)
