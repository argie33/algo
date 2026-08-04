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
    # FIXED 2026-08-04: "NoncurrentLiabilities" (total non-current liabilities, a
    # different line item) was never a real long-term-debt concept - live-checked
    # against ASR's actual ifrs-full facts, which don't even report that tag. The real
    # IFRS taxonomy element filers use for long-term debt is "LongtermBorrowings"
    # (paired with "ShorttermBorrowings" for the current portion, same convention as
    # us-gaap's LongTermDebt); live-confirmed present with real 2018-2024 values for
    # ASR. This alias had never worked for any filer.
    ("LongtermBorrowings", "long_term_debt"),
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
    # TRIED AND REJECTED 2026-08-03: ("NumberOfSharesOutstanding", "shares_outstanding_basic")
    # as an IFRS alias for foreign 20-F filers (TV/Grupo Televisa, FMX/Femsa, SRAD/Sportradar
    # all lack this data any other way). Live-verified this produces dangerously wrong
    # market caps, not just stale ones: TV computed at $883B (real ~$2-3B), FMX at $2.25T
    # (real ~$25-35B) - both ~100-1000x too high. Root cause: unlike us-gaap filers (where
    # SEC convention requires the cover-page share count to already be expressed in the
    # security being registered, i.e. ADS-equivalent), IFRS-taxonomy foreign filers report
    # this concept in local/home-market share units with no ADS-ratio or corporate-action
    # (splits/restructuring) correction available in XBRL - SRAD's value was also from a
    # stale pre-restructuring Swiss AG share count. No reliable way to detect or correct
    # the unit mismatch from XBRL data alone. Leaving these symbols shares_outstanding_unavailable
    # (honest gap) is correct; do not re-add this concept without a verified per-filer
    # ADS-ratio source.
    # Session 398: EBITDA extraction from IFRS filers
    ("DepreciationAndAmortisation", "depreciation_and_amortization"),
    ("DepreciationExpense", "depreciation"),
    # FIXED 2026-08-03: no IFRS income-tax/pretax-income aliases existed at all, so
    # roic_pct's NOPAT computation (needs both to derive an effective tax rate) was stuck
    # at "SEC data not available" for every IFRS-only filer regardless of how much other
    # data they reported. Live-confirmed via real companyfacts JSON: WPM (Wheaton Precious
    # Metals) reports both IncomeTaxExpenseContinuingOperations and ProfitLossBeforeTax for
    # every fiscal year back to 2015. target_key values match the us-gaap concepts'
    # existing snake-cased names so no field_mapping changes are needed (same convention as
    # every other alias in this list).
    ("IncomeTaxExpenseContinuingOperations", "income_tax_expense_benefit"),
    (
        "ProfitLossBeforeTax",
        "income_loss_from_continuing_operations_before_income_taxes_extraordinary_items_noncontrolling_interest",
    ),
    # FIXED 2026-08-04: no IFRS interest-expense alias existed, so interest_coverage was
    # stuck at "SEC data not available" for every IFRS-only filer even when the underlying
    # data existed. "FinanceCosts" is the standard IAS 1 income-statement line IFRS filers
    # use in place of us-gaap's InterestExpense - live-confirmed via ASR (Grupo Aeroportuario
    # del Sureste): real ifrs-full:FinanceCosts data for every fiscal year, $826.7M for
    # FY2024. target_key matches the us-gaap concept's existing column so no field_mapping
    # changes are needed (same convention as every other alias in this list).
    ("FinanceCosts", "interest_expense"),
]

_CASHFLOW_IFRS_ALIASES = [
    ("CashFlowsFromUsedInOperatingActivities", "net_cash_provided_by_used_in_operating_activities"),
    ("CashFlowsFromUsedInInvestingActivities", "net_cash_provided_by_used_in_investing_activities"),
    ("CashFlowsFromUsedInFinancingActivities", "net_cash_provided_by_used_in_financing_activities"),
    (
        "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets",
        "payments_to_acquire_property_plant_and_equipment",
    ),
    # FIXED 2026-08-03: no IFRS dividend concept was mapped at all, so every dividend-paying
    # IFRS filer (live-confirmed: WPM/Wheaton Precious Metals, real ifrs-full:DividendsPaid
    # data present back to FY2015, $296M for FY2025) got payout_ratio/dividend_yield
    # permanently stuck at "SEC data not available" despite the underlying SEC data
    # existing - same target_key as the us-gaap PaymentsOfDividends* concepts below so
    # field_mapping needs no changes.
    ("DividendsPaid", "payments_of_dividends"),
    # ("DepreciationExpense", "depreciation") REMOVED 2026-07-28 - see get_cash_flow()'s
    # comment: no destination column exists for cash-flow-context depreciation.
]

