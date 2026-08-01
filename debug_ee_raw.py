#!/usr/bin/env python3
"""Debug EE raw XBRL data."""

from utils.external.sec_edgar_client import SecEdgarClient

client = SecEdgarClient()
cik = client.symbol_to_cik("EE")
all_facts = client.get_company_facts(cik)

facts = all_facts.get("facts", {})
us_gaap = facts.get("us-gaap", {})

if "NetIncomeLoss" in us_gaap:
    concept_data = us_gaap["NetIncomeLoss"]
    units = concept_data.get("units", {})

    print("All NetIncomeLoss entries for EE:")
    for unit, entries in units.items():
        print(f"\n{unit}: {len(entries)} entries")
        for i, entry in enumerate(entries):
            print(f"  [{i}] end={entry.get('end')}, fp={entry.get('fp')}, val={entry.get('val')}, form={entry.get('form')}")
