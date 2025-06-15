import yfinance as yf
import pandas as pd

# Test the fixed mapping logic
ticker = yf.Ticker('AAPL')
df = ticker.upgrades_downgrades

if df is not None and not df.empty:
    print("Testing data mapping for first few rows:")
    
    for i, (dt, row) in enumerate(df.head(5).iterrows()):
        # Simulate the mapping from the script
        symbol = "AAPL"
        firm = row.get("Firm")
        action = row.get("priceTargetAction")  # Fixed mapping
        from_grade = row.get("FromGrade")
        to_grade = row.get("ToGrade")
        
        # Handle date
        if hasattr(dt, 'date'):
            date_value = dt.date()
        else:
            date_value = dt
            
        print(f"\nRow {i+1}:")
        print(f"  Symbol: {symbol}")
        print(f"  Firm: {firm}")
        print(f"  Action: {action}")
        print(f"  From Grade: {from_grade}")
        print(f"  To Grade: {to_grade}")
        print(f"  Date: {date_value}")
        
        # Check for missing data
        missing_fields = []
        if not firm: missing_fields.append("Firm")
        if not action: missing_fields.append("Action")
        if not from_grade: missing_fields.append("FromGrade")
        if not to_grade: missing_fields.append("ToGrade")
        
        if missing_fields:
            print(f"  ⚠️  Missing: {', '.join(missing_fields)}")
        else:
            print(f"  ✅ All fields populated")
else:
    print("No data found")
