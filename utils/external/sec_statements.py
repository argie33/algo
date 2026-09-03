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

# See the "implausible fiscal_year" sanity-bound comment in _aggregate_concepts
# (BUG FOUND 2026-08-19).
_MIN_PLAUSIBLE_FISCAL_YEAR = 1990


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
    # FIXED 2026-09-03 (same sweep): TSM (Taiwan Semiconductor) live-confirmed via real
    # companyfacts JSON - reports trade receivables under this concept instead of
    # "TradeAndOtherCurrentReceivables" above (USD 6.5746B FY2023 / 8.2551B FY2024,
    # continuous). Same target key as that concept - genuinely the narrower "trade
    # receivables only" IFRS taxonomy element (not a combined trade+other concept), close
    # enough in meaning to the us-gaap "AccountsReceivableNetCurrent" target it feeds.
    ("CurrentTradeReceivables", "accounts_receivable_net_current"),
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
    # FIXED 2026-09-03 (same sweep): Altman Z''-Score's Retained Earnings/Total Assets
    # term (see get_balance_sheet()'s "RetainedEarningsAccumulatedDeficit" comment - that
    # concept is us-gaap only, and its own comment's "no known taxonomy-variant fallback
    # needed" claim was wrong) went universally NULL for every IFRS filer - live-confirmed
    # 7/9 checked (AZN/SHEL/NVO/BHP/SAP/RY/HSBC; NVS/TTE genuinely don't tag it) via real
    # companyfacts JSON, e.g. TSM: ifrs-full "RetainedEarnings" reports both a TWD-unit and
    # a directly-usable USD-unit series, USD 118.1145B as of FY2024, continuous 2018-2024.
    # Target key routes into load_financial_statements.py's _ANNUAL_BALANCE_EXTRA (the
    # same "retained_earnings_accumulated_deficit" -> "retained_earnings" mapping the real
    # us-gaap concept already uses), not a new key - IFRS's single combined retained-
    # earnings/accumulated-deficit line is the same concept the GAAP tag represents.
    ("RetainedEarnings", "retained_earnings_accumulated_deficit"),
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
    # FIXED 2026-08-31 (goal session: "get all the data we need" full-coverage audit):
    # given its OWN target_key ("insurance_revenue") instead of sharing "revenues" with
    # plain Revenue/RevenueAndOperatingIncome - see load_financial_statements.py's
    # _REVENUE_TOTAL_CANDIDATE_FIELDS comment for the live-verified BBVA/HSBC bug this
    # fixes (a bank's real insurance-SEGMENT figure, sometimes negative, was winning a
    # same-filed-date tie against the bank's own true consolidated total purely because
    # this alias is listed earlier in this list than RevenueAndOperatingIncome - the
    # "last-listed-wins" tiebreak documented on that alias's own comment below never
    # actually fires when both facts share an identical filed date, which is the common
    # case for facts drawn from the same annual filing). Splitting the key lets the new
    # magnitude-based final resolution in transform() choose correctly per filer instead
    # of an accidental list-position artifact deciding it.
    ("InsuranceRevenue", "insurance_revenue"),
    # FIXED 2026-08-19 (same-day follow-up, found by generalizing the InsuranceRevenue
    # search): the "Revenue" concept going silent partway through a filer's history isn't
    # insurance-specific - live-confirmed via UBS's real companyfacts JSON: "Revenue"
    # tagged through FY2021 (USD 35.393B), then goes silent; "RevenueAndOperatingIncome"
    # is the SAME total (FY2021 value under this concept: also USD 35.393B, exact match)
    # and has real, continuous data straight through FY2025 (USD 49.573B) - UBS (not an
    # insurer) simply re-tagged the identical figure under a different concept name
    # starting FY2022, likely alongside its 2023 Credit Suisse acquisition's reporting
    # changes. Same "stale anchor fiscal year masks everything" failure mode as AEG - UBS's
    # revenue was NULL for 4 straight years (FY2022-2025) before this fix. Listed after
    # "Revenue" (last-listed-wins is safe here too: verified their overlapping years, e.g.
    # FY2021, agree exactly; where an early filing's since-restated figure differs slightly,
    # _aggregate_concepts's own latest-filed-wins tiebreak converges both concepts to the
    # same final restated number anyway).
    ("RevenueAndOperatingIncome", "revenues"),
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
    # FIXED 2026-08-22 (goal session: "Insufficient history"/revenue-gap audit): foreign
    # (non-US, IFRS-filing) banks report neither "Revenue" nor "RevenuesNetOfInterestExpense"
    # - live-confirmed via WF (Woori Financial Group, a major Korean bank holding company,
    # $55B market cap)'s real companyfacts JSON: real, growing NetIncomeLoss on file for
    # every fiscal year 2015-2024 (e.g. FY2022 $2.67B), but revenue NULL for the same 10
    # straight years despite continuously filing real 20-Fs, wrongly presenting as
    # "insufficient_history" downstream in growth_metrics (WF has 16+ years of real SEC
    # data on file, just not under any previously-mapped revenue concept). Real gross
    # interest income/expense line under ifrs-full:InterestRevenueExpense has full USD-unit
    # coverage FY2017-2024 (e.g. FY2022 $6.9B - a plausible bank revenue figure well above
    # net_income, not a mismatched/wrong concept). Same "gross interest income, not net"
    # choice as InterestIncomeOperating below (mortgage REITs) - IFRS 7's required interest
    # revenue/expense split is the closest bank analog to a top-line revenue figure these
    # filers report. Listed after RevenuesNetOfInterestExpense (a more complete figure when
    # a filer reports both) per this list's last-listed-wins-only-when-nothing-else
    # convention.
    ("InterestRevenueExpense", "interest_revenue_expense"),
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
    # FIXED 2026-08-23 (goal: pre-real-money data-integrity review, "insufficient_history"
    # eps_growth audit): IAS 33.68 requires filers with discontinued operations to present
    # EPS split into Continuing/Discontinued components, and some filers ONLY tag the split
    # - never a combined BasicEarningsLossPerShare/DilutedEarningsLossPerShare concept at
    # all. Live-confirmed via TV (Grupo Televisa, real companyfacts JSON): tags ONLY
    # DilutedEarningsLossPerShareFromContinuingOperations/...FromDiscontinuedOperations (no
    # Basic-shaped concept whatsoever, no combined Diluted concept either) - real MXN/shares
    # values on file for FY2020-2022 (e.g. FY2022 continuing=-0.03, discontinued=0.17), but
    # annual_income_statement.earnings_per_share was NULL for every fiscal year on record
    # despite 10+ years of real revenue/net_income already loaded, wrongly presenting
    # downstream as growth_metrics "insufficient_history" for a well-covered filer. These
    # four are fallback-only inputs summed by
    # _fill_earnings_per_share_from_continuing_discontinued_split() below (genuinely
    # different aggregation than _aggregate_concepts' one-column "last value wins" merge,
    # same reasoning as _fill_long_term_debt_from_noncurrent_current_split above) - not
    # listed as plain aliases, since that would let the Continuing-only portion silently
    # overwrite a real combined total on last-listed-wins for filers that report both.
    ("BasicEarningsLossPerShareFromContinuingOperations", "earnings_per_share_basic_continuing"),
    ("BasicEarningsLossPerShareFromDiscontinuedOperations", "earnings_per_share_basic_discontinued"),
    ("DilutedEarningsLossPerShareFromContinuingOperations", "earnings_per_share_diluted_continuing"),
    ("DilutedEarningsLossPerShareFromDiscontinuedOperations", "earnings_per_share_diluted_discontinued"),
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
    # FIXED 2026-08-29 (goal: "full data" audit continuation, oil & gas E&P follow-up): the
    # two IFRS PP&E-purchase concepts above have never matched TTE (TotalEnergies, 20-F) or
    # SHEL (Shell plc, 20-F) - both real, current oil & gas majors with real capex, not a
    # structural "no capex" sector gap. Live-confirmed via real companyfacts JSON: TTE tags
    # "AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment" through
    # FY2023 ($16.478B FY2023, $13.699B FY2022, $11.647B FY2021) then switches to the
    # "...IncludingRightofuseAssets" variant from FY2024 onward ($13.471B FY2024, $15.756B
    # FY2025) - both a PP&E roll-forward "additions" disclosure, not a primary cash-flow-
    # statement line, but the closest real capex proxy TTE reports (same aggregation
    # semantics as this file's existing "costs incurred" oil & gas fallback below). SHEL
    # tags "PropertyPlantAndEquipmentExpendituresRecognisedForConstructions" ($21.815B
    # FY2025, $27.852B FY2024) - plausible against Shell's publicly reported ~$20-24B/yr
    # capex guidance despite the "Recognised for Constructions" name (a filer-specific
    # extension label, not evidence of a narrower construction-only scope - no other SHEL
    # concept comes close to this magnitude). SHEL's "ContractualCommitmentsForAcquisition
    # OfPropertyPlantAndEquipment" was also checked and rejected: real data but stale
    # (nothing filed since FY2019) and semantically a forward commitment, not actual spend
    # - not added.
    (
        "AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment",
        "payments_to_acquire_property_plant_and_equipment",
    ),
    (
        "AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipmentIncludingRightofuseAssets",
        "payments_to_acquire_property_plant_and_equipment",
    ),
    (
        "PropertyPlantAndEquipmentExpendituresRecognisedForConstructions",
        "payments_to_acquire_property_plant_and_equipment",
    ),
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, capex
    # generic-gap investigation): TM (Toyota Motor Corp, CIK 0001094517) stopped tagging
    # either us-gaap "PaymentsToAcquirePropertyPlantAndEquipment" or
    # "PaymentsToAcquireProductiveAssets" (both real, continuous through FY2020, both
    # already mapped above/in the us-gaap list) after its FY2020 20-F - live-confirmed via
    # real companyfacts JSON that this ifrs-full concept picks up immediately where they
    # stop and continues with real, growing values through FY2025 (JPY 3.582T FY2020,
    # 3.610T FY2021, 3.612T FY2022, 3.496T FY2023, 4.848T FY2024, 5.991T FY2025 -
    # continuously plausible against Toyota's real, publicly reported ~JPY3.5-6T/yr capex
    # scale as EV/battery investment ramped, no other concept in Toyota's companyfacts
    # comes close to this magnitude for FY2021+). Same "closest available proxy" caveat as
    # the PropertyPlantAndEquipmentExpendituresRecognisedForConstructions/SHEL and
    # AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment/TTE concepts
    # above: a PP&E roll-forward "additions to noncurrent assets" disclosure rather than a
    # concept scoped to PP&E alone by name, but the real, current capex figure these
    # filers actually report - no overlap risk with the FY2020-and-earlier concepts above
    # (this concept only appears starting FY2020, after those go silent).
    (
        "AdditionsToNoncurrentAssets",
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
    # FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction): KGC (Kinross
    # Gold, a real, well-known dividend-paying 40-F Canadian FPI) reports neither
    # "DividendsPaid" nor "DividendsPaidClassifiedAsFinancingActivities" - live-confirmed
    # via real companyfacts JSON its actual financing-activities dividend line is this
    # more granular taxonomy variant, which splits the combined concept above into
    # parent-equity-holders vs. noncontrolling-interest portions (KGC also separately
    # reports "DividendsPaidToNoncontrollingInterestsClassifiedAsFinancingActivities",
    # deliberately NOT aliased here - a different, smaller NCI-only figure, not part of
    # this column). Values verified exact against KGC's own DividendsPaidOrdinaryShares
    # sibling concept for FY2021 ($151.1M both) before adding - same "cash-flow-statement
    # financing line" semantics as DividendsPaidClassifiedAsFinancingActivities above, not
    # AEM's rejected DividendsPaidOrdinaryShares (a different, larger figure for AEM
    # specifically - see that concept's own comment above for why it stays unaliased).
    ("DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities", "payments_of_dividends"),
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
        # ADDED 2026-09-02 (goal session: "missing SEC/XBRL data" audit, KKR live-
        # confirmed): limited-partnership-structured filers (KKR & Co. L.P. before its
        # 2018 conversion to a corporation, and other PE firms/MLPs with a similar
        # history) tag total partner capital as "PartnersCapital"/"PartnersCapital
        # IncludingPortionAttributableToNoncontrollingInterest" instead of any
        # "StockholdersEquity" concept - live-confirmed via real SEC companyfacts JSON
        # that KKR's FY2009-2017 10-Ks (CIK 0001404912) have ZERO StockholdersEquity-
        # family facts, only PartnersCapitalIncludingPortionAttributableToNoncontrolling
        # Interest (e.g. FY2014). Mapped to the same "stockholders_equity" DB column via
        # load_financial_statements.py's fallback-only field mapping (never overwrites a
        # real StockholdersEquity value - mutually exclusive by fiscal year in practice,
        # since a filer's legal structure conversion is a one-time event, but kept
        # fallback-only for the same defensive reason as the concept above).
        "PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest",
        "PartnersCapital",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" audit):
        # LLC-structured domestic filers (not FPIs) tag "MembersEquity" instead of any
        # StockholdersEquity/PartnersCapital concept - live-confirmed via real SEC
        # companyfacts JSON for 3 universe symbols (all `is_foreign_private_issuer=False`,
        # `entity_type='operating'`): APGE (Apogee Therapeutics) FY2025 $903,883,000 +
        # current Q2 2026 10-Q $1,194,604,000, ARXS (Arxis) current Q2 2026 10-Q
        # $3,183,274,000, ITG (ITG, Inc./DE/) current Q2 2026 10-Q $34,376,000 - all real,
        # current (through mid-2026), USD-denominated instant facts, zero StockholdersEquity/
        # PartnersCapital facts of any kind for any of the three. Same "direct legal-
        # structure-specific equivalent" pattern as PartnersCapital above (mutually
        # exclusive by entity type in practice - an LLC never also tags StockholdersEquity),
        # not fallback-only for the same reason.
        "MembersEquity",
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
        # FIXED 2026-09-03 (same sweep): WMT/RTX/COST all live-confirmed (via real
        # companyfacts JSON) reporting the primary balance-sheet "Receivables, net" line
        # under this concept instead of "AccountsReceivableNetCurrent" below - WMT: real
        # $9.975B FY2025/$11.172B FY2026; COST: $2.721B FY2024/$3.203B FY2025; RTX reports
        # both concepts with identical values ($14.701B FY2025). Fallback-only, listed
        # before the standard concept so a filer reporting both keeps the more specific
        # trade-only figure.
        "ReceivablesNetCurrent",
        "AccountsReceivableNetCurrent",
        # FIXED 2026-09-03 (same sweep): long-term-contract manufacturers (aerospace/defense
        # primes with real physical inventory) tag it under this concept instead of the
        # plain one below. Live-confirmed via real companyfacts JSON: BA/Boeing ($78.8B
        # FY2021 through $84.7B FY2025, continuous) has ZERO facts ever under `InventoryNet`
        # despite having a real, huge inventory balance; HII/Huntington Ingalls has both
        # concepts defined in its taxonomy but `InventoryNet` itself has zero actual facts
        # filed ($183M-$219M FY2022-2025 all under this concept instead) - confirms it's a
        # real, reused standard element for this filer shape, not a one-off. Fallback-only,
        # listed before the standard concept so a filer reporting both (like HII) keeps
        # whichever one actually has real facts via last-wins overwrite.
        "InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings",
        "InventoryNet",
        # FIXED 2026-09-03 (same sweep): regulated utilities (ES/Eversource live-confirmed
        # via real companyfacts JSON: $39.499B FY2023 / $40.987B FY2024 / $45.931B FY2025,
        # continuous) tag net PP&E under this utility-specific concept instead of the plain
        # one below - a real, sector-standard taxonomy element (rate-base-regulated utility
        # accounting), not a filer-specific quirk. A live DB scan found 11 Utilities-sector
        # symbols (ES/TXNM/AVA/CWT/SWX/MSEX/RGCO among others) with real total_assets but
        # NEVER a single ppe_net value. Fallback-only, listed before the standard concept so
        # a utility holding company that also tags the plain concept keeps that value.
        "PublicUtilitiesPropertyPlantAndEquipmentNet",
        # FIXED 2026-09-03 (same sweep): post-ASC-842 combined PP&E + finance-lease
        # right-of-use concept - DASH (DoorDash) and DINO (HF Sinclair) both live-confirmed
        # via real companyfacts JSON reporting their entire real net PP&E only under this
        # concept in real 10-K filings (DASH: $778M FY2024/$1.067B FY2025; DINO: $6.627B
        # FY2023/$6.558B FY2024/$6.533B FY2025), never the plain concept below. Shared
        # standard taxonomy element (not company-specific), likely broadly applicable
        # post-2019 (ASC 842 adoption). Fallback-only, same before-the-standard-concept
        # ordering as the utility fallback above.
        "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
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
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): the
        # SAME "wiring half-landed" bug the comment immediately above this one already
        # describes and fixed once - the 2026-08-18 ADC/net-lease-REIT fix added
        # "debt_instrument_carrying_amount" to load_financial_statements.py's
        # _BALANCE_FIELD_MAPPING/_DEBT_FALLBACK_ONLY_FIELDS but never added the matching
        # concept string HERE, so SecEdgarClient never actually fetched it from SEC -
        # live-reverified 2026-09-03 that ADC itself (the symbol this fallback was written
        # for) is still NULL for long_term_debt every fiscal year 2023-2025 despite real
        # DebtInstrumentCarryingAmount values in its companyfacts JSON ($1.96B-$3.32B), and
        # DLR (Digital Realty, another net-lease/data-center REIT) is NULL for its entire
        # history despite a real, undimensioned $17,537,652,000 FY2023 fact under this same
        # concept. Confirms this fallback has never fired for any symbol since it was
        # written - the mapping-only "fix" silently did nothing for over 2 weeks.
        "DebtInstrumentCarryingAmount",
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
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, DE debt
        # gap investigation): Deere & Company (CIK 0000315189) tags its primary real
        # current debt under this plain, standard us-gaap concept - live-confirmed via
        # real companyfacts JSON and the rendered FY2025 10-K consolidated balance sheet
        # ("Short-term borrowings" $13,796,000,000 FY2025/$13,533,000,000 FY2024, real and
        # continuous back to FY2020; DE never tags CommercialPaper/ShortTermBorrowings/
        # SeniorNotesCurrent, so no overwrite collision with the concepts above for this
        # filer). DELIBERATELY excludes DE's smaller sibling concept "SecuredDebt"
        # ("Short-term securitization borrowings", $6,596,000,000 FY2025) - this loader's
        # transform() has no summing mechanism for two concepts mapped to the same target
        # column (confirmed by reading loaders/helpers/sec_base.py's transform(): plain
        # `row[db_field] = value` overwrite, last-processed-wins, not additive - same as
        # the CommercialPaper/ShortTermBorrowings pair above already documents as a known,
        # accepted limitation), so adding both here would silently DROP one of the two
        # real figures rather than capture both. Capturing DebtCurrent alone (the larger,
        # ~68% of DE's true current debt) is strictly better than the current NULL and
        # carries no risk of a wrong/incomplete-looking "complete" figure since it's not
        # claimed to include the securitization piece.
        "DebtCurrent",
        # FIXED 2026-09-03 (same sweep): EXPD (Expeditors International) tags its entire
        # real short-term debt under this concept - live-confirmed via real companyfacts
        # JSON: $53,068,000 FY2023 / $30,660,000 FY2024 / $30,263,000 FY2025, small but
        # real and continuous (a genuinely low-debt, asset-light freight-forwarding
        # business - EXPD has no other debt concept tagged anywhere in its companyfacts,
        # consistent with the real figure being this small, not a coverage gap masking a
        # larger number). Fallback-only, same generic-name caution as DebtCurrent above.
        "ShortTermBankLoansAndNotesPayable",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
        # no_recent_debt_components_symbols investigation): VRSN (VeriSign) tags its real,
        # current debt exclusively under "SeniorNotes"/"SeniorNotesCurrent" - live-
        # confirmed via real companyfacts JSON: SeniorNotes (noncurrent) FY2025
        # $1,788,200,000, growing from FY2024's $1,792,300,000 basis; VeriSign's older
        # "LongTermDebt" concept reports real $0 since FY2013 and "ConvertibleDebt" since
        # FY2018 (paid off/refinanced, not still in use) - no overlap with this concept's
        # real values in any year. Same "either/or alternative, plain concept" convention
        # as CommercialPaper/ShortTermBorrowings above (target: long_term_debt).
        "SeniorNotes",
        # Current-portion pairing for the concept above - same either/or convention as
        # CommercialPaper/ShortTermBorrowings (target: short_term_debt). VeriSign's own
        # SeniorNotesCurrent was $299,800,000 FY2024, $0 FY2025 (fully refinanced to
        # noncurrent that year) - a real, moving figure, not a placeholder.
        "SeniorNotesCurrent",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
        # total_debt_not_itemized investigation): AFL (Aflac) and MAA (Mid-America
        # Apartment Communities) both tag their entire real debt load under plain
        # "NotesPayable" instead of any LongTermDebt*/SeniorNotes*/DebtInstrument* concept
        # above - live-confirmed via real companyfacts JSON: AFL NotesPayable FY2025
        # $8,330,000,000, a real, continuously growing figure back to FY2008 ($1.721B),
        # consistent with Aflac's real, publicly known ~$8B debt scale; MAA NotesPayable
        # FY2025 $5,405,372,000, continuous back to FY2009 ($1.4B), consistent with a large
        # apartment REIT's real mortgage/unsecured debt load. Neither filer has a
        # "NotesPayableCurrent" sibling concept (no current/noncurrent split in the source
        # data, same as SeniorNotes above), so this is a single-figure fallback targeting
        # long_term_debt only, same convention as SeniorNotes/CommercialPaper. Fallback-only
        # (see _DEBT_FALLBACK_ONLY_FIELDS) since "NotesPayable" is a generic enough concept
        # name that a filer reporting a real, more complete LongTermDebt/SeniorNotes figure
        # must always keep that value instead.
        "NotesPayable",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
        # continuation): PGR (Progressive) stopped tagging plain "LongTermDebt" after
        # FY2015 (last real fact 2015-12-31, $2.708B) - live-confirmed via real companyfacts
        # JSON that every 10-K since tags its real combined debt under
        # "DebtLongtermAndShorttermCombinedAmount" instead: $4.899B FY2021 growing to
        # $6.897B FY2025, continuous and consistent with Progressive's real, publicly known
        # ~$6.9B debt scale - not debt-free, just a taxonomy switch (same pattern as ADC's
        # DebtInstrumentCarryingAmount switch already fixed above). No current/noncurrent
        # split reported under this concept, so single-figure fallback targeting
        # long_term_debt only, same convention as NotesPayable immediately above.
        # Fallback-only (see _DEBT_FALLBACK_ONLY_FIELDS) so a filer reporting the standard
        # LongTermDebt concept for a given year always keeps that value.
        "DebtLongtermAndShorttermCombinedAmount",
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
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
        # total_debt_not_itemized investigation): small/mid-cap bank and thrift holding
        # companies (IBOC/International Bancshares, HBT/HBT Financial live-confirmed via
        # real companyfacts JSON) carry no conventional LongTermDebt/NotesPayable/
        # SeniorNotes at all - their only real debt instruments are trust-preferred
        # securities. IBOC: real $108.868M "JuniorSubordinatedDebentureOwedTo
        # UnconsolidatedSubsidiaryTrust" balance, continuous through FY2025-2026, never
        # tagged under any concept already fetched above. Listed after "SubordinatedDebt"
        # below (both fallback-only, first-populated-wins): a filer reporting both
        # instruments in the same fiscal year (HBT: real $84.026M SubordinatedDebt +
        # $52.939M JuniorSubordinatedDebenture as of 2026-Q2, two genuinely distinct real
        # instruments) only gets the larger/first-listed one, understating true combined
        # debt - accepted as strictly better than the current "not itemized" NULL, same
        # single-figure-not-perfect-sum convention as NotesPayable/SeniorNotes above.
        "SubordinatedDebt",
        "JuniorSubordinatedDebentureOwedToUnconsolidatedSubsidiaryTrust",
        # ADDED 2026-08-26 (Quality pillar literature audit): needed for Altman Z''-Score's
        # Retained Earnings/Total Assets term (the one term not derivable from concepts
        # already fetched above). Standard, near-universal US-GAAP concept - every filer with
        # a statement of stockholders' equity reports it.
        # CORRECTION 2026-09-03: this WAS missing a taxonomy-variant fallback after all -
        # IFRS filers report the equivalent under ifrs-full "RetainedEarnings" instead, went
        # universally NULL for every one of them until _BALANCE_IFRS_ALIASES added it above.
        "RetainedEarningsAccumulatedDeficit",
    ]
    rows = _aggregate_concepts(client, symbol, concepts, period, ifrs_aliases=_BALANCE_IFRS_ALIASES)
    _fill_long_term_debt_from_noncurrent_current_split(rows)
    if period == "annual":
        _fill_long_term_debt_from_segment_dimensional_facts(rows, client, symbol)
    return rows


