"""Zero-vs-real-component guards for SecEdgarStatementLoader.transform() (sec_base.py) -
extracted 2026-09-16 (goal: SEC-vs-yfinance divergence sweep) to keep sec_base.py under the
file-size ratchet's hard ceiling after this sweep's fixes, mechanical extraction only, no
behavior change.

All three guards close the same root-cause family: this loader's field_mapping resolves
multiple XBRL concepts onto one DB column with "first-populated-wins" / "fallback-only"
semantics, but several concepts represent one component of a multi-part total (one specific
debt instrument, one dividend class, one capex sub-category, one entity's legal-structure-
specific equity tag) rather than an alternate total for the same thing. A real "$0 of this
one component" fact was either unconditionally overwriting an already-resolved larger total
via ordinary last-processed-wins (a plain, non-fallback concept), or permanently blocking a
later, genuinely nonzero component via the fallback-only guard's "already in row" check,
which treats a stored 0 the same as a resolved real total.

Fields covered (per live SEC companyfacts JSON verification, 2026-09-16 sweep):
- long_term_debt/short_term_debt: subordinated_debt, advances_from_federal_home_loan_banks,
  senior_notes, notes_payable, unsecured_debt, FederalHomeLoanBankAdvancesLongTerm (BANR/
  AMTB/IBCP/MPB/CBNK/MYFW/PNBK).
- capex: payments_to_acquire_land, payments_to_acquire_other_productive_assets,
  payments_to_acquire_real_estate (DRH/NSC/SNPS/VICI).
- dividends_paid: PaymentsOfDividendsCommonStock vs PaymentsOfDividendsPreferredStockAnd
  PreferenceStock (CMCT) - genuinely additive, not alternatives; this loader has no
  per-field summing mechanism, so preserving the larger, already-resolved figure rather
  than zeroing it out is the safer of the two available options.
- cash_and_equivalents: CashAndCashEquivalentsAtCarryingValue is a permanently frozen $0
  across every fiscal year for CDIO/FAC/INDO/AKTX, overwriting the real, evolving combined
  cash+restricted-cash figure sec_balance_sheet.py's own design intended as a lower-fidelity
  fallback only.
- stockholders_equity: MembersEquity=0 (meant to be an LLC-only analogue, assumed mutually
  exclusive with StockholdersEquity per sec_balance_sheet.py's own comment) overwrote a
  real, correct StockholdersEquity for FLOC/INR/WBI.
- accounts_receivable: PED's real AccountsReceivableNet value was blocked by an earlier,
  real $0 under ReceivablesNetCurrent.
- income_tax_expense: BCSF's real InvestmentIncomeOperatingTaxExpenseBenefit (a BDC-specific
  concept) was blocked by an earlier, real $0 under IncomeTaxExpenseBenefit.
"""

from decimal import Decimal
from typing import Any

# Fields where a fallback-only concept's OWN real $0 must not permanently claim the slot -
# skip that first write (see is_zero_first_write_blocking_field) so a LATER, genuinely
# nonzero fallback concept still gets a chance; if nothing ever writes a nonzero value, the
# field honestly stays None rather than a confidently-wrong 0.
ZERO_FIRST_WRITE_GUARD_FIELDS = frozenset(
    {
        "long_term_debt",
        "short_term_debt",
        "capex",
        "accounts_receivable",
        "income_tax_expense",
        # ADDED 2026-09-16 (same sweep, second follow-up pass): RAVE (Rave Restaurant
        # Group, a franchisor) tags a real "CostOfRevenue" fact at $0/$1,000 (an
        # unrelated, near-zero line item for this filer) alongside a real, much larger
        # "FranchisorCosts" fact ($3,956,000 FY2023, exactly matching the yfinance-
        # flagged value) for the same fiscal year - same "unrelated concept's real $0/
        # near-0 permanently blocks a later, genuinely nonzero fallback concept" bug as
        # every other field in this set.
        "cost_of_revenue",
        # ADDED 2026-09-16 (same sweep): DTST tags a real "Dividends" bare-concept fact
        # at $0 (processed FIRST in sec_cash_flow.py's concept list, well before the
        # DividendsPreferredStock family) alongside real, nonzero
        # "DividendsPreferredStock" ($63,683) and "DividendsShareBasedCompensationCash"
        # ($1,179,357, the yfinance-matching figure) facts for the same fiscal year -
        # both later fallback-only concepts were permanently blocked by the earlier
        # real-$0 write, same bug shape as every other field in this set.
        "dividends_paid",
        # ADDED 2026-09-16 (same sweep): TITN tags a real "InterestAndDebtExpense" fact
        # at $0 (processed FIRST, fallback-only) alongside a real, nonzero
        # "FinancingInterestExpense" ($24,109,000 FY2026) - the earlier real-$0 write
        # blocked financing_interest_expense from ever populating interest_expense, which
        # in turn meant the interest_expense_other dual-concept sum (see sec_base.py's
        # transform()) summed against 0 instead of the real $24,109,000, silently
        # understating interest_expense by that whole amount. Same bug shape as every
        # other field in this set.
        "interest_expense",
        # ADDED 2026-09-17 (goal: xbrl_yfinance_line_item_report remediation follow-up):
        # INR (Infinity Natural Resources) FY2022 (end 2022-12-31) and FY2024 (end
        # 2024-12-31) live-confirmed via real SEC companyfacts JSON - the mirror image of
        # this module's own FLOC/INR/WBI ZERO_OVERWRITE_GUARD_FIELDS "stockholders_equity"
        # entry (which handles a REAL EXISTING nonzero StockholdersEquity being overwritten
        # by a LATER real $0 MembersEquity - INR's own FY2025 case: StockholdersEquity=
        # $307,139,000 written first, MembersEquity=$0 correctly blocked from overwriting
        # it). For FY2022/FY2024, the plain "StockholdersEquity" concept itself is a real
        # $0 (INR was still LLC-structured pre-IPO), processed FIRST (not fallback-gated at
        # all), which then permanently blocked the later, real, nonzero "MembersEquity"
        # fallback concept ($149,506,000 FY2022, $508,242,000 FY2024 - both EXACT matches
        # to the yfinance-flagged values) from ever being written - the existing
        # `db_field in row` fallback guard treats a stored 0 the same as a resolved real
        # total, same bug shape as every other field in this set.
        "stockholders_equity",
    }
)

# Fields where a LATER write of exactly 0 (fallback-only OR plain) must never overwrite an
# ALREADY-resolved, genuinely nonzero total (see is_zero_overwrite_blocking_field). Never
# fires the reverse direction - a real nonzero value always still overwrites an existing 0.
ZERO_OVERWRITE_GUARD_FIELDS = frozenset(
    {
        "long_term_debt",
        "short_term_debt",
        "capex",
        "dividends_paid",
        "cash_and_equivalents",
        "stockholders_equity",
        # ADDED 2026-09-16 (same sweep, second follow-up pass): QS (QuantumScape) - the
        # real "IncomeTaxExpenseBenefit" concept correctly writes $1,544,000 FY2025
        # (matching the yfinance-flagged value), but sec_statements.py's
        # _fill_income_tax_expense_from_current_deferred_split() then computes a real $0
        # from CurrentIncomeTaxExpenseBenefit + DeferredIncomeTaxExpenseBenefit for this
        # filer and writes it directly to the SAME "income_tax_expense" identity key,
        # processed LAST in dict order, unconditionally overwriting the correct total via
        # plain (non-fallback) last-write-wins - same "component/derived-$0 blocks a real
        # total" bug shape as every other field in this set, just with a computed value
        # instead of a raw XBRL concept as the offending $0.
        "income_tax_expense",
    }
)


def redirect_secured_debt_for_reit(
    sec_field: str, db_field: str, symbol: str | None, reit_symbols: frozenset[str]
) -> str:
    """OLP (One Liberty Properties) live-confirmed via real SEC companyfacts JSON: the
    2026-09-09 "secured_debt" -> "short_term_debt" mapping (added on DE's evidence, where
    SecuredDebt is a smaller short-term-debt-adjacent sibling of DebtCurrent) is wrong for
    equity REITs, where SecuredDebt is the standard concept for their real estate mortgage
    debt - their PRIMARY long-term financing, not a short-term instrument. OLP's SecuredDebt
    grows steadily $396M (FY2021) -> $517M (FY2025), tracking total_assets ($753M -> $858M)
    the way a REIT's mortgage book should - completely implausible as "short-term debt" for
    an $858M-asset REIT. Redirects to long_term_debt for REIT-classified symbols only; DE
    and every other non-REIT filer keep the original short_term_debt mapping (returns
    db_field unchanged for them).
    """
    if sec_field == "secured_debt" and db_field == "short_term_debt" and symbol in reit_symbols:
        return "long_term_debt"
    return db_field


