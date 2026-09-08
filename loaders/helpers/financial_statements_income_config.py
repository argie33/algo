"""Income-statement field mapping and get_income_statement_config(), extracted from
load_financial_statements.py (2026-09-07, file-size ratchet: that file was at its
4244-line ratcheted baseline, past the 2000-line HARD_CEILING in
.pre-commit-scripts/check_file_size_ratchet.py where no baseline raise is ever accepted -
adding the goodwill_impairment_loss field required first shrinking the file below that
baseline in the same commit). Split three ways by statement type (this module, plus the
balance/cashflow siblings) rather than one combined module, since a single combined
module came in at 1394 lines - over the ratchet's 800-line cap for new files. Same
extraction convention as loaders/helpers/sec_valuations_ratios.py (see that file's
docstring): code moved verbatim, only wrapped in a new module - behavior is unchanged.
"""

from typing import Any

from loaders.helpers.financial_statements_config_shared import _MARKER_FIELDS, _QUARTERLY_EXTRA

_INCOME_FIELD_MAPPING = {
    "revenues": "revenue",
    # FIXED 2026-08-31 (goal session: "get all the data we need" full-coverage audit):
    # IFRS 17 InsuranceRevenue now gets its own target_key ("insurance_revenue" - see
    # sec_statements.py's comment on the alias) instead of sharing "revenues" with plain
    # Revenue/RevenueAndOperatingIncome. Live-confirmed via real SEC companyfacts JSON:
    # BBVA (a bank with a minority insurance subsidiary) tags a real but small, sometimes
    # NEGATIVE InsuranceRevenue fact (e.g. FY2025 EUR -3.627B - the segment's net result,
    # not a revenue total at all) that was winning "revenue" over BBVA's real ~EUR26B
    # total (tagged InterestRevenueExpense) purely because both facts share the exact
    # same filed date (same 20-F) and InsuranceRevenue is listed earlier in
    # _INCOME_IFRS_ALIASES - _aggregate_concepts's tiebreak keeps whichever fact was
    # inserted first on an exact filed-date tie, so "last-listed wins" never actually
    # applied here. Same bug independently corrupted HSBC (real total ~$65-68B tagged
    # RevenueAndOperatingIncome, but InsuranceRevenue's small ~$2-3B insurance-segment
    # figure - a real but ~20x-too-small number - silently won instead, undetected until
    # now because it's positive and merely implausibly small rather than negative).
    # See _REVENUE_TOTAL_CANDIDATE_FIELDS in loaders/helpers/sec_base.py for the new
    # magnitude-based resolution among the fields below that fixes this generally rather
    # than special-casing BBVA/HSBC - AEG (a genuine insurer with no bank-interest
    # concepts) is unaffected since InsuranceRevenue is still its only real candidate.
    "insurance_revenue": "revenue",
    # FIXED 2026-08-09: older/narrower goods-revenue tag some pre-2011-ish filers use
    # instead of "Revenues"/"SalesRevenueNet" - see sec_statements.py's concepts-list
    # comment on SalesRevenueGoodsNet for the live-verified AGCO case this recovers.
    "sales_revenue_goods_net": "revenue",
    "sales_revenue_net": "revenue",
    "revenue_from_contract_with_customer_including_assessed_tax": "revenue",
    "revenue_from_contract_with_customer_excluding_assessed_tax": "revenue",
    # FIXED 2026-08-19: equity REITs' ASC 842 lease-revenue tag - see sec_statements.py's
    # comment on OperatingLeaseLeaseIncome for the live-verified AMH/EQR cases this
    # recovers. REIT-gated via _REIT_REVENUE_FALLBACK_ONLY_FIELDS below, not a plain
    # mapping - see that set's comment for why.
    "operating_lease_lease_income": "revenue",
    # ADDED 2026-09-01 (recovered from the growth-multi-input-blend worktree, found stranded
    # off main): older-era (pre-ASC 842, largely pre-2016) equity REITs used this concept as
    # their real estate rental revenue total before "OperatingLeaseLeaseIncome" existed as a
    # tag at all - see utils/external/sec_statements.py's comment on RealEstateRevenueNet for
    # the live-verified ARE case. Same _REIT_EXCLUSIVE_FIELDS wiring as
    # operating_lease_lease_income below (never touches "revenue" outside a confirmed REIT).
    "real_estate_revenue_net": "revenue",
    # FIXED 2026-08-01: RevenuesNetOfInterestExpense for banks (2020+ data).
    # Maps to same "revenue" column - this is the standard revenue metric for
    # financial services companies since 2020. Ordering in sec_statements.py
    # ensures last-listed concept (this one for banks) wins on overwrite.
    "revenues_net_of_interest_expense": "revenue",
    # FIXED 2026-08-22: foreign IFRS-filing banks' gross interest income/expense line - see
    # sec_statements.py's comment on InterestRevenueExpense (live-verified via WF/Woori
    # Financial Group) for the full rationale. Same target column as every other revenue
    # fallback above.
    "interest_revenue_expense": "revenue",
    # FIXED 2026-08-03: mortgage REITs (AGNC, NLY live-confirmed) report gross interest
    # income as their revenue-equivalent line, not any concept above - see sec_statements.py's
    # comment on InterestIncomeOperating for why InterestIncomeExpenseNet (which goes negative
    # in real years) was rejected in favor of this gross, always-positive figure.
    "interest_income_operating": "revenue",
    # FIXED 2026-08-03: community banks/thrifts (FNWB, AMAL, OCFC, and others - live-confirmed
    # via real SEC companyfacts JSON for all three) report neither standard revenue concepts
    # nor RevenuesNetOfInterestExpense (that one's used by larger banks like MS/WFC) - their
    # primary revenue-equivalent line is InterestAndDividendIncomeOperating. Live-verified for
    # FNWB: values for FY2022-2025 line up with the same fiscal years NetIncomeLoss already had
    # real data for, confirming this is the right concept, not a guess. Ordering in
    # sec_statements.py places this after revenues_net_of_interest_expense so it only wins for
    # filers that have nothing else.
    "interest_and_dividend_income_operating": "revenue",
    # FIXED 2026-08-22: a small number of community banks (AROW live-confirmed) tag their
    # combined interest+dividend income total under this concept instead of
    # InterestAndDividendIncomeOperating - see sec_statements.py's comment on
    # InvestmentIncomeInterestAndDividend for the live-verified arithmetic proving this is
    # a real total, not a partial line item. Same target column as every revenue fallback
    # above.
    "investment_income_interest_and_dividend": "revenue",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): BDCs'
    # gross-investment-income top line - see sec_statements.py's comment on
    # GrossInvestmentIncomeOperating for the live-verified CSWC/PFLT/ICMB evidence.
    # Fallback-only (see _REVENUE_FALLBACK_ONLY_FIELDS below), same convention as every
    # other revenue proxy above.
    "gross_investment_income_operating": "revenue",
    # FIXED 2026-08-19: regulated electric/gas utilities' post-ASC-606 revenue tags - see
    # sec_statements.py's comments on RegulatedOperatingRevenue/
    # RegulatedAndUnregulatedOperatingRevenue for the live-verified XEL/DTE/OGS cases this
    # recovers (7+ years of real revenue that had gone silently NULL despite the company
    # continuing to file real, current 10-Ks).
    "regulated_operating_revenue": "revenue",
    "regulated_and_unregulated_operating_revenue": "revenue",
    # FIX 2026-09-02 (goal: "SEC/XBRL missing data" audit): identity key
    # ConsolidatedFinancialStatementsLoader.fetch_incremental() sets directly on rows for
    # symbols in utils/external/sec_custom_xbrl_concepts.py's CUSTOM_REVENUE_CONCEPTS -
    # see that module's docstring for why (real revenue tagged under a filer-specific
    # custom XBRL extension taxonomy, structurally invisible to the companyfacts API this
    # file's normal concept-list extraction depends on). fallback_only (see
    # _REVENUE_FALLBACK_ONLY_FIELDS below) so it never overwrites a real value the normal
    # SEC extraction already found.
    "custom_extension_revenue": "revenue",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, pe_ratio/
    # peg_ratio investigation): identity keys set directly on rows for symbols in
    # utils/external/sec_custom_xbrl_concepts.py's CUSTOM_INCOME_DIMENSIONED_CONCEPTS - see
    # that module's docstring (DB's real net_income/basic_eps/diluted_eps tagged only under
    # a single-explicitMember dimensioned context, invisible to the normal concept-list
    # extraction the same way CUSTOM_REVENUE_CONCEPTS is above). fallback_only (see
    # _REVENUE_FALLBACK_ONLY_FIELDS below) so these never overwrite a real value the normal
    # SEC extraction already found.
    "custom_extension_net_income": "net_income",
    "custom_extension_eps_basic": "earnings_per_share",
    "custom_extension_eps_diluted": "diluted_eps",
    "cost_of_revenue": "cost_of_revenue",
    # FIXED 2026-08-17 (goal: "no SEC data" audit): "CostOfGoodsAndServicesSold" concept
    # added to sec_statements.py's get_income_statement() concepts list - see that file's
    # comment above the concept for the live-verified AMZN/COST/CI/JD/SHEL/TTE cases this
    # recovers. Same target column as "cost_of_revenue" above.
    "cost_of_goods_and_services_sold": "cost_of_revenue",
    # FIXED 2026-08-31 (goal session: "get all the data we need" full-coverage audit): see
    # sec_statements.py's comment on these two concepts for the live-verified LIN case -
    # industrial/materials filers that break out D&A separately tag this DD&A-excluded COGS
    # variant instead of any concept above. Same target column, fallback-only (see
    # _REVENUE_FALLBACK_ONLY_FIELDS below) since excluding D&A makes it a narrower figure
    # than a full COGS-including-D&A tag when a filer reports both.
    "cost_of_goods_and_service_excluding_depreciation_depletion_and_amortization": "cost_of_revenue",
    "cost_of_goods_sold_excluding_depreciation_depletion_and_amortization": "cost_of_revenue",
    # FIXED 2026-09-07 (goal session: "make sure the list/checks are right, then fix issues"
    # audit): fallback-only, see sec_statements.py's get_income_statement() comment on
    # "CostOfGoodsSold" for the live Halliburton/Thermo Fisher/NCR Voyix evidence.
    "cost_of_goods_sold": "cost_of_revenue",
    # FIXED 2026-08-31 (goal session, same sweep as the DD&A-excluded COGS fix above): see
    # sec_statements.py's comment on these two concepts (LYV/AWK/WTRG/MSEX/YORW live-
    # verified). Same target column, fallback-only (see _REVENUE_FALLBACK_ONLY_FIELDS)
    # since both are narrower, business-model-specific cost measures.
    "direct_operating_costs": "cost_of_revenue",
    "utilities_operating_expense_maintenance_and_operations": "cost_of_revenue",
    "gross_profit": "gross_profit",
    # ADDED 2026-08-27 (goal: close the R&D intensity/Mohanram G-Score literature-checklist gap -
    # see sec_statements.py's get_income_statement() comment for the live-verification note).
    # Both concepts map to the same target column (broader standard tag listed later in that
    # file's concepts list, so it wins on overwrite for filers reporting both).
    "research_and_development_expense_excluding_acquired_in_process_cost": "research_development_expense",
    "research_and_development_expense": "research_development_expense",
    # ADDED 2026-09-07 (migration 1264): see sec_income_statement.py's comment on
    # "SellingGeneralAndAdministrativeExpense" for the live WMT/TGT/AAR/ABT evidence.
    "selling_general_and_administrative_expense": "operating_expenses",
    # ADDED 2026-09-07 (migration 1271): see sec_income_statement.py's comment on
    # "GoodwillImpairmentLoss" for the live SOFI/Morgan Stanley/Par Technology evidence.
    # Deliberately only this one us-gaap concept mapped, not a broader impairment catch-all
    # (e.g. "AssetImpairmentCharges" or "ImpairmentOfLongLivedAssetsHeldForUse") - those mix
    # in non-goodwill impairments (PP&E, other intangibles, ROU assets) and would silently
    # overstate a goodwill-specific figure if aliased to the same column. Same target column
    # name as the DB column - a plain pass-through mapping, no fallback tier.
    "goodwill_impairment_loss": "goodwill_impairment_loss",
    "operating_income_loss": "operating_income",
    "net_income_loss": "net_income",
    # FIXED 2026-08-17 (goal: "no SEC data" audit): "ProfitLoss" added to sec_statements.py's
    # get_income_statement() concepts list - see that file's comment above the concept for the
    # live-verified PRI (Primerica) case this recovers: PRI has ZERO NetIncomeLoss entries in
    # its us-gaap facts (confirmed via companyfacts JSON) but reports the exact same figure
    # under ProfitLoss instead (FY2025: $751,234,000, matching pretax_income - income_tax_expense
    # exactly). Same target column as "net_income_loss" above.
    "profit_loss": "net_income",
    # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data" sweep): ESOA-class filers that
    # stop tagging both NetIncomeLoss and ProfitLoss - see sec_statements.py's
    # get_income_statement() comment on "IncomeLossFromContinuingOperationsIncludingPortion
    # AttributableToNoncontrollingInterest" for the live evidence. Same target column as
    # "net_income_loss"/"profit_loss" above; fallback-only via _REVENUE_FALLBACK_ONLY_FIELDS.
    "income_loss_from_continuing_operations_including_portion_attributable_to_noncontrolling_interest": "net_income",
    # ADDED 2026-09-07 (migration 1270): see sec_income_statement.py's comment on these concepts.
    "net_income_loss_available_to_common_stockholders_basic": "net_income_attributable_to_common",
    "net_income_loss_available_to_common_stockholders_diluted": "net_income_attributable_to_common",
    # ADDED 2026-09-08 (goal session: XBRL coverage-scan backlog triage, 3rd batch this
    # session): IFRS's "ordinary equity holders" concept pair - see
    # sec_income_statement.py's own comment on these two _INCOME_IFRS_ALIASES entries for the
    # live BNS evidence (real, material gap vs. "ProfitLossAttributableToOwnersOfParent",
    # confirming it's the genuine IFRS analog of the two us-gaap keys immediately above, not a
    # relabeled duplicate). Same target column.
    "profit_loss_attributable_to_ordinary_equity_holders_of_parent_entity": "net_income_attributable_to_common",
    "profit_loss_attributable_to_ordinary_equity_holders_of_parent_entity_including_dilutive_effects": (
        "net_income_attributable_to_common"
    ),
    "earnings_per_share_basic": "earnings_per_share",
    # FIXED 2026-07-28: EarningsPerShareDiluted (GAAP) and DilutedEarningsLossPerShare
    # (IFRS alias, both target this same key - see sec_statements.py's _INCOME_IFRS_ALIASES)
    # have been fetched from real SEC XBRL data all along, but this mapping never listed a
    # target column - unmapped keys are silently skipped by transform() (see this module's
    # comment above _MARKER_FIELDS), so diluted_eps sat 100% NULL across all 61,427 rows
    # despite the column existing and real data being available every run. Zero consumers
    # currently read diluted_eps (grep-confirmed) so this is additive, not fixing a live
    # scoring bug - but it's a real, standard, already-fetched metric worth actually having.
    "earnings_per_share_diluted": "diluted_eps",
    # FIXED 2026-07-28 (migration 1171): WeightedAverageNumberOfSharesOutstandingBasic has
    # been fetched from real SEC XBRL data all along but had no target column - see
    # sec_statements.py's comment above this concept. load_sec_valuations.py previously
    # derived a lossier proxy (net_income/eps) believing it already used this concept.
    "weighted_average_number_of_shares_outstanding_basic": "shares_outstanding_basic",
    # FIXED (migration 1192): fallback share count column, kept separate from
    # shares_outstanding_basic above - see sec_statements.py's comment on this concept.
    "weighted_average_number_of_diluted_shares_outstanding": "shares_outstanding_diluted",
    # FIXED 2026-08-03: point-in-time/blended share-count fallbacks for filers that tag
    # neither weighted-average concept above - see sec_statements.py's comments on
    # CommonStockSharesOutstanding/WeightedAverageNumberOfShareOutstandingBasicAndDiluted/
    # NumberOfSharesOutstanding (IFRS) for the live-verified filers (PLNT/WHD/YOU/SPT/JG/
    # BNR/TV/FMX) this recovers. All three map to shares_outstanding_basic, same as the
    # real weighted-average concept, since these filers have no separate weighted-average
    # tag to prefer instead.
    # FIXED (migration 1195): shares issued (can include treasury stock, so listed before
    # common_stock_shares_outstanding in sec_statements.py's concepts list to lose on
    # overwrite whenever the real outstanding count is also present).
    "common_stock_shares_issued": "shares_outstanding_basic",
    "common_stock_shares_outstanding": "shares_outstanding_basic",
    "weighted_average_number_of_share_outstanding_basic_and_diluted": "shares_outstanding_basic",
    # FIXED (migration 1195): dei:EntityCommonStockSharesOutstanding cover-page fact -
    # own column, not shares_outstanding_basic, per sec_statements.py's dei_aliases
    # docstring (this fact is present even for filers that already report a real
    # weighted-average count, so sharing a column risks a silent downgrade).
    "entity_common_stock_shares_outstanding": "shares_outstanding_dei",
    "interest_expense": "interest_expense",
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): JKHY (Jack
    # Henry & Associates) taxonomy-relabeled concept - see sec_statements.py's
    # get_income_statement() comment on InterestExpenseOperating for the live evidence
    # (identical value to plain InterestExpense in the one overlap year). Not fallback-
    # only, same "plain relabel" convention as interest_expense_nonoperating/
    # interest_expense_debt below.
    "interest_expense_operating": "interest_expense",
    # FIXED 2026-08-03: real, live-confirmed concepts some filers use INSTEAD of plain
    # "InterestExpense" - see sec_statements.py's comment above these concepts. WMT never
    # reports "InterestExpense" at all (only "InterestExpenseDebt"); JNJ's taxonomy migrated
    # to "InterestExpenseNonoperating" starting FY2024.
    "interest_expense_nonoperating": "interest_expense",
    "interest_expense_debt": "interest_expense",
    # FIXED 2026-08-18 (goal: "no SEC data"/loader audit): see sec_statements.py's
    # get_income_statement() comment for the live evidence (TXN/BA use
    # InterestAndDebtExpense; NEE uses the cash-basis InterestPaidNet as a last resort).
    "interest_and_debt_expense": "interest_expense",
    # FIXED 2026-09-03 (same sweep): EPAC (Enerpac Tool Group) has tagged real,
    # continuous, non-zero interest expense under this concept for its entire filing
    # history - see sec_statements.py's get_income_statement() comment on
    # FinancingInterestExpense for the live evidence (EPAC has no "InterestExpense" at
    # all, and its rare "InterestAndDebtExpense" entries are a genuinely different,
    # smaller line item, not a duplicate). Fallback-only (added to
    # _REVENUE_FALLBACK_ONLY_FIELDS below, which despite its name is this file's shared
    # "only fills an already-empty db_field" bucket for the whole income-statement
    # config) so it never overwrites InterestAndDebtExpense's rare real value for EPAC.
    "financing_interest_expense": "interest_expense",
    "interest_paid_net": "interest_expense",
    # FIXED 2026-09-03 (same "cash paid" fallback tier as interest_paid_net above - see
    # sec_statements.py's get_income_statement() comment on "InterestPaid", ARW).
    "interest_paid": "interest_expense",
    # This mapping key was always correct - the bug was in sec_statements.py's
    # get_income_statement(), which fetched concept "DepreciationExpense" (not a real
    # us-gaap XBRL concept - live-confirmed absent from both AAPL's and MSFT's
    # companyfacts) instead of "Depreciation" (the real concept, live-confirmed present
    # for both, which _to_snake()'s to this "depreciation" key). Fixed there 2026-07-28;
    # live-verified annual_income_statement.depreciation_expense was 0/61,427 populated
    # before that fix. See that module's comment for the full story.
    "depreciation": "depreciation_expense",  # Session 398: EBITDA extraction
    "depreciation_and_amortization": "amortization_expense",  # Fallback if separate D/A not available
    # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): combined
    # D&A taxonomy-transition concept - see sec_statements.py's get_income_statement()
    # comment on DepreciationDepletionAndAmortization for the live-verified PG/WM/ULTA/
    # WSM/CP evidence. Same target column as depreciation_and_amortization above.
    "depreciation_depletion_and_amortization": "amortization_expense",
    "amortization_of_intangibles": "amortization_expense",  # Alt source for amortization
    # FIXED 2026-09-07 (goal session: tie-out/XBRL check audit): AmortizationOfIntangibles
    # above is essentially never tagged in practice (0/5,373 filers in the on-disk
    # companyfacts cache) - wrongly dismissed as a duplicate of this concept in
    # scripts/xbrl_concept_coverage_dismissed.json, which is actually tagged by
    # 3,268/5,373 filers (61%) and was never fetched anywhere. Same target column per
    # this file's "last-listed wins" convention.
    "amortization_of_intangible_assets": "amortization_expense",
    # For roic_pct real effective-tax-rate computation (see sec_statements.py's comment
    # above these concepts for the live-verification note).
    "income_tax_expense_benefit": "income_tax_expense",
    # CNX-class filers (E&P/domestic-only) report pretax income under this concept instead -
    # see sec_statements.py's get_income_statement() comment for the live-verification note.
    "income_loss_from_continuing_operations_before_income_taxes_domestic": "pretax_income",
    "income_loss_from_continuing_operations_before_income_taxes_minority_interest_and_income_loss_from_equity_method_investments": "pretax_income",
    "income_loss_from_continuing_operations_before_income_taxes_extraordinary_items_noncontrolling_interest": "pretax_income",
    # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data" sweep): identity entries for
    # the two derived final-column keys sec_statements.py's
    # _fill_income_tax_expense_from_current_deferred_split()/
    # _fill_pretax_income_from_results_of_operations_when_validated() write directly (e.g.
    # row["income_tax_expense"] = current + deferred) - unlike every other fallback in this
    # dict, those two functions set the DB column name itself, not a raw SEC-concept-derived
    # key, because they combine two SEPARATE concepts (no single concept alias to hang the
    # mapping off). Without these entries, transform()'s `if sec_field not in field_mapping`
    # check silently discarded both computed values on every row that reached this path
    # (verified empirically: dict(_INCOME_FIELD_MAPPING) has no "income_tax_expense"/
    # "pretax_income" key without this fix) - the exact "wiring half-landed" bug class
    # already caught twice before (see debt_fallback_wiring_half_landed_recurring_bug_class
    # in memory), just for a fill-function's OWN output key instead of a missing concept
    # string. This silently no-opped the CNS (income_tax_expense) and RRC
    # (pretax_income) fixes those functions' own docstrings/tests describe - their unit
    # tests only exercised the pure function in isolation, never round-tripped through
    # transform(), so the gap passed CI undetected.
    "income_tax_expense": "income_tax_expense",
    "pretax_income": "pretax_income",
    **_MARKER_FIELDS,
}

