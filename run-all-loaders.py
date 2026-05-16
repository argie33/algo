#!/usr/bin/env python3
import os
import sys
import time
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# Tier 0: Must run first (no dependencies)
tier_0 = ['loadstocksymbols.py']

# Tier 1: Price data (depends on symbols, can run in parallel with tier 2)
tier_1_prices = [
    'loadpricedaily.py', 'loadetfpricedaily.py',
]

# Tier 1b: Price aggregates (depends on tier 1, run after daily prices)
tier_1b_aggregates = [
    'load_price_aggregate.py',  # Generates weekly and monthly from daily
    'load_etf_price_aggregate.py',  # Generates weekly and monthly ETF prices
    # Note: technical_data_daily is populated by load_algo_metrics_daily.py in Tier 4
]

# Tier 2: Reference data (no data deps, just symbol deps, can run in parallel)
# Note: Annual financial data only (quarterly empty, TTM depends on quarterly, stubs and broken loaders removed)
tier_2_reference = [
    'loadcompanyprofile.py',
    # Annual financials only
    ('load_income_statement.py', []), ('load_balance_sheet.py', []), ('load_cash_flow.py', []),
    'loadearningshistory.py', 'loadearningsrevisions.py',
    'load_earnings_calendar.py',  # Upcoming earnings dates for blackout enforcement
    'load_key_metrics.py',
    'loadmarketindices.py', 'loadseasonality.py',
    'loadsectors.py',  # Note: industry_ranking populated by loadsectors.py
    ('loadstockscores.py', ['--parallelism', '16']),  # 16 workers: compensates for retry delays
    'loadecondata.py', 'loadaaiidata.py', 'loadfeargreed.py',
]

# Tier 2b: Computed metrics (depends on tier 2 financials)
tier_2b_metrics = [
    'load_growth_metrics.py',
    'load_quality_metrics.py',
    'load_value_metrics.py',
]

# Tier 3: Technical signals (depends on prices)
tier_3_signals = [
    'loadbuyselldaily.py', 'loadbuysell_etf_daily.py',
]

# Tier 3b: Signal aggregates (depends on tier 3)
tier_3b_aggregates = [
    'load_buysell_aggregate.py',  # Generates weekly and monthly signals
    'load_buysell_etf_aggregate.py',  # Generates weekly and monthly ETF signals
]

# Tier 4: Algo metrics (depends on signals)
tier_4_metrics = ['load_algo_metrics_daily.py']

# All loaders in execution order (but within tiers, parallel)
tiers = [
    ('Tier 0: Stock symbols', tier_0),
    ('Tier 1: Price data (parallel)', tier_1_prices),
    ('Tier 1b: Price aggregates (weekly/monthly)', tier_1b_aggregates),
    ('Tier 2: Reference data (parallel)', tier_2_reference),
    ('Tier 2b: Computed metrics (quality/growth/value)', tier_2b_metrics),
    ('Tier 3: Trading signals (parallel)', tier_3_signals),
    ('Tier 3b: Signal aggregates (weekly/monthly)', tier_3b_aggregates),
    ('Tier 4: Algo metrics', tier_4_metrics),
]

all_loaders = tier_0 + tier_1_prices + tier_1b_aggregates + tier_2_reference + tier_2b_metrics + tier_3_signals + tier_3b_aggregates + tier_4_metrics
logger.info(f"\n{'='*70}")
logger.info(f"Running {len(all_loaders)} loaders across 5 dependency tiers")
logger.info(f"{'='*70}\n")

failed = []
successful = []
rate_limited = []
total_start = time.time()

def run_loader(loader_spec) -> Tuple[str, bool, bool, str]:
    """Run a single loader.

    Accepts either:
    - 'loader.py' (string)
    - ('loader.py', ['--arg', 'value']) (tuple)

    Returns (loader_name, success, rate_limited, error_msg).
    """
    if isinstance(loader_spec, tuple):
        loader, args = loader_spec
        loader_name = f"{loader} {' '.join(args)}"
    else:
        loader = loader_spec
        args = []
        loader_name = loader

    if not os.path.exists(loader):
        return (loader_name, False, False, "not found")

    try:
        result = subprocess.run(
            ['python3', loader] + args,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            return (loader_name, True, False, "")
        elif '429' in result.stderr or 'rate' in result.stderr.lower():
            return (loader_name, False, True, result.stderr[:200])
        else:
            return (loader_name, False, False, result.stderr[:200])

    except subprocess.TimeoutExpired:
        return (loader_name, False, False, "timeout")
    except Exception as e:
        return (loader_name, False, False, str(e)[:100])

def run_tier(tier_name: str, loaders: List[str], workers: int = 1) -> None:
    """Run a tier of loaders in parallel."""
    logger.info(f"\n{tier_name}")
    logger.info(f"  Starting {len(loaders)} loaders (max {workers} workers)...")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_loader, loader): loader for loader in loaders}
        completed = 0

        for future in as_completed(futures):
            completed += 1
            loader, success, rate_limited_flag, error = future.result()

            if success:
                successful.append(loader)
                logger.info(f"  ✓ {loader}")
            elif rate_limited_flag:
                rate_limited.append(loader)
                logger.warning(f"  ⚠ {loader} (rate limited)")
            else:
                failed.append(loader)
                if error and error != "not found":
                    logger.error(f"  ✗ {loader} ({error})")
                else:
                    logger.error(f"  ✗ {loader}")

            if completed % 10 == 0:
                logger.info(f"    {completed}/{len(loaders)} complete")

# Execute tiers sequentially (respecting data dependencies)
for tier_name, loaders in tiers:
    run_tier(tier_name, loaders)

elapsed = time.time() - total_start
logger.info(f"\n{'='*70}")
logger.info(f"SUMMARY (completed in {elapsed:.1f}s)")
logger.info(f"{'='*70}")
logger.info(f"Successful: {len(successful)}/{len(all_loaders)}")
logger.info(f"Failed: {len(failed)}")
logger.info(f"Rate Limited: {len(rate_limited)}")

if failed:
    logger.info(f"\nFailed loaders:")
    for loader in failed[:5]:
        logger.info(f"  - {loader}")
    if len(failed) > 5:
        logger.info(f"  ... and {len(failed)-5} more")

if rate_limited:
    logger.info(f"\nRate limited loaders (retry later):")
    for loader in rate_limited[:5]:
        logger.info(f"  - {loader}")
    if len(rate_limited) > 5:
        logger.info(f"  ... and {len(rate_limited)-5} more")

logger.info(f"\n{'='*70}\n")

sys.exit(0 if len(failed) == 0 else 1)
