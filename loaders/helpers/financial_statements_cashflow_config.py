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
        # FIXED 2026-09-16 (goal: SEC-vs-yfinance divergence sweep): CMCT real preferred-
        # distribution concept - see sec_cash_flow.py's get_cash_flow() comment on
        # "PaymentsOfDividendsPreferredStockAndPreferenceStock" for the live evidence. Same
        # never-overwrite-a-real-common-dividend-total convention as
        # dividends_preferred_stock_cash above.
        "payments_of_dividends_preferred_stock_and_preference_stock",
        # FIXED 2026-09-16 (same sweep, second follow-up pass on the remaining "0-vs-real-
        # yfinance-value" dividends_paid filers). Each found by scanning EVERY numeric fact
        # in the filer's full companyfacts JSON for one matching xbrl_yfinance_line_item_
        # report's flagged dividends_paid value exactly:
        #   - DTST: "DividendsShareBasedCompensationCash" $1,179,357 FY2021 exact match -
        #     cash dividend-equivalents paid on outstanding share-based comp awards, a real
        #     cash dividend outflow this filer reports under no other dividend concept.
        "dividends_share_based_compensation_cash",
        #   - EVEX: "PaymentsOfDistributionsToAffiliates" $1,372,633 FY2022 (~0.03% off,
        #     clear match) - a real cash distribution to a related-party/sponsor entity,
        #     this filer's only dividend-shaped cash outflow.
        "payments_of_distributions_to_affiliates",
        #   - HE (Hawaiian Electric): "PaymentsOfDividendsMinorityInterest" - a fixed
        #     $1,890,000 EVERY fiscal year 2008-2025 (live-confirmed across the filer's
        #     full companyfacts history), consistent with a static-rate preferred-unit
        #     distribution to a minority/noncontrolling interest holder, not a one-off or
        #     stale figure.
        "payments_of_dividends_minority_interest",
        #   - SEAT (Vivid Seats via a de-SPAC structure): "DividendsCommonStockPaidinkind"
        #     $17,698,000 FY2021 exact match - a real paid-in-kind common dividend, a form
        #     not tagged by any of the cash-basis DividendsCommonStock*/PaymentsOfDividends*
        #     concepts already fetched above.
        "dividends_common_stock_paidinkind",
        # ADDED 2026-09-17 (goal: data-coverage-metrics accuracy sweep): AESI real return-of-
        # capital-in-excess-of-earnings distribution - see sec_cash_flow.py's get_cash_flow()
        # comment on "AdjustmentsToAdditionalPaidInCapitalDividendsInExcessOfRetainedEarnings"
        # for the live evidence ($92,281,000 FY2025, exact yfinance match). Fallback-only,
        # same never-overwrite-a-real-standard-dividend-total convention as every other entry
        # in this set.
        "adjustments_to_additional_paid_in_capital_dividends_in_excess_of_retained_earnings",
        # ADDED 2026-09-10 (goal: "missing SEC/XBRL data under 500" push, dcf_fcf
        # missing_cash_flow_data investigation): TALK's capitalized-software-development
        # concept - see sec_cash_flow.py's get_cash_flow() comment for the live evidence.
        # Fallback-only so it never overwrites a real PaymentsToAcquirePropertyPlantAndEquipment
        # (or sibling PP&E-family) value for a filer that reports both.
        "payments_to_acquire_software",
        # ADDED 2026-09-10 (goal: "missing SEC/XBRL data under 300" push, payout_ratio
        # missing_sec_data investigation): TPG's bare "Dividends" concept - see
        # sec_cash_flow.py's get_cash_flow() comment for the live evidence. Fallback-only so
        # it never overwrites a real DividendsCommonStock*/PaymentsOfDividends*/
        # PaymentsOfCapitalDistribution value for a filer that reports any of those.
        "dividends",
        # FIXED 2026-09-16 (goal: SEC-vs-yfinance divergence sweep, our_value=0-vs-real-
        # yfinance-value audit): DRH (DiamondRock Hospitality, a REIT) tags a real capex
        # figure under "PaymentsForCapitalImprovements" ($81,563,000 FY2025, live-confirmed
        # via SEC companyfacts JSON, exactly matching the yfinance-flagged value) AND a
        # narrower "$0 spent on land this year" fact under "PaymentsToAcquireLand" at the
        # same time. "PaymentsToAcquireLand" was a plain (non-fallback) concept - since it's
        # processed after PaymentsForCapitalImprovements/RealEstateImprovements in
        # sec_cash_flow.py's concept-list order, its real $0 land-purchases fact
        # unconditionally overwrote the correct, larger total capex figure via ordinary
        # last-processed-wins. Same bug class as this session's senior_notes/long_term_debt
        # fix in financial_statements_balance_config.py (PNBK) - a concept representing one
        # narrow acquisition category, not the filer's total capex, must never be allowed to
        # clobber a more complete concept already resolved.
        "payments_to_acquire_land",
        # FIXED 2026-09-16 (same sweep, NSC/SNPS live-confirmed via real SEC companyfacts
        # JSON): both tag a real, complete "PaymentsToAcquirePropertyPlantAndEquipment"
        # ($2,204,000,000 for NSC FY2025, $169,454,000 for SNPS FY2025 - both exactly
        # matching the yfinance-flagged value) AND a real "$0 spent on other productive
        # assets this year" fact under "PaymentsToAcquireOtherProductiveAssets" at the same
        # time. Same bug as payments_to_acquire_land above - a plain (non-fallback) concept
        # listed after the standard PP&E concept unconditionally overwrote the correct total
        # with 0 via last-processed-wins.
        "payments_to_acquire_other_productive_assets",
        # FIXED 2026-09-16 (same sweep, VICI live-confirmed): tags a real
        # "PaymentsToAcquireOtherPropertyPlantAndEquipment" ($1,335,000 FY2025, matching the
        # yfinance-flagged value) AND a real "$0 real estate acquired this year" fact under
        # "PaymentsToAcquireRealEstate" at the same time - same overwrite bug. Fallback-only
        # membership preserves the REIT case this concept was added for (AHR/ABR, 2026-08-24
        # fix - reports ONLY this concept, no PP&E-family concept at all): still fills capex
        # when nothing else did, never overwrites a real PP&E-family value.
        "payments_to_acquire_real_estate",
        # FIXED 2026-09-16 (same sweep, second follow-up pass on the remaining "0-vs-real-
        # yfinance-value" capex filers). Each found by scanning EVERY numeric fact in the
        # filer's full companyfacts JSON for one matching xbrl_yfinance_line_item_report's
        # flagged capex value exactly, then confirmed the concept is a genuine capital-
        # spending-equivalent line for that filer:
        #   - FBIO/KIDZ/SCYX: "PaymentsToAcquireIntangibleAssets" - $15,000,000 FY2024 /
        #     $1,250,000 FY2025 / $1,172,000 FY2021, all exact matches.
        "payments_to_acquire_intangible_assets",
        #   - KKR: "PaymentsToAcquireFurnitureAndFixtures" $85,056,000 FY2022 exact match.
        "payments_to_acquire_furniture_and_fixtures",
        #   - KOS (Kosmos Energy, an E&P): "PaymentsToAcquireOilAndGasEquipment"
        #     $933,659,000 FY2024 exact match - a different O&G capex concept from the
        #     costs_incurred_oil_and_gas_property_.../payments_to_acquire_oil_and_gas_
        #     property_and_equipment concepts already fetched above.
        "payments_to_acquire_oil_and_gas_equipment",
        #   - NLY (Annaly Capital, a mortgage REIT): "PaymentsToAcquireMortgageServicing
        #     RightsMSR" $396,806,000 FY2023 exact match - MSR purchases are this filer's
        #     real capex-equivalent spending, analogous to the other REIT-sector capex
        #     concepts already fetched above.
        "payments_to_acquire_mortgage_servicing_rights_msr",
        #   - DOCS/ROOT/STEM: "PaymentsToDevelopSoftware" - $8,901,000 FY2026 (DOCS,
        #     ~0.7% off due to a fiscal-year-end date rounding, still the clear match),
        #     $14,100,000 FY2025 (ROOT), $6,602,000 FY2025 (STEM), all exact/near-exact
        #     matches - the standard concept for capitalized software development, same
        #     role as payments_to_acquire_software above but the exact-name-match variant
        #     for these filers.
        "payments_to_develop_software",
        #   - TIL (Instil Bio -> Tenon Medical, a clinical-stage biotech): "PaymentsToAcquire
        #     InProcessResearchAndDevelopment" $10,000,000 FY2024/FY2025 exact match both
        #     years - a real, recurring capitalized-IPR&D spend for this filer.
        "payments_to_acquire_in_process_research_and_development",
        # MADE FALLBACK-ONLY 2026-09-18 (goal session, xbrl_yfinance_line_item_report capex
        # remediation) - see this field's own comment in _CASHFLOW_FIELD_MAPPING below for
        # the live AMT/SKT evidence.
        "real_estate_improvements",
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
    # MADE FALLBACK-ONLY 2026-09-18 (goal session, xbrl_yfinance_line_item_report capex
    # remediation): SKT tags ONLY this concept (no PaymentsToAcquirePropertyPlantAndEquipment
    # at all), so the fix above was correct for SKT - but AMT (a much larger REIT) tags BOTH,
    # and "RealEstateImprovements" there is a genuinely narrower property-improvement
    # sub-line-item, not its total capex (live-confirmed via SEC companyfacts: AMT FY2022
    # RealEstateImprovements=$155.4M vs PaymentsToAcquirePropertyPlantAndEquipment=$1,873.6M,
    # yfinance's real figure). Unconditional "last-listed-wins" let this narrower concept
    # overwrite AMT's real, much larger total every year - same bug shape as the
    # long_term_debt narrow-vs-combined-concept fix, on the cash-flow side. Fallback-only
    # (added to _SBC_BUYBACK_FALLBACK_ONLY_FIELDS below) preserves SKT's fix (no other capex
    # concept present, so this still wins) while no longer overwriting AMT's real total.
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
    # ADDED 2026-09-11 (goal: "SEC/XBRL missing data under 300" push) - see
    # sec_cash_flow.py's get_cash_flow() comment for the live CleanSpark/McEwen Inc/Idaho
    # Strategic Resources/Materion Corporation evidence: a standard us-gaap mining-asset
    # acquisition capex concept, distinct from payments_to_acquire_mineral_rights above
    # (rights/interests, not the physical mining assets), never fetched at all.
    "payments_to_acquire_mining_assets": "capex",
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
    # FIXED 2026-09-16 (same sweep, second follow-up pass): see
    # _SBC_BUYBACK_FALLBACK_ONLY_FIELDS above for the full live evidence
    # (FBIO/KIDZ/SCYX/KKR/KOS/NLY/DOCS/ROOT/STEM/TIL). All fallback-only.
    "payments_to_acquire_intangible_assets": "capex",
    "payments_to_acquire_furniture_and_fixtures": "capex",
    "payments_to_acquire_oil_and_gas_equipment": "capex",
    "payments_to_acquire_mortgage_servicing_rights_msr": "capex",
    "payments_to_develop_software": "capex",
    "payments_to_acquire_in_process_research_and_development": "capex",
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
    # ADDED 2026-09-10 (goal: "missing SEC/XBRL data under 300" push): TPG's bare
    # "Dividends" concept - see sec_cash_flow.py's get_cash_flow() comment for the live
    # evidence. Fallback-only (added to _SBC_BUYBACK_FALLBACK_ONLY_FIELDS below) since this
    # bare tag name is ambiguous enough (dividends declared vs. paid, or dividend income
    # received for an investment-company-shaped filer) that it must never overwrite a real
    # standard-concept value.
    "dividends": "dividends_paid",
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
    # FIXED 2026-09-16 (goal: SEC-vs-yfinance divergence sweep): see
    # _SBC_BUYBACK_FALLBACK_ONLY_FIELDS above for why this is fallback-only (CMCT).
    "payments_of_dividends_preferred_stock_and_preference_stock": "dividends_paid",
    # FIXED 2026-09-16 (same sweep, second follow-up pass): see
    # _SBC_BUYBACK_FALLBACK_ONLY_FIELDS above for the full live evidence
    # (DTST/EVEX/HE/SEAT). All fallback-only.
    "dividends_share_based_compensation_cash": "dividends_paid",
    "payments_of_distributions_to_affiliates": "dividends_paid",
    "payments_of_dividends_minority_interest": "dividends_paid",
    "dividends_common_stock_paidinkind": "dividends_paid",
    # ADDED 2026-09-17 (goal: data-coverage-metrics accuracy sweep): see
    # _SBC_BUYBACK_FALLBACK_ONLY_FIELDS above for why this is fallback-only (AESI).
    "adjustments_to_additional_paid_in_capital_dividends_in_excess_of_retained_earnings": "dividends_paid",
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
