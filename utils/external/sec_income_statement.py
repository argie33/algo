"""Income-statement extraction for utils/external/sec_statements.py, extracted from that file
(2026-09-05, file-size ratchet: it's a Tier-2 bloater flagged for decomposition). Body is
verbatim, no logic changed - only moved file. get_income_statement() aggregates key income-
statement concepts via sec_statements_aggregate.py's _aggregate_concepts, then applies several
fallback post-processing passes (now in sec_income_statement_fallbacks.py - this file itself
exceeded the 800-line new-file cap once first split out of sec_statements.py, needing a
further split) that _aggregate_concepts' one-column "last value wins" merge can't express
(continuing/discontinued EPS split, dual-class dimensional EPS/shares, income tax
current+deferred split, validated pretax-income promotion, and derived operating income).
"""

from typing import Any

from utils.external.sec_income_statement_fallbacks import (
    _detect_misextracted_cogs_from_gross_profit_mismatch,
    _fill_earnings_per_share_from_continuing_discontinued_split,
    _fill_eps_shares_from_dual_class_dimensional_facts,
    _fill_income_tax_expense_from_current_deferred_split,
    _fill_operating_income_from_revenue_minus_costs_and_expenses,
    _fill_pretax_income_from_domestic_foreign_split,
    _fill_pretax_income_from_results_of_operations_when_validated,
)
from utils.external.sec_statements_aggregate import _aggregate_concepts

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
        # FIXED 2026-08-31 (same sweep): live-events/venue-based filers tag their pass-through
        # artist/venue/ticketing costs under this concept instead of any concept above - live-
        # confirmed Live Nation Entertainment (LYV, $23B market cap): zero data under every
        # concept above for any recent fiscal year, but real, current, plausible
        # DirectOperatingCosts on file every year through FY2025 (FY2023 $17.29B/$22.75B
        # revenue ~76%, FY2024 $17.33B/$23.16B ~75% - consistent with Live Nation's well-known
        # low-margin, pass-through-heavy concert-promotion economics). gross_profitability/
        # gross_margin had been silently NULL (mislabeled "reit_special_entity", this
        # codebase's generic "no cost concept found" label - see
        # load_value_quality_growth_metrics.py) despite decades of otherwise-complete real SEC
        # data on file. Same target column, fallback-only (see _REVENUE_FALLBACK_ONLY_FIELDS)
        # since this is a narrower, business-model-specific cost measure rather than a
        # universal COGS tag.
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
        # REMOVED 2026-07-28, RE-ADDED 2026-09-05: "CostsAndExpenses"/"OperatingExpenses" used
        # to be fetched here as would-be operating_income fallbacks, but neither had a
        # field_mapping entry or destination column, and live-checking real filers missing
        # operating_income at the time (SWK, KMX, BXP) found zero cases where either concept
        # was present and OperatingIncomeLoss wasn't - so it was removed as pure wasted SEC
        # API payload. Re-added 2026-09-05 (goal session: "SEC/XBRL missing data" sweep,
        # operating_income_not_itemized investigation) after live-confirming a DIFFERENT,
        # real population this time: RRC (Range Resources, CIK 0000315852) and ARDT (CIK
        # 0001756655) both report a real "Revenues" total and a real "CostsAndExpenses"
        # total every fiscal year but tag NO OperatingIncomeLoss concept at all anywhere in
        # their companyfacts JSON (single-step income statement format) - RRC FY2025
        # Revenues=$3,115,515,000/CostsAndExpenses=$2,283,825,000, ARDT FY2025
        # Revenues=$6,324,339,000/CostsAndExpenses=$6,037,981,000, both yielding a plausible
        # operating margin once subtracted. "OperatingExpenses" (the sibling concept) is
        # deliberately NOT re-added - not re-verified against this new evidence, no known
        # real filer needing it. See _fill_operating_income_from_revenue_minus_costs_and_
        # expenses() below for the derivation - fallback-only, only fires when
        # OperatingIncomeLoss is absent for that fiscal year.
        "CostsAndExpenses",
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
        # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data" sweep, net_income_not_reported/
        # eps_scale_mismatch investigation): ESOA (Energy Services of America, CIK 0001357971)
        # stopped tagging both "NetIncomeLoss" and "ProfitLoss" after FY2022 - live-confirmed via
        # real SEC companyfacts JSON, its real FY2025 bottom line ($379,708, FY ending
        # 2025-09-30) is tagged solely under this concept instead. Fallback-only (see
        # _REVENUE_FALLBACK_ONLY_FIELDS in load_financial_statements.py, which despite its name
        # is a generic "only fill when target column still empty" set, not revenue-specific) so
        # a filer reporting the standard NetIncomeLoss/ProfitLoss concepts always keeps that
        # value - only fills the gap for a filer like ESOA that stops tagging either. Maps to
        # the same "net_income" column via _INCOME_FIELD_MAPPING's matching key.
        "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
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
        # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" - real extraction bug found):
        # CHKP (Check Point, $1.97B debt FY2025) and ~350 symbols have interest_expense=NULL
        # despite having real debt, because they report interest under non-standard concepts.
        # Live-confirmed CHKP has operating_income=$831M + pretax_income=$945M but interest_expense
        # is NULL across all 5 fiscal years - the ~$114M gap is a real extraction miss, not
        # a data absence. Added these additional fallback concepts to catch alternative
        # reporting patterns (software/tech companies, alternative accounting methods).
        "OtherInterestExpense",
        "InterestExpenseOther",
        "OperatingFinanceCosts",
        "DebtServiceExpense",
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
        # "...BeforeIncomeTaxesDomestic" instead. Live-verified for CNX FY2023: this concept's
        # value ($2,222,925,000) exactly equals net_income ($1,720,716,000) + income_tax_expense
        # ($502,209,000) already in our DB for that year - confirming it IS the real total
        # pretax income for this filer, not a partial figure.
        #
        # CORRECTED 2026-09-06 (tie-out-checker follow-up, ORCL/MCD/PYPL/PSX live-confirmed):
        # this concept is NO LONGER mapped directly to "pretax_income" via field_mapping (it
        # used to be, on the assumption below that a fuller concept - if the filer has one -
        # would always win the overwrite). That assumption was live-disproven: ORCL/MCD/PYPL/
        # PSX all tag a real Domestic AND Foreign split but have NO populated combined-concept
        # entry for the years checked, so "Domestic" alone silently won the DB column,
        # understating true pretax income by the entire foreign-sourced share (ORCL FY2025:
        # stored $4.376B vs. real $14.160B - barely 31% of the true total). Domestic is now
        # consumed only by _fill_pretax_income_from_domestic_foreign_split below (in
        # sec_income_statement_fallbacks.py), which sums it with the new Foreign concept just
        # above and validates the total against net_income+income_tax_expense before trusting
        # it - CNX's domestic-only case (no real Foreign concept at all) still validates
        # correctly via that same function, so this fix is additive, not a regression for it.
        # (A sibling concept, "ResultsOfOperationsIncomeBeforeIncomeTaxes", was
        # checked and rejected - CNX FY2023 value $2,317,918,000 does NOT match, it's the
        # ASC 932 oil-and-gas-producing-activities supplementary disclosure, not consolidated
        # pretax income - do not add it here.)
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
        # ADDED 2026-09-06 (tie-out-checker follow-up, ORCL/MCD/PYPL/PSX live-confirmed - see
        # _fill_pretax_income_from_domestic_foreign_split's docstring in
        # sec_income_statement_fallbacks.py for the full evidence): "Domestic" above is only
        # ONE half of ASC 740-10-50-11's required domestic/foreign pretax-income split for a
        # genuinely multinational filer - this concept is the other half, never fetched before
        # this fix. Kept OUT of field_mapping deliberately (unlike Domestic historically was) -
        # _fill_pretax_income_from_domestic_foreign_split below consumes both raw keys directly
        # and validates their sum against net_income+income_tax_expense before ever writing
        # "pretax_income", rather than letting either half reach the DB unvalidated on its own.
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign",
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
    _detect_misextracted_cogs_from_gross_profit_mismatch(rows)
    _fill_earnings_per_share_from_continuing_discontinued_split(rows)
    _fill_income_tax_expense_from_current_deferred_split(rows)
    _fill_pretax_income_from_domestic_foreign_split(rows)
    _fill_pretax_income_from_results_of_operations_when_validated(rows)
    _fill_operating_income_from_revenue_minus_costs_and_expenses(rows)
    if period == "annual":
        _fill_eps_shares_from_dual_class_dimensional_facts(rows, client, symbol, security_name)
    return rows
