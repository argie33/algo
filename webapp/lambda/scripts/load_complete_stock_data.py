#!/usr/bin/env python3
"""
Load complete stock data for a symbol using yfinance
"""

import sys
import yfinance as yf
import psycopg2
from datetime import datetime

def load_stock_data(symbol):
    """Load all necessary data for a stock symbol"""

    # Database connection
    conn = psycopg2.connect(
        host="localhost",
        database="stocks",
        user="postgres",
        password="password"
    )
    cur = conn.cursor()

    try:
        print(f"Fetching data for {symbol}...")
        stock = yf.Ticker(symbol)
        info = stock.info

        # 1. Load company_profile
        print("Loading company profile...")
        cur.execute("""
            INSERT INTO company_profile (
                ticker, short_name, long_name, quote_type,
                address1, city, state, postal_code, country,
                phone_number, website_url,
                sector, industry, business_summary, employee_count
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker) DO UPDATE SET
                short_name = EXCLUDED.short_name,
                long_name = EXCLUDED.long_name,
                quote_type = EXCLUDED.quote_type,
                address1 = EXCLUDED.address1,
                city = EXCLUDED.city,
                state = EXCLUDED.state,
                postal_code = EXCLUDED.postal_code,
                country = EXCLUDED.country,
                phone_number = EXCLUDED.phone_number,
                website_url = EXCLUDED.website_url,
                sector = EXCLUDED.sector,
                industry = EXCLUDED.industry,
                business_summary = EXCLUDED.business_summary,
                employee_count = EXCLUDED.employee_count
        """, (
            symbol,
            info.get('shortName'),
            info.get('longName'),
            info.get('quoteType'),
            info.get('address1'),
            info.get('city'),
            info.get('state'),
            info.get('zip'),
            info.get('country'),
            info.get('phone'),
            info.get('website'),
            info.get('sector'),
            info.get('industry'),
            info.get('longBusinessSummary'),
            info.get('fullTimeEmployees')
        ))
        conn.commit()
        print(f"✓ Company profile loaded: {info.get('longName', symbol)}")

        # 2. Load key_metrics
        print("Loading key metrics...")
        cur.execute("""
            INSERT INTO key_metrics (
                ticker, trailing_pe, forward_pe, price_to_sales_ttm, price_to_book,
                book_value, peg_ratio, enterprise_value, ev_to_revenue, ev_to_ebitda,
                total_revenue, net_income, ebitda, gross_profit,
                eps_trailing, eps_forward, total_cash, cash_per_share,
                operating_cashflow, free_cashflow, total_debt, debt_to_equity,
                quick_ratio, current_ratio, profit_margin_pct, operating_margin_pct,
                return_on_assets_pct, return_on_equity_pct, revenue_growth_pct,
                dividend_rate, dividend_yield, five_year_avg_dividend_yield
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
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
                total_cash = EXCLUDED.total_cash,
                cash_per_share = EXCLUDED.cash_per_share,
                operating_cashflow = EXCLUDED.operating_cashflow,
                free_cashflow = EXCLUDED.free_cashflow,
                total_debt = EXCLUDED.total_debt,
                debt_to_equity = EXCLUDED.debt_to_equity,
                quick_ratio = EXCLUDED.quick_ratio,
                current_ratio = EXCLUDED.current_ratio,
                profit_margin_pct = EXCLUDED.profit_margin_pct,
                operating_margin_pct = EXCLUDED.operating_margin_pct,
                return_on_assets_pct = EXCLUDED.return_on_assets_pct,
                return_on_equity_pct = EXCLUDED.return_on_equity_pct,
                revenue_growth_pct = EXCLUDED.revenue_growth_pct,
                dividend_rate = EXCLUDED.dividend_rate,
                dividend_yield = EXCLUDED.dividend_yield,
                five_year_avg_dividend_yield = EXCLUDED.five_year_avg_dividend_yield
        """, (
            symbol,
            info.get('trailingPE'),
            info.get('forwardPE'),
            info.get('priceToSalesTrailing12Months'),
            info.get('priceToBook'),
            info.get('bookValue'),
            info.get('pegRatio'),
            info.get('enterpriseValue'),
            info.get('enterpriseToRevenue'),
            info.get('enterpriseToEbitda'),
            info.get('totalRevenue'),
            info.get('netIncomeToCommon'),
            info.get('ebitda'),
            info.get('grossProfits'),
            info.get('trailingEps'),
            info.get('forwardEps'),
            info.get('totalCash'),
            info.get('totalCashPerShare'),
            info.get('operatingCashflow'),
            info.get('freeCashflow'),
            info.get('totalDebt'),
            info.get('debtToEquity'),
            info.get('quickRatio'),
            info.get('currentRatio'),
            info.get('profitMargins'),
            info.get('operatingMargins'),
            info.get('returnOnAssets'),
            info.get('returnOnEquity'),
            info.get('revenueGrowth'),
            info.get('dividendRate'),
            info.get('dividendYield'),
            info.get('fiveYearAvgDividendYield')
        ))
        conn.commit()
        print(f"✓ Key metrics loaded")

        # 3. Load price_daily (last 90 days)
        print("Loading daily price data...")
        hist = stock.history(period="3mo")

        if not hist.empty:
            # First, delete existing data for this symbol to avoid duplicates
            cur.execute("DELETE FROM price_daily WHERE symbol = %s", (symbol,))

            for date, row in hist.iterrows():
                cur.execute("""
                    INSERT INTO price_daily (
                        symbol, date, open, high, low, close, volume, adj_close
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    symbol,
                    date.date(),
                    float(row['Open']) if row['Open'] else None,
                    float(row['High']) if row['High'] else None,
                    float(row['Low']) if row['Low'] else None,
                    float(row['Close']) if row['Close'] else None,
                    int(row['Volume']) if row['Volume'] else None,
                    float(row['Close']) if row['Close'] else None  # Using Close as adj_close
                ))
            conn.commit()
            print(f"✓ Loaded {len(hist)} days of price data")

        # 4. Load earnings history
        print("Loading earnings history...")
        try:
            earnings_history = stock.earnings_history
            if earnings_history is not None and not earnings_history.empty:
                # Delete existing earnings history for this symbol
                cur.execute("DELETE FROM earnings_history WHERE symbol = %s", (symbol,))

                for quarter, row in earnings_history.iterrows():
                    quarter_date = str(quarter)
                    cur.execute("""
                        INSERT INTO earnings_history (
                            symbol, quarter, eps_actual, eps_estimate,
                            eps_difference, surprise_percent
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, quarter) DO UPDATE SET
                            eps_actual = EXCLUDED.eps_actual,
                            eps_estimate = EXCLUDED.eps_estimate,
                            eps_difference = EXCLUDED.eps_difference,
                            surprise_percent = EXCLUDED.surprise_percent,
                            fetched_at = CURRENT_TIMESTAMP
                    """, (
                        symbol,
                        quarter_date,
                        float(row.get('epsActual')) if row.get('epsActual') else None,
                        float(row.get('epsEstimate')) if row.get('epsEstimate') else None,
                        float(row.get('epsDifference')) if row.get('epsDifference') else None,
                        float(row.get('surprisePercent')) if row.get('surprisePercent') else None,
                    ))
                conn.commit()
                print(f"✓ Loaded {len(earnings_history)} earnings history records")
            else:
                print("⚠ No earnings history data available")
        except Exception as e:
            print(f"⚠ Could not load earnings history: {e}")
            conn.rollback()

        print(f"\n✅ Successfully loaded all data for {symbol}")
        print(f"   - Company: {info.get('longName', 'N/A')}")
        print(f"   - Sector: {info.get('sector', 'N/A')}")
        print(f"   - Industry: {info.get('industry', 'N/A')}")
        print(f"   - Price: ${info.get('currentPrice', 'N/A')}")

    except Exception as e:
        print(f"❌ Error loading data: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 load_complete_stock_data.py <SYMBOL>")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    load_stock_data(symbol)