def _fill_long_term_debt_from_segment_dimensional_facts(rows: list[dict[str, Any]], client: Any, symbol: str) -> None:
    """Last-resort fallback: sum segment-dimensional debt facts from the filing's own XBRL
    instance document when every concept-alias tier above found nothing for a fiscal year.

    See loaders/helpers/sec_segment_debt.py's module docstring (Ford live-confirmed
    2026-09-01) for why no concept alias can ever close this gap: SEC's companyconcept/
    companyfacts APIs - the only thing every fallback concept above reads from - structurally
    exclude any fact tagged inside a dimensional (segment) context. A filer like Ford that
    only tags real debt dimensionally (Company-excluding-Ford-Credit vs Ford-Credit segments)
    has ZERO entries for every concept above, indistinguishable via those APIs from "reports
    no debt at all" - the only fix is reading the actual filing.

    One extra HTTP fetch (submissions) + one XML fetch+parse per genuinely-missing fiscal
    year, not per symbol - a filer with real long_term_debt from any tier above never
    triggers this. Deliberately conservative for this first pass: only fires when
    long_term_debt is still None outright (not yet extended to "implausibly small vs
    total_liabilities" - see module docstring's SCOPE note for the narrower residual gap
    that leaves open, e.g. Ford's own 2018-2020 taxonomy-transition years).
    """
    from loaders.helpers.sec_segment_debt import find_10k_for_fiscal_year, sum_segment_dimensional_debt

    all_missing_years = [
        row["fiscal_year"] for row in rows if row.get("long_term_debt") is None and row.get("fiscal_year")
    ]
    if not all_missing_years:
        return

    # BUG FOUND 2026-09-01 (goal session: "understand our data gaps" - live-caught mid-run,
    # not theorized): this loop had no cap on how many fiscal years it would attempt per
    # symbol - a genuinely debt-free filer (real, not a data gap) has long_term_debt=None for
    # EVERY fiscal year in `rows` (this fallback can never find a debt fact that doesn't
    # exist), so every one of those years - live-confirmed some annual histories run 15-18
    # years deep (FLO: 18) - triggered its own submissions-fetch-then-XML-fetch-then-parse
    # round trip, unconditionally, on every single loader run. Caught live via a `py-spy dump`
    # (safe, read-only) on a genuinely stalled `load_financial_statements.py` process: the
    # per-symbol 30s timeout (LOADER_PER_SYMBOL_TIMEOUT_SECONDS) in `_run_symbol_pass` bounds
    # the *reported* time per symbol, but the underlying worker thread is daemon=True and
    # gets abandoned, not killed, when it times out - so a symbol stuck mid-way through a
    # dozen-plus sequential SEC fetches keeps running in the background indefinitely,
    # competing for the same shared `RateLimiter(2)` (2 req/sec, global) every other
    # in-flight and future thread needs. Over a multi-thousand-symbol run, this accumulates:
    # more and more abandoned zombie threads pile onto the same rate limiter, degrading
    # throughput for every symbol after them - a real, previously-undocumented resource-
    # contention bug, distinct from the already-fixed 2026-08-22 single-symbol-hang case.
    # Fix: only attempt the most recent 3 missing fiscal years per symbol. Live scoring only
    # ever reads the latest 1-2 annual rows (see load_stock_scores.py/load_sec_valuations.py),
    # so recovering a stale 2010-era debt figure this fallback was previously chasing has no
    # scoring value - bounding to recent years turns an unbounded (up to ~18) worst-case
    # HTTP-round-trip count into a small, fixed one, without changing behavior for the common
    # case (a symbol missing only its 1-3 most recent years, which this cap doesn't touch).
    missing_years = sorted(all_missing_years, reverse=True)[:3]

    try:
        cik = client.symbol_to_cik(symbol)
        submissions = client.get_submissions(cik)
    except Exception:
        logger.debug(
            f"[SEGMENT_DEBT] {symbol}: could not fetch submissions for dimensional debt fallback", exc_info=True
        )
        return

    for row in rows:
        if row.get("long_term_debt") is not None or row.get("fiscal_year") not in missing_years:
            continue
        located = find_10k_for_fiscal_year(submissions, int(row["fiscal_year"]))
        if located is None:
            continue
        accession, period_end = located
        try:
            xml_text = client.get_filing_xml(cik, accession, "10-K")
        except Exception:
            logger.debug(
                f"[SEGMENT_DEBT] {symbol} FY{row['fiscal_year']}: could not fetch instance XML "
                f"({accession}) for dimensional debt fallback",
                exc_info=True,
            )
            continue
        result = sum_segment_dimensional_debt(xml_text, period_end)
        if result is None:
            logger.debug(
                f"[SEGMENT_DEBT] {symbol} FY{row['fiscal_year']}: no unambiguous single-axis "
                f"business-segment debt decomposition found in {accession} - leaving "
                "long_term_debt None rather than risk an undercount from a partial context set."
            )
            continue
        total, segment_count = result
        logger.info(
            f"[SEGMENT_DEBT] {symbol} FY{row['fiscal_year']}: recovered long_term_debt="
            f"{total:,.0f} by summing {segment_count} business-segment dimensional contexts "
            f"({accession}) - standard concept extraction found none."
        )
        row["long_term_debt"] = total


