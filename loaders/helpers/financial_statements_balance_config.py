"""Balance-sheet field mapping and get_balance_sheet_config(), extracted from
load_financial_statements.py alongside the income/cashflow config modules - see
financial_statements_income_config.py's docstring for the full extraction rationale.
"""

from typing import Any

from loaders.helpers.financial_statements_config_shared import _MARKER_FIELDS, _QUARTERLY_EXTRA

_DEBT_FALLBACK_ONLY_FIELDS = frozenset(
    {
        "notes_payable_related_parties_noncurrent",
        "long_term_notes_payable",
        "convertible_notes_payable",
        # FIXED 2026-08-18 (roic_pct "missing_sec_data" follow-up, goal: "no SEC data"
        # audit): DKNG/DASH-style fallback - see sec_statements.py's get_balance_sheet()
        # comment for the live evidence (DKNG FY2025 $1.26B, DASH FY2025 $2.72B tagged
        # only under this concept, never plain "ConvertibleNotesPayable"/"LongTermDebt").
        "convertible_long_term_notes_payable",
        # FIXED 2026-08-17 (SEC-vs-yfinance audit): JPM-style bank fallback - see
        # sec_statements.py's get_balance_sheet() comment for why this concept is needed
        # (JPM has not tagged plain "LongTermDebt" since FY2013).
        "long_term_debt_and_capital_lease_obligations_including_current_maturities",
        # FIXED 2026-08-18 (roic_pct "missing_sec_data" audit): ADM-style fallback for
        # filers that tag total equity including noncontrolling interest instead of the
        # parent-only "StockholdersEquity" concept - see sec_statements.py's
        # get_balance_sheet() comment for the live evidence. Despite the set's name, this
        # has been the shared "balance-sheet fallback-only fields" bucket since the JPM
        # entry above; both annual/quarterly balance configs reference it directly.
        "stockholders_equity_including_portion_attributable_to_noncontrolling_interest",
        # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep): MembersEquity
        # sibling of the entry above - see sec_balance_sheet.py's get_balance_sheet() comment
        # for the live evidence (ARXS).
        "limited_liability_company_llc_members_equity_including_portion_attributable_to_noncontrolling_interest",
        # FIXED 2026-08-18 (roic_pct "missing_sec_data" follow-up): CAT/SLB-style and
        # XOM-style fallbacks - see sec_statements.py's get_balance_sheet() comment for the
        # live evidence (CAT FY2025 $30.696B, SLB FY2025 $9.742B, XOM FY2025 $34.241B, none
        # of which tag plain "LongTermDebt").
        "long_term_debt_noncurrent",
        "long_term_debt_and_capital_lease_obligations",
        # FIXED 2026-08-18 (missing factor inputs audit, roic_pct/total_debt follow-up):
        # net-lease REITs (ADC/Agree Realty live-confirmed via real SEC companyfacts
        # JSON) stop tagging "LongTermDebt" mid-history (ADC's last real fact under that
        # concept is 2022-03-31) and switch to reporting debt only via
        # "DebtInstrumentCarryingAmount" going forward (ADC FY2022-2025: $1.96B/$2.43B/
        # $2.81B/$3.32B, a clean sum roughly matching SecuredDebt+UnsecuredDebt+
        # SeniorNotes reported the same years) - not debt-free, just a taxonomy switch.
        # Without this fallback, load_sec_valuations.py's total_debt fell back to summing
        # only ADC's tiny lease liabilities (~$25M) instead of its real ~$3B+ debt load,
        # producing a wildly understated invested_capital for roic_pct (and any other
        # consumer of total_debt/long_term_debt).
        "debt_instrument_carrying_amount",
        # ADDED 2026-09-02 (goal session: "missing SEC/XBRL data" audit, KKR live-
        # confirmed): see sec_statements.py's get_balance_sheet() comment on
        # "PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest" -
        # limited-partnership-structured filers (KKR pre-2018) tag total consolidated
        # partner capital (including third-party LP capital in consolidated managed
        # funds - live-confirmed KKR FY2014 $51.4B under this concept vs $5.38B under
        # the parent-only "PartnersCapital" concept the same year, a ~10x gap from
        # consolidated variable-interest entities) under this concept. Fallback-only so
        # the precise parent-only "partners_capital" mapping below (NOT fallback-only,
        # same non-fallback precedence as "stockholders_equity" itself) always wins when
        # both are present for the same fiscal year - same "IncludingPortion" vs.
        # parent-only precedence convention as the StockholdersEquity pair above.
        "partners_capital_including_portion_attributable_to_noncontrolling_interest",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): see
        # utils/external/sec_custom_xbrl_concepts.py's CUSTOM_DEBT_CONCEPTS module comment
        # (BRK.A/BRK.B live evidence) - must never win over a real value the normal
        # concept-list extraction already found.
        "custom_extension_total_debt",
        # FIXED 2026-09-03 (same sweep): see
        # utils/external/sec_custom_xbrl_concepts.py's CUSTOM_DEBT_SHORTTERM_CONCEPTS
        # module comment (AES live evidence) - must never win over a real value the normal
        # concept-list extraction already found.
        "custom_extension_total_debt_current",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "NotesPayable" (AFL/MAA live evidence) - must never win over a real,
        # more complete LongTermDebt/SeniorNotes value.
        "notes_payable",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "DebtLongtermAndShorttermCombinedAmount" (PGR live evidence) - must
        # never win over a real LongTermDebt value from an earlier fiscal year.
        "debt_longterm_and_shortterm_combined_amount",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "SubordinatedDebt"/"JuniorSubordinatedDebentureOwedTo
        # UnconsolidatedSubsidiaryTrust" (IBOC/HBT live evidence) - must never win over
        # any of the standard debt concepts already fetched above.
        "subordinated_debt",
        "junior_subordinated_debenture_owed_to_unconsolidated_subsidiary_trust",
        # FIXED 2026-09-05 (goal session: "missing SEC/XBRL data" sweep): Donegal Group
        # (DGICA/DGICB) real revolving-credit debt - see sec_statements.py's
        # get_balance_sheet() comment on "LineOfCredit" for the live evidence ($35M FY2025).
        "line_of_credit",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "DebtCurrent" (DE live evidence) - a generic enough concept name
        # that a filer reporting a more specific standard concept (CommercialPaper/
        # ShortTermBorrowings/SeniorNotesCurrent/...) must always keep that value; this
        # only fills the gap when nothing else populated short_term_debt.
        "debt_current",
        # ADDED 2026-09-09: see sec_balance_sheet.py's get_balance_sheet() comment on
        # "SecuredDebt" (placed right after DebtCurrent above) for why fallback-only here
        # exactly resolves the DE collision concern that previously blocked adding it.
        "secured_debt",
        # ADDED 2026-09-09: see sec_balance_sheet.py's get_balance_sheet() comment on
        # "NotesPayableCurrent" - current-portion split of notes_payable, same generic-name
        # caution.
        "notes_payable_current",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "ShortTermBankLoansAndNotesPayable" (EXPD live evidence).
        "short_term_bank_loans_and_notes_payable",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): mortgage
        # REIT repo-agreement financing - see sec_statements.py's get_balance_sheet() comment
        # on "SecuritiesSoldUnderAgreementsToRepurchase" (AGNC/ARR live evidence, $60.8B/
        # $10.7B FY2024 respectively, both previously NULL for every debt-component column).
        "securities_sold_under_agreements_to_repurchase",
        # FIXED 2026-09-03 (same sweep, SEVN follow-up): see sec_statements.py's
        # get_balance_sheet() comment on "SecuredDebtRepurchaseAgreements" (SEVN live
        # evidence).
        "secured_debt_repurchase_agreements",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "PublicUtilitiesPropertyPlantAndEquipmentNet" (ES live evidence) and
        # the finance-lease-combined PP&E concept (DASH/DINO live evidence) - despite this
        # set's debt-focused name it's the shared balance-sheet fallback-only bucket (see
        # the stockholders_equity entry's comment above), covers non-debt fields too.
        "public_utilities_property_plant_and_equipment_net",
        "property_plant_and_equipment_and_finance_lease_right_of_use_asset_after_accumulated_depreciation_and_amortization",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "ReceivablesNetCurrent" (WMT/COST/RTX live evidence).
        "receivables_net_current",
        # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet()
        # comment on "InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings"
        # (BA/Boeing, HII/Huntington Ingalls live evidence).
        "inventory_net_of_allowances_customer_advances_and_progress_billings",
        # FIXED 2026-09-05 (goal session: "missing SEC/XBRL data" continuation): ACHV/BENF
        # real convertible-debt/other-long-term-debt concepts - see sec_statements.py's
        # get_balance_sheet() comment on "ConvertibleDebt"/"OtherLongTermDebt" for the live
        # evidence. Must never win over a real value the standard concepts already found.
        "convertible_debt",
        "convertible_debt_current",
        "convertible_debt_noncurrent",
        "other_long_term_debt",
        # FIXED 2026-09-05 (same continuation): SCM (Stellus Capital, a BDC) real secured
        # term-debt concept - see sec_statements.py's get_balance_sheet() comment on
        # "SecuredLongTermDebt" for the live evidence.
        "secured_long_term_debt",
        # FIXED 2026-09-05 (same continuation): KBDC (Kayne Anderson BDC) real fair-value
        # credit-facility concept - see sec_statements.py's get_balance_sheet() comment on
        # "LineOfCreditFacilityFairValueOfAmountOutstanding" for the live evidence and
        # magnitude cross-check.
        "line_of_credit_facility_fair_value_of_amount_outstanding",
        # FIXED 2026-09-07 (goal session: XBRL concept-coverage backlog sweep):
        # AccountsPayableTradeCurrent real fallback - see sec_balance_sheet.py's
        # get_balance_sheet() comment on "AccountsPayableTradeCurrent" for the live evidence
        # (223/485 tagging filers, including Abbott Labs/Air Products/Brown-Forman, have no
        # "AccountsPayableCurrent" at all). Must never win over the standard concept.
        "accounts_payable_trade_current",
        # ADDED 2026-09-09 (goal session: SEC/XBRL missing-data count under 700,
        # total_debt_not_itemized investigation): ETS real short-term-loan concept - see
        # sec_balance_sheet.py's get_balance_sheet() comment on "LoansPayable"/
        # "LoansPayableCurrent" for the live evidence. Must never win over a more specific
        # standard concept.
        "loans_payable",
        "loans_payable_current",
    }
)