def is_zero_first_write_blocking_field(db_field: str, existing: Any, value: Any) -> bool:
    """True if a fallback-only concept's own real value (`value`) is nonzero and would be
    the first write for `db_field`, but the field's existing already-stored value happens to
    be an unrelated concept's real $0 - see ZERO_FIRST_WRITE_GUARD_FIELDS' module docstring
    for why a stored 0 must not block this write the way a stored nonzero total legitimately
    would.
    """
    return (
        db_field in ZERO_FIRST_WRITE_GUARD_FIELDS
        and isinstance(existing, (int, float, Decimal))
        and float(existing) == 0.0
        and isinstance(value, (int, float, Decimal))
        and float(value) != 0.0
    )


def is_zero_overwrite_blocking_field(db_field: str, existing: Any, value: Any) -> bool:
    """True if `value` (the incoming concept's own real $0) would overwrite `db_field`'s
    already-resolved, genuinely nonzero `existing` value - see ZERO_OVERWRITE_GUARD_FIELDS'
    module docstring for why this must be blocked regardless of the incoming concept's
    fallback_only status.
    """
    return (
        db_field in ZERO_OVERWRITE_GUARD_FIELDS
        and isinstance(existing, (int, float, Decimal))
        and float(existing) != 0.0
        and isinstance(value, (int, float, Decimal))
        and float(value) == 0.0
    )


# (db_field, sec_field) pairs where the two concepts are genuinely distinct, additive
# components of the same total rather than alternates for the same fact - extracted here
# 2026-09-17 (moved out of sec_base.py to stay under the file-size ratchet's hard ceiling
# after the TITN addition, mechanical extraction only, no behavior change). Both pairs were
# live-confirmed via real SEC companyfacts JSON to co-occur in the same fiscal year for the
# named filer, each under its own distinct XBRL concept, summing to (or very near) the
# yfinance-flagged total:
# - capex: payments_to_acquire_oil_and_gas_property + payments_to_explore_and_develop_oil_
#   and_gas_properties (CRGY FY2025: $818.9M acquisition + $951.0M E&D).
# - interest_expense: financing_interest_expense (mapped to interest_expense) +
#   interest_expense_other (TITN FY2026: $24,109,000 + $18,974,000 = $43,083,000, exactly
#   matching yfinance; FY2025: $34,710,000 + $15,105,000 = $49,815,000).
# - ppe_net: property_plant_and_equipment_net + mineral_properties_net (mining filers'
#   sector-specific real net property asset, distinct from and additive to a small remaining
#   corporate PP&E balance) / property_plant_and_equipment_net + oil_and_gas_property_
#   successful_effort_method_net (O&G filers' equivalent). ADDED 2026-09-17 (goal:
#   divergence-repair trend-break sweep) - live-confirmed via real SEC companyfacts JSON:
#   THM (International Tower Hill Mines, CIK 0001134115) FY2025: MineralPropertiesNet
#   $55,375,124 + PropertyPlantAndEquipmentNet $7,465 = $55,382,589, an EXACT match to
#   yfinance's flagged $55,382,589 - proves these are genuinely additive components (mineral
#   rights vs. corporate office equipment), not alternates. PZG (Paramount Gold Nevada, CIK
#   0001629210) same pattern. RRC (Range Resources, CIK 0000315852) FY2025:
#   OilAndGasPropertySuccessfulEffortMethodNet $6,708,366,000 + PropertyPlantAndEquipmentNet
#   $4,935,000 = $6,713,301,000, same ballpark as yfinance's $6,886,743,000 (small residual
#   gap plausibly right-of-use/other assets yfinance includes that we don't track here). HPK
#   (HighPeak Energy, CIK 0001792849) same pattern. Initially wired as fallback-only, which
#   was wrong (the plain concept legitimately has real, small data for these filers, so
#   fallback-only's "only fill if nothing else found" ordering let the standard concept
#   silently overwrite the larger sector value on later processing) - corrected to additive
#   same session, before landing, after a reload produced zero DB change and exposed the bug.
# sec_base.py's transform() has no per-field summing mechanism for _aggregate_concepts (each
# concept keeps its own distinct snake_case key there) - the collision happens where
# field_mapping resolves both concepts onto the same db_field, and ordinary last-listed-wins
# would otherwise silently discard whichever processed first, understating the total.
ADDITIVE_CONCEPT_PAIRS = frozenset(
    {
        ("capex", "payments_to_acquire_oil_and_gas_property"),
        ("capex", "payments_to_explore_and_develop_oil_and_gas_properties"),
        # ADDED 2026-09-17 (xbrl_yfinance_line_item_report capex cluster follow-up): SM (SM
        # Energy, CIK 0000893538) FY2022 live-confirmed via real SEC companyfacts JSON -
        # "PaymentsToAcquireOilAndGasPropertyAndEquipment" (a near-zero $7,000 residual
        # instrument that fiscal year) is a DIFFERENT concept from the already-additive
        # "payments_to_acquire_oil_and_gas_property" (no "_and_equipment" suffix) above, so it
        # fell through to the ordinary last-listed-wins else-branch and unconditionally
        # overwrote the already-resolved, much larger
        # "payments_to_explore_and_develop_oil_and_gas_properties" ($879,934,000) with its own
        # tiny $7,000 value. $879,934,000 + $7,000 = $879,941,000, an EXACT match to
        # yfinance's flagged $879,941,000 - proves these are genuinely additive components
        # (development spend vs. a separate small property/equipment acquisition), not
        # alternates, same shape as the sibling concept already in this set.
        ("capex", "payments_to_acquire_oil_and_gas_property_and_equipment"),
        ("interest_expense", "interest_expense_other"),
        # ADDED 2026-09-18 (goal session, data-issue reduction, WBD live-confirmed): see
        # sec_income_statement.py's concept-fetch-list comment on these two film-amortization
        # concepts for the full reconciling math (WBD FY2023: combined depreciation +
        # AmortizationOfIntangibleAssets $7,951,000,000 + these two concepts $10,648,000,000 +
        # $5,165,000,000 = $23,764,000,000, within 1% of yfinance's $24,009,000,000).
        ("amortization_expense", "film_monetized_in_film_group_amortization_expense"),
        ("amortization_expense", "film_monetized_on_its_own_amortization_expense"),
        ("ppe_net", "property_plant_and_equipment_net"),
        # ADDED 2026-09-17 (ppe_net cluster follow-up): WRN, IFRS mining-explorer equivalent
        # of the THM/PZG MineralPropertiesNet pattern above - see this pair's own comment on
        # utils/external/sec_balance_sheet.py's concept-fetch list (search
        # "AssetsArisingFromExplorationForAndEvaluationOfMineralResources") for the live
        # companyfacts evidence.
        ("ppe_net", "assets_arising_from_exploration_for_and_evaluation_of_mineral_resources"),
        # ADDED 2026-09-17 (ppe_net cluster follow-up): NVA (Nova Minerals Corp, CIK
        # 0001852551), IFRS's alternate taxonomy name for the same pre-production mineral-
        # exploration concept - see utils/external/sec_balance_sheet.py's concept-fetch list
        # (search "TangibleExplorationAndEvaluationAssets") for the live companyfacts evidence.
        ("ppe_net", "tangible_exploration_and_evaluation_assets"),
        # ADDED 2026-09-19 (goal: data-quality-issue reduction, NVA capex live-confirmed):
        # cash-flow sibling of the ppe_net pair immediately above, same filer (NVA, Nova
        # Minerals Corp, CIK 1852551) and same root shape as the oil-and-gas capex pairs
        # further up this set - "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvesting
        # Activities" (a small, genuine equipment-purchase line, AUD 1,055,878 FY2022) and
        # "PurchaseOfExplorationAndEvaluationAssets" (the dominant real capex line for a
        # pre-production explorer, AUD 24,799,177 FY2022) both mapped onto the same "capex"
        # db_field, so ordinary last-listed-wins silently discarded the dominant exploration
        # figure and left capex stuck at the equipment-only value - understating NVA's real
        # capex by ~24x (matching xbrl_yfinance_line_item_report's flagged "our value 25-100x
        # smaller than yfinance"). Summed: AUD 25,855,055, consistent with the same
        # AUD->USD conversion already validated for this filer's ppe_net pair above.
        ("capex", "purchase_of_exploration_and_evaluation_assets"),
        # Reverse direction of the pair immediately above - REQUIRED, not redundant: this
        # file's is_additive_concept_pair() does an exact (db_field, sec_field) tuple
        # lookup with no automatic reciprocity (same convention as the ppe_net pair's own
        # "property_plant_and_equipment_net" entry earlier in this set). NVA's real fetch
        # order processes the ifrs_aliases-sourced exploration concept BEFORE the
        # concepts-list-sourced PP&E concept (live-confirmed via direct get_cash_flow()
        # call: exploration key precedes payments_to_acquire_property_plant_and_equipment
        # in the raw row's insertion order) - without this entry, PP&E processed second
        # unconditionally overwrote the already-set exploration value via ordinary
        # last-listed-wins, silently discarding the dominant figure instead of summing.
        ("capex", "payments_to_acquire_property_plant_and_equipment"),
        # ADDED 2026-09-17 (goal: xbrl_yfinance_line_item_report remediation follow-up): RAVE
        # (Rave Restaurant Group) FY2022 (period 2021-06-28 to 2022-06-26) live-confirmed via
        # real SEC companyfacts JSON: real, nonzero "CostOfRevenue" ($1,000, an immaterial
        # non-franchise cost) AND real "FranchisorCosts" ($3,284,000) both tagged for the SAME
        # fiscal year, summing to $3,285,000 - an EXACT match to yfinance's flagged value.
        # Unlike this set's other pairs, "franchisor_costs" is fallback-only (see
        # financial_statements_income_config.py's own comment on it), so sec_base.py's
        # transform() needs its own explicit is_additive_concept_pair exception inside the
        # fallback-only skip block for this pair specifically - see that call site's own
        # comment.
        ("cost_of_revenue", "franchisor_costs"),
        # ADDED 2026-09-17 (goal: xbrl_yfinance_line_item_report remediation follow-up, top-
        # cluster sweep): ACIW (ACI Worldwide, CIK 0000935036) live-confirmed via real SEC
        # companyfacts JSON across all 4 fiscal years present in xbrl_yfinance_line_item_report -
        # a real, nonzero "PaymentsToAcquirePropertyPlantAndEquipment" (physical capex) AND a
        # real, nonzero "PaymentsToAcquireSoftware" (capitalized software development costs)
        # both tagged every fiscal year, two genuinely distinct, non-overlapping investing-
        # activity cash-flow line items for a software company - not alternates. EXACT match to
        # yfinance's flagged value only when summed (not either alone):
        #   FY2022: PP&E $13,103,000 + Software $26,790,000 = $39,893,000 (yfinance-flagged
        #           $39,893,000, exact)
        #   FY2023: $8,924,000 + $28,853,000 = $37,777,000 (yfinance-flagged $37,777,000, exact)
        #   FY2024: $15,402,000 + $29,649,000 = $45,051,000 (yfinance-flagged $45,051,000, exact)
        #   FY2025: $12,907,000 + $20,445,000 = $33,352,000 (yfinance-flagged $33,352,000, exact)
        # Before this fix, our stored capex for every one of these years was exactly the PP&E
        # figure alone (e.g. FY2022 $13,103,000) - PaymentsToAcquireSoftware never wrote,
        # because "payments_to_acquire_software" is fallback-only (added 2026-09-10 for TALK,
        # which reports ONLY software capex with no PP&E concept at all - a genuine either/or
        # case for that filer) and PaymentsToAcquirePropertyPlantAndEquipment is the plain,
        # always-fetched-first standard concept, so the ordinary "db_field in row" fallback
        # guard permanently blocked the software figure once PP&E had already written. Same
        # "fallback-only second component of a known-additive pair" shape as
        # cost_of_revenue/franchisor_costs above - needs the same sec_base.py transform()
        # exception inside the fallback-only skip block.
        ("capex", "payments_to_acquire_software"),
        # ADDED 2026-09-17 (xbrl_yfinance_line_item_report accounts_receivable cluster
        # follow-up): HGTY (Hagerty, Inc., CIK 0001840776, an insurance MGA) live-confirmed
        # via real SEC companyfacts JSON, every fiscal year present in
        # xbrl_yfinance_line_item_report: a real, distinct "PremiumsReceivableAtCarryingValue"
        # fact ADDITIVE to plain "AccountsReceivableNetCurrent" - FY2022: $58,255,000 +
        # $100,700,000 = $158,955,000, an EXACT match to yfinance's flagged value. Insurance-
        # specific premiums receivable is a genuinely separate balance-sheet component, not an
        # alternate concept for ordinary trade AR.
        ("accounts_receivable", "premiums_receivable_at_carrying_value"),
        # ADDED 2026-09-17 (cash_and_equivalents cluster follow-up): ABCB (Ameris Bancorp,
        # CIK 0000351569) live-confirmed via real SEC companyfacts JSON, every fiscal year in
        # xbrl_yfinance_line_item_report - CashAndDueFromBanks (a bank's non-interest-bearing
        # vault/till cash) + InterestBearingDepositsInBanks (its interest-bearing deposits at
        # other banks) are two genuinely distinct, simultaneously-real components of a bank's
        # total cash, not alternates:
        #   FY2022: $284,567,000 + $833,565,000 = $1,118,132,000 (exact yfinance match)
        # Before this fix, our stored cash_and_equivalents for every one of these years was
        # exactly CashAndDueFromBanks alone - InterestBearingDepositsInBanks was never fetched
        # at all. See utils/external/sec_balance_sheet.py's concept-fetch list comment (search
        # "InterestBearingDepositsInBanks") for the full evidence.
        ("cash_and_equivalents", "interest_bearing_deposits_in_banks"),
    }
)


