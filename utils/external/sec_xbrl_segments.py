#!/usr/bin/env python3
"""SEC XBRL Segment Disclosure Parser (ASC 280 - Business Segment Reporting).

Extracts business segment data from SEC 10-K filings in XBRL format.

Two data sources, in order of preference:

1. companyfacts API (fetch_incremental's first attempt) - fast, single request,
   but can ONLY ever answer "how many segments does this company report"
   (NumberOfReportableSegments and similar simple concepts). It can NEVER answer
   "what did each segment earn" - confirmed against SEC's own companyfacts
   response shape (each fact is {val, fy, fp, accn, form, filed, frame, ...},
   with no field identifying which XBRL dimension/segment-member it belongs to).
   SEC's companyfacts/companyconcept/frames APIs only surface facts tied to a
   non-dimensional ("default") context; segment-dimensioned facts are excluded
   from these endpoints entirely, by design of the API, not as a bug in this
   parser. So parse_companyfacts() never attempts per-segment revenue and always
   reports it unavailable, honestly, up front.

2. Raw XBRL instance XML (fetch_incremental's fallback via
   SecEdgarClient.get_filing_xml, which resolves the real standalone instance
   document rather than the inline-XBRL .htm) - the only place per-segment
   revenue actually lives. Segment identity is expressed as a dimensional
   context: <xbrli:context> elements carry an <xbrldi:explicitMember
   dimension="...StatementBusinessSegmentsAxis">...SegmentMember</xbrldi:explicitMember>,
   and a plain revenue concept (RevenueFromContractWithCustomerExcludingAssessedTax
   in modern (post-ASC 606) filings, occasionally the older Revenues/SalesRevenueNet
   concepts) is tagged with a contextRef pointing at that dimensional context -
   there is no distinct "SegmentRevenue"-named concept. Verified against a real
   filing (Microsoft's FY2025 10-K instance document): matches the company's
   actual reported segment revenue exactly ($120.81B/$106.27B/$54.65B for
   Productivity and Business Processes / Intelligent Cloud / More Personal
   Computing). Falls back to the geographic axis (StatementGeographicalAxis) for
   filers that report segments by geography rather than business line.

ASC 280 requires disclosure of:
- Operating segments (reportable if >10% of consolidated revenue)
- Segment revenue, operating income, assets
- Geographic segments (if material)
- Major customer concentrations (>10% revenue)
"""

import logging
import re
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any, cast
from xml.etree import ElementTree as ET

from utils.external.fx_rates import MAJOR_CURRENCIES
from utils.external.sec_custom_xbrl_concepts import _fx_rate_cache, _parse_unit_currencies

logger = logging.getLogger(__name__)

# Standard us-gaap axes used for ASC 280 segment reporting. Axis *names* are
# stable across taxonomy years (unlike concept namespaces, which are versioned
# per year) - business-line segments take priority; geographic is the fallback
# for filers whose only reportable segments are geographic.
_BUSINESS_SEGMENT_AXIS = "StatementBusinessSegmentsAxis"
_GEOGRAPHIC_SEGMENT_AXIS = "StatementGeographicalAxis"
# ifrs-full's equivalent of StatementGeographicalAxis - confirmed live against AstraZeneca's
# (AZN, CIK 901832) real FY2025 20-F instance document: AZN tags NONE of the axes below
# (no SegmentsAxis, no StatementBusinessSegmentsAxis, no filer-specific extension) anywhere in
# its filing, but reports real per-country/region revenue (US $23.970B, China $6.636B, Japan
# $3.556B FY2025, ...) under this axis with the plain "Revenue" concept (already in
# _REVENUE_CONCEPT_LOCAL_NAMES below) - summing "OutsideUnitedKingdomMember" ($54.380B) +
# country:GB ($4.359B) = $58.739B, consistent with AZN's real known consolidated revenue scale.
# Real segment-level operating income (ProfitLossFromOperatingActivities) is tagged the same
# way. Before this fix AZN fell through to "no_segment_dimension_contexts_in_xbrl_xml" despite
# having rich, real, machine-readable geographic segment data on file - not a structural
# absence like ARGX (see _IFRS_SEGMENTS_AXIS's comment). SAP's own gap
# (azn_sap_segment_fix_claimed_live_confirmed_but_not_reproducing_20260901 in memory) is
# unrelated - SAP DOES tag SegmentsAxis, its issue is a missing revenue concept, not axis
# recognition.
_IFRS_GEOGRAPHIC_SEGMENT_AXIS = "GeographicalAreasAxis"
# ifrs-full's equivalent of StatementBusinessSegmentsAxis, used by foreign
# private issuers filing 20-F under IFRS 8 rather than 10-K under ASC 280.
# Confirmed live against BP's FY2025 20-F (CIK 313807): real segment revenue
# (RevenueAndOperatingIncome) is tagged per member of this axis - Gas & Low
# Carbon Energy $38.501B, Oil Production & Operations $1.651B, Customers &
# Products $148.740B, summing to $188.892B vs BP's own plain consolidated
# RevenueAndOperatingIncome total of $189.335B (0.23% residual, comfortably
# inside the existing cross-tab reconciliation tolerance) - these are BP's
# real reported segments, not a coincidence. Before this fix, EVERY IFRS/20-F
# filer with real machine-readable segment data (also confirmed live: Shell,
# Sony, Toyota, Rio Tinto, BHP, Sanofi, Novartis, Novo Nordisk, AstraZeneca,
# GSK, TotalEnergies, SAP, Diageo, AB InBev - 15+ symbols) fell through to
# "no_segment_dimension_contexts_in_xbrl_xml" purely because this axis wasn't
# in the recognized set, not because the data doesn't exist. (Separately
# confirmed some single-segment IFRS filers, e.g. ARGX, genuinely tag no
# SegmentsAxis contexts at all - that class is still correctly reported
# unavailable, this fix only recovers filers that DO tag it.)
_IFRS_SEGMENTS_AXIS = "SegmentsAxis"

# BBVA's own filer-specific extension axis (not a shared ifrs-full/us-gaap concept) -
# confirmed live against BBVA's FY2025 20-F (CIK 842180): BBVA tags NONE of the three
# axes above anywhere in its instance document at all, but its real per-segment income
# ("Note 6 Main margins and profit by operating segments") is tagged under this axis
# with single-letter ISO country-style members (ES/MX/TR - Spain/Mexico/Turkey, BBVA's
# real reportable segments), paired with a `GrossProfit`-labeled concept (see
# `_AXIS_SPECIFIC_EXTRA_REVENUE_CONCEPTS` below for why that concept is trusted ONLY
# under this specific axis, not added to the general `_REVENUE_CONCEPT_LOCAL_NAMES`
# list). Lowest priority (after geographic) since it's a narrow, single-filer-family
# extension, not a general-purpose taxonomy axis like the three above.
_FILER_SPECIFIC_INCOME_SEGMENT_AXIS = "IncomeByOperatingSegmentAxis"

_SEGMENT_AXIS_LOCAL_NAMES = (
    _BUSINESS_SEGMENT_AXIS,
    _IFRS_SEGMENTS_AXIS,
    _GEOGRAPHIC_SEGMENT_AXIS,
    _IFRS_GEOGRAPHIC_SEGMENT_AXIS,
    _FILER_SPECIFIC_INCOME_SEGMENT_AXIS,
)

# Standard (non-filer-specific) us-gaap companion axis some filers pair with a
# segment axis purely to mark "this is a real reportable-operating-segment
# figure" as opposed to the corporate/elimination reconciling line
# (ConsolidationItemsAxis=MaterialReconcilingItemsMember) - confirmed live
# against Coca-Cola's FY2025 10-K, where segment revenue is ONLY ever tagged as
# (ConsolidationItemsAxis=OperatingSegmentsMember, StatementBusinessSegmentsAxis=
# <segment>), never as a plain single-dimension segment context. This is not a
# further breakdown of the segment total (unlike a geography or product-line
# axis paired with the segment axis - see _index_segment_contexts), so a
# context carrying exactly this companion dimension alongside the segment axis
# still counts as "single dimension" for that purpose.
#
# SegmentConsolidationItemsAxis is ifrs-full's equivalent - confirmed live
# against BP's FY2025 20-F: every real segment-revenue context pairs
# SegmentsAxis=<segment> with SegmentConsolidationItemsAxis=OperatingSegmentsMember
# (same member name as the us-gaap convention), never a plain single-dimension
# SegmentsAxis context.
_CONSOLIDATION_ITEMS_AXIS = "ConsolidationItemsAxis"
_IFRS_SEGMENT_CONSOLIDATION_ITEMS_AXIS = "SegmentConsolidationItemsAxis"
_CONSOLIDATION_ITEMS_AXIS_NAMES = (_CONSOLIDATION_ITEMS_AXIS, _IFRS_SEGMENT_CONSOLIDATION_ITEMS_AXIS)
_OPERATING_SEGMENTS_MEMBER = "OperatingSegmentsMember"