# FIXED 2026-08-09: these two concepts are a last-resort revenue proxy for banks/REITs
# with no standard revenue tag (see the mapping comments above) - the "last-listed wins"
# overwrite this dict relies on only produces the documented behavior ("wins for filers
# with nothing else") when a company genuinely never reports one of the concepts above
# it. Live-confirmed that's not always true: ORLY (a normal retailer) reports a small
# real InterestAndDividendIncomeOperating line item (interest on cash investments)
# alongside its real revenue - sec_base.py's transform() now only writes these two into
# "revenue" if nothing else already has, instead of unconditionally overwriting.
#
# FIXED 2026-08-09 (same day, later session): "sales_revenue_net" added to this set too.
# That key is fed by two different source concepts depending on taxonomy - us-gaap
# "SalesRevenueNet" (a real total-revenue tag for some legacy/pre-ASC-606 filers, where
# it's meant to be primary) and ifrs-full "RevenueFromSaleOfGoods" (see
# sec_statements.py's _INCOME_IFRS_ALIASES) - but the latter is only the GOODS sub-line
# for companies that also report separate services/subscription revenue, not the total.
# Live-confirmed via KARO (Karooooo/Cartrack, pure IFRS 20-F filer, live companyfacts
# JSON): real total "Revenue" FY2025 = ZAR 4,567,459,000 (built from
# SubscriptionCirculationRevenue ZAR 4,055,394,000 + RevenueFromRenderingOfTransportServices
# ZAR 2,099,000 + RevenueFromSaleOfGoods ZAR 37,018,000 + other lines), but
# "RevenueFromSaleOfGoods" alone (ZAR 37,018,000) was overwriting it in the "revenue"
# column - same "last-listed wins unconditionally" bug class as the ORLY case above, this
# time triggered by two semantically-different concepts colliding on the same alias
# target_key rather than a single concept's fallback role. Making it fallback-only is
# safe for the legacy us-gaap filers this key also serves: when they have no separate
# "Revenues"/ASC-606 tag (the case the AGCO-style fix for sales_revenue_goods_net below
# depends on), "revenue" isn't populated yet when this key is reached, so it still writes
# normally - it only stops clobbering an already-real total. "sales_revenue_goods_net"
# (a separate, distinctly-keyed us-gaap concept - see the AGCO/pre-2011-filer comment on
# it in sec_statements.py) is added for the same defensive reason, though not yet
# live-confirmed as double-booked for any filer.