# RAVE's cost_of_revenue/franchisor_costs pair (see ADDITIVE_CONCEPT_PAIRS' own comment above)
# is different in kind from this set's other pairs: those (CRGY's O&G capex split, TITN's
# interest_expense_other, THM/PZG/RRC/HPK's ppe_net) are additive regardless of which side is
# larger - both are always genuinely present, non-overlapping components of a filer's real
# total. franchisor_costs is different: a franchisor's PLAIN "CostOfRevenue" tag is only ever
# a genuinely additive immaterial sliver (RAVE FY2022's own $1,000) when franchisor_costs is
# the dominant, much larger figure - live-confirmed via real SEC companyfacts JSON. When a
# filer's plain "cost_of_revenue" is ITSELF the large, real total (an ordinary non-franchisor
# filer with a small/placeholder franchisor_costs value, or none at all), summing would double
# count and silently inflate an already-correct total - the exact
# test_never_overwrites_a_real_cost_of_revenue_value invariant
# test_dividends_paid_and_cost_of_revenue_full_scan_20260916.py already enforces. Gated to
# require the incoming franchisor_costs value be the dominant (larger) one, matching RAVE's own
# live shape ($3,284,000 incoming vs. $1,000 existing) and preserving that invariant.
#
# ADDED 2026-09-17 (same follow-up sweep): capex/payments_to_acquire_software needs the same
# gate for the identical reason - test_never_overwrites_a_real_ppe_capex_value
# (test_talk_payments_to_acquire_software_capex_fallback_20260910.py, AAON fixture:
# PP&E=$195,700,000 existing, software=$1.0 incoming) caught this live: without the gate,
# ADDITIVE_CONCEPT_PAIRS summed unconditionally and corrupted an already-correct large PP&E
# total with a trivial/placeholder software figure. ACIW's own live data (this pair's
# justifying evidence, see ADDITIVE_CONCEPT_PAIRS' comment above) still passes the gate in
# every one of its 4 fiscal years - software is the LARGER figure vs. PP&E every year
# (FY2022 $26.79M > $13.1M, FY2023 $28.853M > $8.924M, FY2024 $29.649M > $15.402M, FY2025
# $20.445M > $12.907M) - so this doesn't weaken the ACIW fix, it just excludes the
# AAON-shape case the fix was never meant to cover.
_ADDITIVE_PAIRS_REQUIRING_DOMINANT_INCOMING = frozenset(
    {
        ("cost_of_revenue", "franchisor_costs"),
        ("capex", "payments_to_acquire_software"),
    }
)