# FIXED 2026-09-02 (goal: "missing SEC/XBRL data" audit, live SEC EDGAR verification of the
# azn_sap_segment_fix memory's SAP "no_segment_revenue_in_xbrl_xml" discrepancy). SAP's own
# custom extension axis (confirmed live: SAP SE's FY2025 20-F, CIK 1000184, accession
# 0001104659-26-020058, raw XBRL instance sap-20251231x20f_htm.xml) tags every real
# segment-total context with a THIRD dimension beyond SegmentsAxis+SegmentConsolidationItemsAxis:
# sap:IfrsScenarioAxis=sap:ActualCurrencyMember (vs. a parallel, non-additive
# ConstantCurrencyMember variant using prior-year FX rates for the same fact - deliberately
# NOT stripped here, so those 3-dimension-after-stripping contexts still fail the len==1 check
# below and are correctly excluded, avoiding a duplicate/wrong-basis value for the same
# segment/period). Like OperatingSegmentsMember, this doesn't narrow the fact to a finer
# sub-breakdown of the segment - it's a reporting-basis marker - so it's stripped the same way
# before judging dimension count. Verified: with this axis-pair also treated as boilerplate,
# ifrs-full:Revenue at SegmentsAxis=sap:ApplicationsTechnologyAndSupportMember (Actual
# Currency, FY2025) = EUR32.847B and at SegmentsAxis=sap:CoreServicesMember (Actual Currency,
# FY2025) = EUR3.953B, summing to EUR36.800B - exactly SAP's own reported consolidated "Total
# revenue" for FY2025 (R119.htm "Results of Segments (Details)"). Matched by local name only,
# consistent with this file's namespace-agnostic convention elsewhere - low false-match risk
# since "IfrsScenarioAxis" is a non-standard extension axis name, not part of the ifrs-full
# taxonomy, that only an actual/constant-currency-reporting filer would plausibly define.
_IFRS_SCENARIO_AXIS = "IfrsScenarioAxis"
_ACTUAL_CURRENCY_MEMBER = "ActualCurrencyMember"

# General list of (axis-name-candidates, member-name) pairs that mark "this is the segment's
# own reportable total under some reporting convention", not a further breakdown - stripped
# before judging whether a context is single-dimension (see _index_segment_contexts).
_BOILERPLATE_AXIS_MEMBER_PAIRS: tuple[tuple[tuple[str, ...], str], ...] = (
    (_CONSOLIDATION_ITEMS_AXIS_NAMES, _OPERATING_SEGMENTS_MEMBER),
    ((_IFRS_SCENARIO_AXIS,), _ACTUAL_CURRENCY_MEMBER),
)

# Combined parent+subsidiary co-registrant filings (e.g. NextEra Energy/Florida
# Power & Light, both SEC registrants sharing one 10-K) tag facts belonging to
# the subsidiary registrant with dei:LegalEntityAxis, in addition to whatever
# segment axis identifies the same business line. Confirmed live against NEE's
# FY2025 10-K: FPL's segment-revenue context carries BOTH
# StatementBusinessSegmentsAxis=FloridaPowerLightCompanyMember AND
# LegalEntityAxis=FloridaPowerLightCompanyMember (identical member on both) -
# this is entity identity, not a further breakdown of the segment (unlike a
# geography or product-line axis paired with the segment axis), so it's
# stripped in _index_segment_contexts when its member matches the segment
# axis's own member in the same context.
_LEGAL_ENTITY_AXIS = "LegalEntityAxis"

# Standard us-gaap StatementBusinessSegmentsAxis member (part of the ASU 2023-07
# segment-reporting taxonomy) marking a SUBTOTAL of all reportable segments before
# adding "All Other" - not a real segment itself. Confirmed live against
# Caterpillar's FY2025 10-K: this member's tagged value ($73.955B) exactly equals
# the sum of CAT's 4 real reportable segments (Construction Industries $25.060B +
# Resource Industries $12.474B + Power Energy $32.201B + Financial Products
# $4.220B) - counting it as a peer "segment" alongside its own components would
# roughly double the true total and corrupt every HHI/concentration figure.
# FIXED 2026-09-02 (goal: "missing SEC/XBRL data" audit, live SEC EDGAR verification):
# "ReportableSegmentsMember" is the standard ASU 2023-07 taxonomy member for the SAME
# "subtotal before All Other" shape as ReportableSegmentAggregationBeforeOtherOperatingSegmentMember
# above - live-confirmed against Corning's (GLW) real FY2025 10-K instance document: this
# member's tagged NetSalesOfReportableSegmentsAndAllOther value ($14.948B) exactly equals
# the sum of GLW's 5 real reportable segments (Optical Communications $6.274B + Display
# $3.697B + Specialty Materials $2.211B + Automotive $1.794B + Life Science $0.972B),
# excluding its 6th "All Other" segment (Hemlock and Emerging Growth Businesses, $1.460B) -
# same double-counting risk as the CAT case if left uncaught, and (unlike the
# GLW-specific NetSalesOfReportableSegmentsAndAllOther concept added alongside this) a
# standard taxonomy member name, so this generalizes to any other ASU 2023-07 filer using it.
_NON_SEGMENT_SUBTOTAL_MEMBERS = (
    "ReportableSegmentAggregationBeforeOtherOperatingSegmentMember",
    "ReportableSegmentsMember",
)

# Revenue concepts to try, in preference order. Segment revenue is tagged using
# the SAME concept as consolidated revenue - just against a dimensioned context -
# so this list is really "which revenue concept does this filer use at all",
# checked most-specific (post-ASC-606 contract revenue) to least.
#
# RevenuesNetOfInterestExpense: banks/financial institutions (verified live
# against JPMorgan Chase's FY2025 10-K) don't tag plain Revenues at the
# per-segment level - they tag this concept instead (NoninterestIncome +
# InterestIncomeExpenseNet, the standard bank-holding-company income-statement
# framing). Confirmed the extracted per-segment values match JPM's real
# reported segment revenue: Consumer & Community Banking $76.0B, Commercial &
# Investment Bank $78.5B, Asset & Wealth Management $24.1B (FY2025). Tried
# last since it's specific to this one sector, not a general fallback.
_REVENUE_CONCEPT_LOCAL_NAMES = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",
    # RegulatedAndUnregulatedOperatingRevenue: regulated utilities (verified live
    # against NextEra Energy's FY2025 10-K) tag segment revenue under this
    # concept rather than Revenues - FPL (regulated) $18.262B, NEER (unregulated)
    # $8.760B, matching the real reported segment split.
    "RegulatedAndUnregulatedOperatingRevenue",
    # RevenuesNetOfInterestExpenseFullTaxEquivalentBasis: a company-specific
    # extension concept (bac: namespace, not us-gaap:) - Bank of America's own
    # FY2025 10-K tags segment revenue this way rather than the standard
    # RevenuesNetOfInterestExpense JPMorgan uses. Matching is by local name only
    # (see _local_name usage below), so a custom-namespace concept works the
    # same as a standard one. Verified: Consumer Banking $43.673B, GWIM
    # $24.883B, Global Banking $24.108B, Global Markets $24.096B, Corporate/
    # Eliminations -$3.054B (excluded by the existing negative-value filter)
    # sum to exactly BAC's real $113.706B consolidated revenue. Tried last -
    # a custom extension name is inherently filer-specific, not a candidate
    # any other filer would plausibly also use.
    "RevenuesNetOfInterestExpenseFullTaxEquivalentBasis",
    # PremiumsEarnedNet: insurers (verified live against AIG's FY2025 10-K) tag
    # segment-level revenue as net earned premiums, not Revenues - AIG's own
    # SupplementaryInsuranceInformationPremiumRevenue concept carries the
    # identical value at the same contexts, confirming this is the real
    # segment-level revenue figure, not a coincidence. North America $8.626B,
    # International $8.580B, Global Personal Travel Insurance $6.472B sum to
    # within 0.3% of AIG's real $23.751B consolidated revenue (a small
    # unallocated-corporate residual, same shape as NEE's). Tried last -
    # sector-specific, like the two revenue concepts above it.
    "PremiumsEarnedNet",
    # RevenueAndOperatingIncome/RevenueFromSaleOfGoods: ifrs-full segment-level
    # revenue concepts for IFRS/20-F filers (verified live: BP's FY2025 20-F tags
    # the former - see _IFRS_SEGMENTS_AXIS above; Sanofi's FY2025 20-F tags the
    # latter, its single BiopharmaSegmentMember context matching its own plain
    # consolidated RevenueFromSaleOfGoods total, $43.626B, exactly). Tried last -
    # taxonomy-family fallbacks, only reached when none of the us-gaap concepts
    # above matched anything.
    "RevenueAndOperatingIncome",
    "RevenueFromSaleOfGoods",
    # FIXED 2026-08-29 (goal: "full data" audit continuation, IFRS segment-revenue
    # follow-up to the SegmentsAxis fix in 821c120ef): that fix made the parser correctly
    # find SegmentsAxis-dimensioned contexts for many more IFRS/20-F filers, but 5 of the
    # majors checked (SHEL/RIO/DEO/UL/TTE) still landed on "no_segment_revenue_in_xbrl_xml"
    # because none of the concepts above matched their segment-note tagging. Pulled each
    # filer's actual filed XBRL segment-note report (FilingSummary.xml -> R-file, not
    # companyfacts) to find the real concept: SHEL's "Segment information" R93.htm, RIO's
    # "Financial performance by segment" R100.htm ("Segmental revenue"), DEO's "Segmental
    # information" R56.htm ("Sales"), and UL's "Segment information" R68.htm ("Turnover")
    # all tag "ifrs-full:Revenue" - the taxonomy's plain top-line concept, not one of the
    # more specific fallbacks already covered. Verified plausible consolidated-level values
    # via companyfacts for all 4: SHEL $266.886B FY2025, RIO $57.638B FY2025, DEO $27.964B
    # FY2025 (USD; also reports in GBP), UL EUR50.503B FY2025 - all match each company's
    # real, publicly known revenue scale. TTE's "Business segment information" R51.htm
    # tags "ifrs-full:RevenueFromContractsWithCustomers" instead (note plural "Contracts",
    # a genuinely distinct IFRS concept from us-gaap's already-covered singular
    # "RevenueFromContractWithCustomerExcludingAssessedTax" above, not a duplicate/typo) -
    # $201.196B FY2025, matches TotalEnergies' real revenue scale. Both listed last
    # (lowest priority, per this list's "first match wins" convention - opposite of
    # sec_statements.py's "last-listed wins") since "Revenue" in particular is IFRS's most
    # generic top-line concept and should only be reached once every more specific
    # us-gaap/IFRS concept above has already been tried and failed to match.
    "RevenueFromContractsWithCustomers",
    "Revenue",
    # FIXED 2026-09-02 (goal: "missing SEC/XBRL data" audit, live SEC EDGAR verification):
    # Corning's (GLW, CIK 24741) own filer-specific extension concept for segment-level net
    # sales - live-confirmed against GLW's real FY2023 10-K instance document
    # (glw-20251231_htm.xml, tagged under the glw: namespace, matched here by local name
    # only per this file's existing namespace-agnostic convention): Optical Communications
    # $4.012B, Display $3.532B, Specialty Materials $1.865B, Automotive $1.893B, Life
    # Science $0.959B, summing with the filing's own "Hemlock and Emerging Growth
    # Businesses" line ($1.319B) to its own tagged "ReportableSegmentsMember"+"All Other"
    # subtotal of $13.580B - internally consistent, real per-segment sales, not a
    # coincidence. Same low-collision-risk rationale as the existing BAC-specific
    # RevenuesNetOfInterestExpenseFullTaxEquivalentBasis entry above: a private filer
    # extension name only that one filer would plausibly define, safe to trust unreconciled
    # like the rest of this list. Before this fix GLW fell through to
    # "no_segment_revenue_in_xbrl_xml" despite having complete real segment revenue on
    # file, purely because this concept wasn't in the recognized set.
    "NetSalesOfReportableSegmentsAndAllOther",
    # FIXED 2026-09-02 (goal: "missing SEC/XBRL data" audit, live SEC EDGAR verification):
    # American Homes 4 Rent's (AMH, CIK 1562401) own extension concept for its single
    # reportable segment's revenue - live-confirmed against AMH's real FY2025 10-K instance
    # document: tags NumberOfReportableSegments=1 and its ONLY revenue-shaped fact anywhere
    # in the filing is amh:CoreRevenues, dimensioned under
    # StatementBusinessSegmentsAxis=ReportableSegmentMember (the standard ASU 2023-07 generic
    # single-segment member name) - no plain, non-dimensioned "Revenues"/
    # "RevenueFromContractWithCustomerExcludingAssessedTax" fact exists anywhere in the
    # filing for _extract_single_segment_revenue's fallback to find either. Values ($1.609B
    # FY2025, $1.507B FY2024, $1.408B FY2023 - a plausible, consistent ~7%/yr growth trend)
    # match AMH's real, publicly known revenue scale. Same low-collision-risk filer-extension
    # rationale as the GLW/BAC entries above.
    "CoreRevenues",
    # FIXED 2026-09-02 (goal: "SEC/XBRL missing data" audit, live SEC EDGAR verification):
    # APA Corporation's (APA, CIK 1841666) own extension concept (apachecorp.com: namespace,
    # matched here by local name only per this file's existing convention) for segment-level
    # revenue including realized hedging gains/losses. Live-confirmed against APA's real
    # FY2025 10-K instance document: tagged directly under StatementBusinessSegmentsAxis
    # (paired only with the standard ConsolidationItemsAxis=OperatingSegmentsMember
    # boilerplate _index_segment_contexts already strips), so this resolves via the PRIMARY
    # single-axis path, not even needing the cross-tab/component-sum fallbacks. Segment
    # values (US $5.541B, Egypt $2.637B, North Sea $0.773B) sum to EXACTLY APA's own plain
    # consolidated total for all 3 fiscal years on file: FY2025 $8.951B, FY2024 $9.739B,
    # FY2023 $8.327B (0% reconciliation error, not just within tolerance). Before this fix,
    # APA fell through to "no_segment_revenue_in_xbrl_xml" because the loader was matching a
    # DIFFERENT, unrelated "Revenues" concept instead - APA also tags oil/gas/NGL revenue by
    # segment cross-tabbed with ProductOrServiceAxis/ReserveQuantitiesByTypeOfReserveAxis
    # under the standard "Revenues" concept (a finer sub-breakdown including purchased
    # volumes, correctly excluded by _index_segment_contexts' multi-axis filter) - this
    # extension concept is the real, complete, ASC 280-reportable segment total.
    "RevenuesAndRealizedGainsLossesOnDerivativeInstruments",
    # FIXED 2026-09-02 (goal: "SEC/XBRL missing data" audit, live SEC EDGAR verification,
    # systematic scan of the no_segment_revenue_in_xbrl_xml bucket following the APA fix
    # above): JBG SMITH Properties' (JBGS, CIK 1689796) own extension concept
    # (jbgsmith.com: namespace) for segment-level property revenue. Live-confirmed against
    # JBGS's real FY2025 10-K instance document, tagged directly under
    # StatementBusinessSegmentsAxis (paired only with the standard ConsolidationItemsAxis
    # boilerplate) - sums EXACTLY to JBGS's own plain consolidated PropertyRevenue for all 3
    # fiscal years on file: FY2025 $433.180M (MultiFamily $205.937M + Commercial $227.243M),
    # FY2024 $465.664M, FY2023 $517.887M - 0% reconciliation error. Before this fix JBGS fell
    # through to "no_segment_revenue_in_xbrl_xml" despite having complete, real segment
    # revenue on file.
    "PropertyRevenue",
    # FIXED 2026-09-02 (same scan as JBGS above): Tredegar Corporation's (TG, CIK 850429) own
    # extension concept (tredegar.com: namespace) for segment-level net sales. Live-confirmed
    # against TG's real FY2025 10-K instance document, tagged directly under
    # StatementBusinessSegmentsAxis (paired only with the standard ConsolidationItemsAxis
    # boilerplate) - sums EXACTLY to TG's own plain consolidated NetSales for all 3 fiscal
    # years on file: FY2025 $698.731M (Aluminum Extrusions $598.975M + PE Films $99.756M),
    # FY2024 $577.014M, FY2023 $551.566M - 0% reconciliation error.
    "NetSales",
)