def _fill_earnings_per_share_from_continuing_discontinued_split(rows: list[dict[str, Any]]) -> None:
    """Fallback-only: earnings_per_share_{basic,diluted} = ...FromContinuingOperations +
    ...FromDiscontinuedOperations, for IFRS filers (IAS 33.68) that only tag the
    continuing/discontinued EPS split rather than a single combined concept - see the
    _INCOME_IFRS_ALIASES comment above these four concepts for the live-confirmed TV
    (Grupo Televisa) case this recovers. Same "fallback-only, sum two real parts, never
    overwrite a real combined value" pattern as
    _fill_long_term_debt_from_noncurrent_current_split below. Discontinued defaults to 0
    when absent (most filers most years have none, and the taxonomy only requires a
    Discontinued tag when discontinued operations are real) rather than leaving the whole
    figure NULL for the common case of a filer that only ever tags the Continuing concept.

    Also falls diluted back into the basic-only "earnings_per_share_basic" key (downstream
    field_mapping's sole source for annual_income_statement.earnings_per_share - see
    load_financial_statements.py's _FIELD_MAPPING) when a filer tags no Basic-shaped EPS
    concept at all, TV's case: it tags only the Diluted split, never Basic in any form.
    Diluted is a close, honestly-approximate stand-in for Basic (differs only by the
    dilutive effect of options/convertibles) - the same "blended figure beats permanently
    NULL" judgment this file already makes for
    WeightedAverageNumberOfShareOutstandingBasicAndDiluted share-count filers. Only fires
    when a filer has no real Basic-shaped fact of its own; a filer reporting genuine Basic
    EPS keeps it untouched.
    """
    for row in rows:
        basic_cont = row.pop("earnings_per_share_basic_continuing", None)
        basic_disc = row.pop("earnings_per_share_basic_discontinued", None)
        if row.get("earnings_per_share_basic") is None and basic_cont is not None:
            row["earnings_per_share_basic"] = basic_cont + (basic_disc or 0)

        diluted_cont = row.pop("earnings_per_share_diluted_continuing", None)
        diluted_disc = row.pop("earnings_per_share_diluted_discontinued", None)
        if row.get("earnings_per_share_diluted") is None and diluted_cont is not None:
            row["earnings_per_share_diluted"] = diluted_cont + (diluted_disc or 0)

        if row.get("earnings_per_share_basic") is None and row.get("earnings_per_share_diluted") is not None:
            row["earnings_per_share_basic"] = row["earnings_per_share_diluted"]


def _fill_eps_shares_from_dual_class_dimensional_facts(
    rows: list[dict[str, Any]], client: Any, symbol: str, security_name: str | None = None
) -> None:
    """Last-resort fallback: recover EPS/weighted-average-share facts tagged only under a
    us-gaap:StatementClassOfStockAxis dimensional context, for symbols whose own share class
    is determinable either from a dot-suffix ticker (BRK.A/BRK.B, CRD.A/CRD.B, GTN.A, GEF.B,
    ...) or, for a bare ticker, from `security_name` stating the class explicitly (e.g. "Greif
    Inc. Class A Common Stock" for GEF) - see resolve_class_letter's docstring. `security_name`
    is optional and defaults to None (dot-suffix-only resolution) so this stays callable with
    no DB access; loaders/helpers/sec_base.py (which already does per-run bulk DB lookups like
    _get_reit_symbols) is the intended source when it's available.

    See loaders/helpers/sec_dual_class_eps.py's module docstring (Berkshire live-confirmed
    2026-09-02) for why no concept alias can ever close this gap - same root cause family as
    _fill_long_term_debt_from_segment_dimensional_facts above, different axis/concepts. Only
    fires for a fiscal year still missing ANY of the 4 target fields after every tier above;
    never overwrites a real value. Bounded to the most recent 3 missing fiscal years per
    symbol, same rationale as the debt fallback's identical cap (live scoring only reads the
    latest 1-2 annual rows; an unbounded scan of a symbol's full history risks the same
    zombie-thread/rate-limiter contention already found and fixed there).
    """
    from loaders.helpers.sec_dual_class_eps import extract_dual_class_eps_shares, resolve_class_letter
    from loaders.helpers.sec_segment_debt import find_10k_for_fiscal_year

    class_letter = resolve_class_letter(symbol, security_name)
    if class_letter is None:
        return

    target_fields = (
        "earnings_per_share_basic",
        "earnings_per_share_diluted",
        "weighted_average_number_of_shares_outstanding_basic",
        "weighted_average_number_of_diluted_shares_outstanding",
    )
    all_missing_years = [
        row["fiscal_year"] for row in rows if row.get("fiscal_year") and any(row.get(f) is None for f in target_fields)
    ]
    if not all_missing_years:
        return
    missing_years = sorted(set(all_missing_years), reverse=True)[:3]

    try:
        cik = client.symbol_to_cik(symbol)
        submissions = client.get_submissions(cik)
    except Exception:
        logger.debug(
            f"[DUAL_CLASS_EPS] {symbol}: could not fetch submissions for dual-class EPS fallback", exc_info=True
        )
        return

    field_map = {
        "eps_basic": "earnings_per_share_basic",
        "eps_diluted": "earnings_per_share_diluted",
        "shares_basic": "weighted_average_number_of_shares_outstanding_basic",
        "shares_diluted": "weighted_average_number_of_diluted_shares_outstanding",
    }

    for row in rows:
        if row.get("fiscal_year") not in missing_years or not any(row.get(f) is None for f in target_fields):
            continue
        located = find_10k_for_fiscal_year(submissions, int(row["fiscal_year"]))
        if located is None:
            continue
        accession, period_end = located
        try:
            xml_text = client.get_filing_xml(cik, accession, "10-K")
        except Exception:
            logger.debug(
                f"[DUAL_CLASS_EPS] {symbol} FY{row['fiscal_year']}: could not fetch instance XML "
                f"({accession}) for dual-class EPS fallback",
                exc_info=True,
            )
            continue
        result = extract_dual_class_eps_shares(xml_text, class_letter, period_end)
        if not result:
            continue
        filled = []
        for src_key, dest_key in field_map.items():
            if row.get(dest_key) is None and src_key in result:
                row[dest_key] = result[src_key]
                filled.append(dest_key)
        if filled:
            logger.info(
                f"[DUAL_CLASS_EPS] {symbol} FY{row['fiscal_year']}: recovered {filled} via class "
                f"'{class_letter}' StatementClassOfStockAxis dimensional match ({accession})"
            )


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


def _fill_income_tax_expense_from_current_deferred_split(rows: list[dict[str, Any]]) -> None:
    """Fallback-only: income_tax_expense = CurrentIncomeTaxExpenseBenefit +
    DeferredIncomeTaxExpenseBenefit.

    Only fires when the primary "income_tax_expense" column (from the plain
    "IncomeTaxExpenseBenefit" concept, fetched above) is still empty for that fiscal year -
    never overwrites a real value. Unlike the long_term_debt Noncurrent/Current split above,
    BOTH components must be present to fire (a filer with only one half tagged genuinely
    hasn't reported its total tax provision that way, unlike LongTermDebtCurrent's "0 if
    absent" convention - a missing current-or-deferred component is not safely assumed to be
    zero the way an untagged current-debt-maturity often genuinely is). Mutates rows in
    place and always strips both raw keys.
    """
    for row in rows:
        current = row.pop("current_income_tax_expense_benefit", None)
        deferred = row.pop("deferred_income_tax_expense_benefit", None)
        if row.get("income_tax_expense") is not None or current is None or deferred is None:
            continue
        row["income_tax_expense"] = current + deferred


def _fill_pretax_income_from_results_of_operations_when_validated(rows: list[dict[str, Any]]) -> None:
    """Fallback-only: pretax_income from "ResultsOfOperationsIncomeBeforeIncomeTaxes", but ONLY
    when it exactly matches the independently-known net_income + income_tax_expense identity
    for that same fiscal year.

    This concept is genuinely ambiguous per-filer - live-confirmed CNX Resources tags it as an
    ASC 932 oil-and-gas-producing-activities supplementary disclosure (NOT consolidated pretax
    income), while RRC (Range Resources, same SIC 1311 E&P classification) tags the identical
    concept name as its REAL consolidated pretax income. Rather than guessing which meaning a
    given filer uses, cross-validate the filer's OWN tagged value against its own already-known
    net_income/income_tax_expense for that year - only promote it when they agree exactly (both
    values, being independently-sourced real SEC facts, should match to the dollar when the
    concept really is consolidated pretax income; a supplementary sub-figure like CNX's won't).
    Never overwrites a real "pretax_income" value already resolved from the primary concepts
    above. Mutates rows in place and always strips the raw candidate key.
    """
    for row in rows:
        candidate = row.pop("results_of_operations_income_before_income_taxes", None)
        if row.get("pretax_income") is not None or candidate is None:
            continue
        net_income = row.get("net_income_loss")
        tax = row.get("income_tax_expense")
        if net_income is None or tax is None:
            continue
        if candidate == net_income + tax:
            row["pretax_income"] = candidate