def is_additive_concept_pair(db_field: str, sec_field: str, existing: Any, value: Any) -> bool:
    """True if `sec_field` is a known-additive component for `db_field` (see
    ADDITIVE_CONCEPT_PAIRS) and both the already-resolved `existing` value and the incoming
    `value` are real numbers - i.e. this is a genuine sum-instead-of-overwrite case, not a
    first write. For pairs in _ADDITIVE_PAIRS_REQUIRING_DOMINANT_INCOMING (see that set's own
    comment - currently just RAVE's cost_of_revenue/franchisor_costs), also requires the
    incoming `value` to be larger than `existing`, so an already-resolved real total (this
    concept's genuinely-alternate use for an ordinary non-franchisor filer) is never
    double-counted.

    FIXED 2026-09-17 (ppe_net cluster follow-up, ADT live-confirmed via real SEC companyfacts
    JSON): ADDITIVE_CONCEPT_PAIRS includes ("ppe_net", "property_plant_and_equipment_net")
    itself - meaning the plain standard concept is one of its own pair's two components, since
    the mining/O&G siblings (mineral_properties_net etc.) also map here. But sec_base.py's raw
    `rows` input can legitimately contain the SAME sec_field's identical fact more than once
    for the same fiscal year (e.g. a 10-K and a later 10-Q both reporting the same period-end
    comparative balance) - when that happens `existing` and `value` are the exact same number,
    and unconditionally summing doubled it (ADT FY2024: SEC PropertyPlantAndEquipmentNet
    $247,183,000 reported identically twice -> stored 494,366,000, exactly 2x; FY2025 same
    shape, $243,398,000 -> 486,796,000). A genuine second additive component (a different
    concept, e.g. THM's MineralPropertiesNet $55,375,124 + PropertyPlantAndEquipmentNet
    $7,465) essentially never coincides in value with what's already stored, so treating an
    exact match as "duplicate re-report of the same fact, not a second component" and skipping
    the sum is a safe, low-risk discriminator that doesn't require plumbing per-db_field
    source-concept identity through the whole transform() call chain.
    """
    if (db_field, sec_field) not in ADDITIVE_CONCEPT_PAIRS:
        return False
    if not (isinstance(existing, (int, float, Decimal)) and isinstance(value, (int, float, Decimal))):
        return False
    if float(existing) == float(value):
        return False
    if (db_field, sec_field) in _ADDITIVE_PAIRS_REQUIRING_DOMINANT_INCOMING:
        return float(value) > float(existing)
    return True


# ADDED 2026-09-17 (goal: data-coverage-metrics accuracy sweep, xbrl_yfinance_line_item_report
# long_term_debt audit): live-confirmed via real SEC companyfacts JSON for DPZ, MAR, BALL, PPC,
# LNTH, CRL - each still tags a real, nonzero plain "LongTermDebt" fact (the standard concept,
# NOT fallback-only, so _fallback_only_fields' "db_field in row" skip always protects it) that
# has become an immaterial single note/instrument, while the filer's real total debt moved
# years ago to one of these combined concepts (the same taxonomy-switch shape already fixed for
# ADC/CAT/SLB/XOM's DIFFERENT fallback concepts, just via a DIFFERENT concept family that a
# real, present "LongTermDebt" tag was blocking outright rather than merely being absent).
# DPZ FY2025: plain LongTermDebt=$14.6M (a real but minor note) vs
# LongTermDebtAndCapitalLeaseObligations=$4,810,683,000 - EXACT match to yfinance's flagged
# value. MAR FY2025: $23M vs $14,995,000,000 (exact yfinance match). BALL/PPC/LNTH: same shape,
# exact yfinance matches. CRL FY2025: $166K vs $2,136,360,000 (yfinance $2,111,712,000, same
# order of magnitude - not exact, plausibly a different point-in-time snapshot, but the stored
# $166K is unambiguously wrong regardless).
_COMBINED_DEBT_TOTAL_CONCEPTS = frozenset(
    {
        "long_term_debt_and_capital_lease_obligations",
        "long_term_debt_and_capital_lease_obligations_including_current_maturities",
        "debt_and_capital_lease_obligations",
    }
)

# A real total can be legitimately many multiples of one narrow instrument it subsumes (DPZ's
# is ~330x) - ordinary filer-to-filer noise in a genuinely small-but-real total debt load
# would never approach this magnitude, so a high multiplier keeps this from firing on filers
# where the plain concept really is closely tracking the truth (e.g. a modest gap from a
# single additional bond issuance).
_COMBINED_DEBT_TOTAL_MIN_MULTIPLE = 5


def is_narrow_standard_debt_blocking_combined_total(
    db_field: str, sec_field: str, existing: Any, value: Any, existing_source_sec_field: str | None
) -> bool:
    """True if `value` (an incoming _COMBINED_DEBT_TOTAL_CONCEPTS concept) should override
    `existing` (long_term_debt's currently-stored value) despite `_fallback_only_fields`
    normally protecting any already-populated field - see this module's docstring above for
    the live DPZ/MAR/BALL/PPC/LNTH/CRL evidence this closes.

    Handles the case where dict/concept-fetch order happens to process the plain
    "long_term_debt" concept BEFORE the combined-total concept for a given row (the combined
    concept is fallback-only, so `_fallback_only_fields`'s ordinary "db_field in row" skip
    would otherwise protect the smaller, already-written value). See
    is_immaterial_standard_debt_overwriting_combined_total below for the mirror-image case
    (combined concept processed first, then the plain concept unconditionally overwrites it
    on its own turn since it isn't fallback-gated at all) - live-confirmed this is actually
    the ordering that fires for DPZ/MAR/BALL/PPC/LNTH/CRL, since sec_balance_sheet.py's own
    concept-fetch list lists the combined concepts BEFORE "LongTermDebt". Both guards are
    needed since concept/dict ordering isn't a stable contract to rely on.

    Deliberately narrow: only fires when (1) db_field is long_term_debt, (2) the incoming
    concept is a known combined-total concept (a structural superset of plain LongTermDebt,
    not an unrelated sibling instrument), (3) the field's current value came specifically from
    the plain "long_term_debt" standard concept itself (not an earlier fallback concept that
    already legitimately won a prior priority contest - this guard is only about the
    standard-concept-always-wins default being wrong, not about re-litigating fallback-vs-
    fallback ordering), and (4) the incoming value is at least
    _COMBINED_DEBT_TOTAL_MIN_MULTIPLE times larger, so this can't fire on ordinary noise.
    """
    return (
        db_field == "long_term_debt"
        and sec_field in _COMBINED_DEBT_TOTAL_CONCEPTS
        and existing_source_sec_field == "long_term_debt"
        and isinstance(existing, (int, float, Decimal))
        and float(existing) > 0
        and isinstance(value, (int, float, Decimal))
        and float(value) >= float(existing) * _COMBINED_DEBT_TOTAL_MIN_MULTIPLE
    )


# ADDED 2026-09-17 (goal: xbrl_yfinance_line_item_report remediation follow-up, verifying a
# prior agent's ZERO_FIRST_WRITE_GUARD_FIELDS "interest_expense" entry): live-confirmed via
# real SEC companyfacts JSON that TITN's FY2025 (period 2024-02-01 to 2025-01-31) case is NOT
# the zero-blocking shape that entry's docstring describes (that entry covers FY2026, where
# InterestAndDebtExpense really is $0) - for FY2025, InterestAndDebtExpense is a real, NONZERO
# $9,650,000 (a genuinely different, much smaller line item for this filer, not the total),
# while FinancingInterestExpense for the same period is $34,710,000 - both real facts, so
# is_zero_first_write_blocking_field's exact-zero check never fires and
# `_fallback_only_fields`'s ordinary "db_field in row" skip protects whichever one processed
# first (interest_and_debt_expense, per financial_statements_income_config.py's concept-list
# order), permanently blocking financing_interest_expense from ever writing. Before this
# session's fix, stored interest_expense was $9,650,000 + InterestExpenseOther's $15,105,000 =
# $24,755,000 (matches the pre-fix xbrl_yfinance_line_item_report row exactly) vs.
# yfinance-flagged $53,993,000 (ratio 0.458, divergent). After the fix,
# $34,710,000 + $15,105,000 = $49,815,000 (ratio to yfinance ~0.923, no longer divergent under
# xbrl_yfinance_crosscheck.py's 2x/0.5x threshold - the residual ~$4.18M gap is plausibly
# FinanceLeaseInterestExpense, $2,419,000 for this same period, which yfinance's aggregate
# appears to fold in and this loader does not separately map to interest_expense; same
# "unambiguously more correct, not necessarily bit-exact" acceptance already used for CRL's
# long_term_debt fix above).
#
# Deliberately narrow, same "large, evidence-based multiple, not ordinary noise" shape as the
# combined-debt-total guards above: EPAC (Enerpac, see financial_statements_income_config.py's
# own "financing_interest_expense" comment) is the one other live-confirmed filer where both
# concepts co-occur with real nonzero values for the same period - EPAC FY2012 (period
# 2011-09-01/2012-08-31): InterestAndDebtExpense=$16,830,000 vs.
# FinancingInterestExpense=$29,561,000, a ratio of only ~1.76x, and that ordering (
# InterestAndDebtExpense wins) is EPAC's documented-correct behavior, not a bug - EPAC's
# InterestAndDebtExpense IS its real total there. TITN's FY2025 ratio is ~3.60x. The multiple
# below sits between the two so it fires for TITN without disturbing EPAC.
_INTEREST_EXPENSE_NARROW_MIN_MULTIPLE = 3


