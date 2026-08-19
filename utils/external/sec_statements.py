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

import datetime
import logging
from typing import Any

from utils.external.fx_rates import MAJOR_CURRENCIES, FxRateCache

logger = logging.getLogger(__name__)

# FIXED 2026-08-17 (goal: "no SEC data" audit): module-level so the (currency, date)
# rate cache is shared and its persistent file cache reused across every symbol
# processed in a run, not just within one _aggregate_concepts call. See fx_rates.py's
# module docstring for the CAD/GBP/EUR/AUD/CHF/JPY-only fix this backs.
_fx_rate_cache = FxRateCache()


def _extract_currency_code(unit: str) -> str:
    """Return the bare currency code from an XBRL unit string.

    Per-share concepts (BasicEarningsLossPerShare etc.) use compound units like
    "CAD/shares", not a bare "CAD" - the currency-rejection/conversion guard below
    only ever matched bare 3-letter units, so foreign filers' EPS silently passed
    through unconverted (and un-rejected) regardless of currency. Splitting on "/"
    first makes "CAD/shares" -> "CAD" (subject to the same reject-or-convert rule as
    a bare "CAD" monetary fact) while "shares"/"pure"/"USD/shares" -> "shares"/"pure"/
    "USD" still correctly fall outside the 3-letter-uppercase-code shape.
    """
    return unit.split("/", 1)[0]


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
    # FIXED 2026-08-17 (loader-review goal, continued): "ShorttermBorrowings" is IFRS's
    # paired current-portion concept for the above (same convention as us-gaap's
    # CommercialPaper/ShortTermBorrowings, which already map to the same short_term_debt
    # column via _BALANCE_FIELD_MAPPING and are NOT fallback-only - i.e. genuine
    # either/or alternatives, not a "don't overwrite the real concept" case). Target key
    # is "short_term_borrowings" (the field_mapping dict KEY the equivalent us-gaap
    # concept _to_snake()'s to), not "short_term_debt" (the DB column) - using the
    # column name directly would make sec_field not in field_mapping true and silently
    # drop the value via the unmapped-field warning path instead of writing it (see
    # sec_ifrs_sbc_buyback_alias_gap_fixed_20260817 memory for this exact class of bug
    # caught before shipping on the SBC/buyback aliases below).
    ("ShorttermBorrowings", "short_term_borrowings"),
    # FIXED 2026-08-17 (loader-review goal continuation): IFRS 16 lessee accounting
    # doesn't distinguish operating vs. finance leases the way US GAAP does - IFRS
    # filers report a single combined "LeaseLiabilities" concept, not separate
    # OperatingLeaseLiability/FinanceLeaseLiability tags. Live-confirmed via real
    # companyfacts JSON that "LeaseLiabilities" is the true Current+Noncurrent total
    # (E/Eni: EUR 5.70B == 1.263B + 4.437B; TS/Tenaris: USD 143.249M == 48.346M +
    # 94.903M), same combined-tag pattern already used for the GAAP concepts above.
    # Mapped to "operating_lease_liability" (not a new column) so it flows through
    # the existing total_debt = long_term_debt + short_term_debt +
    # operating_lease_liability + finance_lease_liability sum unchanged;
    # finance_lease_liability stays NULL for these filers, which is fine since IFRS
    # doesn't separate the two anyway - the combined total lands intact either way.
    # Foreign filers previously got NULL lease liabilities entirely.
    ("LeaseLiabilities", "operating_lease_liability"),
]

