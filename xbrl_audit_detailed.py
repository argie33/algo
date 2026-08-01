#!/usr/bin/env python3
"""Deep dive into why extraction returns None despite data existing."""

from utils.external.sec_edgar_client import SecEdgarClient

def debug_extraction(symbol: str):
    """Debug why extraction returns None when data exists."""
    print(f"\n{'='*70}")
    print(f"DETAILED DEBUG: {symbol}")
    print(f"{'='*70}")

    client = SecEdgarClient()
    cik = client.symbol_to_cik(symbol)
    all_facts = client.get_company_facts(cik)

    facts = all_facts.get("facts", {})
    us_gaap = facts.get("us-gaap", {})
    ifrs = facts.get("ifrs-full", {})

    # Check the actual NetIncomeLoss data
    if "NetIncomeLoss" in us_gaap:
        concept_data = us_gaap["NetIncomeLoss"]
        print(f"\nNetIncomeLoss raw structure:")
        print(f"  Keys: {list(concept_data.keys())}")

        units = concept_data.get("units", {})
        print(f"  Units: {list(units.keys())[:5]}... ({len(units)} total)")

        # Check first unit's entries
        if units:
            first_unit = list(units.keys())[0]
            entries = units[first_unit]
            print(f"\n  First unit ({first_unit}): {len(entries)} entries")
            if entries:
                entry = entries[0]
                print(f"    First entry keys: {list(entry.keys())}")
                print(f"    First entry: {entry}")

                # Check period filter
                fp = entry.get("fp")
                print(f"    fp (fiscal period): {fp} (should match 'FY' for annual)")

        # Look at ALL annual period entries
        annual_count = 0
        for unit, entries in units.items():
            for entry in entries:
                if entry.get("fp") == "FY":
                    annual_count += 1
                    if annual_count == 1:
                        print(f"\n  Sample annual entry (fp=FY):")
                        print(f"    val: {entry.get('val')}")
                        print(f"    end: {entry.get('end')}")
                        print(f"    filed: {entry.get('filed')}")

        print(f"\n  Total annual entries (fp=FY): {annual_count}")

    # Check if we're actually extracting correctly with a mock
    print(f"\n\nSimulating extraction logic:")
    rows = {}

    concept_data = us_gaap.get("NetIncomeLoss")
    if concept_data:
        units = concept_data.get("units", {})
        if units:
            print(f"  Found {len(units)} units in NetIncomeLoss")
            for unit, entries in units.items():
                print(f"    Unit '{unit}': {len(entries)} entries")
                for i, entry in enumerate(entries[:3]):  # Show first 3
                    fp = entry.get("fp")
                    end = entry.get("end")
                    val = entry.get("val")
                    filed = entry.get("filed")
                    print(f"      [{i}] fp={fp}, end={end}, val={val}, filed={filed}")

                    # Check period filter
                    if fp == "FY":
                        period_year = int(end[:4]) if end and len(end) >= 4 else entry.get("fy")
                        key = (period_year, "FY")
                        print(f"          -> Would create row key: {key}")
                        row = rows.setdefault(key, {"symbol": symbol, "fiscal_year": period_year, "fiscal_period": "FY"})
                        row["net_income_loss"] = val
        else:
            print(f"  No units found!")
    else:
        print(f"  NetIncomeLoss not in us_gaap")

    print(f"\nFinal rows: {len(rows)}")
    for key, row in list(rows.items())[:3]:
        print(f"  {key}: net_income_loss={row.get('net_income_loss')}")


# Test the problem companies
for symbol in ["GLD", "EE", "AIFC"]:
    try:
        debug_extraction(symbol)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
