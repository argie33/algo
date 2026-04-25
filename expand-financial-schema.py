#!/usr/bin/env python3
"""
Expand financial statement tables to include all yfinance columns
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv
from pathlib import Path

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", 5432),
        user=os.environ.get("DB_USER", "stocks"),
        password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get("DB_NAME", "stocks")
    )

# Normalize yfinance column names to valid SQL names
def normalize_column_name(name):
    """Convert 'Total Assets' -> 'total_assets'"""
    return name.lower().replace(" ", "_").replace("/", "").replace("&", "and").replace("-", "_").replace("(", "").replace(")", "")

# Balance Sheet columns from yfinance
BALANCE_SHEET_COLUMNS = [
    "Treasury Shares Number", "Ordinary Shares Number", "Share Issued", "Net Debt", "Total Debt",
    "Tangible Book Value", "Invested Capital", "Working Capital", "Net Tangible Assets",
    "Capital Lease Obligations", "Common Stock Equity", "Total Capitalization",
    "Total Equity Gross Minority Interest", "Stockholders Equity",
    "Gains Losses Not Affecting Retained Earnings", "Other Equity Adjustments",
    "Retained Earnings", "Capital Stock", "Common Stock",
    "Total Liabilities Net Minority Interest", "Total Non Current Liabilities Net Minority Interest",
    "Other Non Current Liabilities", "Tradeand Other Payables Non Current",
    "Long Term Debt And Capital Lease Obligation", "Long Term Capital Lease Obligation",
    "Long Term Debt", "Current Liabilities", "Other Current Liabilities",
    "Current Deferred Liabilities", "Current Deferred Revenue",
    "Current Debt And Capital Lease Obligation", "Current Capital Lease Obligation",
    "Current Debt", "Other Current Borrowings", "Commercial Paper",
    "Payables And Accrued Expenses", "Current Accrued Expenses", "Payables",
    "Total Tax Payable", "Income Tax Payable", "Accounts Payable",
    "Total Assets", "Total Non Current Assets", "Other Non Current Assets",
    "Non Current Deferred Assets", "Non Current Deferred Taxes Assets",
    "Investments And Advances", "Other Investments", "Investmentin Financial Assets",
    "Available For Sale Securities", "Net PPE", "Accumulated Depreciation",
    "Gross PPE", "Leases", "Other Properties", "Machinery Furniture Equipment",
    "Land And Improvements", "Properties", "Current Assets", "Other Current Assets",
    "Inventory", "Receivables", "Other Receivables", "Accounts Receivable",
    "Cash Cash Equivalents And Short Term Investments", "Other Short Term Investments",
    "Cash And Cash Equivalents", "Cash Equivalents", "Cash Financial"
]

# Income Statement columns from yfinance
INCOME_STATEMENT_COLUMNS = [
    "Tax Effect Of Unusual Items", "Tax Rate For Calcs", "Normalized EBITDA",
    "Net Income From Continuing Operation Net Minority Interest", "Reconciled Depreciation",
    "Reconciled Cost Of Revenue", "EBITDA", "EBIT", "Net Interest Income",
    "Interest Expense", "Interest Income", "Normalized Income",
    "Net Income From Continuing And Discontinued Operation", "Total Expenses",
    "Total Operating Income As Reported", "Diluted Average Shares", "Basic Average Shares",
    "Diluted EPS", "Basic EPS", "Diluted NI Availto Com Stockholders",
    "Net Income Common Stockholders", "Net Income", "Net Income Including Noncontrolling Interests",
    "Net Income Continuous Operations", "Tax Provision", "Pretax Income",
    "Other Income Expense", "Other Non Operating Income Expenses",
    "Net Non Operating Interest Income Expense", "Interest Expense Non Operating",
    "Interest Income Non Operating", "Operating Income", "Operating Expense",
    "Research And Development", "Selling General And Administration", "Gross Profit",
    "Cost Of Revenue", "Total Revenue", "Operating Revenue"
]

# Cash Flow columns from yfinance
CASH_FLOW_COLUMNS = [
    "Free Cash Flow", "Repurchase Of Capital Stock", "Repayment Of Debt",
    "Issuance Of Debt", "Issuance Of Capital Stock", "Capital Expenditure",
    "Interest Paid Supplemental Data", "Income Tax Paid Supplemental Data",
    "End Cash Position", "Beginning Cash Position", "Changes In Cash",
    "Financing Cash Flow", "Cash Flow From Continuing Financing Activities",
    "Net Other Financing Charges", "Cash Dividends Paid", "Common Stock Dividend Paid",
    "Net Common Stock Issuance", "Common Stock Payments", "Common Stock Issuance",
    "Net Issuance Payments Of Debt", "Net Short Term Debt Issuance",
    "Net Long Term Debt Issuance", "Long Term Debt Payments", "Long Term Debt Issuance",
    "Investing Cash Flow", "Cash Flow From Continuing Investing Activities",
    "Net Other Investing Changes", "Net Investment Purchase And Sale",
    "Sale Of Investment", "Purchase Of Investment", "Net Business Purchase And Sale",
    "Purchase Of Business", "Net PPE Purchase And Sale", "Purchase Of PPE",
    "Operating Cash Flow", "Cash Flow From Continuing Operating Activities",
    "Change In Working Capital", "Change In Other Working Capital",
    "Change In Other Current Liabilities", "Change In Other Current Assets",
    "Change In Payables And Accrued Expense", "Change In Payable",
    "Change In Account Payable", "Change In Inventory", "Change In Receivables",
    "Changes In Account Receivables", "Other Non Cash Items", "Stock Based Compensation",
    "Deferred Tax", "Deferred Income Tax", "Depreciation Amortization Depletion",
    "Depreciation And Amortization", "Net Income From Continuing Operations"
]

def expand_table_schema(conn, table_name, columns):
    """Add missing columns to financial statement table"""
    cur = conn.cursor()

    added = 0
    for col in columns:
        sql_col = normalize_column_name(col)

        # Check if column exists
        cur.execute(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        """, (table_name, sql_col))

        if not cur.fetchone():
            # Add column
            try:
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {sql_col} BIGINT")
                conn.commit()
                added += 1
                print(f"  [+] Added {sql_col}")
            except Exception as e:
                print(f"  [!] Failed to add {sql_col}: {e}")
                conn.rollback()

    cur.close()
    return added

