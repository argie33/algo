"""Cash-flow-statement field mapping and get_cash_flow_config(), extracted from
load_financial_statements.py alongside the income/balance config modules - see
financial_statements_income_config.py's docstring for the full extraction rationale.
"""

from typing import Any

from loaders.helpers.financial_statements_config_shared import _MARKER_FIELDS, _QUARTERLY_EXTRA

_SBC_BUYBACK_FALLBACK_ONLY_FIELDS = frozenset(
    {
        "allocated_share_based_compensation_expense",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): see
        # sec_statements.py's get_cash_flow() comment on StockOptionPlanExpense (CVX
        # live-confirmed) - must never win over a real ShareBasedCompensation/
        # AllocatedShareBasedCompensationExpense value.
        "stock_option_plan_expense",
        "payments_for_repurchase_of_equity",
        # FIXED 2026-08-29 (shipping-sector custom-XBRL-concept capex fallback): must
        # never win over a real value the normal concept-list extraction already found -
        # this key only exists for symbols where that extraction structurally can't work
        # at all (see _CASHFLOW_FIELD_MAPPING's comment on this same key).
        "custom_extension_vessel_capex",
        # FIXED 2026-09-03 (same sweep): NJR's dimensioned-sum capex - same "never win
        # over a real value the normal concept-list extraction already found" reasoning
        # as custom_extension_vessel_capex above (see CUSTOM_CAPEX_DIMENSIONED_CONCEPTS's
        # docstring in sec_custom_xbrl_concepts.py).
        "custom_extension_capex_dimensioned_sum",
        # FIXED 2026-09-03 (same sweep): CMS's custom-extension dividends_paid - same
        # "never win over a real value the normal concept-list extraction already found"
        # reasoning as the capex/revenue custom-extension fields above (see
        # CUSTOM_DIVIDEND_CONCEPTS's docstring in sec_custom_xbrl_concepts.py).
        "custom_extension_dividends_paid",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): ED's
        # narrower "construction work in progress" concept - see this dict's own comment
        # on "payments_for_construction_in_process" above and sec_statements.py's
        # get_cash_flow() comment for the live evidence it must never overwrite a real
        # standard-concept capex value.
        "payments_for_construction_in_process",
        # FIXED 2026-08-19 (goal: "no SEC data"/loader audit): see sec_statements.py's
        # get_cash_flow() comment on "NetCashProvidedByUsedInOperatingActivities
        # ContinuingOperations" (ASH/Ashland live-confirmed: zero entries under the plain
        # concept, ever - real OCF stuck NULL for its entire history). Fallback-only so
        # APD/ANGI (which report both concepts) keep the fuller plain-concept total
        # whenever it's actually present for that fiscal year.
        "net_cash_provided_by_used_in_operating_activities_continuing_operations",
        # ADDED 2026-09-10 (goal session: SEC/XBRL missing-data count under 500,
        # missing_cash_flow_data investigation): shorter-named sibling concept - see
        # sec_statements.py's get_cash_flow() comment on "NetCashProvidedByUsedInContinuing
        # Operations" (KN/Knowles Corporation live-confirmed: real annual figures every
        # FY2012-2025, never a full-year fact under either OperatingActivities concept).
        # Fallback-only, same never-overwrite-a-real-plain-value rationale.
        "net_cash_provided_by_used_in_continuing_operations",
        # FIXED 2026-09-07 (goal session: "make sure the list/checks are right, then fix
        # issues" audit): same fallback-only rationale as the Operating entry above - see
        # sec_statements.py's get_cash_flow() comment on these 2 concepts for the live APD
        # evidence (investing/financing cash flow tagged ONLY under ContinuingOperations for
        # APD's entire FY2016-2025 history) and the broader 1,391/1,373-filer partial-year
        # gap. Must never overwrite a real plain-concept value when both are present for the
        # same fiscal year.
        "net_cash_provided_by_used_in_investing_activities_continuing_operations",
        "net_cash_provided_by_used_in_financing_activities_continuing_operations",
        # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit): BDC-
        # specific distribution concept - see sec_statements.py's get_cash_flow() comment
        # on this concept (MAIN live-confirmed: tags this AND a real, materially LARGER
        # DividendsCommonStock figure - a narrower/different sub-component, not a
        # duplicate) - must never overwrite a real standard-concept dividends_paid value.
        "investment_company_dividend_distribution",
        # ADDED 2026-09-09: see sec_statements.py's get_cash_flow() comment on
        # DividendsPreferredStockCash/DividendsPreferredStock (PSA live evidence) - must
        # never overwrite a real DividendsCommonStock*/PaymentsOfDividends* total, which
        # already reflects the fuller combined-distribution figure whenever tagged.
        "dividends_preferred_stock_cash",
        "dividends_preferred_stock",
        # ADDED 2026-09-10 (goal: "missing SEC/XBRL data under 500" push, dcf_fcf
        # missing_cash_flow_data investigation): TALK's capitalized-software-development
        # concept - see sec_cash_flow.py's get_cash_flow() comment for the live evidence.
        # Fallback-only so it never overwrites a real PaymentsToAcquirePropertyPlantAndEquipment
        # (or sibling PP&E-family) value for a filer that reports both.
        "payments_to_acquire_software",
    }
)


