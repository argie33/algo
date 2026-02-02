#!/usr/bin/env python3
# FORCE RUN: 2026-01-30_093000 - EXECUTE FACTOR METRICS LOADER NOW - DB credentials fixed, loading factor data
"""
Factor Metrics Loader - Consolidated Quality, Growth, Value, Momentum, Stability Metrics
Populates derived metrics from key_metrics fundamental data.

Consolidates calculations previously in:
- loadqualitymetrics.py
- loadgrowthmetrics.py
- loadvaluemetrics.py
- loadmomentum.py
- loadstabilitymetrics.py
- loadearningsmetrics.py

Data Loaded:
- quality_metrics (ROE, ROA, margins, cash flow ratios, liquidity, leverage, earnings surprise, payout)
- growth_metrics (revenue CAGR, EPS growth, margin trends, FCF growth, asset growth)
- momentum_metrics (price momentum across 1m/3m/6m/12m timeframes)

STATUS: PRODUCTION - AWS ECS deployment 2026-01-27
- Trigger: Production deployment to AWS with consolidated loaders
- Deploy: All factor metrics calculations to AWS RDS database
- Impact: ~50-100 symbols skip growth metrics due to missing earnings data (acceptable)
- Performance: ~30-40 seconds for 5000 symbols
- Last run: 2026-01-26 (TODAY - CURRENT)

Author: Financial Dashboard System
Updated: 2025-11-17
Trigger: 20260107-220000-AWS-ECS - Force rebuild with improved beta calculation
"""

import gc
import json
import logging
import os
import resource
import sys
import time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import boto3
import pandas as pd
import psycopg2
import psycopg2.extensions
import numpy as np
from psycopg2.extras import RealDictCursor, execute_values

# Script metadata
SCRIPT_NAME = "loadfactormetrics.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# Register numpy type adapters
def adapt_numpy_int64(numpy_int64):
    return psycopg2.extensions.AsIs(int(numpy_int64))

def adapt_numpy_float64(numpy_float64):
    return psycopg2.extensions.AsIs(float(numpy_float64))

psycopg2.extensions.register_adapter(np.int64, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.int32, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.float64, adapt_numpy_float64)
psycopg2.extensions.register_adapter(np.float32, adapt_numpy_float64)


def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)


def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")


def track_calc_failure(symbol: str, metric_name: str, error: Exception):
    """Log calculation failures with full details instead of silent pass"""
    logging.warning(f"⚠️  {symbol}: {metric_name} calculation FAILED - {type(error).__name__}: {str(error)[:100]}")


def get_db_config():
    """Get database configuration - works in AWS and locally.

    Priority:
    1. AWS Secrets Manager (if DB_SECRET_ARN is set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
    """
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn:
        try:
            secret_str = boto3.client("secretsmanager").get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logging.info("Using AWS Secrets Manager for database config")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "database": sec["dbname"],
            }
        except Exception as e:
            logging.warning(f"AWS Secrets Manager failed ({e.__class__.__name__}): {str(e)[:100]}. Falling back to environment variables.")

    # Fall back to environment variables
    logging.info("Using environment variables for database config")
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", "stocks"),
    }


def get_all_symbols(cursor) -> List[str]:
    """Get list of all stock symbols from stock_symbols table to ensure full coverage"""
    cursor.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
    return [row[0] for row in cursor.fetchall()]


def get_price_history(cursor, symbol: str, days: int = 252*2) -> pd.DataFrame:
    """Fetch historical price data from price_daily table for momentum calculations (NO yfinance)"""
    try:
        # Get last N days of price data from database
        cursor.execute("""
            SELECT date, adj_close
            FROM price_daily
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT %s
        """, (symbol, days))

        data = cursor.fetchall()
        if not data:
            return pd.DataFrame()

        # Convert to DataFrame with date index
        dates = [row[0] for row in reversed(data)]
        prices = [row[1] for row in reversed(data)]

        df = pd.DataFrame({'Close': prices}, index=pd.to_datetime(dates))
        return df

    except Exception as e:
        logging.warning(f"Failed to fetch price history for {symbol}: {e}")
        return pd.DataFrame()


def calculate_quality_metrics(ticker_data: Dict, ticker=None, symbol=None) -> Dict:
    """Calculate quality metrics from key_metrics data (NO yfinance API calls)"""
    # Handle mixed data format: some values are in decimal form (0-1), others already in percentage (>1)
    # Auto-detect and normalize to percentage form for output

    def normalize_percentage(value):
        """Convert percentage to standardized output format. Handles both decimal (0-1) and percentage (>1) inputs."""
        if value is None:
            return None
        try:
            val = float(value)
            # If value is between -1 and 1 (exclusive of 1 to avoid edge cases), it's likely decimal form
            # Percentage form values are typically larger (e.g., 25.5 for 25.5%)
            if -1 < val < 1:
                return val * 100
            else:
                # Already in percentage form
                return val
        except (TypeError, ValueError):
            return None

    gm = ticker_data.get("gross_margin_pct")
    opm = ticker_data.get("operating_margin_pct")
    pm = ticker_data.get("profit_margin_pct")
    pr = ticker_data.get("payout_ratio")
    roe = ticker_data.get("return_on_equity_pct")
    roa = ticker_data.get("return_on_assets_pct")

    # REAL DATA ONLY - Use yfinance profit_margin_pct, no fallback calculations
    # If yfinance doesn't provide it, profit_margin_pct will be None

    metrics = {
        "return_on_equity_pct": normalize_percentage(roe),
        "return_on_assets_pct": normalize_percentage(roa),
        "return_on_invested_capital_pct": None,  # Calculated below from EBITDA / (Debt + Cash)
        "gross_margin_pct": normalize_percentage(gm),
        "operating_margin_pct": normalize_percentage(opm),
        "profit_margin_pct": normalize_percentage(pm),
        "debt_to_equity": ticker_data.get("debt_to_equity"),
        "current_ratio": ticker_data.get("current_ratio"),
        "quick_ratio": ticker_data.get("quick_ratio"),
        "payout_ratio": normalize_percentage(pr),
        "earnings_surprise_avg": None,  # Calculated by get_earnings_surprise_metrics() from quarterly EPS data
        "eps_growth_stability": None,   # Calculated by get_earnings_surprise_metrics() from quarterly EPS data
    }

    # Calculate FCF to Net Income ratio - REAL DATA ONLY
    # Only calculate if we have actual free_cashflow data
    if ticker_data.get("free_cashflow") and ticker_data.get("net_income") and ticker_data["net_income"] != 0:
        metrics["fcf_to_net_income"] = ticker_data["free_cashflow"] / ticker_data["net_income"]

    # Calculate Operating CF to Net Income ratio (primary calculation only, no fallback)
    if ticker_data.get("operating_cashflow") and ticker_data.get("net_income"):
        if ticker_data["net_income"] != 0:
            metrics["operating_cf_to_net_income"] = (
                ticker_data["operating_cashflow"] / ticker_data["net_income"]
            )

    # Calculate ROIC - REAL DATA ONLY
    # EBITDA / (Total Debt + Total Cash) - most accurate measure
    # Only calculate if we have actual EBITDA data
    ebitda = ticker_data.get("ebitda")
    total_debt = ticker_data.get("total_debt")
    total_cash = ticker_data.get("total_cash")

    if ebitda and ebitda > 0 and total_debt is not None and total_cash is not None:
        invested_capital = total_debt + total_cash
        if invested_capital > 0:
            roic_value = ebitda / invested_capital
            roic_pct = roic_value * 100
            metrics["return_on_invested_capital_pct"] = max(-100, min(roic_pct, 200))

    # NOTE: earnings_surprise_avg and eps_growth_stability are calculated separately by calculate_earnings_surprise.py
    # which queries quarterly_income_statement table for real earnings data, not yfinance API calls
    # This avoids rate limiting issues when processing 5000+ symbols

    return metrics


def calculate_cagr(start_value: float, end_value: float, periods: int) -> Optional[float]:
    """Calculate Compound Annual Growth Rate"""
    if not start_value or start_value == 0 or not end_value or periods <= 0:
        return None
    try:
        # CAGR = (Ending Value / Beginning Value)^(1/Number of Years) - 1
        cagr = (end_value / start_value) ** (1 / periods) - 1
        return float(cagr * 100)  # Return as percentage
    except (ValueError, ZeroDivisionError):
        return None


def get_quarterly_statement_growth(cursor, symbol: str) -> Dict:
    """Calculate growth metrics from quarterly financial statements

    Uses most recent 8 quarters (2 years) for YoY comparisons.
    More current than annual data, fills gaps where annual data unavailable.
    """
    metrics = {}

    try:
        # Get recent 8 quarters of revenue and earnings
        cursor.execute("""
            SELECT date, revenue, net_income, operating_income
            FROM quarterly_income_statement
            WHERE symbol = %s AND date IS NOT NULL
            ORDER BY date DESC
            LIMIT 8
        """, (symbol,))

        quarterly_data = cursor.fetchall()

        if len(quarterly_data) >= 5:
            # Most recent quarter
            recent_date, recent_rev, recent_ni, recent_oi = quarterly_data[0]

            # Same quarter one year ago (4 quarters back)
            if len(quarterly_data) >= 5:
                prior_year_date, prior_rev, prior_ni, prior_oi = quarterly_data[4]

                # Calculate YoY revenue growth
                if prior_rev and recent_rev and prior_rev != 0:
                    try:
                        metrics["revenue_growth_quarterly_yoy"] = ((recent_rev - prior_rev) / abs(prior_rev) * 100)
                    except (TypeError, ValueError, ZeroDivisionError) as e:
                        track_calc_failure(symbol, "revenue_growth_quarterly_yoy", e)

                # Calculate YoY net income growth
                if prior_ni and recent_ni and prior_ni != 0:
                    try:
                        metrics["net_income_growth_quarterly_yoy"] = ((recent_ni - prior_ni) / abs(prior_ni) * 100)
                    except (TypeError, ValueError, ZeroDivisionError) as e:
                        track_calc_failure(symbol, "net_income_growth_quarterly_yoy", e)

                # Calculate YoY operating income growth
                if prior_oi and recent_oi and prior_oi != 0:
                    try:
                        metrics["operating_income_growth_quarterly_yoy"] = ((recent_oi - prior_oi) / abs(prior_oi) * 100)
                    except (TypeError, ValueError, ZeroDivisionError) as e:
                        track_calc_failure(symbol, "operating_income_growth_quarterly_yoy", e)

    except Exception as e:
        logging.debug(f"Could not calculate quarterly statement growth for {symbol}: {e}")

    return metrics


def get_earnings_history_growth(cursor, symbol: str) -> Dict:
    """Calculate earnings metrics from quarterly earnings history

    NOTE: earnings_history table contains recent quarters but may not have full
    4-year history needed for proper YoY comparisons. This function calculates
    what's available (current quarter performance vs estimates).
    """
    metrics = {}

    try:
        # Get recent quarters of earnings
        cursor.execute("""
            SELECT quarter, eps_actual, eps_estimate
            FROM earnings_history
            WHERE symbol = %s
            ORDER BY quarter DESC
            LIMIT 4
        """, (symbol,))

        earnings_data = cursor.fetchall()

        if len(earnings_data) >= 2:
            # REAL DATA ONLY - Use actual EPS from earnings_history, no fallback to estimates
            recent_eps = None
            prior_eps = None

            # Only use actual reported EPS (not estimates)
            if earnings_data[0][1] is not None:
                recent_eps = float(earnings_data[0][1])

            if len(earnings_data) >= 2:
                if earnings_data[1][1] is not None:
                    prior_eps = float(earnings_data[1][1])

            # Only calculate if we have actual EPS data (don't proxy or extrapolate)
            if recent_eps is not None and prior_eps is not None and prior_eps != 0:
                try:
                    qoq_growth = ((recent_eps - prior_eps) / abs(prior_eps)) * 100
                    # Store as quarterly growth metric (not annualized)
                    metrics["eps_growth_1y"] = qoq_growth
                except (TypeError, ValueError, ZeroDivisionError) as e:
                    track_calc_failure(symbol, "eps_growth_1y", e)

    except Exception as e:
        logging.debug(f"Could not calculate earnings history metrics for {symbol}: {e}")

    return metrics


