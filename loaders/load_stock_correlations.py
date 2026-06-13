#!/usr/bin/env python3
"""Stock Correlations Loader -- Pre-compute Pearson correlations between symbols.

PHASE 2 ARCHITECTURAL FIX: Move correlation matrix calculation from API
(market.js /api/market/correlation) to pre-computed database.

Current state: market.js calculates O(N^2) Pearson correlations in-memory
on each request (5-15 seconds). This loader pre-computes correlations
(5-15 minutes once daily) so API can fetch from table (~100ms).

Computes:
- 1-month, 3-month, 6-month, 1-year correlations for all symbol pairs
- Uses overlapping trading days to calculate daily returns
- Pearson correlation of aligned returns

Run: python3 load_stock_correlations.py [--symbols "AAPL,MSFT,SPY" --parallelism 1]
"""
from loaders.loader_helper import setup_imports
setup_imports()

import argparse
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple, Dict
from zoneinfo import ZoneInfo
import math
import logging

from utils.loader_helpers import get_active_symbols
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

def calculate_pearson_correlation(returns1: List[float], returns2: List[float]) -> Optional[float]:
    """Calculate Pearson correlation from two aligned return series."""
    if len(returns1) < 2 or len(returns2) < 2 or len(returns1) != len(returns2):
        return None

    n = len(returns1)
    mean1 = sum(returns1) / n
    mean2 = sum(returns2) / n

    covariance = sum((returns1[i] - mean1) * (returns2[i] - mean2) for i in range(n))
    sd1_sq = sum((returns1[i] - mean1) ** 2 for i in range(n))
    sd2_sq = sum((returns2[i] - mean2) ** 2 for i in range(n))

    if sd1_sq == 0 or sd2_sq == 0:
        return 0.0

    return covariance / (math.sqrt(sd1_sq * sd2_sq))

