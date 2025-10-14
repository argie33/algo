#!/usr/bin/env python3
"""
Test script to load quarterly financial data for AAPL and calculate quality/growth metrics
"""

import logging
import os
import sys

# Set up local database
os.environ["USE_LOCAL_DB"] = "true"
os.environ["DB_HOST"] = "localhost"
os.environ["DB_PORT"] = "5432"
os.environ["DB_USER"] = "postgres"
os.environ["DB_PASSWORD"] = "password"
os.environ["DB_NAME"] = "stocks"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

def test_aapl_data_pipeline():
    """Test loading quarterly data and calculating metrics for AAPL"""

    print("\n" + "="*80)
    print("AAPL DATA PIPELINE TEST")
    print("="*80 + "\n")

    # Import after setting environment variables
    from loadquarterlyincomestatement import (
        get_db_config,
        get_quarterly_income_statement_data,
        process_income_statement_data
    )
    from loadquarterlybalancesheet import (
        get_quarterly_balance_sheet_data,
        process_balance_sheet_data
    )
    from loadquarterlycashflow import (
        get_quarterly_cash_flow_data,
        process_cash_flow_data
    )
    import psycopg2
    from psycopg2.extras import execute_values

    # Connect to database
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["dbname"],
    )
    conn.autocommit = False
    cur = conn.cursor()

    symbol = "AAPL"

    try:
        # Step 1: Load Quarterly Income Statement
        print(f"\n{'='*80}")
        print(f"STEP 1: Loading quarterly income statement for {symbol}")
        print("="*80)

        income_stmt = get_quarterly_income_statement_data(symbol)
        if income_stmt is not None:
            income_data = process_income_statement_data(symbol, income_stmt)
            if income_data:
                execute_values(
                    cur,
                    """
                    INSERT INTO quarterly_income_statement (symbol, date, item_name, value)
                    VALUES %s
                    ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = NOW()
                    """,
                    income_data,
                )
                conn.commit()
                print(f"✅ Loaded {len(income_data)} income statement records for {symbol}")
        else:
            print(f"❌ No income statement data for {symbol}")

        # Step 2: Load Quarterly Balance Sheet
        print(f"\n{'='*80}")
        print(f"STEP 2: Loading quarterly balance sheet for {symbol}")
        print("="*80)

        balance_sheet = get_quarterly_balance_sheet_data(symbol)
        if balance_sheet is not None:
            balance_data = process_balance_sheet_data(symbol, balance_sheet)
            if balance_data:
                execute_values(
                    cur,
                    """
                    INSERT INTO quarterly_balance_sheet (symbol, date, item_name, value)
                    VALUES %s
                    ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = NOW()
                    """,
                    balance_data,
                )
                conn.commit()
                print(f"✅ Loaded {len(balance_data)} balance sheet records for {symbol}")
        else:
            print(f"❌ No balance sheet data for {symbol}")

        # Step 3: Load Quarterly Cash Flow
        print(f"\n{'='*80}")
        print(f"STEP 3: Loading quarterly cash flow for {symbol}")
        print("="*80)

        cash_flow = get_quarterly_cash_flow_data(symbol)
        if cash_flow is not None:
            cash_flow_data = process_cash_flow_data(symbol, cash_flow)
            if cash_flow_data:
                execute_values(
                    cur,
                    """
                    INSERT INTO quarterly_cash_flow (symbol, date, item_name, value)
                    VALUES %s
                    ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = NOW()
                    """,
                    cash_flow_data,
                )
                conn.commit()
                print(f"✅ Loaded {len(cash_flow_data)} cash flow records for {symbol}")
        else:
            print(f"❌ No cash flow data for {symbol}")

        # Step 4: Calculate Quality Metrics
        print(f"\n{'='*80}")
        print(f"STEP 4: Calculating quality metrics for {symbol}")
        print("="*80)

        from loadqualitymetrics import process_symbol as process_quality
        from loadqualitymetrics import create_connection_pool

        # Create connection pool for quality metrics
        conn_pool = create_connection_pool()
        records = process_quality(symbol, conn_pool)
        conn_pool.closeall()
        print(f"✅ Calculated {records} quality metric records for {symbol}")

        # Step 5: Calculate Growth Metrics
        print(f"\n{'='*80}")
        print(f"STEP 5: Calculating growth metrics for {symbol}")
        print("="*80)

        from loadgrowthmetrics import process_symbol as process_growth
        from loadgrowthmetrics import create_connection_pool as create_growth_pool

        # Create connection pool for growth metrics
        growth_pool = create_growth_pool()
        growth_records = process_growth(symbol, growth_pool)
        growth_pool.closeall()
        print(f"✅ Calculated {growth_records} growth metric records for {symbol}")

        # Step 6: Verify Data in Database
        print(f"\n{'='*80}")
        print(f"STEP 6: Verifying data in database for {symbol}")
        print("="*80)

        cur.execute("SELECT COUNT(*) FROM quarterly_income_statement WHERE symbol = %s", (symbol,))
        income_count = cur.fetchone()[0]
        print(f"  Income statement records: {income_count}")

        cur.execute("SELECT COUNT(*) FROM quarterly_balance_sheet WHERE symbol = %s", (symbol,))
        balance_count = cur.fetchone()[0]
        print(f"  Balance sheet records: {balance_count}")

        cur.execute("SELECT COUNT(*) FROM quarterly_cash_flow WHERE symbol = %s", (symbol,))
        cashflow_count = cur.fetchone()[0]
        print(f"  Cash flow records: {cashflow_count}")

        cur.execute("SELECT * FROM quality_metrics WHERE symbol = %s", (symbol,))
        quality = cur.fetchone()
        if quality:
            print(f"\n  Quality Metrics:")
            print(f"    Accruals Ratio: {quality[2]}")
            print(f"    FCF to Net Income: {quality[3]}")
            print(f"    Debt to Equity: {quality[4]}")
            print(f"    Current Ratio: {quality[5]}")
            print(f"    Interest Coverage: {quality[6]}")
            print(f"    Asset Turnover: {quality[7]}")
        else:
            print("  ❌ No quality metrics found")

        cur.execute("SELECT * FROM growth_metrics WHERE symbol = %s", (symbol,))
        growth = cur.fetchone()
        if growth:
            print(f"\n  Growth Metrics:")
            print(f"    Revenue Growth 3Y CAGR: {growth[2]}")
            print(f"    EPS Growth 3Y CAGR: {growth[3]}")
            print(f"    Operating Income Growth YoY: {growth[4]}")
            print(f"    ROE Trend: {growth[5]}")
            print(f"    Sustainable Growth Rate: {growth[6]}")
            print(f"    FCF Growth YoY: {growth[7]}")
        else:
            print("  ❌ No growth metrics found")

        print(f"\n{'='*80}")
        print("✅ AAPL DATA PIPELINE TEST COMPLETED SUCCESSFULLY!")
        print("="*80 + "\n")

    except Exception as e:
        print(f"\n❌ Error in pipeline: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    test_aapl_data_pipeline()