# FIXED 2026-08-17 (loader-review goal continuation): the fallback-variant search for
# SBC/buybacks migration 1206's comment flagged as not-yet-done - see sec_statements.py's
# get_cash_flow() comment for the live evidence (FIP/DC/CNA report SBC only under
# "AllocatedShareBasedCompensationExpense"; SPWH reports buybacks only under
# "PaymentsForRepurchaseOfEquity"). Fallback-only for the same reason as
# _DEBT_FALLBACK_ONLY_FIELDS: a filer that DOES report the standard concept
# (ShareBasedCompensation / PaymentsForRepurchaseOfCommonStock) always keeps that value.

_BALANCE_FIELD_MAPPING = {
    "assets": "total_assets",
    "assets_current": "current_assets",
    "liabilities": "total_liabilities",
    "liabilities_current": "current_liabilities",
    "stockholders_equity": "stockholders_equity",
    # FIXED 2026-08-18 (roic_pct "missing_sec_data" audit): fallback for filers (ADM
    # live-confirmed, CIK 0000007084) that tag total equity including noncontrolling/minority
    # interest instead of the parent-only concept above. Flat lookup, not a priority order -
    # actual overwrite precedence comes from sec_statements.py's get_balance_sheet() concept
    # list order (fallback listed before "StockholdersEquity" there), same convention as the
    # cash fallbacks immediately below.
    "stockholders_equity_including_portion_attributable_to_noncontrolling_interest": "stockholders_equity",
    # ADDED 2026-09-02 (goal session: "missing SEC/XBRL data" audit, KKR live-confirmed):
    # see _DEBT_FALLBACK_ONLY_FIELDS's comment on the IncludingPortion key -
    # limited-partnership-structured filers (KKR pre-2018) tag total partner capital
    # instead of any StockholdersEquity concept. "partners_capital" (parent-only, NOT
    # fallback-only) is the direct partnership analogue of "stockholders_equity" above
    # and always wins; the IncludingPortion variant only fills years where the
    # parent-only concept is absent entirely.
    "partners_capital_including_portion_attributable_to_noncontrolling_interest": "stockholders_equity",
    "partners_capital": "stockholders_equity",
    # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep): mirrors
    # "stockholders_equity_including_portion_attributable_to_noncontrolling_interest"
    # above, for the MembersEquity family - see sec_balance_sheet.py's get_balance_sheet()
    # comment on the matching concept-list entry for the live evidence (ARXS). Fallback-only
    # (listed BEFORE "members_equity" below so the direct legal-structure analogue always
    # wins when both are present for the same fiscal year).
    "limited_liability_company_llc_members_equity_including_portion_attributable_to_noncontrolling_interest": "stockholders_equity",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" audit): LLC-
    # structured domestic filers (APGE/ARXS/ITG live-confirmed) tag "MembersEquity"
    # instead of any StockholdersEquity/PartnersCapital concept - see sec_statements.py's
    # get_balance_sheet() comment on the matching concept-list entry for the live
    # evidence. Direct legal-structure analogue, not fallback-only, same convention as
    # "partners_capital" above.
    "members_equity": "stockholders_equity",
    # FIXED 2026-07-28: these 6 concepts are fetched from real SEC XBRL data every run
    # (utils/external/sec_statements.py's get_balance_sheet(), GAAP + IFRS aliases both
    # present since the module was written) but had no target column here - a commit on
    # 2026-06-21 ("Clean up loader infrastructure - remove dead code") removed these exact
    # 6 entries from this mapping and from schema_cols below, mistaking real, actively-used
    # score-relevant balance sheet fields for dead code. Confirmed live: annual_balance_sheet
    # kept writing fresh rows every day (294 in the last 7 days) while goodwill/inventory/etc.
    # silently stopped updating on 2026-07-01 (the last rows written before the June 21
    # regression's effect worked through the existing per-symbol watermark backlog) - a real,
    # ~1-month-old active data-loss regression, not historically-always-missing data.
    "cash_and_cash_equivalents_at_carrying_value": "cash_and_equivalents",
    # FIXED 2026-08-03: two fallback concepts for filers that never tag the standard
    # concept above - banks (ZION live-confirmed) tag CashAndDueFromBanks instead, some
    # non-bank filers only tag the post-ASU-2016-18 combined cash+restricted-cash concept.
    # This dict is a flat lookup, not a priority order - actual overwrite precedence comes
    # from sec_statements.py's get_balance_sheet() concept list order (see its comment).
    "cash_and_due_from_banks": "cash_and_equivalents",
    "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents": "cash_and_equivalents",
    # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet() comment
    # on "ReceivablesNetCurrent" (WMT/COST/RTX live evidence) - fallback-only (see
    # _DEBT_FALLBACK_ONLY_FIELDS below), must never win over the standard concept.
    "receivables_net_current": "accounts_receivable",
    "accounts_receivable_net_current": "accounts_receivable",
    "inventory_net": "inventory",
    # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet() comment
    # on "InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings" - fallback-only
    # (see _DEBT_FALLBACK_ONLY_FIELDS above), must never win over the standard concept.
    "inventory_net_of_allowances_customer_advances_and_progress_billings": "inventory",
    # ADDED 2026-09-07 (goal: SEC/XBRL missing-data audit, migration 1263): see
    # sec_balance_sheet.py's get_balance_sheet() comment on "AccountsPayableCurrent" for the
    # live WMT/TGT evidence. Not fallback-only - this is the only concept fetched for this
    # column, same single-concept convention as accounts_receivable/inventory above.
    "accounts_payable_current": "accounts_payable",
    # ADDED 2026-09-07 (goal session: XBRL concept-coverage backlog sweep): see
    # sec_balance_sheet.py's get_balance_sheet() comment on "AccountsPayableTradeCurrent" for
    # the live evidence. Fallback-only (see _DEBT_FALLBACK_ONLY_FIELDS above), must never win
    # over the standard "AccountsPayableCurrent" concept.
    "accounts_payable_trade_current": "accounts_payable",
    # ADDED 2026-09-07 (goal: check_balance_sheet_identity NCI gap rootcaused, migration
    # 1265): see sec_balance_sheet.py's get_balance_sheet() comment on "MinorityInterest" for
    # the live XOM FY2009 evidence ($4,823,000,000, closing the assets vs.
    # liabilities+stockholders_equity gap exactly). Not fallback-only - single directly-tagged
    # concept, same convention as accounts_payable above.
    "minority_interest": "noncontrolling_interest",
    # ADDED 2026-09-09 (goal session: XBRL scan/tie-out exhaustiveness audit, migration 1274):
    # see sec_balance_sheet.py's get_balance_sheet() comment on
    # "TemporaryEquityCarryingAmountAttributableToParent" for the live OBAI/LTGO/SCTX evidence
    # - this concept exactly closes check_balance_sheet_identity's residual for the
    # PROK/ATTO/FAC/LTGO/SCTX-style mezzanine-equity population migration 1265's own comment
    # left unfixed. Not fallback-only - single directly-tagged concept, same convention as
    # minority_interest above.
    "temporary_equity_carrying_amount_attributable_to_parent": "temporary_equity",
    # ADDED 2026-09-07 (goal session: check_cashflow_reconciliation restricted-cash gap
    # rootcaused, migration 1267): see sec_balance_sheet.py's _fill_cash_and_restricted_cash_
    # combined() for the live ADP evidence. Identity mapping (raw key already equals the
    # canonical column name) - that helper writes the canonical name directly onto the row
    # since the underlying XBRL concept can't be reused for two different target columns via
    # the normal _aggregate_concepts pipeline (it already fallback-feeds cash_and_equivalents).
    "cash_and_restricted_cash_combined": "cash_and_restricted_cash_combined",
    # FIXED 2026-09-03 (same sweep): see sec_statements.py's get_balance_sheet() comments
    # on "PublicUtilitiesPropertyPlantAndEquipmentNet" (ES live evidence) and
    # "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciation
    # AndAmortization" (DASH/DINO live evidence) - both fallback-only (see
    # _DEBT_FALLBACK_ONLY_FIELDS below), must never win over the standard concept.
    "public_utilities_property_plant_and_equipment_net": "ppe_net",
    "property_plant_and_equipment_and_finance_lease_right_of_use_asset_after_accumulated_depreciation_and_amortization": "ppe_net",
    "property_plant_and_equipment_net": "ppe_net",
    "goodwill": "goodwill",
    "long_term_debt": "long_term_debt",
    # FIXED 2026-08-17 (loader-review goal continuation): fallback-only, see
    # _DEBT_FALLBACK_ONLY_FIELDS comment above.
    "notes_payable_related_parties_noncurrent": "long_term_debt",
    "long_term_notes_payable": "long_term_debt",
    "convertible_notes_payable": "long_term_debt",
    # FIXED 2026-08-18 (roic_pct "missing_sec_data" follow-up): see
    # _DEBT_FALLBACK_ONLY_FIELDS comment above (DKNG/DASH live evidence).
    "convertible_long_term_notes_payable": "long_term_debt",
    "long_term_debt_and_capital_lease_obligations_including_current_maturities": "long_term_debt",
    # FIXED 2026-08-18 (roic_pct "missing_sec_data" follow-up): see
    # _DEBT_FALLBACK_ONLY_FIELDS comment above (CAT/SLB/XOM live evidence).
    "long_term_debt_noncurrent": "long_term_debt",
    "long_term_debt_and_capital_lease_obligations": "long_term_debt",
    # FIXED 2026-08-18 (missing factor inputs audit): see _DEBT_FALLBACK_ONLY_FIELDS
    # comment above (ADC/net-lease-REIT live evidence - taxonomy switch mid-history, not
    # a genuine debt-free filer).
    "debt_instrument_carrying_amount": "long_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): BRK.A/BRK.B
    # (Berkshire Hathaway) real, ~$129B combined debt - see
    # utils/external/sec_custom_xbrl_concepts.py's CUSTOM_DEBT_CONCEPTS module comment for
    # the live evidence (two entity-level segment totals, no single consolidated "total
    # debt" line exists at all, structurally invisible to companyfacts). No current/
    # noncurrent split in the source data (Berkshire's balance sheet is unclassified), so
    # this maps to long_term_debt only, same convention as the other single-figure debt
    # fallbacks above. Fallback-only (see _DEBT_FALLBACK_ONLY_FIELDS below) so it never
    # overwrites a real value the normal concept-list extraction already found.
    "custom_extension_total_debt": "long_term_debt",
    # FIXED 2026-09-03 (same sweep): AES Corporation's real, ~$29.9B combined debt - see
    # utils/external/sec_custom_xbrl_concepts.py's CUSTOM_DEBT_LONGTERM_CONCEPTS/
    # CUSTOM_DEBT_SHORTTERM_CONCEPTS module comment for the live evidence (filer-specific
    # recourse/non-recourse debt tags, structurally invisible to companyfacts, same class as
    # CUSTOM_CAPEX_CONCEPTS's DHT/CMRE - not the Berkshire dimensioned-sum case above).
    # AES's source data DOES have a real current/noncurrent split (unlike Berkshire), so
    # this is a separate short_term_debt target, distinct from custom_extension_total_debt.
    "custom_extension_total_debt_current": "short_term_debt",
    # FIXED 2026-08-17 (migration 1204): real short-term/revolving debt concepts, previously
    # fetched nowhere - see sec_statements.py's get_balance_sheet() comment on why LongTermDebt
    # alone (the only debt concept fetched before this fix) misses commercial paper/short-term
    # notes payable. Companion fix to load_sec_valuations.py's total_debt mislabeling bug
    # (was reading total_liabilities, not any debt concept at all).
    "commercial_paper": "short_term_debt",
    "short_term_borrowings": "short_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): DE (Deere &
    # Company) real short-term debt - see sec_statements.py's get_balance_sheet() comment
    # on "DebtCurrent" for the live evidence.
    "debt_current": "short_term_debt",
    # ADDED 2026-09-09: SecuredDebt (DE's smaller sibling concept to DebtCurrent above) -
    # SUPERSEDES the prior "deliberately NOT mapped, no summing mechanism" decision. Made
    # fallback-only instead of summed: DebtCurrent (processed first, listed first in
    # sec_balance_sheet.py) already claims short_term_debt for DE, so this entry's
    # fallback-only check correctly skips DE and never overwrites/loses that value; for
    # the ~399 other filers that tag ONLY SecuredDebt (no DebtCurrent at all), this now
    # fills a previously-NULL short_term_debt instead of doing nothing. See that file's
    # own comment for the full DE reasoning this update builds on.
    "secured_debt": "short_term_debt",
    # ADDED 2026-09-09: current-portion split of notes_payable (see sec_balance_sheet.py's
    # NotesPayable comment: "no NotesPayableCurrent sibling" was explicitly noted as absent
    # for AFL/MAA, implying other filers DO report it) - same generic-name caution as
    # debt_current above.
    "notes_payable_current": "short_term_debt",
    # FIXED 2026-09-03 (same sweep): EXPD (Expeditors International) real short-term
    # debt - see sec_statements.py's get_balance_sheet() comment on
    # "ShortTermBankLoansAndNotesPayable" for the live evidence.
    "short_term_bank_loans_and_notes_payable": "short_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): mortgage
    # REIT repo-agreement financing - see sec_statements.py's get_balance_sheet() comment
    # on "SecuritiesSoldUnderAgreementsToRepurchase" for the live evidence (AGNC/ARR).
    "securities_sold_under_agreements_to_repurchase": "short_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, SEVN
    # follow-up): see sec_statements.py's get_balance_sheet() comment on
    # "SecuredDebtRepurchaseAgreements" for the live evidence (SEVN).
    "secured_debt_repurchase_agreements": "short_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): VRSN
    # (VeriSign) real debt concept - see sec_statements.py's get_balance_sheet() comment
    # on SeniorNotes/SeniorNotesCurrent for the live evidence. Same either/or-alternative,
    # plain-mapping convention as commercial_paper/short_term_borrowings above.
    "senior_notes": "long_term_debt",
    "senior_notes_current": "short_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): AFL/MAA
    # real debt concept - see sec_statements.py's get_balance_sheet() comment on
    # "NotesPayable" for the live evidence. Same either/or-alternative, plain-mapping
    # convention as senior_notes above.
    "notes_payable": "long_term_debt",
    # ADDED 2026-09-09 (goal session: SEC/XBRL missing-data count under 700,
    # total_debt_not_itemized investigation): ETS real short-term-loan concept - see
    # sec_balance_sheet.py's get_balance_sheet() comment on "LoansPayable"/
    # "LoansPayableCurrent" for the live evidence. Same either/or-alternative, plain-mapping
    # convention as senior_notes/notes_payable above.
    "loans_payable": "long_term_debt",
    "loans_payable_current": "short_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): PGR
    # (Progressive) real debt concept - see sec_statements.py's get_balance_sheet()
    # comment on "DebtLongtermAndShorttermCombinedAmount" for the live evidence. Same
    # fallback-only, single-figure convention as notes_payable above.
    "debt_longterm_and_shortterm_combined_amount": "long_term_debt",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): IBOC/HBT
    # real trust-preferred/subordinated-debenture debt - see sec_statements.py's
    # get_balance_sheet() comment on "SubordinatedDebt"/"JuniorSubordinatedDebentureOwedTo
    # UnconsolidatedSubsidiaryTrust" for the live evidence. Same fallback-only,
    # single-figure convention as notes_payable/debt_longterm_and_shortterm_combined_
    # amount above.
    "subordinated_debt": "long_term_debt",
    "junior_subordinated_debenture_owed_to_unconsolidated_subsidiary_trust": "long_term_debt",
    # FIXED 2026-09-05 (goal session: "missing SEC/XBRL data" sweep): Donegal Group
    # (DGICA/DGICB) real revolving-credit debt - see sec_statements.py's get_balance_sheet()
    # comment on "LineOfCredit" for the live evidence. Same fallback-only, single-figure
    # convention as notes_payable/subordinated_debt above.
    "line_of_credit": "long_term_debt",
    # FIXED 2026-09-05 (goal session: "missing SEC/XBRL data" continuation,
    # total_debt_not_itemized investigation): ACHV/BENF real convertible-note debt - see
    # sec_statements.py's get_balance_sheet() comment on "ConvertibleDebt" for the live
    # evidence ($16.66M ACHV FY2023; split into Current/Noncurrent starting FY2024). Same
    # either/or-alternative convention as senior_notes/senior_notes_current above - a
    # filer reporting the split never also reports the bare concept for the same year.
    "convertible_debt": "long_term_debt",
    "convertible_debt_current": "short_term_debt",
    "convertible_debt_noncurrent": "long_term_debt",
    # FIXED 2026-09-05 (same sweep): BENF (Beneficient) real long-term debt - see
    # sec_statements.py's get_balance_sheet() comment on "OtherLongTermDebt" for the live
    # evidence ($117.9M FY2025/$96.8M FY2026). Fallback-only, single-figure convention as
    # notes_payable/subordinated_debt above.
    "other_long_term_debt": "long_term_debt",
    # FIXED 2026-09-05 (same sweep): SCM (Stellus Capital, a BDC) real secured term-debt -
    # see sec_statements.py's get_balance_sheet() comment on "SecuredLongTermDebt" for the
    # live evidence ($299M FY2025). Fallback-only, single-figure convention as above.
    "secured_long_term_debt": "long_term_debt",
    # FIXED 2026-09-05 (same sweep): KBDC (Kayne Anderson BDC) real fair-value credit-
    # facility balance - see sec_statements.py's get_balance_sheet() comment on
    # "LineOfCreditFacilityFairValueOfAmountOutstanding" for the live evidence and
    # magnitude cross-check against implied total liabilities (96% match). Fallback-only,
    # single-figure convention as above.
    "line_of_credit_facility_fair_value_of_amount_outstanding": "long_term_debt",
    # FIXED 2026-08-17 (migration 1205): post-ASC 842 capitalized lease liabilities -
    # see sec_statements.py's get_balance_sheet() comment for why these use the combined
    # (not Current/Noncurrent split) XBRL tags. Included in load_sec_valuations.py's
    # total_debt per the S&P/Moody's adjusted-debt convention (operating leases) plus
    # unambiguous debt (finance leases).
    "operating_lease_liability": "operating_lease_liability",
    "finance_lease_liability": "finance_lease_liability",
    **_MARKER_FIELDS,
}