def is_financing_interest_expense_overriding_narrow_interest_and_debt_expense(
    db_field: str, sec_field: str, existing: Any, value: Any, existing_source_sec_field: str | None
) -> bool:
    """True if `value` (an incoming "financing_interest_expense" concept write) should
    override `existing` (interest_expense's currently-stored value, sourced from the
    "interest_and_debt_expense" concept) despite `_fallback_only_fields` normally protecting
    any already-populated field - see this function's own module-level comment above for the
    live TITN FY2025 evidence this closes and the EPAC evidence it deliberately does not
    disturb.

    Mirrors is_narrow_standard_debt_blocking_combined_total's shape: only fires when (1)
    db_field is interest_expense, (2) the incoming concept is specifically
    financing_interest_expense, (3) the field's current value came specifically from the
    "interest_and_debt_expense" concept (not some other already-resolved fallback that won a
    prior, unrelated priority contest), and (4) the incoming value is at least
    _INTEREST_EXPENSE_NARROW_MIN_MULTIPLE times larger, so ordinary filer-to-filer noise (like
    EPAC's ~1.76x gap) can't fire this.
    """
    return (
        db_field == "interest_expense"
        and sec_field == "financing_interest_expense"
        and existing_source_sec_field == "interest_and_debt_expense"
        and isinstance(existing, (int, float, Decimal))
        and float(existing) > 0
        and isinstance(value, (int, float, Decimal))
        and float(value) >= float(existing) * _INTEREST_EXPENSE_NARROW_MIN_MULTIPLE
    )


# ADDED 2026-09-17 (goal: xbrl_yfinance_line_item_report remediation follow-up, verifying a
# prior agent's ZERO_FIRST_WRITE_GUARD_FIELDS "accounts_receivable" entry): PED (PEDEVCO Corp)
# FY2023 (period end 2023-12-31) and FY2024 (period end 2024-12-31) live-confirmed via real SEC
# companyfacts JSON: "ReceivablesNetCurrent" is a real, NONZERO but immaterial value ($42,000
# FY2023, $293,000 FY2024 - some narrow receivable slice, not PED's real total) that gets
# processed before the real, much larger "AccountsReceivableNet" ($5,790,000 FY2023,
# $7,995,000 FY2024 - EXACT matches to the yfinance-flagged values for both years). Neither
# blocking value is exactly $0, so is_zero_first_write_blocking_field never fires, and
# `_fallback_only_fields`'s ordinary "db_field in row" skip protects the tiny
# ReceivablesNetCurrent value from ever being overridden. FY2023 ratio ~137.9x, FY2024 ratio
# ~27.3x - both dramatically larger than any plausible ordinary noise, so a magnitude floor
# well below either actual ratio safely distinguishes this from a legitimate close contest.
_ACCOUNTS_RECEIVABLE_NARROW_MIN_MULTIPLE = 5

_ACCOUNTS_RECEIVABLE_OVERRIDE_CONCEPTS = frozenset(
    {
        "accounts_receivable_net",
        "accounts_and_other_receivables_net_current",
    }
)


def is_accounts_receivable_net_overriding_narrow_receivables_net_current(
    db_field: str, sec_field: str, existing: Any, value: Any, existing_source_sec_field: str | None
) -> bool:
    """True if `value` (an incoming real AccountsReceivableNet-family concept write) should
    override `existing` (accounts_receivable's currently-stored value, sourced from the
    narrower "receivables_net_current" concept) - see this function's own module-level comment
    above for the live PED FY2023/FY2024 evidence this closes.

    Same shape as is_narrow_standard_debt_blocking_combined_total: only fires when (1) db_field
    is accounts_receivable, (2) the incoming concept is a known broader receivables concept,
    (3) the field's current value came specifically from "receivables_net_current" (not some
    other already-resolved fallback that won a prior, unrelated priority contest), and (4) the
    incoming value is at least _ACCOUNTS_RECEIVABLE_NARROW_MIN_MULTIPLE times larger.
    """
    return (
        db_field == "accounts_receivable"
        and sec_field in _ACCOUNTS_RECEIVABLE_OVERRIDE_CONCEPTS
        and existing_source_sec_field == "receivables_net_current"
        and isinstance(existing, (int, float, Decimal))
        and float(existing) > 0
        and isinstance(value, (int, float, Decimal))
        and float(value) >= float(existing) * _ACCOUNTS_RECEIVABLE_NARROW_MIN_MULTIPLE
    )


# ADDED 2026-09-17 (goal: xbrl_yfinance_line_item_report remediation follow-up): DTST (Data
# Storage Corp) FY2021 (period 2021-01-01 to 2021-12-31) live-confirmed via real SEC
# companyfacts JSON: the bare "Dividends" concept really is $0 that fiscal year (already
# correctly unblocked by the existing "dividends_paid" ZERO_FIRST_WRITE_GUARD_FIELDS entry -
# not the bug here), but "DividendsPreferredStock" then writes a real, NONZERO $63,683 (a
# genuinely different, narrower preferred-distribution line item, not DTST's total), which
# permanently blocks the later, real, much larger "DividendsShareBasedCompensationCash"
# ($1,179,357 - the value financial_statements_cashflow_config.py's own "dividends_share_based_
# compensation_cash" comment already documents as the exact yfinance match for this filer/year)
# from ever being written - neither value is exactly $0, so the zero-first-write guard doesn't
# apply, and dividends_preferred_stock is fallback-only, listed before dividends_share_based_
# compensation_cash, so the ordinary "db_field in row" skip protects it. Ratio ~18.5x - well
# above ordinary noise.
_DIVIDENDS_SHARE_BASED_COMP_MIN_MULTIPLE = 5

_NARROW_PREFERRED_DIVIDEND_CONCEPTS = frozenset(
    {
        "dividends_preferred_stock",
        "dividends_preferred_stock_cash",
    }
)


def is_share_based_comp_dividends_overriding_narrow_preferred_stock_dividends(
    db_field: str, sec_field: str, existing: Any, value: Any, existing_source_sec_field: str | None
) -> bool:
    """True if `value` (an incoming real DividendsShareBasedCompensationCash write) should
    override `existing` (dividends_paid's currently-stored value, sourced from one of the
    narrower preferred-stock dividend concepts) - see this function's own module-level comment
    above for the live DTST FY2021 evidence this closes.

    Deliberately narrow to this one specific concept pairing (not a general "share-based-comp
    dividends always win" rule): only fires when (1) db_field is dividends_paid, (2) the
    incoming concept is specifically dividends_share_based_compensation_cash, (3) the field's
    current value came from one of the narrow preferred-stock dividend concepts (not an
    already-resolved common-stock/total dividend concept - those must keep winning normally,
    per this module's own dividends_preferred_stock* comments), and (4) the incoming value is
    at least _DIVIDENDS_SHARE_BASED_COMP_MIN_MULTIPLE times larger.
    """
    return (
        db_field == "dividends_paid"
        and sec_field == "dividends_share_based_compensation_cash"
        and existing_source_sec_field in _NARROW_PREFERRED_DIVIDEND_CONCEPTS
        and isinstance(existing, (int, float, Decimal))
        and float(existing) > 0
        and isinstance(value, (int, float, Decimal))
        and float(value) >= float(existing) * _DIVIDENDS_SHARE_BASED_COMP_MIN_MULTIPLE
    )