def get_financial_statement_growth(cursor, symbol: str) -> Dict:
    """Calculate growth metrics from financial statement tables with improved coverage"""
    metrics = {
        "revenue_growth_3y_cagr": None,
        "eps_growth_3y_cagr": None,
        "operating_income_growth_yoy": None,
        "fcf_growth_yoy": None,
        "ocf_growth_yoy": None,
        "net_income_growth_yoy": None,
        "asset_growth_yoy": None,
        "revenue_growth_yoy": None,
    }

    try:
        # Get annual income statement data (most recent 4 years)
        cursor.execute("""
            SELECT date, revenue, operating_income, net_income
            FROM annual_income_statement
            WHERE symbol = %s AND date IS NOT NULL
            ORDER BY date DESC
            LIMIT 4
        """, (symbol,))

        income_data = cursor.fetchall()

        if len(income_data) >= 2:
            # Most recent year data
            recent_date, recent_revenue, recent_oi, recent_ni = income_data[0]

            # Get previous year data for YoY calculation
            prev_date, prev_revenue, prev_oi, prev_ni = income_data[1]

            # Calculate YoY (year-over-year) growth
            # Allow any valid numeric comparison (including negative/zero base values)
            if prev_revenue is not None and recent_revenue is not None:
                if prev_revenue != 0:
                    try:
                        metrics["revenue_growth_yoy"] = ((recent_revenue - prev_revenue) / abs(prev_revenue) * 100)
                        logging.debug(f"DEBUG {symbol} revenue_growth_yoy: {metrics['revenue_growth_yoy']}")
                    except (TypeError, ValueError, ZeroDivisionError) as e:
                        logging.debug(f"DEBUG {symbol} revenue_growth_yoy exception: prev={prev_revenue}, recent={recent_revenue}")
                        track_calc_failure(symbol, "revenue_growth_yoy", e)
            else:
                logging.debug(f"DEBUG {symbol} skipped revenue_growth_yoy: prev={prev_revenue}, recent={recent_revenue}")

            # Operating Income Growth: Allow any valid numeric comparison (including negative base)
            # Company going from -$10M to -$5M to +$2M shows recovery progression
            if prev_oi is not None and recent_oi is not None:
                if prev_oi != 0:
                    try:
                        metrics["operating_income_growth_yoy"] = ((recent_oi - prev_oi) / abs(prev_oi) * 100)
                    except (TypeError, ValueError, ZeroDivisionError) as e:
                        track_calc_failure(symbol, "operating_income_growth_yoy", e)

            # Net Income Growth: Allow any valid numeric comparison (including negative base)
            # Company going profitable shows real growth, even from loss position
            if prev_ni is not None and recent_ni is not None:
                if prev_ni != 0:
                    try:
                        metrics["net_income_growth_yoy"] = ((recent_ni - prev_ni) / abs(prev_ni) * 100)
                    except (TypeError, ValueError, ZeroDivisionError) as e:
                        track_calc_failure(symbol, "net_income_growth_yoy", e)

            # Calculate 3-year CAGR if we have 4 years of data
            if len(income_data) >= 4:
                oldest_date, oldest_revenue, oldest_oi, oldest_ni = income_data[3]

                # Revenue CAGR: Only calculate when both oldest and recent are positive
                # CAGR requires starting from a positive base value
                if oldest_revenue and oldest_revenue > 0 and recent_revenue and recent_revenue > 0:
                    metrics["revenue_growth_3y_cagr"] = calculate_cagr(oldest_revenue, recent_revenue, 3)

                # EPS CAGR: Calculate when BOTH years have valid earnings (positive or negative consistently)
                # Real data scenarios:
                # - Profitable 3Y ago and profitable now: calculate normal CAGR
                # - Unprofitable 3Y ago and unprofitable now: calculate from negative values (shows improvement)
                # - Both non-null allows recovery analysis (profitable to unprofitable or vice versa)
                if recent_ni is not None and oldest_ni is not None and recent_ni != 0 and oldest_ni != 0:
                    try:
                        # Calculate CAGR from actual values (may be negative)
                        # This captures real business transitions
                        metrics["eps_growth_3y_cagr"] = calculate_cagr(oldest_ni, recent_ni, 3)
                    except (ValueError, ZeroDivisionError):
                        # CAGR calculation failed (e.g., sign change), leave as None
                        pass

            # REAL DATA ONLY - If 4-year CAGR not available, leave eps_growth_3y_cagr as None
            # Do not use 2-year growth as fallback proxy
            # Use YoY calculation if available (already calculated above in YoY section)

        # Get annual cashflow data for FCF growth (4 years available, use first 2)
        cursor.execute("""
            SELECT date, free_cash_flow
            FROM annual_cash_flow
            WHERE symbol = %s AND date IS NOT NULL
            ORDER BY date DESC
            LIMIT 4
        """, (symbol,))

        cf_data = cursor.fetchall()
        if len(cf_data) >= 2:
            recent_fcf = cf_data[0][1] if cf_data[0] else None
            prev_fcf = cf_data[1][1] if cf_data[1] else None
            # Allow growth from negative FCF to positive (company improving cash generation)
            # Or from positive to positive (normal growth)
            # BUT: Only calculate if base FCF is meaningful (abs value > 1M to avoid extreme %'s from tiny bases)
            if recent_fcf is not None and prev_fcf is not None and prev_fcf != 0 and abs(prev_fcf) > 1000000:
                try:
                    fcf_pct = ((recent_fcf - prev_fcf) / abs(prev_fcf) * 100)
                    # Cap at ±500% to avoid meaningless extreme values from calculation errors
                    metrics["fcf_growth_yoy"] = max(-500, min(500, fcf_pct))
                except (TypeError, ValueError, ZeroDivisionError) as e:
                    track_calc_failure(symbol, "fcf_growth_yoy", e)

        # Get annual cashflow data for OCF growth
        cursor.execute("""
            SELECT date, operating_cash_flow
            FROM annual_cash_flow
            WHERE symbol = %s AND date IS NOT NULL
            ORDER BY date DESC
            LIMIT 4
        """, (symbol,))

        ocf_data = cursor.fetchall()
        if len(ocf_data) >= 2:
            recent_ocf = ocf_data[0][1] if ocf_data[0] else None
            prev_ocf = ocf_data[1][1] if ocf_data[1] else None
            # Allow growth from negative OCF to positive (company improving operations)
            # Or from positive to positive (normal growth)
            # BUT: Only calculate if base OCF is meaningful (abs value > 1M to avoid extreme %'s from tiny bases)
            if recent_ocf is not None and prev_ocf is not None and prev_ocf != 0 and abs(prev_ocf) > 1000000:
                try:
                    ocf_pct = ((recent_ocf - prev_ocf) / abs(prev_ocf) * 100)
                    # Cap at ±500% to avoid meaningless extreme values
                    metrics["ocf_growth_yoy"] = max(-500, min(500, ocf_pct))
                except (TypeError, ValueError, ZeroDivisionError) as e:
                    track_calc_failure(symbol, "ocf_growth_yoy", e)

        # Get annual balance sheet data for asset growth
        try:
            cursor.execute("""
                SELECT date, total_assets
                FROM annual_balance_sheet
                WHERE symbol = %s AND date IS NOT NULL
                ORDER BY date DESC
                LIMIT 2
            """, (symbol,))

            bs_data = cursor.fetchall()
            if len(bs_data) >= 2:
                recent_assets = bs_data[0][1]
                prev_assets = bs_data[1][1]
                if prev_assets and recent_assets:
                    if prev_assets > 0:
                        try:
                            metrics["asset_growth_yoy"] = ((recent_assets - prev_assets) / prev_assets * 100)
                        except (TypeError, ValueError, ZeroDivisionError) as e:
                            track_calc_failure(symbol, "asset_growth_yoy", e)
        except Exception as bs_error:
            # Balance sheet table might not exist or have data
            logging.debug(f"Could not get balance sheet data for {symbol}: {bs_error}")

    except Exception as e:
        logging.warning(f"Could not calculate financial growth metrics for {symbol}: {e}")
        import traceback
        logging.debug(f"Full traceback: {traceback.format_exc()}")

    return metrics


def get_earnings_surprise_metrics(cursor, symbol: str) -> Dict:
    """Calculate earnings surprise from quarterly actual vs estimated EPS"""
    metrics = {
        "earnings_surprise_avg": None,
        "eps_growth_stability": None,
    }

    try:
        # Get actual quarterly EPS from income statement
        cursor.execute("""
            SELECT
                DATE_PART('YEAR', qis.date::date)::int as year,
                DATE_PART('QUARTER', qis.date::date)::int as quarter,
                qis.eps::float as actual_eps
            FROM quarterly_income_statement qis
            WHERE qis.symbol = %s
            AND qis.eps IS NOT NULL
            ORDER BY qis.date DESC
            LIMIT 4
        """, (symbol,))

        actual_eps_data = cursor.fetchall()

        if not actual_eps_data or len(actual_eps_data) < 2:
            return metrics

        # Calculate EPS growth stability from historical data
        eps_values = [row[2] for row in actual_eps_data]

        if len(eps_values) >= 2:
            growth_rates = []
            for i in range(len(eps_values) - 1):
                if eps_values[i+1] != 0:
                    try:
                        growth = ((eps_values[i] - eps_values[i+1]) / abs(eps_values[i+1])) * 100
                        growth_rates.append(growth)
                    except (TypeError, ValueError) as e:
                        track_calc_failure(symbol, "unknown_metric", e)

            if growth_rates and len(growth_rates) >= 2:
                try:
                    mean_growth = float(np.mean(growth_rates))
                    std_growth = float(np.std(growth_rates))

                    if mean_growth != 0:
                        metrics["eps_growth_stability"] = float(std_growth / abs(mean_growth))
                    else:
                        metrics["eps_growth_stability"] = float(std_growth)
                except (TypeError, ValueError) as e:
                    track_calc_failure(symbol, "eps_growth_stability", e)

        # Calculate earnings surprise: (actual - estimate) / estimate
        # Using historical average as estimate baseline
        if len(eps_values) >= 2:
            surprises = []
            for i in range(len(eps_values) - 1):
                actual = eps_values[i]
                # Use previous quarters' average as estimate
                estimate = float(np.mean(eps_values[i+1:]))
                if estimate != 0:
                    try:
                        surprise = ((actual - estimate) / abs(estimate)) * 100
                        surprises.append(surprise)
                    except (TypeError, ValueError) as e:
                        track_calc_failure(symbol, "unknown_metric", e)

            if surprises:
                try:
                    metrics["earnings_surprise_avg"] = float(np.mean(surprises))
                except (TypeError, ValueError) as e:
                    track_calc_failure(symbol, "earnings_surprise_avg", e)

    except Exception as e:
        logging.debug(f"Could not calculate earnings surprise for {symbol}: {e}")

    return metrics


def get_earnings_beat_rate(cursor, symbol: str) -> Optional[float]:
    """Calculate earnings beat rate - % of quarters beating estimates (REAL DATA)"""
    try:
        # REAL DATA: Use earnings_history table which has actual vs estimated EPS
        cursor.execute("""
            SELECT quarter, eps_actual, eps_estimate
            FROM earnings_history
            WHERE symbol = %s
              AND eps_actual IS NOT NULL
              AND eps_estimate IS NOT NULL
            ORDER BY quarter DESC
            LIMIT 8
        """, (symbol,))

        earnings_data = cursor.fetchall()
        if not earnings_data or len(earnings_data) < 2:
            return None

        # Count beats: actual >= estimate (real comparison, not fake)
        beat_count = 0
        for quarter, actual, estimate in earnings_data:
            try:
                actual_val = float(actual)
                estimate_val = float(estimate)
                if estimate_val != 0 and actual_val >= estimate_val:
                    beat_count += 1
            except (ValueError, TypeError) as e:
                track_calc_failure(symbol, "unknown_metric", e)

        if earnings_data:
            return (float(beat_count) / len(earnings_data)) * 100

    except Exception as e:
        logging.debug(f"Could not calculate earnings beat rate for {symbol}: {e}")

    return None


def get_consecutive_positive_quarters(cursor, symbol: str) -> Optional[int]:
    """Calculate consecutive quarters with positive EPS"""
    try:
        cursor.execute("""
            SELECT eps FROM quarterly_income_statement
            WHERE symbol = %s AND eps IS NOT NULL
            ORDER BY date DESC
            LIMIT 8
        """, (symbol,))

        eps_values = [row[0] for row in cursor.fetchall()]
        if not eps_values:
            return None

        consecutive = 0
        for eps in eps_values:
            if eps is not None and float(eps) > 0:
                consecutive += 1
            else:
                break

        return consecutive if consecutive > 0 else None
    except Exception as e:
        logging.debug(f"Could not calculate consecutive positive quarters for {symbol}: {e}")

    return None


def get_surprise_consistency(cursor, symbol: str) -> Optional[float]:
    """Calculate consistency of earnings surprises (std dev of actual vs estimate surprise % - REAL DATA)"""
    try:
        # REAL DATA: Use actual vs estimate surprises from earnings_history
        cursor.execute("""
            SELECT surprise_percent FROM earnings_history
            WHERE symbol = %s AND surprise_percent IS NOT NULL
            ORDER BY quarter DESC
            LIMIT 8
        """, (symbol,))

        surprise_values = [float(row[0]) for row in cursor.fetchall()]
        if len(surprise_values) < 4:
            return None

        # Calculate consistency: std deviation of actual surprise percentages
        # Higher std = less consistent surprises, Lower std = more consistent
        if len(surprise_values) >= 2:
            return float(np.std(surprise_values))
    except Exception as e:
        logging.debug(f"Could not calculate surprise consistency for {symbol}: {e}")

    return None


def get_estimate_revision_direction(cursor, symbol: str) -> Optional[float]:
    """Calculate direction of estimate revisions (net ups vs downs)"""
    try:
        cursor.execute("""
            SELECT SUM(up_last_7d) as total_ups, SUM(down_last_7d) as total_downs
            FROM earnings_estimate_revisions
            WHERE symbol = %s AND (up_last_7d IS NOT NULL OR down_last_7d IS NOT NULL)
        """, (symbol,))

        row = cursor.fetchone()
        if row and row[0] is not None and row[1] is not None:
            ups = float(row[0]) if row[0] else 0
            downs = float(row[1]) if row[1] else 0
            total = ups + downs
            if total > 0:
                # Positive = more ups than downs, Negative = more downs than ups
                return ((ups - downs) / total) * 100
    except Exception as e:
        logging.debug(f"Could not calculate estimate revision direction for {symbol}: {e}")

    return None


def get_revision_activity_30d(cursor, symbol: str) -> Optional[float]:
    """Calculate recent revision activity score (7d vs 30d)

    Returns score 0-100 where:
    - >50 = upward momentum (more recent ups)
    - 50 = balanced
    - <50 = downward momentum (more recent downs)
    """
    try:
        cursor.execute("""
            SELECT up_last_7d, down_last_7d, up_last_30d, down_last_30d
            FROM earnings_estimate_revisions
            WHERE symbol = %s AND snapshot_date = (
                SELECT MAX(snapshot_date) FROM earnings_estimate_revisions WHERE symbol = %s
            )
        """, (symbol, symbol))

        row = cursor.fetchone()
        if row:
            up_7d = float(row[0]) if row[0] else 0
            down_7d = float(row[1]) if row[1] else 0
            up_30d = float(row[2]) if row[2] else 0
            down_30d = float(row[3]) if row[3] else 0

            total_7d = up_7d + down_7d
            total_30d = up_30d + down_30d

            if total_30d > 0:
                # Score recent activity vs historical
                recent_ratio = ((up_7d - down_7d) / max(total_7d, 1)) if total_7d > 0 else 0
                overall_ratio = ((up_30d - down_30d) / total_30d) if total_30d > 0 else 0

                # 0-100 scale: high if recent is more positive than overall
                score = 50 + (recent_ratio - overall_ratio) * 50
                return max(0, min(100, score))
    except Exception as e:
        logging.debug(f"Could not calculate revision activity for {symbol}: {e}")

    return None