# `ifrs-full:GrossProfit` is deliberately NOT in _REVENUE_CONCEPT_LOCAL_NAMES above, even
# though it's confirmed live (BBVA's FY2025 20-F: Spain EUR10.027B, Mexico EUR15.198B,
# Turkey EUR5.213B, matching BBVA's own reported "Gross profit" segment table exactly;
# Santander's FY2025 20-F: plain consolidated GrossProfit EUR58.670B matches its own
# "Total income" line exactly) to be how these Spanish IFRS banks tag their bank-specific
# "total income" segment measure. Unlike every other concept in the main list,
# `GrossProfit` is a genuinely common, generic concept for retail/manufacturing/industrial
# filers meaning Revenue minus COGS - a real, much SMALLER number than total revenue for
# any normal company. Adding it to the general list (searched, unreconciled, under any of
# the three standard axes) would risk silently corrupting segment revenue/HHI for some
# OTHER filer that tags genuine COGS-based gross profit under a segment axis. It's only
# trusted here, scoped to the one axis whose NAME itself asserts "this is per-operating-
# segment income data" (see `_FILER_SPECIFIC_INCOME_SEGMENT_AXIS`) - see
# `_AXIS_SPECIFIC_EXTRA_REVENUE_CONCEPTS` below for how this scoping is actually enforced.
_AXIS_SPECIFIC_EXTRA_REVENUE_CONCEPTS: dict[str, tuple[str, ...]] = {
    _FILER_SPECIFIC_INCOME_SEGMENT_AXIS: ("GrossProfit",),
}

# Santander (FY2025 20-F) tags the SAME GrossProfit-as-segment-income pattern as BBVA, but
# cross-tabbed under the STANDARD SegmentsAxis (paired with SegmentConsolidationItemsAxis/
# SegmentItemsAxis) rather than a single-dimension filer-specific axis - so the axis-name-
# based trust above can't reach it (it only fires in the primary single-dimension scan).
# _extract_cross_tab_segment_revenue is a SEPARATE, already-safe mechanism: every candidate
# it finds is reconciled against the filer's own plain consolidated total for the SAME
# concept before being trusted (see its docstring) - that reconciliation, not axis-name
# scoping, is what makes trying a generic concept like GrossProfit safe here. Confirmed
# live: Santander's plain consolidated GrossProfit (EUR58.670B FY2025) matches its own
# reported "Total income" line exactly, so this concept reconciles cleanly once tried.
# Deliberately NOT added to _REVENUE_CONCEPT_LOCAL_NAMES itself - that list is also used
# unreconciled by the primary scan and by _extract_single_segment_revenue, where the same
# false-match risk that keeps it out of the axis-agnostic list still applies.
_CROSS_TAB_ONLY_EXTRA_REVENUE_CONCEPTS = ("GrossProfit",)

# Standard us-gaap ConsolidationItemsAxis members marking a reconciling/adjustment
# line rather than a real component of a segment's own reportable revenue - used by
# the cross-tab reconciliation fallback (see _extract_cross_tab_segment_revenue) to
# exclude these from the sum. Confirmed live against Exxon Mobil's FY2023-2025 10-Ks:
# "intersegment sales elimination" facts are tagged under
# ConsolidationItemsAxis=IntersegmentEliminationMember alongside the same geography
# axis used for real revenue breakdown facts - summing them in would silently corrupt
# the total.
_NON_ADDITIVE_CONSOLIDATION_MEMBERS = ("IntersegmentEliminationMember", "MaterialReconcilingItemsMember")

# Tolerance for validating a cross-tab reconciled segment-revenue candidate against
# the filer's own plain (non-dimensioned) consolidated revenue fact for the same
# period. 3% comfortably covers a small unallocated "Corporate/Financing" residual
# (confirmed live: Exxon's reconciliation lands within 0.3-0.5% every year) while
# still rejecting a wrong-axis-combo candidate, which is typically off by double
# digits or more (e.g. XOM's plain geography-only total, gross of intersegment
# sales, overstates the real total by ~36%).
_CROSS_TAB_RECONCILIATION_TOLERANCE = 0.03

