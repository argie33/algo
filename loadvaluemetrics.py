#!/usr/bin/env python3
"""
Value Metrics Calculator
Calculates raw value input metrics (not scores) for use in loadstockscores.py

Storage: Metrics are stored as JSON in stock_scores.value_inputs (JSONB column)

Metrics Calculated:
1. Valuation Multiples: P/E (forward/trailing), P/B, P/S, EV/EBITDA
2. Dividend Yield: Annual dividend as % of stock price
3. FCF Yield: Free cash flow / market cap
4. Market Benchmarks: P/E, P/B, P/S, EV/EBITDA, FCF Yield, Dividend Yield
5. Sector Benchmarks: P/E, P/B, P/S, EV/EBITDA, FCF Yield, Dividend Yield
6. PEG Ratio: P/E / earnings growth rate
7. DCF Intrinsic Value: Discounted cash flow valuation (currently disabled)
8. Percentile Ranks: Per-metric ranking across all stocks

Note: Scoring logic is in loadstockscores.py - this only calculates inputs
Phase 1: Calculate and store value metrics as JSON
Phase 2: Calculate percentile ranks and merge into value_inputs

Updated: 2025-10-20 - Fixed: Removed unused value_metrics table, clarified storage location"""

import json
import logging
import math
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

SCRIPT_NAME = "calculate_value_metrics.py"


def get_db_config():
    """Get database configuration from environment or AWS Secrets Manager"""
    if os.getenv("USE_LOCAL_DB") == "true" or os.getenv("DB_HOST"):
        logging.info("Using local database configuration")
        return {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "5432")),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "password"),
            "dbname": os.getenv("DB_NAME", "stocks"),
        }

    # AWS Secrets Manager for production
    import boto3
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])
    sec = json.loads(resp["SecretString"])
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"],
    }


def calculate_market_benchmarks(cursor):
    """Calculate market-wide median valuation multiples"""
    logging.info("Calculating market benchmarks...")

    cursor.execute("""
        SELECT
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.trailing_pe) FILTER (WHERE km.trailing_pe > 0 AND km.trailing_pe < 1000) as market_pe_median,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.price_to_book) FILTER (WHERE km.price_to_book > 0) as market_pb_median,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.price_to_sales_ttm) FILTER (WHERE km.price_to_sales_ttm > 0) as market_ps_median,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.ev_to_ebitda) FILTER (WHERE km.ev_to_ebitda > 0) as market_ev_ebitda_median,
            -- FCF Yield: use only stocks where FCF data actually exists and market cap can be calculated
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
                (km.free_cashflow / NULLIF(km.enterprise_value - km.total_debt + km.total_cash, 0)) * 100
            ) FILTER (WHERE km.free_cashflow IS NOT NULL AND km.free_cashflow > 0
                      AND km.enterprise_value IS NOT NULL AND km.total_debt IS NOT NULL AND km.total_cash IS NOT NULL
                      AND (km.enterprise_value - km.total_debt + km.total_cash) > 0) as market_fcf_yield_median,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.dividend_yield) FILTER (WHERE km.dividend_yield >= 0) as market_dividend_yield_median,
            COUNT(*) as stock_count
        FROM key_metrics km
        LEFT JOIN stock_symbols ss ON km.ticker = ss.symbol
        WHERE (ss.etf IS NULL OR ss.etf != 'Y')
    """)

    row = cursor.fetchone()
    benchmarks = {
        "pe_median": float(row[0]) if row[0] is not None else None,
        "pb_median": float(row[1]) if row[1] is not None else None,
        "ps_median": float(row[2]) if row[2] is not None else None,
        "ev_ebitda_median": float(row[3]) if row[3] is not None else None,
        "fcf_yield_median": float(row[4]) if row[4] is not None else None,
        "dividend_yield_median": float(row[5]) if row[5] is not None else None,
        "stock_count": int(row[6]) if row[6] is not None else 0,
    }

    pe_val = f"{benchmarks['pe_median']:.2f}" if benchmarks['pe_median'] is not None else 'N/A'
    pb_val = f"{benchmarks['pb_median']:.2f}" if benchmarks['pb_median'] is not None else 'N/A'
    ps_val = f"{benchmarks['ps_median']:.2f}" if benchmarks['ps_median'] is not None else 'N/A'
    ev_val = f"{benchmarks['ev_ebitda_median']:.2f}" if benchmarks['ev_ebitda_median'] is not None else 'N/A'
    fcf_val = f"{benchmarks['fcf_yield_median']:.2f}" if benchmarks['fcf_yield_median'] is not None else 'N/A'
    div_val = f"{benchmarks['dividend_yield_median']:.2f}" if benchmarks['dividend_yield_median'] is not None else 'N/A'
    logging.info(f"  Market PE Median: {pe_val}")
    logging.info(f"  Market PB Median: {pb_val}")
    logging.info(f"  Market PS Median: {ps_val}")
    logging.info(f"  Market EV/EBITDA Median: {ev_val}")
    logging.info(f"  Market FCF Yield Median: {fcf_val}%")
    logging.info(f"  Market Dividend Yield Median: {div_val}%")
    logging.info(f"  Stocks in Market: {benchmarks['stock_count']}")

    return benchmarks