# ADDED 2026-09-17 (goal: xbrl_yfinance_line_item_report remediation follow-up, top-cluster
# sweep): ABCB (Ameris Bancorp, CIK 0000351569) live-confirmed via real SEC companyfacts
# JSON across all 4 fiscal years present in xbrl_yfinance_line_item_report - a genuine
# systematic bug, not per-filer noise. utils/external/sec_balance_sheet.py's own
# concept-fetch list already documents this exact shape as a known, accepted limitation
# (see its "IBOC/HBT... two genuinely distinct real instruments... accepted as strictly
# better than the current not itemized NULL, same single-figure-not-perfect-sum
# convention" comment) - written before ADDITIVE_CONCEPT_PAIRS/is_additive_concept_pair
# existed as a summing mechanism. Both concepts are fallback-only (first-populated-wins),
# "SubordinatedDebt" listed BEFORE "OtherBorrowings" in that fetch list, so for a filer
# reporting both, SubordinatedDebt permanently wins the long_term_debt slot and
# OtherBorrowings - the filer's real, and usually much larger, other real borrowed-funds
# instrument (FHLB advances, repos, etc.) - never gets a chance to write at all.
#
# Live SEC data for ABCB, every fiscal year on file in xbrl_yfinance_line_item_report,
# EXACTLY matches yfinance's flagged value only when BOTH concepts are summed (not either
# alone):
#   FY2022: SubordinatedDebt $128,322,000 + OtherBorrowings $1,875,736,000 = $2,004,058,000
#           (yfinance-flagged $2,004,058,000, exact)
#   FY2023: $130,315,000 + $509,586,000 = $639,901,000 (yfinance-flagged $639,901,000, exact)
#   FY2024: $132,309,000 + $291,788,000 = $424,097,000 (yfinance-flagged $424,097,000, exact)
#   FY2025: $134,302,000 + $558,039,000 = $692,341,000 (yfinance-flagged $692,341,000, exact)
# Before this fix, our stored long_term_debt for every one of these years was exactly
# SubordinatedDebt alone (e.g. FY2022 $128,322,000) - OtherBorrowings never wrote.
#
# Deliberately narrow (unlike the general ADDITIVE_CONCEPT_PAIRS mechanism, which doesn't
# gate on which concept the existing value came from): only fires when the field's current
# value came specifically from one of the subordinated-debt/trust-preferred family concepts
# (not some other already-resolved fallback, e.g. a combined-debt-total concept, that
# legitimately represents a filer's COMPLETE debt already and would be double-counted by
# adding OtherBorrowings on top) - same "gate on existing_source_sec_field" discipline as
# is_narrow_standard_debt_blocking_combined_total and its siblings above, chosen because
# OtherBorrowings is documented elsewhere in this codebase (FFIN, see
# sec_balance_sheet.py's own "OtherBorrowings" comment) as sometimes a filer's ENTIRE real
# debt figure on its own, not always an additive component - summing it against every kind
# of pre-existing value would risk double-counting for filers where it (or something else)
# is already the complete total.
_SUBORDINATED_DEBT_FAMILY_CONCEPTS = frozenset(
    {
        "subordinated_debt",
        "junior_subordinated_debenture_owed_to_unconsolidated_subsidiary_trust",
    }
)


def is_other_borrowings_additive_to_subordinated_debt(
    db_field: str, sec_field: str, existing: Any, value: Any, existing_source_sec_field: str | None
) -> bool:
    """True if `value` (an incoming "other_borrowings" concept write) should be SUMMED with
    `existing` (long_term_debt's currently-stored value, sourced from one of the
    subordinated-debt/trust-preferred family concepts) rather than being blocked outright by
    `_fallback_only_fields`'s ordinary "db_field in row" skip - see this module's own
    docstring above for the live ABCB evidence this closes.

    Only fires when (1) db_field is long_term_debt, (2) the incoming concept is specifically
    other_borrowings, (3) the field's current value came from one of
    _SUBORDINATED_DEBT_FAMILY_CONCEPTS (not some other already-resolved fallback that may
    already represent a complete total), and (4) both existing and incoming values are real,
    positive numbers - genuinely distinct, simultaneously-outstanding instruments, not a
    first write or a zero-blocking case (those are handled by the guards above).
    """
    return (
        db_field == "long_term_debt"
        and sec_field == "other_borrowings"
        and existing_source_sec_field in _SUBORDINATED_DEBT_FAMILY_CONCEPTS
        and isinstance(existing, (int, float, Decimal))
        and float(existing) > 0
        and isinstance(value, (int, float, Decimal))
        and float(value) > 0
    )


def is_immaterial_standard_debt_overwriting_combined_total(
    db_field: str, sec_field: str, existing: Any, value: Any, existing_source_sec_field: str | None
) -> bool:
    """True if `value` (an incoming plain "long_term_debt" concept write) should be REJECTED
    to protect `existing` (long_term_debt's currently-stored value, already resolved from a
    _COMBINED_DEBT_TOTAL_CONCEPTS concept) - the actual live-confirmed failure mode for DPZ/
    MAR/BALL/PPC/LNTH/CRL: sec_balance_sheet.py's concept-fetch list lists the combined
    concepts BEFORE "LongTermDebt" specifically so the plain concept (processed later) can win
    a normal, legitimate priority contest - but "LongTermDebt" is not fallback-gated at all,
    so it unconditionally overwrote even a MUCH LARGER already-resolved combined total when
    its own real value was actually just one immaterial sub-instrument, not the filer's real
    total debt. DPZ FY2025: combined concept wrote $4,810,683,000 first (matches yfinance
    exactly), then plain LongTermDebt's own real-but-tiny $14,600,000 unconditionally
    overwrote it via ordinary last-listed-wins.

    Deliberately narrow, same magnitude floor as the sibling guard above: only fires when the
    incoming plain-concept value is smaller than the existing combined-total value by at least
    _COMBINED_DEBT_TOTAL_MIN_MULTIPLE - an ordinary, more-precise plain LongTermDebt update
    that's merely somewhat smaller (e.g. after a real debt paydown) still wins normally.
    """
    return (
        db_field == "long_term_debt"
        and sec_field == "long_term_debt"
        and existing_source_sec_field in _COMBINED_DEBT_TOTAL_CONCEPTS
        and isinstance(existing, (int, float, Decimal))
        and float(existing) > 0
        and isinstance(value, (int, float, Decimal))
        and float(value) > 0
        and float(existing) >= float(value) * _COMBINED_DEBT_TOTAL_MIN_MULTIPLE
    )


# ADDED 2026-09-18 (goal session, data-issue reduction, GM live-confirmed via real SEC
# companyfacts JSON): same shape as is_immaterial_standard_debt_overwriting_combined_total
# above, for amortization_expense instead of long_term_debt. sec_income_statement.py's
# concept-fetch list lists "DepreciationDepletionAndAmortization" (a real COMBINED
# depreciation+amortization total) BEFORE "AmortizationOfIntangibleAssets" specifically so the
# more-precise plain concept (processed later) can normally win - but AmortizationOfIntangible
# Assets is not fallback-gated, so for a filer like GM whose intangible-amortization is a small,
# genuinely separate sub-item ($146,000,000 FY2024) it unconditionally overwrote the much
# larger, already-resolved combined DD&A total ($11,456,000,000 FY2024) instead of losing to it
# as intended. Reusing _COMBINED_DEBT_TOTAL_MIN_MULTIPLE (5x) - same "can't fire on ordinary
# noise" reasoning as the debt guards.
_DDA_COMBINED_TOTAL_SOURCE_CONCEPTS = frozenset({"depreciation_depletion_and_amortization"})


def is_narrow_intangible_amortization_overwriting_combined_dda(
    db_field: str, sec_field: str, existing: Any, value: Any, existing_source_sec_field: str | None
) -> bool:
    """True if `value` (an incoming plain intangible-amortization concept write) should be
    REJECTED to protect `existing` (amortization_expense's currently-stored value, already
    resolved from a combined DepreciationDepletionAndAmortization total) - see this function's
    own module comment above for the live GM evidence. Deliberately narrow: only fires when the
    incoming value is smaller than the existing combined total by at least the same 5x
    magnitude floor the debt-guard siblings use, so an ordinary, more-precise intangible-
    amortization update that's merely somewhat smaller still wins normally.
    """
    return (
        db_field == "amortization_expense"
        and sec_field in ("amortization_of_intangible_assets", "amortization_of_intangibles")
        and existing_source_sec_field in _DDA_COMBINED_TOTAL_SOURCE_CONCEPTS
        and isinstance(existing, (int, float, Decimal))
        and float(existing) > 0
        and isinstance(value, (int, float, Decimal))
        and float(value) > 0
        and float(existing) >= float(value) * _COMBINED_DEBT_TOTAL_MIN_MULTIPLE
    )


