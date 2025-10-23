#!/usr/bin/env python3
"""
Key Metrics Loader - Loads comprehensive financial metrics from yfinance
Loads data for ALL stocks in the stock_symbols table (not just hardcoded symbols)

Metrics loaded:
- Valuation multiples: P/E, P/B, P/S, EV/EBITDA, PEG
- Cash flows: Free Cash Flow, Operating Cash Flow
- Profitability: Profit Margin, Gross Margin, EBITDA Margin
- Returns: ROA, ROE
- Growth rates: Revenue Growth, Earnings Growth
- Dividend: Dividend Rate, Dividend Yield
- Debt: Total Debt, Debt to Equity
- Beta and other risk metrics
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

import psycopg2
import yfinance as yf
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

SCRIPT_NAME = "loadkeymetrics"


def get_db_config():
    """Get database configuration from environment"""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "password"),
        "dbname": os.getenv("DB_NAME", "stocks"),
    }


def get_all_symbols(cursor) -> list:
    """Get all stock symbols from the database"""
    cursor.execute("""
        SELECT symbol FROM stock_symbols
        WHERE (etf IS NULL OR etf != 'Y')
        ORDER BY symbol
    """)
    return [row[0] for row in cursor.fetchall()]


def load_key_metrics_for_symbol(ticker: str) -> Optional[Dict]:
    """Load comprehensive key metrics for a symbol from yfinance"""
    try:
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info

        if not info:
            logging.debug(f"  {ticker}: No yfinance data")
            return None

        # Extract metrics - using ONLY columns that exist in key_metrics table
        metrics = {
            "ticker": ticker,
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "price_to_sales_ttm": info.get("priceToSalesTrailing12Months"),
            "price_to_book": info.get("priceToBook"),
            "book_value": info.get("bookValue"),
            "peg_ratio": info.get("trailingPegRatio"),
            "enterprise_value": info.get("enterpriseValue"),
            "ev_to_revenue": info.get("enterpriseToRevenue"),
            "ev_to_ebitda": info.get("enterpriseToEbitda"),
            "total_revenue": info.get("totalRevenue"),
            "net_income": info.get("netIncomeToCommon"),
            "ebitda": info.get("ebitda"),
            "gross_profit": info.get("grossProfits"),
            "eps_trailing": info.get("trailingEps"),
            "eps_forward": info.get("forwardEps"),
            "eps_current_year": info.get("epsCurrentYear"),
            "price_eps_current_year": info.get("priceEpsCurrentYear"),
            "earnings_q_growth_pct": info.get("earningsQuarterlyGrowth"),
            "total_cash": info.get("totalCash"),
            "cash_per_share": info.get("totalCashPerShare"),
            "operating_cashflow": info.get("operatingCashflow"),
            "free_cashflow": info.get("freeCashflow"),
            "total_debt": info.get("totalDebt"),
            "debt_to_equity": info.get("debtToEquity"),
            "quick_ratio": info.get("quickRatio"),
            "current_ratio": info.get("currentRatio"),
            "profit_margin_pct": info.get("profitMargins"),
            "gross_margin_pct": info.get("grossMargins"),
            "ebitda_margin_pct": info.get("ebitdaMargins"),
            "operating_margin_pct": info.get("operatingMargins"),
            "return_on_assets_pct": info.get("returnOnAssets"),
            "return_on_equity_pct": info.get("returnOnEquity"),
            "revenue_growth_pct": info.get("revenueGrowth"),
            "earnings_growth_pct": info.get("earningsGrowth"),
            "dividend_rate": info.get("dividendRate"),
            "dividend_yield": info.get("dividendYield"),
            "five_year_avg_dividend_yield": info.get("fiveYearAvgDividendYield"),
        }

        # Filter out None values
        metrics = {k: v for k, v in metrics.items() if v is not None}

        # Require at least some data
        if len(metrics) <= 1:  # Only ticker field
            logging.debug(f"  {ticker}: Insufficient data")
            return None

        return metrics

    except Exception as e:
        logging.debug(f"  {ticker}: Error - {str(e)[:100]}")
        return None


def store_key_metrics(cursor, metrics: Dict) -> bool:
    """Store key metrics in database"""
    try:
        ticker = metrics["ticker"]
        columns = list(metrics.keys())
        values = [metrics[col] for col in columns]

        # Build UPSERT query
        col_str = ", ".join(columns)
        val_placeholders = ", ".join(["%s"] * len(values))
        update_clause = ", ".join(
            [f"{col} = EXCLUDED.{col}" for col in columns if col != "ticker"]
        )

        query = f"""
            INSERT INTO key_metrics ({col_str})
            VALUES ({val_placeholders})
            ON CONFLICT (ticker) DO UPDATE SET {update_clause}
        """

        cursor.execute(query, values)
        return True
    except Exception as e:
        logging.error(f"  {ticker}: DB Error - {str(e)[:100]}")
        return False


def main():
    """Main execution"""
    logging.info("=" * 80)
    logging.info("🚀 Key Metrics Loader - Loading for ALL stocks")
    logging.info("=" * 80)

    cfg = get_db_config()
    conn = psycopg2.connect(**cfg)
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        # Get all symbols
        symbols = get_all_symbols(cursor)
        logging.info(f"📊 Processing {len(symbols)} stocks...")
        logging.info("")

        success_count = 0
        failed_count = 0
        skipped_count = 0

        # Process each symbol
        for idx, ticker in enumerate(symbols, 1):
            # Load from yfinance
            metrics = load_key_metrics_for_symbol(ticker)

            if metrics is None:
                skipped_count += 1
                if idx % 250 == 0:
                    logging.info(f"  Progress: {idx}/{len(symbols)} symbols processed...")
                continue

            # Store in database
            try:
                if store_key_metrics(cursor, metrics):
                    success_count += 1
                    conn.commit()  # Commit after each successful insert
                else:
                    failed_count += 1
                    conn.rollback()  # Rollback on store failure to reset transaction
            except Exception as e:
                logging.debug(f"  {ticker}: Store error - {str(e)[:80]}")
                failed_count += 1
                conn.rollback()  # Reset transaction on any error
                continue

            # Progress updates every 250 symbols
            if idx % 250 == 0:
                logging.info(f"  Progress: {idx}/{len(symbols)} symbols processed...")

            # Rate limiting - yfinance has limits, be gentle
            if idx % 50 == 0:
                time.sleep(1)  # 1 second pause every 50 symbols

        # Final commit for any remaining changes
        try:
            conn.commit()
        except:
            pass  # Already committed individually

        # Update tracking
        cursor.execute("""
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, NOW())
            ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run
        """, (SCRIPT_NAME,))
        conn.commit()

        logging.info("")
        logging.info("=" * 80)
        logging.info("✅ Key Metrics Loader Complete!")
        logging.info(f"   Loaded: {success_count} symbols")
        logging.info(f"   Skipped (no data): {skipped_count} symbols")
        logging.info(f"   Failed: {failed_count} symbols")
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