_REVENUE_FALLBACK_ONLY_FIELDS = frozenset(
    {
        "interest_income_operating",
        "interest_and_dividend_income_operating",
        # FIXED 2026-08-22: same fallback-only reasoning as interest_and_dividend_income_
        # operating just above - see sec_statements.py's comment on
        # InvestmentIncomeInterestAndDividend and this dict's own comment on that key.
        "investment_income_interest_and_dividend",
        # FIXED 2026-09-03: BDC gross-investment-income fallback - see
        # _INCOME_FIELD_MAPPING's comment on "gross_investment_income_operating" above.
        "gross_investment_income_operating",
        # FIXED 2026-08-22 (goal session: "Insufficient history"/revenue-gap audit): IFRS 7
        # requires ALL filers with financial instruments (not just banks with no other
        # revenue tag) to disclose interest revenue/expense, so a filer that already reports
        # a real "Revenue"/"RevenuesNetOfInterestExpense" figure could ALSO separately report
        # InterestRevenueExpense as a supplementary disclosure - without fallback-only status
        # sec_base.py's last-processed-wins copy loop would let it silently clobber a correct,
        # more complete revenue figure with the narrower gross-interest-income one (same risk
        # class as the cost_of_goods_and_services_sold/CAT incident above). See
        # sec_statements.py's comment on InterestRevenueExpense (live-verified via WF/Woori
        # Financial Group, which has zero data under any other revenue concept, for the case
        # this genuinely does need to fill).
        "interest_revenue_expense",
        # WIDENED 2026-08-31: both also added to sec_base.py's _REVENUE_TOTAL_CANDIDATE_
        # FIELDS (magnitude-resolved group, checked BEFORE this fallback-only set - see
        # that set's own comment for the ANDE/PRGO/TKR cases that motivated it), same dual-
        # membership precedent as interest_revenue_expense above. Their fallback-only
        # membership here is now vestigial for filers that reach that check at all (the
        # magnitude branch always continues first) but kept rather than removed - harmless,
        # and this set is still the operative one for any other field that might someday
        # legitimately need pure fallback-only (never-overwrite-if-populated) semantics
        # without the magnitude comparison.
        "sales_revenue_net",
        "sales_revenue_goods_net",
        # FIXED 2026-08-17 (goal: "no SEC data" audit continuation): "cost_of_goods_and_
        # services_sold" (added e1a3ae3b9 as a plain, always-overwrite mapping so retail/
        # product filers that never tag CostOfRevenue/CostOfSales at all - AMZN et al -
        # get a real cost_of_revenue) was NOT fallback-only, so on filers that tag BOTH
        # concepts for unrelated line items it silently clobbered a correct value with a
        # wrong one via sec_base.py's last-processed-wins copy loop. Live-confirmed via
        # real SEC EDGAR companyfacts for CAT: CostOfRevenue FY2025=$44.75B (real,
        # consolidated, ~65% of $67.6B revenue) vs. CostOfGoodsAndServicesSold FY2025=$49M
        # (some unrelated minor line item) - annual_income_statement.cost_of_revenue was
        # $49M, wrong by ~900x, with no data_unavailable/reason flag anywhere. A DB-wide
        # ratio scan (revenue > $1B, cost_of_revenue/revenue < 2%) found 32 symbols with
        # this same implausible-magnitude signature (CAT, CNC, VICI, JEF, ARCO, ...) - not
        # proof for every one without a per-symbol EDGAR check the way CAT was, but the
        # same pattern. Reusing this frozenset (not just "revenue" fields despite the
        # name - it's really "sec_field keys that only fill an already-empty db_field")
        # since it's already wired into every income-statement cfg below; this key now
        # only fills cost_of_revenue when CostOfRevenue/CostOfSales didn't already set it,
        # same as this set's existing entries, so AMZN-style filers are unaffected.
        "cost_of_goods_and_services_sold",
        # FIXED 2026-08-31: see sec_statements.py's comment on these two concepts (LIN
        # live-verified) - same "fills only an already-empty db_field" reasoning as
        # cost_of_goods_and_services_sold just above, since excluding D&A makes this a
        # narrower figure than a full COGS-including-D&A tag when both are reported.
        "cost_of_goods_and_service_excluding_depreciation_depletion_and_amortization",
        "cost_of_goods_sold_excluding_depreciation_depletion_and_amortization",
        "cost_of_goods_sold",
        # FIXED 2026-08-31: same "fills only an already-empty db_field" reasoning - see
        # sec_statements.py's comments on these two concepts (LYV/AWK/WTRG/MSEX/YORW live-
        # verified) and _INCOME_FIELD_MAPPING's comment on them above.
        "direct_operating_costs",
        "utilities_operating_expense_maintenance_and_operations",
        # FIXED 2026-08-18 (goal: "no SEC data"/loader audit): see sec_statements.py's
        # get_income_statement() comment for the live evidence (TXN/BA/NEE). Reusing this
        # same "fills only an already-empty db_field" set for the same overwrite-safety
        # reason as cost_of_goods_and_services_sold above - live-confirmed TRV reports
        # BOTH a real "InterestExpense" ($425M FY2025) AND "InterestPaidNet" ($393M
        # FY2025, a different, less precise cash-paid figure) for the same fiscal year, so
        # a plain always-overwrite mapping for interest_paid_net would have silently
        # downgraded TRV's real interest_expense on every filer that reports both (a very
        # common combination - "cash paid for interest" is a near-universal ASC 230
        # supplemental cash-flow disclosure). interest_and_debt_expense made fallback-only
        # too for the same reason, even though no live overwrite case was found for it
        # specifically - not exhaustively checked across the universe, so defaulting to
        # the safe convention this file uses everywhere else.
        "interest_and_debt_expense",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): same
        # "fills only an already-empty db_field" reasoning - see
        # _INCOME_FIELD_MAPPING's comment on "financing_interest_expense" above (EPAC
        # live-verified). Listed after interest_and_debt_expense in sec_statements.py's
        # concept list, so a filer with a rare real interest_and_debt_expense value keeps
        # it.
        "financing_interest_expense",
        "interest_paid_net",
        # FIXED 2026-09-03 (same reasoning as interest_paid_net just above - see
        # _INCOME_FIELD_MAPPING's comment on "interest_paid" above, ARW live-verified).
        "interest_paid",
        # FIX 2026-09-02 (goal: "SEC/XBRL missing data" audit): same "fills only an
        # already-empty db_field" reasoning as this set's other entries - see
        # _INCOME_FIELD_MAPPING's comment on "custom_extension_revenue" above. Only ever
        # populated for CUSTOM_REVENUE_CONCEPTS-registered symbols in the first place, so
        # this is a defensive-in-depth guard rather than a live-confirmed clobber risk.
        "custom_extension_revenue",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, pe_ratio/
        # peg_ratio investigation): same "fills only an already-empty db_field" reasoning as
        # custom_extension_revenue above - see _INCOME_FIELD_MAPPING's comment on these keys.
        # Only ever populated for CUSTOM_INCOME_DIMENSIONED_CONCEPTS-registered symbols.
        "custom_extension_net_income",
        "custom_extension_eps_basic",
        "custom_extension_eps_diluted",
        # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data" sweep): ESOA-class filers
        # that stop tagging NetIncomeLoss/ProfitLoss - see _INCOME_FIELD_MAPPING's comment on
        # this key above.
        "income_loss_from_continuing_operations_including_portion_attributable_to_noncontrolling_interest",
    }
)

