#!/usr/bin/env python3
"""
Calculate Missing Quality Metrics from Financial Statements
Populates gross_margin, operating_margin, debt_to_equity, current_ratio, quick_ratio
and other missing financial metrics by calculating from annual_balance_sheet and
annual_income_statement tables.
"""

import sys
import os
import io

# Fix Unicode encoding on Windows
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import logging
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values

# Load environment
env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_db_connection():
    """Create database connection."""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'stockdb'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'postgres')
    )

def calculate_missing_quality_metrics():
    """Calculate missing quality metrics from financial statements."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        logging.info("Fetching all symbols that need quality metrics...")

        # Get all symbols that have financial statement data
        cursor.execute("""
            SELECT DISTINCT symbol FROM annual_balance_sheet
            UNION
            SELECT DISTINCT symbol FROM annual_income_statement
            ORDER BY symbol
        """)
        symbols = [row[0] for row in cursor.fetchall()]
        logging.info(f"Found {len(symbols)} symbols with financial data")

        updates = []
        skipped = 0

        for i, symbol in enumerate(symbols, 1):
            if i % 100 == 0:
                logging.info(f"Processing symbol {i}/{len(symbols)}...")

            try:
                # Get latest balance sheet data
                cursor.execute("""
                    SELECT total_assets, total_liabilities, stockholders_equity,
                           current_assets, current_liabilities
                    FROM annual_balance_sheet
                    WHERE symbol = %s
                    ORDER BY fiscal_year DESC
                    LIMIT 1
                """, (symbol,))
                balance_row = cursor.fetchone()

                # Get latest income statement data
                cursor.execute("""
                    SELECT revenue, gross_profit, operating_income, net_income
                    FROM annual_income_statement
                    WHERE symbol = %s
                    ORDER BY fiscal_year DESC
                    LIMIT 1
                """, (symbol,))
                income_row = cursor.fetchone()

                # Get latest cash flow data
                cursor.execute("""
                    SELECT free_cash_flow, operating_cash_flow
                    FROM annual_cash_flow
                    WHERE symbol = %s
                    ORDER BY fiscal_year DESC
                    LIMIT 1
                """, (symbol,))
                cf_row = cursor.fetchone()

                # Calculate metrics from available data
                metrics = {
                    'gross_margin_pct': None,
                    'operating_margin_pct': None,
                    'profit_margin_pct': None,
                    'return_on_assets_pct': None,
                    'return_on_equity_pct': None,
                    'return_on_invested_capital_pct': None,
                    'debt_to_equity': None,
                    'current_ratio': None,
                    'quick_ratio': None,
                }

                if income_row:
                    revenue, gross_profit, operating_income, net_income = income_row

                    if revenue and revenue > 0:
                        if gross_profit:
                            metrics['gross_margin_pct'] = (gross_profit / revenue) * 100
                        if operating_income:
                            metrics['operating_margin_pct'] = (operating_income / revenue) * 100
                        if net_income:
                            metrics['profit_margin_pct'] = (net_income / revenue) * 100

                if balance_row and income_row:
                    total_assets, total_liabilities, stockholders_equity, current_assets, current_liabilities = balance_row
                    _, _, _, net_income = income_row

                    if total_assets and total_assets > 0 and net_income:
                        metrics['return_on_assets_pct'] = (net_income / total_assets) * 100

                    if stockholders_equity and stockholders_equity > 0 and net_income:
                        metrics['return_on_equity_pct'] = (net_income / stockholders_equity) * 100

                    # Return on invested capital = EBIT / Invested Capital
                    # Where Invested Capital = Shareholders Equity + Total Debt
                    # We approximate EBIT as Net Income + Interest (simplified, assuming no tax)
                    # For now, use: (Net Income / (Shareholders Equity + Total Liabilities)) * 100
                    if net_income and stockholders_equity and total_liabilities:
                        invested_capital = stockholders_equity + total_liabilities
                        if invested_capital > 0:
                            metrics['return_on_invested_capital_pct'] = (net_income / invested_capital) * 100

                    if total_liabilities and stockholders_equity:
                        if stockholders_equity > 0:
                            metrics['debt_to_equity'] = total_liabilities / stockholders_equity
                        else:
                            metrics['debt_to_equity'] = None

                    if current_assets and current_liabilities and current_liabilities > 0:
                        metrics['current_ratio'] = current_assets / current_liabilities

                    # Quick ratio: (current_assets - inventory) / current_liabilities
                    # We don't have inventory, so we approximate using current_assets / current_liabilities
                    # This is actually the current ratio; true quick_ratio requires inventory data
                    # For now, skip quick_ratio calculation since we lack the data

                # Skip if no metrics calculated
                if not any(v is not None for v in metrics.values()):
                    skipped += 1
                    continue

                updates.append((
                    symbol,
                    metrics['gross_margin_pct'],
                    metrics['operating_margin_pct'],
                    metrics['profit_margin_pct'],
                    metrics['return_on_assets_pct'],
                    metrics['return_on_equity_pct'],
                    metrics['return_on_invested_capital_pct'],
                    metrics['debt_to_equity'],
                    metrics['current_ratio'],
                ))

            except Exception as e:
                logging.warning(f"Error processing {symbol}: {e}")
                conn.rollback()

        # Update quality_metrics with calculated values
        if updates:
            logging.info(f"Updating quality_metrics with {len(updates)} calculated metrics...")

            update_sql = """
                UPDATE quality_metrics SET
                    gross_margin_pct = COALESCE(gross_margin_pct, %s),
                    operating_margin_pct = COALESCE(operating_margin_pct, %s),
                    profit_margin_pct = COALESCE(profit_margin_pct, %s),
                    return_on_assets_pct = COALESCE(return_on_assets_pct, %s),
                    return_on_equity_pct = COALESCE(return_on_equity_pct, %s),
                    return_on_invested_capital_pct = COALESCE(return_on_invested_capital_pct, %s),
                    debt_to_equity = COALESCE(debt_to_equity, %s),
                    current_ratio = COALESCE(current_ratio, %s)
                WHERE symbol = %s AND date = (SELECT MAX(date) FROM quality_metrics WHERE symbol = %s)
            """

            for symbol, gross_m, op_m, profit_m, roa, roe, roic, de, cr in updates:
                cursor.execute(update_sql, (
                    gross_m, op_m, profit_m, roa, roe, roic, de, cr, symbol, symbol
                ))

            conn.commit()
            logging.info(f"Successfully updated {len(updates)} metrics ({skipped} skipped)")
        else:
            logging.info(f"No metrics to update ({skipped} symbols skipped)")

    except Exception as e:
        logging.error(f"Fatal error: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

    return True

if __name__ == "__main__":
    success = calculate_missing_quality_metrics()
    sys.exit(0 if success else 1)