# Bank/thrift holding companies (verified live against BOK Financial's, Ameris
# Bancorp's, and Arbor Realty Trust's FY2025 10-K instances - a super-regional bank,
# a community bank, and a mortgage REIT, three genuinely different sub-industries
# hitting the identical pattern) tag segment-level revenue as these two SEPARATE
# standard us-gaap concepts rather than any single combined revenue-shaped concept
# in _REVENUE_CONCEPT_LOCAL_NAMES - "net interest income + noninterest income" is the
# standard bank-industry income-statement equivalent of "total revenue". Distinct
# from JPMorgan/Bank of America's pattern (a single already-combined
# RevenuesNetOfInterestExpense-family concept, already covered above): these three
# filers tag no such combined concept at the segment level at all, only the two
# components - _extract_component_sum_segment_revenue sums them and reconciles the
# result the same way _extract_cross_tab_segment_revenue does. Order matters here
# (unlike _REVENUE_CONCEPT_LOCAL_NAMES's "first match wins" list): the first concept
# is the anchor used to discover which segment members and fiscal period exist at
# all, the second is looked up only for members the anchor already found.
_BANK_REVENUE_COMPONENT_CONCEPTS = ("InterestIncomeExpenseNet", "NoninterestIncome")

# FIXED 2026-09-03 (goal: SEC/XBRL missing-data sweep, "sec_segment_info" biggest-bucket
# investigation): alternative asset managers (confirmed live: Blackstone's real FY2025
# 10-K instance, CIK 1393818) tag segment revenue as FOUR separate custom-namespace
# fee-line concepts instead of any us-gaap Revenues-family concept - real segment
# reporting (49 genuine StatementBusinessSegmentsAxis-dimensioned contexts for
# Blackstone's 4 real segments: RealEstateSegmentMember/PrivateEquitySegmentMember/
# CreditAndInsuranceMember/MultiAssetInvestingMember), just under filer-specific
# extension concepts, not a missing-data gap. Verified EXACT (to the dollar) against
# Blackstone's own published "Total Segment Revenues" footnote in its real FY2025 10-K
# (R115.htm/R116.htm renderings, both fetched directly from sec.gov): live raw-XBRL
# fact values for FY2025 (in raw dollars) - ManagementAndAdvisoryFeesNet=8,016,049,000
# + FeeRelatedPerformanceRevenues=1,825,428,000 + PerformanceRevenueRealized=
# 2,815,529,000 + RealizedPrincipalInvestmentIncomeLoss=419,743,000 = 13,076,749,000,
# matching Blackstone's own reported "Total Segment Revenues" for Operating Segments
# to the dollar - not an approximation.
#
# Unlike _BANK_REVENUE_COMPONENT_CONCEPTS (universal us-gaap concepts any bank can tag),
# these are Blackstone's own custom-namespace extension concepts - non-transferable to
# other alternative asset managers (Ares/Apollo/KKR/Carlyle each use their own custom
# namespace and, potentially, a different component breakdown, none verified here) -
# this list intentionally stays scoped to the concepts actually verified against a
# real filing, not generalized from Blackstone's shape alone.
_ALT_ASSET_MANAGER_REVENUE_COMPONENT_CONCEPTS = (
    "ManagementAndAdvisoryFeesNet",
    "FeeRelatedPerformanceRevenues",
    "PerformanceRevenueRealized",
    "RealizedPrincipalInvestmentIncomeLoss",
)

# ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, segment-reporting
# deep-dive): Federal Agricultural Mortgage Corporation ("Farmer Mac") tags segment-level
# revenue as GROSS interest income and interest expense requiring subtraction, unlike
# _BANK_REVENUE_COMPONENT_CONCEPTS's already-netted anchor - see
# _extract_gse_net_interest_income_segment_revenue's own docstring for the to-the-dollar
# live verification. AGM and AGM.A are both Farmer Mac (CIK 0000845877, common stock and
# Class A voting stock respectively) - verified live via SEC's own symbol_to_cik. AGMB
# ("AgomAb Therapeutics NV", CIK 0002020932) and AGMH ("AGM Group Holdings Inc.", CIK
# 0001705402) merely share a similar-looking ticker prefix and are NOT Farmer Mac -
# confirmed live via each symbol's own real entityName before assuming ticker similarity
# implied the same company. Deliberately excluded: this function is a no-op safety net for
# them either way (it checks for Farmer Mac's own concept names, absent from their real
# filings, so it would just fall through to the next tier) but listing them here would be
# actively misleading to a future reader.
_GSE_NET_INTEREST_INCOME_SEGMENT_SYMBOLS = frozenset({"AGM", "AGM.A"})
_GSE_NET_INTEREST_INCOME_CONCEPTS = ("InterestAndDividendIncomeOperating", "InterestExpenseOperating")

# The dimension/member Blackstone uses for its own "Operating Segments" (pre-
# consolidation-adjustment) aggregate - live-confirmed in the raw XBRL instance as a
# context with EXACTLY this one explicitMember (no StatementBusinessSegmentsAxis) - the
# coarser anchor _extract_alt_asset_manager_segment_revenue reconciles the summed
# per-segment total against, since no truly plain (zero-dimension) fact exists for any
# of the four concepts above.
_OPERATING_SEGMENTS_AGGREGATE_DIMENSION = "ConsolidationItemsAxis"
_OPERATING_SEGMENTS_AGGREGATE_MEMBER = "OperatingSegmentsMember"

# FIXED 2026-09-03 (goal: SEC/XBRL missing-data sweep, Ares Management follow-up to the
# Blackstone fix above): confirmed live via Ares's real FY2025 10-K instance (CIK 1176948,
# accession 0001628280-26-011413) - a DIFFERENT shape from Blackstone's, deliberately NOT
# generalized into the shared boilerplate-stripping mechanism (_BOILERPLATE_AXIS_MEMBER_PAIRS)
# because `ConsolidatedEntitiesAxis=ParentCompanyMember` is a standard SRT dimension that,
# for OTHER filers (e.g. holding companies with genuine parent-only vs. consolidated-
# subsidiary Rule 3-10 disclosures), can legitimately mean a PARTIAL, non-consolidated
# figure - checked KKR/Apollo/Carlyle's own real FY2025 10-K instances too and NONE of them
# use this exact combo, so there is no multi-filer evidence this convention generalizes
# safely. Scoped narrowly to Ares's own exact, verified shape instead - this extractor can
# only ever fire when ALL of the specific concept names and axis combination below match,
# so it cannot silently mis-extract data for any other filer.
#
# Ares tags real segment revenue as the STANDARD `RevenueFromContractWithCustomerExcludingAssessedTax`
# concept (already in _REVENUE_CONCEPT_LOCAL_NAMES) cross-tabbed by
# `srt:ProductOrServiceAxis` (ManagementServiceMember/FeeRelatedPerformanceRevenuesMember/
# ServiceOtherMember) - each context ALSO carries `srt:ConsolidatedEntitiesAxis=
# ParentCompanyMember` alongside the already-recognized `ConsolidationItemsAxis=
# OperatingSegmentsMember` boilerplate marker, which is why the generic cross-tab fallback
# above doesn't already find it (_index_segment_contexts's boilerplate-stripping only
# recognizes the latter, not ConsolidatedEntitiesAxis=ParentCompanyMember). PLUS a fourth,
# separately-tagged additive component (`PerformanceFeesRealizedRevenue`, Ares's own
# custom-namespace concept) carrying the same ConsolidatedEntitiesAxis+ConsolidationItemsAxis
# pairing but NOT the ProductOrServiceAxis. Verified EXACT (to the dollar) against Ares's own
# published FY2025 "Total segment revenues" (R93.htm "Schedule of Segment Revenue Expenses
# and Realized Net Investment Income (Expense) (Details)"): the 3 ProductOrServiceAxis
# components (Management fees $3,682,922,000 + Fee related performance revenues
# $301,309,000 + Other fees $245,103,000) + Performance income-realized $526,284,000 =
# $4,755,618,000, matching to the dollar.
_ARES_STYLE_ENTITIES_DIMENSION = "ConsolidatedEntitiesAxis"
_ARES_STYLE_ENTITIES_MEMBER = "ParentCompanyMember"
_ARES_STYLE_REVENUE_CONCEPT = "RevenueFromContractWithCustomerExcludingAssessedTax"
_ARES_STYLE_ADDITIVE_CONCEPT = "PerformanceFeesRealizedRevenue"

# ASC 280 also requires segment operating income and assets "if regularly
# provided to the CODM" - unlike revenue, not every filer discloses these by
# segment (verified live: MSFT and AAPL tag OperatingIncomeLoss per segment but
# never Assets; AMZN tags both). OperatingIncomeLoss is a duration concept like
# revenue (matched on the same end date + duration); Assets is an instant
# (balance-sheet) concept, so it only has an end date, no duration.
_OPERATING_INCOME_CONCEPT_LOCAL_NAMES = ("OperatingIncomeLoss",)
_ASSETS_CONCEPT_LOCAL_NAMES = ("Assets",)

# ASU 2023-07 requires every filer, even ones with a single reportable segment,
# to disclose the count via one of these concepts. Confirmed live: Gilead,
# Regeneron, United Airlines Holdings, and Realty Income all tag
# NumberOfReportableSegments/NumberOfOperatingSegments=1 as a plain
# (non-dimensioned) fact, with zero or incomplete segment-dimensioned revenue
# facts anywhere in the filing (a single segment's revenue is just the
# consolidated total, so filers don't bother re-tagging it per-segment). Used
# by _extract_single_segment_revenue as the last fallback before declaring
# data_unavailable.
_SEGMENT_COUNT_CONCEPT_LOCAL_NAMES = ("NumberOfReportableSegments", "NumberOfOperatingSegments")


def _local_name(tag: str) -> str:
    """Strip the Clark-notation namespace from an ElementTree tag."""
    return tag.rsplit("}", 1)[-1]


def _qname_local(qname: str | None) -> str:
    """Strip the XML prefix from a QName-valued attribute/text (e.g. "us-gaap:FooAxis" -> "FooAxis").

    ElementTree only resolves namespaces for element/attribute *names*, not for
    QNames appearing as attribute values or text content - dimension/member
    references in XBRL contexts are exactly that case.
    """
    if not qname:
        return ""
    return qname.strip().rsplit(":", 1)[-1]


