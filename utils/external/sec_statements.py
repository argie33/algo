#!/usr/bin/env python3
"""SEC EDGAR financial statement extractors.

High-level helpers for extracting balance sheet, income statement, and cash flow data.
These methods leverage the SecEdgarClient for company facts and aggregate multiple
GAAP concepts into structured financial statements.

Foreign private issuers (20-F/40-F filers - ADRs like ABEV, E, AEG, ACB, IBN) report
under the IFRS taxonomy (facts["ifrs-full"]) instead of, or in addition to, us-gaap.
Many report ZERO us-gaap concepts (e.g. ABEV: 0 us-gaap, 298 ifrs-full), so extracting
only us-gaap silently drops fundamental data SEC EDGAR actually has for these filers.
Each concept list below is followed by an IFRS_ALIASES list: (ifrs_concept, target_key)
pairs where target_key is the SAME snake_cased key the equivalent GAAP concept would
produce, so downstream field_mapping in load_financial_statements.py needs no changes -
an IFRS-sourced row looks identical to a GAAP-sourced one once aggregated.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

_BALANCE_IFRS_ALIASES = [
    # (IFRS concept name, target key = _to_snake() of the equivalent GAAP concept)
    ("Assets", "assets"),
    ("CurrentAssets", "assets_current"),
    ("Liabilities", "liabilities"),
    ("CurrentLiabilities", "liabilities_current"),
    ("Equity", "stockholders_equity"),
    ("EquityAttributableToOwnersOfParent", "stockholders_equity"),
    ("CashAndCashEquivalents", "cash_and_cash_equivalents_at_carrying_value"),
    ("TradeAndOtherCurrentReceivables", "accounts_receivable_net_current"),
    ("Inventories", "inventory_net"),
    ("PropertyPlantAndEquipment", "property_plant_and_equipment_net"),
    ("Goodwill", "goodwill"),
    ("NoncurrentLiabilities", "long_term_debt"),
]

_INCOME_IFRS_ALIASES = [
    ("Revenue", "revenues"),
    ("RevenueFromContractsWithCustomers", "revenue_from_contract_with_customer_excluding_assessed_tax"),
    ("RevenueFromSaleOfGoods", "sales_revenue_net"),
    # FIXED 2026-08-01: Add IFRS alias for financial services revenue.
    # Some IFRS-reporting banks may use this concept instead of legacy "Revenue".
    ("RevenuesNetOfInterestExpense", "revenues_net_of_interest_expense"),
    ("CostOfSales", "cost_of_revenue"),
    ("GrossProfit", "gross_profit"),
    ("ProfitLossFromOperatingActivities", "operating_income_loss"),
    ("ProfitLoss", "net_income_loss"),
    # Fixed 2026-07-31: Add fallback IFRS net income concepts for companies that don't report
    # ProfitLoss (ONON reports ProfitLossAttributableToOwnersOfParent; ATHE reports
    # ComprehensiveIncome). These map to the same net_income_loss column downstream, ensuring
    # IFRS-only filers are not silently dropped.
    ("ProfitLossAttributableToOwnersOfParent", "net_income_loss"),
    ("ComprehensiveIncome", "net_income_loss"),
    ("BasicEarningsLossPerShare", "earnings_per_share_basic"),
    ("DilutedEarningsLossPerShare", "earnings_per_share_diluted"),
    # Session 398: EBITDA extraction from IFRS filers
    ("DepreciationAndAmortisation", "depreciation_and_amortization"),
    ("DepreciationExpense", "depreciation"),
]

_CASHFLOW_IFRS_ALIASES = [
    ("CashFlowsFromUsedInOperatingActivities", "net_cash_provided_by_used_in_operating_activities"),
    ("CashFlowsFromUsedInInvestingActivities", "net_cash_provided_by_used_in_investing_activities"),
    ("CashFlowsFromUsedInFinancingActivities", "net_cash_provided_by_used_in_financing_activities"),
    (
        "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets",
        "payments_to_acquire_property_plant_and_equipment",
    ),
    # ("DepreciationExpense", "depreciation") REMOVED 2026-07-28 - see get_cash_flow()'s
    # comment: no destination column exists for cash-flow-context depreciation.
]


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
    return _aggregate_concepts(client, symbol, concepts, period, ifrs_aliases=_BALANCE_IFRS_ALIASES)


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
        # Post-ASC 606 (post-2018) revenue concepts used by most large-cap companies.
        # IncludingAssessedTax must be listed BEFORE ExcludingAssessedTax: both map to
        # the same "revenue" output column (see load_financial_statements.py's
        # _INCOME_FIELD_MAPPING), and the last-listed concept present wins on overwrite.
        # ExcludingAssessedTax (net of sales/excise tax collected as agent) is the
        # standard net-revenue measure most filers use, so it must win when both are
        # reported; IncludingAssessedTax is kept only as a fallback for the minority of
        # filers (e.g. some telecom/utility filers passing through excise tax) that
        # report solely the tax-inclusive tag - previously unmapped entirely, silently
        # dropping their revenue.
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        # FIXED 2026-08-01: RevenuesNetOfInterestExpense for financial services companies.
        # Banks (MS, WFC, etc.) switched from reporting "Revenues" (2007-2019) to
        # "RevenuesNetOfInterestExpense" (2013+) as their primary revenue metric in 2020+.
        # This concept has full 2020+ coverage for financial services while legacy
        # "Revenues" concept stops updating for banks after 2019. Must be listed BEFORE
        # SalesRevenueNet/legacy Revenues so they don't overwrite with zero values.
        # Live-verified: MS has 2020-2026 data, WFC has 2018-2026 data.
        "RevenuesNetOfInterestExpense",
        "CostOfRevenue",
        # REMOVED 2026-07-28: "CostsAndExpenses"/"OperatingExpenses" used to be fetched here
        # as would-be operating_income fallbacks, but neither has a field_mapping entry or
        # destination column, and live-checking real filers missing operating_income (SWK,
        # KMX, BXP - all with NULL operating_income despite real revenue) found zero cases
        # where either concept was present and OperatingIncomeLoss wasn't - the NULLs are
        # explained by fiscal-year filing timing, not a missing concept these would recover.
        # Pure wasted SEC API payload, same class as the cash-flow depreciation fetch
        # removed the same session (see get_cash_flow() below).
        "GrossProfit",
        "OperatingIncomeLoss",
        "NetIncomeLoss",
        "EarningsPerShareBasic",
        "EarningsPerShareDiluted",
        # FIXED 2026-07-28: real, officially-reported weighted-average basic share count -
        # now mapped to annual/quarterly_income_statement.shares_outstanding_basic (migration
        # 1171). Previously fetched every run and silently discarded (no field_mapping entry),
        # while load_sec_valuations.py derived an inferior EPS-rounding-lossy proxy instead
        # (shares = net_income / eps) believing (per its own stale docstring) it was already
        # using this concept.
        "WeightedAverageNumberOfSharesOutstandingBasic",
        # For interest_coverage (quality_metrics) = OperatingIncomeLoss / InterestExpense.
        # No IFRS alias: IFRS "FinanceCosts" is a broader concept (includes non-interest
        # debt costs) and would silently overstate interest expense for foreign filers -
        # leaving it unmapped means those symbols correctly get interest_coverage=NULL
        # instead of a wrong number.
        "InterestExpense",
        # Session 398: For EBITDA calculation = OperatingIncomeLoss + Depreciation + Amortization
        # FIXED 2026-07-28: was "DepreciationExpense", which is not a real us-gaap XBRL
        # concept at all (live-confirmed absent from both AAPL's and MSFT's companyfacts) -
        # the real concept standalone-depreciation filers report is "Depreciation" (present
        # for both). This silently fetched nothing every run since Session 398 introduced
        # it; annual_income_statement.depreciation_expense was 0/61,427 populated. The
        # pre-existing field_mapping key "depreciation" (matching _to_snake("Depreciation"))
        # was already correct and just never received a matching concept to receive.
        "Depreciation",
        "DepreciationAndAmortization",
        "AmortizationOfIntangibles",
    ]
    return _aggregate_concepts(client, symbol, concepts, period, ifrs_aliases=_INCOME_IFRS_ALIASES)


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
        # For value_metrics.dividend_yield = dividends_paid / market_cap. No IFRS alias,
        # same reasoning as InterestExpense above - foreign filers get NULL instead of a
        # guessed value.
        "PaymentsOfDividends",
    ]
    # REMOVED 2026-07-28: "Depreciation"/"DepreciationAndAmortization" (and the matching
    # ("DepreciationExpense", "depreciation") IFRS alias) used to be fetched here too, but
    # annual_cash_flow/quarterly_cash_flow have no depreciation-related column at all (see
    # load_financial_statements.py's _CASHFLOW_FIELD_MAPPING) - every fetch was silently
    # discarded at the schema_cols filter, wasting SEC API payload for data that could never
    # land anywhere. The same EBITDA-relevant depreciation figure is already correctly
    # sourced from get_income_statement()'s own "DepreciationExpense" concept (see the fix
    # to _INCOME_FIELD_MAPPING's "depreciation"/"depreciation_expense" keys, same session) -
    # this was redundant, not a second real source.
    return _aggregate_concepts(client, symbol, concepts, period, ifrs_aliases=_CASHFLOW_IFRS_ALIASES)


def _aggregate_concepts(
    client: Any,
    symbol: str,
    concepts: list[str],
    period: str,
    ifrs_aliases: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Pivot multiple concepts into rows keyed by (fiscal_year, fiscal_period).

    Optimized: Uses get_company_facts (1 API call) instead of multiple get_concept calls.
    Gracefully skips concepts that don't exist for this company (e.g., different revenue
    reporting standards across companies).

    Args:
        client: SecEdgarClient instance
        symbol: Stock ticker
        concepts: List of us-gaap XBRL concept names (skipped if not reported by this company)
        period: "annual" or "quarterly"
        ifrs_aliases: Optional (ifrs_concept, target_key) pairs checked against the
            ifrs-full taxonomy for foreign private issuers (20-F/40-F filers) that
            report no us-gaap concepts at all. target_key is the snake_cased key the
            equivalent us-gaap concept would have produced, so callers/field_mapping
            downstream don't need to know which taxonomy a row actually came from.

    Returns:
        List of dicts with aggregated concept data

    Raises:
        ValueError: If no XBRL filings found (REIT, investment trust, ETF, etc.)
    """
    cik = client.symbol_to_cik(symbol)

    # Fetch all facts for this company in a single API call.
    # FileNotFoundError (404) means the CIK has no XBRL filings - mutual funds,
    # special-purpose vehicles, REITs, and some investment trusts never file XBRL.
    # GOVERNANCE: Fail-fast on missing data with explicit context.
    try:
        all_facts = client.get_company_facts(cik)
    except FileNotFoundError as e:
        raise ValueError(
            f"[SEC_EDGAR] No XBRL filings found for {symbol} (CIK {cik}). "
            f"Company is likely REIT, investment trust, ETF, or special-purpose vehicle "
            f"that does not file traditional SEC XBRL statements. "
            f"Downstream loaders must mark data_unavailable with this reason."
        ) from e

    # Extract concepts from all_facts. Most US domestic filers report under
    # us-gaap; foreign private issuers (20-F/40-F - ADRs like ABEV, E, AEG, ACB)
    # report under ifrs-full instead, often with ZERO us-gaap concepts present.
    # REITs and investment trusts in particular may use real-estate-focused reporting
    # that doesn't map to standard income statement concepts under either taxonomy.
    facts = all_facts.get("facts")
    if facts is None:
        raise ValueError(
            f"[SEC_EDGAR] SEC API returned no 'facts' key for {symbol} (CIK {cik}). "
            f"Likely REIT, investment trust, or special entity without traditional SEC filing data. "
            f"Downstream loaders must mark data_unavailable with this reason."
        )

    us_gaap_facts = facts.get("us-gaap")
    ifrs_facts = facts.get("ifrs-full")
    if not us_gaap_facts and not ifrs_facts:
        raise ValueError(
            f"[SEC_EDGAR] SEC API has no US-GAAP or IFRS facts for {symbol} (CIK {cik}). "
            f"Company may be a REIT, investment trust, or special entity without traditional "
            f"SEC filing data under either taxonomy. "
            f"Downstream loaders must mark data_unavailable with this reason."
        )
    rows: dict[Any, dict[str, Any]] = {}
    fp_filter = "FY" if period == "annual" else ("Q1", "Q2", "Q3", "Q4")

    # (xbrl_concept_name, target_key) pairs to look up, us-gaap first (preserves
    # exact prior behavior/column names), then IFRS aliases for foreign filers.
    concept_specs: list[tuple[str, str]] = [(c, _to_snake(c)) for c in concepts]
    if ifrs_aliases:
        concept_specs.extend(ifrs_aliases)

    for concept, target_key in concept_specs:
        concept_data = us_gaap_facts.get(concept) if us_gaap_facts is not None else None
        if concept_data is None:
            concept_data = ifrs_facts.get(concept) if ifrs_facts is not None else None
        if concept_data is None:
            continue

        units = concept_data.get("units")
        if not units:
            continue

        for _unit, entries in units.items():
            for entry in entries:
                fp = entry.get("fp")
                # Fixed 2026-07-31: For annual extraction, accept quarterly (Q1-Q4), annual (FY),
                # and proxy-statement (fp=None) data. This handles:
                # - Standard annual 10-Ks: fp='FY'
                # - Quarterly-only reporters (ETFs like EE): fp in ('Q1'-'Q4')
                # - Proxy statements with annual data: fp=None (e.g., EE's net income from DEF 14A)
                # Use the end date to derive the fiscal year. This fixes 466 companies (8.4%)
                # with zero net_income coverage because extraction silently skipped them.
                if period == "annual":
                    if fp == "FY" or fp is None or fp in ("Q1", "Q2", "Q3", "Q4"):
                        pass  # Accept annual, proxy, and quarterly data for annual extraction
                    else:
                        continue  # Skip other FP values
                elif period == "quarterly" and fp not in fp_filter:
                    continue

                # Use period end year as the fiscal year key, not SEC's fy field.
                # SEC tags ALL periods in a 10-K with fy=FILING_YEAR - so prior-year
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
                col = target_key
                # Keep latest filing if multiple for same period
                entry_filed = entry.get("filed")
                if not entry_filed:
                    raise ValueError(
                        f"SEC data missing filed date for {symbol} {period}. "
                        f"Cannot determine latest filing without date information. "
                        f"Check SEC data source or API response."
                    )
                row_filed = row.get(f"_filed_{col}")
                if col not in row or (row_filed is None or entry_filed > row_filed):
                    row[col] = entry.get("val")
                    row[f"_filed_{col}"] = entry.get("filed")

    # Drop helper fields, return sorted (require fiscal_year for ordering)
    result = []
    for row in rows.values():
        result.append({k: v for k, v in row.items() if not k.startswith("_filed_")})
    # Validate fiscal_year exists before sorting (critical for financial statement ordering)
    for r in result:
        if r.get("fiscal_year") is None:
            raise ValueError(
                f"SEC statements missing fiscal_year for {symbol} {period}. "
                f"Cannot sort or aggregate financial statements without year information. "
                f"Check SEC data source or API response."
            )
    result.sort(key=lambda r: (int(r["fiscal_year"]), r["fiscal_period"] or ""))
    return result


def _to_snake(name: str) -> str:
    """CamelCase → snake_case. Used for converting XBRL concept names to columns."""
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not name[i - 1].isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out)