def get_sector_benchmarks(cursor):
    """Calculate sector-level median valuation multiples dynamically"""
    logging.info("Calculating sector benchmarks...")

    cursor.execute("""
        SELECT
            cp.sector,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.trailing_pe) FILTER (WHERE km.trailing_pe > 0 AND km.trailing_pe < 1000) as sector_pe_median,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.price_to_book) FILTER (WHERE km.price_to_book > 0) as sector_pb_median,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.price_to_sales_ttm) FILTER (WHERE km.price_to_sales_ttm > 0) as sector_ps_median,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.ev_to_ebitda) FILTER (WHERE km.ev_to_ebitda > 0) as sector_ev_ebitda_median,
            -- FCF Yield: use only stocks where FCF data actually exists
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
                (km.free_cashflow / NULLIF(km.enterprise_value - km.total_debt + km.total_cash, 0)) * 100
            ) FILTER (WHERE km.free_cashflow IS NOT NULL AND km.free_cashflow > 0
                      AND km.enterprise_value IS NOT NULL AND km.total_debt IS NOT NULL AND km.total_cash IS NOT NULL
                      AND (km.enterprise_value - km.total_debt + km.total_cash) > 0) as sector_fcf_yield_median,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.dividend_yield) FILTER (WHERE km.dividend_yield >= 0) as sector_dividend_yield_median,
            COUNT(*) as stock_count
        FROM key_metrics km
        LEFT JOIN company_profile cp ON km.ticker = cp.ticker
        LEFT JOIN stock_symbols ss ON km.ticker = ss.symbol
        WHERE cp.sector IS NOT NULL
          AND cp.sector != ''
          AND (ss.etf IS NULL OR ss.etf != 'Y')
        GROUP BY cp.sector
        HAVING COUNT(*) >= 3
    """)

    sector_data = {}
    for row in cursor.fetchall():
        sector_data[row[0]] = {
            "pe_median": float(row[1]) if row[1] else None,
            "pb_median": float(row[2]) if row[2] else None,
            "ps_median": float(row[3]) if row[3] else None,
            "ev_ebitda_median": float(row[4]) if row[4] else None,
            "fcf_yield_median": float(row[5]) if row[5] else None,
            "dividend_yield_median": float(row[6]) if row[6] else None,
            "stock_count": int(row[7]) if row[7] else 0,
        }

    logging.info(f"  Calculated benchmarks for {len(sector_data)} sectors")
    return sector_data


def calculate_fcf_yield(market_cap: float, free_cashflow: float) -> Optional[float]:
    """Calculate Free Cash Flow Yield"""
    if market_cap and free_cashflow and market_cap > 0:
        return (free_cashflow / market_cap) * 100
    return None


def calculate_peg_ratio(pe_ratio: float, growth_rate: float) -> Optional[float]:
    """Calculate PEG Ratio (Peter Lynch formula)"""
    if pe_ratio and growth_rate and growth_rate > 0:
        return pe_ratio / growth_rate
    return None