# Imported here (not at module top) because sec_xbrl_segment_revenue.py/_2.py import the
# constants/functions defined above from this module - placing this import before they exist
# would be a circular-import failure. By this point in the file, everything those two files
# need from here has already been defined.
from utils.external.sec_xbrl_segment_revenue import (  # noqa: E402
    _extract_alt_asset_manager_segment_revenue,
    _extract_component_sum_segment_revenue,
    _extract_cross_tab_segment_revenue,
    _extract_gse_net_interest_income_segment_revenue,
)
from utils.external.sec_xbrl_segment_revenue_2 import (  # noqa: E402
    _extract_ares_style_segment_revenue,
    _extract_single_segment_revenue,
    _single_segment_result,
)


class XBRLSegmentParser:
    """Parse segment disclosure data from SEC XBRL filings (10-K).

    See module docstring for the companyfacts-vs-raw-XML split and why
    per-segment revenue can only ever come from the raw XML path.
    """

    @staticmethod
    def parse_companyfacts(facts: dict[str, Any], symbol: str) -> dict[str, Any]:
        """Parse segment COUNT (only) from SEC companyfacts JSON API response.

        Args:
            facts: JSON facts dict from SEC companyfacts API (us/CIK/CIK_0000123456.json)
                   Structure: {cik, entityName, facts: {us-gaap: {concept_name: [{...}]}}}
            symbol: Stock ticker symbol (for logging)

        Returns:
            Dict with segment_count if a company-level count concept is tagged,
            and data_available=False always (per-segment revenue is not
            recoverable from this endpoint - see module docstring).
        """
        try:
            if "facts" not in facts or "us-gaap" not in facts.get("facts", {}):
                return {
                    "segment_count": None,
                    "largest_segment_revenue_pct": None,
                    "revenue_concentration_hhi": None,
                    "segments": [],
                    "segment_type": None,
                    "data_available": False,
                    "reason": "no_us_gaap_facts",
                }

            us_gaap = facts["facts"]["us-gaap"]
            segment_count = XBRLSegmentParser._extract_segment_count(us_gaap, symbol)

            return {
                "segment_count": segment_count,
                "largest_segment_revenue_pct": None,
                "revenue_concentration_hhi": None,
                "segments": [],
                "segment_type": None,
                "data_available": False,
                "reason": (
                    "no_segment_count_facts_in_companyfacts"
                    if segment_count is None
                    else "companyfacts_api_never_exposes_per_segment_revenue"
                ),
            }

        except Exception as e:
            logger.warning(f"[{symbol}] XBRL segment parse failed: {type(e).__name__}: {str(e)[:200]}")
            return {
                "segment_count": None,
                "largest_segment_revenue_pct": None,
                "revenue_concentration_hhi": None,
                "segments": [],
                "segment_type": None,
                "data_available": False,
                "reason": f"parse_error: {type(e).__name__}",
            }

    @staticmethod
    def _extract_segment_count(us_gaap: dict[str, Any], symbol: str) -> int | None:
        """Extract number of reportable segments from us-gaap facts.

        FIXED 2026-07-28: previously checked ["SegmentNumber", "NumberOfReportableSegments",
        "OperatingSegmentNumber", "NumberOfSegments"] - live-checking 5 real filers (GILD,
        REGN, UAL, O, MSFT) found "SegmentNumber"/"OperatingSegmentNumber"/"NumberOfSegments"
        present in NONE of them, while "NumberOfOperatingSegments" (the real ASU 2023-07
        concept, already verified and used by _SEGMENT_COUNT_CONCEPT_LOCAL_NAMES elsewhere in
        this module) was missing from this list entirely despite being present for 3 of the 5
        (UAL, GILD, O) - UAL in particular tags ONLY this concept, so this function silently
        returned None for it. Zero live impact today (this function's caller,
        parse_companyfacts(), always reports data_available=False, and
        loaders/load_sec_segment_info.py unconditionally overwrites its result with the raw-
        XML path before persisting anything), but wrong/dead concept names left in the
        candidate list regardless - reusing the same verified constant instead of a second,
        divergent hand-maintained list.
        """
        candidates = list(_SEGMENT_COUNT_CONCEPT_LOCAL_NAMES)

        for concept_name in candidates:
            if concept_name in us_gaap:
                concept_data = us_gaap[concept_name]
                if isinstance(concept_data, dict) and "units" in concept_data:
                    # companyfacts structure: units[unit_name][facts_list]
                    units = concept_data.get("units") or {}
                    if isinstance(units, dict):
                        for _unit, facts_list in units.items():
                            if isinstance(facts_list, list):
                                best_fact = None
                                best_fy = -1
                                for fact in facts_list:
                                    if isinstance(fact, dict):
                                        val = fact.get("val") or fact.get("value")
                                        if val is not None:
                                            try:
                                                count = int(val)
                                                if count > 0:
                                                    fy = fact.get("fy", -1)
                                                    # Prefer FY periods over quarterly
                                                    fp = fact.get("fp", "")
                                                    if fp == "FY" and fy > best_fy:
                                                        best_fy = fy
                                                        best_fact = count
                                                    elif best_fact is None:
                                                        best_fact = count
                                            except (ValueError, TypeError):
                                                pass
                                if best_fact:
                                    return best_fact

        return None

    @staticmethod
    def _compute_herfindahl_index(revenues: Sequence[float | Decimal], total: float | Decimal) -> float:
        """Compute Herfindahl-Hirschman Index (HHI) of revenue concentration.

        HHI = sum of (revenue_share ^ 2) scaled to 0-10000
        - HHI < 1500: competitive
        - 1500-2500: moderate concentration
        - > 2500: highly concentrated
        - 10000: perfect monopoly (single segment)
        """
        if not revenues or total == 0:
            return 0.0

        total = float(total)
        hhi = 0.0
        for revenue in revenues:
            share = float(revenue) / total
            hhi += share * share

        # Scale to 0-10000
        return hhi * 10000

    @staticmethod
    def _prettify_segment_name(member_local_name: str) -> str:
        """ "AmericasSegmentMember" / "IntelligentCloudMember" -> "Americas Segment" / "Intelligent Cloud"."""
        name = member_local_name
        if name.endswith("Member"):
            name = name[: -len("Member")]
        name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
        return name.strip() or member_local_name

    @staticmethod
    def _index_legal_entity_to_segments(root: ET.Element) -> dict[str, set[str]]:
        """Map each dei:LegalEntityAxis member -> the set of segment-axis members it's
        ever paired with, anywhere in the whole instance document.

        FIXED 2026-09-09 (goal: "missing SEC/XBRL data" audit, sec_segment_info/
        sec_segment_metrics no_segment_revenue_in_xbrl_xml investigation): live-verified
        against American States Water's (AWR, CIK 1056903) real FY2025 10-K instance
        document (awr-20251231_htm.xml, accession 0001628280-26-009114). AWR's segments each
        map to ONE DEDICATED regulated subsidiary - StatementBusinessSegmentsAxis=
        WaterServiceUtilityOperationsMember is always paired with dei:LegalEntityAxis=
        GoldenStateWaterCompanyMember, ElectricServiceUtilityOperationsMember always with
        BearValleyElectricServiceIncMember, ContractedServicesMember always with
        AmericanStatesUtilityServicesMember - a fixed, non-overlapping 1:1 mapping, the same
        "entity identity, not a further breakdown" shape as NEE's FPL case (see
        _LEGAL_ENTITY_AXIS docstring), just with a DIFFERENT member name on each axis instead
        of an identical one (AWR's subsidiaries are named after their regulated business, not
        after the segment label itself). The old exact-name-match check in
        _index_segment_contexts couldn't recognize this, so these dual-dimensioned contexts
        were excluded as "cross-tabbed" even though AWR's own real, complete segment revenue
        is tagged there and nowhere else - us-gaap:Revenues at these 3 contexts (Water
        $464,114,000 + Electric $57,217,000 + Contracted Services $136,742,000 =
        $658,073,000 FY2025) sums EXACTLY to AWR's own plain consolidated Revenues total for
        the same period, confirming these are the real segment totals, not a finer
        sub-breakdown.

        Generalized here via a document-wide check instead of exact-name matching:
        _index_segment_contexts treats a LegalEntityAxis member as identity (safe to strip)
        when it is associated with EXACTLY ONE segment-axis member anywhere in the whole
        instance document (this dict having a value of size 1) - whether because the names
        match (NEE) or because the filer simply never reuses that subsidiary across more
        than one segment (AWR). A LegalEntityAxis member seen paired with 2+ DIFFERENT
        segment members somewhere in the document is a genuine cross-tab (a co-registrant
        reporting within more than one segment) and is still NOT stripped - this deliberately
        preserves the existing fail-closed behavior for that case (see
        test_legal_entity_axis_not_stripped_when_used_across_multiple_segments).
        """
        entity_to_segments: dict[str, set[str]] = {}
        for ctx in root.iter():
            if _local_name(ctx.tag) != "context":
                continue
            raw_members: list[tuple[str, str]] = []
            for child in ctx.iter():
                if _local_name(child.tag) == "explicitMember":
                    dim_local = _qname_local(child.get("dimension"))
                    raw_members.append((dim_local, _qname_local(child.text)))
            segs_here = {m[1] for m in raw_members if m[0] in _SEGMENT_AXIS_LOCAL_NAMES}
            if not segs_here:
                continue
            for m in raw_members:
                if m[0] == _LEGAL_ENTITY_AXIS:
                    entity_to_segments.setdefault(m[1], set()).update(segs_here)
        return entity_to_segments

    @staticmethod
    def _index_segment_contexts(root: ET.Element) -> dict[str, tuple[str, str, str, str | None, bool]]:
        """Map context id -> (axis_local_name, segment_member, period_end, period_start, is_boilerplate_paired).

        Only contexts representing the segment's own total are included - a
        recognized segment axis alone, or paired only with the standard
        ConsolidationItemsAxis=OperatingSegmentsMember marker (see
        _CONSOLIDATION_ITEMS_AXIS above). Non-segment-dimensioned contexts (the
        consolidated totals) and contexts dimensioned on any OTHER additional axis
        (product line, sub-segment, tax jurisdiction, equity component, etc. - a
        real 10-K instance has dozens) are excluded.

        Many filers cross-tab segment revenue against a further axis in the same
        instance document - e.g. business segment x geography, or business segment
        x product sub-line (confirmed live against JNJ's FY2025 10-K: Innovative
        Medicine revenue is tagged once for the segment total, then again broken
        out by US/Non-US, then again by therapeutic-area sub-segment, all sharing
        the same StatementBusinessSegmentsAxis=InnovativeMedicineMember dimension).
        A context dimensioned on one of those extra axes is one of those finer
        breakdowns, not the segment-level total - counting it under the same
        member key as the plain segment total silently multiplies revenue several
        times over. Restricting to single-dimension-or-OperatingSegmentsMember-
        paired contexts keeps only the true segment-level (or geography-level)
        totals.

        See _index_legal_entity_to_segments for the AWR-shape LegalEntityAxis
        bijection check used below (also handles NEE's exact-name-match shape as a
        special case of the same rule).
        """
        entity_to_segments = XBRLSegmentParser._index_legal_entity_to_segments(root)
        context_segment: dict[str, tuple[str, str, str, str | None, bool]] = {}
        for ctx in root.iter():
            if _local_name(ctx.tag) != "context":
                continue
            ctx_id = ctx.get("id")
            if not ctx_id:
                continue

            explicit_members: list[tuple[str, str]] = []
            start_str = end_str = None
            for child in ctx.iter():
                loc = _local_name(child.tag)
                if loc == "explicitMember":
                    dim_local = _qname_local(child.get("dimension"))
                    explicit_members.append((dim_local, _qname_local(child.text)))
                elif loc == "startDate":
                    start_str = (child.text or "").strip() or None
                elif loc == "endDate":
                    end_str = (child.text or "").strip() or None
                elif loc == "instant":
                    end_str = (child.text or "").strip() or None

            # Drop boilerplate reporting-convention markers (e.g. "this is a real
            # operating segment, not the eliminations line"; SAP's "this is the
            # actual-currency figure, not the constant-currency one" - see
            # _BOILERPLATE_AXIS_MEMBER_PAIRS) before judging dimension count - none
            # of these narrow the fact to a sub-breakdown of the segment.
            def _is_boilerplate_pair(m: tuple[str, str]) -> bool:
                return any(m[0] in axes and m[1] == member for axes, member in _BOILERPLATE_AXIS_MEMBER_PAIRS)

            is_boilerplate_paired = any(_is_boilerplate_pair(m) for m in explicit_members)
            non_boilerplate = [m for m in explicit_members if not _is_boilerplate_pair(m)]
            # Also drop a co-registrant LegalEntityAxis dimension that identifies WHICH
            # subsidiary reports a segment rather than further breaking it down - either
            # because its member is IDENTICAL to the segment-axis member in this same context
            # (NEE's shape), or because, across the whole document, this entity member is
            # associated with exactly one segment-axis member (AWR's shape - see the FIXED
            # 2026-09-09 comment above). A LegalEntityAxis member ever paired with 2+ distinct
            # segment members anywhere in the document is a genuine further-breakdown-by-entity
            # case and is left in place, still disqualifying the context as a cross-tab.
            segment_members = {m[1] for m in non_boilerplate if m[0] in _SEGMENT_AXIS_LOCAL_NAMES}
            non_boilerplate = [
                m
                for m in non_boilerplate
                if not (
                    m[0] == _LEGAL_ENTITY_AXIS
                    and (m[1] in segment_members or len(entity_to_segments.get(m[1], set())) == 1)
                )
            ]
            if len(non_boilerplate) != 1:
                continue
            axis, member = non_boilerplate[0]
            if axis not in _SEGMENT_AXIS_LOCAL_NAMES:
                continue
            if member in _NON_SEGMENT_SUBTOTAL_MEMBERS:
                continue

            if axis and member and end_str:
                context_segment[ctx_id] = (axis, member, end_str, start_str, is_boilerplate_paired)

        # FIXED 2026-09-07 (goal: stock_scores/tie-out sanity audit, segment-sum-to-consolidated
        # investigation): "ReportableSegmentMember" (singular - the ASU 2023-07 generic member a
        # single-reportable-segment filer tags on its own aggregate total) is AMBIGUOUS in a way
        # the always-a-subtotal plural "ReportableSegmentsMember" isn't - live-confirmed two
        # opposite real shapes for the exact same member name:
        #   - Electronic Arts (EA) FY2026 10-K: StatementBusinessSegmentsAxis=ReportableSegmentMember
        #     tags $7.531B (the real, correct total) ALONGSIDE separate real disaggregation-by-
        #     category members (Mobile/Live Services/Full Game/etc.) under the SAME axis -
        #     counting it as an additional peer segment roughly doubles the true total.
        #   - Realty Income's FY2025 10-K: this is the filer's ONLY segment-dimensioned member at
        #     all (a genuinely single-segment company) - dropping it unconditionally (an earlier,
        #     REVERTED version of this fix added it to _NON_SEGMENT_SUBTOTAL_MEMBERS directly)
        #     broke the single-segment fallback path further down that needs this exact member
        #     present in context_segment to correctly label/value the one real segment.
        # Distinguishing factor: EA's shape has 2+ OTHER distinct real members sharing the axis;
        # Realty Income's shape has none. Only drop this specific member when 2+ siblings exist -
        # a sole "ReportableSegmentMember" with no siblings is genuinely the one real segment, not
        # a redundant subtotal.
        for axis_with_member in {info[0] for info in context_segment.values()}:
            members_on_axis = {info[1] for info in context_segment.values() if info[0] == axis_with_member}
            if "ReportableSegmentMember" not in members_on_axis:
                continue
            sibling_members = members_on_axis - {"ReportableSegmentMember"}
            if len(sibling_members) >= 2:
                context_segment = {
                    cid: info
                    for cid, info in context_segment.items()
                    if not (info[0] == axis_with_member and info[1] == "ReportableSegmentMember")
                }

        return context_segment

    @staticmethod
    def _dedupe_member_facts(facts: list[tuple[str, float, bool]], symbol: str, concept: str) -> dict[str, float]:
        """Collapse duplicate (member, value, is_boilerplate_paired) facts for the same
        member down to one value per member, instead of summing them.

        FIXED 2026-09-02 (goal: "missing SEC/XBRL data" audit, live SEC EDGAR
        verification): a filer can tag the SAME real segment/period fact via more than
        one qualifying context - most commonly a plain single-axis context AND a
        ConsolidationItemsAxis=OperatingSegmentsMember-paired one (see this file's
        Caterpillar/JNJ comments on extract_segment_revenue_from_xbrl_xml's own primary
        revenue-selection path, which already handles this correctly - this generalizes
        that same fix to every OTHER per-member accumulation in this file, which were
        blindly summing instead). Live-confirmed via Truist Financial's (TFC, CIK 92230)
        real FY2025 10-K instance document: InterestIncomeExpenseNet is tagged BOTH as a
        plain StatementBusinessSegmentsAxis=ConsumerAndSmallBusinessBankingMember context
        ($6,120,000,000) AND, separately, paired with ConsolidationItemsAxis=
        OperatingSegmentsMember for the identical segment/period ($9,584,000,000, a
        different real value, not a duplicate tagging of the same fact) -
        _extract_component_sum_segment_revenue's old blind `+=` accumulation summed both,
        producing a segment total 71% over TFC's own consolidated
        InterestIncomeExpenseNet+NoninterestIncome anchor ($34.7B vs the real $20.3B),
        which failed reconciliation and fell through to "no_segment_revenue_in_xbrl_xml"
        despite TFC having complete, real, reconcilable segment data on file. Deduping
        first (dropping to just the plain, non-boilerplate-paired value per member, the
        same "prefer plain on disagreement" rule the primary path already uses) makes the
        segment total reconcile EXACTLY to TFC's real $20,319,000,000 consolidated figure.
        Same accumulation shape is used for operating_income_by_member/assets_by_member
        via _extract_segment_member_values below, so this also fixes silently-inflated
        (not just missing) operating-income/assets figures for any filer with this same
        dual-tagging pattern under those concepts, not just bank revenue.
        """
        values: dict[str, float] = {}
        is_boilerplate_by_member: dict[str, bool] = {}
        for member, value, is_boilerplate in facts:
            if member not in values:
                values[member] = value
                is_boilerplate_by_member[member] = is_boilerplate
                continue
            if abs(values[member] - value) <= max(1.0, abs(values[member]) * 0.001):
                continue  # same fact tagged twice, nothing to reconcile
            if is_boilerplate_by_member[member] and not is_boilerplate:
                logger.warning(
                    f"[{symbol}] {concept}: segment '{member}' tagged with disagreeing "
                    f"values across contexts ({values[member]} vs {value}) for the same "
                    "period - preferring the plain (non-OperatingSegmentsMember-paired) value."
                )
                values[member] = value
                is_boilerplate_by_member[member] = is_boilerplate
            else:
                logger.warning(
                    f"[{symbol}] {concept}: segment '{member}' tagged with disagreeing "
                    f"values across contexts ({values[member]} vs {value}) for the same "
                    "period - keeping the first value seen."
                )
        return values

    @staticmethod
    def _extract_segment_member_values(
        root: ET.Element,
        context_segment: dict[str, tuple[str, str, str, str | None, bool]],
        axis_to_use: str,
        concept_local_names: tuple[str, ...],
        target_end: str,
        match_duration_days: int | None,
        symbol: str = "",
    ) -> dict[str, float]:
        """Extract member -> value for a concept, restricted to the same fiscal
        period already selected for segment revenue (target_end, and for
        duration concepts, match_duration_days).

        match_duration_days=None means an instant (balance-sheet) concept
        (e.g. Assets) - matched on end date alone, since instant contexts have
        no startDate. A duration concept (e.g. OperatingIncomeLoss) must also
        match the same period length as the revenue figure it's paired with, so
        a stray quarterly fact sharing the fiscal year-end date can't leak in
        next to an annual revenue total.

        Unlike revenue, values are NOT filtered by sign - a segment can have a
        real, legitimate operating loss (confirmed live: Amazon's International
        segment reported a -$2.66B OperatingIncomeLoss in FY2023).
        """
        values: dict[str, float] = {}
        unit_currencies = _parse_unit_currencies(root)
        for concept in concept_local_names:
            facts: list[tuple[str, float, bool]] = []
            for elem in root.iter():
                if _local_name(elem.tag) != concept:
                    continue
                info = context_segment.get(elem.get("contextRef", ""))
                if not info or info[0] != axis_to_use:
                    continue
                _axis, member, end_str, start_str, is_boilerplate = info
                if end_str != target_end:
                    continue
                if match_duration_days is not None:
                    if not start_str:
                        continue
                    try:
                        duration = (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days
                    except ValueError:
                        continue
                    if duration != match_duration_days:
                        continue
                elif start_str:
                    # An instant concept (no startDate expected) matched a
                    # duration context - not the balance-sheet fact we want.
                    continue
                value = elem.text
                if value is None:
                    continue
                try:
                    fvalue = float(value.strip())
                except ValueError:
                    continue
                # Same FX-normalization as the revenue path above (see
                # extract_segment_revenue_from_xbrl_xml's 2026-09-06 comment) - operating_income
                # and assets share this one extraction function, so the same wrong-magnitude
                # local-currency bug applied to both, not just revenue.
                currency = unit_currencies.get(elem.get("unitRef") or "")
                if currency and currency != "USD":
                    if currency not in MAJOR_CURRENCIES:
                        continue
                    fx_rate = _fx_rate_cache.get_usd_rate(currency, end_str)
                    if fx_rate is None or fx_rate == 0:
                        continue
                    fvalue = fvalue / fx_rate
                facts.append((member, fvalue, is_boilerplate))
            if facts:
                values = XBRLSegmentParser._dedupe_member_facts(facts, symbol, concept)
                break
        return values

    @staticmethod
    def extract_segment_revenue_from_xbrl_xml(xml_content: str, symbol: str) -> dict[str, Any]:  # noqa: C901
        """Extract per-segment revenue from a raw XBRL instance document.

        Reads the actual XBRL dimensional model (context -> explicitMember ->
        segment axis/member) instead of guessing segment identity from
        contextRef naming conventions, which are filer/tool-specific and not
        governed by any SEC-wide convention.

        Returns:
            Same structure as parse_companyfacts(), with real segment-level
            revenue when the filing tags any recognized segment axis.
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.warning(f"[{symbol}] Failed to parse XBRL XML: {e}")
            return {
                "segment_count": None,
                "largest_segment_revenue_pct": None,
                "revenue_concentration_hhi": None,
                "segments": [],
                "segment_type": None,
                "data_available": False,
                "reason": f"xml_parse_error: {str(e)[:100]}",
            }

        context_segment = XBRLSegmentParser._index_segment_contexts(root)
        if not context_segment:
            single = _extract_single_segment_revenue(root, symbol)
            if single is not None:
                _concept, revenue, _end, _duration = single
                return _single_segment_result(
                    name="Consolidated (Single Reportable Segment)",
                    segment_id="single_reportable_segment",
                    segment_type="operating",
                    revenue=revenue,
                    operating_income=None,
                    assets=None,
                )
            return {
                "segment_count": None,
                "largest_segment_revenue_pct": None,
                "revenue_concentration_hhi": None,
                "segments": [],
                "segment_type": None,
                "data_available": False,
                "reason": "no_segment_dimension_contexts_in_xbrl_xml",
            }

        # Prefer business-line segments (ASC 280's primary "operating segments" /
        # IFRS 8's SegmentsAxis equivalent); fall back to geographic only when the
        # filer doesn't tag either business-line axis.
        # FIXED 2026-08-29 (goal: "full data" audit, FPI-bank segment sweep follow-up):
        # a filer can tag MORE THAN ONE recognized segment axis in the same instance for
        # UNRELATED purposes - confirmed live against Bank of Montreal's FY2025 40-F:
        # `StatementBusinessSegmentsAxis` is present, but ONLY on a Goodwill-by-segment
        # footnote covering 2 of BMO's 5 real segments (WealthManagement, CapitalMarkets);
        # the REAL, complete 5-segment (+CorporateServices) revenue breakdown - real values
        # confirmed against BMO's own reported figures, e.g. Canadian P&C $12.262B, US
        # Banking $11.483B FY2025 - is tagged under the co-existing `SegmentsAxis` instead.
        # The prior single-axis-then-give-up logic picked `StatementBusinessSegmentsAxis`
        # (higher priority, and genuinely present) and never looked at `SegmentsAxis` at
        # all once that pick came up empty for revenue, reporting data_unavailable despite
        # the real data sitting right there under a different axis in the same filing. Now
        # tries every recognized axis actually present, in the same priority order, and
        # keeps whichever one is the first to actually yield a revenue candidate - a filer
        # with real data under its first-priority axis (the overwhelmingly common case,
        # unaffected by this change) still resolves exactly as before.
        available_axes = {info[0] for info in context_segment.values()}
        axis_priority = [axis for axis in _SEGMENT_AXIS_LOCAL_NAMES if axis in available_axes]
        axis_to_use = axis_priority[0]

        # ADDED 2026-09-06 (goal session: "SEC/XBRL missing data to zero" sweep, segment-sum-to-
        # consolidated FX gap - see this file's module docstring on the previously-rejected
        # "Segment-sum-to-consolidated" tie-out check for the live evidence: AKO.A/AKO.B/KWM/
        # LGPS/MRM/LFS/LRE/PDC/PAYP-style foreign filers showed 100x-1,400x magnitude errors
        # because segment revenue is tagged in the filer's local reporting currency with no
        # normalization step here, unlike annual_income_statement.revenue (which DOES convert -
        # see sec_statements_entry_resolution.py's _aggregate_concepts_apply_entry_value). This
        # was silently storing wrong-magnitude local-currency values as if they were USD, not
        # just under-reporting - a real "no confidently-wrong data" violation, not merely a
        # missing-data gap. Live-verified against AKO.A's real FY2025 20-F (CIK 0000925261,
        # accession 0001104659-26-038506): Brazil segment revenue was $976,907,746,000 (raw CLP
        # stored as if USD) before this fix, $1,085,525,417 (a plausible real figure) after -
        # Chile/Argentina/Paraguay corrected the same way, summing to ~$3.7B total, consistent
        # with Andina's real known consolidated scale. Resolves each matched fact's own unitRef
        # to a currency and converts via the same real historical-ECB-rate FxRateCache the
        # income/balance-sheet extractors use (never a guessed rate); a non-major, non-USD
        # currency (e.g. KRW/JPY-scale mismatches, or a lookup failure) rejects the fact entirely
        # rather than storing an unconverted or fabricated value - same fail-closed discipline as
        # every other currency guard in this codebase. Scoped to this direct-axis-facts path and
        # its sibling _extract_segment_member_values (operating_income/assets, same bug) - the
        # cross-tab/component-sum/Ares-style fallback paths below are predominantly US filers
        # already reporting in USD and are left untouched rather than risk a wider, less-tested
        # change.
        unit_currencies = _parse_unit_currencies(root)

        candidate_facts: list[tuple[str, str, int, float, bool]] = []
        # (member, end_date, duration_days, revenue, is_boilerplate_paired)
        matched_concept = None
        for axis_candidate in axis_priority:
            concepts_to_try = _REVENUE_CONCEPT_LOCAL_NAMES + _AXIS_SPECIFIC_EXTRA_REVENUE_CONCEPTS.get(
                axis_candidate, ()
            )
            for concept in concepts_to_try:
                candidate_facts = []
                for elem in root.iter():
                    if _local_name(elem.tag) != concept:
                        continue
                    info = context_segment.get(elem.get("contextRef", ""))
                    if not info or info[0] != axis_candidate:
                        continue
                    _axis, member, end_str, start_str, is_boilerplate_paired = info
                    value = elem.text
                    if value is None:
                        continue
                    try:
                        revenue = float(value.strip())
                    except ValueError:
                        continue
                    currency = unit_currencies.get(elem.get("unitRef") or "")
                    if currency and currency != "USD":
                        if currency not in MAJOR_CURRENCIES or not end_str:
                            continue
                        fx_rate = _fx_rate_cache.get_usd_rate(currency, end_str)
                        if fx_rate is None or fx_rate == 0:
                            continue
                        revenue = revenue / fx_rate
                    duration_days = 0
                    if start_str and end_str:
                        try:
                            duration_days = (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days
                        except ValueError:
                            duration_days = 0
                    candidate_facts.append((member, end_str, duration_days, revenue, is_boilerplate_paired))
                if candidate_facts:
                    matched_concept = concept
                    break
            if candidate_facts:
                axis_to_use = axis_candidate
                break

        if not candidate_facts:
            cross_tab = _extract_cross_tab_segment_revenue(root, symbol, axis_to_use)
            component_sum = (
                _extract_component_sum_segment_revenue(root, context_segment, axis_to_use, symbol)
                if cross_tab is None
                else None
            )
            alt_asset_manager_sum = (
                _extract_alt_asset_manager_segment_revenue(root, context_segment, axis_to_use, symbol)
                if cross_tab is None and component_sum is None
                else None
            )
            gse_net_interest_income_sum = (
                _extract_gse_net_interest_income_segment_revenue(root, context_segment, axis_to_use, symbol)
                if cross_tab is None
                and component_sum is None
                and alt_asset_manager_sum is None
                and symbol in _GSE_NET_INTEREST_INCOME_SEGMENT_SYMBOLS
                else None
            )
            ares_style_sum = (
                _extract_ares_style_segment_revenue(root, symbol)
                if cross_tab is None
                and component_sum is None
                and alt_asset_manager_sum is None
                and gse_net_interest_income_sum is None
                else None
            )
            if (
                cross_tab is None
                and component_sum is None
                and alt_asset_manager_sum is None
                and gse_net_interest_income_sum is None
                and ares_style_sum is None
            ):
                # require_explicit_count_tag=True: real segment-dimensioned contexts DO exist
                # here (context_segment is non-empty - see the early-return branch above for
                # the true zero-context case) but none of the reconciliation strategies
                # matched them - see _extract_single_segment_revenue's own docstring
                # ("BUG FOUND 2026-09-06") for why the relaxed no-count-tag-required rule
                # must not apply at this call site.
                single = _extract_single_segment_revenue(root, symbol, require_explicit_count_tag=True)
                if single is not None:
                    _concept, revenue, single_end, single_duration = single
                    # Realty Income's FY2025 10-K tags the single segment's
                    # own member (ReportableSegmentMember) on cost-item facts
                    # even though it never tags revenue under that axis - use
                    # the real member name/operating-income/assets if the
                    # filing happens to disclose them, honest None otherwise.
                    distinct_members = {(a, m) for a, m, _e, _s, _b in context_segment.values() if a == axis_to_use}
                    member_key = next(iter(distinct_members))[1] if len(distinct_members) == 1 else None
                    name = (
                        XBRLSegmentParser._prettify_segment_name(member_key)
                        if member_key
                        else "Consolidated (Single Reportable Segment)"
                    )
                    operating_income = assets = None
                    if member_key:
                        operating_income = XBRLSegmentParser._extract_segment_member_values(
                            root,
                            context_segment,
                            axis_to_use,
                            _OPERATING_INCOME_CONCEPT_LOCAL_NAMES,
                            single_end,
                            single_duration,
                            symbol,
                        ).get(member_key)
                        assets = XBRLSegmentParser._extract_segment_member_values(
                            root, context_segment, axis_to_use, _ASSETS_CONCEPT_LOCAL_NAMES, single_end, None, symbol
                        ).get(member_key)
                    return _single_segment_result(
                        name=name,
                        segment_id=member_key or "single_reportable_segment",
                        segment_type="operating"
                        if axis_to_use in (_BUSINESS_SEGMENT_AXIS, _IFRS_SEGMENTS_AXIS)
                        else "geographic",
                        revenue=revenue,
                        operating_income=operating_income,
                        assets=assets,
                    )
                return {
                    "segment_count": None,
                    "largest_segment_revenue_pct": None,
                    "revenue_concentration_hhi": None,
                    "segments": [],
                    "segment_type": None,
                    "data_available": False,
                    "reason": "no_segment_revenue_in_xbrl_xml",
                }
            if cross_tab is not None:
                segments, max_end, max_duration = cross_tab
                logger.debug(f"[{symbol}] Segment revenue matched via cross-tab reconciliation on {axis_to_use}")
            elif component_sum is not None:
                segments, max_end, max_duration = component_sum
                logger.debug(
                    f"[{symbol}] Segment revenue matched via component-sum "
                    f"({' + '.join(_BANK_REVENUE_COMPONENT_CONCEPTS)}) on {axis_to_use}"
                )
            elif alt_asset_manager_sum is not None:
                segments, max_end, max_duration = alt_asset_manager_sum
                logger.debug(
                    f"[{symbol}] Segment revenue matched via alt-asset-manager component-sum "
                    f"({' + '.join(_ALT_ASSET_MANAGER_REVENUE_COMPONENT_CONCEPTS)}) on {axis_to_use}"
                )
            elif gse_net_interest_income_sum is not None:
                segments, max_end, max_duration = gse_net_interest_income_sum
                logger.debug(
                    f"[{symbol}] Segment revenue matched via GSE net-interest-income "
                    f"component-sum ({_GSE_NET_INTEREST_INCOME_CONCEPTS[0]} - "
                    f"{_GSE_NET_INTEREST_INCOME_CONCEPTS[1]}) on {axis_to_use}"
                )
            elif ares_style_sum is not None:
                segments, max_end, max_duration = ares_style_sum
                logger.debug(f"[{symbol}] Segment revenue matched via Ares-style component-sum")
            else:
                raise AssertionError("unreachable: single-segment fallback branch above already handled this case")
        else:
            logger.debug(f"[{symbol}] Segment revenue matched via {matched_concept} on {axis_to_use}")

            # A 10-K instance carries multiple fiscal years side by side for
            # comparison tables - keep only the most recent period (max end date;
            # among ties, the longest duration, to prefer an annual figure over a
            # stray quarterly context sharing the fiscal year-end date).
            max_end = max(f[1] for f in candidate_facts)
            same_end = [f for f in candidate_facts if f[1] == max_end]
            max_duration = max(f[2] for f in same_end)
            latest_facts = [f for f in same_end if f[2] == max_duration]

            # A filer can tag the same segment's revenue via more than one qualifying
            # context for the same period - e.g. a plain single-axis context AND a
            # ConsolidationItemsAxis=OperatingSegmentsMember-paired one (confirmed
            # live: JNJ's FY2025 10-K tags Innovative Medicine revenue both ways,
            # both contexts carrying the identical value). These are usually
            # redundant taggings of ONE real fact, not two additive ones - summing
            # them would silently double the segment's revenue. Keep one value per
            # member.
            #
            # They can also genuinely disagree: confirmed live against Caterpillar's
            # FY2025 10-K, Power & Energy's OperatingSegmentsMember-paired context
            # tags $32.201B (gross, including intersegment sales) while its plain
            # context tags $27.143B (net, externally reported) - the two reconcile
            # exactly against CAT's own tagged IntersegmentEliminationMember fact
            # (-$5.058B). The plain, non-boilerplate-paired context is the filer's
            # actual externally-reported segment revenue; prefer it on disagreement
            # rather than picking whichever happened to be tagged first in document
            # order.
            segments = {}
            segment_is_boilerplate: dict[str, bool] = {}
            for member, _end, _duration, revenue, is_boilerplate_paired in latest_facts:
                if member not in segments:
                    segments[member] = revenue
                    segment_is_boilerplate[member] = is_boilerplate_paired
                    continue
                if abs(segments[member] - revenue) <= max(1.0, abs(segments[member]) * 0.001):
                    continue  # same fact tagged twice, nothing to reconcile
                if segment_is_boilerplate[member] and not is_boilerplate_paired:
                    logger.warning(
                        f"[{symbol}] Segment '{member}' tagged with disagreeing revenue values "
                        f"across contexts ({segments[member]} vs {revenue}) for the same period - "
                        "preferring the plain (non-OperatingSegmentsMember-paired) value."
                    )
                    segments[member] = revenue
                    segment_is_boilerplate[member] = is_boilerplate_paired
                else:
                    logger.warning(
                        f"[{symbol}] Segment '{member}' tagged with disagreeing revenue values "
                        f"across contexts ({segments[member]} vs {revenue}) for the same period - "
                        "keeping the first value seen."
                    )

        # Many filers tag a non-operating "Corporate and Eliminations" (or similarly
        # named) reconciling line under the same segment axis so segment totals foot
        # to the consolidated total - by ASC 280 convention that's an intercompany
        # elimination/unallocated-corporate line, not a real reportable operating
        # segment, and it's the only case revenue under this axis is ever negative.
        # Excluding negative entries (rather than matching on member name, which SEC
        # does not standardize) keeps HHI/largest_segment_revenue_pct meaningful -
        # without this, an elimination line can push total_revenue below any single
        # real segment's revenue, producing an impossible >100% largest_pct.
        reportable_segments = {member: revenue for member, revenue in segments.items() if revenue >= 0}

        total_revenue = sum(reportable_segments.values())
        if not reportable_segments or total_revenue == 0:
            return {
                "segment_count": len(reportable_segments) or None,
                "largest_segment_revenue_pct": None,
                "revenue_concentration_hhi": None,
                "segments": [],
                "segment_type": None,
                "data_available": False,
                "reason": "zero_total_segment_revenue",
            }

        operating_income_by_member = XBRLSegmentParser._extract_segment_member_values(
            root, context_segment, axis_to_use, _OPERATING_INCOME_CONCEPT_LOCAL_NAMES, max_end, max_duration, symbol
        )
        assets_by_member = XBRLSegmentParser._extract_segment_member_values(
            root, context_segment, axis_to_use, _ASSETS_CONCEPT_LOCAL_NAMES, max_end, None, symbol
        )

        segment_list = sorted(
            (
                {
                    "segment_id": member,
                    "name": XBRLSegmentParser._prettify_segment_name(member),
                    "revenue": revenue,
                    "operating_income": operating_income_by_member.get(member),
                    "assets": assets_by_member.get(member),
                }
                for member, revenue in reportable_segments.items()
            ),
            key=lambda s: cast(float, s["revenue"]),
            reverse=True,
        )
        revenues: list[float] = [cast(float, s["revenue"]) for s in segment_list]
        hhi = XBRLSegmentParser._compute_herfindahl_index(revenues, total_revenue)
        largest_pct = revenues[0] / total_revenue * 100

        return {
            "segment_count": len(segment_list),
            "largest_segment_revenue_pct": round(largest_pct, 2),
            "revenue_concentration_hhi": round(hhi, 3),
            "segments": segment_list,
            "segment_type": "operating"
            if axis_to_use in (_BUSINESS_SEGMENT_AXIS, _IFRS_SEGMENTS_AXIS)
            else "geographic",
            "data_available": True,
            "reason": None,
        }
