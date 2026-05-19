#!/usr/bin/env python3
"""
Master loader: runs all critical loaders in dependency order.
Populates database for orchestrator execution.

Usage:
  python3 run-all-loaders.py                    # Load all
  python3 run-all-loaders.py --quick            # Load only critical for orchestrator
  python3 run-all-loaders.py --symbols AAPL,MSFT  # Specific symbols
"""

import sys
import os
import subprocess
import logging
from pathlib import Path
from datetime import date
from typing import List, Optional

# Add root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.env_loader import load_env
from utils.structured_logger import get_logger

logger = get_logger(__name__)

# Dependency order for loaders
LOADER_GROUPS = {
    "foundation": [
        ("loaders/loadstocksymbols.py", []),
        ("loaders/loadsectors.py", []),
        ("loaders/loadindustryranking.py", []),
    ],
    "prices_and_technicals": [
        ("loaders/loadpricedaily.py", ["--interval", "1d"]),
        ("loaders/loadpricedaily.py", ["--interval", "1wk"]),
        ("loaders/loadpricedaily.py", ["--interval", "1mo"]),
        ("loaders/load_technical_data_daily.py", []),
        ("loaders/loadbuyselldaily.py", []),
    ],
    "trend_and_scores": [
        ("loaders/load_trend_criteria_data.py", []),
        ("loaders/load_swing_trader_scores.py", []),
        ("loaders/load_signal_quality_scores.py", []),
    ],
    "market_context": [
        ("loaders/loadmarketindices.py", []),
        ("loaders/loadecondata.py", []),
        ("loaders/loadfeargreed.py", []),
        ("loaders/loadnaaim.py", []),
        ("loaders/load_market_health_daily.py", []),
    ],
    "fundamentals": [
        ("loaders/loadcompanyprofile.py", []),
        ("loaders/loadearningshistory.py", []),
        ("loaders/load_earnings_calendar.py", []),
        ("loaders/loadearningsestimates.py", []),
        ("loaders/loadearningsrevisions.py", []),
        ("loaders/loadanalystsentiment.py", []),
        ("loaders/loadanalystupgradedowngrade.py", []),
    ],
    "growth_and_value": [
        ("loaders/load_growth_metrics.py", []),
        ("loaders/load_value_metrics.py", []),
        ("loaders/load_quality_metrics.py", []),
    ],
    "financial_statements": [
        ("loaders/load_income_statement.py", []),
        ("loaders/load_balance_sheet.py", []),
        ("loaders/load_cash_flow.py", []),
        ("loaders/load_ttm_aggregates.py", []),
    ],
    "research": [
        ("loaders/loadstockscores.py", []),
        ("loaders/loadaaiidata.py", []),
        ("loaders/loadseasonality.py", []),
    ],
}

QUICK_LOADERS = {
    "foundation": LOADER_GROUPS["foundation"],
    "prices_and_technicals": LOADER_GROUPS["prices_and_technicals"],
    "trend_and_scores": LOADER_GROUPS["trend_and_scores"],
    "market_context": LOADER_GROUPS["market_context"],
}


def run_loader(script: str, args: List[str] = None) -> bool:
    """Run a single loader script. Return True if successful."""
    args = args or []
    try:
        cmd = ["python3", script] + args
        logger.info(f"  ▶️  {Path(script).name} {' '.join(args)}")
        # Increase timeout for price loaders (yfinance is slow on large symbol sets)
        timeout = 1800 if "price" in script.lower() else 600
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        if result.returncode == 0:
            logger.info(f"  ✅ {Path(script).name}")
            return True
        else:
            logger.error(f"  ❌ {Path(script).name} failed")
            if result.stderr:
                logger.error(f"     Error: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"  ⏱️  {Path(script).name} timeout")
        return False
    except Exception as e:
        logger.error(f"  💥 {Path(script).name}: {e}")
        return False


def run_loaders(groups: dict, symbols: Optional[str] = None) -> dict:
    """Run loader groups. Return summary."""
    load_env()

    total = 0
    passed = 0
    failed = 0

    logger.info("\n" + "="*70)
    logger.info("LOADING DATA" + (" FOR SYMBOLS: " + symbols if symbols else ""))
    logger.info("="*70)

    for group_name, loaders in groups.items():
        logger.info(f"\n[{group_name.upper()}]")
        for script, args in loaders:
            total += 1
            loader_args = args.copy()
            if symbols:
                loader_args.extend(["--symbols", symbols])

            if run_loader(script, loader_args):
                passed += 1
            else:
                failed += 1

    logger.info("\n" + "="*70)
    logger.info(f"SUMMARY: {passed}/{total} loaders passed, {failed} failed")
    logger.info("="*70 + "\n")

    return {"passed": passed, "failed": failed, "total": total}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run all data loaders")
    parser.add_argument("--quick", action="store_true", help="Load only critical loaders for orchestrator")
    parser.add_argument("--symbols", type=str, help="Specific symbols (comma-separated)")
    args = parser.parse_args()

    groups = QUICK_LOADERS if args.quick else LOADER_GROUPS
    result = run_loaders(groups, args.symbols)

    sys.exit(0 if result["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