def calculate_dcf_intrinsic(
    free_cashflow: float,
    growth_rate: float,
    shares_outstanding: float,
    total_debt: float,
    total_cash: float,
) -> Optional[float]:
    """
    Calculate DCF intrinsic value per share
    Uses simplified 2-stage growth model
    NOTE: Beta must be available from risk_metrics table - no fallback to 1.0
    """
    if not (free_cashflow and shares_outstanding and free_cashflow > 0 and shares_outstanding > 0):
        return None

    # DCF requires real beta from database - no fallback calculation without it
    # If beta is needed, it must be passed as parameter or queried separately
    # For now, skip DCF if we don't have the required risk metric
    return None

    # Growth assumptions
    high_growth_rate = min(0.25, max(0.02, growth_rate or 0.05))
    terminal_growth_rate = 0.025  # 2.5%
    high_growth_years = 5

    # Project cash flows
    projected_fcf = []
    current_fcf = free_cashflow

    for year in range(1, high_growth_years + 1):
        year_growth = high_growth_rate * (1 - (year - 1) * 0.1)  # Declining growth
        current_fcf *= (1 + year_growth)
        projected_fcf.append(current_fcf)

    # Terminal value
    terminal_fcf = projected_fcf[-1] * (1 + terminal_growth_rate)
    terminal_value = terminal_fcf / (cost_of_equity - terminal_growth_rate)

    # Discount to present value
    pv_fcf = sum([fcf / ((1 + cost_of_equity) ** (i + 1)) for i, fcf in enumerate(projected_fcf)])
    pv_terminal = terminal_value / ((1 + cost_of_equity) ** high_growth_years)

    # Enterprise value
    enterprise_value = pv_fcf + pv_terminal

    # Equity value
    equity_value = enterprise_value - (total_debt or 0) + (total_cash or 0)

    # Per share value
    intrinsic_value_per_share = equity_value / shares_outstanding

    return intrinsic_value_per_share if intrinsic_value_per_share > 0 else None