def main():
    try:
        conn = get_db_connection()

        print("\nExpanding Financial Statement Table Schemas...")
        print("=" * 60)

        print("\nBalance Sheet Table (annual_balance_sheet)...")
        added = expand_table_schema(conn, 'annual_balance_sheet', BALANCE_SHEET_COLUMNS)
        print(f"Added {added} new columns\n")

        print("Quarterly Balance Sheet Table (quarterly_balance_sheet)...")
        added = expand_table_schema(conn, 'quarterly_balance_sheet', BALANCE_SHEET_COLUMNS)
        print(f"Added {added} new columns\n")

        print("Income Statement Table (annual_income_statement)...")
        added = expand_table_schema(conn, 'annual_income_statement', INCOME_STATEMENT_COLUMNS)
        print(f"Added {added} new columns\n")

        print("Quarterly Income Statement Table (quarterly_income_statement)...")
        added = expand_table_schema(conn, 'quarterly_income_statement', INCOME_STATEMENT_COLUMNS)
        print(f"Added {added} new columns\n")

        print("Cash Flow Table (annual_cash_flow)...")
        added = expand_table_schema(conn, 'annual_cash_flow', CASH_FLOW_COLUMNS)
        print(f"Added {added} new columns\n")

        print("Quarterly Cash Flow Table (quarterly_cash_flow)...")
        added = expand_table_schema(conn, 'quarterly_cash_flow', CASH_FLOW_COLUMNS)
        print(f"Added {added} new columns\n")

        conn.close()
        print("[OK] Schema expansion complete!")

    except Exception as e:
        print(f"[ERROR] Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