_CASHFLOW_FIELD_MAPPING = {
    "net_cash_provided_by_used_in_operating_activities": "operating_cash_flow",
    # FIXED 2026-08-19 (goal: "no SEC data"/loader audit): fallback-only, see
    # _OCF_FALLBACK-style comment on _SBC_BUYBACK_FALLBACK_ONLY_FIELDS above and
    # sec_statements.py's get_cash_flow() comment for the live ASH evidence.
    "net_cash_provided_by_used_in_operating_activities_continuing_operations": "operating_cash_flow",
    # ADDED 2026-09-10: see this dict's own _OCF_FALLBACK_ONLY_FIELDS comment above (KN live
    # evidence) - fallback-only, same convention as the sibling entry immediately above.
    "net_cash_provided_by_used_in_continuing_operations": "operating_cash_flow",
    "net_cash_provided_by_used_in_investing_activities": "investing_cash_flow",
    "net_cash_provided_by_used_in_financing_activities": "financing_cash_flow",
    # FIXED 2026-09-07 (goal session: "make sure the list/checks are right, then fix issues"
    # audit): fallback-only, see _SBC_BUYBACK_FALLBACK_ONLY_FIELDS above and
    # sec_statements.py's get_cash_flow() comment for the live APD evidence.
    "net_cash_provided_by_used_in_investing_activities_continuing_operations": "investing_cash_flow",
    "net_cash_provided_by_used_in_financing_activities_continuing_operations": "financing_cash_flow",
    # Found 2026-07-20: this mapped to "capital_expenditures", a column that has never
    # existed in annual_cash_flow/quarterly_cash_flow (real column is "capex") - every
    # write silently vanished at the schema-validation step below, leaving capex NULL for
    # all ~140K existing rows across both tables since this loader was created (Session
    # 274). Renamed to match the real column so new/incremental writes actually land;
    # existing NULL rows need a backfill (re-run with BACKFILL_DAYS or per-symbol refetch).
    "payments_to_acquire_property_plant_and_equipment": "capex",
    # FIXED 2026-08-10: real capex concept some filers use INSTEAD of plain
    # "PaymentsToAcquirePropertyPlantAndEquipment" - live-confirmed via AAON, KELYB, CPS,
    # DTIL (all report ONLY "PaymentsToAcquireProductiveAssets", with real recent values -
    # AAON has 112 entries back through FY2023). This was the direct cause of
    # free_cash_flow/fcf_to_net_income being stuck at "SEC data not available" for these
    # symbols despite operating_cash_flow being populated - capex was never NULL because
    # the filer didn't report capex, it was NULL because this loader only looked for one
    # of two real capex tags. See sec_statements.py's get_cash_flow() concept list.
    "payments_to_acquire_productive_assets": "capex",
    # FIXED 2026-08-18 (goal: "missing SEC data" scores audit, AAON live-confirmed): see
    # sec_statements.py's get_cash_flow() comment on this concept - AAON (and likely other
    # filers) switched from PaymentsToAcquireProductiveAssets to this tag starting FY2023,
    # with zero overlap between the two, so capex was silently NULL for 3+ years.
    "payments_to_acquire_machinery_and_equipment": "capex",
    # FIXED 2026-08-18 (goal: "missing factor inputs" audit continuation): see
    # sec_statements.py's get_cash_flow() comments on these 2 concepts - VZ tags capex
    # ONLY under "OtherProductiveAssets" (NULL every year 2021-2026 despite real OCF);
    # LLY/ADP tag it ONLY under "OtherPropertyPlantAndEquipment" (same failure shape).
    "payments_to_acquire_other_productive_assets": "capex",
    "payments_to_acquire_other_property_plant_and_equipment": "capex",
    # ADDED 2026-09-10 (goal: "missing SEC/XBRL data under 500" push, dcf_fcf
    # missing_cash_flow_data investigation): TALK (Talkspace, CIK 1803901, a real
    # telehealth 10-K filer) stopped tagging any PP&E-family capex concept after FY2023
    # ($151K, its last "PaymentsToAcquirePropertyPlantAndEquipment" entry) - live-confirmed
    # via real companyfacts JSON that its FY2024/FY2025 capex is instead tagged under this
    # standard (not filer-specific) us-gaap concept for capitalized software development
    # costs, the real dominant capex line for a light-physical-footprint SaaS/telehealth
    # business: $5,443,000 FY2024 / $10,641,000 FY2025, both real 10-K annual-duration
    # facts. dcf_fcf/free_cash_flow/fcf_margin were stuck at "missing_cash_flow_data" for
    # FY2024-2025 despite real, current operating_cash_flow being tagged every year.
    # Fallback-only (see _SBC_BUYBACK_FALLBACK_ONLY_FIELDS above) so it never overwrites a
    # real PP&E-family capex value for a filer that reports both.
    "payments_to_acquire_software": "capex",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep) - see
    # sec_statements.py's get_cash_flow() comment for the live CTOS evidence: a standard
    # (not filer-specific) equipment-rental-fleet capex concept, never fetched at all.
    "payments_to_acquire_equipment_on_lease": "capex",
    # FIXED 2026-08-24 (goal: "Margin of Safety (DCF)" cash-flow-coverage audit): REIT-sector
    # capex concepts - see sec_statements.py's get_cash_flow() comment for the live AAT/AHT/
    # AHR/ABR evidence. Same "capex" target column as the PP&E-family concepts above.
    "payments_to_acquire_and_develop_real_estate": "capex",
    "payments_to_acquire_real_estate": "capex",
    "payments_for_capital_improvements": "capex",
    # ADDED 2026-09-06 (goal session: "SEC/XBRL missing data to zero" sweep, scored-symbol
    # follow-up beyond the earlier REIT capex sweep) - see sec_cash_flow.py's get_cash_flow()
    # comment for the live SKT (Tanger Inc) evidence: a standard REIT property-improvement
    # capex concept, never fetched at all.
    "real_estate_improvements": "capex",
    # FIXED 2026-09-02 (goal: "missing SEC/XBRL data" audit, live SEC EDGAR verification of
    # the 2026-08-24 fix's "pending separate verification" exclusion) - see sec_statements.py's
    # get_cash_flow() comment for the live SLG (SL Green) evidence: 8 straight years of real,
    # varying (including genuine $0) values under this concept since it replaced
    # "payments_to_acquire_real_estate" in SLG's FY2020 10-K.
    "payments_to_acquire_commercial_real_estate": "capex",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep) - see
    # sec_statements.py's get_cash_flow() comment for the live DLR/REG evidence: a standard
    # (not filer-specific) real-estate-development-spend concept, never fetched at all.
    "payments_to_develop_real_estate_assets": "capex",
    # FIXED 2026-09-06 (capex_never_tagged_in_recent_filings sweep) - see
    # sec_cash_flow.py's get_cash_flow() comment for the live MRP (Millrose Properties)
    # evidence: a land-banking REIT's direct capex-equivalent concept, never fetched at
    # all. Same "capex" target column as the other REIT concepts above.
    "payments_to_acquire_land": "capex",
    # FIXED 2026-09-09 (capex_never_tagged_in_recent_filings 86-symbol sweep) - see
    # sec_cash_flow.py's get_cash_flow() comment for the live LZM (Lifezone Metals)/FMST
    # (Foremost Clean Energy) evidence: a standard ifrs-full mineral-exploration capex
    # concept, never fetched at all. Same "capex" target column as the other sector-
    # specific PP&E-family concepts above.
    "purchase_of_exploration_and_evaluation_assets": "capex",
    # FIXED 2026-09-09 (same sweep) - see sec_cash_flow.py's get_cash_flow() comment for
    # the live Freeport-McMoRan/Royal Gold/Diamondback Energy/Coeur Mining/TMQ evidence: a
    # standard us-gaap mineral-rights-acquisition capex concept, never fetched at all.
    "payments_to_acquire_mineral_rights": "capex",
    # FIXED 2026-08-24 (same audit, insurance-sector continuation): insurer investment-
    # real-estate capex concepts - see sec_statements.py's get_cash_flow() comment for the
    # live MET/RGA/BHF/PFG/TRV/WRB evidence.
    "payments_to_acquire_real_estate_and_real_estate_joint_ventures": "capex",
    "payments_to_acquire_real_estate_held_for_investment": "capex",
    # FIXED 2026-08-29 (goal: "full data" audit continuation): oil & gas E&P sector capex
    # concepts - see sec_statements.py's get_cash_flow() comment for the live APA/AR/CHRD/
    # CRGY/AMPY/EGY/DVN evidence. Same "capex" target column as the PP&E-family concepts
    # above.
    "costs_incurred_oil_and_gas_property_acquisition_exploration_and_development_activities": "capex",
    "payments_to_acquire_oil_and_gas_property": "capex",
    "payments_to_explore_and_develop_oil_and_gas_properties": "capex",
    # FIXED 2026-08-29 (same audit, MGY/GTE follow-up): see sec_statements.py's get_cash_flow()
    # comment for the live evidence - a distinct concept from payments_to_acquire_oil_and_gas_
    # property above, not a duplicate.
    "payments_to_acquire_oil_and_gas_property_and_equipment": "capex",
    # FIXED 2026-08-29 (same audit, shipping-sector follow-up): identity key
    # ConsolidatedFinancialStatementsLoader.fetch_incremental() sets directly on rows for
    # symbols in utils/external/sec_custom_xbrl_concepts.py's CUSTOM_CAPEX_CONCEPTS - see
    # that module's docstring for why (real capex tagged under a filer-specific custom
    # XBRL extension taxonomy, structurally invisible to the companyfacts API this file's
    # normal concept-list extraction depends on). fallback_only (see
    # _SBC_BUYBACK_FALLBACK_ONLY_FIELDS below) so it never overwrites a real value the
    # normal SEC extraction already found.
    "custom_extension_vessel_capex": "capex",
    "custom_extension_capex_dimensioned_sum": "capex",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data" sweep) - see
    # sec_statements.py's get_cash_flow() comment for the live CWT (water utility)
    # evidence. Same "capex" target column as the other sector-specific PP&E-family
    # concepts above.
    "payments_to_acquire_water_and_waste_water_systems": "capex",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, capex_never_
    # tagged_in_recent_filings continuation): see sec_statements.py's get_cash_flow()
    # comment on this concept - D (Dominion Energy) live-confirmed, a pure taxonomy
    # relabeling of the same real capex line, not fallback-only (value-identical to the
    # standard concept in every year both are present).
    "payments_for_proceeds_from_productive_assets": "capex",
    # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_cash_flow() comment on
    # this concept - ED (Consolidated Edison) live-confirmed. Fallback-only (added to
    # _SBC_BUYBACK_FALLBACK_ONLY_FIELDS below): unlike the concept above, this is a
    # narrower "construction work in progress" sub-line that reports a genuinely smaller
    # figure than the standard concept in years both are present, so it must never
    # overwrite a real standard-concept value.
    "payments_for_construction_in_process": "capex",
    # FIXED 2026-09-05: fetched since the 2026-09-03 PSA fix to sec_statements.py's
    # get_cash_flow() concept list but never mapped here, so it was silently dropped at
    # transform() - PSA payments_of_capital_distribution=$2,303,381,000 FY2025
    # live-confirmed. Least-preferred/first in the concept list so last-listed-wins
    # ordering still lets a real DividendsCommonStock*/PaymentsOfDividends* value win.
    "payments_of_capital_distribution": "dividends_paid",
    # FIXED 2026-09-05: see sec_statements.py's get_cash_flow() comment on this concept -
    # BDC-specific (TRIN live-confirmed as the only concept it tags at all). Fallback-only
    # (added to _SBC_BUYBACK_FALLBACK_ONLY_FIELDS below): MAIN tags this AND a real,
    # materially larger DividendsCommonStock figure, so this must never overwrite a real
    # standard-concept value.
    "investment_company_dividend_distribution": "dividends_paid",
    "payments_of_dividends": "dividends_paid",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): CMS's
    # filer-specific custom XBRL extension dividends concept - see
    # utils/external/sec_custom_xbrl_concepts.py's CUSTOM_DIVIDEND_CONCEPTS docstring.
    # fallback_only (see _SBC_BUYBACK_FALLBACK_ONLY_FIELDS below) so it never overwrites a
    # real value the normal SEC extraction already found.
    "custom_extension_dividends_paid": "dividends_paid",
    # FIXED 2026-08-17 (migration 1206): ShareBasedCompensation/
    # PaymentsForRepurchaseOfCommonStock were added to sec_statements.py's fetch list but
    # never mapped here - same "fetched but unmapped" bug class this file has hit
    # repeatedly (see test_financial_statements_field_mapping_completeness.py). Real data
    # was being fetched from SEC every run and silently dropped at transform().
    "share_based_compensation": "stock_based_compensation",
    "payments_for_repurchase_of_common_stock": "common_stock_repurchased",
    # FIXED 2026-08-17 (loader-review goal continuation): fallback-only, see
    # _SBC_BUYBACK_FALLBACK_ONLY_FIELDS comment above.
    "allocated_share_based_compensation_expense": "stock_based_compensation",
    "payments_for_repurchase_of_equity": "common_stock_repurchased",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): CVX
    # (Chevron) live-confirmed - see sec_statements.py's get_cash_flow() comment on this
    # concept. Fallback-only (added to _SBC_BUYBACK_FALLBACK_ONLY_FIELDS below), least
    # preferred of the three SBC concepts.
    "stock_option_plan_expense": "stock_based_compensation",
    # FIXED 2026-08-03: real dividend-payment concepts some filers use INSTEAD of plain
    # "PaymentsOfDividends" - see sec_statements.py's comment above these concepts.
    "payments_of_dividends_common_stock": "dividends_paid",
    "payments_of_ordinary_dividends": "dividends_paid",
    # FIXED 2026-08-18 (missing factor inputs audit): ACGL (Arch Capital)/FRT (Federal
    # Realty)/VSH (Vishay) - all 3 live-confirmed real, currently-paying dividend stocks
    # (real recent ex_dividend_date on file in dividend_data) - never tag any of the 3
    # "PaymentsOf*Dividend*" concepts above at all. They report under "DividendsCommonStockCash"
    # instead (a genuine, well-populated concept: VSH's real values run $35M-$57M/year,
    # 2014-2025, growing in line with a normal dividend program). 19 confirmed real payers
    # universe-wide had NULL dividends_paid in every annual_cash_flow row before this fix.
    # Unlike the "PaymentsOf*" family (a payments/outflow concept, standard-positive by XBRL
    # convention), "DividendsCommonStockCash" carries a debit-balance definition and
    # live-confirmed flips sign by filing vintage (VSH: negative 2014-2017, positive
    # 2019-2025, for the exact same real dividend program) - see the abs() normalization in
    # ConsolidatedFinancialStatementsLoader.transform() below, required specifically for
    # this concept so a sign flip can't silently produce a negative payout_ratio/dividend
    # figure downstream.
    "dividends_common_stock_cash": "dividends_paid",
    "dividends_common_stock": "dividends_paid",
    # ADDED 2026-09-09: see _SBC_BUYBACK_FALLBACK_ONLY_FIELDS above for why these are
    # fallback-only.
    "dividends_preferred_stock_cash": "dividends_paid",
    "dividends_preferred_stock": "dividends_paid",
    # ADDED 2026-09-07 (goal: "SEC/XBRL missing data" + tie-out sweep): net_change_cash was
    # a declared schema column with zero rows ever populated (0/66,580) - fetched by none of
    # sec_cash_flow.py's concepts and mapped by no entry here. See that file's get_cash_flow()
    # comment on these 4 concepts for the live AMZN evidence (pre- and post-ASU-2016-18
    # generations, each with an ExcludingExchangeRateEffect sibling).
    "cash_and_cash_equivalents_period_increase_decrease_excluding_exchange_rate_effect": "net_change_cash",
    "cash_and_cash_equivalents_period_increase_decrease": "net_change_cash",
    "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents_period_increase_decrease_excluding_exchange_rate_effect": "net_change_cash",
    "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents_period_increase_decrease_including_exchange_rate_effect": "net_change_cash",
    **_MARKER_FIELDS,
}