def calculate_value_metrics_for_stock(
    cursor,
    ticker: str,
    market_benchmarks: Dict,
    sector_benchmarks: Dict,
) -> Optional[Dict]:
    """Calculate value metrics (inputs only, not scores) for a single stock"""

    # Get stock data with forward-looking estimates
    cursor.execute("""
        SELECT
            km.trailing_pe,
            km.forward_pe,
            km.price_to_book,
            km.ev_to_ebitda,
            km.free_cashflow,
            km.enterprise_value,
            km.peg_ratio,
            km.earnings_q_growth_pct,
            km.earnings_growth_pct,
            km.total_debt,
            km.total_cash,
            cp.sector,
            pm.shares_outstanding,
            pd.close as current_price,
            km.dividend_yield,
            km.price_to_sales_ttm
        FROM key_metrics km
        LEFT JOIN company_profile cp ON km.ticker = cp.ticker
        LEFT JOIN positioning_metrics pm ON pm.symbol = km.ticker AND pm.date = (SELECT MAX(date) FROM positioning_metrics WHERE symbol = km.ticker)
        LEFT JOIN LATERAL (
            SELECT close FROM price_daily
            WHERE symbol = km.ticker
            ORDER BY date DESC LIMIT 1
        ) pd ON true
        WHERE km.ticker = %s
    """, (ticker,))

    row = cursor.fetchone()
    if not row:
        return None

    (trailing_pe, forward_pe, pb, ev_ebitda, fcf, enterprise_val, peg,
     earnings_q_growth, earnings_growth, debt, cash, sector, shares, price,
     dividend_yield, price_to_sales) = row

    # Convert all Decimal types to float
    trailing_pe = float(trailing_pe) if trailing_pe else None
    forward_pe = float(forward_pe) if forward_pe else None
    pb = float(pb) if pb else None
    ev_ebitda = float(ev_ebitda) if ev_ebitda else None
    fcf = float(fcf) if fcf else None
    enterprise_val = float(enterprise_val) if enterprise_val else None
    peg = float(peg) if peg else None
    earnings_q_growth = float(earnings_q_growth) if earnings_q_growth else None
    earnings_growth = float(earnings_growth) if earnings_growth else None
    debt = float(debt) if debt else None
    cash = float(cash) if cash else None
    shares = float(shares) if shares else None
    price = float(price) if price else None
    dividend_yield = float(dividend_yield) if dividend_yield else None
    price_to_sales = float(price_to_sales) if price_to_sales else None

    # Use forward P/E when available (best practice), fall back to trailing P/E
    pe = forward_pe if forward_pe and forward_pe > 0 else trailing_pe
    pe_type = "forward" if (forward_pe and forward_pe > 0) else "trailing"

    # Use earnings growth (prefer annualized over quarterly)
    growth_pct = earnings_growth if earnings_growth else earnings_q_growth

    # Calculate market cap from enterprise value or price * shares
    market_cap = None
    if enterprise_val and debt is not None and cash is not None:
        market_cap = enterprise_val - debt + cash
    elif price and shares:
        market_cap = price * shares

    # NOTE: NO P/E FILTER - We include ALL stocks, even unprofitable ones (pe=None/0)
    # Unprofitable companies will use alternative metrics (P/B, P/S, EV/EBITDA)
    # This ensures we capture ALL available data without artificial exclusions
    has_any_metric = pe or pb or ev_ebitda or price_to_sales
    if not has_any_metric:
        logging.debug(f"  {ticker}: Skipping (no valuation metrics available)")
        return None

    # Get sector benchmarks (fallback to market if sector not available)
    sector_bench = sector_benchmarks.get(sector, {})
    sector_pe = sector_bench.get("pe_median", market_benchmarks["pe_median"])
    sector_pb = sector_bench.get("pb_median", market_benchmarks["pb_median"])
    sector_ps = sector_bench.get("ps_median", market_benchmarks["ps_median"])
    sector_ev = sector_bench.get("ev_ebitda_median", market_benchmarks["ev_ebitda_median"])
    sector_fcf_yield = sector_bench.get("fcf_yield_median", market_benchmarks["fcf_yield_median"])
    sector_dividend_yield = sector_bench.get("dividend_yield_median", market_benchmarks["dividend_yield_median"])

    # Calculate relative ratios (market-relative 70% + sector-relative 30%)
    pe_market_relative = pe / market_benchmarks["pe_median"] if pe else None
    pb_market_relative = pb / market_benchmarks["pb_median"] if pb else None
    ev_market_relative = ev_ebitda / market_benchmarks["ev_ebitda_median"] if ev_ebitda else None

    pe_sector_relative = pe / sector_pe if pe and sector_pe else None
    pb_sector_relative = pb / sector_pb if pb and sector_pb else None
    ev_sector_relative = ev_ebitda / sector_ev if ev_ebitda and sector_ev else None

    # Combined relative (70% market + 30% sector)
    pe_relative = None
    pb_relative = None
    ps_relative = None
    ev_relative = None
    if pe_market_relative and pe_sector_relative:
        pe_relative = (pe_market_relative * 0.7) + (pe_sector_relative * 0.3)
    elif pe_market_relative:
        pe_relative = pe_market_relative

    if pb_market_relative and pb_sector_relative:
        pb_relative = (pb_market_relative * 0.7) + (pb_sector_relative * 0.3)
    elif pb_market_relative:
        pb_relative = pb_market_relative

    # Calculate PS relative ratios
    ps_market_relative = price_to_sales / market_benchmarks["ps_median"] if price_to_sales else None
    sector_ps = sector_bench.get("ps_median", market_benchmarks["ps_median"])
    ps_sector_relative = price_to_sales / sector_ps if price_to_sales and sector_ps else None

    if ps_market_relative and ps_sector_relative:
        ps_relative = (ps_market_relative * 0.7) + (ps_sector_relative * 0.3)
    elif ps_market_relative:
        ps_relative = ps_market_relative

    if ev_market_relative and ev_sector_relative:
        ev_relative = (ev_market_relative * 0.7) + (ev_sector_relative * 0.3)
    elif ev_market_relative:
        ev_relative = ev_market_relative

    # Calculate other metrics
    fcf_yield = calculate_fcf_yield(market_cap, fcf) if market_cap and fcf else None
    peg_calc = calculate_peg_ratio(pe, growth_pct) or peg  # Use yfinance PEG if calculation fails (negative growth)
    dcf_intrinsic = calculate_dcf_intrinsic(fcf, growth_pct/100 if growth_pct else 0.05,
                                           shares, debt, cash) if fcf and shares else None
    dcf_discount_pct = None
    if dcf_intrinsic and price:
        dcf_discount_pct = ((dcf_intrinsic - price) / price) * 100

    # Return input metrics (scoring happens in loadstockscores.py)
    return {
        "ticker": ticker,
        # Valuation multiples
        "stock_pe": float(pe) if pe else None,
        "pe_type": pe_type,  # "forward" or "trailing"
        "forward_pe": float(forward_pe) if forward_pe else None,
        "trailing_pe": float(trailing_pe) if trailing_pe else None,
        "stock_pb": float(pb) if pb else None,
        "stock_ps": float(price_to_sales) if price_to_sales else None,
        "stock_ev_ebitda": float(ev_ebitda) if ev_ebitda else None,
        "dividend_yield": float(dividend_yield) if dividend_yield else None,
        # Market benchmarks
        "market_pe": market_benchmarks["pe_median"],
        "market_pb": market_benchmarks["pb_median"],
        "market_ps": market_benchmarks["ps_median"],
        "market_ev_ebitda": market_benchmarks["ev_ebitda_median"],
        "market_fcf_yield": market_benchmarks["fcf_yield_median"],
        "market_dividend_yield": market_benchmarks["dividend_yield_median"],
        # Sector benchmarks
        "sector_pe": sector_pe,
        "sector_pb": sector_pb,
        "sector_ps": sector_ps,
        "sector_ev_ebitda": sector_ev,
        "sector_fcf_yield": sector_fcf_yield,
        "sector_dividend_yield": sector_dividend_yield,
        # Relative ratios (for scoring)
        "pe_relative": round(pe_relative, 4) if pe_relative else None,
        "pb_relative": round(pb_relative, 4) if pb_relative else None,
        "ps_relative": round(ps_relative, 4) if ps_relative else None,
        "ev_relative": round(ev_relative, 4) if ev_relative else None,
        # Calculated metrics
        "fcf_yield": round(fcf_yield, 2) if fcf_yield else None,
        "peg_ratio": round(peg_calc, 2) if peg_calc else None,
        "dcf_intrinsic_value": round(dcf_intrinsic, 2) if dcf_intrinsic else None,
        "dcf_discount_pct": round(dcf_discount_pct, 2) if dcf_discount_pct else None,
        "current_price": float(price) if price else None,
        "earnings_growth_pct": float(growth_pct) if growth_pct else None,
    }


