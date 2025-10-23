#!/usr/bin/env python3
"""
Simple Key Metrics Loader - loads ALL stocks from yfinance
Each symbol gets its own connection/transaction to avoid "aborted transaction" issues
"""

import logging
import os
import time
from typing import Optional, Dict

import psycopg2
import yfinance as yf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

def get_db_config():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "password"),
        "dbname": os.getenv("DB_NAME", "stocks"),
    }

def load_for_symbol(ticker: str) -> Optional[Dict]:
    """Load metrics for ONE symbol (handles errors individually)"""
    try:
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info

        if not info:
            return None

        # Only extract columns that EXIST in key_metrics table
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

        # Filter None values
        metrics = {k: v for k, v in metrics.items() if v is not None}

        # Need at least some data
        if len(metrics) <= 1:
            return None

        return metrics

    except Exception as e:
        logging.debug(f"{ticker}: {str(e)[:80]}")
        return None

def save_metrics(ticker: str, metrics: Dict) -> bool:
    """Save metrics - uses fresh connection for each save to avoid transaction issues"""
    try:
        cfg = get_db_config()
        conn = psycopg2.connect(**cfg)
        cursor = conn.cursor()

        columns = list(metrics.keys())
        values = [metrics[col] for col in columns]

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
        conn.commit()
        cursor.close()
        conn.close()
        return True

    except Exception as e:
        logging.debug(f"{ticker}: Save error - {str(e)[:80]}")
        try:
            cursor.close()
            conn.close()
        except:
            pass
        return False

def main():
    logging.info("=" * 80)
    logging.info("Key Metrics Loader - Loading for ALL stocks")
    logging.info("=" * 80)

    # Get all symbols
    cfg = get_db_config()
    conn = psycopg2.connect(**cfg)
    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y') ORDER BY symbol")
    symbols = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    logging.info(f"Processing {len(symbols)} stocks...")

    success = 0
    skipped = 0

    for idx, ticker in enumerate(symbols, 1):
        metrics = load_for_symbol(ticker)

        if metrics is None:
            skipped += 1
        else:
            if save_metrics(ticker, metrics):
                success += 1

        if idx % 250 == 0:
            logging.info(f"Progress: {idx}/{len(symbols)}")

        # Rate limiting
        if idx % 50 == 0:
            time.sleep(1)

    logging.info("")
    logging.info("=" * 80)
    logging.info(f"✅ Complete: {success} loaded, {skipped} skipped")
    logging.info("=" * 80)

if __name__ == "__main__":
    main()