# ADDED 2026-08-26 (Quality pillar literature audit): Altman Z''-Score's Retained Earnings/
# Total Assets term - see sec_statements.py's get_balance_sheet() comment. Kept out of the
# shared _BALANCE_FIELD_MAPPING base dict deliberately: that dict is reused by every period's
# balance-sheet config, and each period has its own schema_cols frozenset - merging a mapping
# into the shared base for a column not every period's table has raises sec_base.py's "not in
# target schema" RuntimeError (self._schema_cols is hardcoded per-config, not introspected
# from the live DB). Live-caught 2026-08-26 when this exact mistake broke every quarterly
# fetch. Migration 1234 added `retained_earnings` to annual_balance_sheet; migration 1266
# (2026-09-07) added the equivalent to quarterly_balance_sheet too, via its own
# _QUARTERLY_BALANCE_EXTRA below rather than merging here - same pattern,
# _QUARTERLY_INCOME_EXTRA already established it for period_end. TTM still has no
# retained_earnings column - nothing in this codebase consumes a TTM Altman Z''-Score.

_ANNUAL_BALANCE_EXTRA = {"retained_earnings_accumulated_deficit": "retained_earnings"}


# ADDED 2026-09-07 (goal session: quarterly_balance_sheet missing retained_earnings column):
# every quarterly balance-sheet fetch already pulls the real SEC-tagged
# "RetainedEarningsAccumulatedDeficit" concept (see sec_balance_sheet.py's get_balance_sheet(),
# concept list is shared with annual) but quarterly_balance_sheet had no column to store it in,
# so it was discarded post-fetch with an "Unmapped SEC field" warning on every symbol, every
# quarter. Kept separate from _QUARTERLY_EXTRA (shared by cashflow/income-statement quarterly
# configs too) for the same reason _QUARTERLY_INCOME_EXTRA is separate above - merging into the
# shared dict would raise sec_base.py's "not in target schema" RuntimeError for the other two
# statement types, whose schema_cols don't have this column (see _ANNUAL_BALANCE_EXTRA's
# comment for the live 2026-08-26 incident this exact mistake caused).
_QUARTERLY_BALANCE_EXTRA = {**_QUARTERLY_EXTRA, "retained_earnings_accumulated_deficit": "retained_earnings"}


