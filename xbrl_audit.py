#!/usr/bin/env python3
"""Audit XBRL extraction for companies with 0% net income coverage.

Tests what SEC XBRL concepts are actually available for problem companies
and identifies why net_income extraction is failing.
"""

import json
from utils.external.sec_statements import get_income_statement, _aggregate_concepts
from utils.external.sec_edgar_client import SecEdgarClient

# Problem companies identified in /goal
PROBLEM_COMPANIES = [
    "GLD",   # SPDR Gold Trust (ETF)
    "IAC",   # InterActiveCorp
    "EE",    # iShares MSCI EAFE (ETF)
    "RANI",  # Aytu BioPharma (small-cap)
    "CWAN",  # China Pharma Holdings (ADR)
    "ONON",  # On Holding (footwear)
    "SNGX",  # Singe Holdings (small-cap)
    "AIFC",  # AIF Holdings
    "JHG",   # Janus Henderson Group
    "ATHE",  # Athena Health (acquired, delisted or special entity)
]

def audit_company(client: SecEdgarClient, symbol: str):
    """Audit what XBRL concepts a company actually reports."""
    print(f"\n{'='*70}")
    print(f"AUDITING {symbol}")
    print(f"{'='*70}")

    try:
        cik = client.symbol_to_cik(symbol)
        print(f"CIK: {cik}")
    except Exception as e:
        print(f"ERROR: Could not find CIK for {symbol}: {e}")
        return

    # Get all facts
    try:
        all_facts = client.get_company_facts(cik)
        print(f"[OK] Got company facts")
    except FileNotFoundError:
        print(f"[NO] No XBRL filings found (company doesn't file XBRL)")
        return
    except Exception as e:
        print(f"[ERR] Error fetching facts: {e}")
        return

    facts = all_facts.get("facts", {})
    us_gaap = facts.get("us-gaap", {})
    ifrs = facts.get("ifrs-full", {})

    print(f"Taxonomies available:")
    print(f"  - us-gaap: {len(us_gaap)} concepts")
    print(f"  - ifrs-full: {len(ifrs)} concepts")

    # Check for net income concepts
    net_income_concepts = [
        "NetIncomeLoss",         # us-gaap standard
        "ProfitLoss",            # ifrs-full standard
        "ProfitLossAttributableToOwnersOfParent",  # ifrs variant
        "ComprehensiveIncome",   # might be used instead
        "ProfitForThePeriod",    # alternative ifrs
        "IncomeLoss",            # general variant
        "NetIncomeAttributableToNoncontrollingInterest",  # subsidiary variant
    ]

    print(f"\nChecking net income concepts:")
    found_net_income = False
    for concept in net_income_concepts:
        if concept in us_gaap:
            units = us_gaap[concept].get("units", {})
            filing_count = sum(len(v) for v in units.values())
            print(f"  [Y] {concept:45} (us-gaap): {filing_count:3} filings")
            if filing_count > 0:
                found_net_income = True
        elif concept in ifrs:
            units = ifrs[concept].get("units", {})
            filing_count = sum(len(v) for v in units.values())
            print(f"  [Y] {concept:45} (ifrs-full): {filing_count:3} filings")
            if filing_count > 0:
                found_net_income = True
        else:
            print(f"  [N] {concept:45} (not found)")

    if not found_net_income:
        print(f"\n  [WARN] NO NET INCOME CONCEPTS FOUND!")

        # Look for revenue as alternative
        print(f"\n  Checking for revenue concepts:")
        revenue_concepts = ["Revenues", "Revenue", "RevenueFromContractsWithCustomers", "SalesRevenueNet"]
        for concept in revenue_concepts:
            if concept in us_gaap:
                units = us_gaap[concept].get("units", {})
                filing_count = sum(len(v) for v in units.values())
                print(f"    [Y] {concept:40} (us-gaap): {filing_count:3} filings")
            elif concept in ifrs:
                units = ifrs[concept].get("units", {})
                filing_count = sum(len(v) for v in units.values())
                print(f"    [Y] {concept:40} (ifrs-full): {filing_count:3} filings")

    # Check entity type
    entity_data = all_facts.get("entity", {})
    entity_type = entity_data.get("entityType", "unknown")
    print(f"\nEntity Type: {entity_type}")

    # Try extraction
    print(f"\nTesting get_income_statement():")
    try:
        statements = get_income_statement(client, symbol, period="annual")
        print(f"  [OK] Got {len(statements)} annual income statements")
        if statements:
            latest = statements[-1]
            net_income = latest.get("net_income_loss")
            revenues = latest.get("revenues") or latest.get("sales_revenue_net")
            print(f"    Latest year: {latest.get('fiscal_year')}")
            print(f"      - net_income_loss: {net_income}")
            print(f"      - revenues: {revenues}")
    except ValueError as e:
        print(f"  [ERR] ValueError: {e}")
    except Exception as e:
        print(f"  [ERR] Exception: {e}")


def main():
    client = SecEdgarClient()

    for symbol in PROBLEM_COMPANIES:
        try:
            audit_company(client, symbol)
        except Exception as e:
            print(f"\n{'='*70}")
            print(f"ERROR AUDITING {symbol}: {e}")
            print(f"{'='*70}")


if __name__ == "__main__":
    main()
