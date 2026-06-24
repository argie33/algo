#!/usr/bin/env python3
"""SEC EDGAR financial statement extractors.

High-level helpers for extracting balance sheet, income statement, and cash flow data.
These methods leverage the SecEdgarClient for company facts and aggregate multiple
GAAP concepts into structured financial statements.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_balance_sheet(client: Any, symbol: str, period: str = "annual") -> list[dict[str, Any]]:
    """Aggregate balance sheet rows from key concepts.

    Args:
        client: SecEdgarClient instance
        symbol: Stock ticker
        period: "annual" or "quarterly"

    Returns:
        List of dicts with balance sheet data keyed by fiscal year/period
    """
    concepts = [
        "Assets",
        "AssetsCurrent",
        "Liabilities",
        "LiabilitiesCurrent",
        "StockholdersEquity",
        "CashAndCashEquivalentsAtCarryingValue",
        "AccountsReceivableNetCurrent",
        "InventoryNet",
        "PropertyPlantAndEquipmentNet",
        "Goodwill",
        "LongTermDebt",
    ]
    return _aggregate_concepts(client, symbol, concepts, period)


def get_income_statement(client: Any, symbol: str, period: str = "annual") -> list[dict[str, Any]]:
    """Aggregate income statement rows from key concepts.

    Args:
        client: SecEdgarClient instance
        symbol: Stock ticker
        period: "annual" or "quarterly"

    Returns:
        List of dicts with income statement data keyed by fiscal year/period
    """
    concepts = [
        "Revenues",
        "SalesRevenueNet",
        # Post-ASC 606 (post-2018) revenue concepts used by most large-cap companies:
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "CostOfRevenue",
        "CostsAndExpenses",
        "GrossProfit",
        "OperatingExpenses",
        "OperatingIncomeLoss",
        "NetIncomeLoss",
        "EarningsPerShareBasic",
        "EarningsPerShareDiluted",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ]
    return _aggregate_concepts(client, symbol, concepts, period)


def get_cash_flow(client: Any, symbol: str, period: str = "annual") -> list[dict[str, Any]]:
    """Aggregate cash flow rows from key concepts.

    Args:
        client: SecEdgarClient instance
        symbol: Stock ticker
        period: "annual" or "quarterly"

    Returns:
        List of dicts with cash flow data keyed by fiscal year/period
    """
    concepts = [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInInvestingActivities",
        "NetCashProvidedByUsedInFinancingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "Depreciation",
        "DepreciationAndAmortization",
    ]
    return _aggregate_concepts(client, symbol, concepts, period)


def _aggregate_concepts(
    client: Any,
    symbol: str,
    concepts: list[str],
    period: str,
) -> list[dict[str, Any]]:
    """Pivot multiple concepts into rows keyed by (fiscal_year, fiscal_period).

    Optimized: Uses get_company_facts (1 API call) instead of multiple get_concept calls.
    Gracefully skips concepts that don't exist for this company (e.g., different revenue
    reporting standards across companies).

    Args:
        client: SecEdgarClient instance
        symbol: Stock ticker
        concepts: List of XBRL concept names (will skip those not reported by this company)
        period: "annual" or "quarterly"

    Returns:
        List of dicts with aggregated concept data
    """
    cik = client.symbol_to_cik(symbol)

    # Fetch all facts for this company in a single API call.
    # FileNotFoundError (404) means the CIK has no XBRL filings — mutual funds,
    # special-purpose vehicles, and some investment trusts never file XBRL.
    try:
        all_facts = client.get_company_facts(cik)
    except FileNotFoundError:
        return []

    # Extract concepts from all_facts (us-gaap taxonomy).
    # Some entities (ETFs, foreign filers) have CIKs but report under IFRS
    # or a non-US-GAAP taxonomy — return empty for those too.
    facts = all_facts.get("facts")
    if facts is None:
        logger.debug(f"SEC API returned no 'facts' in company filings for CIK {cik}")
        return []
    us_gaap_facts = facts.get("us-gaap")
    if not us_gaap_facts:
        logger.debug(f"SEC API has no US-GAAP facts for CIK {cik} (possibly IFRS filer)")
        return []
    rows: dict[Any, dict[str, Any]] = {}
    fp_filter = "FY" if period == "annual" else ("Q1", "Q2", "Q3", "Q4")

    for concept in concepts:
        concept_data = us_gaap_facts.get(concept)
        if concept_data is None:
            continue

        units = concept_data.get("units")
        if not units:
            continue

        for _unit, entries in units.items():
            for entry in entries:
                fp = entry.get("fp")
                if period == "annual" and fp != "FY":
                    continue
                if period == "quarterly" and fp not in fp_filter:
                    continue

                # Use period end year as the fiscal year key, not SEC's fy field.
                # SEC tags ALL periods in a 10-K with fy=FILING_YEAR — so prior-year
                # comparison data (end='2022-06-30') included in a FY2024 10-K would
                # have fy=2024 instead of fy=2022. Deriving year from end date correctly
                # separates current-year data from the multi-year comparison tables.
                end_date = entry.get("end", "")
                period_year = int(end_date[:4]) if end_date and len(end_date) >= 4 else entry.get("fy")

                key = (
                    period_year,
                    fp if period == "quarterly" else "FY",
                )
                row = rows.setdefault(
                    key,
                    {
                        "symbol": symbol,
                        "fiscal_year": period_year,
                        "fiscal_period": fp if period == "quarterly" else "FY",
                        "period_end": end_date,
                        "filed": entry.get("filed"),
                        "form": entry.get("form"),
                    },
                )
                # Snake-case the concept for column compatibility
                col = _to_snake(concept)
                # Keep latest filing if multiple for same period
                entry_filed = entry.get("filed") or ""
                row_filed = row.get(f"_filed_{col}") or ""
                if col not in row or entry_filed > row_filed:
                    row[col] = entry.get("val")
                    row[f"_filed_{col}"] = entry.get("filed")

    # Drop helper fields, return sorted
    result = []
    for row in rows.values():
        result.append({k: v for k, v in row.items() if not k.startswith("_filed_")})
    result.sort(key=lambda r: (r["fiscal_year"] or 0, r["fiscal_period"]))
    return result


def _to_snake(name: str) -> str:
    """CamelCase → snake_case. Used for converting XBRL concept names to columns."""
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not name[i - 1].isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out)
