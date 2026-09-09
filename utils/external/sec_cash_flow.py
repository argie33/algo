"""Cash-flow-statement extraction for utils/external/sec_statements.py, extracted from that
file (2026-09-05, file-size ratchet: it's a Tier-2 bloater flagged for decomposition). Body is
verbatim, no logic changed - only moved file. get_cash_flow() aggregates key cash-flow concepts
via sec_statements_aggregate.py's _aggregate_concepts - no post-processing fallback passes are
needed here, unlike get_balance_sheet/get_income_statement.
"""

from typing import Any

from utils.external.sec_statements_aggregate import _aggregate_concepts

_CASHFLOW_IFRS_ALIASES = [
    ("CashFlowsFromUsedInOperatingActivities", "net_cash_provided_by_used_in_operating_activities"),
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
    # free_cash_flow/fcf_margin/accruals_ratio investigation): NGG (National Grid plc,
    # $78.5B UK utility, CIK 0001004315, 20-F/IFRS filer) never tags plain
    # "CashFlowsFromUsedInOperatingActivities" - live-confirmed real operating cash flow
    # is only reported as "CashFlowsFromUsedInOperatingActivitiesContinuingOperations"
    # (GBP 6,939,000,000 FY2024 / 6,808,000,000 FY2025), the standard IAS 7 "Net cash from
    # operating activities" line for a filer presenting continuing/discontinued operations
    # separately - reconciles with the sibling "CashFlowsFromUsedInOperations" (a
    # before-tax subtotal) minus "IncomeTaxesPaidRefundClassifiedAsOperatingActivities".
    # Same target_key as the plain concept above so field_mapping needs no changes.
    # Listed AFTER the plain concept - for ifrs_aliases specifically, `_aggregate_concepts`
    # keeps the FIRST match per (fiscal_year, target_key) rather than the last (verified
    # empirically via a _FakeClient test - unlike the "last-listed wins" convention
    # documented for the plain-concepts/PaymentsOf*/capex fallback lists elsewhere in this
    # file, which is a different code path), so this earlier-registered plain concept
    # keeps priority for a filer reporting both, and this later entry only fills the gap
    # when that concept is absent entirely - real capex (annual_cash_flow.capex) was
    # already populated for NGG via a separate concept, only operating_cash_flow (and
    # everything downstream: free_cash_flow, fcf_margin, accruals_ratio) was blocked by
    # this gap.
    ("CashFlowsFromUsedInOperatingActivitiesContinuingOperations", "net_cash_provided_by_used_in_operating_activities"),
    # FIXED 2026-09-08 (goal session: "Missing SEC/XBRL data" 993 sweep, dcf_fcf/fcf_margin
    # "missing_cash_flow_data" investigation): SU (Suncor Energy, $50B+ Canadian oil major,
    # CIK 0000311337, 40-F/IFRS filer) and several smaller miners (GLDG/SLI/SLSR) and other
    # 20-F/40-F filers (LPA/CDRO) tag NEITHER "CashFlowsFromUsedInOperatingActivities" NOR
    # the "...ContinuingOperations" variant above - live-confirmed via real companyfacts
    # JSON, the ONLY operating-cash-flow-shaped concept they report at all is
    # "CashFlowsFromUsedInOperations" (SU FY2025: CAD 12.781B, real, current, full 12-month
    # annual duration from a 40-F). The comment above this list's own NGG entry documents
    # this same concept as "a before-tax subtotal" that normally needs
    # "IncomeTaxesPaidRefundClassifiedAsOperatingActivities" subtracted to reconcile with
    # the final post-tax figure - but NGG separately tags an
    # "...OperatingActivitiesContinuingOperations" concept that already IS the correct
    # final figure, so that subtraction was never actually needed to populate NGG's
    # operating_cash_flow (see that entry's own comment: "operating_cash_flow ... was
    # already populated for NGG via a separate concept"). For SU/GLDG/SLI/SLSR/LPA/CDRO,
    # live-confirmed via the same real companyfacts JSON: none of them tag ANY
    # "IncomeTaxesPaidRefundClassifiedAsOperatingActivities" fact either - i.e. these
    # filers don't disaggregate a separate tax-paid line at all, so
    # "CashFlowsFromUsedInOperations" is the only, and therefore the best-available, real
    # total operating cash flow figure on file for them (same "partial but far better than
    # missing" precedent as RevenueFromSaleOfGold below in the revenue aliases). Listed
    # last (lowest priority) so it only ever fills the gap when both more precise concepts
    # above are absent - never overrides a real, more complete figure a filer that
    # separately itemizes tax already provides via the higher-priority entries.
    ("CashFlowsFromUsedInOperations", "net_cash_provided_by_used_in_operating_activities"),
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
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data" reduction): KGC (Kinross
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
        # FIXED 2026-09-07 (goal session: "make sure the list/checks are right, then fix
        # issues" audit): same "discontinued-operations filer" failure shape as the Operating
        # pair above, live-confirmed via real companyfacts JSON. Air Products and Chemicals
        # (APD, a major real 10-K filer) tags investing/financing cash flow ONLY under these
        # ContinuingOperations concepts for EVERY fiscal year 2016-2025 - the plain concepts
        # below have zero entries for APD in that entire span - so investing_cash_flow/
        # financing_cash_flow were silently NULL for APD's whole recent history despite real
        # data being available. More broadly: of 1,887/1,925 filers that tag the financing/
        # investing ContinuingOperations concepts at all, 1,391/1,373 have at least one
        # individual fiscal year present ONLY under the ContinuingOperations tag (not just
        # APD - a widespread partial-year gap, not a single-filer quirk). Listed BEFORE the
        # plain concepts (this file's "last-listed wins on overwrite" convention) so a filer
        # that reports BOTH for the same fiscal year keeps the fuller plain-concept total
        # whenever it's actually present, same precedent as Operating above.
        "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
        "NetCashProvidedByUsedInInvestingActivities",
        "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
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
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
        # no_recent_free_cash_flow_reported continuation): equipment-rental filers' rental
        # fleet purchases - a standard (not filer-specific) us-gaap concept, never in this
        # fetch list at all. Live-confirmed via CTOS (Custom Truck One Source, $2.0B mkt
        # cap, CIK 1709682): $456,984,000 FY2025 / $398,317,000 FY2024 / $364,190,000
        # FY2023 (accession 0001709682-26-000008), plain non-dimensioned annual contexts -
        # the real, dominant capex line for a rental-fleet business model, plausible vs.
        # CTOS's known scale. A standard taxonomy element, likely generalizes to other
        # equipment-rental filers, not just CTOS. NOTE: CTOS also tags a smaller
        # (~$32-42M/yr) custom "ctos:PurchaseOfNonRentalPropertyAndCloudComputingArrangements"
        # concept, additive to this one - deliberately NOT added, since
        # CUSTOM_CAPEX_CONCEPTS entries are fallback-only (see
        # `_DEBT_FALLBACK_ONLY_FIELDS`'s "custom_extension_vessel_capex" entry in
        # load_financial_statements.py) and would be silently dropped once this plain
        # concept already populates "capex" -
        # summing across the two independent extraction paths would need a new mechanism,
        # not worth building for a ~7-9% single-symbol undercount.
        "PaymentsToAcquireEquipmentOnLease",
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
        # ADDED 2026-09-06 (goal session: "SEC/XBRL missing data to zero" sweep,
        # capex_never_tagged_in_recent_filings continuation, scored-symbol sample beyond the
        # earlier 2026-09-06 REIT sweep above): Tanger Inc (SKT, CIK 0000899715, real outlet-mall
        # REIT) reports NEITHER "PaymentsForCapitalImprovements" nor any other RealEstate/
        # PP&E-family concept above - live-confirmed via real companyfacts JSON its actual
        # property-improvement capex is tagged under this standard (not filer-specific) us-gaap
        # concept instead: $188.863M FY2023, $77.194M FY2024, $93.868M FY2025 (10-K, accession
        # confirmed via real end-dates) - plausible ~15-19% of SKT's real ~$500M annual revenue,
        # consistent with an outlet-center REIT's ongoing renovation/expansion spend, not a
        # placeholder. Standard taxonomy element, so likely generalizes beyond SKT even though
        # only this one filer was live-confirmed this session (same "standard concept, single
        # filer verified" precedent as PaymentsToDevelopRealEstateAssets/
        # PaymentsToAcquireCommercialRealEstate above).
        "RealEstateImprovements",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
        # no_recent_free_cash_flow_reported investigation): a standard (not filer-specific)
        # us-gaap concept for real-estate development spend, never in this fetch list at
        # all - live-confirmed via two REITs' real raw XBRL instance documents. DLR
        # (Digital Realty Trust, $62.4B mkt cap, CIK 1297996): $3,525,598,000 FY2023
        # (accession 0001558370-24-001575) / $2,831,740,000 FY2024 (accession
        # 0001558370-25-001424) / $3,181,179,000 FY2025 (accession 0001104659-26-015365) -
        # matches DLR's real data-center buildout scale, zero overlap with
        # PaymentsToAcquireRealEstate/PaymentsForDepositsOnRealEstateAcquisitions (both
        # already fetched above, both genuinely zero for DLR in these years). REG (Regency
        # Centers, $13.9B mkt cap): $435,112,000 FY2025 (accession 0001193125-26-051668) /
        # $343,368,000 FY2024 / $232,855,000 FY2023 - real, growing development spend for
        # a shopping-center REIT of REG's size. Plain (non-fallback) concept, same
        # convention as the other REIT concepts immediately above - a standard taxonomy
        # element, not filer-specific, so likely benefits other REITs beyond these two.
        "PaymentsToDevelopRealEstateAssets",
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
        # FIXED 2026-09-06 (goal: "capex_never_tagged_in_recent_filings" sweep across the
        # active universe, ~60 symbols live-checked across SIC 1040/2834/2836/6199/6282/
        # 6311/6331/6798 and BDC clusters): MRP (Millrose Properties, Inc., CIK 2017206) -
        # a land-banking REIT spun off from Lennar in Feb 2025 whose entire business model
        # is acquiring and optioning land to homebuilders - reports NEITHER
        # "PaymentsToAcquireRealEstate" nor any other RealEstate/Capital/PP&E-family
        # concept above at all. Live-confirmed via real companyfacts JSON: real, single-
        # year (only FY2025 exists post-spinoff) value of $858,938,000 under this concept,
        # plausible against MRP's own reported $9.258B total assets / $5.856B stockholders'
        # equity for the same fiscal year (accn 0002017206-26-000002) - the direct cash
        # equivalent of capex for a land-acquisition-as-core-business REIT, not an
        # investment-securities purchase. Standard (not filer-specific) us-gaap concept, so
        # likely generalizes to other land-banking-model filers even though only MRP was
        # live-confirmed this session (same "standard concept, single filer verified"
        # precedent as PaymentsToAcquireWaterAndWasteWaterSystems/CWT above). Everything
        # else checked this session in the same reason bucket (mortgage REITs like AGNC/
        # RITM/MFA/TWO/BXMT/PMT/IVR/EARN/MITT/RWT/RC, BDCs like MAIN/FSK/OBDC/TSLX/GSBD/
        # HRZN/PSBD/SAR, asset managers APO/ARES/KKR, insurers MFC/VOYA/BHF/WTM, and
        # pharma/biotech RIGL/VKTX/RPRX/XERS/GALT/AVIR/FENC/STRO/AVXL/etc.) only reports
        # investment-securities/loan/notes-receivable purchase concepts (e.g.
        # "PaymentsToAcquireInvestments", "PaymentsToAcquireAvailableForSaleSecuritiesDebt",
        # "PaymentsToAcquireMortgageBackedSecuritiesMBSCategorizedAsAvailableForSale") -
        # confirmed genuine, not a bug: these filers' investing activities are portfolio
        # securities/loan turnover, a fundamentally different economic activity from
        # capital expenditure, and adding them here would misrepresent free_cash_flow for
        # these business models. Not added.
        "PaymentsToAcquireLand",
        # FIXED 2026-09-09 (goal session: "capex_never_tagged_in_recent_filings" 86-symbol
        # sweep): mineral exploration/development-stage filers report capex under this
        # ifrs-full concept instead of any PP&E-family concept above - live-confirmed via
        # real companyfacts JSON across 2 independent filers. Lifezone Metals (LZM, CIK
        # 1958217, developing the Kabanga Nickel project in Tanzania): FY2025 $21,826,327 /
        # FY2024 $49,951,501 / FY2023 $51,355,297 (all 20-F), each closely tracking (~95-105%
        # of) the same fiscal year's real "CashFlowsFromUsedInInvestingActivities" total
        # (FY2025 $21,283,241 / FY2024 $52,659,817 / FY2023 $59,947,767) - i.e. this concept
        # is the dominant, not incidental, driver of LZM's investing outflow, not a minor
        # sub-line. Foremost Clean Energy (FMST, CIK 1935418): CAD 249,957 FY2024/24-25 /
        # CAD 198,829 prior FY - smaller scale but the same concept, confirming this is a
        # standard (not filer-specific) IFRS taxonomy element for the mineral-exploration
        # sector, not a coincidence specific to LZM. Per scripts/xbrl_concept_coverage_scan.py
        # (--grep Explor), 45 distinct filers in the on-disk companyfacts cache tag this
        # concept. This was the direct cause of LZM's dcf_fcf/fcf_margin/free_cash_flow
        # being stuck at "capex_never_tagged_in_recent_filings" despite real, current,
        # well-populated investing-activity data existing. Rejected for this same reason
        # bucket in the same investigation: TFPM's (Triple Flag Precious Metals)
        # semantically-similar "PaymentsForExplorationAndEvaluationExpenses" concept - only
        # $8.8M of TFPM's $218M FY2025 investing outflow (4%, genuinely $0 in FY2024), i.e.
        # a minor incidental sub-line for a royalty/streaming company whose real investing
        # activity is buying royalty interests (no PP&E), not a capex proxy worth adding -
        # correctly still missing_sec_data. Also rejected: Trilogy Metals' (TMQ)
        # "SignificantCostsIncurredToAcquireMineralInterestOfProvedReserves" - only 6 filers
        # use it and TMQ's own values are "since inception" cumulative totals (2003-12-01
        # through the period end), not per-fiscal-year durations, so aggregating by
        # fiscal_year would misattribute a 17-year cumulative figure as one year's capex;
        # TMQ's real recent-year investing activity is also genuinely near-zero (its Ambler
        # project capex is spent at the South32 joint-venture level, not on TMQ's own
        # balance sheet) - correctly left as no-capex, not a bug this concept addition
        # should paper over.
        "PurchaseOfExplorationAndEvaluationAssets",
        # FIXED 2026-09-09 (same sweep): "PaymentsToAcquireMineralRights" is a real,
        # standard (not filer-specific) us-gaap concept for cash paid to acquire mineral
        # rights/interests - never fetched at all despite being a substantial, common real
        # capex line (33 distinct filers tag it per the coverage scan). Live-confirmed via
        # real companyfacts JSON across large, well-known filers already in the broader
        # universe: Freeport-McMoRan $2,200,000,000, Royal Gold $1,164,753,000, Diamondback
        # Energy $444,083,000, Coeur Mining $116,898,000 - all real, current, substantial
        # 10-K figures, not noise. Also live-confirmed on Trilogy Metals (TMQ, one of this
        # session's 86 target symbols): real annual values through FY2021 ($119,000), though
        # TMQ's own capex genuinely goes to ~$0 from FY2022 onward (see the
        # PurchaseOfExplorationAndEvaluationAssets comment above for why that's a genuine
        # business-model change, not a missing-concept bug for TMQ specifically). Standard
        # taxonomy element, so this should recover other mining/oil-and-gas filers beyond
        # the ones checked live this session, not just TMQ.
        "PaymentsToAcquireMineralRights",
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
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, UBS/SPG/
        # PSA/HUBB/RS "real historical dividends_paid, stopped tagging any known concept"
        # audit): PSA (Public Storage, CIK 1393311) stopped tagging "DividendsCommonStock"/
        # "DividendsPreferredStock"-family concepts continuously after FY2017 (both keep
        # reappearing sporadically in later years but with real gaps - e.g. no
        # DividendsCommonStockCash fact at all for FY2018-2020/2023/2025) - live-confirmed
        # via real companyfacts JSON that "PaymentsOfCapitalDistribution" is tagged
        # continuously FY2009-2025 with no gaps and, in every year both concepts are
        # present (2010-2017, 2021, 2022), equals DividendsCommonStockCash +
        # DividendsPreferredStockCash to within rounding (e.g. FY2022: $3,908,497,000 vs.
        # $3,714,000,000 + $194,390,000 = $3,908,390,000) - the real combined common+
        # preferred total-distributions figure, not a narrower/different line. Standard
        # us-gaap concept (not a filer-specific extension), simply missing from this list
        # before now. Listed first/least-preferred (same "last-listed wins" convention as
        # this file's other fallback groups) so the more standard DividendsCommonStock*/
        # PaymentsOfDividends* concepts below win whenever a filer reports both.
        "PaymentsOfCapitalDistribution",
        # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit): BDCs
        # (business development companies) commonly tag distributions under this
        # investment-company-specific concept instead of, or in addition to, the standard
        # PaymentsOf*/DividendsCommonStock* family - live-confirmed TRIN (Trinity Capital,
        # CIK 1786108) tags ONLY this concept (no PaymentsOfDividends/DividendsCommonStock/
        # PaymentsOfCapitalDistribution at all), real values through FY2024 ($112.1M).
        # Listed first/least-preferred (same "last-listed wins" convention as this file's
        # other fallback groups): live-checked MAIN (CIK 1396440) tags BOTH concepts with
        # materially DIFFERENT, non-overlapping magnitudes (DividendsCommonStock $161M-
        # $378M vs this concept's $12M-$110M) - this is a narrower/different distribution
        # sub-component for filers that also report the real total elsewhere, not a
        # duplicate tag, so it must never win over a real DividendsCommonStock*/
        # PaymentsOfDividends* value.
        "InvestmentCompanyDividendDistribution",
        # ADDED 2026-09-09 (xbrl_concept_coverage_scan.py comment-leak fix follow-up: this
        # standard us-gaap concept was quoted in the PSA comment above describing what
        # PaymentsOfCapitalDistribution equals, but never actually fetched - 639 real filers
        # tag it (scan-confirmed post-fix). Fallback-only (_SBC_BUYBACK_FALLBACK_ONLY_FIELDS)
        # so it only fills dividends_paid for a preferred-only distributor (no common
        # dividend concept tagged at all, e.g. a mortgage REIT/BDC with only preferred stock
        # outstanding) - never overwrites a real DividendsCommonStock*/PaymentsOfDividends*
        # total, which would otherwise silently understate combined common+preferred
        # distributions if this simply won the ordinary last-listed-wins overwrite.
        "DividendsPreferredStockCash",
        "DividendsPreferredStock",
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
        # ADDED 2026-09-07 (goal: "SEC/XBRL missing data" + tie-out sweep): net_change_cash
        # has been a real, declared schema column on annual_cash_flow/quarterly_cash_flow/
        # ttm_cash_flow since this loader's creation, but NO concept was ever fetched for
        # it and no field_mapping entry ever targeted it - live-confirmed via direct DB
        # query, 0 of 66,580 annual_cash_flow rows have net_change_cash populated, for
        # every symbol, ever. Standard XBRL concept for "cash flow statement's total
        # change in cash for the period" comes in two generations: the plain pre-ASU-
        # 2016-18 concept (live-confirmed via AMZN's real companyfacts JSON: real values
        # FY2015-2017, e.g. $1,188,000,000 FY2017) and the post-ASU-2016-18 restricted-
        # cash-inclusive concept most large filers switched to afterward (live-confirmed
        # via AMZN again: real values every year since, e.g. $7,794,000,000 FY2025) - most
        # filers use exactly one of the two for any given fiscal year, not both, so listing
        # the modern concept last (this file's "last-listed wins on overwrite" convention)
        # lets it take priority for filers who report both in a transition year without
        # ever losing the plain concept's value for filers who never switched. Each has an
        # "ExcludingExchangeRateEffect" sibling for filers with no material FX translation
        # effect on cash - same target column, listed immediately before its "Including"
        # counterpart so the fuller (higher-priority, present-when-tagged) figure still
        # wins when a filer tags both.
        "CashAndCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect",
        "CashAndCashEquivalentsPeriodIncreaseDecrease",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
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