def sanitize_for_json(obj):
    """
    Convert Infinity and NaN to None for JSON serialization
    PostgreSQL JSONB type cannot store Infinity or NaN values
    """
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return None
        return obj
    return obj


def store_value_metrics(cursor, value_data: Dict, percentile_ranks: Dict = None):
    """Store value input metrics in stock_scores table"""

    # Sanitize data to handle Infinity/NaN before JSON serialization
    value_inputs_clean = sanitize_for_json({
        # Valuation multiples
        "stock_pe": value_data["stock_pe"],
        "pe_type": value_data["pe_type"],
        "forward_pe": value_data["forward_pe"],
        "trailing_pe": value_data["trailing_pe"],
        "stock_pb": value_data["stock_pb"],
        "stock_ps": value_data["stock_ps"],
        "stock_ev_ebitda": value_data["stock_ev_ebitda"],
        "dividend_yield": value_data["dividend_yield"],
        # Market benchmarks
        "market_pe": value_data["market_pe"],
        "market_pb": value_data["market_pb"],
        "market_ps": value_data["market_ps"],
        "market_ev_ebitda": value_data["market_ev_ebitda"],
        "market_fcf_yield": value_data["market_fcf_yield"],
        "market_dividend_yield": value_data["market_dividend_yield"],
        # Sector benchmarks
        "sector_pe": value_data["sector_pe"],
        "sector_pb": value_data["sector_pb"],
        "sector_ps": value_data["sector_ps"],
        "sector_ev_ebitda": value_data["sector_ev_ebitda"],
        "sector_fcf_yield": value_data["sector_fcf_yield"],
        "sector_dividend_yield": value_data["sector_dividend_yield"],
        # Relative ratios
        "pe_relative": value_data["pe_relative"],
        "pb_relative": value_data["pb_relative"],
        "ev_relative": value_data["ev_relative"],
        "ps_relative": value_data.get("ps_relative"),  # Added PS relative
        # Calculated metrics
        "fcf_yield": value_data["fcf_yield"],
        "peg_ratio": value_data["peg_ratio"],
        "dcf_intrinsic_value": value_data["dcf_intrinsic_value"],
        "dcf_discount_pct": value_data["dcf_discount_pct"],
        "current_price": value_data["current_price"],
        "earnings_growth_pct": value_data["earnings_growth_pct"],
    })

    # Add percentile ranks if calculated
    if percentile_ranks:
        value_inputs_clean.update({
            "pe_percentile_rank": percentile_ranks.get("pe_percentile"),
            "pb_percentile_rank": percentile_ranks.get("pb_percentile"),
            "ps_percentile_rank": percentile_ranks.get("ps_percentile"),
            "ev_percentile_rank": percentile_ranks.get("ev_percentile"),
            "peg_percentile_rank": percentile_ranks.get("peg_percentile"),
            "fcf_yield_percentile_rank": percentile_ranks.get("fcf_yield_percentile"),
            "dividend_yield_percentile_rank": percentile_ranks.get("dividend_yield_percentile"),
        })

    cursor.execute("""
        UPDATE stock_scores
        SET value_inputs = %s::jsonb
        WHERE symbol = %s
    """, (
        json.dumps(value_inputs_clean),
        value_data["ticker"],
    ))


