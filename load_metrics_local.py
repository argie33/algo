#!/usr/bin/env python3
"""
Local script to populate key_metrics table with complete financial data from yfinance
Run this to ensure all cash flow and financial metrics are populated before testing
"""

import logging
import sys
import time
import psycopg2
from psycopg2.extras import execute_values
import yfinance as yf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# Local database config
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "stocks",
    "password": "stocks",
    "dbname": "stocks",
}


def load_key_metrics_for_symbols(symbols):
    """Load comprehensive key metrics from yfinance for given symbols"""

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    logging.info(f"Loading key metrics for {len(symbols)} symbols: {symbols}")

    for symbol in symbols:
        try:
            logging.info(f"Fetching data for {symbol}...")
            ticker = yf.Ticker(symbol)
            info = ticker.info

            if not info or not isinstance(info, dict):
                logging.warning(f"No data available for {symbol}")
                continue

            # Extract all key metrics with safe defaults
            metrics = {
                'ticker': symbol,
                'trailing_pe': info.get('trailingPE'),
                'forward_pe': info.get('forwardPE'),
                'price_to_sales_ttm': info.get('priceToSalesTrailing12Months'),
                'price_to_book': info.get('priceToBook'),
                'book_value': info.get('bookValue'),
                'peg_ratio': info.get('pegRatio'),
                'enterprise_value': info.get('enterpriseValue'),
                'ev_to_revenue': info.get('enterpriseToRevenue'),
                'ev_to_ebitda': info.get('enterpriseToEbitda'),

                # Income statement
                'total_revenue': info.get('totalRevenue'),
                'net_income': info.get('netIncomeToCommon'),
                'ebitda': info.get('ebitda'),
                'gross_profit': info.get('grossProfits'),

                # EPS metrics
                'eps_trailing': info.get('trailingEps'),
                'eps_forward': info.get('forwardEps'),
                'eps_current_year': info.get('currentEps'),
                'price_eps_current_year': info.get('currentPrice'),

                # Growth metrics
                'earnings_q_growth_pct': info.get('earningsQuarterlyGrowth'),
                'earnings_growth_pct': info.get('earningsGrowth'),
                'revenue_growth_pct': info.get('revenueGrowth'),

                # Earnings dates
                'earnings_ts_ms': None,  # Would need earnings_dates
                'earnings_ts_start_ms': None,
                'earnings_ts_end_ms': None,
                'earnings_call_ts_start_ms': None,
                'earnings_call_ts_end_ms': None,
                'is_earnings_date_estimate': None,

                # Cash metrics
                'total_cash': info.get('totalCash'),
                'cash_per_share': info.get('totalCashPerShare'),
                'operating_cashflow': info.get('operatingCashflow'),
                'free_cashflow': info.get('freeCashflow'),

                # Debt metrics
                'total_debt': info.get('totalDebt'),
                'debt_to_equity': info.get('debtToEquity'),
                'quick_ratio': info.get('quickRatio'),
                'current_ratio': info.get('currentRatio'),

                # Profitability margins
                'profit_margin_pct': info.get('profitMargins') * 100 if info.get('profitMargins') else None,
                'gross_margin_pct': info.get('grossMargins') * 100 if info.get('grossMargins') else None,
                'ebitda_margin_pct': info.get('ebitdaMargins') * 100 if info.get('ebitdaMargins') else None,
                'operating_margin_pct': info.get('operatingMargins') * 100 if info.get('operatingMargins') else None,

                # Returns
                'return_on_assets_pct': info.get('returnOnAssets') * 100 if info.get('returnOnAssets') else None,
                'return_on_equity_pct': info.get('returnOnEquity') * 100 if info.get('returnOnEquity') else None,

                # Dividend metrics
                'dividend_rate': info.get('dividendRate'),
                'dividend_yield': info.get('dividendYield') * 100 if info.get('dividendYield') else None,
                'five_year_avg_dividend_yield': info.get('fiveYearAvgDividendYield'),
                'ex_dividend_date_ms': None,  # Would need conversion
                'last_annual_dividend_amt': info.get('lastDividendValue'),
                'last_annual_dividend_yield': None,
                'last_dividend_amt': info.get('lastDividendValue'),
                'last_dividend_date_ms': None,
                'dividend_date_ms': None,
                'payout_ratio': info.get('payoutRatio'),

                # Split info
                'last_split_factor': info.get('lastSplitFactor'),
                'last_split_date_ms': None,
            }

            # Insert or update key_metrics
            upsert_query = """
                INSERT INTO key_metrics (
                    ticker, trailing_pe, forward_pe, price_to_sales_ttm, price_to_book,
                    book_value, peg_ratio, enterprise_value, ev_to_revenue, ev_to_ebitda,
                    total_revenue, net_income, ebitda, gross_profit,
                    eps_trailing, eps_forward, eps_current_year, price_eps_current_year,
                    earnings_q_growth_pct, earnings_growth_pct, revenue_growth_pct,
                    total_cash, cash_per_share, operating_cashflow, free_cashflow,
                    total_debt, debt_to_equity, quick_ratio, current_ratio,
                    profit_margin_pct, gross_margin_pct, ebitda_margin_pct, operating_margin_pct,
                    return_on_assets_pct, return_on_equity_pct,
                    dividend_rate, dividend_yield, five_year_avg_dividend_yield,
                    last_annual_dividend_amt, last_dividend_amt, payout_ratio,
                    last_split_factor
                ) VALUES (
                    %(ticker)s, %(trailing_pe)s, %(forward_pe)s, %(price_to_sales_ttm)s, %(price_to_book)s,
                    %(book_value)s, %(peg_ratio)s, %(enterprise_value)s, %(ev_to_revenue)s, %(ev_to_ebitda)s,
                    %(total_revenue)s, %(net_income)s, %(ebitda)s, %(gross_profit)s,
                    %(eps_trailing)s, %(eps_forward)s, %(eps_current_year)s, %(price_eps_current_year)s,
                    %(earnings_q_growth_pct)s, %(earnings_growth_pct)s, %(revenue_growth_pct)s,
                    %(total_cash)s, %(cash_per_share)s, %(operating_cashflow)s, %(free_cashflow)s,
                    %(total_debt)s, %(debt_to_equity)s, %(quick_ratio)s, %(current_ratio)s,
                    %(profit_margin_pct)s, %(gross_margin_pct)s, %(ebitda_margin_pct)s, %(operating_margin_pct)s,
                    %(return_on_assets_pct)s, %(return_on_equity_pct)s,
                    %(dividend_rate)s, %(dividend_yield)s, %(five_year_avg_dividend_yield)s,
                    %(last_annual_dividend_amt)s, %(last_dividend_amt)s, %(payout_ratio)s,
                    %(last_split_factor)s
                )
                ON CONFLICT (ticker) DO UPDATE SET
                    trailing_pe = EXCLUDED.trailing_pe,
                    forward_pe = EXCLUDED.forward_pe,
                    price_to_sales_ttm = EXCLUDED.price_to_sales_ttm,
                    price_to_book = EXCLUDED.price_to_book,
                    book_value = EXCLUDED.book_value,
                    peg_ratio = EXCLUDED.peg_ratio,
                    enterprise_value = EXCLUDED.enterprise_value,
                    ev_to_revenue = EXCLUDED.ev_to_revenue,
                    ev_to_ebitda = EXCLUDED.ev_to_ebitda,
                    total_revenue = EXCLUDED.total_revenue,
                    net_income = EXCLUDED.net_income,
                    ebitda = EXCLUDED.ebitda,
                    gross_profit = EXCLUDED.gross_profit,
                    eps_trailing = EXCLUDED.eps_trailing,
                    eps_forward = EXCLUDED.eps_forward,
                    eps_current_year = EXCLUDED.eps_current_year,
                    price_eps_current_year = EXCLUDED.price_eps_current_year,
                    earnings_q_growth_pct = EXCLUDED.earnings_q_growth_pct,
                    earnings_growth_pct = EXCLUDED.earnings_growth_pct,
                    revenue_growth_pct = EXCLUDED.revenue_growth_pct,
                    total_cash = EXCLUDED.total_cash,
                    cash_per_share = EXCLUDED.cash_per_share,
                    operating_cashflow = EXCLUDED.operating_cashflow,
                    free_cashflow = EXCLUDED.free_cashflow,
                    total_debt = EXCLUDED.total_debt,
                    debt_to_equity = EXCLUDED.debt_to_equity,
                    quick_ratio = EXCLUDED.quick_ratio,
                    current_ratio = EXCLUDED.current_ratio,
                    profit_margin_pct = EXCLUDED.profit_margin_pct,
                    gross_margin_pct = EXCLUDED.gross_margin_pct,
                    ebitda_margin_pct = EXCLUDED.ebitda_margin_pct,
                    operating_margin_pct = EXCLUDED.operating_margin_pct,
                    return_on_assets_pct = EXCLUDED.return_on_assets_pct,
                    return_on_equity_pct = EXCLUDED.return_on_equity_pct,
                    dividend_rate = EXCLUDED.dividend_rate,
                    dividend_yield = EXCLUDED.dividend_yield,
                    five_year_avg_dividend_yield = EXCLUDED.five_year_avg_dividend_yield,
                    last_annual_dividend_amt = EXCLUDED.last_annual_dividend_amt,
                    last_dividend_amt = EXCLUDED.last_dividend_amt,
                    payout_ratio = EXCLUDED.payout_ratio,
                    last_split_factor = EXCLUDED.last_split_factor
            """

            cur.execute(upsert_query, metrics)
            conn.commit()

            logging.info(f"✅ Successfully loaded metrics for {symbol}")
            logging.info(f"   PE: {metrics['trailing_pe']}, Market Cap: {metrics['enterprise_value']}, "
                        f"ROE: {metrics['return_on_equity_pct']}%, Cash Flow: {metrics['free_cashflow']}")

            # Rate limit: yfinance free tier allows ~2 requests/second
            time.sleep(0.6)

        except Exception as e:
            logging.error(f"❌ Failed to load metrics for {symbol}: {e}")
            conn.rollback()
            continue

    cur.close()
    conn.close()
    logging.info("✅ Key metrics loading complete")


if __name__ == "__main__":
    # Get symbols from database
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM company_profile ORDER BY ticker")
    symbols = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()

    logging.info(f"Found {len(symbols)} symbols in company_profile table")
    load_key_metrics_for_symbols(symbols)
