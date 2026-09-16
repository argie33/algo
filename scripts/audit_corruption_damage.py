#!/usr/bin/env python3
"""Full audit of data corrupted by blind yfinance repairs."""

import json
import sys

sys.path.insert(0, ".")

from utils.db import get_db_connection

db = get_db_connection()
cursor = db.cursor()

# Get ALL corrupted records (not just top 100)
cursor.execute("""
    SELECT DISTINCT
        symbol,
        our_table,
        our_field,
        fiscal_year,
        yfinance_value::text as yfinance_value,
        ratio
    FROM xbrl_yfinance_line_item_report
    WHERE divergent = true
    ORDER BY ratio DESC, symbol, fiscal_year
""")

print("COMPLETE AUDIT OF DATA CORRUPTION FROM BLIND YFINANCE REPAIRS")
print("=" * 80)
print()

corrupted_records = []
audit_file = "/tmp/corruption_audit.json"

candidates = cursor.fetchall()
for symbol, table, field, fiscal_year, yfinance_value, ratio in candidates:
    # Get current value
    query = f"SELECT {field} FROM {table} WHERE symbol = %s AND fiscal_year = %s"
    cursor.execute(query, (symbol, fiscal_year))
    result = cursor.fetchone()

    if result:
        current_value = result[0]
        # If current value matches yfinance value, it was "fixed" by our script
        if current_value == float(yfinance_value) if yfinance_value else current_value == yfinance_value:
            corrupted_records.append(
                {
                    "symbol": symbol,
                    "table": table,
                    "field": field,
                    "fiscal_year": fiscal_year,
                    "corrupted_value": current_value,
                    "ratio": float(ratio),
                }
            )

print(f"TOTAL CORRUPTED RECORDS: {len(corrupted_records)}")
print()

# Group by severity
severe = [r for r in corrupted_records if r["ratio"] > 1000]
moderate = [r for r in corrupted_records if 100 < r["ratio"] <= 1000]
mild = [r for r in corrupted_records if r["ratio"] <= 100]

print(f"Severe (ratio > 1000x): {len(severe)}")
print(f"Moderate (100x < ratio <= 1000x): {len(moderate)}")
print(f"Mild (ratio <= 100x): {len(mild)}")
print()

# Save audit to file for recovery
with open(audit_file, "w") as f:
    json.dump(corrupted_records, f, indent=2, default=str)

print(f"Corruption audit saved to: {audit_file}")
print()

# Show top 20 by severity
print("TOP 20 CORRUPTED RECORDS BY SEVERITY:")
print()
for i, record in enumerate(sorted(corrupted_records, key=lambda x: x["ratio"], reverse=True)[:20], 1):
    print(
        f"{i}. {record['symbol']:8} FY{record['fiscal_year']} {record['field']:30}: "
        f"value={record['corrupted_value']:15} (ratio={record['ratio']:.0f}x)"
    )

cursor.close()
db.close()