def calculate_percentile_ranks(cursor):
    """
    Calculate percentile ranks for all value metrics across all stocks.
    Returns a dict mapping symbol to its percentile ranks.

    Lower is better for: P/E, P/B, P/S, EV/EBITDA, PEG
    Higher is better for: FCF Yield, Dividend Yield
    """
    logging.info("Calculating percentile ranks for all stocks...")

    # Fetch all stocks' value metrics from the value_inputs JSON column
    # NOTE: We fetch ALL stocks (including those with NULL value_inputs) because
    # this function is responsible for calculating and populating value_inputs.
    # The circular dependency WHERE value_inputs IS NOT NULL was preventing
    # calculation for ~1,829 stocks that had never been processed.
    cursor.execute("""
        SELECT
            symbol,
            value_inputs
        FROM stock_scores
        ORDER BY symbol
    """)

    all_stocks = cursor.fetchall()
    stock_metrics = {}

    # Parse JSON and collect all metrics
    for symbol, value_inputs_json in all_stocks:
        if value_inputs_json:
            try:
                # PostgreSQL returns JSONB as dict, JSON as string
                if isinstance(value_inputs_json, dict):
                    metrics = value_inputs_json
                else:
                    metrics = json.loads(value_inputs_json)
                stock_metrics[symbol] = metrics
            except (json.JSONDecodeError, TypeError):
                continue

    if not stock_metrics:
        logging.warning("  No stocks with value metrics found")
        return {}

    # Extract metric values for percentile calculation
    pe_relatives = []
    pb_relatives = []
    ps_relatives = []
    ev_relatives = []
    peg_ratios = []
    fcf_yields = []
    dividend_yields = []

    for symbol, metrics in stock_metrics.items():
        if metrics.get("pe_relative"):
            pe_relatives.append((symbol, metrics["pe_relative"]))
        if metrics.get("pb_relative"):
            pb_relatives.append((symbol, metrics["pb_relative"]))
        if metrics.get("ps_relative"):
            ps_relatives.append((symbol, metrics["ps_relative"]))
        if metrics.get("ev_relative"):
            ev_relatives.append((symbol, metrics["ev_relative"]))
        if metrics.get("peg_ratio"):
            peg_ratios.append((symbol, metrics["peg_ratio"]))
        if metrics.get("fcf_yield"):
            fcf_yields.append((symbol, metrics["fcf_yield"]))
        if metrics.get("dividend_yield"):
            dividend_yields.append((symbol, metrics["dividend_yield"]))

    # Calculate percentile ranks (lower is better for P/E, P/B, P/S, EV, PEG)
    percentile_ranks = {}

    def calculate_percentile_position(symbol, value, values_list, lower_is_better=True):
        """
        Calculate percentile rank position (0-100).
        lower_is_better=True: Lower values get higher percentile (cheaper stocks)
        lower_is_better=False: Higher values get higher percentile (better yields)
        NO FALLBACK - Returns None if insufficient data
        """
        if not values_list:
            return None  # FAIL - No comparison data available

        values_only = [v for _, v in values_list]
        sorted_values = sorted(values_only)

        # Find percentile position
        position = sum(1 for v in sorted_values if v < value) / len(sorted_values) * 100

        # Invert for metrics where lower is better
        if lower_is_better:
            position = 100 - position

        return round(position, 1)

    # For each metric type, calculate percentiles
    for symbol, value in pe_relatives:
        if symbol not in percentile_ranks:
            percentile_ranks[symbol] = {}
        percentile_ranks[symbol]["pe_percentile"] = calculate_percentile_position(
            symbol, value, pe_relatives, lower_is_better=True
        )

    for symbol, value in pb_relatives:
        if symbol not in percentile_ranks:
            percentile_ranks[symbol] = {}
        percentile_ranks[symbol]["pb_percentile"] = calculate_percentile_position(
            symbol, value, pb_relatives, lower_is_better=True
        )

    for symbol, value in ps_relatives:
        if symbol not in percentile_ranks:
            percentile_ranks[symbol] = {}
        percentile_ranks[symbol]["ps_percentile"] = calculate_percentile_position(
            symbol, value, ps_relatives, lower_is_better=True
        )

    for symbol, value in ev_relatives:
        if symbol not in percentile_ranks:
            percentile_ranks[symbol] = {}
        percentile_ranks[symbol]["ev_percentile"] = calculate_percentile_position(
            symbol, value, ev_relatives, lower_is_better=True
        )

    for symbol, value in peg_ratios:
        if symbol not in percentile_ranks:
            percentile_ranks[symbol] = {}
        percentile_ranks[symbol]["peg_percentile"] = calculate_percentile_position(
            symbol, value, peg_ratios, lower_is_better=True
        )

    for symbol, value in fcf_yields:
        if symbol not in percentile_ranks:
            percentile_ranks[symbol] = {}
        percentile_ranks[symbol]["fcf_yield_percentile"] = calculate_percentile_position(
            symbol, value, fcf_yields, lower_is_better=False
        )

    for symbol, value in dividend_yields:
        if symbol not in percentile_ranks:
            percentile_ranks[symbol] = {}
        percentile_ranks[symbol]["dividend_yield_percentile"] = calculate_percentile_position(
            symbol, value, dividend_yields, lower_is_better=False
        )

    logging.info(f"  Calculated percentile ranks for {len(percentile_ranks)} stocks")
    return percentile_ranks


