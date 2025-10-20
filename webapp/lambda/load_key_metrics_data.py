#!/usr/bin/env python3
"""
Key Metrics Loader Script
Loads comprehensive financial metrics from yfinance into key_metrics table.
"""

import os
import sys
import psycopg2
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'postgres',
    'password': 'password',
    'dbname': 'stocks'
}

def get_db_connection():
    """Get database connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.Error as e:
        logger.error(f"❌ Failed to connect to database: {e}")
        return None

def load_key_metrics_for_symbol(conn, symbol):
    """Load comprehensive key metrics for a symbol."""
    try:
        logger.info(f"📊 Loading key metrics for {symbol}")
        ticker = yf.Ticker(symbol)
        info = ticker.info

        if not info:
            logger.warning(f"⚠️ No info data for {symbol}")
            return False

        # Extract all key metrics from yfinance info - match existing table columns
        metrics_data = {
            'ticker': symbol,
            'trailing_pe': info.get('trailingPE'),
            'forward_pe': info.get('forwardPE'),
            'price_to_sales_ttm': info.get('priceToSalesTrailing12Months'),
            'price_to_book': info.get('priceToBook'),
            'book_value': info.get('bookValue'),
            'peg_ratio': info.get('trailingPegRatio'),
            'enterprise_value': info.get('enterpriseValue'),
            'ev_to_revenue': info.get('enterpriseToRevenue'),
            'ev_to_ebitda': info.get('enterpriseToEbitda'),
            'total_revenue': info.get('totalRevenue'),
            'net_income': info.get('netIncomeToCommon'),
            'ebitda': info.get('ebitda'),
            'gross_profit': info.get('grossProfits'),
            'eps_trailing': info.get('trailingEps'),
            'eps_forward': info.get('forwardEps'),
            'eps_current_year': info.get('epsCurrentYear'),
            'price_eps_current_year': info.get('priceEpsCurrentYear'),
            'earnings_q_growth_pct': info.get('earningsQuarterlyGrowth'),
            'total_cash': info.get('totalCash'),
            'cash_per_share': info.get('totalCashPerShare'),
            'operating_cashflow': info.get('operatingCashflow'),
            'free_cashflow': info.get('freeCashflow'),
            'total_debt': info.get('totalDebt'),
            'debt_to_equity': info.get('debtToEquity'),
            'quick_ratio': info.get('quickRatio'),
            'current_ratio': info.get('currentRatio'),
            'profit_margin_pct': info.get('profitMargins'),
            'gross_margin_pct': info.get('grossMargins'),
            'ebitda_margin_pct': info.get('ebitdaMargins'),
            'operating_margin_pct': info.get('operatingMargins'),
            'return_on_assets_pct': info.get('returnOnAssets'),
            'return_on_equity_pct': info.get('returnOnEquity'),
            'revenue_growth_pct': info.get('revenueGrowth'),
            'earnings_growth_pct': info.get('earningsGrowth'),
            'dividend_rate': info.get('dividendRate'),
            'dividend_yield': info.get('dividendYield'),
            'five_year_avg_dividend_yield': info.get('fiveYearAvgDividendYield'),
            'last_annual_dividend_amt': info.get('trailingAnnualDividendRate'),
            'last_annual_dividend_yield': info.get('trailingAnnualDividendYield'),
            'payout_ratio': info.get('payoutRatio'),
            'beta': info.get('beta')
        }

        # Insert into database
        cur = conn.cursor()

        # Build dynamic insert query
        columns = []
        values = []
        placeholders = []

        for key, value in metrics_data.items():
            if value is not None:
                columns.append(key)
                values.append(value)
                placeholders.append('%s')

        if not columns:
            logger.warning(f"⚠️ No valid metrics data for {symbol}")
            return False

        insert_query = f"""
            INSERT INTO key_metrics ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT (ticker) DO UPDATE SET
                {', '.join([f'{col} = EXCLUDED.{col}' for col in columns if col not in ['ticker']])}
        """

        cur.execute(insert_query, values)
        conn.commit()
        cur.close()

        logger.info(f"✅ Loaded {len(columns)} metrics for {symbol}")
        return True

    except Exception as e:
        logger.error(f"❌ Error loading metrics for {symbol}: {e}")
        return False

def main():
    """Main loader function."""
    logger.info("🚀 Starting key metrics data loader...")

    # Major stock symbols to populate
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX', 'JPM', 'JNJ', 'V', 'SPY', 'QQQ']

    # Connect to database
    conn = get_db_connection()
    if not conn:
        logger.error("❌ Failed to connect to database")
        sys.exit(1)

    try:
        success_count = 0
        total_count = len(symbols)

        for symbol in symbols:
            if load_key_metrics_for_symbol(conn, symbol):
                success_count += 1

        logger.info(f"""
✅ Key metrics loading completed!
📊 Successfully loaded: {success_count}/{total_count} symbols
        """)

    except Exception as e:
        logger.error(f"❌ Loading failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()