def get_income_statement(
    client: Any, symbol: str, period: str = "annual", security_name: str | None = None
) -> list[dict[str, Any]]:
    """Aggregate income statement rows from key concepts.

    Args:
        client: SecEdgarClient instance
        symbol: Stock ticker
        period: "annual" or "quarterly"
        security_name: Optional stock_symbols.security_name, used only by the dual-class
            EPS/shares fallback (see _fill_eps_shares_from_dual_class_dimensional_facts) to
            resolve a bare-ticker dual-class symbol's own share class (e.g. "Greif Inc.
            Class A Common Stock" for GEF). Callers with no DB access can omit it - a
            dot-suffix ticker (BRK.A, CRD.B, ...) still resolves without it.

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
        # FIXED 2026-08-19 (goal: "no SEC data"/loader audit): equity REITs (AMH/American
        # Homes 4 Rent, EQR/Equity Residential live-confirmed via real companyfacts JSON)
        # adopted this ASC 842 (new lease standard, effective 2019) concept as their real
        # top-line lease-revenue tag - "Revenues" goes silent for these filers right around
        # the same 2019/2020 transition (AMH FY2020 "Revenues"=$1.1828B is its last real
        # entry) while OperatingLeaseLeaseIncome continues with real, growing figures for
        # years after (AMH FY2025=$1.850B, EQR FY2025=$3.094B). Same "revenue concept
        # silently re-tagged" bug class as the utility fixes above, REIT/lease-accounting
        # trigger this time. Deliberately NOT a plain always-fallback mapping here - REIT
        # revenue also includes non-lease fee income this concept excludes (AMH's own
        # overlap year is ~99% but not exactly equal to the old "Revenues" figure), so it's
        # wired as a REIT-only (SIC 6798) fallback in load_financial_statements.py's
        # _REIT_REVENUE_FALLBACK_ONLY_FIELDS instead - same precedent as that set's existing
        # RevenueFromContractWithCustomer entries, and it only ever fills an already-empty
        # revenue rather than risking a clobber for a non-REIT filer that happens to tag it.
        "OperatingLeaseLeaseIncome",
        # ADDED 2026-09-01 (recovered from the growth-multi-input-blend worktree, found
        # stranded off main): older-era (pre-ASC 842, largely pre-2016) equity REITs used
        # this concept as their real estate rental revenue total before
        # "OperatingLeaseLeaseIncome" existed as a tag at all. Live-confirmed via ARE
        # (Alexandria Real Estate Equities, a real office/lab REIT, SIC 6798): FY2010 real
        # "RealEstateRevenueNet"=$487,303,000 (later restated $460,621,000, both plausible
        # for ARE's real historical scale) - no "Revenues"/"OperatingLeaseLeaseIncome"/
        # ASC-606 concept exists for this filer at all for that era, so revenue fell back
        # all the way to a genuinely unrelated, minor `InterestIncomeOperating` fact
        # ($800,000) - a ~600x understatement with no data_unavailable/reason flag anywhere.
        # Same REIT-exclusive wiring as OperatingLeaseLeaseIncome (see
        # load_financial_statements.py's _REIT_EXCLUSIVE_FIELDS) - a non-REIT filer tagging
        # real-estate rental revenue at all is implausible, so this never touches "revenue"
        # outside a confirmed REIT.
        "RealEstateRevenueNet",
        # FIXED 2026-08-01: RevenuesNetOfInterestExpense for financial services companies.
        # Banks (MS, WFC, etc.) switched from reporting "Revenues" (2007-2019) to
        # "RevenuesNetOfInterestExpense" (2013+) as their primary revenue metric in 2020+.
        # This concept has full 2020+ coverage for financial services while legacy
        # "Revenues" concept stops updating for banks after 2019. Must be listed BEFORE
        # SalesRevenueNet/legacy Revenues so they don't overwrite with zero values.
        # Live-verified: MS has 2020-2026 data, WFC has 2018-2026 data.
        "RevenuesNetOfInterestExpense",
        # FIXED 2026-08-19 (goal: "no SEC data"/loader audit): regulated electric/gas
        # utilities (XEL/Xcel Energy, DTE/DTE Energy, OGS/ONE Gas live-confirmed via real
        # companyfacts JSON) switched their primary revenue tag to this utility-specific
        # concept - "Revenues"/"RevenueFromContractWithCustomerExcludingAssessedTax" both
        # stop updating for these filers around FY2018/2019 (ASC 606 adoption era) even
        # though the company keeps filing real 10-Ks every year after. Confirmed via
        # matching overlap-year values: XEL FY2017/2018 = $11.404B/$11.537B under BOTH the
        # old "Revenues" tag and this one, exactly - then this concept alone continues with
        # real, growing figures through FY2025 ($14.669B) while "Revenues" goes silent.
        # This is the SAME "revenue concept silently re-tagged, freezing every downstream
        # quality/growth metric behind a stale multi-year-old anchor" bug class as the
        # AEG/UBS IFRS fixes (see f6baac459/a46b6378b) - just a us-gaap utility-sector
        # trigger (ASC 606) instead of an IFRS-transition or M&A-driven one. Listed as a
        # normal (always-processed, not fallback-only) concept per this list's usual
        # convention: it's a combined "regulated AND unregulated" total by name/design, not
        # a partial segment figure, so it's safe to let it win on overwrite like any other
        # top-line revenue tag.
        # FIXED 2026-08-19 (same session, same root cause as the concept below): pure
        # single-segment regulated utilities with no unregulated business line (OGS/ONE
        # Gas, a natural-gas-only distributor - live-confirmed via real companyfacts JSON)
        # use this narrower tag instead - RegulatedAndUnregulatedOperatingRevenue doesn't
        # exist at all for OGS. Values match "Revenues" exactly for the FY2018-2022 overlap
        # years ($1.634B/$2.578B), then continue real and current through FY2025 ($2.427B)
        # after "Revenues" goes silent starting FY2023. Listed BEFORE the broader
        # And-Unregulated variant (last-listed-wins convention) so a filer that somehow
        # tags both (unseen so far, but plausible for a utility transitioning between a
        # regulated-only and combined segment split across years) keeps the more complete
        # combined figure, not this narrower one.
        "RegulatedOperatingRevenue",
        "RegulatedAndUnregulatedOperatingRevenue",
        # FIXED 2026-08-03: community banks/thrifts (FNWB, AMAL, OCFC live-confirmed via real
        # companyfacts JSON) have neither the concepts above nor RevenuesNetOfInterestExpense
        # (that one's for larger banks).
        #
        # ORDERING FIXED 2026-08-22 (goal session: real-money-readiness audit, live-confirmed
        # via AMTB): this concept and InterestIncomeOperating (just below) used to be ordered
        # the other way around, on the assumption that this file's normal "last-listed-wins"
        # overwrite convention applied - true when that 2026-08-03 comment was written, but
        # both concepts became fallback-only (skip if "revenue" already populated, never
        # overwrite - see load_financial_statements.py's _REVENUE_FALLBACK_ONLY_FIELDS) in a
        # separate 2026-08-09 fix that nobody cross-checked against this ordering comment.
        # Under fallback-only semantics, "last-listed" no longer means "wins" - it means
        # "processed last, so it only gets `revenue` if the earlier one left it empty" -
        # exactly inverting the intended priority for any filer reporting both concepts.
        # Live-confirmed via AMTB (a bank holding company, SIC 6022): FY2022
        # InterestIncomeOperating=$200,000 (a minor, incidental line) vs.
        # InterestAndDividendIncomeOperating=$338,776,000 (the real, complete total,
        # consistent with AMTB's real net_income that year) - the $200,000 figure was winning
        # and being stored as "revenue", a ~1,694x understatement. This concept now listed
        # first so it gets first claim under fallback-only "first written wins" semantics,
        # restoring the priority the 2026-08-03 comment always intended.
        "InterestAndDividendIncomeOperating",
        # FIXED 2026-08-03: mortgage REITs (AGNC, NLY live-confirmed via real companyfacts
        # JSON) have none of the revenue concepts above - their primary revenue-equivalent
        # line is gross interest income (before subtracting interest expense on their own
        # borrowings). Deliberately did NOT use InterestIncomeExpenseNet (interest income
        # MINUS interest expense) for this - live-confirmed it goes NEGATIVE in real years
        # (AGNC FY2023: -246M) unlike a normal top-line revenue figure, which would distort
        # downstream margin/ratio calculations that assume revenue >= 0.
        # InterestIncomeOperating (gross, always positive in both AGNC's and NLY's real data)
        # is the correct analog instead. Listed after InterestAndDividendIncomeOperating (see
        # that concept's own comment above for why) so it only wins under fallback-only
        # semantics for filers with nothing more complete.
        "InterestIncomeOperating",
        # FIXED 2026-08-22 (goal session: real-money-readiness audit, "Insufficient
        # history" bucket sample): a small number of community banks (AROW/Arrow
        # Financial Corp live-confirmed via real companyfacts JSON) tag neither
        # "InterestAndDividendIncomeOperating" nor any other concept above at all -
        # their combined interest+dividend income total lives under this differently-
        # named concept instead. Live-verified AROW FY2015: InvestmentIncomeInterest
        # AndDividend=$70,738,000 exactly equals the sum of AROW's itemized interest
        # lines that year (InterestAndFeeIncomeLoansAndLeases $56,856,000 +
        # InterestIncomeSecuritiesTaxable $8,043,000 + InterestIncomeSecuritiesTaxExempt
        # $5,745,000 + InterestIncomeDomesticDeposits $94,000 = $70,738,000) - a real,
        # correct total, not a partial line item. AROW had 13 straight years (2009-2021)
        # of real, growing NetIncomeLoss but NULL revenue before this fix. Listed last
        # in this revenue group (after InterestAndDividendIncomeOperating) so it only
        # wins on overwrite for filers with nothing else, same convention as that
        # concept's own comment above. NOTE: this does NOT generalize to every small
        # bank with a revenue gap - live-checked BANR/CLBK/LSBK/PNFP (same "Insufficient
        # history" sample) have none of the concepts in this list at all, only a filer-
        # specific mix of itemized interest sub-line concepts with no single combined
        # tag - that's a structurally different, harder problem (would need a per-filer-
        # verified summation, not a single concept alias) and is NOT fixed here.
        "InvestmentIncomeInterestAndDividend",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
        # no_recent_revenue_symbols investigation): BDCs (business development companies,
        # regulated as closed-end investment companies) report neither any concept above
        # nor a standard revenue tag - their top-line revenue-equivalent is total gross
        # investment income before fund-level operating expenses. Live-confirmed via real
        # SEC companyfacts JSON: CSWC (Capital Southwest) FY2026 (period ended 2026-03-31)
        # $232,105,000, PFLT (PennantPark Floating Rate Capital) FY2025 $261,427,000, ICMB
        # (Investcorp Credit Management BDC) FY2025 $17,396,235 - all real, current,
        # growing figures with zero "Revenues"/other-fallback concepts anywhere in their
        # filing history. Deliberately NOT "NetInvestmentIncome" (AFTER fund operating
        # expenses are deducted - CSWC FY2026 $136,588,000 vs. this gross figure's
        # $232,105,000, ~59% of gross, confirming real expenses are being netted out,
        # not a duplicate tag) - same "gross, not net" top-line convention as
        # InterestIncomeOperating's mortgage-REIT fix above. Listed last in this revenue
        # group (fallback-only, see load_financial_statements.py's
        # _REVENUE_FALLBACK_ONLY_FIELDS) so it only wins for filers with nothing else.
        "GrossInvestmentIncomeOperating",
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
        # FIXED 2026-08-31 (goal session: "get all the data we need" full-coverage audit):
        # industrial/materials filers that break out D&A as its own income-statement line
        # (rather than folding it into cost of sales) tag this DD&A-excluded COGS variant
        # instead of any concept above - live-confirmed via Linde plc (LIN, $230B market
        # cap): zero data under CostOfRevenue/CostOfSales/CostOfGoodsAndServicesSold for
        # any fiscal year, but real, plausible COGS on file here (FY2025 $17.39B against
        # $33.99B revenue, ~51% - a normal industrial-gas cost ratio) under
        # CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization (LIN's
        # concept name pre-2023 was the older "GoodsSold" singular variant below - same
        # figure, same filer, just renamed). `gross_profitability`/`cost_of_revenue` had
        # been silently NULL for LIN this whole time despite 40,000+ real income-statement
        # data on file. Same target column ("cost_of_revenue") as every other concept in
        # this group; kept fallback-only (see load_financial_statements.py's
        # _REVENUE_FALLBACK_ONLY_FIELDS) since it deliberately excludes D&A and so is a
        # narrower/less-comparable figure than a full COGS-including-D&A tag when a filer
        # reports both.
        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
        "CostOfGoodsSoldExcludingDepreciationDepletionAndAmortization",
        # FIXED 2026-08-31 (goal session, same sweep as the DD&A-excluded COGS fix above):
        # live-events/venue-based filers tag their pass-through artist/venue/ticketing costs
        # under this concept instead of any concept above - live-confirmed Live Nation
        # Entertainment (LYV, $23B market cap): zero data under every concept above for any
        # recent fiscal year, but real, current, plausible DirectOperatingCosts on file every
        # year through FY2025 (FY2023 $17.29B/$22.75B revenue ~76%, FY2024 $17.33B/$23.16B
        # ~75% - consistent with Live Nation's well-known low-margin, pass-through-heavy
        # concert-promotion economics). gross_profitability/gross_margin had been silently
        # NULL (mislabeled "reit_special_entity", this codebase's generic "no cost concept
        # found" label - see load_value_quality_growth_metrics.py) despite decades of
        # otherwise-complete real SEC data on file. Same target column, fallback-only (see
        # _REVENUE_FALLBACK_ONLY_FIELDS) since this is a narrower, business-model-specific
        # cost measure rather than a universal COGS tag.
        "DirectOperatingCosts",
        # FIXED 2026-08-31 (same sweep): regulated water utilities tag their direct
        # utility-operations cost under this utility-specific concept - live-confirmed AWK
        # ($1.72B/$4.22B revenue FY2023 ~41%), WTRG, MSEX ($91.3M/$194.7M ~47%), and YORW
        # ($20.8M/$77.0M ~27%) all have real, current, plausible data every year; CWT/SJW/
        # ARTNA checked and confirmed to NOT use this concept (different taxonomy choice,
        # not fixed by this). Electric utilities (NEE, live-verified) tag ZERO cost-of-X
        # concepts of any kind and are unaffected either way. Fallback-only for the same
        # narrower-measure reason as DirectOperatingCosts above - excludes D&A/interest/taxes
        # that a full cost-of-revenue figure might otherwise include.
        "UtilitiesOperatingExpenseMaintenanceAndOperations",
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
        # ADDED 2026-08-27 (goal: close the R&D intensity/Mohanram G-Score literature-checklist
        # gap - see MEMORY.md growth_missing_metrics_swept_20260827, which had incorrectly
        # marked these permanently blocked on "no research_development column exists anywhere").
        # Live-verified via real SEC companyfacts JSON (AAPL/MSFT/NVDA, 51 annual entries each,
        # values matching known public R&D figures) that this standard concept is present and
        # populated all along - just never extracted. Narrower "ExcludingAcquiredInProcessCost"
        # variant (some biotech/pharma filers separate out acquired in-process R&D write-offs)
        # listed first so the broader standard tag wins on overwrite for filers reporting both,
        # same last-listed-wins convention as every other concept in this list. Both map to the
        # same "research_development_expense" target column (see load_financial_statements.py's
        # _INCOME_FIELD_MAPPING). Naturally sparse/NULL for non-R&D sectors (banks, REITs,
        # utilities) - expected and correct, same as capex is NULL for many financials today,
        # not a bug to chase.
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        "ResearchAndDevelopmentExpense",
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
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
        # interest_expense_not_itemized investigation): JKHY (Jack Henry & Associates)
        # stopped tagging plain "InterestExpense" after its FY2023 10-K - live-confirmed
        # via real companyfacts JSON that both concepts report the IDENTICAL value for
        # the same fiscal year (FY2023, period 2022-07-01 to 2023-06-30: $15,073,000
        # under either concept), then this concept continues alone with real values
        # through FY2026 ($16,384,000/$10,438,000/$5,387,000 for FY2024-2026) - a pure
        # taxonomy relabeling, not a different/narrower figure. Plain (non-fallback)
        # concept, same convention as the PaymentsForProceedsFromProductiveAssets/D capex
        # fix (identical-value-on-overlap pattern).
        "InterestExpenseOperating",
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
        # FIXED 2026-09-03 (same sweep): EPAC (Enerpac Tool Group) has tagged real,
        # continuous, non-zero interest expense under this concept for its ENTIRE filing
        # history (FY2009-2025, e.g. FY2025 $9,911,000) - live-confirmed via real
        # companyfacts JSON EPAC has no fact under "InterestExpense" at all, and its rare
        # "InterestAndDebtExpense" entries are mostly $0 except one real but SMALLER
        # FY2012 value ($16,830,000 vs. this concept's $29,561,000 the same year) -
        # a genuinely different, smaller line item, not a duplicate/relabeling. Fallback-
        # only (see load_financial_statements.py's field_mapping) so it only fills years
        # where InterestAndDebtExpense didn't already report EPAC's (rare) real value.
        "FinancingInterestExpense",
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
        # FIXED 2026-09-03 (same sweep, same reasoning as InterestPaidNet just above): ARW
        # (Arrow Electronics, $37B revenue) tags NEITHER InterestPaidNet nor any
        # InterestExpense* concept above - live-confirmed via real companyfacts JSON its
        # only interest-on-debt fact anywhere is plain "InterestPaid" (FY2021 $113.1M,
        # FY2022 $175.6M, FY2023 $274.1M - a real, growing, plausible figure for a large
        # distributor with real debt). Same "cash paid, not accrued expense" imprecision as
        # InterestPaidNet, so kept at the same lowest-priority fallback tier, listed right
        # after it so any filer with the more complete "Net" variant keeps that value
        # instead.
        "InterestPaid",
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
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
        # ebitda_not_extracted investigation): several large, well-known filers (PG, WM,
        # ULTA, WSM, CP live-confirmed via real companyfacts JSON) stopped tagging plain
        # "DepreciationAndAmortization" and switched to this combined depreciation +
        # depletion + amortization concept instead - PG FY2026 $3,160,000,000, WM FY2025
        # $2,863,000,000, ULTA FY2025 (period ended 2026-01-31) $300,772,000, all real,
        # current, growing figures with zero data under the concept above for recent
        # years. Same target column ("amortization_expense") as DepreciationAndAmortization
        # above per this file's "last-listed wins" convention - not a new column, matching
        # that concept's existing "combined D&A total, not a separate depreciation-only
        # figure" semantics.
        "DepreciationDepletionAndAmortization",
        "AmortizationOfIntangibles",
        # For roic_pct (quality_metrics) = EBIT*(1-effective_tax_rate)/invested_capital.
        # Live-confirmed against AAPL/MSFT companyfacts (2026-08-03): both real GAAP
        # concepts, not guessed. IncomeTaxExpenseBenefit is the real tax provision (was
        # previously deliberately left unfetched - a hardcoded 25% tax-rate assumption
        # was correctly rejected as synthetic data, see load_value_quality_growth_metrics.py's
        # prior "CRITICAL FIX" comment - this replaces that gap with the real reported figure).
        "IncomeTaxExpenseBenefit",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
        # income_tax_expense investigation): CNS (Cohen & Steers) stopped tagging plain
        # "IncomeTaxExpenseBenefit" after FY2024 (last real fact 2024-12-31, $46,749,000) -
        # live-confirmed via real companyfacts JSON that FY2025 instead splits the same
        # total across "CurrentIncomeTaxExpenseBenefit" ($46,671,000) +
        # "DeferredIncomeTaxExpenseBenefit" ($561,000) = $47,232,000, consistent with
        # FY2024's total and each individually a completely standard ASC 740 tax-note
        # concept (not a guess or reconstruction - current + deferred tax provision sums
        # to total tax expense by definition). Not fetched via field_mapping directly -
        # _fill_income_tax_expense_from_current_deferred_split() below sums both into
        # "income_tax_expense" as a post-processing step (same "genuinely different
        # aggregation than last-value-wins" pattern as
        # _fill_long_term_debt_from_noncurrent_current_split above) and pops both raw
        # keys, so this fallback only fires when the plain concept above is absent for
        # that fiscal year - never overwrites a real value.
        "CurrentIncomeTaxExpenseBenefit",
        "DeferredIncomeTaxExpenseBenefit",
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
        # FIXED 2026-09-03 (goal session: "Missing SEC/XBRL data" reduction, pretax_income
        # investigation): the comment above rejected "ResultsOfOperationsIncomeBeforeIncomeTaxes"
        # wholesale after finding it's CNX's ASC 932 oil-and-gas-producing-activities
        # supplementary disclosure, not consolidated pretax income - true for CNX, but NOT
        # universal. Live-confirmed RRC (Range Resources, also SIC 1311 E&P) tags this SAME
        # concept as its REAL consolidated pretax income: FY2020/2021/2022 values
        # (-$737,329,000 / $402,035,000 / $1,413,830,000) match net_income + income_tax_expense
        # to the exact dollar in all 3 years. Since this concept is genuinely ambiguous
        # per-filer (sometimes the real total, sometimes a supplementary sub-figure), it is
        # deliberately NOT mapped to "pretax_income" via field_mapping here (which would apply
        # it blindly, unlike every concept above) - instead kept under its own raw key and only
        # promoted by _fill_pretax_income_from_results_of_operations_when_validated() below,
        # which requires an exact match against the already-known net_income+income_tax_expense
        # identity before trusting it for that specific fiscal year. This is NOT the blanket
        # "pretax_income = net_income + income_tax_expense" reconstruction already investigated
        # and rejected as a scoring-layer fallback (~75% accurate universe-wide, see MEMORY.md's
        # pretax_income_derivation_rejected) - it only ever uses the filer's OWN real tagged
        # value, and only when independently corroborated, never a computed number.
        "ResultsOfOperationsIncomeBeforeIncomeTaxes",
    ]
    rows = _aggregate_concepts(
        client, symbol, concepts, period, ifrs_aliases=_INCOME_IFRS_ALIASES, dei_aliases=_INCOME_DEI_ALIASES
    )
    _fill_earnings_per_share_from_continuing_discontinued_split(rows)
    _fill_income_tax_expense_from_current_deferred_split(rows)
    _fill_pretax_income_from_results_of_operations_when_validated(rows)
    if period == "annual":
        _fill_eps_shares_from_dual_class_dimensional_facts(rows, client, symbol, security_name)
    return rows


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
        # FIXED 2026-08-19 (goal: "no SEC data"/loader audit): filers that report
        # discontinued operations (divestitures, spinoffs - a common occurrence, not rare)
        # tag operating cash flow under this narrower "continuing operations only" concept
        # instead of - or, more often, ALSO instead of any year where the plain concept
        # below goes untagged. Live-confirmed via ASH (Ashland, a normal specialty-
        # chemicals 10-K filer): companyfacts JSON has ZERO entries under plain
        # "NetCashProvidedByUsedInOperatingActivities" for ANY fiscal year, but real,
        # plausible-scale figures ($134M-$703M) under this concept for every FY2014-2025 -
        # operating_cash_flow (and everything derived from it: free_cash_flow,
        # fcf_to_net_income, fcf_yield, intrinsic_value, margin_of_safety) was NULL for
        # this filer's entire history, marked the generic "incomplete_sec_filing_cashflow"
        # (the whole row - required_metrics only accepts operating_cash_flow - discarded
        # even though investing/financing/capex data was real and present). Listed BEFORE
        # the plain concept (this file's "last-listed wins on overwrite" convention) AND
        # marked fallback-only in load_financial_statements.py's field_mapping
        # (_OCF_FALLBACK_ONLY_FIELDS) - APD/ANGI (live-confirmed) report BOTH concepts for
        # the same fiscal year, where the plain tag is the fuller total (continuing +
        # discontinued) and must keep winning whenever it's actually present.
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
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
        # FIXED 2026-08-24 (goal: "Margin of Safety (DCF) / Cash flow data unavailable"
        # audit): REITs (SIC 6798) never tag any of the PP&E-family concepts above - their
        # capex is real property investment, tagged under a completely different concept
        # family. Live-confirmed via real companyfacts JSON: AAT (American Assets Trust)
        # tags "PaymentsForCapitalImprovements" ($70.2M FY2024, $108.0M for AHT/Ashford
        # Hospitality Trust same concept same year); AHR (American Healthcare REIT) and ABR
        # (Arbor Realty Trust, a commercial mortgage REIT that still holds some real estate)
        # tag "PaymentsToAcquireRealEstate"/"PaymentsToAcquireAndDevelopRealEstate" ($60.4M/
        # $3.47M respectively). None of these filers report under any PP&E-family concept at
        # all - this was a genuine unextracted-data gap, not a structural absence, for 134
        # SIC-6798 symbols found with intrinsic_value_unavailable_reason=
        # 'missing_cash_flow_data'. Excluded "PaymentsToAcquireCommercialRealEstate" at the
        # time (AAT tags it too, but at $0 the one year checked - and
        # "PaymentsToAcquireBusinesses*" M&A-style concepts stay excluded here same as for
        # industrials above) pending separate verification - see that concept's own entry
        # below (added 2026-09-02) for the live verification that resolved the pending
        # exclusion. Pure agency-mortgage REITs with no real estate at all (e.g. AGNC, which
        # only tags MBS-purchase concepts) will still correctly end up with capex=None after
        # this - a real structural gap for that subclass, not fixed here.
        "PaymentsToAcquireAndDevelopRealEstate",
        "PaymentsToAcquireRealEstate",
        "PaymentsForCapitalImprovements",
        # FIXED 2026-09-02 (goal session: "missing SEC/XBRL data" audit, live SEC EDGAR
        # verification of the 2026-08-24 fix's "pending separate verification" exclusion
        # above). Live-confirmed via SL Green's (SLG, CIK 1040971) real companyfacts JSON:
        # SLG re-tagged its real-estate-acquisition capex under THIS concept starting with
        # its FY2020 10-K (accn 0001040971-21-000007) - its last "PaymentsToAcquireRealEstate"
        # entry is FY2019 ($262,591,000), and "PaymentsToAcquireCommercialRealEstate"'s
        # FY2019 entry carries the IDENTICAL value ($262,591,000, filed same accession) -
        # a straight relabel, not a new/different line item. Continues with real, varied,
        # non-placeholder annual values every year since: FY2020 $86.846M, FY2021 $152.791M,
        # FY2022 $64.491M, FY2023 $0 (genuine - no acquisitions that year, matches slow
        # 2023 commercial real estate market), FY2024 $0, FY2025 $271.649M (accn
        # 0001628280-26-008669) - real economic zeros mixed with real nonzero years, not a
        # placeholder/broken tag. The 2026-08-24 exclusion cited AAT tagging this same
        # concept at $0 "the one year checked" as grounds for suspicion; SLG's 8-year,
        # clearly-varying history (including genuine zeros) shows a single $0 observation
        # is not itself evidence of unreliability - REITs legitimately have zero-acquisition
        # years. DLR (Digital Realty) and REG (Regency Centers), by contrast, do NOT tag
        # this concept at all and have no other candidate concept in their real companyfacts
        # JSON for capex after ~2019/2021 either (checked live, all remaining PP&E/
        # RealEstate/Capital/Construction-family concepts scanned) - a genuine SEC/XBRL
        # granularity gap for those two specifically, correctly left as missing_sec_data,
        # not something this concept addition can fix.
        "PaymentsToAcquireCommercialRealEstate",
        # FIXED 2026-08-24 (same audit, insurance-sector continuation): insurers (SIC
        # 6311/6321/6331/6351/6361/6399) hold investment real estate as part of their
        # portfolio, tagged under these two insurer-specific concepts rather than any
        # PP&E-family or REIT concept above. Live-confirmed via real companyfacts JSON:
        # MET (MetLife) $633M FY2025, RGA (Reinsurance Group of America) $1.073B FY2025,
        # and BHF (Brighthouse Financial) under
        # "PaymentsToAcquireRealEstateAndRealEstateJointVentures"; PFG (Principal
        # Financial) $135.5M FY2025, TRV (Travelers) $48M FY2025, and WRB (W.R. Berkley)
        # under "PaymentsToAcquireRealEstateHeldForInvestment". Confirmed a genuinely
        # heterogeneous sector, not a blanket structural gap like depository institutions -
        # ALL (Allstate) and HIG (Hartford) already report standard
        # "PaymentsToAcquirePropertyPlantAndEquipment" ($267M/$215M FY2023) and were
        # already correctly extracted before this fix, so no SIC-wide capex=0 coercion is
        # applied for this sector (see SecValuationsLoader.DEPOSITORY_INSTITUTION_SIC_CODES'
        # comment for why that coercion is bank-specific only).
        "PaymentsToAcquireRealEstateAndRealEstateJointVentures",
        "PaymentsToAcquireRealEstateHeldForInvestment",
        # FIXED 2026-08-29 (goal: "full data" audit continuation, oil & gas E&P sector):
        # exploration & production filers (SIC 1311 "Crude Petroleum & Natural Gas" and
        # related codes) tag capex under sector-specific concept families instead of any
        # PP&E-family concept above - none of the 43 SIC-1311 symbols checked with
        # unexplained-NULL capex report under "PaymentsToAcquirePropertyPlantAndEquipment"
        # at all for recent fiscal years. Live-confirmed via real companyfacts JSON across
        # 7 filers: APA (Apache/APA Corp) $2.740B FY2025, AR (Antero Resources) $685.5M
        # FY2025, CHRD (Chord Energy) $1.348B FY2025, CRGY (Crescent Energy) $951.0M
        # FY2025, AMPY (Amplify Energy) $84.3M FY2025 all tag
        # "PaymentsToExploreAndDevelopOilAndGasProperties" - the standard cash-flow-
        # statement E&D capex line for this sector. CRGY separately also tags
        # "PaymentsToAcquireOilAndGasProperty" $818.9M FY2025 for its acquisition-specific
        # spend (a genuinely distinct investing-activity line, not a duplicate of the E&D
        # figure - _aggregate_concepts has no summing mechanism, so whichever of the two is
        # listed last here wins and CRGY's true total capex is understated by the other
        # line's amount; still a strict improvement over NULL). EGY (small-cap, no current
        # E&D tag) reports only "PaymentsToAcquireOilAndGasProperty" $103.0M FY2024.
        # DVN (Devon Energy) reports NEITHER "Payments"-prefixed concept for any fiscal
        # year since 2019 (last used generic PP&E) - its only current capex-equivalent
        # figure is "CostsIncurredOilAndGasPropertyAcquisitionExplorationAndDevelopment
        # Activities" $4.000B FY2025, the standard ASC 932 full-cost/successful-efforts
        # supplemental "costs incurred" disclosure (an accrual-basis total industry
        # analysts commonly use as an E&P capex proxy when no cash-flow-statement tag
        # exists, but not a strict cash-paid figure - may include non-cash items like
        # asset-retirement-obligation accretion). Listed first (least-preferred position,
        # same "last-listed wins" convention as this file's other fallback groups) so the
        # more precise Payments-based concepts below win whenever a filer reports both.
        "CostsIncurredOilAndGasPropertyAcquisitionExplorationAndDevelopmentActivities",
        "PaymentsToAcquireOilAndGasProperty",
        "PaymentsToExploreAndDevelopOilAndGasProperties",
        # FIXED 2026-08-29 (same audit, follow-up after the sec_base.py capex retry-gap fix
        # let already-stored SIC-1311 rows actually be re-checked): MGY (Magnolia Oil & Gas)
        # and GTE (Gran Tierra Energy) tag neither concept above at all for recent fiscal
        # years - live-confirmed via real companyfacts JSON: MGY reports
        # "PaymentsToAcquireOilAndGasPropertyAndEquipment" $469.5M FY2025 (its
        # "PaymentsToExploreAndDevelopOilAndGasProperties" tag exists but is stale, last
        # used FY2018), GTE the same concept $275.9M FY2025 (tags neither of the other two
        # oil & gas concepts at all). A distinct XBRL element from "...OilAndGasProperty"
        # above (note the "AndEquipment" suffix) - not a duplicate/typo, both are real,
        # separately-defined us-gaap concepts. Listed last (highest priority) since it was
        # the only concept with real current data for both filers checked.
        "PaymentsToAcquireOilAndGasPropertyAndEquipment",
        # FIXED 2026-09-03 (goal session: "get missing SEC/XBRL data under 7k" sweep,
        # capex_never_tagged_in_recent_filings investigation): water utilities (SIC 4941)
        # tag capex under this sector-specific concept instead of any PP&E-family concept
        # above - live-confirmed via CWT (California Water Service Group, CIK 1035201)
        # real companyfacts JSON: FY2025 $516,991,000 / FY2024 $470,800,000 / FY2023
        # $383,747,000, all full-year 10-K entries, growing year over year (plausible for
        # a capital-intensive regulated utility, not a placeholder). CWT tags zero
        # PP&E-family concepts anywhere in its companyfacts JSON - a genuine unextracted-
        # data gap, not a structural absence, same bug class as the REIT/insurance/oil-gas
        # sector capex fixes above. 13 SIC-4941 symbols in the universe (YORW, HTO, MSEX,
        # CWCO, CWT, SBS, ARTNA, AWK, AWR, CDZI, GWRS, PCYO, WTRG) - only CWT verified live
        # this session, but the concept is standard (not filer-specific), so this should
        # recover the whole sector wherever it applies.
        "PaymentsToAcquireWaterAndWasteWaterSystems",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
        # capex_never_tagged_in_recent_filings continuation): D (Dominion Energy, CIK
        # 715957) stopped tagging "PaymentsToAcquirePropertyPlantAndEquipment" after its
        # FY2019 10-K - live-confirmed via real companyfacts JSON that this concept's
        # values for FY2015-2019 (e.g. FY2017 $5,909,000,000, FY2016 $6,125,000,000)
        # exactly match this concept's values for the SAME fiscal years (both tagged in
        # parallel during the transition), then this concept continues alone with real,
        # growing values through FY2025 ($6,331M/$6,061M/$7,758M/$10,235M/$12,427M/
        # $12,653M for FY2020-2025) while the old concept goes silent - a pure taxonomy
        # relabeling of the identical real capex line, not a different/narrower figure.
        # Plain (non-fallback) concept, same convention as
        # PaymentsToAcquireWaterAndWasteWaterSystems above - safe because the two
        # concepts are value-identical in every year both are present.
        "PaymentsForProceedsFromProductiveAssets",
        # FIXED 2026-09-03 (same sweep): ED (Consolidated Edison, CIK 1047862) stopped
        # tagging "PaymentsToAcquirePropertyPlantAndEquipment" after its FY2022 10-K -
        # live-confirmed via real companyfacts JSON that this concept continues with real
        # values through FY2025 ($4,353M/$4,770M/$4,764M for FY2023-2025). Unlike the
        # PaymentsForProceedsFromProductiveAssets/D case above, this is NOT a pure
        # relabeling: ED tags this concept continuously back to FY2009 IN PARALLEL with
        # the standard concept, and the two report genuinely DIFFERENT values in years
        # both are present (FY2020: $3,326M this concept vs. $4,085M standard concept) -
        # a narrower "construction work in progress" sub-line, not the full capex total.
        # Fallback-only (see load_financial_statements.py's field_mapping comment) so it
        # only fills FY2023+ (where the standard concept is genuinely absent) and never
        # overwrites the standard concept's more complete figure in years both exist.
        "PaymentsForConstructionInProcess",
        # RESTORED 2026-08-29 (worktree growth-multi-input-blend reconciliation): main's commit
        # 3152939f7 (SIC 700/7200 mapping fix) accidentally dropped these 3 lines - a
        # concurrent-editing collision, not an intentional removal (its own commit message never
        # mentions oil & gas capex). test_oil_gas_capex_concepts_fixed_20260829.py was silently
        # failing on main's own tip because of this. See MEMORY.md's recurring
        # concurrent-session-revert-race pattern for the bug class.
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
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
        # stock_based_compensation generic-gap investigation): CVX (Chevron, CIK
        # 0000093410) never tags "ShareBasedCompensation" or
        # "AllocatedShareBasedCompensationExpense" at all - live-confirmed real, continuous,
        # plausible-magnitude values under this legacy-named concept instead every year
        # FY2008-2025 ($168M FY2008 declining to $60-90M range FY2021-2025, consistent
        # with a large, mature filer's real non-cash stock comp scale). Semantically
        # narrower-sounding ("option plan") than the standard concepts but functions as
        # Chevron's actual full SBC add-back line, same "closest real proxy this filer
        # reports" precedent as this file's other legacy-naming fallbacks. Listed even
        # more fallback than AllocatedShareBasedCompensationExpense (least-preferred
        # position) and marked fallback-only in load_financial_statements.py's
        # field_mapping (_SBC_BUYBACK_FALLBACK_ONLY_FIELDS) so a filer reporting either
        # standard concept always keeps that value.
        "StockOptionPlanExpense",
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
    # See the "implausible fiscal_year" sanity-bound comment further below (BUG FOUND
    # 2026-08-19). SEC XBRL history starts ~2009; 1990 is a deliberately generous floor
    # so it never rejects a real fiscal year, only Excel-serial-style corruption
    # (43465, 43830, ...) or a stray "0". +1 allows a company whose fiscal year hasn't
    # calendar-ended yet to still file forward-looking amendments without tripping this.
    _max_plausible_fiscal_year = datetime.date.today().year + 1

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
            # ADDED 2026-09-02 (goal session: "missing SEC/XBRL data" audit, WEC live-
            # confirmed): the has_annual_report_form gate below (2026-08-18 GM/DIS fix)
            # blanket-skips every non-10-K-form instant fact once a concept has ANY real
            # 10-K history, on the assumption a 10-Q-sourced instant fact is always a
            # premature mid-year snapshot for a not-yet-filed fiscal year. That's true for
            # the CURRENT in-progress year (the case it was built for) but wrongly also
            # drops a PAST fiscal year-end that a filer's own 10-K genuinely never tagged
            # this exact concept for - live-confirmed via WEC's real companyfacts JSON:
            # StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest has
            # 10-K-form entries for FY2019-2025 but NONE for FY2018 (WEC's real FY2018
            # 10-K apparently didn't tag this concept at all that year), while three
            # FY2019 10-Qs each cite the real FY2018-end comparative value ($9.8427B,
            # end=2018-12-31) - the ONLY source for that fiscal year, silently dropped by
            # the blanket rule, leaving annual_balance_sheet.stockholders_equity NULL for
            # FY2018 despite total_assets/current_liabilities/etc. all being populated
            # (211 symbols / 1,144 rows share this "data_unavailable=FALSE but core field
            # NULL" shape live). Track the latest end date this concept's own confirmed
            # 10-K/20-F/40-F history actually reaches - only a fact BEYOND that boundary
            # is a genuine premature snapshot; one at or before it is a legitimate past
            # fiscal year-end the annual filing itself just never re-tagged.
            _max_annual_report_end = max(
                (
                    e["end"]
                    for e in entries
                    if e.get("form") in _ANNUAL_REPORT_FORMS and not e.get("start") and e.get("end")
                ),
                default=None,
            )
            # FIXED 2026-08-22 (goal session: real-money-readiness audit, quarterly_balance_
            # sheet residual-contamination follow-up): some filers mistag EVERY 10-Q's fp as
            # "FY" instead of "Q1"/"Q2"/"Q3" for a specific fiscal year (a filer-side XBRL
            # tagging quirk, not per-fact noise - live-confirmed via AGNC/AGNC Investment
            # Corp: every one of its FY2020 10-Qs tags fp="FY", while its FY2021 10-Qs
            # correctly tag fp="Q1"/"Q2"/"Q3"). The strict `fp not in fp_filter` quarterly
            # gate below then drops the ENTIRE fiscal year from quarterly extraction, even
            # though real, distinct, correctly-deduped quarter-end instant values exist
            # (AGNC FY2020: Q1=$85.137B, Q2=$89.853B, Q3=$79.968B, live-confirmed via real
            # companyfacts JSON) - quarterly_balance_sheet was left showing 3 straight
            # quarters frozen at the FY-end value ($81.817B) from a stale pre-fix write,
            # untouched by the 2026-08-22 watermark-bypass backfill because the current
            # (correct) extraction logic produces zero rows for that year at all, not a
            # wrong value to overwrite it with. Derive a fallback quarter from the entry's
            # own end-date month instead of trusting the filer's fp tag, but ONLY when: (a)
            # it's an instant fact (no start - the accn+max-end-date dedup above already
            # guarantees this is the filing's own genuine current-period value, never a
            # comparative echo, so fp's unreliability here doesn't risk the contamination
            # this file's other fp-trust fixes are guarding against), and (b) this filer's
            # own fiscal year genuinely ends in December (checked below from its real
            # 10-K/equivalent instant facts) - deliberately NOT extended to non-calendar
            # fiscal years, where a bare calendar-month-to-quarter mapping would be wrong.
            _fye_month: int | None = None
            for _e in entries:
                if _e.get("form") in _ANNUAL_REPORT_FORMS and not _e.get("start") and _e.get("end"):
                    _fye_month = int(_e["end"][5:7])
                    break
            has_december_fiscal_year_end = _fye_month == 12
            # RESTORED 2026-09-02 (goal session: "missing SEC/XBRL data" audit) - this block
            # was part of `fd1c8a99f` (OFRM comparative-fp-aliasing fix) but that commit only
            # ever landed on the unmerged `growth-factor-realignment` branch; main picked up
            # the OTHER half of that same commit (the span-gated derived_fp override a few
            # dozen lines below, "not start_date" removed + 80-100 day duration-span gate
            # added) via a later commit, but not this block - a partial-hunk loss, not a
            # deliberate removal (confirmed via `git log -S` finding only fd1c8a99f ever
            # touched this exact line, and `git merge-base --is-ancestor fd1c8a99f HEAD`
            # returning false). Live re-verified the regression directly: calling
            # get_income_statement(client, 'OFRM', period='quarterly') against real SEC data
            # right now reproduces the original bug exactly - fiscal_year=2026 net_income_loss
            # is -$15,811,000 for BOTH Q1 and Q2 (Q1's real value silently overwriting Q2's),
            # instead of Q2's real -$4,950,000 per the original commit message.
            #
            # The instant-fact check above can never fire for an income-statement/cash-flow
            # concept (NetIncomeLoss, Revenues, ...) - those are always duration facts, so
            # "not _e.get('start')" never matches, and a company with < 1 year of public
            # history (e.g. OFRM, IPO'd Feb 2026) has no 10-K at all yet for ANY concept to
            # borrow a fiscal-year-end signal from. Fall back to a self-consistency check on
            # this concept's own duration facts: a genuine (non-comparative-echo) quarterly
            # fact's own fp tag agrees with the calendar quarter its own end-date month
            # implies under a December fiscal year end (Q1->03, Q2->06, Q3->09, Q4->12) - a
            # coincidence only possible for a company whose fiscal quarters actually do end
            # in Mar/Jun/Sep/Dec in that exact Q1-Q4 order, i.e. a genuine December fiscal
            # year end. Live-confirmed via OFRM's real NetIncomeLoss facts: its own Q1-2026
            # 10-Q reports start=2026-01-01/end=2026-03-31 under fp="Q1" - self-consistent -
            # even though OFRM has filed zero 10-Ks to date.
            #
            # NARROWED vs. the original fd1c8a99f version: only accept a match whose span is
            # a genuine single quarter (80-100 days), same gate already used a few dozen
            # lines below for the override itself. Found and live-confirmed why this matters
            # via DXC (a March-fiscal-year-end filer, one quarter offset from calendar): its
            # cash-flow concepts have exactly 2 "matches" under the original unqualified
            # check, both ~183/364-day CUMULATIVE comparative facts that happen to land on a
            # calendar-quarter-end month purely by coincidence (e.g. a 6-month-cumulative
            # fact spanning 2017-04-01 to 2017-09-30, re-tagged with the filing's own fp='Q3'
            # - an aliased comparative echo, not genuine self-consistency evidence). Without
            # this gate, restoring the block would wrongly mark DXC has_december_fiscal_year_
            # end=True and corrupt its real Q1 (a genuine 90-91 day fact) into the Q2 bucket
            # via the override below - live-confirmed via
            # utils.external.sec_statements.get_cash_flow(client, 'DXC', period='quarterly')
            # matching real SEC values ($-66M/$1.585B/$2.062B for Q1/Q2/Q3 FY2019) only
            # WITHOUT this block; a plain restoration of the original unqualified check
            # reproduces the exact Q1==Q2 collision found live in quarterly_cash_flow for 250
            # symbols (768 collision rows) that motivated this investigation. A genuine
            # single-quarter self-consistency match (like OFRM's, span=89) is unaffected by
            # this narrowing.
            if not has_december_fiscal_year_end:
                _q_from_month = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}
                for _e in entries:
                    _e_fp = _e.get("fp")
                    _e_start = _e.get("start")
                    _e_end = _e.get("end")
                    if _e_fp not in ("Q1", "Q2", "Q3", "Q4") or not _e_end or len(_e_end) < 7:
                        continue
                    if _q_from_month.get(_e_end[5:7]) != _e_fp:
                        continue
                    if _e_start:
                        try:
                            _e_span = (datetime.date.fromisoformat(_e_end) - datetime.date.fromisoformat(_e_start)).days
                        except ValueError:
                            continue
                        if not (80 <= _e_span <= 100):
                            continue
                    has_december_fiscal_year_end = True
                    break
            # BUG FOUND 2026-08-22 (goal session: quarterly balance-sheet comparative-period
            # contamination): a single filing (one accession number, "accn") typically tags
            # an instant concept's value TWICE - once for its own current reporting period,
            # once as a "prior period" comparative shown for context (occasionally a THIRD
            # time for an even older rollforward comparative, e.g. in a statement-of-equity
            # table). All copies inherit that SAME filing's fp/fy, which reflects the FILING's
            # own period, not each individual fact's real period (same filing-context-vs-
            # fact-identity conflation the "Use period end year..." comment below already
            # documents for "fy" specifically). Within any one filing, the fact with the
            # LATEST end date for a concept is always the filing's own current-period value;
            # every other same-accn fact for that concept is a comparative echo of a period
            # whose real value is already captured by ITS OWN filing (where it WAS the latest
            # end date). Tried a fiscal-year-end-month/day heuristic first instead of this -
            # live-confirmed too unreliable via PMT: its own 10-Ks separately tag "selected
            # quarterly financial data" footnote disclosures under fp='FY' with genuine
            # quarter-end dates, so a fact's own end date being a quarter-end date does NOT
            # reliably distinguish it from a true fiscal-year-end fact either way. Excluding
            # every non-latest-in-its-accn instant fact sidesteps the fp/fy unreliability
            # entirely - it only ever looks at each filing's own internal facts, never trusts
            # SEC's period labels. Duration facts (has "start") are unaffected - each real
            # duration fact within a filing already has its own distinct (start, end) span,
            # so they don't collide across periods the way instant facts do.
            _max_end_by_accn: dict[str, str] = {}
            for _e in entries:
                if _e.get("start"):
                    continue
                _accn, _e_end = _e.get("accn"), _e.get("end")
                if _accn and _e_end and (_accn not in _max_end_by_accn or _e_end > _max_end_by_accn[_accn]):
                    _max_end_by_accn[_accn] = _e_end
            # BUG FOUND 2026-08-31 (goal session: real-money-readiness audit, resolving
            # jakk_duration_fact_comparative_aliasing_found_not_fixed_20260831): the comment
            # just above ("duration facts... don't collide across periods the way instant
            # facts do") assumes a comparative echo always carries dates matching its real
            # period. Live-confirmed false via JAKK (JAKKS Pacific, CIK 1009829): its Q1
            # 2026 10-Q (accn 0001185185-26-001667) correctly tags its own Q1-2025
            # comparative (start=2025-01-01/end=2025-03-31, val=$113,253,000,
            # frame="CY2025Q1") but ALSO carries a second fact for the SAME concept with
            # FULL-YEAR dates (start=2025-01-01/end=2025-12-31) and the IDENTICAL
            # $113,253,000 value - not FY2025's real revenue ($570,671,000, confirmed via
            # JAKK's own real FY2025 10-K, accn 0001185185-26-000723, filed 2026-03-02).
            # This full-year-shaped fact even carries frame="CY2025" - the canonical-period
            # marker the PMT fix above trusts for instant facts - while the REAL 10-K fact
            # for that year carries no frame at all here, so extending that precedent to
            # duration facts would pick the WRONG value; deliberately not done. The
            # reliable signal instead: a real annual total practically never exactly equals
            # a single quarter's total for an operating company (verified zero false
            # positives against AAPL/MSFT/CHTR/ANDE's combined 685 real annual-span
            # duration facts) - only a copy-pasted/aliased comparative would. Detect this
            # per-accn: if an annual-span (>=330 day) duration fact's value exactly matches
            # a genuine short-span (<330 day) duration fact for the SAME concept from the
            # SAME accn (i.e. the filing's own real quarter figure), the long-span fact is
            # that quarter's value wearing borrowed annual dates, not a real annual total.
            # Skipped entirely below rather than let it win a "latest filed" tiebreak
            # against the genuine 10-K figure - exactly what happened for JAKK: the
            # mistagged fact's 2026-05-01 filed date beat the real 10-K's 2026-03-02 filed
            # date under the plain latest-filed rule the annual duration-fact tiebreak
            # otherwise uses.
            _short_span_val_by_accn: dict[str, set[Any]] = {}
            for _e in entries:
                _e_start = _e.get("start")
                if not _e_start or not _e.get("end"):
                    continue
                try:
                    _span = (datetime.date.fromisoformat(_e["end"]) - datetime.date.fromisoformat(_e_start)).days
                except ValueError:
                    continue
                if _span < 330:
                    _accn = _e.get("accn")
                    if _accn:
                        _short_span_val_by_accn.setdefault(_accn, set()).add(_e.get("val"))
            # BUG FOUND 2026-09-01 (goal session: "understand our data gaps" audit,
            # 52/53-week-fiscal-year phantom-year follow-up): the Jan-1-10-crossing
            # correction just below trusts entry['fy'] to detect and correct a 52/53-week
            # fiscal year whose end date lands in early January. That works for a fact's
            # own home filing (a 10-K correctly tags fy=<the fiscal year it's labeled>),
            # but breaks for TWO kinds of same-concept echo of that same fact appearing in
            # a later filing:
            #   (a) a DEF 14A proxy restating prior years for its compensation-discussion
            #       table - live-confirmed via FLO's and EXPO's proxies - carries
            #       fy=None/fp=None (no SEC period label at all).
            #   (b) a LATER 10-K's own prior-year comparative column for the same fact -
            #       live-confirmed via EXPO's FY2025 10-K (accn 0001193125-26-082508):
            #       its FY2024 comparative entry (start=2023-12-30, end=2025-01-03,
            #       val=$109,002,000 - identical to FY2024's own 10-K figure) carries
            #       fy=2025, NOT 2024 - SEC's "fy tags the FILING's own year, not each
            #       fact's true period" behavior (already documented above for the
            #       plain non-crossing case) applies just as much inside the Jan-crossing
            #       window. Unlike case (a), this entry's fy IS a plausible-looking int,
            #       so it doesn't even reach a "fy is missing" check - it just silently
            #       fails the `fy == period_year - 1` test (2025 != 2024) and keeps its
            #       naive, one-year-too-late period_year.
            # Case (a) leaves an fy-less entry with no correction at all - a phantom
            # bucket one year ahead of the real one, seeded with only whatever concept(s)
            # the proxy restates (usually just NetIncomeLoss, not EPS/shares) while the
            # real fiscal year's own complete row sits one bucket back - live-confirmed
            # FLO (phantom fiscal_year=2026 has only net_income_loss) and EXPO (same
            # shape). Case (b) is worse: it collides INTO the real next fiscal year's own
            # bucket (same period_year, same "FY" key, same form/filed date as the real
            # current-year fact, since both come from the same 10-K) and can silently win
            # or lose the existing tiebreak by iteration order alone - live-confirmed via
            # EXPO: with only fix (a) applied, this comparative echo (FY2024's real
            # $109,002,000) overwrote FY2025's own real value ($106,009,000) in the
            # fiscal_year=2025 bucket.
            #
            # Fix: for any entry landing in this Jan-crossing window, resolve fy from
            # whichever entry for this SAME concept+(start, end, val) - i.e. a genuine
            # duplicate/echo of the identical real-world fact - was FILED EARLIEST, not
            # from the entry's own bare fy field. A fact's earliest-filed appearance is
            # always its own home filing (10-K/20-F/etc., correctly fy-tagged for its own
            # period); every later echo (a subsequent 10-K's comparative column, a DEF
            # 14A's restated table) inherits that echoing filing's own fy/no-fy instead,
            # which this proves is not trustworthy. Applied unconditionally (not just
            # when the entry's own fy is missing) so case (b)'s misleading-but-present fy
            # is overridden too, not just case (a)'s absent one. Falls back to the
            # pre-fix behavior (no correction) when no earlier-filed corroborating entry
            # exists at all.
            _fy_by_start_end_val: dict[tuple[str, str, Any], tuple[int, str]] = {}
            for _e in entries:
                _e_fy = _e.get("fy")
                _e_filed = _e.get("filed")
                if isinstance(_e_fy, int) and _e.get("start") and _e.get("end") and _e_filed:
                    _key = (_e["start"], _e["end"], _e.get("val"))
                    _existing = _fy_by_start_end_val.get(_key)
                    if _existing is None or _e_filed < _existing[1]:
                        _fy_by_start_end_val[_key] = (_e_fy, _e_filed)
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
                    # See the _short_span_val_by_accn comment above this loop (JAKK case):
                    # an annual-shaped span whose value exactly matches a genuine quarter
                    # from the same accn is that quarter's value under borrowed annual
                    # dates, not a real annual total.
                    if span_days is not None and span_days >= 330:
                        _accn = entry.get("accn")
                        if _accn and entry.get("val") in _short_span_val_by_accn.get(_accn, ()):
                            continue

                # BUG FOUND 2026-08-31 (goal session: "get all the data we need" full-
                # coverage audit): a duration fact (has "start") sourced from an 8-K is
                # never a genuine periodic financial statement - Item 9.01 exhibits, investor-
                # presentation Regulation FD disclosures, and other 8-K content are not
                # subject to the same XBRL-tagging rigor as a 10-K/10-Q, and can carry
                # numbers that are wrong, a peer-comparison figure, or otherwise not the
                # filer's own audited result. Live-confirmed via real SEC companyfacts JSON:
                # Essential Utilities (WTRG, CIK 0000078128) tags
                # RevenueFromContractWithCustomerExcludingAssessedTax for FY2023/2024/2025
                # under a single 2026-03-25 "Regulation FD Disclosure" 8-K (accn
                # 0001193125-26-124163, fp=None, fy=None) with values ($4.217B/$4.653B/
                # $5.121B) that exactly match American Water Works' (AWK, an unrelated
                # company) real 10-K-sourced revenue for the same years to the dollar - not
                # WTRG's own real revenue (WTRG's genuine "Revenues" concept for the same
                # years, sourced from real 10-Ks, is ~$2.1-2.5B). Because this concept is
                # listed after "Revenues" in get_income_statement()'s concepts list (ASC-606
                # tags legitimately supersede the older concept for most post-2018 filers),
                # this bad 8-K value silently overwrote WTRG's real revenue in
                # annual_income_statement, corrupting every downstream ratio.
                # Deliberately does NOT extend to DEF 14A/proxy statements (fp=None is
                # accepted above specifically because 2026-07-31 relies on exactly that for
                # quarterly-only reporters like EE with no full annual filing) - 8-K
                # specifically, since it's a "current report" for events/exhibits, never a
                # periodic financial statement, and no fix in this file has ever relied on
                # trusting one for duration data (test_sec_custom_xbrl_concepts.py already
                # treats 8-K as something to skip when looking for a filer's authoritative
                # annual data, for the same reason).
                if start_date and entry.get("form") in ("8-K", "8-K/A"):
                    continue

                # See the _max_end_by_accn comment above this loop: drop any instant fact
                # that isn't the latest-end-date one within its own filing - a comparative/
                # rollforward echo of a period whose real value comes from its own filing.
                if not start_date:
                    _accn, _e_end = entry.get("accn"), entry.get("end")
                    if _accn and _e_end and _max_end_by_accn.get(_accn) not in (None, _e_end):
                        continue

                # FIXED 2026-08-18 (no-SEC-data audit continuation): see the
                # has_annual_report_form comment above this loop. An instant fact sourced
                # from a 10-Q/6-K must not seed the annual bucket when this concept has
                # real 10-K/20-F/40-F history and the fact is BEYOND that history's own
                # reach - it's a genuine mid-year snapshot, not a fiscal-year-end position,
                # and the fiscal year it falls in (derived from its own end date below)
                # usually has no 10-K filed yet at all.
                # NARROWED 2026-09-02 (see _max_annual_report_end comment above this loop,
                # WEC live-confirmed): only skip when this fact's end date is genuinely
                # AFTER the concept's own latest confirmed 10-K/20-F/40-F end date - a
                # fact at or before that boundary is a past fiscal year-end the annual
                # filing itself simply never re-tagged (recoverable from a later filing's
                # comparative column), not a premature current-year snapshot.
                if (
                    period == "annual"
                    and not start_date
                    and has_annual_report_form
                    and entry.get("form") not in _ANNUAL_REPORT_FORMS
                    and (_max_annual_report_end is None or (entry.get("end") or "") > _max_annual_report_end)
                ):
                    continue

                if period == "annual":
                    if fp == "FY" or fp is None or fp in ("Q1", "Q2", "Q3", "Q4"):
                        pass  # Accept annual, proxy, and quarterly(-but-full-span) data
                    else:
                        continue  # Skip other FP values
                elif period == "quarterly" and fp not in fp_filter:
                    # See has_december_fiscal_year_end's comment above this loop for the
                    # full AGNC-verified rationale. Only ever a fallback when the filer's
                    # own fp tag doesn't already give a real Q1-Q4 answer; derived_fp stays
                    # None (entry skipped, same as before this fix) for every case this
                    # doesn't narrowly apply to - duration facts, non-December fiscal
                    # years, or an end date that isn't a clean quarter-boundary month.
                    derived_fp = None
                    if not start_date and has_december_fiscal_year_end and entry.get("end") and len(entry["end"]) >= 7:
                        derived_fp = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}.get(entry["end"][5:7])
                    if derived_fp is None:
                        continue
                    fp = derived_fp
                elif (
                    period == "quarterly"
                    and has_december_fiscal_year_end
                    and entry.get("end")
                    and len(entry["end"]) >= 7
                ):
                    # BUG FOUND 2026-08-24 (goal session: real-money-readiness audit,
                    # quarterly_balance_sheet residual follow-up): an instant fact's own fp
                    # tag reflects the FILING's reporting period, not the fact's own period -
                    # the exact same filing-context-vs-fact-identity conflation this file
                    # already documents for fy (see "Use period end year..." below) and for
                    # fp when it's mistagged 'FY' (the AGNC case just above). This is a THIRD
                    # variant: fp already looks like a normal Q1-Q4 tag (so the branch above
                    # never fires), but the fact is actually a prior-period comparative echo
                    # that its own filing never re-tagged with a genuine current-period value
                    # for this concept - live-confirmed via CCLD: its Q1/Q2/Q3 2021 10-Qs each
                    # have exactly ONE Assets fact, end=2020-12-31 (the FY2020 year-end
                    # comparative), tagged fp='Q1'/'Q2'/'Q3' (borrowed from the FILING's own
                    # quarter) - so it passes the accn-latest-end-date filter above (it's the
                    # only Assets fact in that accn) and, untouched, would collide with the
                    # real Q1/Q2/Q3 2020 facts' own (2020, 'Q1'/'Q2'/'Q3') keys, winning via
                    # the "prefer latest end date" tiebreak below and silently overwriting
                    # them with the FY-end value. A universe-wide scan for this exact
                    # single-quarter-aliasing signature found 53 symbols, including
                    # actively-traded large/mid-caps (BX, BN, AES), not just micro-caps.
                    # Always deriving fp from the fact's own end date (already trusted
                    # elsewhere in this file - see period_year below - as more reliable than
                    # any SEC period label) instead of trusting a syntactically-valid-looking
                    # fp tag closes this: when the filer's own fp already agrees with the
                    # end-date-derived quarter, this is a no-op; when it doesn't, the derived
                    # quarter is the fact's real period, and the key it produces will
                    # correctly collide with (not overwrite) the genuine same-period fact.
                    #
                    # EXTENDED 2026-09-02 (goal session: "missing SEC/XBRL data" audit,
                    # restoring the duration-fact half of `fd1c8a99f`, which - like the
                    # self-consistency block above - only ever landed on the unmerged
                    # `growth-factor-realignment` branch, not main). Live-confirmed via OFRM
                    # why "not start_date" (instant-only) isn't enough on its own: even with
                    # the self-consistency block above correctly setting
                    # has_december_fiscal_year_end=True and the existing shorter-span-wins
                    # tiebreak below (2026-08-29, META fix), OFRM's real Q2-2026 NetIncomeLoss
                    # bucket has THREE competing duration facts - a genuine H1 cumulative
                    # (~180 days), the real discrete Q2 (Apr-Jun, 90 days), and a Q1
                    # comparative mistagged with the filing's own fp='Q2' (Jan-Mar, 89 days,
                    # same accn as the H1 fact). The shorter-span heuristic correctly prefers
                    # a genuine quarter over a cumulative echo, but is not a meaningful
                    # tiebreak between TWO genuine single-quarter spans - Jan-Mar's 89 days
                    # happens to be one day shorter than Apr-Jun's 90 (February is short), so
                    # the mistagged comparative silently won over the real value purely by
                    # calendar-month coincidence (live-confirmed: net_income_loss stored
                    # -$15,811,000 for both Q1 and Q2 2026, when Q2's real value is
                    # -$4,950,000). The fix is to remove the mistagged entry from the Q2
                    # bucket entirely rather than out-tiebreak it: applying this same
                    # end-date-derived fp correction to a duration fact - narrowly gated to a
                    # genuine single-quarter span (80-100 days) so real cumulative (H1/9mo)
                    # facts are untouched and still resolved by the shorter-span tiebreak once
                    # co-located with their quarter's real discrete fact via this same
                    # derivation - relocates Jan-Mar's comparative echo to Q1 (where it
                    # harmlessly duplicates the real Q1 value already there), leaving Q2's
                    # bucket with only the real discrete fact and the H1 cumulative, which the
                    # existing tiebreak already resolves correctly.
                    _duration_span_days: int | None = None
                    if start_date:
                        try:
                            _duration_span_days = (
                                datetime.date.fromisoformat(entry["end"]) - datetime.date.fromisoformat(start_date)
                            ).days
                        except ValueError:
                            _duration_span_days = None
                    if not start_date or (_duration_span_days is not None and 80 <= _duration_span_days <= 100):
                        derived_fp = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}.get(entry["end"][5:7])
                        if derived_fp is not None:
                            fp = derived_fp

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
                    if start_date:
                        _corroborated = _fy_by_start_end_val.get((start_date, end_date, entry.get("val")))
                        if _corroborated is not None:
                            fy = _corroborated[0]
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

                # BUG FOUND 2026-08-19 (goal: fix today's halting/data-quality issues):
                # SEC's own XBRL data is occasionally corrupted in ways that produce an
                # implausible fiscal year from either derivation path above - live-confirmed
                # two distinct patterns: (1) NAII NetIncomeLoss fact tagged end="2031-09-25"
                # (evidently meant 2023 - fy=2022 on the same fact is correct) fed
                # fiscal_year=2031 via the end-date derivation, writing REAL revenue/
                # net_income into the DB under a 5-years-in-the-future fiscal year
                # (data_unavailable=False, so it would be picked up as "latest data" by any
                # naive ORDER BY fiscal_year DESC caller); (2) PRTH dei:
                # EntityCommonStockSharesOutstanding facts carry fy=43465/43830 directly in
                # SEC's JSON (an Excel-serial-like value, not a real year) - trusted verbatim
                # by the dei-source branch above, this also broke
                # data_loader_status's MAX(fiscal_year) -> date(fiscal_year, 12, 31) watermark
                # write every run ("year 43830 is out of range", live-confirmed in
                # logs/load_financial_statements_1787150329.log). Neither end_date nor fy is
                # trustworthy in isolation, so fall back to whichever of the two is itself
                # plausible, and skip the entry entirely (like other malformed-data skip
                # paths in this file) only if neither is.
                if isinstance(period_year, int) and not (
                    _MIN_PLAUSIBLE_FISCAL_YEAR <= period_year <= _max_plausible_fiscal_year
                ):
                    fallback_year = entry.get("fy")
                    end_year = int(end_date[:4]) if end_date and len(end_date) >= 4 else None
                    candidate = fallback_year if isinstance(fallback_year, int) else None
                    if candidate is None or not (_MIN_PLAUSIBLE_FISCAL_YEAR <= candidate <= _max_plausible_fiscal_year):
                        candidate = end_year
                    if candidate is not None and (
                        _MIN_PLAUSIBLE_FISCAL_YEAR <= candidate <= _max_plausible_fiscal_year
                    ):
                        logger.warning(
                            f"[SEC_STATEMENTS] {symbol}: implausible fiscal_year={period_year} "
                            f"from concept={concept} end={end_date!r} fy={entry.get('fy')!r} - "
                            f"using {candidate} instead"
                        )
                        period_year = candidate
                    else:
                        logger.warning(
                            f"[SEC_STATEMENTS] {symbol}: skipping entry with implausible "
                            f"fiscal_year={period_year} and no plausible fallback "
                            f"(end={end_date!r} fy={entry.get('fy')!r})"
                        )
                        continue

                # FIX 2026-09-03 (goal: SEC/XBRL missing-data audit, BTCS live-verified via
                # real SEC companyfacts JSON): the annual branch above already rejects a too-
                # SHORT duration from its own bucket (span_days < 330 -> skip, "Real single-
                # quarter/partial-year data - not annual"), but quarterly had no mirror-image
                # guard against a too-LONG one. A fact whose OWN fp tag already equals Q1-Q4
                # skips the derived_fp relocation logic above entirely (that only fires when fp
                # does NOT already match a real quarter) and was accepted at face value with no
                # span check at all. Live-confirmed via BTCS: its 2012 Q1/Q2/Q3 10-Qs (and 2014
                # 10-Q/A amendments) each independently mistagged the SAME full FY2010 annual
                # total (start=2010-01-01, end=2010-12-31, 365 days) as that quarter's own
                # "prior year" comparative figure - fp="Q1" in the Q1 10-Q, fp="Q2" in the Q2
                # 10-Q, fp="Q3" in the Q3 10-Q, four separate genuine filer-side tagging errors
                # across four filings, not one mis-relocated comparative like the OFRM/DXC case
                # `b8c37c0bc` fixed. With no genuine discrete quarterly fact ever filed for
                # FY2010 to tiebreak against, each mistagged annual total became the sole
                # occupant of its (2010, Q1/Q2/Q3) bucket - reproduced exactly via
                # get_income_statement(client, 'BTCS', period='quarterly'): FY2010 Q1/Q2/Q3
                # revenue/net_income all equalled the FY2010 annual total. Same 330-day
                # threshold as the annual branch's own span_days<330 guard, applied
                # symmetrically: no genuine quarterly-bucket fact (even a 9-month YTD
                # cumulative, the longest legitimate one) should ever approach a full year.
                if period == "quarterly" and start_date and fp in ("Q1", "Q2", "Q3", "Q4") and end_date:
                    try:
                        _q_span_days = (
                            datetime.date.fromisoformat(end_date) - datetime.date.fromisoformat(start_date)
                        ).days
                    except ValueError:
                        _q_span_days = None
                    if _q_span_days is not None and _q_span_days >= 330:
                        continue

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
                # FIXED 2026-09-02 (goal session: "missing SEC/XBRL data" audit, live SEC
                # EDGAR verification): _PRIMARY_STATEMENT_FORMS ranks 10-K and 10-Q equally
                # (both "primary", tier 1) - correct for a QUARTERLY bucket, but wrong for
                # an annual ("FY") bucket: a 10-Q can carry a genuine "trailing twelve
                # months" duration fact (start/end exactly ~365 days apart, passing this
                # loop's own span_days>=330 "annual-shaped" filter above) that is NOT the
                # filer's real Jan-Dec fiscal year - it's a rolling window ending mid-year.
                # Live-confirmed via real SEC EDGAR companyconcept JSON: AMZN's Q2 2026
                # 10-Q (filed 2026-07-31) tags NetIncomeLoss with start=2025-07-01,
                # end=2026-06-30, val=$135,281,000,000 (a real TTM figure) - this lands in
                # the SAME (period_year=2026, "FY") bucket as AMZN's real FY2026 10-K would,
                # and via the old equal-rank-then-latest-filed tiebreak, ALSO clobbered the
                # already-correct FY2025 entry: AMZN's real FY2025 10-K (filed 2026-02-06)
                # reports NetIncomeLoss=$77,670,000,000, but a LATER-filed Q2 2026 10-Q TTM
                # fact (start=2024-07-01, end=2025-06-30, val=$70,623,000,000, also >=330
                # days) won the (2025, "FY") bucket instead purely by filing date - live-
                # confirmed exactly these two wrong values on file in annual_income_statement
                # before this fix. A genuine annual-report-form entry (10-K/20-F/40-F) must
                # always outrank a same-tier 10-Q/6-K entry for the "FY" key specifically,
                # regardless of filed date - same "structural form authority beats filing
                # recency" principle _ANNUAL_REPORT_FORMS already applies to the instant-fact
                # premature-bucket guard elsewhere in this function. Only applies to the "FY"
                # key; quarterly buckets (fp in Q1-Q4) are unaffected, so a pure quarterly-
                # only reporter's own latest-filed 10-Q still wins its bucket unchanged - and
                # a 10-Q still wins the "FY" bucket by the ordinary rank-vs-non-primary-form
                # rule above when no annual-report-form entry exists for that period at all.
                is_fy_bucket = key[1] == "FY"
                entry_rank = (
                    2
                    if is_fy_bucket and entry_form in _ANNUAL_REPORT_FORMS
                    else 1
                    if entry_form in _PRIMARY_STATEMENT_FORMS
                    else 0
                )
                row_filed = row.get(f"_filed_{col}")
                row_end = row.get(f"_end_{col}")
                rank_key = f"_rank_{col}"
                row_rank = int(row[rank_key]) if rank_key in row else 0
                # Form-rank gates first: a primary form (10-K/10-Q) always outranks a
                # non-primary one (DEF 14A, 8-K, S-1, etc.) regardless of end/filed date -
                # see the 2026-08-17 DEF 14A comment above. Only when ranks tie do we fall
                # through to the existing instant-vs-duration end-date/filed-date tiebreak.
                is_instant = not start_date
                if col not in row:
                    should_replace = True
                elif entry_rank != row_rank:
                    should_replace = entry_rank > row_rank
                elif is_instant != bool(row.get(f"_is_instant_{col}")):
                    # FIX 2026-08-31 (/goal pre-real-money audit, live-verified LADR): a
                    # genuine annual duration fact (has "start", already passed the
                    # span_days>=330 annual-shape filter above) must always outrank an
                    # instant (point-in-time, no "start") fact colliding into the same
                    # (fiscal_year, "FY") bucket for the same concept - an instant fact
                    # appearing at all under a duration-shaped concept's name is itself
                    # anomalous (a real annual total is never point-in-time). Live-confirmed
                    # via LADR (Ladder Capital, mortgage REIT) FY2019: OperatingLeaseLeaseIncome
                    # has both the real annual total (start=2019-01-01/end=2019-12-31,
                    # val=$106,366,000) AND a bare instant fact (no start, end=2019-05-01,
                    # val=$3,900,000 - almost certainly a future-minimum-lease-payments
                    # schedule row, not a period total) from the SAME accn/filed date, so
                    # neither the rank gate above nor the old filed-date tiebreak below could
                    # tell them apart - whichever was iterated first in SEC's JSON silently
                    # won, and that was the wrong one. Safe for balance-sheet concepts too:
                    # they structurally never emit a genuine annual-duration-shaped fact
                    # under their own concept name (Assets/Liabilities/etc. are inherently
                    # point-in-time - no legitimate "start" date ever exists for them), so
                    # this branch is a no-op there and only fires on a real conflict like
                    # LADR's.
                    should_replace = bool(row.get(f"_is_instant_{col}"))
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
                    # tiebreak; annual duration facts are unaffected - their span-day filter
                    # above already narrows the field to genuine annual totals, where "most
                    # recently filed" legitimately means "most likely restated/corrected".
                    # Quarterly duration facts get their own span tiebreak below - see the
                    # 2026-08-29 comment at that branch.
                    if is_instant:
                        should_replace = row_end is None or end_date > row_end
                        if not should_replace and end_date == row_end:
                            # FIXED 2026-08-22 (goal session: PMT debt-maturity-schedule
                            # contamination): multiple facts can legitimately share the exact
                            # same (concept, end_date) - a real balance-sheet snapshot AND
                            # unrelated debt-maturity-schedule footnote entries that happen to
                            # use the same future end date as a schedule bucket boundary.
                            # "latest filed wins" alone is NOT reliable here: schedule entries
                            # get re-disclosed (same date, same value) in every subsequent
                            # year's 10-K/10-Q, so a schedule entry can have a LATER filed
                            # date than the one real snapshot fact for that period. SEC's own
                            # "frame" key is the reliable signal - it's only assigned to the
                            # single canonical, non-dimensional instant/duration fact for a
                            # standardized calendar period, never to a dimensional/footnote
                            # schedule entry. Live-confirmed via PMT's real companyfacts JSON:
                            # LongTermDebt end=2026-03-31 has 4 candidate entries (fy=2021/22/23
                            # all val=$695M, no frame; fy=2024 val=$1.497B, frame="CY2026Q1I")
                            # - the frame'd entry is the real snapshot, the other 3 are the
                            # same static debt-maturity-schedule bucket re-cited across 3 years
                            # of filings. DB-wide cross-check against every frame-confirmed
                            # LongTermDebt value found 11 real mismatches (FY2022-2024 Q1-Q3,
                            # off by billions - e.g. FY2022 stored $1.70B vs real $5.07B).
                            entry_has_frame = bool(entry.get("frame"))
                            row_has_frame = bool(row.get(f"_frame_{col}"))
                            if entry_has_frame != row_has_frame:
                                should_replace = entry_has_frame
                            else:
                                should_replace = row_filed is None or entry_filed > row_filed
                    elif period == "quarterly":
                        # FIXED 2026-08-29 (goal: composite-score validation against real
                        # data): a Q2/Q3 10-Q's XBRL discloses BOTH the discrete "three
                        # months ended" fact AND the cumulative "six/nine months ended"
                        # fact for the same line item, and SEC tags fp='Q2'/'Q3' on the
                        # FILING's own period for both - identical (fiscal_year, fp) key,
                        # same filed date (same filing) - so the old filed-date-only
                        # tiebreak picked whichever happened to iterate first, which
                        # empirically was the CUMULATIVE fact. Live-confirmed via META's
                        # real companyfacts JSON: fy=2026/fp=Q2 has both a 2026-04-01to
                        # 2026-06-30 discrete fact (val=$60.801B, frame="CY2026Q2") and a
                        # 2026-01-01to2026-06-30 cumulative fact (val=$117.111B,
                        # frame=None) - quarterly_income_statement stored the $117.111B
                        # H1-cumulative figure as META's "Q2 2026 revenue", corrupting
                        # every downstream growth_metrics YoY/TTM calc (revenue_growth_1y
                        # came out -71.98% against margins that were actually improving).
                        # Same pattern independently confirmed for AAPL and MSFT - this is
                        # a systemic bug affecting essentially every calendar-Q2/Q3 filer,
                        # not a META-specific data issue. A genuine single quarter always
                        # spans ~89-92 days; a same-fiscal-year cumulative echo spans
                        # ~180-190 (H1) or ~270-280 (9mo) days - always clearly
                        # distinguishable via duration alone, so prefer the entry with the
                        # SHORTER start-to-end span over the filed-date tiebreak.
                        entry_span = (
                            (datetime.date.fromisoformat(entry["end"]) - datetime.date.fromisoformat(start_date)).days
                            if entry.get("end")
                            else None
                        )
                        row_span = row.get(f"_span_{col}")
                        if entry_span is not None and row_span is not None and entry_span != row_span:
                            should_replace = entry_span < row_span
                        else:
                            should_replace = row_filed is None or entry_filed > row_filed
                    else:
                        # FIX 2026-08-31 (/goal pre-real-money audit, live-verified TKR):
                        # two genuine annual-length (>=330-day) duration facts for the SAME
                        # concept can both exist in the SAME filing (same accn/filed date) -
                        # a real calendar-year total and an off-calendar spurious value
                        # (e.g. a stray sub-line or filing-agent error) - and then both get
                        # re-cited verbatim in later years' 10-Ks with matching filed dates
                        # each time, so the old plain filed-date tiebreak (strict >) never
                        # distinguishes them; whichever was iterated first in SEC's JSON
                        # silently won. Live-confirmed via TKR (Timken) FY2015
                        # SalesRevenueGoodsNet: the real total (start=2015-01-01/
                        # end=2015-12-31, val=$2,872,300,000) and a spurious value
                        # (start=2014-10-01/end=2015-09-30, val=$20,600,000, ~0.7% of real
                        # revenue) both first appear in accn 0000098362-16-000097 (filed
                        # 2016-02-24) and both get re-cited identically in 2 later 10-Ks
                        # (accn ...17-000031 filed 2017-02-21, accn ...18-000033 filed
                        # 2018-02-15) - same filed dates every time. The one reliable
                        # difference: the real value eventually gets frame="CY2015" in its
                        # later re-citations (SEC's own signal for "the single canonical
                        # value for this standardized period" - already trusted the same
                        # way for the instant-fact PMT case above), the spurious value
                        # never does, in any of its 3 occurrences. Applying the identical
                        # frame-preference principle here (not a new heuristic - the same
                        # one already proven safe for instant facts) before falling back to
                        # filed-date resolves this the same way it does for PMT.
                        entry_has_frame = bool(entry.get("frame"))
                        row_has_frame = bool(row.get(f"_frame_{col}"))
                        if entry_has_frame != row_has_frame:
                            should_replace = entry_has_frame
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
                    row[f"_frame_{col}"] = bool(entry.get("frame"))
                    row[f"_is_instant_{col}"] = is_instant
                    if period == "quarterly" and start_date and end_date:
                        try:
                            row[f"_span_{col}"] = (
                                datetime.date.fromisoformat(end_date) - datetime.date.fromisoformat(start_date)
                            ).days
                        except ValueError:
                            row[f"_span_{col}"] = None

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
                and not k.startswith("_frame_")
                and not k.startswith("_span_")
                and not k.startswith("_is_instant_")
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
