#!/usr/bin/env python3
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

Author: Financial Dashboard System
Updated: 2025-11-17
Trigger: 20251227-120600-AWS-ECS - Load factor metrics derived from key metrics
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


def get_db_config():
    """Get database configuration - works in AWS and locally"""
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn:
        secret_str = boto3.client("secretsmanager").get_secret_value(
            SecretId=db_secret_arn
        )["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": sec["port"],
            "user": sec["username"],
            "password": sec["password"],
            "database": sec["dbname"],
        }

    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", 5432),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", "bed0elAn"),
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

    # Calculate FCF to Net Income ratio (only if both values exist)
    if ticker_data.get("free_cashflow") and ticker_data.get("net_income"):
        if ticker_data["net_income"] != 0:
            metrics["fcf_to_net_income"] = (
                ticker_data["free_cashflow"] / ticker_data["net_income"]
            )

    # Calculate Operating CF to Net Income ratio (only if both values exist)
    if ticker_data.get("operating_cashflow") and ticker_data.get("net_income"):
        if ticker_data["net_income"] != 0:
            metrics["operating_cf_to_net_income"] = (
                ticker_data["operating_cashflow"] / ticker_data["net_income"]
            )

    # ENHANCED: Calculate ROIC with fallback logic
    # Primary: ROIC = EBITDA / (Total Debt + Total Cash)
    # Fallback: ROIC = Operating Income / (Total Debt + Total Cash) if EBITDA missing
    # Fallback: ROIC = Net Income / (Total Debt + Total Cash) if operating income missing

    ebitda = ticker_data.get("ebitda")
    operating_income = ticker_data.get("operating_income")
    net_income = ticker_data.get("net_income")
    total_debt = ticker_data.get("total_debt")
    total_cash = ticker_data.get("total_cash")

    # CRITICAL: Require real capital data - do not synthesize $0 invested capital
    # Both debt and cash values must be available (not None) to calculate invested capital
    if total_debt is not None and total_cash is not None:
        invested_capital = total_debt + total_cash

        # Only calculate ROIC if invested capital is positive (real data)
        if invested_capital > 0:
            roic_value = None
            roic_source = None

            # Try EBITDA first (primary calculation)
            if ebitda and ebitda > 0:
                roic_value = ebitda / invested_capital
                roic_source = "EBITDA"

            # Fallback to Operating Income if EBITDA missing
            elif operating_income and operating_income > 0:
                roic_value = operating_income / invested_capital
                roic_source = "OPERATING_INCOME"
                logging.debug(f"ROIC calculated from Operating Income for {symbol}")

            # Fallback to Net Income if operating income missing
            elif net_income and net_income > 0:
                roic_value = net_income / invested_capital
                roic_source = "NET_INCOME"
                logging.debug(f"ROIC calculated from Net Income for {symbol}")

            if roic_value is not None:
                # Convert from decimal to percentage and clamp to realistic range
                roic_pct = roic_value * 100
                metrics["return_on_invested_capital_pct"] = max(-100, min(roic_pct, 200))
                if roic_source and roic_source != "EBITDA":
                    metrics["roic_source"] = roic_source
        # If invested capital is 0 or negative, ROIC cannot be calculated - return None
    # If debt and cash both missing, ROIC cannot be calculated - return None (no fake values)

    # NOTE: earnings_surprise_avg and eps_growth_stability are calculated separately by calculate_earnings_surprise.py
    # which queries quarterly_income_statement table for real earnings data, not yfinance API calls
    # This avoids rate limiting issues when processing 5000+ symbols

    return metrics