_INCOME_IFRS_ALIASES = [
    ("Revenue", "revenues"),
    # FIXED 2026-08-19 ("no SEC data"/loader audit, roic_pct/AEG follow-up): IFRS 17
    # ("Insurance Contracts", effective FY2023 for most insurers) replaced the general
    # "Revenue" concept with a dedicated "InsuranceRevenue" concept for insurers' income
    # statements - the underlying figure isn't just relabeled, it's a genuinely different,
    # narrower recognition basis than the old premium-based revenue. Live-confirmed via
    # Aegon's (AEG) real companyfacts JSON: "Revenue" tagged through FY2022 (EUR 21.33B),
    # then goes silent - "InsuranceRevenue" takes over from FY2023 onward (EUR 10.39B,
    # 9.84B, 9.10B). Our anchor-fiscal-year-selection query in
    # load_value_quality_growth_metrics.py strongly prefers a fiscal year with a non-NULL
    # "revenues" value, so 3 straight years of real, complete balance-sheet AND income-
    # statement data (FY2023-2025) lost out to a stale FY2022 anchor purely because
    # "revenues" was NULL there - the stale anchor then failed the staleness gate,
    # masking every quality_metrics field for AEG behind a generic reason (roic_pct's
    # correctly-computed "unprofitable_stock" among them) instead of computing off real,
    # current data. Listed right after "Revenue" (not made fallback-only via
    # load_financial_statements.py's _REVENUE_FALLBACK_ONLY_FIELDS - tried that first,
    # live-caught it as wrong: "revenues" is the PRIMARY revenue signal, and several
    # weaker fields also map to the same "revenue" DB column - e.g.
    # interest_income_operating - fallback-only would let one of THOSE populate "revenue"
    # first and then block the real InsuranceRevenue value from ever overwriting it).
    # _aggregate_concepts's own per-fiscal-year merge below already resolves Revenue vs.
    # InsuranceRevenue correctly with no ambiguity - for any given fiscal year at most one
    # of the two ever has a real entry (temporally exclusive: Revenue stops exactly when
    # InsuranceRevenue starts), so ordinary last-listed-wins is safe here.
    ("InsuranceRevenue", "revenues"),
    ("RevenueFromContractsWithCustomers", "revenue_from_contract_with_customer_excluding_assessed_tax"),
    ("RevenueFromSaleOfGoods", "sales_revenue_net"),
    # FIXED 2026-08-18 (goal: "no SEC data"/loader audit): pure-play IFRS metals producers
    # (B2Gold/BTG live-confirmed via real companyfacts JSON - CIK 1429937, ifrs-full
    # namespace only, no us-gaap facts at all) disaggregate revenue by metal
    # (RevenueFromSaleOfGold + RevenueFromSaleOfSilver as a byproduct credit) and never tag
    # any of the concepts above - real total revenue only exists as a sum of per-metal
    # dimensional facts, which this extractor doesn't aggregate. Gold is the overwhelming
    # majority of revenue for these filers (silver is a minor byproduct), so mapping just
    # this concept recovers most of the real figure instead of leaving revenue NULL/0 -
    # same "partial but far better than missing" precedent as sales_revenue_goods_net below.
    # Maps to the same fallback-only target as sales_revenue_goods_net (see
    # load_financial_statements.py's _REVENUE_FALLBACK_ONLY_FIELDS) so it never clobbers a
    # real total-revenue figure for filers that report one.
    ("RevenueFromSaleOfGold", "sales_revenue_goods_net"),
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
    # FIXED 2026-08-10: the concept above has never matched any real filer checked live -
    # VALN (Valneva SE) and IMTX (Immatics N.V.), both IFRS 20-F filers with real capex
    # data, report the shorter "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"
    # instead (also confirmed for ASM/VIVO/EFXT/ALAR). Same target_key as the alias above
    # so field_mapping needs no changes; this was the direct cause of free_cash_flow/
    # fcf_to_net_income being stuck at "SEC data not available" for these symbols despite
    # operating_cash_flow being populated.
    (
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "payments_to_acquire_property_plant_and_equipment",
    ),
    # FIXED 2026-08-03: no IFRS dividend concept was mapped at all, so every dividend-paying
    # IFRS filer (live-confirmed: WPM/Wheaton Precious Metals, real ifrs-full:DividendsPaid
    # data present back to FY2015, $296M for FY2025) got payout_ratio/dividend_yield
    # permanently stuck at "SEC data not available" despite the underlying SEC data
    # existing - same target_key as the us-gaap PaymentsOfDividends* concepts below so
    # field_mapping needs no changes.
    ("DividendsPaid", "payments_of_dividends"),
    # FIXED 2026-08-17 (user-reported live: AEM's Scores page showed dividend_yield "SEC
    # data not available" despite AEM being a well-known real dividend payer). Root cause:
    # AEM is a 40-F/20-F Canadian foreign private issuer that reports BOTH us-gaap and
    # ifrs-full facts, but its us-gaap:PaymentsOfDividendsCommonStock data stops at FY2013
    # (filer switched taxonomies) while "DividendsPaid" (the alias above) was never AEM's
    # real concept name at all. Live-confirmed via real companyfacts JSON: AEM reports
    # ifrs-full:DividendsPaidClassifiedAsFinancingActivities every fiscal year through
    # FY2025 ($728.1M FY2025, $671.7M FY2024) - the IFRS cash-flow-statement financing-
    # activities dividend line, i.e. exactly what this target column represents (unlike
    # the sibling ifrs-full:DividendsPaidOrdinaryShares concept AEM also reports, which is
    # a different, larger figure - $802.9M FY2025 - not the cash-flow-statement line, so
    # deliberately not aliased here to avoid conflating the two).
    ("DividendsPaidClassifiedAsFinancingActivities", "payments_of_dividends"),
    # ("DepreciationExpense", "depreciation") REMOVED 2026-07-28 - see get_cash_flow()'s
    # comment: no destination column exists for cash-flow-context depreciation.
    # FIXED 2026-08-17 (loader-review goal continuation, migration 1206 follow-up): the
    # us-gaap ShareBasedCompensation/PaymentsForRepurchaseOfCommonStock concepts added
    # this session had no IFRS equivalents, so every IFRS-only filer got NULL for both -
    # same "foreign filer silently dropped" bug class as every other alias in this list.
    # Live-confirmed via real companyfacts JSON against ifrs-full (not guessed):
    # "AdjustmentsForSharebasedPayments" is WPM's real cash-flow-statement non-cash SBC
    # addback (the IFRS reconciliation-of-profit-to-operating-cash-flow line, direct
    # analog of us-gaap's ShareBasedCompensation) - $16.57M FY2024, $26.03M FY2025.
    # "PurchaseOfTreasuryShares" is TS's and E's real financing-activities buyback outflow
    # - TS $1.44B FY2024/$1.36B FY2025, E EUR2.00B FY2024/EUR1.88B FY2025 (E's non-USD
    # facts are correctly dropped by the non-USD unit guard below, not fabricated).
    # Same target_key as the us-gaap concepts so field_mapping needs no changes.
    ("AdjustmentsForSharebasedPayments", "share_based_compensation"),
    ("PurchaseOfTreasuryShares", "payments_for_repurchase_of_common_stock"),
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

# Forms that carry audited/reviewed primary financial statements. See the
# "FIXED 2026-08-17 (goal: 'no SEC data' audit)" comment in _aggregate_concepts for why
# these must outrank other forms (DEF 14A Pay vs Performance tables, 8-K, S-1, etc.)
# regardless of filing date - those forms retag figures like NetIncomeLoss without a
# reliable guarantee of the correct XBRL scale.
_PRIMARY_STATEMENT_FORMS = {
    "10-K",
    "10-K/A",
    "10-KT",
    "10-KT/A",
    "10-Q",
    "10-Q/A",
    "10-QT",
    "10-QT/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
    "6-K",
    "6-K/A",
}

# Forms that represent a genuine fiscal-year-end annual report (as opposed to a 10-Q/6-K
# interim filing). See the "FIXED 2026-08-18 (no-SEC-data audit continuation)" comment in
# _aggregate_concepts for why instant (point-in-time) balance-sheet facts need this
# narrower set: a 10-Q's balance sheet is a real, valid "as of" snapshot, but it's a
# mid-year snapshot, not the fiscal year's actual year-end position.
_ANNUAL_REPORT_FORMS = {
    "10-K",
    "10-K/A",
    "10-KT",
    "10-KT/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
}


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
        # FIXED 2026-08-18 (roic_pct "missing_sec_data" audit): fallback for filers that
        # tag total equity INCLUDING noncontrolling/minority interest instead of (or as well
        # as) the parent-only "StockholdersEquity" concept - live-confirmed via real SEC
        # companyfacts JSON that ADM (CIK 0000007084) has ZERO "StockholdersEquity" facts
        # ever filed, only this concept (e.g. FY2021 $22,508,000,000). A live DB scan found
        # 115 symbols with 2+ real (non-data_unavailable) annual_balance_sheet rows where
        # stockholders_equity was NULL in every single one - after excluding commodity/crypto
        # trusts and ETFs that legitimately have no XBRL company facts at all (AAAU, BAR,
        # BITB, BITW, BNO, BDRY, ...), several (ADM, AAON among them) are ordinary profitable
        # operating companies that should have this field. Listed BEFORE "StockholdersEquity"
        # (same last-listed-wins convention as the cash fallbacks below) so the more precise
        # parent-only figure always wins when a filer reports both for the same fiscal year -
        # this only fills years/filers where the parent-only concept is absent entirely.
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
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
        # FIXED 2026-08-17 (loader-review goal continuation): fallback long-term-debt
        # concepts for filers that never tag the standard "LongTermDebt" concept at all -
        # live-confirmed via real SEC companyfacts JSON that this is common among small/
        # micro-cap filers (MRKR, MODD, ATNM among others), which tag their real debt
        # under one of these instead. A live DB scan found 2,306 symbols with real
        # (non-data_unavailable) annual_balance_sheet rows that had NEVER had a single
        # long_term_debt value across every fiscal year - many are genuinely debt-free
        # (biotechs funded by equity), but MRKR/MODD/ATNM specifically have real,
        # instant-fact (not duration) debt reported under these concepts and were being
        # silently treated as debt-free. Listed BEFORE "LongTermDebt" (least-preferred
        # position, same "fallback listed first" convention as the cash_and_equivalents
        # fallbacks above) AND marked fallback-only in load_financial_statements.py's
        # field_mapping (_DEBT_FALLBACK_ONLY_FIELDS) so a filer that reports the standard
        # LongTermDebt concept always keeps that value - these only fill the gap when
        # LongTermDebt is absent for that fiscal year, never overwrite it.
        "NotesPayableRelatedPartiesNoncurrent",
        "LongTermNotesPayable",
        "ConvertibleNotesPayable",
        # FIXED 2026-08-18 (goal: "no SEC data" loader audit, roic_pct missing_sec_data
        # follow-up): live-confirmed via real SEC companyfacts JSON that DKNG (DraftKings)
        # and DASH (DoorDash) - both large, well-known filers, not obscure micro-caps -
        # report their real convertible debt exclusively under this concept, never plain
        # "ConvertibleNotesPayable" or "LongTermDebt": DKNG FY2025 10-K = $1,259,096,000,
        # DASH FY2025 10-K = $2,724,000,000. Both were silently treated as debt-free
        # (long_term_debt NULL across every fiscal year) despite carrying material
        # long-term debt - part of the same "2,306 symbols with real balance
        # sheet rows but zero long_term_debt ever" gap the fallback concepts above were
        # added for, this specific concept just wasn't in that sweep. Fallback-only, listed
        # before "LongTermDebt" (least-preferred position, same convention as the other
        # fallbacks here) so a filer reporting the standard concept always keeps that value.
        "ConvertibleLongTermNotesPayable",
        # FIXED 2026-08-18 (concurrent goal-session continuation): completes a mapping-only
        # change already landed in load_financial_statements.py's _BALANCE_FIELD_MAPPING/
        # _DEBT_FALLBACK_ONLY_FIELDS (and its regression test) that was missing the matching
        # entry here - without a concept string in THIS list, SecEdgarClient never fetches it
        # from SEC at all, so the mapping/test alone can never actually populate long_term_debt
        # (same "wiring half-landed" class as the DCF branch collision, see
        # dcf_margin_of_safety_scoring_restored_20260818 in memory). Live-confirmed via real SEC
        # companyfacts JSON: neither CAT, SLB, nor XOM ever tags plain "LongTermDebt" - CAT
        # reports LongTermDebtNoncurrent ($30.696B FY2025), XOM reports
        # LongTermDebtAndCapitalLeaseObligations (distinct concept from the "...Including
        # CurrentMaturities" JPM variant below - no "IncludingCurrentMaturities" suffix).
        # Both fallback-only, same convention as the rest of this block.
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
        # FIXED 2026-08-17 (SEC-vs-yfinance audit): JPM (the largest US bank by assets)
        # stopped tagging the plain "LongTermDebt" concept after FY2013 - live-confirmed
        # via its real companyfacts JSON, last "LongTermDebt" fact is 2013-12-31, every
        # 10-K since uses "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities"
        # instead ($435.2B for FY2025). Most other large banks (MS/USB/PNC/TFC/COF/AXP/
        # SCHW/STT live-checked) still tag plain LongTermDebt even when they also report
        # this concept, so - same reasoning as the small/micro-cap fallbacks just above -
        # it's fallback-only in field_mapping's _DEBT_FALLBACK_ONLY_FIELDS: only fills the
        # gap when a filer has no real LongTermDebt for that fiscal year, never overwrites it.
        "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
        "LongTermDebt",
        # FIXED 2026-08-17 (migration 1204): real short-term/revolving debt instruments -
        # LongTermDebt only covers long-term borrowings (including their current portion for
        # most filers, e.g. AAPL's LongTermDebt = LongTermDebtNoncurrent +
        # LongTermDebtCurrent), never commercial paper or short-term notes payable. Live-
        # confirmed via AAPL's real companyfacts JSON: CommercialPaper FY2025 = $7.98B, a
        # real, separate debt instrument not captured by any concept fetched above - this was
        # previously entirely missing from total_debt, on top of the separate total_debt
        # mislabeling bug fixed the same session (see load_sec_valuations.py). Both target
        # the same short_term_debt column (loader-side sum, not an alias collision - a filer
        # reporting both concepts in different fiscal years would incorrectly overwrite via
        # the same "last-listed wins" convention as elsewhere in this file, but live-checked
        # AAPL only ever reports CommercialPaper, never both, so this is not yet a live
        # collision case).
        "CommercialPaper",
        "ShortTermBorrowings",
        # FIXED 2026-08-17 (migration 1205): post-ASC 842 (2019+) capitalized lease
        # liabilities - a real, separate liability from long_term_debt/short_term_debt
        # above (AAPL's LongTermDebt does not include either). Using the COMBINED tags
        # ("OperatingLeaseLiability"/"FinanceLeaseLiability"), not the Current/Noncurrent
        # split variants: live-confirmed via AAPL's real companyfacts JSON that the
        # combined tag exactly equals Current+Noncurrent for both concepts (FY2025:
        # OperatingLeaseLiability $12.49B == Current $1.579B + Noncurrent $10.911B;
        # FinanceLeaseLiability $1.23B == Current $538M + Noncurrent $692M) - so this is
        # the true total, not a dimensional/duplicate fact. Deliberately NOT also fetching
        # the Current/Noncurrent variants into these same target keys: unlike the
        # CommercialPaper/ShortTermBorrowings "last-listed wins" pattern above (genuine
        # either/or alternatives), Current and Noncurrent are two PARTS of one total -
        # summing them would require different aggregation logic than _aggregate_concepts
        # provides, and naively listing them here would let a partial (e.g.
        # Noncurrent-only) value silently overwrite a correct combined total on
        # last-filed-wins, undercounting real lease debt - same bug class as the
        # total_liabilities mislabeling this migration's session already fixed once. A
        # filer that reports only the split (no combined tag) gets an honest NULL here
        # instead of a guessed or partial sum.
        "OperatingLeaseLiability",
        "FinanceLeaseLiability",
        # FIXED 2026-08-18 (no-SEC-data audit continuation, landed alongside a concurrent
        # session's "LongTermDebtNoncurrent" fallback-only addition above - see that
        # comment): live-confirmed via real SEC companyfacts JSON that PFE stopped tagging
        # plain "LongTermDebt" after FY2020 and every 10-K since splits it into
        # "LongTermDebtNoncurrent" ($61.641B FY2025) + "LongTermDebtCurrent" ($2.997B
        # FY2025) instead - same real ~$64.6B debt load, just under different concepts. The
        # Noncurrent-alone fallback above recovers most of this but understates real debt
        # by the current-maturities portion (~5% for PFE, larger for filers with more debt
        # maturing soon). Only "LongTermDebtCurrent" needs adding here - Noncurrent is
        # already fetched. _fill_long_term_debt_from_noncurrent_current_split() below sums
        # both into "long_term_debt" as a post-processing step (genuinely different
        # aggregation than _aggregate_concepts' one-column "last value wins" merge, per the
        # lease-liability comment above) and pops both raw keys before returning - so this
        # step's more accurate sum always wins over the other session's Noncurrent-alone
        # field_mapping fallback (load_financial_statements.py's _DEBT_FALLBACK_ONLY_FIELDS),
        # which only ever sees "long_term_debt_noncurrent" if this function is bypassed.
        "LongTermDebtCurrent",
    ]
    rows = _aggregate_concepts(client, symbol, concepts, period, ifrs_aliases=_BALANCE_IFRS_ALIASES)
    _fill_long_term_debt_from_noncurrent_current_split(rows)
    return rows


