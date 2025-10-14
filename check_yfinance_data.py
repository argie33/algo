#!/usr/bin/env python3
"""
Check what financial metrics are available from yfinance ticker.info and key_statistics
to determine optimal data sources for quality and growth metrics.
"""

import yfinance as yf
import json
from pprint import pprint

# Test with a sample ticker
symbol = "AAPL"
ticker = yf.Ticker(symbol)

print(f"\n{'='*80}")
print(f"CHECKING YFINANCE DATA AVAILABILITY FOR {symbol}")
print(f"{'='*80}\n")

# Get basic ticker info
print("1. TICKER.INFO (Basic Information)")
print("-" * 80)
info = ticker.info
if info:
    # Quality-related metrics
    quality_related = {
        'currentRatio': info.get('currentRatio'),
        'quickRatio': info.get('quickRatio'),
        'debtToEquity': info.get('debtToEquity'),
        'totalDebt': info.get('totalDebt'),
        'totalCash': info.get('totalCash'),
        'freeCashflow': info.get('freeCashflow'),
        'operatingCashflow': info.get('operatingCashflow'),
        'totalRevenue': info.get('totalRevenue'),
        'ebitda': info.get('ebitda'),
        'netIncomeToCommon': info.get('netIncomeToCommon'),
        'returnOnAssets': info.get('returnOnAssets'),
        'returnOnEquity': info.get('returnOnEquity'),
    }

    print("\nQuality-Related Metrics from ticker.info:")
    for key, value in quality_related.items():
        print(f"  {key}: {value}")

    # Growth-related metrics
    growth_related = {
        'revenueGrowth': info.get('revenueGrowth'),
        'earningsGrowth': info.get('earningsGrowth'),
        'earningsQuarterlyGrowth': info.get('earningsQuarterlyGrowth'),
        'revenuePerShare': info.get('revenuePerShare'),
        'profitMargins': info.get('profitMargins'),
        'grossMargins': info.get('grossMargins'),
        'operatingMargins': info.get('operatingMargins'),
        'trailingEps': info.get('trailingEps'),
        'forwardEps': info.get('forwardEps'),
    }

    print("\nGrowth-Related Metrics from ticker.info:")
    for key, value in growth_related.items():
        print(f"  {key}: {value}")
else:
    print("  No ticker.info data available")

# Get financial statements for comparison
print(f"\n2. QUARTERLY FINANCIAL STATEMENTS")
print("-" * 80)

print("\n  a) Quarterly Income Statement (latest):")
quarterly_income = ticker.quarterly_income_stmt
if not quarterly_income.empty:
    print(f"     Columns: {quarterly_income.columns.tolist()[:5]}")  # Show first 5 dates
    print(f"     Available fields: {quarterly_income.index.tolist()[:15]}")  # Show first 15 fields
else:
    print("     No quarterly income statement data")

print("\n  b) Quarterly Balance Sheet (latest):")
quarterly_balance = ticker.quarterly_balance_sheet
if not quarterly_balance.empty:
    print(f"     Columns: {quarterly_balance.columns.tolist()[:5]}")
    print(f"     Available fields: {quarterly_balance.index.tolist()[:15]}")
else:
    print("     No quarterly balance sheet data")

print("\n  c) Quarterly Cash Flow (latest):")
quarterly_cashflow = ticker.quarterly_cashflow
if not quarterly_cashflow.empty:
    print(f"     Columns: {quarterly_cashflow.columns.tolist()[:5]}")
    print(f"     Available fields: {quarterly_cashflow.index.tolist()[:15]}")
else:
    print("     No quarterly cash flow data")

# Check if we can get historical data for growth calculations
print(f"\n3. HISTORICAL DATA FOR GROWTH CALCULATIONS")
print("-" * 80)

print("\n  a) Annual Financials:")
annual_income = ticker.income_stmt
if not annual_income.empty:
    print(f"     Available years: {annual_income.columns.tolist()}")
    print(f"     Can calculate 3-year CAGR: {len(annual_income.columns) >= 3}")
else:
    print("     No annual income statement data")

print("\n  b) Financial Data:")
financials = ticker.financials
if not financials.empty:
    print(f"     Available years: {financials.columns.tolist()}")
else:
    print("     No financials data")

# Summary and recommendations
print(f"\n{'='*80}")
print("SUMMARY AND RECOMMENDATIONS")
print(f"{'='*80}\n")

print("QUALITY METRICS COMPARISON:")
print("-" * 80)
print("\n1. Current Ratio:")
print("   - Available from ticker.info: YES (currentRatio)")
print("   - Calculated from quarterly: YES (Current Assets / Current Liabilities)")
print("   → RECOMMENDATION: Use ticker.info (simpler, already calculated)\n")

print("2. Debt-to-Equity:")
print("   - Available from ticker.info: YES (debtToEquity)")
print("   - Calculated from quarterly: YES (Total Debt / Total Equity)")
print("   → RECOMMENDATION: Use ticker.info (simpler, already calculated)\n")

print("3. Free Cash Flow to Net Income:")
print("   - Available from ticker.info: PARTIAL (freeCashflow, netIncomeToCommon)")
print("   - Calculated from quarterly: YES (requires both cash flow and income statements)")
print("   → RECOMMENDATION: Use ticker.info for both values, calculate ratio\n")

print("4. Accruals Ratio:")
print("   - Available from ticker.info: NO")
print("   - Calculated from quarterly: YES ((Net Income - Operating CF) / Total Assets)")
print("   → RECOMMENDATION: Must calculate from quarterly statements\n")

print("5. Interest Coverage:")
print("   - Available from ticker.info: NO")
print("   - Calculated from quarterly: YES (Operating Income / Interest Expense)")
print("   → RECOMMENDATION: Must calculate from quarterly statements\n")

print("6. Asset Turnover:")
print("   - Available from ticker.info: NO")
print("   - Calculated from quarterly: YES (Revenue / Avg Total Assets)")
print("   → RECOMMENDATION: Must calculate from quarterly statements\n")

print("\nGROWTH METRICS COMPARISON:")
print("-" * 80)
print("\n1. Revenue Growth:")
print("   - Available from ticker.info: YES (revenueGrowth - YoY)")
print("   - Calculated from statements: YES (3-year CAGR from annual data)")
print("   → RECOMMENDATION: ticker.info for YoY, calculate 3Y CAGR from annual\n")

print("2. Earnings Growth:")
print("   - Available from ticker.info: YES (earningsGrowth, earningsQuarterlyGrowth)")
print("   - Calculated from statements: YES (3-year CAGR from annual data)")
print("   → RECOMMENDATION: ticker.info for YoY, calculate 3Y CAGR from annual\n")

print("3. ROE and ROE Trend:")
print("   - Available from ticker.info: YES (returnOnEquity - current)")
print("   - Calculated from statements: YES (need historical for trend)")
print("   → RECOMMENDATION: ticker.info for current, need historical for trend calculation\n")

print("4. Sustainable Growth Rate:")
print("   - Available from ticker.info: NO (need ROE and payout ratio)")
print("   - Calculated from statements: YES (ROE × (1 - Payout Ratio))")
print("   → RECOMMENDATION: Calculate using ticker.info ROE if available\n")

print("\nOVERALL STRATEGY:")
print("-" * 80)
print("✓ Use ticker.info for: currentRatio, debtToEquity, freeCashflow/netIncome ratio,")
print("                        ROE (current), revenue/earnings growth (YoY)")
print("✗ Must calculate from quarterly: accruals_ratio, interest_coverage, asset_turnover")
print("~ Hybrid approach: Use ticker.info when available, fall back to calculations")
print("\n")
