import yfinance as yf
import pandas as pd

# Test a ticker that should have analyst data
ticker = yf.Ticker('AAPL')
df = ticker.upgrades_downgrades

if df is not None and not df.empty:
    print("DataFrame shape:", df.shape)
    print("\nColumn names:")
    print(df.columns.tolist())
    print("\nFirst few rows:")
    print(df.head())
    print("\nIndex name:")
    print(df.index.name)
    print("\nSample row data:")
    for i, (dt, row) in enumerate(df.head(3).iterrows()):
        print(f"\nRow {i}:")
        print(f"  Date: {dt}")
        print(f"  Row data: {dict(row)}")
        for col in df.columns:
            print(f"  {col}: {row.get(col, 'N/A')}")
else:
    print("No data found")