def _fill_long_term_debt_from_noncurrent_current_split(rows: list[dict[str, Any]]) -> None:
    """Fallback-only: long_term_debt = LongTermDebtNoncurrent + LongTermDebtCurrent.

    Only fires when the primary "long_term_debt" column (LongTermDebt /
    LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities / the other fallback
    concepts above, including "LongTermDebtNoncurrent" - fetched as a plain concept above,
    not by this function) is still empty for that fiscal year - never overwrites a real
    value. LongTermDebtCurrent defaults to 0 when absent (a filer with no current-portion
    tag for that year, not necessarily zero, but the closer approximation to the real total
    than leaving the whole figure NULL). Mutates rows in place and always strips both raw
    keys, including "long_term_debt_noncurrent" (fetched above as a plain fallback concept
    for a different, concurrent fix) - this function's sum is strictly more accurate, so it
    always supersedes that field_mapping-level fallback rather than leaving both to race.
    """
    for row in rows:
        noncurrent = row.pop("long_term_debt_noncurrent", None)
        current = row.pop("long_term_debt_current", None)
        if row.get("long_term_debt") is not None or noncurrent is None:
            continue
        row["long_term_debt"] = noncurrent + (current or 0)


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
        # FIXED 2026-08-09: pre-2011-ish filers (AGCO live-confirmed: FY2009-2015 10-Ks)
        # sometimes tag neither "Revenues" nor "SalesRevenueNet" at all - their only real
        # revenue concept is this older, goods-specific tag (AGCO FY2009: $6.52B here vs
        # nothing under either concept above it). Left completely unmapped before this fix,
        # so transform() silently discarded it and a tiny fallback concept
        # (InterestAndDividendIncomeOperating, ~$20-30M) won "revenue" by default for these
        # years - same visible symptom (revenue << gross_profit) as the REIT/duration bugs
        # fixed earlier today, different root cause (missing concept mapping, not a
        # priority-chain or duration-check bug). Listed before SalesRevenueNet since it's
        # the older/narrower of the two - SalesRevenueNet should win when both are present.
        "SalesRevenueGoodsNet",
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
        # FIXED 2026-08-17 (goal: "no SEC data" audit): "CostOfGoodsAndServicesSold" is the
        # standard us-gaap tag product/retail companies use for cost of goods sold - it was
        # never fetched at all, only the much rarer "CostOfRevenue"/"CostOfSales" tags were.
        # Live-confirmed via this DB: AMZN, COST, CI, JD, SHEL, TTE all have real revenue but
        # NULL cost_of_revenue AND NULL gross_profit for every fiscal year - not financial/
        # unclassified-balance-sheet filers (which legitimately lack a COGS concept), but
        # ordinary product/retail companies that plainly report cost of goods sold in their
        # 10-Ks. 2,261 of 5,304 symbols (43%) with revenue had both concepts NULL at their
        # latest fiscal year before this fix. Same target_key ("cost_of_revenue") as
        # "CostOfRevenue" above via load_financial_statements.py's _INCOME_FIELD_MAPPING, so
        # no new column is needed. Listed after CostOfRevenue (wins on overwrite per this
        # file's last-listed-wins convention) though not live-confirmed as a real double-
        # booking case for any filer - the two tags serve different business models
        # (services vs. product/retail) and haven't been seen co-reported.
        "CostOfGoodsAndServicesSold",
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
        # FIXED 2026-08-17 (goal: "no SEC data" audit): PRI (Primerica) live-confirmed via real
        # companyfacts JSON to report ZERO NetIncomeLoss entries ever, using "ProfitLoss" (the
        # us-gaap concept for consolidated net income including noncontrolling interest) as its
        # only bottom-line tag instead - FY2025 ProfitLoss=$751,234,000 exactly matches
        # pretax_income ($974,564,000) minus income_tax_expense ($223,330,000), confirming this
        # is the real net income figure, not a different line item. This is a legitimate us-gaap
        # concept (also aliased for ifrs-full filers via _INCOME_IFRS_ALIASES below, but that
        # list is only checked against the ifrs-full namespace - PRI files under us-gaap, so it
        # needs its own entry here). Listed BEFORE NetIncomeLoss so the standard tag wins on
        # overwrite for the common case of filers reporting both; ProfitLoss only wins for
        # filers (like PRI) that report solely this concept. Maps to the same "net_income"
        # column via _INCOME_FIELD_MAPPING's "profit_loss" key.
        "ProfitLoss",
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
        # FIXED 2026-08-18 (goal: "no SEC data"/loader audit): live-confirmed via real SEC
        # companyfacts JSON that TXN (Texas Instruments, FY2025 $543M) and BA (Boeing,
        # FY2025 $2,771M) tag their real income-statement interest expense only under this
        # concept - neither has any fact under "InterestExpense",
        # "InterestExpenseNonoperating", or "InterestExpenseDebt" above. Listed after those
        # per this file's "last-listed wins on overwrite" convention.
        "InterestAndDebtExpense",
        # FIXED 2026-08-18 (same audit): CAT (Caterpillar) and NEE (NextEra Energy) tag
        # NEITHER "InterestAndDebtExpense" nor any InterestExpense* concept above -
        # live-confirmed their only interest-on-debt fact anywhere in companyfacts is this
        # cash-flow-statement supplemental-disclosure concept (NEE FY2025 $3,501M; CAT has
        # none at all, so this doesn't help CAT specifically, but recovers real data for
        # other filers with the same reporting gap). Cash interest PAID is not identical to
        # accrued interest EXPENSE (debt discount/premium amortization, capitalized
        # interest), so this is intentionally the lowest-priority, last-resort fallback -
        # listed last so any filer with a real accrual-basis concept above keeps that value.
        "InterestPaidNet",
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
        #
        # FIXED 2026-08-17 (goal: "no SEC data" audit, CNX live-confirmed): neither variant
        # above exists at all for some filers (CNX Resources - E&P, SIC 1311 - has zero
        # entries for either, confirmed via real companyfacts JSON) - they tag
        # "...BeforeIncomeTaxesDomestic" instead. Listed FIRST (not last) because, unlike the
        # two concepts above, "Domestic" only covers US operations for a genuinely
        # multinational filer - for a filer that also reports one of the fuller concepts
        # above, that more complete figure must win on overwrite. Live-verified for CNX
        # FY2023: this concept's value ($2,222,925,000) exactly equals net_income
        # ($1,720,716,000) + income_tax_expense ($502,209,000) already in our DB for that
        # year - confirming it IS the real total pretax income for this filer, not a partial
        # figure. (A sibling concept, "ResultsOfOperationsIncomeBeforeIncomeTaxes", was
        # checked and rejected - CNX FY2023 value $2,317,918,000 does NOT match, it's the
        # ASC 932 oil-and-gas-producing-activities supplementary disclosure, not consolidated
        # pretax income - do not add it here.)
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
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
        # FIXED 2026-08-10: real capex concept some filers use INSTEAD of the concept
        # above - live-confirmed via AAON, KELYB, CPS, DTIL (all report ONLY this tag,
        # AAON with 112 real entries back through FY2023, none report the standard tag
        # at all). Target key "payments_to_acquire_productive_assets" maps to the same
        # "capex" column - see load_financial_statements.py's field_mapping comment.
        "PaymentsToAcquireProductiveAssets",
        # FIXED 2026-08-18 (goal: "missing SEC data" scores audit, AAON live-confirmed):
        # AAON tagged "PaymentsToAcquireProductiveAssets" through FY2023 Q3 (2023-09-30)
        # then switched to this concept for FY2023 Q4/10-K onward with no overlap -
        # FY2023-FY2026 real capex ($104.3M/$195.7M/$190.6M and counting) was never
        # fetched at all, leaving capex/free_cash_flow/fcf_yield/fcf_to_net_income NULL
        # ("missing_sec_data") for 3+ straight fiscal years despite operating_cash_flow
        # being populated every year. Same target key "capex" as the concepts above -
        # see load_financial_statements.py's field_mapping comment.
        "PaymentsToAcquireMachineryAndEquipment",
        # FIXED 2026-08-18 (goal: "missing factor inputs" audit continuation): live-
        # confirmed via VZ (Verizon) - a major US domestic 10-K filer whose capex is one
        # of its most closely-watched public metrics - NULL across EVERY historical
        # fiscal year (2021-2026) in our DB despite operating_cash_flow being fully
        # populated. VZ tags its real capex ONLY under this concept, never any of the
        # 3 above: real SEC values $17.011B (FY2025)/$17.090B (FY2024) match VZ's
        # publicly reported capex almost exactly. Also live-confirmed on QCOM (which
        # already has a working fallback via PaymentsToAcquireProductiveAssets, so this
        # is an additional/redundant concept for QCOM specifically, not its primary
        # gap-closer).
        "PaymentsToAcquireOtherProductiveAssets",
        # FIXED 2026-08-18 (same investigation): live-confirmed via LLY (Eli Lilly) and
        # ADP - both major US domestic 10-K filers, NULL across every historical year
        # despite real operating_cash_flow. Real SEC values: LLY $7.841B (FY2025)/
        # $5.058B (FY2024, plausible big-pharma capex); ADP $196.6M (FY2026, plausible
        # for a payroll/HR-services company with light physical footprint) - both
        # confirmed via direct live SEC companyfacts lookup, not guessed.
        "PaymentsToAcquireOtherPropertyPlantAndEquipment",
        # FIXED 2026-08-18 (missing factor inputs audit): ACGL/FRT/VSH-class filers report
        # dividends under this concept instead of any "PaymentsOf*Dividend*" tag below - see
        # load_financial_statements.py's _CASHFLOW_FIELD_MAPPING comment for the live
        # evidence and the required sign normalization. Listed BEFORE the "PaymentsOf*"
        # concepts (this file's "last-listed wins" overwrite convention) so the more
        # standard/reliable PaymentsOf* tag stays authoritative on the rare filer that
        # reports both - live-confirmed no overlap exists for ACGL/FRT/VSH, but there's no
        # reason to risk it for filers not yet characterized.
        "DividendsCommonStockCash",
        "DividendsCommonStock",
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
        # FIXED 2026-08-17 (migration 1206): non-cash stock-based compensation and cash
        # buybacks - both real, well-populated concepts (live-confirmed AAPL 180/126
        # entries, MSFT 133/230 entries) never fetched before. ShareBasedCompensation is
        # the standard operating-section addback tag; PaymentsForRepurchaseOfCommonStock
        # is the standard financing-section buyback outflow (counterpart to
        # PaymentsOfDividends above). No fallback-variant search done yet for either (only
        # AAPL/MSFT verified this session) - unlike the multi-variant dividend/capex
        # concepts above, coverage gaps for other filers are not yet characterized.
        #
        # FIXED 2026-08-17 (loader-review goal continuation): the fallback-variant search
        # promised above, now done. Live-confirmed via real companyfacts JSON across a
        # random sample of ~80 symbols with real cash-flow data:
        # - "AllocatedShareBasedCompensationExpense": the standard alternate SBC-expense
        #   tag filers use instead of "ShareBasedCompensation" (real, reasonable-magnitude
        #   annual totals confirmed for FIP $11.1M FY2025, DC $3.5M FY2025, CNA $41M
        #   FY2025 - all three report ONLY this tag, never "ShareBasedCompensation").
        #   Every OTHER us-gaap concept containing "SharebasedCompensation"/
        #   "StockCompensat" in these filers' companyfacts is a disclosure-only item
        #   (option pricing assumptions, shares outstanding, tax benefit detail) - not a
        #   real cash-flow-statement addback total, so not added here.
        # - "PaymentsForRepurchaseOfEquity": the standard broader alternate SPWH (real
        #   duration facts, $2.75M and $64.7M across two fiscal years, both real
        #   filed 10-Ks) uses instead of "PaymentsForRepurchaseOfCommonStock", which it
        #   never tags at all. Deliberately NOT adding "StockRepurchasedDuringPeriodValue"
        #   (RKTO/ARES) - that is an equity-statement (shares issued/repurchased roll-
        #   forward) concept, not a cash-flow-statement concept; the amount recognized in
        #   the equity roll-forward is not guaranteed to equal cash actually paid in the
        #   period (timing differences from unsettled repurchases), so it is not a safe
        #   substitute for a real cash outflow figure. Same reasoning applies to
        #   "PaymentsForRepurchaseOfPreferredStockAndPreferenceStock" (FIP/RKTO) - a
        #   different equity instrument (preferred, not common), not a substitute for a
        #   missing common-stock buyback figure.
        #
        # Listed BEFORE their preferred counterparts (least-preferred position, same
        # "fallback listed first" convention as the cash/debt fallbacks above) AND marked
        # fallback-only in load_financial_statements.py's field_mapping
        # (_SBC_BUYBACK_FALLBACK_ONLY_FIELDS) so a filer that reports the standard concept
        # always keeps that value - these only fill the gap when the standard concept is
        # absent for that fiscal year, never overwrite it.
        "AllocatedShareBasedCompensationExpense",
        "ShareBasedCompensation",
        "PaymentsForRepurchaseOfEquity",
        "PaymentsForRepurchaseOfCommonStock",
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