# FIXED 2026-08-09: REIT-specific fallback (SIC 6798 only, see sec_base.py's
# _reit_only_fallback_fields comment). Equity REITs' real revenue ("revenues", mostly
# lease income) is explicitly out of ASC 606's scope, so their ASC-606 contract-revenue
# tags only ever capture a much smaller non-lease fee-income line - unlike the general
# case (most post-2018 filers), where the ASC-606 tag legitimately supersedes "revenues"
# as the fuller, more current figure. Live-confirmed UDR: revenues=$1.67B (real) vs.
# revenue_from_contract_with_customer_excluding_assessed_tax=$8.3M (real but minor fee
# income) - the general priority chain let the $8.3M win.

_REIT_REVENUE_FALLBACK_ONLY_FIELDS = frozenset(
    {
        "revenue_from_contract_with_customer_including_assessed_tax",
        "revenue_from_contract_with_customer_excluding_assessed_tax",
    }
)

# BUG FOUND 2026-08-19 (goal: "no SEC data"/loader audit): "operating_lease_lease_income"
# used to live in _REIT_REVENUE_FALLBACK_ONLY_FIELDS above, but that set's "unaffected for
# non-REIT filers" semantics is only correct for the two ASC-606 concepts (which SHOULD
# also win normally for non-REIT filers via the general priority chain - see
# test_sec_reit_lease_revenue_not_overwritten.py's AAPL case). OperatingLeaseLeaseIncome is
# different: for a non-REIT filer it's an unrelated, minor line item (real-estate sublease
# income), never a revenue analog, and must never touch "revenue" regardless of processing
# order. Live-confirmed via IHRT (iHeartMedia, SIC 7812, not a REIT): its real annual
# "Revenues" ($3.75B/$3.85B/$3.86B for FY2023-2025) was silently clobbered by its tiny
# sublease income under this concept ($2.01M/$787K/$562K - exact match to the corrupted DB
# values), a ~1000x understatement with no data_unavailable/reason flag anywhere. Wired via
# sec_base.py's new, stricter "reit_exclusive_fields" - skip (never write) for any symbol
# that isn't a confirmed REIT, fallback-only (skip if already populated) for symbols that
# are.