# ADDED 2026-09-17 (goal: xbrl_yfinance_line_item_report remediation follow-up, AVA live-
# confirmed via real SEC companyfacts JSON, CIK 0000104918): Avista Corp, a regulated
# electric/gas utility (NOT a REIT - redirect_secured_debt_for_reit above never fires for it),
# stopped tagging "LongTermDebtNoncurrent" after FY2022 (last real fact 2022-12-31:
# $2,281,013,000) and "LongTermDebtCurrent" after FY2023 ($15,000,000); its real, ongoing
# first-mortgage-bond debt is tagged exclusively under "SecuredDebt" from then on
# ($2,619,000,000 FY2024, $2,759,000,000 FY2025), tracking total_assets growth ($7.70B ->
# $8.36B) the way a utility's real long-term mortgage-bond book should - not a short-term
# instrument the way this loader's default secured_debt -> short_term_debt mapping (added on
# DE's evidence, see redirect_secured_debt_for_reit's own docstring) assumes. Without a
# redirect, AVA's long_term_debt fell through to whatever smaller fallback concept (e.g.
# LineOfCredit, fetched later in sec_balance_sheet.py's concept list) happened to claim the
# slot instead - live-confirmed $3,000,000 stored for FY2025 vs SecuredDebt's real
# $2,759,000,000.
#
# Deliberately narrow to this one live-confirmed symbol, not a general utility-SIC-code rule:
# SecuredDebt's real-world meaning varies by filer (DE's own SecuredDebt genuinely is a small
# short-term-debt-adjacent sibling of DebtCurrent), so a blanket redirect risks reproducing
# DE's false-positive case for some other utility this session hasn't individually verified.
_UTILITY_SECURED_DEBT_LONG_TERM_SYMBOLS = frozenset({"AVA"})


def redirect_secured_debt_for_utility_long_term_financing(sec_field: str, db_field: str, symbol: str | None) -> str:
    """Mirrors redirect_secured_debt_for_reit's shape for the one live-confirmed non-REIT case
    (AVA) where SecuredDebt is genuinely a filer's real long-term financing rather than a
    short-term instrument - see _UTILITY_SECURED_DEBT_LONG_TERM_SYMBOLS' own comment above for
    the live evidence this closes. Returns db_field unchanged for every other symbol.
    """
    if (
        sec_field == "secured_debt"
        and db_field == "short_term_debt"
        and symbol in _UTILITY_SECURED_DEBT_LONG_TERM_SYMBOLS
    ):
        return "long_term_debt"
    return db_field


# ADDED 2026-09-18 (goal session, xbrl_yfinance_line_item_report short_term_debt remediation):
# WVVI (Willamette Valley Vineyards) live-confirmed via its own filed SEC calculation linkbase
# (FY2023/2024/2025 10-Ks): "LineOfCredit" is declared as a direct child of the
# "LiabilitiesCurrent" calculation total in every one of these filings, not "Liabilities" -
# meaning the filer itself classifies this facility as CURRENT debt on its own balance sheet.
# `financial_statements_balance_config.py`'s blanket `"line_of_credit": "long_term_debt"`
# mapping (added for the common case where a filer's revolver is genuinely long-term financing,
# or where an unclassified balance sheet has no current/noncurrent split at all - see the many
# symbols confirmed as "rolls up under total Liabilities" in this same review pass) is wrong
# for this filer specifically. Confirmed live: WVVI's real short_term_debt was understated by
# roughly the size of its LineOfCredit balance every year (our stored value ~$0.9-1.2M vs
# yfinance's ~$1.9-5.0M, tracking the LineOfCredit facility's own growth).
#
# Deliberately narrow to this one live-confirmed symbol via calculation-linkbase evidence, not
# a general rule - most filers checked in this same pass have LineOfCredit rolling up under
# total Liabilities (no split) or under long-term financing, so a blanket current-classification
# rule would misclassify those.
_LINE_OF_CREDIT_CURRENT_SYMBOLS = frozenset({"WVVI"})


def redirect_line_of_credit_for_current_classification(sec_field: str, db_field: str, symbol: str | None) -> str:
    """Mirrors redirect_secured_debt_for_reit's shape for the one live-confirmed filer (WVVI)
    whose own calculation linkbase declares LineOfCredit as a child of LiabilitiesCurrent -
    see _LINE_OF_CREDIT_CURRENT_SYMBOLS' own comment above. Returns db_field unchanged for
    every other symbol (the default long_term_debt mapping is correct or ambiguous-but-
    unclassified for everyone else checked)."""
    if sec_field == "line_of_credit" and db_field == "long_term_debt" and symbol in _LINE_OF_CREDIT_CURRENT_SYMBOLS:
        return "short_term_debt"
    return db_field


# ADDED 2026-09-18 (goal session, WVVI short_term_debt investigation - direct follow-up to
# the redirect above, which was confirmed live-correct but dormant since NotesPayableCurrent
# always writes first and fallback-only blocks everything after it). Live-confirmed via WVVI's
# own real SEC companyfacts JSON (CIK 0000838875): FY2025's three current-debt components -
# NotesPayableCurrent ($884,221), LongTermDebtCurrent ($1,008,215), and LineOfCredit
# ($3,140,140, redirected to short_term_debt above) - sum to $5,032,576, an EXACT match to
# yfinance's own FY2025 figure for the same row (not just close - to the dollar). FY2023/2024
# don't reconcile as cleanly (naive sum off by ~9%/~10%) but per this session's standing rule
# a yfinance mismatch alone never overrides a live-verified primary-source SEC value - FY2025's
# exact match is the real evidence, FY2023/2024 are presumed to be yfinance's own
# stale/differently-vintaged historical figures, not a 4th missing SEC component (see
# wvvi_line_of_credit_short_term_debt_finding memory note for the fuller trace of what was
# ruled out, incl. OperatingLeaseLiabilityCurrent, before landing this).
#
# Deliberately narrow to this one live-confirmed symbol: summing three separate current-debt
# concepts together is NOT a safe general rule (most filers report only one of these, or a
# combined total, and blind stacking would double-count for them) - same reasoning as every
# other symbol-gated guard in this module.
_WVVI_CURRENT_DEBT_COMPONENT_SYMBOLS = frozenset({"WVVI"})
_WVVI_CURRENT_DEBT_COMPONENT_SEC_FIELDS = frozenset(
    {"notes_payable_current", "long_term_debt_current", "line_of_credit"}
)


def is_wvvi_current_debt_component_additive(
    db_field: str, sec_field: str, existing: Any, value: Any, symbol: str | None
) -> bool:
    """True if `value` (an incoming current-debt-component write for WVVI specifically) should
    be SUMMED into `existing` (short_term_debt's currently-stored value) rather than being
    blocked by the ordinary fallback-only "db_field in row" skip - see this function's own
    module comment above for the live evidence this closes.

    Only fires for WVVI, only when db_field is short_term_debt and sec_field is one of the
    three live-confirmed genuinely-distinct current-debt components, and only when both the
    existing and incoming values are real, positive numbers - matches the shape of
    is_other_borrowings_additive_to_subordinated_debt above.
    """
    return (
        db_field == "short_term_debt"
        and sec_field in _WVVI_CURRENT_DEBT_COMPONENT_SEC_FIELDS
        and symbol in _WVVI_CURRENT_DEBT_COMPONENT_SYMBOLS
        and isinstance(existing, (int, float, Decimal))
        and float(existing) > 0
        and isinstance(value, (int, float, Decimal))
        and float(value) > 0
    )