def _aggregate_concepts(  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
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
            # FIXED 2026-08-17 (SEC-vs-yfinance audit): foreign private issuers filing
            # 20-F/40-F often report monetary facts in home-market currency instead of
            # USD, with no separate USD-denominated fact anywhere in the filing - live-
            # confirmed via real companyfacts JSON: SHG (Shinhan) tags "Assets" only
            # under unit="KRW" ($739.76e12 raw KRW, ~$550B real), MUFG/SMFG only under
            # unit="JPY". Every dollar-value concept in this file was being pulled
            # regardless of unit, so these filers' total_assets/long_term_debt/revenue/
            # etc. landed in the DB as raw local-currency magnitudes masquerading as
            # USD - off by ~100-1000x (KRW/JPY are both ~3-4 orders of magnitude weaker
            # than USD). Live DB scan found 15 symbols with total_assets > $50 trillion
            # (BCH, BSAC, EC, KB, KEP, MFG, MUFG, NMR, PKX, SHG, SMFG, TLK, TM, VFS, WF)
            # - all real foreign banks/industrials whose true USD-equivalent assets are
            # 2-4 orders of magnitude smaller, plus an unknown number of smaller foreign
            # filers below that crude threshold that are still wrong without looking
            # absurd. No reliable per-filer FX rate is available in XBRL to convert
            # these correctly (same "can't safely correct, only detect" situation as
            # the rejected NumberOfSharesOutstanding IFRS alias above) - skip any
            # non-USD 3-letter ISO-4217-style currency unit entirely rather than fabricate
            # a converted value; "shares"/"pure"/"USD/shares" units (share counts, ratios,
            # per-share figures) don't match this 3-letter-uppercase-currency-code shape
            # and are unaffected. A filer left without a real USD fact gets an honest
            # NULL, not a silently wrong number 2-4 orders of magnitude off.
            #
            # FIXED 2026-08-17 (goal: "no SEC data" audit): that blanket rule also caught
            # CAD/GBP/EUR/AUD/CHF/JPY filers (CP, ASML, BBVA, BCS, BAP, BCE and 270+ more
            # live-confirmed via DB scan) whose currencies are NOT a 100-1000x magnitude
            # mismatch like KRW/JPY's original unit-scale bug - these are liquid,
            # developed-market currencies within roughly a 2x band of USD historically.
            # fx_rates.py fetches a REAL historical ECB rate for the filing's own period-
            # end date (never a guessed/current-day rate applied retroactively, never a
            # fallback value) - see that module's docstring for the full rationale and
            # why volatile/emerging-market currencies are deliberately excluded. A rate
            # lookup failure still leaves the value NULL, same fail-closed discipline as
            # every other currency this guard rejects outright.
            _currency_code = _extract_currency_code(_unit)
            is_major_currency = _currency_code != "USD" and _currency_code in MAJOR_CURRENCIES
            if (
                _currency_code != "USD"
                and len(_currency_code) == 3
                and _currency_code.isalpha()
                and _currency_code.isupper()
                and not is_major_currency
            ):
                continue
            # FIXED 2026-08-18 (no-SEC-data audit continuation): live-confirmed via GM and
            # DIS - both file normal 10-Ks every year, yet annual_balance_sheet had a
            # fiscal_year=2026 row (the current, not-yet-concluded fiscal year) with
            # total_assets/stockholders_equity populated from a 10-Q's mid-year instant
            # snapshot (e.g. GM: Assets end=2026-06-30, form=10-Q, val=$282.742B) while
            # long_term_debt stayed NULL because no 10-Q that quarter re-tagged that
            # concept. Real, complete FY2025 data (long_term_debt=$131.574B) already
            # existed one row back, but every "ORDER BY fiscal_year DESC LIMIT 1" caller
            # picked the incomplete FY2026 stub instead - this single pattern explains a
            # large share of "missing_sec_data" across quality_metrics/value_metrics
            # (debt_to_equity, interest_coverage, total_debt, roic_pct, ...), not a
            # per-concept fallback gap. The instant-fact "prefer latest end date" logic
            # below (test_sec_statements_instant_fact_prefers_latest_end_date.py) already
            # established that only a true fiscal-year-end snapshot should win within a
            # single bucket; this closes the related gap where a mid-year 10-Q snapshot
            # creates an entirely NEW, premature bucket for a fiscal year whose 10-K
            # hasn't been filed yet. Only suppresses 10-Q/6-K instant facts when this
            # concept has a real annual-report history at all - quarterly-only reporters
            # (no 10-K/20-F/40-F ever, e.g. EE) keep using their 10-Q instant facts as the
            # only available annual data, same fallback-of-last-resort precedent as
            # _PRIMARY_STATEMENT_FORMS above.
            has_annual_report_form = any(e.get("form") in _ANNUAL_REPORT_FORMS for e in entries)
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
                #
                # FIXED 2026-08-09: annual extraction had no check on the entry's actual
                # reporting SPAN, so a genuine single-quarter duration fact (~90 days) was
                # accepted into the annual "FY" bucket with no annualization - silently
                # masquerading as a full year's figure. Live-confirmed via ORLY: its FY2026
                # 10-K hasn't been filed yet (mid-year), so revenue/gross_profit had no real
                # annual entry; but a real Q1-2026 "InterestAndDividendIncomeOperating" fact
                # (a minor interest-income line, $1.75M, unrelated to their real ~$4B/qtr
                # retail revenue) got bucketed into fiscal_year=2026 "FY" as if it were the
                # year's revenue, producing garbage 1000%+ margins downstream once divided
                # against a genuine (also wrongly quarter-only) gross_profit figure. Duration
                # (end - start) is only meaningful for flow/duration facts (revenue, income,
                # cash flow - always have "start"); instant/point-in-time balance-sheet facts
                # (Assets, Liabilities, ...) have no "start" and are correctly accepted for any
                # fp, since an "as of" balance is valid regardless of the tag's fp. Threshold
                # (330 days) intentionally excludes real single-quarter chunks (~90 days) while
                # still accepting genuine full-year cumulative facts that got mistagged with a
                # quarterly fp (e.g. some Q4 YTD figures span the whole year).
                #
                # WIDENED 2026-08-09 (same day, later session): the check above only fired for
                # fp in ('Q1'-'Q4'), on the assumption a short-duration entry would always carry
                # a quarterly fp tag. Live-confirmed false via AAT (American Assets Trust, a
                # REIT): its FY2025 10-K's XBRL "Revenues" facts include a genuinely 90-day
                # entry (2024-01-01 to 2024-03-31, real Q1 2024 data used as a comparative
                # figure elsewhere in the filing) tagged fp='FY' - the SEC fy/fp combination
                # apparently isn't a reliable proxy for actual span even when fp='FY'. That
                # entry was accepted into the FY2024 annual bucket, understating real revenue
                # ($110.7M quarter vs a real ~$440M+ full year, confirmed via the same filing's
                # own comparative FY2023 entry). Now applies the same span check to every fp
                # value during annual extraction, not just Q1-Q4 - only gated on period=="annual"
                # so quarterly extraction (which legitimately wants short-duration entries) is
                # unaffected.
                start_date = entry.get("start")
                if period == "annual" and start_date and entry.get("end"):
                    try:
                        span_days = (
                            datetime.date.fromisoformat(entry["end"]) - datetime.date.fromisoformat(start_date)
                        ).days
                    except ValueError:
                        span_days = None
                    if span_days is not None and span_days < 330:
                        continue  # Real single-quarter/partial-year data - not annual

                # FIXED 2026-08-18 (no-SEC-data audit continuation): see the
                # has_annual_report_form comment above this loop. An instant fact sourced
                # from a 10-Q/6-K must not seed the annual bucket when this concept has
                # real 10-K/20-F/40-F history - it's a genuine mid-year snapshot, not a
                # fiscal-year-end position, and the fiscal year it falls in (derived from
                # its own end date below) usually has no 10-K filed yet at all.
                if (
                    period == "annual"
                    and not start_date
                    and has_annual_report_form
                    and entry.get("form") not in _ANNUAL_REPORT_FORMS
                ):
                    continue

                if period == "annual":
                    if fp == "FY" or fp is None or fp in ("Q1", "Q2", "Q3", "Q4"):
                        pass  # Accept annual, proxy, and quarterly(-but-full-span) data
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

                # FIXED 2026-08-16: 52/53-week fiscal calendars (common among retail/
                # industrial filers, e.g. SWK) can end a few days into January instead
                # of Dec 31 - live-confirmed SWK's real FY2020 10-K reports fy=2020,
                # start=2019-12-29, end=2021-01-02 (370-day/53-week year, majority of
                # days in calendar 2020). Bucketing by end-date's bare calendar year put
                # this in "2021", silently colliding with (and getting overwritten by)
                # FY2021's own later-filed entry - leaving FY2020 revenue/net_income
                # NULL (data_unavailable='incomplete_sec_filing_income') despite SEC
                # having the data all along; live-confirmed via direct DB query this
                # single mislabeling pattern accounts for a meaningful share of the
                # ~1,077 historical-year "incomplete_sec_filing" rows. Narrowly scoped
                # to end dates in the first 10 days of January, so ordinary non-calendar
                # fiscal years that end well into January/February (e.g. Walmart's Jan
                # 31) or other months (e.g. Apple's Sep 30) are untouched - only the
                # narrow year-end-crosses-Jan-1 case is affected. entry['fy'] is trusted
                # here specifically because in this window it's the filing's own current-
                # period label, not a comparative-year figure (see comment above) - only
                # applied when it actually points one year earlier than the naive
                # end-date bucket, so a filer that genuinely intends the end-year label
                # is left alone.
                if period == "annual" and end_date and len(end_date) >= 10 and end_date[5:10] <= "01-10":
                    fy = entry.get("fy")
                    if isinstance(fy, int) and fy == period_year - 1:
                        period_year = fy

                # FIXED 2026-08-18 (goal: "no SEC data"/missing factor inputs audit): DEI
                # cover-page facts (e.g. EntityCommonStockSharesOutstanding) are "as of the
                # latest practicable date before filing" snapshots, not economic-activity
                # facts - their own end date can be weeks to months AFTER the real fiscal
                # year end. Live-confirmed via AAP: the FY2024 10-K's real revenue duration
                # fact ends 2024-12-28 (bucketed fiscal_year=2024, correct), but its
                # accompanying dei:EntityCommonStockSharesOutstanding cover-page fact is
                # dated 2025-02-19 - 6 weeks later, crossing into the next calendar year.
                # Bucketing by end-date year (the general rule above, justified for us-gaap/
                # ifrs facts since SEC's fy tag conflates current-year and comparative-year
                # data within one filing - see the "Use period end year..." comment above)
                # created a phantom fiscal_year=2025 bucket containing ONLY this one DEI
                # fact, sandwiched between the real FY2024 and FY2026 buckets - and every
                # prior-year lookback in load_value_quality_growth_metrics.py keys strictly
                # off fiscal_year-1, so this phantom bucket silently blocked EVERY
                # *_growth_yoy/*_trend metric for the symbol (live DB scan: 120 active
                # symbols have this exact sandwiched-incomplete-year signature). Unlike
                # us-gaap/ifrs facts, DEI cover-page facts don't carry historical
                # comparative-year entries (one "as of" value per filing, not a multi-year
                # table), so entry['fy'] IS reliably the filing's real fiscal year for this
                # source - trust it directly instead of the end-date derivation.
                if source == "dei" and period == "annual" and isinstance(entry.get("fy"), int):
                    period_year = entry["fy"]

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
                # Keep latest filing if multiple for same period, EXCEPT: never let a
                # non-primary-statement form (DEF 14A, 8-K, S-1, etc.) outrank a primary
                # annual/quarterly-report form (10-K/10-Q and their foreign-filer
                # equivalents) just because it was filed later.
                #
                # FIXED 2026-08-17 (goal: "no SEC data" audit): SEC's mandatory Pay vs
                # Performance table (Item 402(v), required in every proxy since 2023) tags
                # "Net Income" in XBRL using the table's display units (thousands) but
                # numerous filers/filing agents omit the corresponding XBRL scale factor,
                # so the tagged fact is the raw table number - 1000x too small - instead of
                # true dollars. DEF 14A proxies are filed AFTER the 10-K for the same fiscal
                # year, so the old date-only tie-break silently let this broken value
                # clobber the correct 10-K NetIncomeLoss. Live-confirmed via real
                # companyfacts JSON, filed literally today (2026-08-17): FDX FY2026 10-K
                # NetIncomeLoss=$4,433,000,000 (filed 2026-07-20) vs its DEF 14A entry for
                # the same period=$4,433 (filed 2026-08-17); same pattern for MDT
                # ($4,801,000,000 vs $4,801) and MIST ($-63,058,000 vs $-63,058). Live DB
                # scan found 154 symbols with this exact signature (net_income < $1M despite
                # revenue > $10M) just from the current watermark, and it is actively
                # recurring every proxy season, not a one-time historical gap. Primary forms
                # still lose to a LATER primary form (a genuine 10-K/A restatement should
                # still win), and a non-primary form is still accepted as a last-resort
                # fallback when no primary-form entry exists for that period at all
                # (preserves the 2026-07-31 DEF 14A fallback for proxy-only reporters like
                # EE, which have no 10-K net income at all).
                entry_filed = entry.get("filed")
                if not entry_filed:
                    raise ValueError(
                        f"SEC data missing filed date for {symbol} {period}. "
                        f"Cannot determine latest filing without date information. "
                        f"Check SEC data source or API response."
                    )
                entry_form = entry.get("form")
                entry_rank = 1 if entry_form in _PRIMARY_STATEMENT_FORMS else 0
                row_filed = row.get(f"_filed_{col}")
                row_end = row.get(f"_end_{col}")
                rank_key = f"_rank_{col}"
                row_rank = int(row[rank_key]) if rank_key in row else 0
                # Form-rank gates first: a primary form (10-K/10-Q) always outranks a
                # non-primary one (DEF 14A, 8-K, S-1, etc.) regardless of end/filed date -
                # see the 2026-08-17 DEF 14A comment above. Only when ranks tie do we fall
                # through to the existing instant-vs-duration end-date/filed-date tiebreak.
                if col not in row:
                    should_replace = True
                elif entry_rank != row_rank:
                    should_replace = entry_rank > row_rank
                else:
                    # FIXED 2026-08-18 (live-verified RIGL): instant/point-in-time balance-
                    # sheet facts (no "start" - see this loop's is_instant-equivalent comment
                    # above) for DIFFERENT periods within the same calendar year (e.g. a Q1
                    # comparative StockholdersEquity figure re-cited in a later 10-Q's
                    # context, alongside the real FY-end figure) collide into the SAME
                    # (fiscal_year, "FY") bucket and frequently share the identical "filed"
                    # date (both facts come from the same filing). "latest filed wins" alone
                    # then picks whichever entry happened to be iterated last - arbitrary,
                    # not correctness-driven. Live-confirmed: RIGL's real FY2025 10-K/10-Q
                    # filings tag StockholdersEquity end=2025-03-31 ($18.567M, a Q1 snapshot)
                    # AND end=2025-12-31 ($391.48M, the real year-end) with the SAME filed
                    # date - the Q1 value won on iteration order, producing net_income
                    # ($367.0M) / equity($18.567M) = 1976.75% ROE instead of the real ~94%.
                    # For instant facts, prefer the entry whose end date is latest (closest
                    # to the true fiscal year end) before falling back to filed-date as a
                    # tiebreak; duration facts (has "start") are unaffected - their span-day
                    # filter above already narrows the field to genuine annual totals, where
                    # "most recently filed" legitimately means "most likely restated/
                    # corrected".
                    is_instant = not start_date
                    if is_instant:
                        should_replace = row_end is None or end_date > row_end
                        if not should_replace and end_date == row_end:
                            should_replace = row_filed is None or entry_filed > row_filed
                    else:
                        should_replace = row_filed is None or entry_filed > row_filed
                if should_replace:
                    val = entry.get("val")
                    if is_major_currency and isinstance(val, (int, float)) and end_date:
                        fx_rate = _fx_rate_cache.get_usd_rate(_currency_code, end_date)
                        if fx_rate is None or fx_rate == 0:
                            # No real rate available for this exact date - fail closed,
                            # never guess. Leaves this entry unset for this column, same
                            # as if the whole currency had been rejected outright.
                            continue
                        val = val / fx_rate
                    row[col] = val
                    row[f"_filed_{col}"] = entry.get("filed")
                    row[f"_end_{col}"] = end_date
                    row[f"_rank_{col}"] = entry_rank

    # Drop helper fields, return sorted (require fiscal_year for ordering)
    # period_end/filed/form are row bookkeeping set unconditionally above (not XBRL
    # concepts, no target column) - left in, they guaranteed-fire sec_base.py's
    # "Unmapped SEC field" warning on every single row of every symbol across all 6
    # statement tables, drowning real per-symbol unmapped-concept warnings in noise
    # (564,688 lines / 109MB from one 2026-08-14 run, confirmed via log analysis).
    result = []
    for row in rows.values():
        result.append(
            {
                k: v
                for k, v in row.items()
                if not k.startswith("_filed_")
                and not k.startswith("_end_")
                and not k.startswith("_rank_")
                and k not in ("period_end", "filed", "form")
            }
        )
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
