#!/usr/bin/env python3
"""
Value Metrics Calculator
Calculates raw value input metrics (not scores) for use in loadstockscores.py

Metrics Calculated:
1. Valuation Multiples: P/E (forward/trailing), P/B, P/S, EV/EBITDA
2. Dividend Yield: Annual dividend as % of stock price
3. Benchmarks: Market and sector medians for comparison
4. FCF Yield: Free cash flow / market cap
5. PEG Ratio: P/E / earnings growth rate
6. DCF Intrinsic Value: Discounted cash flow valuation
7. DCF Discount: Percentage difference from intrinsic value

Note: Scoring logic is in loadstockscores.py - this only calculates inputs

Updated: 2025-10-12 - Added Dividend Yield and P/S metrics
"""

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
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.trailing_pe) as market_pe_median,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.price_to_book) as market_pb_median,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.ev_to_ebitda) as market_ev_ebitda_median,
            COUNT(*) as stock_count
        FROM key_metrics km
        LEFT JOIN stock_symbols ss ON km.ticker = ss.symbol
        WHERE km.trailing_pe > 0
          AND km.trailing_pe < 100
          AND km.price_to_book > 0
          AND km.ev_to_ebitda > 0
          AND (ss.etf IS NULL OR ss.etf != 'Y')
    """)

    row = cursor.fetchone()
    benchmarks = {
        "pe_median": float(row[0]) if row[0] else 18.0,
        "pb_median": float(row[1]) if row[1] else 2.5,
        "ev_ebitda_median": float(row[2]) if row[2] else 12.0,
        "stock_count": int(row[3]) if row[3] else 0,
    }

    logging.info(f"  Market PE Median: {benchmarks['pe_median']:.2f}")
    logging.info(f"  Market PB Median: {benchmarks['pb_median']:.2f}")
    logging.info(f"  Market EV/EBITDA Median: {benchmarks['ev_ebitda_median']:.2f}")
    logging.info(f"  Stocks in Market: {benchmarks['stock_count']}")

    return benchmarks


def get_sector_benchmarks(cursor):
    """Get sector-level median valuation multiples"""
    logging.info("Loading sector benchmarks...")

    cursor.execute("""
        SELECT sector, pe_ratio, price_to_book, ev_to_ebitda, stock_count
        FROM sector_benchmarks
        WHERE sector != 'MARKET'
    """)

    sector_data = {}
    for row in cursor.fetchall():
        sector_data[row[0]] = {
            "pe_median": float(row[1]) if row[1] else None,
            "pb_median": float(row[2]) if row[2] else None,
            "ev_ebitda_median": float(row[3]) if row[3] else None,
            "stock_count": int(row[4]) if row[4] else 0,
        }

    logging.info(f"  Loaded benchmarks for {len(sector_data)} sectors")
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
    """
    if not (free_cashflow and shares_outstanding and free_cashflow > 0 and shares_outstanding > 0):
        return None

    # Cost of equity (CAPM): risk_free_rate + beta * market_risk_premium
    risk_free_rate = 0.045  # 4.5%
    market_risk_premium = 0.065  # 6.5%
    beta = 1.0  # Default market beta
    cost_of_equity = risk_free_rate + beta * market_risk_premium

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
            km.implied_shares_outstanding,
            pd.close as current_price,
            km.dividend_yield,
            km.price_to_sales_ttm
        FROM key_metrics km
        LEFT JOIN company_profile cp ON km.ticker = cp.ticker
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

    if not pe or pe <= 0:
        logging.debug(f"  {ticker}: Skipping (no valid P/E)")
        return None

    # Get sector benchmarks
    sector_bench = sector_benchmarks.get(sector, {})
    sector_pe = sector_bench.get("pe_median", market_benchmarks["pe_median"])
    sector_pb = sector_bench.get("pb_median", market_benchmarks["pb_median"])
    sector_ev = sector_bench.get("ev_ebitda_median", market_benchmarks["ev_ebitda_median"])

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
    ev_relative = None
    if pe_market_relative and pe_sector_relative:
        pe_relative = (pe_market_relative * 0.7) + (pe_sector_relative * 0.3)
    elif pe_market_relative:
        pe_relative = pe_market_relative

    if pb_market_relative and pb_sector_relative:
        pb_relative = (pb_market_relative * 0.7) + (pb_sector_relative * 0.3)
    elif pb_market_relative:
        pb_relative = pb_market_relative

    if ev_market_relative and ev_sector_relative:
        ev_relative = (ev_market_relative * 0.7) + (ev_sector_relative * 0.3)
    elif ev_market_relative:
        ev_relative = ev_market_relative

    # Calculate other metrics
    fcf_yield = calculate_fcf_yield(market_cap, fcf) if market_cap and fcf else None
    peg_calc = calculate_peg_ratio(pe, growth_pct) if pe and growth_pct else peg
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
        "stock_ev_ebitda": float(ev_ebitda) if ev_ebitda else None,
        "stock_ps": float(price_to_sales) if price_to_sales else None,
        "dividend_yield": float(dividend_yield) if dividend_yield else None,
        # Benchmarks
        "market_pe": market_benchmarks["pe_median"],
        "market_pb": market_benchmarks["pb_median"],
        "market_ev_ebitda": market_benchmarks["ev_ebitda_median"],
        "sector_pe": sector_pe,
        "sector_pb": sector_pb,
        "sector_ev_ebitda": sector_ev,
        # Relative ratios (for scoring)
        "pe_relative": round(pe_relative, 4) if pe_relative else None,
        "pb_relative": round(pb_relative, 4) if pb_relative else None,
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


