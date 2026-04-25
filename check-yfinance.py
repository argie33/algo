import yfinance as yf

# Get AAPL data
ticker = yf.Ticker("AAPL")

# Get balance sheet
bs = ticker.balance_sheet

if bs is not None and len(bs) > 0:
    print("Balance Sheet Columns Available from yfinance:")
    print("=" * 60)
    for idx, col in enumerate(bs.index, 1):
        print(f"{idx:2}. {col}")
    print(f"\nTotal: {len(bs.index)} columns")
    print(f"Fiscal Years Available: {len(bs.columns)}")
else:
    print("No balance sheet data available")

print("\n" + "=" * 60)

# Get income statement
income = ticker.income_stmt

if income is not None and len(income) > 0:
    print("\nIncome Statement Columns Available from yfinance:")
    print("=" * 60)
    for idx, col in enumerate(income.index, 1):
        print(f"{idx:2}. {col}")
    print(f"\nTotal: {len(income.index)} columns")
    print(f"Fiscal Years Available: {len(income.columns)}")
else:
    print("No income statement data available")

print("\n" + "=" * 60)

# Get cash flow
cf = ticker.cashflow

if cf is not None and len(cf) > 0:
    print("\nCash Flow Columns Available from yfinance:")
    print("=" * 60)
    for idx, col in enumerate(cf.index, 1):
        print(f"{idx:2}. {col}")
    print(f"\nTotal: {len(cf.index)} columns")
    print(f"Fiscal Years Available: {len(cf.columns)}")
else:
    print("No cash flow data available")
