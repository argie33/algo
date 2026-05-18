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
# REFACTORED: Consolidated 4 loaders (loadpricedaily, load_price_aggregate, loadetfpricedaily, load_etf_price_aggregate)
# into 1 parametrized loader using native yfinance intervals (1d/1wk/1mo) instead of local aggregation
tier_1_prices = [
    ('loadpricedaily.py', ['--interval', '1d']),  # Daily stock prices from yfinance
    ('loadpricedaily.py', ['--interval', '1d', '--asset-class', 'etf']),  # Daily ETF prices
]

# Tier 1b: Price aggregates (depends on tier 1, run after daily prices)
# Now uses native yfinance intervals instead of client-side aggregation
tier_1b_aggregates = [
    ('loadpricedaily.py', ['--interval', '1wk']),  # Weekly stock prices (native API call)
    ('loadpricedaily.py', ['--interval', '1mo']),  # Monthly stock prices (native API call)
    ('loadpricedaily.py', ['--interval', '1wk', '--asset-class', 'etf']),  # Weekly ETF prices
    ('loadpricedaily.py', ['--interval', '1mo', '--asset-class', 'etf']),  # Monthly ETF prices
]

# Tier 1c: Technical indicators (depends on tier 1 prices)
tier_1c_technical = [
    'load_technical_data_daily.py',
    'load_market_health_daily.py',
]

# Tier 1d: Trend template (depends on tier 1c technical)
tier_1d_trend = [
    'load_trend_criteria_data.py',
]

tier_2_reference = [
    # Annual financials
    ('load_income_statement.py', ['--period', 'annual']),
    ('load_balance_sheet.py', ['--period', 'annual']),
    ('load_cash_flow.py', ['--period', 'annual']),
    # Quarterly financials (raw SEC data, one quarter at a time)
    ('load_income_statement.py', ['--period', 'quarterly']),
    ('load_balance_sheet.py', ['--period', 'quarterly']),
    ('load_cash_flow.py', ['--period', 'quarterly']),
    'loadearningshistory.py', 'loadearningsrevisions.py', 'loadearningsestimates.py',
    'loadmarketindices.py', 'loadseasonality.py',
    'loadecondata.py', 'loadaaiidata.py', 'loadfeargreed.py',
    # Company and sentiment data
    'loadcompanyprofile.py', 'loadanalystsentiment.py', 'loadanalystupgradedowngrade.py',
    # Calendar data
    'load_earnings_calendar.py',
    # Sector and industry data
    'loadsectors.py', 'loadindustryranking.py', 'loadnaaim.py',
]

# Tier 2c: TTM aggregates (depends on quarterly financials from tier 2)
tier_2c_ttm = [
    'loadttmincomestatement.py',  # Sums 4 most recent quarters
    'loadttmcashflow.py',         # Sums 4 most recent quarters
]

# Tier 2b: Computed metrics (depends on tier 2 financials)
tier_2b_metrics = [
    'load_growth_metrics.py',
    'load_quality_metrics.py',
    'load_value_metrics.py',
]

# Tier 2d: Stock scores (depends on quality/growth/value metrics from tier 2b)
tier_2d_scores = [
    ('loadstockscores.py', ['--parallelism', '16']),  # 16 workers, depends on tier 2b metrics
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

# Tier 4: Signal quality scores and algo metrics (depends on signals)
tier_4_metrics = [
    'load_signal_quality_scores.py',
]

# All loaders in execution order (but within tiers, parallel)
# Format: (tier_name, loaders, workers)
tiers = [
    ('Tier 0: Stock symbols', tier_0, 1),
    ('Tier 1: Price data (parallel)', tier_1_prices, 2),  # Reduced: 4→2 to avoid Alpaca rate limits
    ('Tier 1b: Price aggregates (weekly/monthly)', tier_1b_aggregates, 2),
    ('Tier 1c: Technical indicators (RSI, MACD, SMA, EMA, etc.)', tier_1c_technical, 2),
    ('Tier 1d: Trend template data (depends on tier 1c)', tier_1d_trend, 2),
    ('Tier 2: Reference data (parallel)', tier_2_reference, 2),  # Reduced: 4→2 to avoid API timeouts
    ('Tier 2c: TTM aggregates (from quarterly)', tier_2c_ttm, 2),
    ('Tier 2b: Computed metrics (quality/growth/value)', tier_2b_metrics, 4),  # CPU-bound, keep at 4
    ('Tier 2d: Stock scores (depends on tier 2b metrics)', tier_2d_scores, 4),
    ('Tier 3: Trading signals (parallel)', tier_3_signals, 4),  # CPU-bound, keep at 4
    ('Tier 3b: Signal aggregates (weekly/monthly)', tier_3b_aggregates, 2),
    ('Tier 4: Signal quality scores and metrics', tier_4_metrics, 4),
]

all_loaders = tier_0 + tier_1_prices + tier_1b_aggregates + tier_1c_technical + tier_1d_trend + tier_2_reference + tier_2c_ttm + tier_2b_metrics + tier_2d_scores + tier_3_signals + tier_3b_aggregates + tier_4_metrics
logger.info(f"\n{'='*70}")
logger.info(f"Running {len(all_loaders)} loaders across 12 dependency tiers")
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

    # Look for loader in loaders/ subdirectory
    loader_path = os.path.join('loaders', loader)
    if not os.path.exists(loader_path):
        return (loader_name, False, False, "not found")

    try:
        env = os.environ.copy()
        env['PYTHONPATH'] = os.getcwd()
        # Increase timeout for data-heavy loaders (loadpricedaily ~30+ min for 500+ stocks with yfinance rate limit)
        # price/scores/income/balance/cashflow loaders are heavy; others are lighter
        heavy_loaders = ['price', 'scores', 'income', 'balance', 'cashflow', 'financial']
        loader_timeout = 7200 if any(x in loader.lower() for x in heavy_loaders) else 1800  # 2h for heavy, 30m for others
        result = subprocess.run(
            ['python3', loader_path] + args,
            capture_output=True,
            text=True,
            timeout=loader_timeout,
            env=env
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

for tier_name, loaders, workers in tiers:
    run_tier(tier_name, loaders, workers)

elapsed = time.time() - total_start
logger.info(f"\n{'='*70}")
logger.info(f"SUMMARY (completed in {elapsed:.1f}s)")
logger.info(f"{'='*70}")
logger.info(f"Successful: {len(successful)}/{len(all_loaders)}")
logger.info(f"Failed: {len(failed)}")
logger.info(f"Rate Limited: {len(rate_limited)}")

# Run data loader health check to populate data_loader_status table
logger.info(f"\n{'='*70}")
logger.info(f"DATA LOADER HEALTH CHECK")
logger.info(f"{'='*70}\n")
try:
    from utils.monitoring.loader_health_tracker import LoaderHealthTracker
    tracker = LoaderHealthTracker()
    tracker.connect()
    try:
        tracker.run_health_check(verbose=True)
    finally:
        tracker.disconnect()
except Exception as e:
    logger.error(f"Health check failed: {e}")

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