_REIT_EXCLUSIVE_FIELDS = frozenset(
    {
        "operating_lease_lease_income",
        "real_estate_revenue_net",
    }
)

# FIXED 2026-08-17 (loader-review goal continuation): see sec_statements.py's
# get_balance_sheet() comment - these 3 concepts are alternate ways small/micro-cap
# filers tag real long-term debt when they never use the standard "LongTermDebt" concept
# at all (live-confirmed real instant-fact debt for MRKR/MODD/ATNM under these tags,
# part of a live DB scan finding 2,306 symbols with real balance sheet rows but zero
# long_term_debt ever). Fallback-only (not a plain mapping) so a filer that DOES report
# the standard LongTermDebt concept always keeps that value - see sec_base.py's copy
# loop: a non-fallback field always overwrites unconditionally regardless of processing
# order, so "long_term_debt" (from the real LongTermDebt concept) wins over any of these
# 3 whenever both are present for the same fiscal year; these only fill genuinely empty
# years.

# Migration 1256 ("implausible values" sweep, quarterly fiscal-year-ordering bug): only
# quarterly_income_statement has a period_end column (see that migration's own header for
# why fiscal_year/fiscal_quarter alone can't reliably sort into true chronological order for
# non-December-fiscal-year-end filers) - kept separate from _QUARTERLY_EXTRA (shared by
# cashflow/balance sheet quarterly configs too) so this doesn't map a field into a column
# those two tables don't have.
_QUARTERLY_INCOME_EXTRA = {**_QUARTERLY_EXTRA, "period_end": "period_end"}