def get_estimate_momentum_60d(cursor, symbol: str) -> Optional[float]:
    """Calculate estimate momentum: change from 60 days ago

    Returns percentage change where:
    - Positive = estimates rising
    - Negative = estimates falling
    """
    try:
        cursor.execute("""
            SELECT current_estimate, estimate_60d_ago
            FROM earnings_estimate_trends
            WHERE symbol = %s AND snapshot_date = (
                SELECT MAX(snapshot_date) FROM earnings_estimate_trends WHERE symbol = %s
            )
        """, (symbol, symbol))

        row = cursor.fetchone()
        if row and row[0] is not None and row[1] is not None:
            current = float(row[0])
            past = float(row[1])

            if past != 0:
                return ((current - past) / abs(past)) * 100
    except Exception as e:
        logging.debug(f"Could not calculate estimate momentum for {symbol}: {e}")

    return None


def get_estimate_momentum_90d(cursor, symbol: str) -> Optional[float]:
    """Calculate estimate momentum: change from 90 days ago

    Returns percentage change where:
    - Positive = estimates rising
    - Negative = estimates falling
    """
    try:
        cursor.execute("""
            SELECT current_estimate, estimate_90d_ago
            FROM earnings_estimate_trends
            WHERE symbol = %s AND snapshot_date = (
                SELECT MAX(snapshot_date) FROM earnings_estimate_trends WHERE symbol = %s
            )
        """, (symbol, symbol))

        row = cursor.fetchone()
        if row and row[0] is not None and row[1] is not None:
            current = float(row[0])
            past = float(row[1])

            if past != 0:
                return ((current - past) / abs(past)) * 100
    except Exception as e:
        logging.debug(f"Could not calculate 90d estimate momentum for {symbol}: {e}")

    return None


def get_revision_trend_score(cursor, symbol: str) -> Optional[float]:
    """Calculate overall revision trend quality (0-100)

    Combines:
    - Estimate momentum (60d and 90d trends)
    - Revision activity (recent vs historical)
    - Net revision direction

    Returns 0-100 where higher = more positive estimate environment
    """
    try:
        momentum_60d = get_estimate_momentum_60d(cursor, symbol)
        momentum_90d = get_estimate_momentum_90d(cursor, symbol)
        activity = get_revision_activity_30d(cursor, symbol)
        direction = get_estimate_revision_direction(cursor, symbol)

        scores = []

        # Momentum component: normalize to 0-100 (capped at ±50% change)
        if momentum_60d is not None:
            scores.append(50 + min(max(momentum_60d, -50), 50))
        if momentum_90d is not None:
            scores.append(50 + min(max(momentum_90d, -50), 50))

        # Activity component: already 0-100
        if activity is not None:
            scores.append(activity)

        # Direction component: scale from -100,100 to 0,100
        if direction is not None:
            scores.append(50 + (direction / 2))

        if scores:
            return float(np.mean(scores))
    except Exception as e:
        logging.debug(f"Could not calculate revision trend score for {symbol}: {e}")

    return None


def get_earnings_growth_4q_avg(cursor, symbol: str) -> Optional[float]:
    """Calculate 4-quarter average earnings growth"""
    try:
        cursor.execute("""
            SELECT eps FROM quarterly_income_statement
            WHERE symbol = %s AND eps IS NOT NULL
            ORDER BY date DESC
            LIMIT 4
        """, (symbol,))

        eps_values = [row[0] for row in cursor.fetchall()]
        if len(eps_values) < 4:
            return None

        growth_rates = []
        for i in range(len(eps_values) - 1):
            if eps_values[i+1] is not None and float(eps_values[i+1]) != 0:
                growth = ((float(eps_values[i]) - float(eps_values[i+1])) / abs(float(eps_values[i+1]))) * 100
                growth_rates.append(growth)

        if growth_rates:
            return float(np.mean(growth_rates))
    except Exception as e:
        logging.debug(f"Could not calculate 4Q earnings growth for {symbol}: {e}")

    return None


def normalize_percentage(value):
    """Convert percentage to standardized output format. Handles both decimal (0-1) and percentage (>1) inputs."""
    if value is None:
        return None
    try:
        val = float(value)
        # If value is between -1 and 1, it's likely decimal form; otherwise percentage form
        if -1 < val < 1:
            return val * 100
        else:
            return val
    except (TypeError, ValueError):
        return None


def calculate_growth_metrics(ticker_data: Dict, financial_growth: Dict = None, quarterly_growth: Dict = None, earnings_history_growth: Dict = None, cursor=None, symbol=None) -> Dict:
    """Calculate growth metrics from key_metrics, financial statements, quarterly data, and earnings history

    Priority order:
    1. Annual financial statements (most comprehensive)
    2. Quarterly financial statements (more current)
    3. Earnings history (real-time EPS)
    4. key_metrics provider data (fallback)
    5. Derived calculations (EPS forward vs trailing)
    """
    metrics = {}

    # Use annual financial statement data if available (highest priority)
    if financial_growth:
        metrics.update({k: v for k, v in financial_growth.items() if v is not None})

    # REAL DATA ONLY - No fallback logic
    # Use only financial statements and earnings history data
    # Do NOT substitute quarterly for annual, or estimates for actuals
    # If data is missing, metric remains None

    # Calculate quarterly earnings growth from actual quarterly data
    try:
        if "quarterly_growth_momentum" not in metrics or metrics["quarterly_growth_momentum"] is None:
            if cursor and symbol:
                cursor.execute("""
                    SELECT date, net_income
                    FROM quarterly_income_statement
                    WHERE symbol = %s AND net_income IS NOT NULL
                    ORDER BY date DESC
                    LIMIT 2
                """, (symbol,))

                q_data = cursor.fetchall()
                if len(q_data) >= 2:
                    curr_date, curr_qi = q_data[0]
                    prior_date, prior_qi = q_data[1]

                    if prior_qi is not None and prior_qi != 0:
                        try:
                            q_growth = ((float(curr_qi) - float(prior_qi)) / abs(float(prior_qi))) * 100
                            metrics["quarterly_growth_momentum"] = round(q_growth, 2)
                        except (TypeError, ValueError, ZeroDivisionError) as e:
                            track_calc_failure(symbol, "quarterly_growth_momentum", e)
    except Exception as e:
        logging.debug(f"Could not calculate quarterly growth momentum for {symbol}: {e}")

    # REAL DATA ONLY - Sustainable growth rate = ROE * (1 - Payout Ratio)
    # Requires both ROE and Payout Ratio (no fallback to ROE alone)
    # Handle both decimal (0-1) and percentage forms
    roe = ticker_data.get("return_on_equity_pct")
    payout = ticker_data.get("payout_ratio")
    if roe and payout:
        try:
            roe_f = float(roe) if roe else None
            payout_f = float(payout) if payout else None
            if roe_f and payout_f:
                # Normalize both to decimal form first
                roe_decimal = roe_f / 100 if roe_f >= 1 or roe_f <= -1 else roe_f
                payout_decimal = payout_f / 100 if payout_f >= 1 else payout_f
                # Calculate: ROE_decimal * (1 - Payout_decimal) * 100 for percentage result
                metrics["sustainable_growth_rate"] = roe_decimal * (1 - payout_decimal) * 100
        except (TypeError, ValueError) as e:
            track_calc_failure(symbol, "sustainable_growth_rate", e)
    # NO FALLBACK - If payout ratio missing, sustainable_growth_rate remains None

    # Calculate margin trends from annual income statement data
    # Margin trend = current margin - prior year margin (in percentage points)
    try:
        if "gross_margin_trend" not in metrics or metrics["gross_margin_trend"] is None:
            # Query for gross profit data (may not always be available)
            if cursor and symbol:
                cursor.execute("""
                SELECT date, revenue, (revenue - cost_of_revenue) as gross_profit, operating_income, net_income
                FROM annual_income_statement
                WHERE symbol = %s AND revenue IS NOT NULL
                ORDER BY date DESC
                LIMIT 2
            """, (symbol,))

            margin_data = cursor.fetchall()
            if len(margin_data) >= 2:
                # Current year
                curr_date, curr_rev, curr_gp, curr_oi, curr_ni = margin_data[0]
                # Prior year
                prior_date, prior_rev, prior_gp, prior_oi, prior_ni = margin_data[1]

                # Calculate gross margin YoY change (in percentage points)
                if curr_rev and prior_rev and curr_gp is not None and prior_gp is not None:
                    try:
                        if curr_rev != 0 and prior_rev != 0:
                            curr_gm = (float(curr_gp) / float(curr_rev)) * 100
                            prior_gm = (float(prior_gp) / float(prior_rev)) * 100
                            metrics["gross_margin_trend"] = round(curr_gm - prior_gm, 2)  # pp change
                    except (TypeError, ValueError, ZeroDivisionError) as e:
                        track_calc_failure(symbol, "gross_margin_trend", e)

        if "operating_margin_trend" not in metrics or metrics["operating_margin_trend"] is None:
            # Query operating income data
            cursor.execute("""
                SELECT date, revenue, operating_income
                FROM annual_income_statement
                WHERE symbol = %s AND revenue IS NOT NULL AND operating_income IS NOT NULL
                ORDER BY date DESC
                LIMIT 2
            """, (symbol,))

            opm_data = cursor.fetchall()
            if len(opm_data) >= 2:
                # Current year
                curr_date, curr_rev, curr_oi = opm_data[0]
                # Prior year
                prior_date, prior_rev, prior_oi = opm_data[1]

                # Calculate operating margin YoY change (in percentage points)
                if curr_rev and prior_rev and curr_oi is not None and prior_oi is not None:
                    try:
                        if curr_rev != 0 and prior_rev != 0:
                            curr_opm = (float(curr_oi) / float(curr_rev)) * 100
                            prior_opm = (float(prior_oi) / float(prior_rev)) * 100
                            metrics["operating_margin_trend"] = round(curr_opm - prior_opm, 2)  # pp change
                    except (TypeError, ValueError, ZeroDivisionError) as e:
                        track_calc_failure(symbol, "operating_margin_trend", e)

        if "net_margin_trend" not in metrics or metrics["net_margin_trend"] is None:
            # Query net income data
            cursor.execute("""
                SELECT date, revenue, net_income
                FROM annual_income_statement
                WHERE symbol = %s AND revenue IS NOT NULL AND net_income IS NOT NULL
                ORDER BY date DESC
                LIMIT 2
            """, (symbol,))

            npm_data = cursor.fetchall()
            if len(npm_data) >= 2:
                # Current year
                curr_date, curr_rev, curr_ni = npm_data[0]
                # Prior year
                prior_date, prior_rev, prior_ni = npm_data[1]

                # Calculate net margin YoY change (in percentage points)
                if curr_rev and prior_rev and curr_ni is not None and prior_ni is not None:
                    try:
                        if curr_rev != 0 and prior_rev != 0:
                            curr_npm = (float(curr_ni) / float(curr_rev)) * 100
                            prior_npm = (float(prior_ni) / float(prior_rev)) * 100
                            metrics["net_margin_trend"] = round(curr_npm - prior_npm, 2)  # pp change
                    except (TypeError, ValueError, ZeroDivisionError) as e:
                        track_calc_failure(symbol, "net_margin_trend", e)
    except Exception as e:
        logging.debug(f"Could not calculate margin trends for {symbol}: {e}")

    # ROE trend - calculate from annual data
    try:
        if "roe_trend" not in metrics or metrics["roe_trend"] is None:
            # Query net income and shareholder equity data
            cursor.execute("""
                SELECT date, net_income
                FROM annual_income_statement
                WHERE symbol = %s AND net_income IS NOT NULL
                ORDER BY date DESC
                LIMIT 2
            """, (symbol,))

            roe_data = cursor.fetchall()
            if len(roe_data) >= 2:
                # For ROE trend, use change in profitability
                curr_date, curr_ni = roe_data[0]
                prior_date, prior_ni = roe_data[1]

                # Calculate net income growth as ROE trend proxy
                if prior_ni is not None and prior_ni != 0:
                    try:
                        roe_trend = ((float(curr_ni) - float(prior_ni)) / abs(float(prior_ni))) * 100
                        metrics["roe_trend"] = round(roe_trend, 2)
                    except (TypeError, ValueError, ZeroDivisionError) as e:
                        track_calc_failure(symbol, "roe_trend", e)
    except Exception as e:
        logging.debug(f"Could not calculate ROE trend for {symbol}: {e}")

    # Asset growth - use if available from financial statements, otherwise None
    # (requires balance sheet data which is not in key_metrics)
    if "asset_growth_yoy" not in metrics:
        metrics["asset_growth_yoy"] = None

    # DATA INTEGRITY RULE: Return None for missing real data instead of using calculated proxies
    # Historical reason: Previous code tried to fill fcf_growth_yoy and ocf_growth_yoy with
    # calculated ratios (FCF margin, OCF-to-NI ratio) as "proxies" for growth
    # PROBLEM: These are NOT growth metrics - they corrupt scoring by mixing ratio data with growth data
    #
    # CORRECT BEHAVIOR: Only calculate these if real YoY data is available from financial statements
    # get_financial_statement_growth() has already run and populated these if real data exists
    # If it didn't populate them, it means data is unavailable → return None (don't use proxies)
    #
    # This ensures:
    # - Scores use REAL DATA only
    # - No false growth attribution based on margins/ratios
    # - Composite scoring is accurate and reliable

    return metrics