def is_fallback_only_write_permitted_by_documented_override(
    db_field: str,
    sec_field: str,
    existing: Any,
    value: Any,
    long_term_debt_source_sec_field: str | None,
    interest_expense_source_sec_field: str | None,
    accounts_receivable_source_sec_field: str | None,
    dividends_paid_source_sec_field: str | None,
    symbol: str | None = None,
) -> bool:
    """Extracted 2026-09-17 (file-size ratchet: sec_base.py hit the 2000-line hard ceiling,
    no baseline raise accepted for that file - see this repo's own .file-size-baseline.json
    policy) from SecEdgarStatementLoader.transform()'s own fallback-only-write branch,
    mechanical extraction only, no behavior change.

    A fallback-only sec_field's write is normally skipped once `db_field` is already
    populated (`existing`) - real total already resolved by a higher-priority concept. This
    is True when one of the documented exceptions to that default applies instead: `existing`
    is itself a zero this loader shouldn't have trusted in the first place (MYFW-class), or
    `value`/`sec_field` is a genuinely distinct, additive or narrowly-scoped component this
    session's own live-confirmed evidence (DPZ/MAR/BALL/PPC/LNTH/CRL, TITN, RAVE, PED, DTST,
    ABCB - see each individual guard's own docstring above) says should still be written/
    combined rather than dropped. Callers should proceed with the normal write/sum logic when
    this returns True, and fall through to skipping the write (higher-priority concept already
    populated this field) when it returns False - matching the pre-extraction inline
    `if not (...): continue` shape exactly.
    """
    return (
        is_zero_first_write_blocking_field(db_field, existing, value)
        or is_narrow_standard_debt_blocking_combined_total(
            db_field, sec_field, existing, value, long_term_debt_source_sec_field
        )
        or is_financing_interest_expense_overriding_narrow_interest_and_debt_expense(
            db_field, sec_field, existing, value, interest_expense_source_sec_field
        )
        or is_additive_concept_pair(db_field, sec_field, existing, value)
        or is_accounts_receivable_net_overriding_narrow_receivables_net_current(
            db_field, sec_field, existing, value, accounts_receivable_source_sec_field
        )
        or is_share_based_comp_dividends_overriding_narrow_preferred_stock_dividends(
            db_field, sec_field, existing, value, dividends_paid_source_sec_field
        )
        or is_other_borrowings_additive_to_subordinated_debt(
            db_field, sec_field, existing, value, long_term_debt_source_sec_field
        )
        or is_wvvi_current_debt_component_additive(db_field, sec_field, existing, value, symbol)
    )


# ADDED 2026-09-17 (goal: xbrl_yfinance_line_item_report remediation follow-up, long_term_debt
# cluster sweep) - REBUILT same day after a multi-session working-tree collision (another
# session's subagent manually reconciling a concurrent capex edit to this file dropped this
# function, its wiring in utils/external/sec_balance_sheet.py, and its regression test entirely;
# every other guard added this session survived intact - confirmed via a full function-by-
# function audit - so this was an isolated casualty, not a broader corruption).
#
# Live-confirmed via real SEC companyfacts JSON: AJG (Arthur J. Gallagher, all 3 fiscal years in
# xbrl_yfinance_line_item_report) and EMPD (FY2025) tag a real but immaterial plain "LongTermDebt"
# fact alongside a real, dramatically larger "LongTermDebtNoncurrent" fact in the SAME 10-K - a
# taxonomy switch, same shape as this session's earlier DPZ/MAR/BALL/PPC/LNTH/CRL combined-total
# fix, but via a different concept pair. AJG FY2022: plain LongTermDebt=$16,800,000 vs.
# LongTermDebtNoncurrent=$5,562,800,000 (exact yfinance match). FY2023: $23,600,000 vs.
# $7,006,000,000 (exact match). FY2024: $23,000,000 vs. $12,732,000,000 (exact match).
#
# utils/external/sec_balance_sheet.py's _fill_long_term_debt_from_noncurrent_current_split()
# runs on the raw row BEFORE sec_base.py's transform() field-mapping guards ever see it, and its
# primary branch only fills from the noncurrent split when "long_term_debt" is still None for
# that fiscal year - so the real LongTermDebtNoncurrent total was silently discarded whenever
# ANY plain LongTermDebt value existed already, however immaterial. This guard lets that branch
# also fire when the existing plain value is real but narrow relative to the noncurrent+current
# sum, mirroring is_narrow_standard_debt_blocking_combined_total's shape one layer up.
_NONCURRENT_CURRENT_SUM_MIN_MULTIPLE = 50


def is_narrow_long_term_debt_blocking_noncurrent_current_sum(existing: Any, noncurrent: Any, current: Any) -> bool:
    """True if `existing` (long_term_debt's already-populated plain-concept value) is a real
    but immaterial figure that should be overridden by `noncurrent` + `current` (the
    LongTermDebtNoncurrent/LongTermDebtCurrent split) - see this module's own comment above for
    the live AJG/EMPD evidence. Deliberately narrow: only fires when the combined
    noncurrent+current total is at least _NONCURRENT_CURRENT_SUM_MIN_MULTIPLE times larger than
    the existing plain value, so an ordinary filer where the plain concept genuinely is close to
    the real total (a modest gap from timing/rounding) is never touched.
    """
    if not isinstance(existing, (int, float, Decimal)) or float(existing) <= 0:
        return False
    if not isinstance(noncurrent, (int, float, Decimal)):
        return False
    total = float(noncurrent) + float(current or 0)
    if total <= 0:
        return False
    return total >= float(existing) * _NONCURRENT_CURRENT_SUM_MIN_MULTIPLE


# ADDED 2026-09-17 (goal: xbrl_yfinance_line_item_report remediation follow-up, cash_and_
# equivalents cluster) - live-confirmed via real SEC companyfacts JSON: AUID (authID Inc.,
# CIK 0001534154) FY2023/FY2024 tags a real, immaterial "CashAndDueFromBanks" fact ($700 /
# $600 - not a bank, this looks like a stray escrow/petty-cash line the filer mis-tagged under
# a bank-specific concept) alongside a real, dramatically larger
# "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents" combined-cash fact
# ($10,177,099 / $8,471,561, exact yfinance match for both years).
#
# Root cause: sec_balance_sheet.py's concept-fetch list intentionally lists the combined
# concept BEFORE "CashAndDueFromBanks" (see that list's own comment - "least preferred...
# listed BEFORE the standard concept to keep it authoritative"), and sec_base.py's transform()
# processes raw concepts in the RAW ROW's own key order (from _aggregate_concepts, i.e. the
# concept-fetch list order), NOT field_mapping's dict order - confirmed empirically via
# SecEdgarStatementLoader.transform() called directly on AUID's real raw row. Since
# "CashAndDueFromBanks" is a plain concept (not fallback-gated - see its own comment: banks
# like ZION never tag any other cash concept at all, so it's meant to be directly
# authoritative for them), it unconditionally overwrote the earlier-processed, correct
# combined-cash total via ordinary last-processed-wins - the exact same failure shape as
# is_immaterial_standard_debt_overwriting_combined_total above, just for cash_and_equivalents
# instead of long_term_debt, and via CashAndDueFromBanks instead of the plain LongTermDebt
# concept.
_CASH_DUE_FROM_BANKS_MIN_MULTIPLE = 10


def is_narrow_cash_due_from_banks_overwriting_combined_cash(
    db_field: str, sec_field: str, existing: Any, value: Any, cash_source_sec_field: str | None
) -> bool:
    """True if `value` (an incoming "cash_and_due_from_banks" concept write) should be
    REJECTED to protect `existing` (cash_and_equivalents's already-resolved value, sourced
    specifically from the combined cash+restricted-cash concept) - see this module's own
    comment above for the live AUID evidence. Deliberately narrow: only fires when (1)
    db_field is cash_and_equivalents, (2) the incoming concept is specifically
    "cash_and_due_from_banks", (3) the field's current value came from the combined
    cash+restricted-cash concept (not some other, unrelated already-resolved figure - this
    guard is not about re-litigating other priority contests), and (4) the existing value is
    at least _CASH_DUE_FROM_BANKS_MIN_MULTIPLE times larger than the incoming one, so a real
    bank filer (ZION-class) whose CashAndDueFromBanks genuinely IS the authoritative, large
    total never gets blocked here - only fires when the incoming value is real but immaterial
    relative to an already-resolved, dramatically larger combined total.
    """
    return (
        db_field == "cash_and_equivalents"
        and sec_field == "cash_and_due_from_banks"
        and cash_source_sec_field == "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents"
        and isinstance(existing, (int, float, Decimal))
        and float(existing) > 0
        and isinstance(value, (int, float, Decimal))
        and float(value) > 0
        and float(existing) >= float(value) * _CASH_DUE_FROM_BANKS_MIN_MULTIPLE
    )