def ensure_stock_scores_ready(cursor):
    """Ensure stock_scores table has value_inputs column"""
    logging.info("Verifying stock_scores table structure...")

    # Check if value_inputs column exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='stock_scores' AND column_name='value_inputs'
        );
    """)

    if not cursor.fetchone()[0]:
        logging.warning("  Adding value_inputs column to stock_scores...")
        cursor.execute("""
            ALTER TABLE stock_scores ADD COLUMN value_inputs JSONB DEFAULT NULL;
        """)

    logging.info("✅ stock_scores table ready for value metrics")

def main():
    """Main execution function"""
    logging.info("=" * 80)
    logging.info("Value Metrics Loader - Starting")
    logging.info("=" * 80)

    # Connect to database
    cfg = get_db_config()
    conn = psycopg2.connect(**cfg)
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        # Ensure stock_scores table is ready
        ensure_stock_scores_ready(cursor)
        conn.commit()
        # Calculate market benchmarks
        market_benchmarks = calculate_market_benchmarks(cursor)

        # Get sector benchmarks
        sector_benchmarks = get_sector_benchmarks(cursor)

        # Get all active stocks
        # NOTE: We process ALL stocks, even those without trailing_pe, because:
        # - Some companies are unprofitable (no earnings, no PE)
        # - We still have other valuation metrics (P/B, P/S, EV, etc.) for these stocks
        # - Removed WHERE km.trailing_pe > 0 filter that was excluding ~1,829 stocks
        cursor.execute("""
            SELECT DISTINCT ss.symbol
            FROM stock_symbols ss
            WHERE (ss.etf IS NULL OR ss.etf != 'Y')
              AND ss.symbol IS NOT NULL
            ORDER BY ss.symbol
        """)

        tickers = [row[0] for row in cursor.fetchall()]
        logging.info(f"Processing {len(tickers)} stocks...")

        success_count = 0
        failed_count = 0

        # PHASE 1: Calculate and store value metrics
        logging.info("\n[Phase 1/2] Calculating and storing value metrics...")
        for ticker in tickers:
            try:
                value_data = calculate_value_metrics_for_stock(
                    cursor, ticker, market_benchmarks, sector_benchmarks
                )

                if value_data:
                    store_value_metrics(cursor, value_data)
                    success_count += 1

                    if success_count % 10 == 0:
                        logging.info(f"  Processed {success_count}/{len(tickers)} stocks...")
                else:
                    failed_count += 1

            except Exception as e:
                import traceback
                logging.error(f"  Error processing {ticker}: {e}")
                if failed_count == 0:  # Print full traceback for first error only
                    logging.error(f"  Full traceback:\n{traceback.format_exc()}")
                failed_count += 1
                conn.rollback()  # Rollback to recover from transaction error

        conn.commit()
        logging.info(f"  Phase 1 complete: {success_count} stocks processed, {failed_count} failed")

        # PHASE 2: Calculate percentile ranks for all stocks
        logging.info("\n[Phase 2/2] Calculating percentile ranks...")
        percentile_ranks = calculate_percentile_ranks(cursor)

        if percentile_ranks:
            percentile_updated = 0
            for ticker in tickers:
                if ticker in percentile_ranks:
                    try:
                        # Fetch current value_inputs
                        cursor.execute(
                            "SELECT value_inputs FROM stock_scores WHERE symbol = %s",
                            (ticker,)
                        )
                        row = cursor.fetchone()
                        if row and row[0]:
                            value_inputs = row[0]
                            # Handle both dict (from JSONB) and string (from JSON) types
                            if isinstance(value_inputs, str):
                                value_inputs = json.loads(value_inputs)

                            # Merge percentile ranks
                            value_inputs.update({
                                "pe_percentile_rank": percentile_ranks[ticker].get("pe_percentile"),
                                "pb_percentile_rank": percentile_ranks[ticker].get("pb_percentile"),
                                "ps_percentile_rank": percentile_ranks[ticker].get("ps_percentile"),
                                "ev_percentile_rank": percentile_ranks[ticker].get("ev_percentile"),
                                "peg_percentile_rank": percentile_ranks[ticker].get("peg_percentile"),
                                "fcf_yield_percentile_rank": percentile_ranks[ticker].get("fcf_yield_percentile"),
                                "dividend_yield_percentile_rank": percentile_ranks[ticker].get("dividend_yield_percentile"),
                            })
                            cursor.execute(
                                "UPDATE stock_scores SET value_inputs = %s::jsonb WHERE symbol = %s",
                                (json.dumps(value_inputs), ticker)
                            )
                            percentile_updated += 1

                            if percentile_updated % 20 == 0:
                                logging.info(f"  Updated {percentile_updated} stocks with percentile ranks...")
                    except Exception as e:
                        logging.error(f"  Error updating percentile for {ticker}: {e}")
                        conn.rollback()

            conn.commit()
            logging.info(f"  Phase 2 complete: {percentile_updated} stocks updated with percentile ranks")

        # Update last_updated
        cursor.execute("""
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, NOW())
            ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run
        """, (SCRIPT_NAME,))
        conn.commit()

        logging.info("=" * 80)
        logging.info(f"✅ Value Metrics Loader Complete!")
        logging.info(f"   Phase 1 - Metrics: {success_count} success, {failed_count} failed")
        logging.info(f"   Phase 2 - Percentile Ranks: {len(percentile_ranks)} stocks")
        logging.info("=" * 80)

    except Exception as e:
        logging.error(f"Fatal error: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