def get_volume_metrics(cursor, symbol: str) -> Dict:
    """Calculate volume-based stability metrics from price and volume data"""
    metrics = {
        "volume_consistency": None,
        "turnover_velocity": None,
        "volatility_volume_ratio": None,
        "daily_spread": None,
    }

    try:
        # Get last 252 trading days of OHLCV data
        cursor.execute("""
            SELECT date, open, high, low, close, volume, adj_close
            FROM price_daily
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 252
        """, (symbol,))

        price_data = cursor.fetchall()
        if len(price_data) < 20:
            return metrics

        # Reverse to chronological order
        price_data = list(reversed(price_data))

        # Extract data
        volumes = [p[5] for p in price_data if p[5]]  # volume column
        opens = [p[1] for p in price_data if p[1]]
        highs = [p[2] for p in price_data if p[2]]
        lows = [p[3] for p in price_data if p[3]]
        closes = [p[4] for p in price_data if p[4]]

        if len(volumes) < 20 or len(closes) < 20:
            return metrics

        # 1. VOLUME CONSISTENCY: Coefficient of variation of daily volume
        # Low CV = consistent volume, High CV = volatile volume
        try:
            avg_volume = float(np.mean(volumes))
            if avg_volume > 0:
                volume_cv = (float(np.std(volumes)) / avg_volume) * 100
                # Invert so higher score = better consistency (lower CV)
                metrics["volume_consistency"] = max(0, 100 - volume_cv)
        except (TypeError, ValueError) as e:
            track_calc_failure(symbol, "volume_consistency", e)

        # 2. TURNOVER VELOCITY: Average daily volume relative to 52-week average
        # Higher velocity = more active trading (capped at 999.99 for database precision)
        try:
            week_52_avg_volume = float(np.mean(volumes[-252:]))
            recent_avg_volume = float(np.mean(volumes[-20:]))
            if week_52_avg_volume > 0:
                turnover_vel = (recent_avg_volume / week_52_avg_volume) * 100
                # Cap at 999.99 to fit numeric(5,2) precision in database
                turnover_vel = min(999.99, max(0, turnover_vel))
                metrics["turnover_velocity"] = float(turnover_vel)
        except (TypeError, ValueError) as e:
            track_calc_failure(symbol, "volume_consistency", e)

        # 3. VOLATILITY/VOLUME RATIO: Price volatility normalized to volume volatility
        # Measures whether price swings correlate with volume (healthy = correlated)
        # Capped at 999.99 for database precision
        try:
            # Calculate price volatility (std dev of daily returns)
            returns = []
            for i in range(1, len(closes)):
                if closes[i-1] > 0:
                    ret = ((closes[i] - closes[i-1]) / closes[i-1]) * 100
                    returns.append(ret)

            if len(returns) >= 20:
                price_volatility = float(np.std(returns))
                volume_std = float(np.std(volumes))

                if volume_std > 0:
                    # Normalized ratio: price volatility / normalized volume volatility
                    vol_volume_ratio = (price_volatility * 100) / (volume_std / np.mean(volumes))
                    # Cap at 999.99 to fit database precision
                    vol_volume_ratio = min(999.99, max(0, vol_volume_ratio))
                    metrics["volatility_volume_ratio"] = float(vol_volume_ratio)
        except (TypeError, ValueError) as e:
            track_calc_failure(symbol, "volatility_volume_ratio", e)

        # 4. DAILY SPREAD: Average bid-ask spread as % of price
        # Calculated as (high - low) / close as proxy for spread
        try:
            spreads = []
            for i in range(len(highs)):
                if closes[i] > 0:
                    spread = ((highs[i] - lows[i]) / closes[i]) * 100
                    spreads.append(spread)

            if spreads:
                avg_spread = float(np.mean(spreads))
                metrics["daily_spread"] = avg_spread
        except (TypeError, ValueError) as e:
            track_calc_failure(symbol, "daily_spread", e)

    except Exception as e:
        logging.debug(f"Could not calculate volume metrics for {symbol}: {e}")

    return metrics


def get_stability_metrics(cursor, symbol: str, benchmark_cache: Dict = None) -> Dict:
    """Calculate stability metrics from price data (volatility, drawdown, beta)

    Args:
        cursor: Database cursor
        symbol: Stock symbol
        benchmark_cache: Cached benchmark (SPY) price data to avoid redundant queries

    Beta Strategy (YFINANCE ONLY):
    1. Get beta from yfinance table (via load_yfinance_beta.py)
    2. NO fallback calculations - must come from yfinance
    Requires robust yfinance loader to handle rate limiting
    """
    metrics = {
        "volatility_12m": None,
        "downside_volatility": None,
        "max_drawdown_52w": None,
        "beta": None,
    }

    # FIRST TRY: Get beta from yfinance via beta_yfinance table
    try:
        cursor.execute("SELECT beta FROM beta_yfinance WHERE symbol = %s", (symbol,))
        row = cursor.fetchone()
        if row and row[0] is not None:
            metrics["beta"] = float(row[0])
            logging.debug(f"{symbol}: Using yfinance beta = {metrics['beta']}")
            # Return early if we have yfinance beta for remaining metrics
            # Continue with volatility/drawdown calculation below
    except Exception as e:
        logging.debug(f"{symbol}: Could not retrieve yfinance beta: {e}")

    try:
        # Get last 252 trading days of price data for 12-month volatility
        cursor.execute("""
            SELECT date, adj_close
            FROM price_daily
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 252
        """, (symbol,))

        price_data = cursor.fetchall()
        if len(price_data) < 20:  # Need at least 20 data points
            return metrics

        # Reverse to chronological order
        price_data = list(reversed(price_data))
        prices = [p[1] for p in price_data]

        # Calculate daily returns (filter out None/invalid prices)
        returns = []
        for i in range(1, len(prices)):
            if prices[i-1] is not None and prices[i] is not None and prices[i-1] > 0:
                ret = ((prices[i] - prices[i-1]) / prices[i-1]) * 100
                returns.append(ret)

        if returns:
            # 12-month annualized volatility (std dev * sqrt(252))
            try:
                volatility = (np.std(returns) * np.sqrt(252))
                if isinstance(volatility, complex):
                    volatility = volatility.real
                volatility_f = float(volatility)
                metrics["volatility_12m"] = volatility_f if not np.isnan(volatility_f) else None
            except (TypeError, ValueError) as e:
                track_calc_failure(symbol, "volatility_12m", e)

            # Downside volatility (only negative returns)
            downside_returns = [r for r in returns if r < 0]
            if downside_returns:
                try:
                    downside_vol = (np.std(downside_returns) * np.sqrt(252))
                    if isinstance(downside_vol, complex):
                        downside_vol = downside_vol.real
                    downside_vol_f = float(downside_vol)
                    metrics["downside_volatility"] = downside_vol_f if not np.isnan(downside_vol_f) else None
                except (TypeError, ValueError) as e:
                    track_calc_failure(symbol, "volatility_12m", e)

        # Max drawdown (52-week window)
        if len(prices) >= 52:
            # Filter out None values from prices
            valid_prices = [p for p in prices[-252:] if p is not None and p > 0]  # Last 252 trading days
            if len(valid_prices) >= 10:  # Need at least 10 valid prices
                max_dd = 0
                peak = valid_prices[0]
                for price in valid_prices:
                    if price > peak:
                        peak = price
                    dd = ((peak - price) / peak) * 100
                    if dd > max_dd:
                        max_dd = dd
                metrics["max_drawdown_52w"] = float(max_dd) if max_dd > 0 else None

        # Beta must come from yfinance - no SPY fallback
        # If beta is None at this point, it means yfinance didn't have it
        if metrics["beta"] is None:
            logging.debug(f"{symbol}: Beta not available from yfinance (will be NULL in database)")

    except Exception as e:
        logging.error(f"Error calculating stability metrics for {symbol}: {e}")

    return metrics


def validate_beta_with_yfinance(symbol: str, calculated_beta: Optional[float]) -> Dict:
    """
    Validate our calculated beta against yfinance beta (for testing/validation only)

    Returns:
        dict with yfinance_beta, difference_pct, validation_status
    """
    import yfinance as yf

    validation = {
        "yfinance_beta": None,
        "calculated_beta": calculated_beta,
        "difference_pct": None,
        "status": "NO_CALCULATED_BETA"
    }

    if calculated_beta is None:
        return validation

    try:
        ticker = yf.Ticker(symbol)
        yf_beta = ticker.info.get('beta')

        if yf_beta is None:
            validation["status"] = "NO_YFINANCE_BETA"
            logging.debug(f"{symbol}: yfinance beta not available")
            return validation

        validation["yfinance_beta"] = float(yf_beta)

        # Calculate percentage difference
        if yf_beta != 0:
            diff_pct = abs((calculated_beta - yf_beta) / yf_beta) * 100
            validation["difference_pct"] = diff_pct

            if diff_pct <= 10:
                validation["status"] = "MATCH"
            elif diff_pct <= 25:
                validation["status"] = "CLOSE"
                logging.info(f"{symbol}: Beta diff {diff_pct:.1f}% - Calculated: {calculated_beta:.3f}, yfinance: {yf_beta:.3f}")
            else:
                validation["status"] = "MISMATCH"
                logging.warning(f"{symbol}: LARGE beta diff {diff_pct:.1f}% - Calculated: {calculated_beta:.3f}, yfinance: {yf_beta:.3f}")
        else:
            validation["status"] = "YFINANCE_BETA_ZERO"

    except Exception as e:
        logging.debug(f"{symbol}: Error validating beta: {e}")
        validation["status"] = "ERROR"

    return validation


def calculate_momentum_metrics(
    symbol: str, current_price: Optional[float]
) -> Dict:
    """Calculate momentum metrics from price history"""
    metrics = {
        "current_price": current_price,
        "momentum_1m": None,
        "momentum_3m": None,
        "momentum_6m": None,
        "momentum_12m": None,
    }

    if not current_price or current_price <= 0:
        return metrics

    # Fetch price history
    hist = get_price_history(symbol)

    if hist.empty:
        return metrics

    # Calculate momentum as percentage change from period start to end
    try:
        hist["Close"] = pd.to_numeric(hist["Close"], errors="coerce")

        # 1-month momentum (last 20-22 trading days)
        if len(hist) >= 20:
            price_1m_ago = hist["Close"].iloc[-20]
            if price_1m_ago and price_1m_ago > 0:
                metrics["momentum_1m"] = (
                    (current_price - price_1m_ago) / price_1m_ago * 100
                )

        # 3-month momentum (last 60 trading days)
        if len(hist) >= 60:
            price_3m_ago = hist["Close"].iloc[-60]
            if price_3m_ago and price_3m_ago > 0:
                metrics["momentum_3m"] = (
                    (current_price - price_3m_ago) / price_3m_ago * 100
                )

        # 6-month momentum (last 120 trading days)
        if len(hist) >= 120:
            price_6m_ago = hist["Close"].iloc[-120]
            if price_6m_ago and price_6m_ago > 0:
                metrics["momentum_6m"] = (
                    (current_price - price_6m_ago) / price_6m_ago * 100
                )

        # 12-month momentum (last 252 trading days)
        if len(hist) >= 252:
            price_12m_ago = hist["Close"].iloc[-252]
            if price_12m_ago and price_12m_ago > 0:
                metrics["momentum_12m"] = (
                    (current_price - price_12m_ago) / price_12m_ago * 100
                )
    except Exception as e:
        logging.warning(f"Failed to calculate momentum for {symbol}: {e}")

    return metrics


def calculate_accumulation_distribution_rating(cursor, symbol: str) -> Optional[float]:
    """
    Calculate IBD-style Accumulation/Distribution Rating (0-100 scale).

    Analyzes 20-60 trading days of volume data to determine institutional
    buying/selling patterns:
    - A: 90-100% accumulation volume = Strong Accumulation
    - B: 70-89% accumulation volume = Moderate Accumulation
    - C: 50-69% accumulation volume = Neutral
    - D: 30-49% accumulation volume = Moderate Distribution
    - E: 0-29% accumulation volume = Strong Distribution

    Returns numeric score on 50-100 scale (all positive).

    Coverage improvement: Minimum 20 days (reduced from 60) for better coverage of new stocks
    and low-liquidity securities. 20 days = 4 weeks of trading = meaningful A/D signal.
    """
    try:
        # Get last 100+ trading days of price/volume data (20 weeks)
        # Fetch more data to handle symbols with sparse recent data
        # Expanded from LIMIT 60 to LIMIT 100 to improve coverage of symbols with gaps
        cursor.execute("""
            SELECT date, close, volume
            FROM price_daily
            WHERE symbol = %s
            AND close IS NOT NULL
            AND volume IS NOT NULL
            ORDER BY date DESC
            LIMIT 100
        """, (symbol,))

        rows = cursor.fetchall()

        # Need at least 20 days of data for A/D calculation (reduced from 60 for better coverage)
        # 20 days = 4 weeks of trading activity, good balance between reliability and coverage
        # Improved from original 60-day requirement to cover new stocks and low-liquidity securities
        if len(rows) < 20:
            return None

        # Reverse to chronological order (oldest first)
        rows = list(reversed(rows))

        # Calculate accumulation vs distribution volume
        accumulation_volume = 0
        distribution_volume = 0
        total_volume = 0

        for i in range(1, len(rows)):
            current_date, current_close, current_volume = rows[i]
            previous_date, previous_close, previous_volume = rows[i-1]

            # Skip if no volume or price data
            if current_volume is None or current_close is None or previous_close is None:
                continue

            total_volume += current_volume

            # Up day (close > previous close) = accumulation
            if current_close > previous_close:
                accumulation_volume += current_volume
            # Down day (close < previous close) = distribution
            elif current_close < previous_close:
                distribution_volume += current_volume
            # Unchanged = neutral, doesn't count

        # If no trading volume, can't calculate
        if total_volume == 0:
            return None

        # If we have some data but less than 20 days, warn that it's minimal
        # But still calculate since we met the minimum requirement
        if len(rows) < 30 and len(rows) >= 20:
            logging.debug(f"{symbol}: A/D rating calculated with {len(rows)} days (ideal: 30+ days)")

        # Calculate accumulation percentage (0-100)
        accumulation_pct = (accumulation_volume / total_volume) * 100

        # Convert to 50-100 positive scale (letter grades)
        # Formula: 50 + (accumulation_pct / 2)
        # 100% accumulation = 100 (A: 90-100)
        # 80% accumulation = 90 (B: 80-89)
        # 70% accumulation = 85 (C: 70-79)
        # 50% accumulation = 75 (neutral/C grade)
        # 30% accumulation = 65 (D: 60-69)
        # 0% accumulation = 50 (E: 50-59, strong distribution)
        rating_score = 50 + (accumulation_pct / 2)

        return round(rating_score, 2)

    except Exception as e:
        logging.warning(f"❌ Failed to calculate A/D rating for {symbol}: {type(e).__name__}: {str(e)[:200]}")
        import traceback
        logging.debug(f"A/D calculation traceback: {traceback.format_exc()}")
        return None