def store_value_metrics(cursor, value_data: Dict):
    """Store value input metrics in stock_scores table"""

    # Sanitize data to handle Infinity/NaN before JSON serialization
    value_inputs_clean = sanitize_for_json({
        # Valuation multiples
        "stock_pe": value_data["stock_pe"],
        "pe_type": value_data["pe_type"],
        "forward_pe": value_data["forward_pe"],
        "trailing_pe": value_data["trailing_pe"],
        "stock_pb": value_data["stock_pb"],
        "stock_ev_ebitda": value_data["stock_ev_ebitda"],
        "stock_ps": value_data["stock_ps"],
        "dividend_yield": value_data["dividend_yield"],
        # Benchmarks
        "market_pe": value_data["market_pe"],
        "market_pb": value_data["market_pb"],
        "market_ev_ebitda": value_data["market_ev_ebitda"],
        "sector_pe": value_data["sector_pe"],
        "sector_pb": value_data["sector_pb"],
        "sector_ev_ebitda": value_data["sector_ev_ebitda"],
        # Relative ratios
        "pe_relative": value_data["pe_relative"],
        "pb_relative": value_data["pb_relative"],
        "ev_relative": value_data["ev_relative"],
        # Calculated metrics
        "fcf_yield": value_data["fcf_yield"],
        "peg_ratio": value_data["peg_ratio"],
        "dcf_intrinsic_value": value_data["dcf_intrinsic_value"],
        "dcf_discount_pct": value_data["dcf_discount_pct"],
        "current_price": value_data["current_price"],
        "earnings_growth_pct": value_data["earnings_growth_pct"],
    })

    cursor.execute("""
        UPDATE stock_scores
        SET value_inputs = %s::jsonb
        WHERE symbol = %s
    """, (
        json.dumps(value_inputs_clean),
        value_data["ticker"],
    ))


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
        # Calculate market benchmarks
        market_benchmarks = calculate_market_benchmarks(cursor)

        # Get sector benchmarks
        sector_benchmarks = get_sector_benchmarks(cursor)

        # Get all active stocks
        cursor.execute("""
            SELECT DISTINCT km.ticker
            FROM key_metrics km
            LEFT JOIN stock_symbols ss ON km.ticker = ss.symbol
            WHERE km.trailing_pe > 0
              AND (ss.etf IS NULL OR ss.etf != 'Y')
            ORDER BY km.ticker
            LIMIT 100
        """)

        tickers = [row[0] for row in cursor.fetchall()]
        logging.info(f"Processing {len(tickers)} stocks...")

        success_count = 0
        failed_count = 0

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
        logging.info(f"   Success: {success_count}")
        logging.info(f"   Failed: {failed_count}")
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