def get_income_statement_config(period: str) -> dict[str, Any]:
    """Income statement configuration for annual/quarterly/ttm."""
    if period == "annual":
        return {
            "table_name": "annual_income_statement",
            "field_mapping": dict(_INCOME_FIELD_MAPPING),
            "fallback_only_fields": _REVENUE_FALLBACK_ONLY_FIELDS,
            "reit_only_fallback_fields": _REIT_REVENUE_FALLBACK_ONLY_FIELDS,
            "reit_exclusive_fields": _REIT_EXCLUSIVE_FIELDS,
            "primary_key": ("symbol", "fiscal_year"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "fiscal_year",
                    "revenue",
                    "cost_of_revenue",
                    "gross_profit",
                    "operating_income",
                    "operating_expenses",
                    "goodwill_impairment_loss",
                    "net_income",
                    "net_income_attributable_to_common",
                    "earnings_per_share",
                    "diluted_eps",
                    "interest_expense",
                    "depreciation_expense",
                    "amortization_expense",
                    "research_development_expense",
                    "shares_outstanding_basic",
                    "shares_outstanding_diluted",
                    "shares_outstanding_dei",
                    "income_tax_expense",
                    "pretax_income",
                    "created_at",
                    "data_unavailable",
                    "reason",
                    "data_source",
                ]
            ),
        }
    elif period == "quarterly":
        return {
            "table_name": "quarterly_income_statement",
            "field_mapping": {**_INCOME_FIELD_MAPPING, **_QUARTERLY_INCOME_EXTRA},
            "fallback_only_fields": _REVENUE_FALLBACK_ONLY_FIELDS,
            "reit_only_fallback_fields": _REIT_REVENUE_FALLBACK_ONLY_FIELDS,
            "reit_exclusive_fields": _REIT_EXCLUSIVE_FIELDS,
            "primary_key": ("symbol", "fiscal_year", "fiscal_quarter"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "fiscal_year",
                    "fiscal_quarter",
                    "revenue",
                    "cost_of_revenue",
                    "gross_profit",
                    "operating_income",
                    "operating_expenses",
                    "goodwill_impairment_loss",
                    "net_income",
                    "net_income_attributable_to_common",
                    "earnings_per_share",
                    "diluted_eps",
                    "interest_expense",
                    "depreciation_expense",
                    "amortization_expense",
                    "research_development_expense",
                    "shares_outstanding_basic",
                    "shares_outstanding_diluted",
                    "shares_outstanding_dei",
                    "income_tax_expense",
                    "pretax_income",
                    "period_end",
                    "created_at",
                    "data_unavailable",
                    "reason",
                    "data_source",
                ]
            ),
        }
    elif period == "ttm":
        return {
            "table_name": "ttm_income_statement",
            "field_mapping": dict(_INCOME_FIELD_MAPPING),
            "fallback_only_fields": _REVENUE_FALLBACK_ONLY_FIELDS,
            "reit_only_fallback_fields": _REIT_REVENUE_FALLBACK_ONLY_FIELDS,
            "reit_exclusive_fields": _REIT_EXCLUSIVE_FIELDS,
            "primary_key": ("symbol", "report_date"),
            "schema_cols": frozenset(
                [
                    "symbol",
                    "report_date",
                    "revenue",
                    "cost_of_revenue",
                    "gross_profit",
                    "operating_income",
                    "net_income",
                    "earnings_per_share",
                    "created_at",
                    "data_unavailable",
                    "reason",
                ]
            ),
        }
    else:
        raise ValueError(f"Unknown period: {period}")