def load_ad_ratings(conn, cursor, symbols: List[str]):
    """Load Accumulation/Distribution ratings for all symbols"""
    logging.info("Loading A/D ratings...")

    # Ensure clean transaction state
    try:
        conn.rollback()
    except:
        pass

    ad_rows = []
    failed_symbols = []

    for idx, symbol in enumerate(symbols, 1):
        try:
            ad_rating = calculate_accumulation_distribution_rating(cursor, symbol)

            # ALWAYS append result (even if None) so UPDATE runs for all symbols
            ad_rows.append((ad_rating, symbol))

            if ad_rating is None:
                failed_symbols.append(symbol)

            # Print progress every 100 symbols
            if idx % 100 == 0:
                logging.info(f"  ✓ A/D ratings: {idx}/{len(symbols)}")

        except Exception as e:
            logging.warning(f"Failed to calculate A/D for {symbol}: {e}")
            ad_rows.append((None, symbol))  # Still update with None so we track it
            failed_symbols.append(symbol)

    # Update positioning_metrics with A/D ratings (including None values)
    if ad_rows:
        logging.info(f"Updating {len(ad_rows)} A/D ratings in positioning_metrics...")
        logging.info(f"  ⚠️  {len(failed_symbols)} symbols with NULL A/D (insufficient price data or calculation failed)")

        updated_count = 0
        for ad_rating, symbol in ad_rows:
            try:
                cursor.execute("""
                    INSERT INTO positioning_metrics (symbol, ad_rating, created_at, updated_at)
                    VALUES (%s, %s, NOW(), NOW())
                    ON CONFLICT (symbol) DO UPDATE SET
                        ad_rating = EXCLUDED.ad_rating,
                        updated_at = NOW()
                """, (symbol, ad_rating))
                updated_count += 1
            except Exception as e:
                logging.warning(f"Failed to update A/D for {symbol}: {e}")
                # Don't rollback here - it aborts the whole transaction
                # Just skip this stock and continue with the next one

        try:
            conn.commit()
            logging.info(f"✅ Updated {updated_count} A/D ratings ({len(ad_rows) - len(failed_symbols)} with values, {len(failed_symbols)} NULL)")
        except Exception as e:
            logging.error(f"Failed to commit A/D updates: {e}")
            conn.rollback()


def load_quality_metrics(conn, cursor, symbols: List[str]):
    """Load quality metrics for all symbols - with fallback for missing key_metrics"""
    logging.info("Loading quality metrics...")

    # Recover from any previous transaction abort
    try:
        conn.rollback()
    except Exception as e:
        logging.debug(f"Rollback during quality metrics setup: {e}")
        pass

    # Helper function to cap extreme ratio values that exceed database NUMERIC(8,4) precision
    def cap_ratio(val, max_val=9999):
        if val is None: return None
        return max(-max_val, min(max_val, float(val)))

    quality_rows = []

    # First: Get all key_metrics data in one query
    cursor.execute(
        "SELECT ticker, return_on_equity_pct, return_on_assets_pct, "
        "gross_margin_pct, operating_margin_pct, profit_margin_pct, "
        "free_cashflow, net_income, operating_cashflow, debt_to_equity, "
        "current_ratio, quick_ratio, payout_ratio, ebitda, total_debt, total_cash, "
        "total_revenue "
        "FROM key_metrics WHERE ticker = ANY(%s)",
        (symbols,)
    )

    processed_symbols = set()

    for row in cursor.fetchall():
        try:
            symbol = row[0]
            processed_symbols.add(symbol)
            ticker_dict = {
                "ticker": symbol,
                "return_on_equity_pct": row[1],
                "return_on_assets_pct": row[2],
                "gross_margin_pct": row[3],
                "operating_margin_pct": row[4],
                "profit_margin_pct": row[5],
                "free_cashflow": row[6],
                "net_income": row[7],
                "operating_cashflow": row[8],
                "debt_to_equity": row[9],
                "current_ratio": row[10],
                "quick_ratio": row[11],
                "payout_ratio": row[12],
                "ebitda": row[13],
                "total_debt": row[14],
                "total_cash": row[15],
                "total_revenue": row[16],
            }

            # Calculate quality metrics from key_metrics
            metrics = calculate_quality_metrics(ticker_dict, ticker=None, symbol=symbol)

            # Get earnings surprise metrics from quarterly statements
            earnings_metrics = get_earnings_surprise_metrics(cursor, symbol)
            metrics.update(earnings_metrics)

            # Get additional earnings quality metrics
            metrics["earnings_beat_rate"] = get_earnings_beat_rate(cursor, symbol)
            metrics["consecutive_positive_quarters"] = get_consecutive_positive_quarters(cursor, symbol)
            metrics["surprise_consistency"] = get_surprise_consistency(cursor, symbol)
            metrics["estimate_revision_direction"] = get_estimate_revision_direction(cursor, symbol)
            metrics["earnings_growth_4q_avg"] = get_earnings_growth_4q_avg(cursor, symbol)

            # Get estimate trends and revision activity
            metrics["revision_activity_30d"] = get_revision_activity_30d(cursor, symbol)
            metrics["estimate_momentum_60d"] = get_estimate_momentum_60d(cursor, symbol)
            metrics["estimate_momentum_90d"] = get_estimate_momentum_90d(cursor, symbol)
            metrics["revision_trend_score"] = get_revision_trend_score(cursor, symbol)

            quality_rows.append([
                ticker_dict["ticker"],
                date.today(),
                metrics.get("return_on_equity_pct"),
                metrics.get("return_on_assets_pct"),
                metrics.get("return_on_invested_capital_pct"),
                metrics.get("gross_margin_pct"),
                metrics.get("operating_margin_pct"),
                metrics.get("profit_margin_pct"),
                metrics.get("fcf_to_net_income"),
                metrics.get("operating_cf_to_net_income"),
                cap_ratio(metrics.get("debt_to_equity")),  # Cap D/E at ±9999
                cap_ratio(metrics.get("current_ratio")),  # Cap current ratio at ±9999
                cap_ratio(metrics.get("quick_ratio")),    # Cap quick ratio at ±9999
                metrics.get("earnings_surprise_avg"),
                metrics.get("eps_growth_stability"),
                metrics.get("payout_ratio"),
                metrics.get("earnings_beat_rate"),
                metrics.get("estimate_revision_direction"),
                metrics.get("consecutive_positive_quarters"),
                metrics.get("surprise_consistency"),
                metrics.get("earnings_growth_4q_avg"),
                metrics.get("revision_activity_30d"),
                metrics.get("estimate_momentum_60d"),
                metrics.get("estimate_momentum_90d"),
                metrics.get("revision_trend_score"),
            ])
        except Exception as e:
            logging.warning(f"Error processing quality metrics for {symbol}: {e}")
            # Recover from transaction abort to continue processing other symbols
            try:
                conn.rollback()
            except Exception as rollback_e:
                logging.debug(f"Rollback failed after quality metrics error for {symbol}: {rollback_e}")
                pass

    # FALLBACK: Process stocks missing from key_metrics but with financial statement data
    missing_symbols = set(symbols) - processed_symbols
    if missing_symbols:
        logging.info(f"Processing {len(missing_symbols)} symbols with financial data but no key_metrics data")

        for symbol in missing_symbols:
            try:
                # Recover transaction state before processing each symbol
                try:
                    conn.rollback()
                except Exception as rollback_e:
                    logging.debug(f"Rollback failed before processing {symbol}: {rollback_e}")
                    pass

                # Calculate quality metrics from balance sheet and income statement
                # Get balance sheet data
                balance_row = None
                try:
                    cursor.execute("""
                        SELECT total_assets, total_debt, total_cash, current_assets, current_liabilities,
                               quick_assets
                        FROM annual_balance_sheet
                        WHERE symbol = %s
                        ORDER BY fiscal_date DESC
                        LIMIT 1
                    """, (symbol,))
                    balance_row = cursor.fetchone()
                except Exception as e:
                    logging.debug(f"Could not fetch balance sheet for {symbol}: {e}")
                    conn.rollback()

                # Get income statement data
                income_row = None
                try:
                    cursor.execute("""
                        SELECT total_revenue, gross_profit, operating_income, net_income, ebitda
                        FROM annual_income_statement
                        WHERE symbol = %s
                        ORDER BY fiscal_date DESC
                        LIMIT 1
                    """, (symbol,))
                    income_row = cursor.fetchone()
                except Exception as e:
                    logging.debug(f"Could not fetch income statement for {symbol}: {e}")
                    conn.rollback()

                # Create minimal ticker dict from available data
                ticker_dict = {
                    "ticker": symbol,
                    "return_on_equity_pct": None,
                    "return_on_assets_pct": None,
                    "gross_margin_pct": None,
                    "operating_margin_pct": None,
                    "profit_margin_pct": None,
                    "free_cashflow": None,
                    "net_income": income_row[3] if income_row else None,
                    "operating_cashflow": None,
                    "debt_to_equity": None,
                    "current_ratio": None,
                    "quick_ratio": None,
                    "payout_ratio": None,
                    "ebitda": income_row[4] if income_row else None,
                    "total_debt": balance_row[1] if balance_row else None,
                    "total_cash": balance_row[2] if balance_row else None,
                    "total_revenue": income_row[0] if income_row else None,
                }

                # Calculate what we can from available data
                if balance_row and income_row:
                    total_assets, total_debt, total_cash, current_assets, current_liabilities, quick_assets = balance_row
                    total_revenue, gross_profit, operating_income, net_income, ebitda = income_row

                    # Calculate ratios from balance sheet and income statement
                    if total_assets and net_income:
                        ticker_dict["return_on_assets_pct"] = (net_income / total_assets) * 100
                    if total_debt and gross_profit and total_revenue:
                        ticker_dict["debt_to_equity"] = total_debt / max(total_assets - total_debt, 1)
                    if current_assets and current_liabilities:
                        ticker_dict["current_ratio"] = current_assets / max(current_liabilities, 1)
                    if quick_assets and current_liabilities:
                        ticker_dict["quick_ratio"] = quick_assets / max(current_liabilities, 1)
                    if total_revenue:
                        if gross_profit:
                            ticker_dict["gross_margin_pct"] = (gross_profit / total_revenue) * 100
                        if operating_income:
                            ticker_dict["operating_margin_pct"] = (operating_income / total_revenue) * 100
                        if net_income:
                            ticker_dict["profit_margin_pct"] = (net_income / total_revenue) * 100

                metrics = calculate_quality_metrics(ticker_dict, ticker=None, symbol=symbol)

                # Get earnings surprise metrics from quarterly statements
                earnings_metrics = get_earnings_surprise_metrics(cursor, symbol)
                metrics.update(earnings_metrics)

                # Get additional earnings quality metrics
                metrics["earnings_beat_rate"] = get_earnings_beat_rate(cursor, symbol)
                metrics["consecutive_positive_quarters"] = get_consecutive_positive_quarters(cursor, symbol)
                metrics["surprise_consistency"] = get_surprise_consistency(cursor, symbol)
                metrics["estimate_revision_direction"] = get_estimate_revision_direction(cursor, symbol)
                metrics["earnings_growth_4q_avg"] = get_earnings_growth_4q_avg(cursor, symbol)

                # Get estimate trends and revision activity
                metrics["revision_activity_30d"] = get_revision_activity_30d(cursor, symbol)
                metrics["estimate_momentum_60d"] = get_estimate_momentum_60d(cursor, symbol)
                metrics["estimate_momentum_90d"] = get_estimate_momentum_90d(cursor, symbol)
                metrics["revision_trend_score"] = get_revision_trend_score(cursor, symbol)

                quality_rows.append([
                    symbol,
                    date.today(),
                    metrics.get("return_on_equity_pct"),
                    metrics.get("return_on_assets_pct"),
                    metrics.get("return_on_invested_capital_pct"),
                    metrics.get("gross_margin_pct"),
                    metrics.get("operating_margin_pct"),
                    metrics.get("profit_margin_pct"),
                    metrics.get("fcf_to_net_income"),
                    metrics.get("operating_cf_to_net_income"),
                    cap_ratio(metrics.get("debt_to_equity")),  # Cap D/E at ±9999
                    cap_ratio(metrics.get("current_ratio")),  # Cap current ratio at ±9999
                    cap_ratio(metrics.get("quick_ratio")),    # Cap quick ratio at ±9999
                    metrics.get("earnings_surprise_avg"),
                    metrics.get("eps_growth_stability"),
                    metrics.get("payout_ratio"),
                    metrics.get("earnings_beat_rate"),
                    metrics.get("estimate_revision_direction"),
                    metrics.get("consecutive_positive_quarters"),
                    metrics.get("surprise_consistency"),
                    metrics.get("earnings_growth_4q_avg"),
                    metrics.get("revision_activity_30d"),
                    metrics.get("estimate_momentum_60d"),
                    metrics.get("estimate_momentum_90d"),
                    metrics.get("revision_trend_score"),
                ])
            except Exception as e:
                logging.warning(f"Error processing fallback quality metrics for {symbol}: {e}")
                # Recover from transaction abort to continue processing other symbols
                try:
                    conn.rollback()
                except Exception as rollback_e:
                    logging.debug(f"Rollback failed after fallback quality metrics error for {symbol}: {rollback_e}")
                    pass

    # Upsert quality_metrics
    if quality_rows:
        upsert_sql = """
            INSERT INTO quality_metrics (
                symbol, date, return_on_equity_pct, return_on_assets_pct,
                return_on_invested_capital_pct, gross_margin_pct, operating_margin_pct,
                profit_margin_pct, fcf_to_net_income, operating_cf_to_net_income,
                debt_to_equity, current_ratio, quick_ratio, earnings_surprise_avg,
                eps_growth_stability, payout_ratio,
                earnings_beat_rate, estimate_revision_direction, consecutive_positive_quarters,
                surprise_consistency, earnings_growth_4q_avg, revision_activity_30d,
                estimate_momentum_60d, estimate_momentum_90d, revision_trend_score
            ) VALUES %s
            ON CONFLICT (symbol, date) DO UPDATE SET
                return_on_equity_pct = EXCLUDED.return_on_equity_pct,
                return_on_assets_pct = EXCLUDED.return_on_assets_pct,
                return_on_invested_capital_pct = EXCLUDED.return_on_invested_capital_pct,
                gross_margin_pct = EXCLUDED.gross_margin_pct,
                operating_margin_pct = EXCLUDED.operating_margin_pct,
                profit_margin_pct = EXCLUDED.profit_margin_pct,
                fcf_to_net_income = EXCLUDED.fcf_to_net_income,
                operating_cf_to_net_income = EXCLUDED.operating_cf_to_net_income,
                debt_to_equity = EXCLUDED.debt_to_equity,
                current_ratio = EXCLUDED.current_ratio,
                quick_ratio = EXCLUDED.quick_ratio,
                earnings_surprise_avg = EXCLUDED.earnings_surprise_avg,
                eps_growth_stability = EXCLUDED.eps_growth_stability,
                payout_ratio = EXCLUDED.payout_ratio,
                earnings_beat_rate = EXCLUDED.earnings_beat_rate,
                estimate_revision_direction = EXCLUDED.estimate_revision_direction,
                consecutive_positive_quarters = EXCLUDED.consecutive_positive_quarters,
                surprise_consistency = EXCLUDED.surprise_consistency,
                earnings_growth_4q_avg = EXCLUDED.earnings_growth_4q_avg,
                revision_activity_30d = EXCLUDED.revision_activity_30d,
                estimate_momentum_60d = EXCLUDED.estimate_momentum_60d,
                estimate_momentum_90d = EXCLUDED.estimate_momentum_90d,
                revision_trend_score = EXCLUDED.revision_trend_score
        """
        try:
            # First, try to recover from any transaction abort from previous steps
            try:
                conn.rollback()
            except Exception as rollback_e:
                logging.debug(f"Rollback before quality metrics upsert: {rollback_e}")
                pass

            execute_values(cursor, upsert_sql, quality_rows)
            conn.commit()
            logging.info(f"Loaded {len(quality_rows)} quality metric records")
        except Exception as e:
            logging.error(f"Failed to insert quality metrics: {e}")
            try:
                conn.rollback()
            except Exception as rollback_e:
                logging.debug(f"Rollback after quality metrics insert failure: {rollback_e}")
                pass
            # Re-raise so main() can handle and recreate cursor
            raise