def get_balance_sheet_config(period: str) -> dict[str, Any]:
    """Balance sheet configuration for annual/quarterly/ttm."""
    if period == "annual":
        return {
            "table_name": "annual_balance_sheet",
            "field_mapping": {**_BALANCE_FIELD_MAPPING, **_ANNUAL_BALANCE_EXTRA},
            "fallback_only_fields": _DEBT_FALLBACK_ONLY_FIELDS,
            "primary_key": ("symbol", "fiscal_year"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "fiscal_year",
                    "total_assets",
                    "current_assets",
                    "total_liabilities",
                    "current_liabilities",
                    "stockholders_equity",
                    "cash_and_equivalents",
                    "accounts_receivable",
                    "accounts_payable",
                    "inventory",
                    "ppe_net",
                    "goodwill",
                    "long_term_debt",
                    "short_term_debt",
                    "operating_lease_liability",
                    "finance_lease_liability",
                    "noncontrolling_interest",
                    "temporary_equity",
                    "cash_and_restricted_cash_combined",
                    "retained_earnings",
                    "created_at",
                    "data_unavailable",
                    "reason",
                    "data_source",
                ]
            ),
        }
    elif period == "quarterly":
        return {
            "table_name": "quarterly_balance_sheet",
            "field_mapping": {**_BALANCE_FIELD_MAPPING, **_QUARTERLY_BALANCE_EXTRA},
            "fallback_only_fields": _DEBT_FALLBACK_ONLY_FIELDS,
            "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "fiscal_year",
                    "fiscal_quarter",
                    "total_assets",
                    "current_assets",
                    "total_liabilities",
                    "current_liabilities",
                    "stockholders_equity",
                    "cash_and_equivalents",
                    "accounts_receivable",
                    "accounts_payable",
                    "inventory",
                    "ppe_net",
                    "goodwill",
                    "long_term_debt",
                    "short_term_debt",
                    "operating_lease_liability",
                    "finance_lease_liability",
                    "noncontrolling_interest",
                    "temporary_equity",
                    "cash_and_restricted_cash_combined",
                    "retained_earnings",
                    "created_at",
                    "data_unavailable",
                    "reason",
                    "data_source",
                ]
            ),
        }
    elif period == "ttm":
        return {
            "table_name": "ttm_balance_sheet",
            "field_mapping": dict(_BALANCE_FIELD_MAPPING),
            "primary_key": ("symbol", "report_date"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "report_date",
                    "total_assets",
                    "current_assets",
                    "total_liabilities",
                    "current_liabilities",
                    "stockholders_equity",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    else:
        raise ValueError(f"Unknown period: {period}")