# Quarterly rows carry fiscal_period ("Q1".."Q4"), which transform() converts to the
# integer fiscal_quarter column. Annual rows' fiscal_period ("FY") stays unmapped -
# annual tables have no fiscal_quarter column.


def get_cash_flow_config(period: str) -> dict[str, Any]:
    """Cash flow statement configuration for annual/quarterly/ttm."""
    if period == "annual":
        return {
            "table_name": "annual_cash_flow",
            "field_mapping": dict(_CASHFLOW_FIELD_MAPPING),
            "fallback_only_fields": _SBC_BUYBACK_FALLBACK_ONLY_FIELDS,
            "primary_key": ("symbol", "fiscal_year"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "fiscal_year",
                    "operating_cash_flow",
                    "investing_cash_flow",
                    "financing_cash_flow",
                    "net_change_cash",
                    "free_cash_flow",
                    "capex",
                    "dividends_paid",
                    "stock_based_compensation",
                    "common_stock_repurchased",
                    "created_at",
                    "data_unavailable",
                    "reason",
                    "data_source",
                ]
            ),
        }
    elif period == "quarterly":
        return {
            "table_name": "quarterly_cash_flow",
            "field_mapping": {**_CASHFLOW_FIELD_MAPPING, **_QUARTERLY_EXTRA},
            "fallback_only_fields": _SBC_BUYBACK_FALLBACK_ONLY_FIELDS,
            "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "fiscal_year",
                    "fiscal_quarter",
                    "operating_cash_flow",
                    "investing_cash_flow",
                    "financing_cash_flow",
                    "net_change_cash",
                    "free_cash_flow",
                    "capex",
                    "dividends_paid",
                    "stock_based_compensation",
                    "common_stock_repurchased",
                    "created_at",
                    "data_unavailable",
                    "reason",
                    "data_source",
                ]
            ),
        }
    elif period == "ttm":
        return {
            "table_name": "ttm_cash_flow",
            "field_mapping": dict(_CASHFLOW_FIELD_MAPPING),
            "primary_key": ("symbol", "report_date"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "report_date",
                    "operating_cash_flow",
                    "investing_cash_flow",
                    "financing_cash_flow",
                    "net_change_cash",
                    "free_cash_flow",
                    "capex",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    else:
        raise ValueError(f"Unknown period: {period}")