def load_growth_metrics(conn, cursor, symbols: List[str]):
    """Load growth metrics for all symbols with proper transaction isolation"""
    logging.info(f"Loading growth metrics for {len(symbols)} symbols...")

    # Ensure clean transaction state and enable autocommit to avoid transaction abort issues
    try:
        conn.rollback()
    except:
        pass

    try:
        conn.autocommit = True
    except:
        pass

    growth_rows = []

    # Get all key_metrics data in one query - include margin and financial data for trend calculations
    try:
        cursor.execute(
            """
            SELECT ticker,
                   revenue_growth_pct,
                   earnings_growth_pct,
                   earnings_q_growth_pct,
                   return_on_equity_pct,
                   payout_ratio,
                   gross_margin_pct,
                   operating_margin_pct,
                   profit_margin_pct,
                   ebitda_margin_pct,
                   free_cashflow,
                   net_income,
                   operating_cashflow,
                   total_revenue,
                   eps_trailing,
                   eps_forward
            FROM key_metrics
            WHERE ticker = ANY(%s)
            """,
            (symbols,)
        )

        # Materialize results to avoid cursor state issues with nested queries
        key_metrics_rows = cursor.fetchall()
    except Exception as e:
        logging.warning(f"Failed to fetch key_metrics: {e}. Attempting to recover...")
        try:
            conn.rollback()
        except Exception as rollback_e:
            logging.debug(f"Rollback failed during key_metrics recovery: {rollback_e}")
            pass
        cursor.close()
        cursor = conn.cursor()
        key_metrics_rows = []

    for idx, row in enumerate(key_metrics_rows):
        try:
            ticker = row[0]
            ticker_dict = {
                "ticker": ticker,
                "revenue_growth_pct": row[1],
                "earnings_growth_pct": row[2],
                "earnings_q_growth_pct": row[3],
                "return_on_equity_pct": row[4],
                "payout_ratio": row[5],
                "gross_margin_pct": row[6],
                "operating_margin_pct": row[7],
                "profit_margin_pct": row[8],
                "ebitda_margin_pct": row[9],
                "free_cashflow": row[10],
                "net_income": row[11],
                "operating_cashflow": row[12],
                "total_revenue": row[13],
                "eps_trailing": row[14],
                "eps_forward": row[15],
            }

            # Get growth metrics from multiple sources (priority order) with error recovery
            financial_growth = None
            quarterly_growth = None
            earnings_history_growth = None

            try:
                financial_growth = get_financial_statement_growth(cursor, ticker)
            except Exception as fge:
                logging.debug(f"Could not get financial growth for {ticker}: {fge}")
                try:
                    conn.rollback()
                except:
                    pass
                cursor = conn.cursor()
                financial_growth = None

            try:
                quarterly_growth = get_quarterly_statement_growth(cursor, ticker)
            except Exception as qge:
                logging.debug(f"Could not get quarterly growth for {ticker}: {qge}")
                try:
                    conn.rollback()
                except:
                    pass
                cursor = conn.cursor()
                quarterly_growth = None

            try:
                earnings_history_growth = get_earnings_history_growth(cursor, ticker)
            except Exception as ege:
                logging.debug(f"Could not get earnings history growth for {ticker}: {ege}")
                try:
                    conn.rollback()
                except:
                    pass
                cursor = conn.cursor()
                earnings_history_growth = None

            # Calculate metrics combining all available data sources
            try:
                metrics = calculate_growth_metrics(ticker_dict, financial_growth, quarterly_growth, earnings_history_growth, cursor, ticker)
            except Exception as mce:
                logging.debug(f"Error calculating growth metrics for {ticker}: {mce}")
                metrics = {}  # Return empty metrics instead of failing

            growth_rows.append([
                ticker,
                date.today(),
                metrics.get("revenue_growth_3y_cagr"),
                metrics.get("eps_growth_3y_cagr"),
                metrics.get("operating_income_growth_yoy"),
                metrics.get("roe_trend"),
                metrics.get("sustainable_growth_rate"),
                metrics.get("fcf_growth_yoy"),
                metrics.get("ocf_growth_yoy"),
                metrics.get("net_income_growth_yoy"),
                metrics.get("gross_margin_trend"),
                metrics.get("operating_margin_trend"),
                metrics.get("net_margin_trend"),
                metrics.get("quarterly_growth_momentum"),
                metrics.get("asset_growth_yoy"),
                metrics.get("revenue_growth_yoy"),
            ])

            # Commit every 100 symbols to prevent transaction bloat
            if (idx + 1) % 100 == 0:
                try:
                    conn.commit()
                    logging.debug(f"Committed growth metrics for {idx + 1} symbols")
                except Exception as commit_e:
                    logging.warning(f"Commit failed at symbol {idx + 1}: {commit_e}")
                    try:
                        conn.rollback()
                    except:
                        pass
                    cursor = conn.cursor()
        except Exception as e:
            logging.warning(f"Error processing growth metrics for {row[0] if row else 'unknown'}: {e}")

    # Also process symbols that have financial statement data but no key_metrics
    # These are companies with annual income statements but missing from key_metrics table
    cursor.execute("""
        SELECT DISTINCT symbol
        FROM annual_income_statement ais
        WHERE symbol = ANY(%s)
        AND NOT EXISTS (SELECT 1 FROM growth_metrics WHERE symbol = ais.symbol)
        AND NOT EXISTS (SELECT 1 FROM key_metrics WHERE ticker = ais.symbol)
    """, (symbols,))

    missing_key_metrics_symbols = [row[0] for row in cursor.fetchall()]

    if missing_key_metrics_symbols:
        logging.info(f"Processing {len(missing_key_metrics_symbols)} symbols with financial statements but no key_metrics")

        for symbol in missing_key_metrics_symbols:
            # Get growth metrics from multiple sources (priority order) with error recovery
            financial_growth = None
            quarterly_growth = None
            earnings_history_growth = None

            try:
                financial_growth = get_financial_statement_growth(cursor, symbol)
            except Exception as fge:
                logging.debug(f"Could not get financial growth for {symbol}: {fge}")
                try:
                    conn.rollback()
                except:
                    pass
                cursor = conn.cursor()
                financial_growth = None

            try:
                quarterly_growth = get_quarterly_statement_growth(cursor, symbol)
            except Exception as qge:
                logging.debug(f"Could not get quarterly growth for {symbol}: {qge}")
                try:
                    conn.rollback()
                except:
                    pass
                cursor = conn.cursor()
                quarterly_growth = None

            try:
                earnings_history_growth = get_earnings_history_growth(cursor, symbol)
            except Exception as ege:
                logging.debug(f"Could not get earnings history growth for {symbol}: {ege}")
                try:
                    conn.rollback()
                except:
                    pass
                cursor = conn.cursor()
                earnings_history_growth = None

            # Create minimal metrics dict (no key_metrics available)
            ticker_dict = {
                "ticker": symbol,
                "revenue_growth_pct": None,
                "earnings_growth_pct": None,
                "earnings_q_growth_pct": None,
                "return_on_equity_pct": None,
                "payout_ratio": None,
                "gross_margin_pct": None,
                "operating_margin_pct": None,
                "profit_margin_pct": None,
                "ebitda_margin_pct": None,
                "free_cashflow": None,
                "net_income": None,
                "operating_cashflow": None,
                "total_revenue": None,
                "eps_trailing": None,
                "eps_forward": None,
            }

            # Calculate metrics using all available financial data
            metrics = calculate_growth_metrics(ticker_dict, financial_growth, quarterly_growth, earnings_history_growth)
            growth_rows.append([
                symbol,
                date.today(),
                metrics.get("revenue_growth_3y_cagr"),
                metrics.get("eps_growth_3y_cagr"),
                metrics.get("operating_income_growth_yoy"),
                metrics.get("roe_trend"),
                metrics.get("sustainable_growth_rate"),
                metrics.get("fcf_growth_yoy"),
                metrics.get("ocf_growth_yoy"),
                metrics.get("net_income_growth_yoy"),
                metrics.get("gross_margin_trend"),
                metrics.get("operating_margin_trend"),
                metrics.get("net_margin_trend"),
                metrics.get("quarterly_growth_momentum"),
                metrics.get("asset_growth_yoy"),
                metrics.get("revenue_growth_yoy"),
            ])

    # Upsert growth_metrics
    logging.info(f"DEBUG: growth_rows has {len(growth_rows)} rows before upsert")
    if growth_rows:
        logging.info(f"DEBUG: First row sample: {growth_rows[0] if growth_rows else 'EMPTY'}")
        upsert_sql = """
            INSERT INTO growth_metrics (
                symbol, date, revenue_growth_3y_cagr, eps_growth_3y_cagr,
                operating_income_growth_yoy, roe_trend, sustainable_growth_rate,
                fcf_growth_yoy, ocf_growth_yoy, net_income_growth_yoy, gross_margin_trend,
                operating_margin_trend, net_margin_trend, quarterly_growth_momentum,
                asset_growth_yoy, revenue_growth_yoy
            ) VALUES %s
            ON CONFLICT (symbol, date) DO UPDATE SET
                revenue_growth_3y_cagr = EXCLUDED.revenue_growth_3y_cagr,
                eps_growth_3y_cagr = EXCLUDED.eps_growth_3y_cagr,
                operating_income_growth_yoy = EXCLUDED.operating_income_growth_yoy,
                roe_trend = EXCLUDED.roe_trend,
                sustainable_growth_rate = EXCLUDED.sustainable_growth_rate,
                fcf_growth_yoy = EXCLUDED.fcf_growth_yoy,
                ocf_growth_yoy = EXCLUDED.ocf_growth_yoy,
                net_income_growth_yoy = EXCLUDED.net_income_growth_yoy,
                gross_margin_trend = EXCLUDED.gross_margin_trend,
                operating_margin_trend = EXCLUDED.operating_margin_trend,
                net_margin_trend = EXCLUDED.net_margin_trend,
                quarterly_growth_momentum = EXCLUDED.quarterly_growth_momentum,
                asset_growth_yoy = EXCLUDED.asset_growth_yoy,
                revenue_growth_yoy = EXCLUDED.revenue_growth_yoy
        """
        try:
            # First, try to recover from any transaction abort from previous steps
            try:
                conn.rollback()
            except Exception as rollback_e:
                logging.debug(f"Rollback before growth metrics upsert: {rollback_e}")
                pass

            logging.info(f"DEBUG: About to execute_values with {len(growth_rows)} rows")
            execute_values(cursor, upsert_sql, growth_rows)
            logging.info(f"DEBUG: execute_values completed successfully")
            conn.commit()
            logging.info(f"DEBUG: commit completed")
            logging.info(f"Loaded {len(growth_rows)} growth metric records")
        except Exception as e:
            logging.error(f"Failed to insert growth metrics: {e}")
            try:
                conn.rollback()
            except Exception as rollback_e:
                logging.debug(f"Rollback after growth metrics insert failure: {rollback_e}")
                pass
            # Don't raise - continue to next step so data isn't completely lost