def fetch_price_data(symbols: List[str], days: int) -> Dict[str, List[Tuple[date, float]]]:
    """Fetch price data for symbols over the last N days."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days + 30)  # +30 days buffer for weekends/holidays

    prices_by_symbol = {}
    with DatabaseContext('read') as cur:
        cur.execute("""
            SELECT symbol, date, close
            FROM price_daily
            WHERE symbol = ANY(%s)
              AND date >= %s::DATE
            ORDER BY symbol, date ASC
        """, [symbols, start_date])
        for row in cur.fetchall():
            symbol = row["symbol"]
            if symbol not in prices_by_symbol:
                prices_by_symbol[symbol] = []
            prices_by_symbol[symbol].append((row["date"], float(row["close"])))

    return prices_by_symbol

def calculate_returns(prices: List[Tuple[date, float]]) -> Tuple[List[float], List[date]]:
    """Calculate daily returns from price series."""
    if len(prices) < 2:
        return [], []

    returns = []
    dates = []
    for i in range(1, len(prices)):
        prev_close = prices[i - 1][1]
        curr_close = prices[i][1]
        if prev_close > 0:
            ret = (curr_close - prev_close) / prev_close
            returns.append(ret)
            dates.append(prices[i][0])

    return returns, dates

def load_correlations(
    symbols: List[str],
    period_days: int,
) -> List[Dict]:
    """Calculate correlation matrix for given symbols and period."""
    prices = fetch_price_data(symbols, period_days)

    # Filter symbols with insufficient data
    valid_symbols = [s for s in symbols if s in prices and len(prices[s]) >= 2]
    if not valid_symbols:
        logger.warning(f"No valid price data found for symbols: {symbols}")
        return []

    logger.info(f"Calculating {period_days}-day correlations for {len(valid_symbols)} symbols")

    # Pre-calculate returns for all symbols
    returns_by_symbol = {}
    dates_by_symbol = {}
    for symbol in valid_symbols:
        rets, date_list = calculate_returns(prices[symbol])
        if rets:
            returns_by_symbol[symbol] = rets
            dates_by_symbol[symbol] = date_list

    # Calculate correlations for all pairs
    correlations = []
    processed_pairs = set()

    for i, symbol1 in enumerate(valid_symbols):
        for symbol2 in valid_symbols[i + 1:]:
            pair_key = (symbol1, symbol2) if symbol1 < symbol2 else (symbol2, symbol1)
            if pair_key in processed_pairs:
                continue
            processed_pairs.add(pair_key)

            # Find overlapping dates
            dates1 = set(dates_by_symbol.get(symbol1, []))
            dates2 = set(dates_by_symbol.get(symbol2, []))
            overlapping = sorted(dates1 & dates2)

            if len(overlapping) < 2:
                logger.debug(f"  Skipping {symbol1}-{symbol2}: only {len(overlapping)} overlapping dates")
                continue

            # Align returns on overlapping dates
            date_to_idx1 = {d: idx for idx, d in enumerate(dates_by_symbol[symbol1])}
            date_to_idx2 = {d: idx for idx, d in enumerate(dates_by_symbol[symbol2])}

            aligned_returns1 = [returns_by_symbol[symbol1][date_to_idx1[d]] for d in overlapping]
            aligned_returns2 = [returns_by_symbol[symbol2][date_to_idx2[d]] for d in overlapping]

            # Calculate correlation
            corr = calculate_pearson_correlation(aligned_returns1, aligned_returns2)
            if corr is not None:
                correlations.append({
                    "symbol1": pair_key[0],
                    "symbol2": pair_key[1],
                    "correlation": corr,
                    "days_overlapped": len(overlapping),
                })

    return correlations

def upsert_correlations(
    correlations_1m: List[Dict],
    correlations_3m: List[Dict],
    correlations_6m: List[Dict],
    correlations_1y: List[Dict],
) -> int:
    """Upsert correlation data into database."""
    # Build a merged map: (symbol1, symbol2) -> {1m, 3m, 6m, 1y correlations}
    corr_map = {}

    for corrs, col_name in [
        (correlations_1m, "correlation_1m"),
        (correlations_3m, "correlation_3m"),
        (correlations_6m, "correlation_6m"),
        (correlations_1y, "correlation_1y"),
    ]:
        for corr in corrs:
            key = (corr["symbol1"], corr["symbol2"])
            if key not in corr_map:
                corr_map[key] = {"symbol1": corr["symbol1"], "symbol2": corr["symbol2"]}
            corr_map[key][col_name] = corr["correlation"]

    # Upsert into database
    rows_inserted = 0
    with DatabaseContext('write') as cur:
        for (symbol1, symbol2), data in corr_map.items():
            cur.execute("""
                INSERT INTO stock_correlations (symbol1, symbol2, correlation_1m, correlation_3m, correlation_6m, correlation_1y, days_overlapped, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (symbol1, symbol2)
                DO UPDATE SET
                    correlation_1m = EXCLUDED.correlation_1m,
                    correlation_3m = EXCLUDED.correlation_3m,
                    correlation_6m = EXCLUDED.correlation_6m,
                    correlation_1y = EXCLUDED.correlation_1y,
                    updated_at = CURRENT_TIMESTAMP
            """, [
                data["symbol1"],
                data["symbol2"],
                data.get("correlation_1m"),
                data.get("correlation_3m"),
                data.get("correlation_6m"),
                data.get("correlation_1y"),
                data.get("days_overlapped", 0),
            ])
            rows_inserted += 1

    return rows_inserted

def main():
    parser = argparse.ArgumentParser(description="Load stock correlations")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols (default: active symbols)")
    parser.add_argument("--parallelism", type=int, default=1, help="Parallelism (not used, for compatibility)")
    args = parser.parse_args()

    # Determine which symbols to process
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        with DatabaseContext('read') as cur:
            symbols = get_active_symbols(cur)

    if not symbols:
        logger.error("No symbols to process")
        return

    logger.info(f"Loading correlations for {len(symbols)} symbols: {symbols[:10]}{'...' if len(symbols) > 10 else ''}")

    # Calculate correlations for different periods
    try:
        corr_1m = load_correlations(symbols, 30)
        logger.info(f"  1-month: {len(corr_1m)} pairs")

        corr_3m = load_correlations(symbols, 90)
        logger.info(f"  3-month: {len(corr_3m)} pairs")

        corr_6m = load_correlations(symbols, 180)
        logger.info(f"  6-month: {len(corr_6m)} pairs")

        corr_1y = load_correlations(symbols, 365)
        logger.info(f"  1-year: {len(corr_1y)} pairs")

        # Upsert all correlations
        rows = upsert_correlations(corr_1m, corr_3m, corr_6m, corr_1y)
        logger.info(f"Upserted {rows} correlation pairs")

    except Exception as e:
        logger.error(f"Error loading correlations: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