_INCOME_DEI_ALIASES = [
    # FIXED (migration 1195): the universal SEC cover-page share count, present for
    # virtually every registrant regardless of accounting standard - live-confirmed real,
    # recent (2024+) data for filers with NO us-gaap share-count concept at all (PFLT,
    # TRAD, TRAX, ORKA, KLRA, AIAI, BRR, FRNM, KBON). target_key is intentionally distinct
    # from "common_stock_shares_outstanding" - see this file's _aggregate_concepts
    # docstring on dei_aliases for why sharing a target_key with a us-gaap concept would be
    # unsafe here (unlike ifrs_aliases, dei facts are present even for well-covered
    # domestic filers). Restricted to domestic filing forms only (10-K/10-Q) inside
    # _aggregate_concepts - see the form-check comment there for the foreign-filer
    # unit-mismatch trap this avoids repeating.
    ("EntityCommonStockSharesOutstanding", "entity_common_stock_shares_outstanding"),
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
        # FIXED 2026-08-03: two fallback cash concepts added below, both mapped to the same
        # cash_and_equivalents column via field_mapping in load_financial_statements.py.
        # _aggregate_concepts keeps the LAST-processed concept's value on overwrite when a
        # filer reports more than one for the same fiscal year (same convention as this
        # file's revenue-concept ordering), so the two lower-fidelity fallbacks are listed
        # BEFORE the standard concept to keep it authoritative whenever a filer reports it.
        #
        # Post-ASU-2016-18 (effective 2018) combined concept: many non-bank filers now tag
        # period-end cash together with restricted cash in one XBRL fact instead of the
        # plain concept below. Least preferred - includes restricted cash where a filer
        # only tags this combined figure, but recovers real data for filers that otherwise
        # report zero cash at all.
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        # Live-confirmed via real companyfacts JSON that banks (ZION and others) never tag
        # the standard concept below at all - their balance sheet reports "Cash and due
        # from banks" as a distinct line item tagged CashAndDueFromBanks instead. Found
        # while tracing why 1869/5486 symbols with real total_assets had NULL
        # cash_and_equivalents; ZION's balance sheet was reloaded the same day this was
        # found and still came back NULL, ruling out staleness for this subset.
        "CashAndDueFromBanks",
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
        # FIXED 2026-08-03: mortgage REITs (AGNC, NLY live-confirmed via real companyfacts
        # JSON) have none of the revenue concepts above - their primary revenue-equivalent
        # line is gross interest income (before subtracting interest expense on their own
        # borrowings). Deliberately did NOT use InterestIncomeExpenseNet (interest income
        # MINUS interest expense) for this - live-confirmed it goes NEGATIVE in real years
        # (AGNC FY2023: -246M) unlike a normal top-line revenue figure, which would distort
        # downstream margin/ratio calculations that assume revenue >= 0.
        # InterestIncomeOperating (gross, always positive in both AGNC's and NLY's real data)
        # is the correct analog instead. MUST be listed BEFORE InterestAndDividendIncomeOperating:
        # some community banks (FNWB, OCFC live-confirmed) report BOTH concepts, and the
        # "+dividend" variant is the more complete figure for them - it must win the
        # last-listed-wins overwrite, not this narrower one.
        "InterestIncomeOperating",
        # FIXED 2026-08-03: community banks/thrifts (FNWB, AMAL, OCFC live-confirmed via real
        # companyfacts JSON) have neither the concepts above nor RevenuesNetOfInterestExpense
        # (that one's for larger banks). Listed last in this revenue group so it only wins on
        # overwrite for filers with nothing else - see load_financial_statements.py's
        # _INCOME_FIELD_MAPPING comment for the live-verification details.
        "InterestAndDividendIncomeOperating",
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
        # FIXED 2026-08-03: live-confirmed against real companyfacts JSON that several
        # filers never tag EITHER weighted-average concept below, but do tag a
        # point-in-time balance-sheet/cover-page share count instead: PLNT (Planet
        # Fitness), WHD (Cactus Inc), YOU (Clear Secure) all have real
        # CommonStockSharesOutstanding but zero WeightedAverageNumberOfShares*; SPT
        # (Sprout Social), JG (Aurora Mobile), BNR (Burning Rock Biotech) only tag the
        # combined WeightedAverageNumberOfShareOutstandingBasicAndDiluted concept
        # (smaller/foreign filers often report one blended number instead of separate
        # Basic/Diluted tags). Listed BEFORE the two concepts below so a filer that
        # reports the real weighted-average correctly still wins on overwrite (same
        # "last-listed wins" convention as RevenuesNetOfInterestExpense above) - these
        # are lower-quality point-in-time fallbacks, not a preferred source.
        # FIXED (migration 1195): CommonStockSharesIssued (shares issued, which can exceed
        # shares outstanding if the filer holds treasury stock) - listed BEFORE
        # CommonStockSharesOutstanding so the real outstanding count wins on overwrite
        # whenever a filer reports both; only wins for filers with neither weighted-average
        # concept nor CommonStockSharesOutstanding.
        "CommonStockSharesIssued",
        "CommonStockSharesOutstanding",
        "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
        # FIXED 2026-07-28: real, officially-reported weighted-average basic share count -
        # now mapped to annual/quarterly_income_statement.shares_outstanding_basic (migration
        # 1171). Previously fetched every run and silently discarded (no field_mapping entry),
        # while load_sec_valuations.py derived an inferior EPS-rounding-lossy proxy instead
        # (shares = net_income / eps) believing (per its own stale docstring) it was already
        # using this concept.
        "WeightedAverageNumberOfSharesOutstandingBasic",
        # FIXED (migration 1192): fallback share count for filers that only tag diluted
        # shares (live-confirmed: JOUT/Johnson Outdoors has 44 real 10-K entries here but
        # zero for the basic concept above). Mapped to its own shares_outstanding_diluted
        # column, not shares_outstanding_basic - load_sec_valuations.py decides when to use
        # it, so filers that already report basic correctly are unaffected.
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        # For interest_coverage (quality_metrics) = OperatingIncomeLoss / InterestExpense.
        # No IFRS alias: IFRS "FinanceCosts" is a broader concept (includes non-interest
        # debt costs) and would silently overstate interest expense for foreign filers -
        # leaving it unmapped means those symbols correctly get interest_coverage=NULL
        # instead of a wrong number.
        "InterestExpense",
        # FIXED 2026-08-03: interest_expense was NULL for 83.5% of latest annual rows -
        # live-confirmed against real filers (not a coverage limit, a concept-list gap):
        # WMT never reports plain "InterestExpense" at all, only "InterestExpenseDebt" (real
        # value confirmed present for FY2025/2026); JNJ's taxonomy migrated from "InterestExpense"
        # (through FY2023) to "InterestExpenseNonoperating" (FY2024+, real value confirmed
        # present). Both are genuine interest-on-debt concepts (not the broader IFRS
        # "FinanceCosts" concern above), listed after the base concept per this file's
        # "last-listed wins on overwrite" convention.
        "InterestExpenseNonoperating",
        "InterestExpenseDebt",
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
        # For roic_pct (quality_metrics) = EBIT*(1-effective_tax_rate)/invested_capital.
        # Live-confirmed against AAPL/MSFT companyfacts (2026-08-03): both real GAAP
        # concepts, not guessed. IncomeTaxExpenseBenefit is the real tax provision (was
        # previously deliberately left unfetched - a hardcoded 25% tax-rate assumption
        # was correctly rejected as synthetic data, see load_value_quality_growth_metrics.py's
        # prior "CRITICAL FIX" comment - this replaces that gap with the real reported figure).
        "IncomeTaxExpenseBenefit",
        # Pretax income: the taxonomy migrated concepts over time (older filings/filers use
        # the MinorityInterest variant, current filers use the ExtraordinaryItems variant -
        # live-confirmed AAPL/MSFT both report ONLY the newer variant for fiscal years after
        # ~2012). List the deprecated concept first so the current one wins on overwrite,
        # same convention as the RevenuesNetOfInterestExpense ordering above.
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ]
    return _aggregate_concepts(
        client, symbol, concepts, period, ifrs_aliases=_INCOME_IFRS_ALIASES, dei_aliases=_INCOME_DEI_ALIASES
    )


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
        # FIXED 2026-08-03: dividends_paid was NULL for MSFT/JNJ (and presumably many other
        # well-known dividend payers) despite both definitely paying real dividends - live-
        # confirmed neither reports plain "PaymentsOfDividends" at all. Same taxonomy-variant
        # bug class as the interest_expense/pretax_income fixes this session: MSFT uses
        # "PaymentsOfDividendsCommonStock" (real value confirmed), JNJ uses
        # "PaymentsOfOrdinaryDividends" (real value confirmed). Both are genuine
        # dividend-payment concepts, not a broader/narrower one.
        "PaymentsOfDividendsCommonStock",
        "PaymentsOfOrdinaryDividends",
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
    dei_aliases: list[tuple[str, str]] | None = None,
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
        dei_aliases: Optional (dei_concept, target_key) pairs checked against the "dei"
            (Document and Entity Information) taxonomy - cover-page facts like the
            as-of-filing-date share count, reported by virtually every registrant
            regardless of accounting standard. Unlike ifrs_aliases, dei facts are present
            even for well-covered us-gaap filers, so target_key MUST be distinct from any
            us-gaap/ifrs target_key sharing a downstream db column, or a cruder cover-page
            fact could silently overwrite a better weighted-average figure - see
            load_financial_statements.py's field_mapping comment on shares_outstanding_dei.

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
    dei_facts = facts.get("dei")
    if not us_gaap_facts and not ifrs_facts:
        raise ValueError(
            f"[SEC_EDGAR] SEC API has no US-GAAP or IFRS facts for {symbol} (CIK {cik}). "
            f"Company may be a REIT, investment trust, or special entity without traditional "
            f"SEC filing data under either taxonomy. "
            f"Downstream loaders must mark data_unavailable with this reason."
        )
    rows: dict[Any, dict[str, Any]] = {}
    fp_filter = "FY" if period == "annual" else ("Q1", "Q2", "Q3", "Q4")

    # (xbrl_concept_name, target_key, source) triples to look up: "gaap" specs check
    # us-gaap first and fall back to ifrs-full only if us-gaap has nothing at all for
    # that concept name; "ifrs" alias specs go straight to ifrs-full, never through
    # us-gaap first (preserves exact prior behavior/column names for plain concepts),
    # then dei aliases (looked up only in dei_facts - see this function's dei_aliases
    # docstring for why these must never share a target_key with a us-gaap/ifrs concept).
    #
    # FIXED 2026-08-04: ifrs_aliases used to share the exact same us-gaap-first lookup
    # as plain concepts. That's a silent no-op whenever an ifrs alias's concept name is
    # spelled identically to a real us-gaap concept name ("Assets", "Liabilities",
    # "Goodwill" are valid tags in BOTH taxonomies) and the filer has ANY us-gaap entry
    # under that name - even a stale one from years before they were IFRS-only. Live-
    # confirmed via ASR (Grupo Aeroportuario del Sureste): us-gaap:Assets has exactly 2
    # entries (FY2016-2017, filed 2018), so both the plain spec AND the "Assets" ifrs
    # alias spec found that same stale us-gaap data and neither ever reached
    # ifrs-full:Assets's real 2018-2024 entries - total_assets/total_liabilities came
    # back NULL every year since 2018 despite current_assets/current_liabilities/
    # stockholders_equity (different-spelled ifrs concepts, no collision) working fine.
    # Confirmed via a live DB scan: 58 symbols affected today (HMC, TM, SONY, PBR, VALE,
    # WPP, FRO, ALC, FMS among them) - total_assets NULL for fiscal_year >= 2022 despite
    # current_assets present. IFRS alias specs must always read ifrs-full directly; the
    # existing latest-filed-wins merge per fiscal year (below) already handles combining
    # both sources correctly when a company legitimately has both.
    concept_specs: list[tuple[str, str, str]] = [(c, _to_snake(c), "gaap") for c in concepts]
    if ifrs_aliases:
        concept_specs.extend((c, k, "ifrs") for c, k in ifrs_aliases)
    if dei_aliases:
        concept_specs.extend((c, k, "dei") for c, k in dei_aliases)

    for concept, target_key, source in concept_specs:
        if source == "dei":
            concept_data = dei_facts.get(concept) if dei_facts is not None else None
        elif source == "ifrs":
            concept_data = ifrs_facts.get(concept) if ifrs_facts is not None else None
        else:
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
                # dei facts (e.g. EntityCommonStockSharesOutstanding) are reported in
                # whatever share unit the local filing uses - domestic 10-K/10-Q filers
                # report it in the actual registered security's units, but foreign 20-F/
                # 40-F/6-K filers often report it in home-market local shares with no
                # ADS-ratio conversion available in XBRL. A prior session in this file hit
                # exactly this trap with a different IFRS shares concept (see the removed-
                # concept comment above _INCOME_IFRS_ALIASES: SRAD's value was a stale
                # pre-restructuring Swiss AG share count, live-caught via a market-cap
                # sanity check) and reverted it. Restrict dei facts to domestic forms only
                # to avoid reintroducing the same class of silent unit-mismatch error.
                if source == "dei" and entry.get("form") in ("20-F", "40-F", "6-K"):
                    continue
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