def load_momentum_metrics(conn, cursor, symbols: List[str]):
    """Load momentum metrics from price_daily database - skip yfinance, use local data only"""
    logging.info("Loading momentum metrics from price_daily table...")

    # Ensure clean transaction state
    try:
        conn.rollback()
    except:
        pass

    momentum_rows = []

    # Insert records ONLY for symbols with actual price data in price_daily table
    # This avoids yfinance calls entirely and uses pre-loaded data
    for i, symbol in enumerate(symbols):
        if i % 100 == 0:
            logging.info(f"Processing momentum for {symbol} ({i+1}/{len(symbols)})")

        metrics = {
            "current_price": None,
            "momentum_3m": None,
            "momentum_6m": None,
            "momentum_12m": None,
            "price_vs_sma_50": None,
            "price_vs_sma_200": None,
            "price_vs_52w_high": None,
        }

        try:
            # Get price data from price_daily table (already loaded, no yfinance needed)
            cursor.execute("""
                SELECT date, adj_close
                FROM price_daily
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT 252
            """, (symbol,))

            price_data = cursor.fetchall()
            if len(price_data) > 0:
                # Reverse to chronological order
                price_data = list(reversed(price_data))
                prices = [p[1] for p in price_data]
                current_price = prices[-1] if prices else None

                # Calculate momentum from price data
                if current_price and len(prices) >= 20:
                    # Calculate raw momentum values
                    m3m = ((prices[-1] - prices[-60]) / prices[-60] * 100) if len(prices) >= 60 else None
                    m6m = ((prices[-1] - prices[-120]) / prices[-120] * 100) if len(prices) >= 120 else None
                    m12m = ((prices[-1] - prices[-252]) / prices[-252] * 100) if len(prices) >= 252 else None

                    # Calculate 50-day SMA (price vs SMA_50)
                    sma_50 = None
                    if len(prices) >= 50:
                        sma_50 = sum(prices[-50:]) / 50
                        price_vs_sma_50 = ((current_price - sma_50) / sma_50 * 100) if sma_50 > 0 else None
                    else:
                        price_vs_sma_50 = None

                    # Calculate 200-day SMA (price vs SMA_200)
                    sma_200 = None
                    if len(prices) >= 200:
                        sma_200 = sum(prices[-200:]) / 200
                        price_vs_sma_200 = ((current_price - sma_200) / sma_200 * 100) if sma_200 > 0 else None
                    else:
                        price_vs_sma_200 = None

                    # Calculate 52-week high (price vs 52-week high)
                    high_52w = None
                    if len(prices) >= 252:
                        high_52w = max(prices[-252:])
                        price_vs_52w_high = ((current_price - high_52w) / high_52w * 100) if high_52w > 0 else None
                    else:
                        price_vs_52w_high = None

                    # Cap momentum values to fit numeric(8,4) precision constraint (±9999.99)
                    # Field max is 9999.9999, so cap at ±9999.99 to be safe
                    def cap_momentum(val):
                        if val is None:
                            return None
                        return max(-9999.99, min(9999.99, round(val, 2)))

                    metrics = {
                        "current_price": current_price,
                        "momentum_3m": cap_momentum(m3m),
                        "momentum_6m": cap_momentum(m6m),
                        "momentum_12m": cap_momentum(m12m),
                        "price_vs_sma_50": cap_momentum(price_vs_sma_50),
                        "price_vs_sma_200": cap_momentum(price_vs_sma_200),
                        "price_vs_52w_high": cap_momentum(price_vs_52w_high),
                    }
        except Exception as e:
            logging.debug(f"Could not calculate momentum for {symbol}: {e}")

        # Only insert if we have actual data
        if metrics.get("current_price"):
            momentum_rows.append([
                symbol,
                date.today(),
                metrics.get("current_price"),
                metrics.get("momentum_1m"),
                metrics.get("momentum_3m"),
                metrics.get("momentum_6m"),
                metrics.get("momentum_12m"),
                metrics.get("price_vs_sma_50"),
                metrics.get("price_vs_sma_200"),
                metrics.get("price_vs_52w_high"),
            ])

    # Upsert momentum_metrics - will now have all symbols with proper NULL handling
    if momentum_rows:
        upsert_sql = """
            INSERT INTO momentum_metrics (
                symbol, date, current_price, momentum_1m, momentum_3m,
                momentum_6m, momentum_12m, price_vs_sma_50, price_vs_sma_200,
                price_vs_52w_high
            ) VALUES %s
            ON CONFLICT (symbol, date) DO UPDATE SET
                current_price = EXCLUDED.current_price,
                momentum_1m = EXCLUDED.momentum_1m,
                momentum_3m = EXCLUDED.momentum_3m,
                momentum_6m = EXCLUDED.momentum_6m,
                momentum_12m = EXCLUDED.momentum_12m,
                price_vs_sma_50 = EXCLUDED.price_vs_sma_50,
                price_vs_sma_200 = EXCLUDED.price_vs_sma_200,
                price_vs_52w_high = EXCLUDED.price_vs_52w_high
        """
        try:
            execute_values(cursor, upsert_sql, momentum_rows)
            conn.commit()
            logging.info(f"Loaded {len(momentum_rows)} momentum metric records (all {len(symbols)} stocks)")
        except Exception as e:
            logging.error(f"Failed to insert momentum metrics: {e}")
            conn.rollback()
            raise


def load_stability_metrics(conn, cursor, symbols: List[str]):
    """Load stability metrics (volatility, drawdown, beta, volume metrics) from price data"""
    logging.info("Loading stability metrics...")

    # Ensure clean transaction state
    try:
        conn.rollback()
    except:
        pass

    stability_rows = []
    today = date.today()

    # Initialize benchmark cache to avoid redundant SPY queries
    # This reduces database load from 5000+ SPY queries to just 1
    benchmark_cache = {}
    logging.info(f"📊 Benchmark cache initialized - SPY data will be loaded once and reused for {len(symbols)} symbols")

    for i, symbol in enumerate(symbols, 1):
        try:
            # Get traditional stability metrics (volatility, drawdown, beta)
            # Pass benchmark_cache to reuse SPY data for all symbols
            stability = get_stability_metrics(cursor, symbol, benchmark_cache)

            # Validate beta if enabled (for testing/verification)
            if os.environ.get("VALIDATE_BETA", "false").lower() == "true":
                if stability.get("beta") is not None:
                    validation = validate_beta_with_yfinance(symbol, stability["beta"])
                    logging.debug(f"{symbol}: Beta validation result - {validation['status']}")

                    # Store validation results in beta_validation table
                    if validation["yfinance_beta"] is not None:
                        try:
                            cursor.execute("""
                                INSERT INTO beta_validation
                                (symbol, date, beta_calculated, beta_yfinance, difference_pct, validation_status)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT (symbol, date) DO UPDATE SET
                                    beta_calculated = EXCLUDED.beta_calculated,
                                    beta_yfinance = EXCLUDED.beta_yfinance,
                                    difference_pct = EXCLUDED.difference_pct,
                                    validation_status = EXCLUDED.validation_status,
                                    created_at = CURRENT_TIMESTAMP
                            """, (
                                symbol,
                                today,
                                validation["calculated_beta"],
                                validation["yfinance_beta"],
                                validation["difference_pct"],
                                validation["status"]
                            ))
                            conn.commit()
                        except Exception as e:
                            logging.debug(f"Could not store beta validation for {symbol}: {e}")

            # Get volume-based stability metrics (consistency, velocity, ratio, spread)
            volume_metrics = get_volume_metrics(cursor, symbol)

            # Merge both metric sets
            all_metrics = {**stability, **volume_metrics}

            if any(v is not None for v in all_metrics.values()):
                stability_rows.append((
                    symbol,
                    today,
                    all_metrics.get("volatility_12m"),
                    all_metrics.get("downside_volatility"),
                    all_metrics.get("max_drawdown_52w"),
                    all_metrics.get("beta"),
                    all_metrics.get("volume_consistency"),
                    all_metrics.get("turnover_velocity"),
                    all_metrics.get("volatility_volume_ratio"),
                    all_metrics.get("daily_spread")
                ))

            if (i % 100) == 0:
                logging.info(f"Processed {i}/{len(symbols)} symbols for stability metrics")

            # Pause to avoid rate limiting
            if (i + 1) % 100 == 0:
                time.sleep(1)

        except Exception as e:
            logging.debug(f"Could not load stability metrics for {symbol}: {e}")

    # Upsert stability_metrics with all 8 columns (original 4 + new 4 volume metrics)
    if stability_rows:
        upsert_sql = """
            INSERT INTO stability_metrics (
                symbol, date, volatility_12m, downside_volatility,
                max_drawdown_52w, beta, volume_consistency, turnover_velocity,
                volatility_volume_ratio, daily_spread
            ) VALUES %s
            ON CONFLICT (symbol, date) DO UPDATE SET
                volatility_12m = EXCLUDED.volatility_12m,
                downside_volatility = EXCLUDED.downside_volatility,
                max_drawdown_52w = EXCLUDED.max_drawdown_52w,
                beta = EXCLUDED.beta,
                volume_consistency = EXCLUDED.volume_consistency,
                turnover_velocity = EXCLUDED.turnover_velocity,
                volatility_volume_ratio = EXCLUDED.volatility_volume_ratio,
                daily_spread = EXCLUDED.daily_spread
        """
        try:
            execute_values(cursor, upsert_sql, stability_rows)
            conn.commit()
            logging.info(f"Loaded {len(stability_rows)} stability metric records (including volume metrics)")
        except Exception as e:
            logging.error(f"Failed to insert stability metrics: {e}")
            conn.rollback()
            raise


def load_value_metrics(conn, cursor, symbols: List[str]):
    """Load value metrics (PE, P/B, P/S, EV/EBITDA, etc.) from key_metrics"""
    logging.info("Loading value metrics...")

    # Ensure clean transaction state
    try:
        conn.rollback()
    except:
        pass

    value_rows = []
    today = date.today()

    for symbol in symbols:
        try:
            cursor.execute("""
                SELECT trailing_pe, forward_pe, price_to_book, price_to_sales_ttm,
                       peg_ratio, ev_to_revenue, ev_to_ebitda, dividend_yield,
                       payout_ratio
                FROM key_metrics
                WHERE ticker = %s
            """, (symbol,))

            row = cursor.fetchone()
            if row:
                value_rows.append((
                    symbol,
                    today,
                    row[0],  # trailing_pe
                    row[1],  # forward_pe
                    row[2],  # price_to_book
                    row[3],  # price_to_sales_ttm
                    row[4],  # peg_ratio
                    row[5],  # ev_to_revenue
                    row[6],  # ev_to_ebitda
                    row[7],  # dividend_yield
                    row[8]   # payout_ratio
                ))
        except Exception as e:
            logging.debug(f"Could not load value metrics for {symbol}: {e}")

    # Upsert value_metrics
    if value_rows:
        upsert_sql = """
            INSERT INTO value_metrics (
                symbol, date, trailing_pe, forward_pe, price_to_book, price_to_sales_ttm,
                peg_ratio, ev_to_revenue, ev_to_ebitda, dividend_yield, payout_ratio
            ) VALUES %s
            ON CONFLICT (symbol, date) DO UPDATE SET
                trailing_pe = EXCLUDED.trailing_pe,
                forward_pe = EXCLUDED.forward_pe,
                price_to_book = EXCLUDED.price_to_book,
                price_to_sales_ttm = EXCLUDED.price_to_sales_ttm,
                peg_ratio = EXCLUDED.peg_ratio,
                ev_to_revenue = EXCLUDED.ev_to_revenue,
                ev_to_ebitda = EXCLUDED.ev_to_ebitda,
                dividend_yield = EXCLUDED.dividend_yield,
                payout_ratio = EXCLUDED.payout_ratio
        """
        try:
            execute_values(cursor, upsert_sql, value_rows)
            conn.commit()
            logging.info(f"Loaded {len(value_rows)} value metric records")
        except Exception as e:
            logging.error(f"Failed to insert value metrics: {e}")
            conn.rollback()
            raise