def calculate_roe_stability_index(cursor, symbol: str, conn=None) -> Optional[float]:
    """Calculate ROE Stability Index from 4 years of annual ROE data

    Formula: ROE_Stability = (% of years with positive ROE) × (1 - ROE volatility)

    This metric captures:
    - roe_consistency: What % of years had positive ROE?
    - roe_volatility: How stable was ROE across years?

    Result: 0-100 score where higher = more stable positive ROE
    """
    try:
        # Use separate cursor to avoid transaction conflicts
        temp_cur = conn.cursor() if conn else cursor

        # Get ROE from last 4 fiscal years (from key_metrics historical data)
        # We calculate ROE from annual statements: Net Income / Shareholders Equity
        temp_cur.execute("""
            SELECT net_income, total_assets, total_liabilities
            FROM annual_balance_sheet
            WHERE symbol = %s
            ORDER BY fiscal_year DESC
            LIMIT 4
        """, (symbol,))

        annual_data = temp_cur.fetchall()

        # Close temp cursor if it was a separate one
        if conn and temp_cur != cursor:
            temp_cur.close()

        if not annual_data or len(annual_data) < 2:
            return None

        # Calculate ROE for each year: Net Income / Shareholders Equity
        # Shareholders Equity = Total Assets - Total Liabilities
        roe_values = []

        for row in annual_data:
            net_income = row[0]
            total_assets = row[1]
            total_liabilities = row[2]

            if net_income is not None and total_assets is not None and total_liabilities is not None:
                equity = total_assets - total_liabilities
                if equity > 0:  # Only calculate if equity is positive
                    roe = (net_income / equity) * 100
                    roe_values.append(roe)

        if not roe_values or len(roe_values) < 2:
            return None

        # Calculate % of years with positive ROE
        positive_years = sum(1 for roe in roe_values if roe > 0)
        pct_positive = positive_years / len(roe_values)

        # Calculate ROE volatility (coefficient of variation)
        roe_mean = sum(roe_values) / len(roe_values)
        if roe_mean == 0:
            return None

        variance = sum((roe - roe_mean) ** 2 for roe in roe_values) / len(roe_values)
        std_dev = variance ** 0.5

        # Coefficient of variation (normalized volatility)
        # Use absolute mean to handle negative averages
        cv = std_dev / abs(roe_mean) if roe_mean != 0 else 0

        # Cap CV at 2.0 to prevent extreme values (volatility > 200% = very unstable)
        cv_capped = min(cv, 2.0)
        volatility_factor = cv_capped / 2.0  # Normalize to 0-1 range

        # ROE Stability Index = consistency × (1 - volatility)
        roe_stability = pct_positive * (1 - volatility_factor) * 100

        return max(0, min(100, roe_stability))  # Clamp to 0-100

    except Exception as e:
        logging.debug(f"Error calculating ROE stability for {symbol}: {e}")
        return None


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
            SELECT date,
                   revenue,
                   net_income,
                   operating_income
            FROM quarterly_income_statement
            WHERE symbol = %s
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
                    except (TypeError, ValueError, ZeroDivisionError):
                        pass

                # Calculate YoY net income growth
                if prior_ni and recent_ni and prior_ni != 0:
                    try:
                        metrics["net_income_growth_quarterly_yoy"] = ((recent_ni - prior_ni) / abs(prior_ni) * 100)
                    except (TypeError, ValueError, ZeroDivisionError):
                        pass

                # Calculate YoY operating income growth
                if prior_oi and recent_oi and prior_oi != 0:
                    try:
                        metrics["operating_income_growth_quarterly_yoy"] = ((recent_oi - prior_oi) / abs(prior_oi) * 100)
                    except (TypeError, ValueError, ZeroDivisionError):
                        pass

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
            # Use actual EPS if available, fallback to estimate
            recent_eps = None
            prior_eps = None

            if earnings_data[0][1] is not None:
                recent_eps = float(earnings_data[0][1])
            elif earnings_data[0][2] is not None:
                recent_eps = float(earnings_data[0][2])

            if len(earnings_data) >= 2:
                if earnings_data[1][1] is not None:
                    prior_eps = float(earnings_data[1][1])
                elif earnings_data[1][2] is not None:
                    prior_eps = float(earnings_data[1][2])

            # Calculate QoQ EPS growth as proxy metric when YoY unavailable
            if recent_eps is not None and prior_eps is not None and prior_eps != 0:
                try:
                    qoq_growth = ((recent_eps - prior_eps) / abs(prior_eps)) * 100
                    # Store as annual equivalent (multiply by 4 for rough estimate)
                    metrics["eps_growth_1y"] = qoq_growth * 4
                except (TypeError, ValueError, ZeroDivisionError):
                    pass

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
        # Note: annual_income_statement has columns: symbol, date, revenue, operating_income, pretax_income, net_income
        cursor.execute("""
            SELECT date, revenue, operating_income, net_income
            FROM annual_income_statement
            WHERE symbol = %s AND revenue IS NOT NULL
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
            # Only set if both current and previous values are valid
            if prev_revenue and recent_revenue:
                if prev_revenue > 0:
                    try:
                        metrics["revenue_growth_yoy"] = ((recent_revenue - prev_revenue) / prev_revenue * 100)
                        logging.debug(f"DEBUG {symbol} revenue_growth_yoy: {metrics['revenue_growth_yoy']}")
                    except (TypeError, ValueError, ZeroDivisionError):
                        logging.debug(f"DEBUG {symbol} revenue_growth_yoy exception: prev={prev_revenue}, recent={recent_revenue}")
                        pass
            else:
                logging.debug(f"DEBUG {symbol} skipped revenue_growth_yoy: prev={prev_revenue}, recent={recent_revenue}")

            # Operating Income Growth: Allow any valid numeric comparison (including negative base)
            # Company going from -$10M to -$5M to +$2M shows recovery progression
            if prev_oi is not None and recent_oi is not None:
                if prev_oi != 0:
                    try:
                        metrics["operating_income_growth_yoy"] = ((recent_oi - prev_oi) / abs(prev_oi) * 100)
                    except (TypeError, ValueError, ZeroDivisionError):
                        pass

            # Net Income Growth: Allow any valid numeric comparison (including negative base)
            # Company going profitable shows real growth, even from loss position
            if prev_ni is not None and recent_ni is not None:
                if prev_ni != 0:
                    try:
                        metrics["net_income_growth_yoy"] = ((recent_ni - prev_ni) / abs(prev_ni) * 100)
                    except (TypeError, ValueError, ZeroDivisionError):
                        pass

            # Calculate 3-year CAGR if we have 4 years of data
            if len(income_data) >= 4:
                oldest_date, oldest_revenue, oldest_oi, oldest_ni = income_data[3]

                # Revenue CAGR: Only calculate when both oldest and recent are positive
                # CAGR requires starting from a positive base value
                if oldest_revenue and oldest_revenue > 0 and recent_revenue and recent_revenue > 0:
                    metrics["revenue_growth_3y_cagr"] = calculate_cagr(oldest_revenue, recent_revenue, 3)

                # EPS CAGR: Calculate when recent is profitable (positive), regardless of historical path
                # Company that became profitable after losses is a real growth case
                if recent_ni is not None and recent_ni > 0 and oldest_ni is not None and oldest_ni > 0:
                    metrics["eps_growth_3y_cagr"] = calculate_cagr(oldest_ni, recent_ni, 3)

            # If 4-year CAGR not available, try 2-year growth as fallback for EPS
            elif len(income_data) >= 2 and metrics["eps_growth_3y_cagr"] is None:
                # Use YoY calculation as proxy when full CAGR unavailable
                # This ensures we capture companies with 2-year positive earnings
                pass  # Already calculated above in YoY section

        # Get annual cashflow data for FCF growth (4 years available, use first 2)
        # Note: annual_cash_flow has columns: symbol, date, operating_cash_flow, free_cash_flow, etc.
        cursor.execute("""
            SELECT date, free_cash_flow
            FROM annual_cash_flow
            WHERE symbol = %s AND free_cash_flow IS NOT NULL
            ORDER BY date DESC
            LIMIT 4
        """, (symbol,))

        cf_data = cursor.fetchall()
        if len(cf_data) >= 2:
            recent_fcf = cf_data[0][1] if cf_data[0] else None
            prev_fcf = cf_data[1][1] if cf_data[1] else None
            # Allow growth from negative FCF to positive (company improving cash generation)
            # Or from positive to positive (normal growth)
            if recent_fcf is not None and prev_fcf is not None and prev_fcf != 0:
                try:
                    metrics["fcf_growth_yoy"] = ((recent_fcf - prev_fcf) / abs(prev_fcf) * 100)
                except (TypeError, ValueError, ZeroDivisionError):
                    pass

        # Get annual cashflow data for OCF growth
        # Note: annual_cash_flow has columns: symbol, date, operating_cash_flow, free_cash_flow, etc.
        cursor.execute("""
            SELECT date, operating_cash_flow
            FROM annual_cash_flow
            WHERE symbol = %s AND operating_cash_flow IS NOT NULL
            ORDER BY date DESC
            LIMIT 4
        """, (symbol,))

        ocf_data = cursor.fetchall()
        if len(ocf_data) >= 2:
            recent_ocf = ocf_data[0][1] if ocf_data[0] else None
            prev_ocf = ocf_data[1][1] if ocf_data[1] else None
            # Allow growth from negative OCF to positive (company improving operations)
            # Or from positive to positive (normal growth)
            if recent_ocf is not None and prev_ocf is not None and prev_ocf != 0:
                try:
                    metrics["ocf_growth_yoy"] = ((recent_ocf - prev_ocf) / abs(prev_ocf) * 100)
                except (TypeError, ValueError, ZeroDivisionError):
                    pass

        # Get annual balance sheet data for asset growth
        # Note: annual_balance_sheet has columns: symbol, date, total_assets, total_liabilities, total_equity
        try:
            cursor.execute("""
                SELECT date, total_assets
                FROM annual_balance_sheet
                WHERE symbol = %s AND total_assets IS NOT NULL
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
                        except (TypeError, ValueError, ZeroDivisionError):
                            pass
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
                    except (TypeError, ValueError):
                        pass

            if growth_rates and len(growth_rates) >= 2:
                try:
                    mean_growth = float(np.mean(growth_rates))
                    std_growth = float(np.std(growth_rates))

                    if mean_growth != 0:
                        metrics["eps_growth_stability"] = float(std_growth / abs(mean_growth))
                    else:
                        metrics["eps_growth_stability"] = float(std_growth)
                except (TypeError, ValueError):
                    pass

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
                    except (TypeError, ValueError):
                        pass

            if surprises:
                try:
                    metrics["earnings_surprise_avg"] = float(np.mean(surprises))
                except (TypeError, ValueError):
                    pass

    except Exception as e:
        logging.debug(f"Could not calculate earnings surprise for {symbol}: {e}")

    return metrics


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


def calculate_growth_metrics(ticker_data: Dict, financial_growth: Dict = None, quarterly_growth: Dict = None, earnings_history_growth: Dict = None) -> Dict:
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

    # Use quarterly data as secondary source (more current when annual unavailable)
    if quarterly_growth:
        # Revenue growth: prefer annual, use quarterly as fallback
        if "revenue_growth_3y_cagr" not in metrics or metrics["revenue_growth_3y_cagr"] is None:
            if quarterly_growth.get("revenue_growth_quarterly_yoy") is not None:
                metrics["revenue_growth_3y_cagr"] = quarterly_growth.get("revenue_growth_quarterly_yoy")

        # Net income growth: prefer annual, use quarterly as fallback
        if "net_income_growth_yoy" not in metrics or metrics["net_income_growth_yoy"] is None:
            if quarterly_growth.get("net_income_growth_quarterly_yoy") is not None:
                metrics["net_income_growth_yoy"] = quarterly_growth.get("net_income_growth_quarterly_yoy")

        # Operating income growth: prefer annual, use quarterly as fallback
        if "operating_income_growth_yoy" not in metrics or metrics["operating_income_growth_yoy"] is None:
            if quarterly_growth.get("operating_income_growth_quarterly_yoy") is not None:
                metrics["operating_income_growth_yoy"] = quarterly_growth.get("operating_income_growth_quarterly_yoy")

    # Use earnings history growth as tertiary fallback for EPS metrics
    if earnings_history_growth:
        if "eps_growth_3y_cagr" not in metrics or metrics["eps_growth_3y_cagr"] is None:
            if earnings_history_growth.get("eps_growth_1y") is not None:
                # Use 1-year growth as proxy when 3-year CAGR unavailable
                metrics["eps_growth_3y_cagr"] = earnings_history_growth.get("eps_growth_1y")

    # Use available growth percentages from key_metrics (as fallback or supplement)
    # key_metrics provides alternative data sources for better coverage
    if "revenue_growth_pct" in ticker_data and ticker_data.get("revenue_growth_pct") is not None:
        # Only set if we don't already have from financial statements
        if "revenue_growth_3y_cagr" not in metrics or metrics["revenue_growth_3y_cagr"] is None:
            metrics["revenue_growth_3y_cagr"] = ticker_data.get("revenue_growth_pct")

    if "earnings_growth_pct" in ticker_data and ticker_data.get("earnings_growth_pct") is not None:
        # Only set if we don't already have from financial statements or earnings history
        if "eps_growth_3y_cagr" not in metrics or metrics["eps_growth_3y_cagr"] is None:
            metrics["eps_growth_3y_cagr"] = ticker_data.get("earnings_growth_pct")

    # Fallback: Calculate EPS growth from forward vs trailing EPS
    if (not metrics.get("eps_growth_3y_cagr")) and ticker_data.get("eps_forward") and ticker_data.get("eps_trailing"):
        try:
            eps_forward = float(ticker_data.get("eps_forward"))
            eps_trailing = float(ticker_data.get("eps_trailing"))
            if eps_trailing > 0:
                eps_growth = ((eps_forward - eps_trailing) / eps_trailing) * 100
                if eps_growth != 0:  # Only set if meaningful
                    metrics["eps_growth_3y_cagr"] = eps_growth
        except (TypeError, ValueError):
            pass

    if "earnings_q_growth_pct" in ticker_data and ticker_data.get("earnings_q_growth_pct"):
        metrics["quarterly_growth_momentum"] = ticker_data.get("earnings_q_growth_pct")

    # Sustainable growth rate = ROE * (1 - Payout Ratio)
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
        except (TypeError, ValueError):
            pass
    elif roe and "sustainable_growth_rate" not in metrics:
        # If we don't have payout ratio, use ROE as sustainable growth estimate
        try:
            roe_f = float(roe) if roe else None
            if roe_f:
                # Normalize to decimal form, apply 0.6 factor, convert to percentage
                roe_decimal = roe_f / 100 if roe_f >= 1 or roe_f <= -1 else roe_f
                metrics["sustainable_growth_rate"] = roe_decimal * 0.6 * 100
        except (TypeError, ValueError):
            pass

    # Margin trend proxies - use current values from key_metrics when financial data unavailable
    # These represent the current state of margins rather than historical trends
    # Normalize to percentage form using normalize_percentage function (handles both formats)
    if "gross_margin_trend" not in metrics or metrics["gross_margin_trend"] is None:
        gm_val = ticker_data.get("gross_margin_pct")
        if gm_val:
            metrics["gross_margin_trend"] = normalize_percentage(gm_val)

    if "operating_margin_trend" not in metrics or metrics["operating_margin_trend"] is None:
        opm_val = ticker_data.get("operating_margin_pct")
        if opm_val:
            metrics["operating_margin_trend"] = normalize_percentage(opm_val)

    if "net_margin_trend" not in metrics or metrics["net_margin_trend"] is None:
        pm_val = ticker_data.get("profit_margin_pct")
        if pm_val:
            metrics["net_margin_trend"] = normalize_percentage(pm_val)

    # ROE trend - use current ROE value when financial trend data unavailable
    # Normalize to percentage form using normalize_percentage function
    if "roe_trend" not in metrics or metrics["roe_trend"] is None:
        roe_val = ticker_data.get("return_on_equity_pct")
        if roe_val:
            metrics["roe_trend"] = normalize_percentage(roe_val)

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
        except (TypeError, ValueError):
            pass

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
        except (TypeError, ValueError):
            pass

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
        except (TypeError, ValueError):
            pass

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
        except (TypeError, ValueError):
            pass

    except Exception as e:
        logging.debug(f"Could not calculate volume metrics for {symbol}: {e}")

    return metrics


def get_stability_metrics(cursor, symbol: str) -> Dict:
    """Calculate stability metrics from price data (volatility, drawdown, beta)"""
    metrics = {
        "volatility_12m": None,
        "downside_volatility": None,
        "max_drawdown_52w": None,
        "beta": None,
    }

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

        # Calculate daily returns
        returns = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0:
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
            except (TypeError, ValueError):
                pass

            # Downside volatility (only negative returns)
            downside_returns = [r for r in returns if r < 0]
            if downside_returns:
                try:
                    downside_vol = (np.std(downside_returns) * np.sqrt(252))
                    if isinstance(downside_vol, complex):
                        downside_vol = downside_vol.real
                    downside_vol_f = float(downside_vol)
                    metrics["downside_volatility"] = downside_vol_f if not np.isnan(downside_vol_f) else None
                except (TypeError, ValueError):
                    pass

        # Max drawdown (52-week window)
        if len(prices) >= 52:
            max_dd = 0
            peak = prices[0]
            for price in prices[-252:]:  # Last 252 trading days ~= 1 year
                if price > peak:
                    peak = price
                dd = ((peak - price) / peak) * 100
                if dd > max_dd:
                    max_dd = dd
            metrics["max_drawdown_52w"] = float(max_dd) if max_dd > 0 else None

        # Beta calculation (vs SPY - market benchmark)
        # Get SPY prices for same period
        cursor.execute("""
            SELECT date, adj_close
            FROM price_daily
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 252
        """, ('SPY',))

        spy_data = cursor.fetchall()
        if len(spy_data) >= 20:
            spy_data = list(reversed(spy_data))
            spy_prices = [p[1] for p in spy_data]

            # Calculate SPY returns (match the period with our stock)
            spy_returns = []
            for i in range(1, min(len(spy_prices), len(prices))):
                if spy_prices[i-1] > 0:
                    spy_ret = ((spy_prices[i] - spy_prices[i-1]) / spy_prices[i-1]) * 100
                    spy_returns.append(spy_ret)

            # Calculate covariance and market variance
            if len(spy_returns) >= 20 and len(returns) >= 20:
                # Use matching period
                min_len = min(len(returns), len(spy_returns))
                stock_ret = returns[-min_len:]
                spy_ret = spy_returns[-min_len:]

                covariance = np.cov(stock_ret, spy_ret)[0][1]
                market_variance = np.var(spy_ret)

                if market_variance > 0:
                    try:
                        beta = covariance / market_variance
                        # Handle complex numbers by taking the real part
                        if isinstance(beta, complex):
                            beta = beta.real
                        beta_f = float(beta)
                        metrics["beta"] = beta_f if not np.isnan(beta_f) else None
                    except (TypeError, ValueError):
                        pass

    except Exception as e:
        logging.error(f"Error calculating stability metrics for {symbol}: {e}")

    return metrics


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

    Analyzes 63 trading days of volume data to determine institutional
    buying/selling patterns:
    - A: 90-100% accumulation volume = Strong Accumulation
    - B: 70-89% accumulation volume = Moderate Accumulation
    - C: 50-69% accumulation volume = Neutral
    - D: 30-49% accumulation volume = Moderate Distribution
    - E: 0-29% accumulation volume = Strong Distribution

    Returns numeric score on 50-100 scale (all positive).
    """
    try:
        # Get last 63+ trading days of price/volume data (13 weeks)
        cursor.execute("""
            SELECT date, close, volume
            FROM price_daily
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 63
        """, (symbol,))

        rows = cursor.fetchall()

        # Need at least 60 days of data
        if len(rows) < 60:
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
        logging.warning(f"Failed to calculate A/D rating for {symbol}: {e}")
        return None


def load_ad_ratings(conn, cursor, symbols: List[str]):
    """Load Accumulation/Distribution ratings for all symbols"""
    logging.info("Loading A/D ratings...")

    ad_rows = []

    for idx, symbol in enumerate(symbols, 1):
        try:
            ad_rating = calculate_accumulation_distribution_rating(cursor, symbol)

            if ad_rating is not None:
                ad_rows.append((ad_rating, symbol))

                # Print progress every 100 symbols
                if idx % 100 == 0:
                    logging.info(f"  ✓ A/D ratings: {idx}/{len(symbols)}")

        except Exception as e:
            logging.warning(f"Failed to calculate A/D for {symbol}: {e}")

    # Update positioning_metrics with A/D ratings
    if ad_rows:
        logging.info(f"Updating {len(ad_rows)} A/D ratings in positioning_metrics...")

        updated_count = 0
        for ad_rating, symbol in ad_rows:
            try:
                cursor.execute("""
                    UPDATE positioning_metrics
                    SET ad_rating = %s, updated_at = NOW()
                    WHERE symbol = %s
                """, (ad_rating, symbol))
                updated_count += 1
            except Exception as e:
                logging.warning(f"Failed to update A/D for {symbol}: {e}")
                # Rollback the bad transaction to recover
                try:
                    conn.rollback()
                except:
                    pass

        try:
            conn.commit()
            logging.info(f"✅ Updated {updated_count} A/D ratings")
        except Exception as e:
            logging.error(f"Failed to commit A/D updates: {e}")
            conn.rollback()


def load_quality_metrics(conn, cursor, symbols: List[str]):
    """Load quality metrics for all symbols"""
    logging.info("Loading quality metrics...")

    # Recover from any previous transaction abort
    try:
        conn.rollback()
    except:
        pass

    quality_rows = []

    # Get all key_metrics data in one query
    cursor.execute(
        "SELECT ticker, return_on_equity_pct, return_on_assets_pct, "
        "gross_margin_pct, operating_margin_pct, profit_margin_pct, "
        "free_cashflow, net_income, operating_cashflow, debt_to_equity, "
        "current_ratio, quick_ratio, payout_ratio, ebitda, total_debt, total_cash, "
        "total_revenue "
        "FROM key_metrics WHERE ticker = ANY(%s)",
        (symbols,)
    )

    for row in cursor.fetchall():
        try:
            symbol = row[0]
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

            # Calculate ROE Stability Index from 4 years of annual data
            roe_stability = calculate_roe_stability_index(cursor, symbol, conn=conn)
            metrics["roe_stability_index"] = roe_stability

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
                metrics.get("debt_to_equity"),
                metrics.get("current_ratio"),
                metrics.get("quick_ratio"),
                metrics.get("earnings_surprise_avg"),
                metrics.get("eps_growth_stability"),
                metrics.get("payout_ratio"),
                metrics.get("roe_stability_index"),
            ])
        except Exception as e:
            logging.warning(f"Error processing quality metrics for {symbol}: {e}")

    # Upsert quality_metrics
    if quality_rows:
        upsert_sql = """
            INSERT INTO quality_metrics (
                symbol, date, return_on_equity_pct, return_on_assets_pct,
                return_on_invested_capital_pct, gross_margin_pct, operating_margin_pct,
                profit_margin_pct, fcf_to_net_income, operating_cf_to_net_income,
                debt_to_equity, current_ratio, quick_ratio, earnings_surprise_avg,
                eps_growth_stability, payout_ratio, roe_stability_index
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
                roe_stability_index = EXCLUDED.roe_stability_index
        """
        try:
            # First, try to recover from any transaction abort from previous steps
            try:
                conn.rollback()
            except:
                pass

            execute_values(cursor, upsert_sql, quality_rows)
            conn.commit()
            logging.info(f"Loaded {len(quality_rows)} quality metric records")
        except Exception as e:
            logging.error(f"Failed to insert quality metrics: {e}")
            try:
                conn.rollback()
            except:
                pass
            # Re-raise so main() can handle and recreate cursor
            raise


def load_growth_metrics(conn, cursor, symbols: List[str]):
    """Load growth metrics for all symbols"""
    # Enhanced error handling to recover from transaction abort states
    logging.info(f"Loading growth metrics for {len(symbols)} symbols...")

    growth_rows = []

    # Get all key_metrics data in one query - include margin and financial data for trend calculations
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

    for row in key_metrics_rows:
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

            # Get growth metrics from multiple sources (priority order)
            financial_growth = get_financial_statement_growth(cursor, ticker)
            quarterly_growth = get_quarterly_statement_growth(cursor, ticker)
            earnings_history_growth = get_earnings_history_growth(cursor, ticker)

            # Calculate metrics combining all available data sources
            metrics = calculate_growth_metrics(ticker_dict, financial_growth, quarterly_growth, earnings_history_growth)
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
        except Exception as e:
            logging.warning(f"Error processing growth metrics for {row[0] if row else 'unknown'}: {e}")
            # Recover transaction state to continue processing other symbols
            try:
                conn.rollback()
            except:
                pass

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
            # Get growth metrics from multiple sources (priority order)
            financial_growth = get_financial_statement_growth(cursor, symbol)
            quarterly_growth = get_quarterly_statement_growth(cursor, symbol)
            earnings_history_growth = get_earnings_history_growth(cursor, symbol)

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
            except:
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
            except:
                pass
            # Don't raise - continue to next step so data isn't completely lost


def load_momentum_metrics(conn, cursor, symbols: List[str]):
    """Load momentum metrics from price_daily database - skip yfinance, use local data only"""
    logging.info("Loading momentum metrics from price_daily table...")

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
    stability_rows = []
    today = date.today()

    for i, symbol in enumerate(symbols, 1):
        try:
            # Get traditional stability metrics (volatility, drawdown, beta)
            stability = get_stability_metrics(cursor, symbol)

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
                roe_stability_index FLOAT,
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
            ADD COLUMN IF NOT EXISTS roe_stability_index FLOAT
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
            conn.rollback()
            cursor.close()
            cursor = conn.cursor()  # Create new cursor after rollback

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
                except:
                    pass
                conn = psycopg2.connect(**db_config)
            cursor.close()
            cursor = conn.cursor()  # Create new cursor after rollback

        try:
            load_momentum_metrics(conn, cursor, symbols)
            log_mem("After momentum metrics")
        except Exception as e:
            logging.error(f"Momentum metrics loading failed: {e}")
            conn.rollback()
            cursor.close()
            cursor = conn.cursor()  # Create new cursor after rollback

        try:
            load_stability_metrics(conn, cursor, symbols)
            log_mem("After stability metrics")
        except Exception as e:
            logging.error(f"Stability metrics loading failed: {e}")
            conn.rollback()
            cursor.close()
            cursor = conn.cursor()  # Create new cursor after rollback

        try:
            load_value_metrics(conn, cursor, symbols)
            log_mem("After value metrics")
        except Exception as e:
            logging.error(f"Value metrics loading failed: {e}")
            conn.rollback()
            cursor.close()
            cursor = conn.cursor()  # Create new cursor after rollback

        try:
            load_ad_ratings(conn, cursor, symbols)
            log_mem("After A/D ratings")
        except Exception as e:
            logging.error(f"A/D ratings loading failed: {e}")
            conn.rollback()
            cursor.close()
            cursor = conn.cursor()  # Create new cursor after rollback

        cursor.close()
        conn.close()

        logging.info(f"{SCRIPT_NAME} completed successfully")

    except Exception as e:
        logging.error(f"Error in {SCRIPT_NAME}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
# BATCH 1 FOUNDATION: momentum_metrics table creation