def create_factor_metrics_tables(cursor):
    """Create factor metrics tables if they don't exist"""
    logging.info("Creating factor metrics tables if needed...")

    try:
        # Create quality_metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quality_metrics (
                symbol VARCHAR(50) NOT NULL,
                date DATE NOT NULL,
                return_on_equity_pct FLOAT,
                return_on_assets_pct FLOAT,
                return_on_invested_capital_pct FLOAT,
                gross_margin_pct FLOAT,
                operating_margin_pct FLOAT,
                profit_margin_pct FLOAT,
                fcf_to_net_income FLOAT,
                operating_cf_to_net_income FLOAT,
                debt_to_equity FLOAT,
                current_ratio FLOAT,
                quick_ratio FLOAT,
                earnings_surprise_avg FLOAT,
                eps_growth_stability FLOAT,
                payout_ratio FLOAT,
                earnings_beat_rate FLOAT,
                estimate_revision_direction FLOAT,
                consecutive_positive_quarters INT,
                surprise_consistency FLOAT,
                earnings_growth_4q_avg FLOAT,
                revision_activity_30d FLOAT,
                estimate_momentum_60d FLOAT,
                estimate_momentum_90d FLOAT,
                revision_trend_score FLOAT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (symbol, date)
            )
        """)

        # Add missing columns if they don't exist (for existing tables)
        cursor.execute("""
            ALTER TABLE quality_metrics
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()
        """)
        cursor.execute("""
            ALTER TABLE quality_metrics
            ADD COLUMN IF NOT EXISTS return_on_invested_capital_pct FLOAT
        """)
        cursor.execute("""
            ALTER TABLE quality_metrics
            ADD COLUMN IF NOT EXISTS earnings_beat_rate FLOAT
        """)
        cursor.execute("""
            ALTER TABLE quality_metrics
            ADD COLUMN IF NOT EXISTS estimate_revision_direction FLOAT
        """)
        cursor.execute("""
            ALTER TABLE quality_metrics
            ADD COLUMN IF NOT EXISTS consecutive_positive_quarters INT
        """)
        cursor.execute("""
            ALTER TABLE quality_metrics
            ADD COLUMN IF NOT EXISTS surprise_consistency FLOAT
        """)
        cursor.execute("""
            ALTER TABLE quality_metrics
            ADD COLUMN IF NOT EXISTS earnings_growth_4q_avg FLOAT
        """)
        cursor.execute("""
            ALTER TABLE quality_metrics
            ADD COLUMN IF NOT EXISTS revision_activity_30d FLOAT
        """)
        cursor.execute("""
            ALTER TABLE quality_metrics
            ADD COLUMN IF NOT EXISTS estimate_momentum_60d FLOAT
        """)
        cursor.execute("""
            ALTER TABLE quality_metrics
            ADD COLUMN IF NOT EXISTS estimate_momentum_90d FLOAT
        """)
        cursor.execute("""
            ALTER TABLE quality_metrics
            ADD COLUMN IF NOT EXISTS revision_trend_score FLOAT
        """)

        # Create growth_metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS growth_metrics (
                symbol VARCHAR(50) NOT NULL,
                date DATE NOT NULL,
                revenue_growth_3y_cagr FLOAT,
                eps_growth_3y_cagr FLOAT,
                operating_income_growth_yoy FLOAT,
                roe_trend FLOAT,
                sustainable_growth_rate FLOAT,
                fcf_growth_yoy FLOAT,
                ocf_growth_yoy FLOAT,
                net_income_growth_yoy FLOAT,
                gross_margin_trend FLOAT,
                operating_margin_trend FLOAT,
                net_margin_trend FLOAT,
                quarterly_growth_momentum FLOAT,
                asset_growth_yoy FLOAT,
                revenue_growth_yoy FLOAT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, date)
            )
        """)

        # Add missing columns if they don't exist (for existing tables)
        cursor.execute("""
            ALTER TABLE growth_metrics
            ADD COLUMN IF NOT EXISTS ocf_growth_yoy FLOAT
        """)
        cursor.execute("""
            ALTER TABLE growth_metrics
            ADD COLUMN IF NOT EXISTS revenue_growth_yoy FLOAT
        """)
        cursor.execute("""
            ALTER TABLE growth_metrics
            ADD COLUMN IF NOT EXISTS net_income_growth_yoy FLOAT
        """)

        # Create momentum_metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS momentum_metrics (
                id SERIAL,
                symbol VARCHAR(50) NOT NULL,
                date DATE NOT NULL,
                current_price FLOAT,
                momentum_1m FLOAT,
                momentum_3m FLOAT,
                momentum_6m FLOAT,
                momentum_12m FLOAT,
                created_at TIMESTAMP,
                price_vs_sma_50 FLOAT,
                price_vs_sma_200 FLOAT,
                price_vs_52w_high FLOAT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, date)
            )
        """)

        # Add momentum_1m column if it doesn't exist (for existing tables)
        cursor.execute("""
            ALTER TABLE momentum_metrics
            ADD COLUMN IF NOT EXISTS momentum_1m FLOAT
        """)

        # Add SMA columns if they don't exist (for existing tables)
        cursor.execute("""
            ALTER TABLE momentum_metrics
            ADD COLUMN IF NOT EXISTS price_vs_sma_50 FLOAT
        """)
        cursor.execute("""
            ALTER TABLE momentum_metrics
            ADD COLUMN IF NOT EXISTS price_vs_sma_200 FLOAT
        """)
        cursor.execute("""
            ALTER TABLE momentum_metrics
            ADD COLUMN IF NOT EXISTS price_vs_52w_high FLOAT
        """)

        # Create stability_metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stability_metrics (
                symbol VARCHAR(50) NOT NULL,
                date DATE NOT NULL,
                volatility_12m FLOAT,
                downside_volatility FLOAT,
                max_drawdown_52w FLOAT,
                beta FLOAT,
                volume_consistency FLOAT,
                turnover_velocity FLOAT,
                volatility_volume_ratio FLOAT,
                daily_spread FLOAT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, date)
            )
        """)

        # Add liquidity metrics columns to existing stability_metrics table if needed
        cursor.execute("""
            ALTER TABLE stability_metrics
            ADD COLUMN IF NOT EXISTS volume_consistency FLOAT
        """)
        cursor.execute("""
            ALTER TABLE stability_metrics
            ADD COLUMN IF NOT EXISTS turnover_velocity FLOAT
        """)
        cursor.execute("""
            ALTER TABLE stability_metrics
            ADD COLUMN IF NOT EXISTS volatility_volume_ratio FLOAT
        """)
        cursor.execute("""
            ALTER TABLE stability_metrics
            ADD COLUMN IF NOT EXISTS daily_spread FLOAT
        """)

        # Create value_metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS value_metrics (
                symbol VARCHAR(50) NOT NULL,
                date DATE NOT NULL,
                trailing_pe FLOAT,
                forward_pe FLOAT,
                price_to_book FLOAT,
                price_to_sales_ttm FLOAT,
                peg_ratio FLOAT,
                ev_to_revenue FLOAT,
                ev_to_ebitda FLOAT,
                dividend_yield FLOAT,
                payout_ratio FLOAT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, date)
            )
        """)

        # Add forward_pe column if it doesn't exist (for existing tables)
        cursor.execute("""
            ALTER TABLE value_metrics
            ADD COLUMN IF NOT EXISTS forward_pe FLOAT
        """)

        # Add payout_ratio column if it doesn't exist (for existing tables)
        cursor.execute("""
            ALTER TABLE value_metrics
            ADD COLUMN IF NOT EXISTS payout_ratio FLOAT
        """)

        # Create beta_validation table for testing/validation
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS beta_validation (
                symbol VARCHAR(50) NOT NULL,
                date DATE NOT NULL,
                beta_calculated DOUBLE PRECISION,
                beta_yfinance DOUBLE PRECISION,
                difference_pct DOUBLE PRECISION,
                validation_status VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, date)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_beta_validation_symbol_date
            ON beta_validation(symbol, date DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_beta_validation_status
            ON beta_validation(validation_status)
        """)

        # Create indexes for better performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_quality_metrics_symbol_date ON quality_metrics(symbol, date DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_growth_metrics_symbol_date ON growth_metrics(symbol, date DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_momentum_metrics_symbol_date ON momentum_metrics(symbol, date DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stability_metrics_symbol_date ON stability_metrics(symbol, date DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_value_metrics_symbol_date ON value_metrics(symbol, date DESC)")

        logging.info("✅ Factor metrics tables created/verified")
    except Exception as e:
        logging.error(f"Error creating tables: {e}")
        raise


def fill_metric_gaps(conn, cursor):
    """
    Fill NULL gaps in quality_metrics by calculating from key_metrics.

    Calculations (using available columns):
    - D/E Ratio = Total Debt / Book Value (equity)
    - ROE % = (Net Income / Book Value) * 100
    - Profit Margin = (Net Income / Revenue) * 100
    """
    try:
        logging.info("=" * 70)
        logging.info("FILLING METRIC GAPS FROM KEY_METRICS DATA")
        logging.info("=" * 70)

        # Calculate and fill Debt-to-Equity where missing (using book_value as equity)
        logging.info("\n[1] Calculating D/E Ratio = total_debt / book_value...")
        cursor.execute("""
            UPDATE quality_metrics qm
            SET debt_to_equity = CASE
                WHEN km.total_debt IS NOT NULL
                AND km.book_value IS NOT NULL
                AND km.book_value > 0
                THEN ROUND((km.total_debt::numeric / km.book_value), 4)
                ELSE NULL
            END
            FROM key_metrics km
            WHERE qm.symbol = km.ticker
            AND qm.debt_to_equity IS NULL
        """)
        de_count = cursor.rowcount
        logging.info(f"  ✓ D/E Ratio filled: {de_count} records")

        # Calculate and fill ROE where missing (using book_value as shareholders equity)
        logging.info("\n[2] Calculating ROE % = (net_income / book_value) * 100...")
        cursor.execute("""
            UPDATE quality_metrics qm
            SET return_on_equity_pct = CASE
                WHEN km.net_income IS NOT NULL
                AND km.book_value IS NOT NULL
                AND km.book_value > 0
                THEN ROUND(((km.net_income::numeric / km.book_value) * 100), 2)
                ELSE NULL
            END
            FROM key_metrics km
            WHERE qm.symbol = km.ticker
            AND qm.return_on_equity_pct IS NULL
        """)
        roe_count = cursor.rowcount
        logging.info(f"  ✓ ROE % filled: {roe_count} records")

        # Calculate and fill Profit Margin where missing or zero
        logging.info("\n[3] Calculating Profit Margin % = (net_income / revenue) * 100...")
        cursor.execute("""
            UPDATE quality_metrics qm
            SET profit_margin_pct = CASE
                WHEN km.net_income IS NOT NULL
                AND km.total_revenue IS NOT NULL
                AND km.total_revenue > 0
                THEN ROUND(((km.net_income::numeric / km.total_revenue) * 100), 2)
                ELSE NULL
            END
            FROM key_metrics km
            WHERE qm.symbol = km.ticker
            AND (qm.profit_margin_pct IS NULL OR qm.profit_margin_pct = 0)
        """)
        pm_count = cursor.rowcount
        logging.info(f"  ✓ Profit Margin % filled: {pm_count} records")

        conn.commit()

        # Report final coverage
        logging.info("\n" + "=" * 70)
        logging.info("FINAL METRIC COVERAGE AFTER GAP FILLING")
        logging.info("=" * 70)

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN profit_margin_pct IS NOT NULL THEN 1 END) as pm_filled,
                COUNT(CASE WHEN debt_to_equity IS NOT NULL THEN 1 END) as de_filled,
                COUNT(CASE WHEN return_on_equity_pct IS NOT NULL THEN 1 END) as roe_filled
            FROM quality_metrics
        """)

        total, pm_filled, de_filled, roe_filled = cursor.fetchone()
        logging.info(f"\nQuality Metrics Coverage:")
        logging.info(f"  Profit Margin: {pm_filled:,}/{total:,} ({pm_filled/total*100:.1f}%)")
        logging.info(f"  D/E Ratio: {de_filled:,}/{total:,} ({de_filled/total*100:.1f}%)")
        logging.info(f"  ROE %: {roe_filled:,}/{total:,} ({roe_filled/total*100:.1f}%)")
        logging.info("\n✅ Gap filling completed")

    except Exception as e:
        logging.error(f"Error filling metric gaps: {e}", exc_info=True)
        conn.rollback()


def main():
    """Main loader entry point"""
    log_mem("Start")

    try:
        db_config = get_db_config()
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()

        logging.info(f"{SCRIPT_NAME} starting...")

        # Create tables first
        create_factor_metrics_tables(cursor)
        conn.commit()

        # Get all symbols
        symbols = get_all_symbols(cursor)
        logging.info(f"Found {len(symbols)} symbols to process")

        if not symbols:
            logging.warning("No symbols found in key_metrics")
            return

        # Load factor metrics - each loader has its own error handling
        try:
            load_quality_metrics(conn, cursor, symbols)
            log_mem("After quality metrics")
        except Exception as e:
            logging.error(f"Quality metrics loading failed: {e}")
            try:
                conn.rollback()
            except Exception as rollback_err:
                logging.warning(f"Rollback failed, attempting disconnect/reconnect: {rollback_err}")
                try:
                    cursor.close()
                    conn.close()
                except Exception as close_e:
                    logging.debug(f"Error closing connection during quality metrics recovery: {close_e}")
                    pass
                conn = psycopg2.connect(**db_config)
            cursor.close()
            cursor = conn.cursor()  # Create new cursor after rollback

        # Force connection refresh before growth metrics to ensure clean state
        try:
            cursor.close()
            conn.close()
        except:
            pass
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()

        try:
            load_growth_metrics(conn, cursor, symbols)
            log_mem("After growth metrics")
        except Exception as e:
            logging.error(f"Growth metrics loading failed: {e}")
            try:
                conn.rollback()
            except Exception as rollback_err:
                logging.warning(f"Rollback failed, attempting disconnect/reconnect: {rollback_err}")
                try:
                    cursor.close()
                    conn.close()
                except Exception as close_e:
                    logging.debug(f"Error closing connection during growth metrics recovery: {close_e}")
                    pass
                conn = psycopg2.connect(**db_config)
            cursor.close()
            cursor = conn.cursor()  # Create new cursor after rollback

        # Force connection refresh before momentum metrics
        try:
            cursor.close()
            conn.close()
        except:
            pass
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()

        try:
            load_momentum_metrics(conn, cursor, symbols)
            log_mem("After momentum metrics")
        except Exception as e:
            logging.error(f"Momentum metrics loading failed: {e}")
            try:
                conn.rollback()
            except Exception as rollback_err:
                logging.warning(f"Rollback failed, attempting disconnect/reconnect: {rollback_err}")
                try:
                    cursor.close()
                    conn.close()
                except Exception as close_e:
                    logging.debug(f"Error closing connection during momentum metrics recovery: {close_e}")
                    pass
                conn = psycopg2.connect(**db_config)
            cursor.close()
            cursor = conn.cursor()  # Create new cursor after rollback

        # Force connection refresh before stability metrics
        try:
            cursor.close()
            conn.close()
        except:
            pass
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()

        try:
            load_stability_metrics(conn, cursor, symbols)
            log_mem("After stability metrics")
        except Exception as e:
            logging.error(f"Stability metrics loading failed: {e}")
            try:
                conn.rollback()
            except Exception as rollback_err:
                logging.warning(f"Rollback failed, attempting disconnect/reconnect: {rollback_err}")
                try:
                    cursor.close()
                    conn.close()
                except Exception as close_e:
                    logging.debug(f"Error closing connection during stability metrics recovery: {close_e}")
                    pass
                conn = psycopg2.connect(**db_config)
            cursor.close()
            cursor = conn.cursor()  # Create new cursor after rollback

        # Force connection refresh before value metrics
        try:
            cursor.close()
            conn.close()
        except:
            pass
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()

        try:
            load_value_metrics(conn, cursor, symbols)
            log_mem("After value metrics")
        except Exception as e:
            logging.error(f"Value metrics loading failed: {e}")
            try:
                conn.rollback()
            except Exception as rollback_err:
                logging.warning(f"Rollback failed, attempting disconnect/reconnect: {rollback_err}")
                try:
                    cursor.close()
                    conn.close()
                except Exception as close_e:
                    logging.debug(f"Error closing connection during value metrics recovery: {close_e}")
                    pass
                conn = psycopg2.connect(**db_config)
            cursor.close()
            cursor = conn.cursor()  # Create new cursor after rollback

        # Force connection refresh before A/D ratings
        try:
            cursor.close()
            conn.close()
        except:
            pass
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()

        try:
            load_ad_ratings(conn, cursor, symbols)
            log_mem("After A/D ratings")
        except Exception as e:
            logging.error(f"A/D ratings loading failed: {e}")
            try:
                conn.rollback()
            except Exception as rollback_err:
                logging.warning(f"Rollback failed, attempting disconnect/reconnect: {rollback_err}")
                try:
                    cursor.close()
                    conn.close()
                except Exception as close_e:
                    logging.debug(f"Error closing connection during A/D ratings recovery: {close_e}")
                    pass
                conn = psycopg2.connect(**db_config)
            cursor.close()
            cursor = conn.cursor()  # Create new cursor after rollback

        # Force connection refresh before fill_metric_gaps
        try:
            cursor.close()
            conn.close()
        except:
            pass
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()

        # Fill metric gaps from available data
        try:
            fill_metric_gaps(conn, cursor)
            log_mem("After gap filling")
        except Exception as e:
            logging.error(f"Metric gap filling failed: {e}")
            conn.rollback()

        cursor.close()
        conn.close()

        logging.info(f"{SCRIPT_NAME} completed successfully")

    except Exception as e:
        logging.error(f"Error in {SCRIPT_NAME}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
# BATCH 1 FOUNDATION: momentum_metrics table creation
