"""Balance-sheet extraction for utils/external/sec_statements.py, extracted from that file
(2026-09-05, file-size ratchet: it's a Tier-2 bloater flagged for decomposition). Bodies are
verbatim, no logic changed - only moved file. get_balance_sheet() aggregates key balance-sheet
concepts via sec_statements_aggregate.py's _aggregate_concepts, then applies two fallback
post-processing passes for long-term debt that _aggregate_concepts' one-column "last value
wins" merge can't express.
"""

import logging
from typing import Any

from utils.external.sec_statements_aggregate import _aggregate_concepts

logger = logging.getLogger(__name__)

# ADDED 2026-09-10 (goal: "Missing SEC/XBRL data" under-500 push, ANDG live-confirmed): every
# concept below is a real, mutually-exclusive-in-practice equivalent of "stockholders_equity"
# (see this file's own comments on each below, and load_financial_statements.py's
# _BALANCE_FIELD_MAPPING, which is where they all actually collapse onto that one DB column -
# _aggregate_concepts itself has no visibility into that mapping, hence this local group).
# Passed as `alias_groups` to _aggregate_concepts so its has_annual_report_form/
# _max_annual_report_end "don't accept a premature 10-Q snapshot once a real 10-K exists"
# guard (see that function's own GM/DIS/WEC comments) sees ALL of a filer's equity-family
# concepts together, not just whichever single one it's currently resolving. Without this, a
# filer that tags one equity concept in its 10-K but a DIFFERENT one (still same DB column) in
# a later 10-Q defeats the guard entirely for that 10-Q concept - live-confirmed via ANDG:
# FY2025 10-K tags bare "StockholdersEquity", but its FY2026 Q2 10-Q instead tags
# "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest" - which, having no
# 10-K history of its OWN, sailed straight into the FY2026 bucket as if it were fiscal-year-end
# data while sibling concepts (Assets/LongTermDebt, same concept name in both filings) were
# correctly withheld by the same guard - an inconsistent partial row instead of a clean
# "not yet confirmed" state.
_EQUITY_ALIAS_GROUPS = {
    "stockholders_equity": "stockholders_equity_group",
    "stockholders_equity_including_portion_attributable_to_noncontrolling_interest": "stockholders_equity_group",
    "partners_capital": "stockholders_equity_group",
    "partners_capital_including_portion_attributable_to_noncontrolling_interest": "stockholders_equity_group",
    "members_equity": "stockholders_equity_group",
    "limited_liability_company_llc_members_equity_including_portion_attributable_to_noncontrolling_interest": (
        "stockholders_equity_group"
    ),
}

_BALANCE_IFRS_ALIASES = [
    # (IFRS concept name, target key = _to_snake() of the equivalent GAAP concept)
    ("Assets", "assets"),
    ("CurrentAssets", "assets_current"),
    # FIXED 2026-09-07 (tie-out check_current_assets_le_total_assets, SSL/Sasol live-
    # confirmed): a filer that reclassifies part of its balance sheet under IFRS 5
    # ("non-current assets/disposal groups held for sale") splits the plain "CurrentAssets"
    # concept above into two: this concept (current assets EXCLUDING the held-for-sale
    # reclassification) plus "NoncurrentAssetsOrDisposalGroupsClassifiedAsHeldForSale"
    # (assets originally non-current but presented WITHIN current assets per IFRS 5 -
    # "Noncurrent" in the name refers to their original classification, not their balance-
    # sheet presentation). Live-confirmed via SSL's real companyfacts JSON (CIK 0000314590):
    # plain ifrs-full:CurrentAssets has ZERO facts after FY2020 (last: 2020-06-30) - Sasol
    # switched to this split style from FY2021 onward - so the bare alias above has silently
    # returned nothing for 5 straight fiscal years while SSL's DB rows for FY2022-2025 sat on
    # a STALE raw-ZAR (unconverted) current_assets value from some earlier extraction,
    # preserved indefinitely by preserve_on_missing_fields' COALESCE. FY2025:
    # CurrentAssetsOtherThan...=ZAR 130,101,000,000 + NoncurrentAssetsOrDisposalGroups...=
    # ZAR 53,000,000 = ZAR 130,154,000,000, exactly matching the stale unconverted DB value -
    # confirming this concept pairing IS the real "current assets" figure, just never
    # FX-converted because nothing was fetching it. Listed AFTER the bare "CurrentAssets"
    # alias, deliberately - NOT this file's usual "fallback listed first" convention.
    # Live-verified via _aggregate_concepts_should_replace_entry's actual instant-fact
    # tiebreak (utils/external/sec_statements_entry_resolution.py): when two DIFFERENT
    # concepts for the same column collide on an identical (end_date, filed_date) - which
    # genuinely happens for SSL's own FY2020, where BOTH "CurrentAssets" ($177,969,000,000)
    # and this concept ($93,701,000,000) are tagged in the same 20-F - the FIRST-listed
    # concept wins the tie (a strict `>` comparison, not `>=`), matching this file's own
    # "first-populated-wins" terminology already used for the SubordinatedDebt/
    # JuniorSubordinatedDebenture pair further below. SSL's real, currently-correct FY2020
    # DB row uses the bare CurrentAssets concept ($177.969B ZAR / 17.3625 2020-06-30 rate =
    # $10.25B, live-confirmed matching the DB) - listing the fallback second preserves that
    # already-correct year; only fiscal years where the bare concept has NO fact at all
    # (FY2021+ for SSL) ever reach this fallback. Not summed with the held-for-sale
    # component (this loader's transform() has no summing mechanism for two concepts mapped
    # to the same column - see the DebtCurrent/SecuredDebt comment below) - capturing the
    # larger, near-total figure alone is strictly better than the prior stale/wrong value,
    # same accepted-partial-figure precedent as elsewhere in this file.
    (
        "CurrentAssetsOtherThanAssetsOrDisposalGroupsClassifiedAsHeldForSaleOrAsHeldForDistributionToOwners",
        "assets_current",
    ),
    # ADDED 2026-09-09 (goal session: XBRL coverage-scan gap triage, 101 undismissed filers):
    # the held-for-sale component itself, for the rare filer that tags ONLY this concept for
    # a given fiscal year (neither bare "CurrentAssets" nor the "OtherThan..." concept above
    # has a fact) - live-confirmed via the real companyfacts cache that this genuinely happens
    # for some filer/year combinations, not just as a sibling of the other two. Deliberately
    # listed LAST (after both other current-assets concepts) so first-populated-wins (see
    # _aggregate_concepts_should_replace_entry in sec_statements_entry_resolution.py) means it
    # only ever fills a column that's otherwise completely empty for that period - it can
    # never partially overwrite/double-count against the "OtherThan..." figure when a filer
    # tags both (the common case, confirmed via cross-referencing the cache: many filers tag
    # identical values under both concepts for the same period, e.g. Korea Electric Power,
    # Brookfield, National Grid, GSK - summing those would double-count). NOT a substitute for
    # real summing (this loader's transform() still has no summing mechanism for two concepts
    # targeting the same column, same limitation noted above for the OtherThan... concept) -
    # for filers that tag both concepts as genuinely separate non-overlapping pieces (e.g. YPF
    # 2017: HeldForSale=$8.823B vs OtherThan=$43M, a ~99.5%/0.5% split, clearly not duplicate
    # values), the OtherThan concept alone (already fetched, listed first) still undercounts -
    # that residual gap is real and NOT closed by this entry; it would need an actual summing
    # feature, out of scope here.
    ("NoncurrentAssetsOrDisposalGroupsClassifiedAsHeldForSale", "assets_current"),
    ("Liabilities", "liabilities"),
    ("CurrentLiabilities", "liabilities_current"),
    # FIXED 2026-09-07 (same SSL fix): paired liabilities-side concept for the same IFRS 5
    # split - SSL's plain ifrs-full:CurrentLiabilities also has zero facts after FY2020.
    # FY2025 CurrentLiabilitiesOtherThan...=ZAR 69,436,000,000 exactly matches the stale
    # unconverted DB current_liabilities value (SSL had no held-for-sale liabilities that
    # year, so no summing gap here). Listed AFTER the bare concept for the same first-
    # populated-wins reasoning as the assets-side fallback above.
    ("CurrentLiabilitiesOtherThanLiabilitiesIncludedInDisposalGroupsClassifiedAsHeldForSale", "liabilities_current"),
    # ADDED 2026-09-08 (goal session: XBRL coverage-scan backlog triage, 403 undismissed
    # filers - the single highest-count undismissed concept after the IFRS namespace fix
    # earlier this session): IFRS's combined trade-plus-other current-payables concept, the
    # closest IFRS analog to us-gaap "AccountsPayableCurrent" - live-confirmed via Agnico
    # Eagle's real companyfacts JSON (CIK 0000002809, an ifrs-full-only filer with no
    # us-gaap accounts_payable-shaped concept tagged at all): FY2025 (period end
    # 2025-12-31) TradeAndOtherCurrentPayables=USD 1,033,444,000, a sane ~42% of that same
    # period's CurrentLiabilities (USD 2,472,206,000) - plausible for a mining major's real
    # trade-payables scale, not a placeholder or an implausible near-total figure. Target
    # key "accounts_payable_current" (not a new column) is deliberate - it's the
    # _to_snake() raw key the us-gaap "AccountsPayableCurrent" concept already produces,
    # which _BALANCE_FIELD_MAPPING already routes to the accounts_payable column (reused
    # here, not duplicated, same convention as this file's own "NoncontrollingInterests"/
    # "minority_interest" entry above). Deliberately did NOT alias the bare (no "Current")
    # "TradeAndOtherPayables"/"TradeAndOtherReceivables" sibling concepts elsewhere in the
    # ifrs-full taxonomy to this or the accounts-receivable target - live-checked via
    # PLDT's real companyfacts JSON (CIK 0000078150) that those bare concepts are NOT
    # equivalent to their Current-suffixed counterparts for the same fiscal year (e.g.
    # FY2022: bare TradeAndOtherPayables=PHP 1,745,000,000 vs.
    # TradeAndOtherCurrentPayables=PHP 105,187,000,000 - a ~60x difference, not the same
    # line item at all), so those stay unmapped rather than risk a wildly wrong figure.
    ("TradeAndOtherCurrentPayables", "accounts_payable_current"),
    ("Equity", "stockholders_equity"),
    ("EquityAttributableToOwnersOfParent", "stockholders_equity"),
    # ADDED 2026-09-08 (goal session: scores-reload due-diligence audit, IFRS coverage-scan
    # follow-up): IFRS's own noncontrolling-interest equity concept, direct equivalent of the
    # us-gaap "MinorityInterest" concept already mapped to the same target below via
    # _BALANCE_FIELD_MAPPING's "minority_interest": "noncontrolling_interest" entry (reused
    # here, not duplicated) - live-confirmed via Bank of Nova Scotia's real companyfacts JSON
    # (CIK 0000009631): FY2026 Q1 (period end 2026-01-31) NoncontrollingInterests=
    # CAD 1,434,000,000, and EquityAttributableToOwnersOfParent (CAD 87,588,000,000) +
    # NoncontrollingInterests exactly equals the filer's own total Equity fact
    # (CAD 89,022,000,000) - confirms this is the real, complete NCI figure, not a partial
    # component. Target key "minority_interest" (not "noncontrolling_interest" directly) is
    # deliberate - it's the _to_snake() raw key the us-gaap concept produces, which
    # _BALANCE_FIELD_MAPPING already routes to the noncontrolling_interest column.
    ("NoncontrollingInterests", "minority_interest"),
    ("CashAndCashEquivalents", "cash_and_cash_equivalents_at_carrying_value"),
    ("TradeAndOtherCurrentReceivables", "accounts_receivable_net_current"),
    # FIXED 2026-09-03 (same sweep): TSM (Taiwan Semiconductor) live-confirmed via real
    # companyfacts JSON - reports trade receivables under this concept instead of
    # "TradeAndOtherCurrentReceivables" above (USD 6.5746B FY2023 / 8.2551B FY2024,
    # continuous). Same target key as that concept - genuinely the narrower "trade
    # receivables only" IFRS taxonomy element (not a combined trade+other concept), close
    # enough in meaning to the us-gaap "AccountsReceivableNetCurrent" target it feeds.
    ("CurrentTradeReceivables", "accounts_receivable_net_current"),
    # ADDED 2026-09-08 (goal session: XBRL coverage-scan backlog triage, 227 undismissed
    # filers): "TradeReceivables" - live-confirmed via Himax Technologies' real companyfacts
    # JSON (CIK 0001342338, a fabless semiconductor 20-F filer with none of the concepts
    # above tagged at all): FY2024 (period end 2024-12-31) TradeReceivables=USD 89,527,000,
    # a sane ~7.7% of that year's CurrentAssets (USD 1,168,043,000) - previously invisible,
    # not a placeholder. Cross-checked against Agnico Eagle (which already has a working
    # "CurrentTradeReceivables" alias above): AEM's own TradeReceivables FY2025 value (USD
    # 18,690,000) is within 0.05% of its CurrentTradeReceivables value for the same period
    # (USD 18,700,000) - confirms this is genuinely the same "current trade receivables"
    # concept, not a broader/noncurrent-inclusive one (ruled out via PLDT's real
    # companyfacts JSON for the analogous bare-vs-Current "TradeAndOtherReceivables" pair
    # below, where the bare concept is ~50% LARGER than its Current-suffixed sibling - a
    # genuinely different, noncurrent-inclusive scope, correctly NOT aliased here). Same
    # target as CurrentTradeReceivables/TradeAndOtherCurrentReceivables above - listed
    # LAST in this same-target group so this aggregation's first-populated-wins tiebreak
    # (see the "Borrowings" comment further below for the live-verified mechanics) defers
    # to either of those more-established concepts for a filer reporting more than one in
    # the same fiscal year.
    ("TradeReceivables", "accounts_receivable_net_current"),
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
    # ADDED 2026-09-08 (goal session: XBRL coverage-scan exhaustive triage, "get data issues to
    # zero"): the SAME "LongtermBorrowings" concept, fetched a SECOND time under a different
    # target key purely so _fill_long_term_debt_from_noncurrent_current_split below can detect
    # "this filer's long_term_debt came from LongtermBorrowings specifically (not Borrowings)"
    # and add the current-maturities figure it was otherwise missing. Live-confirmed via Agnico
    # Eagle's real companyfacts JSON (CIK 0000002809): FY2024 LongtermBorrowings=
    # USD 1,052,956,000 is a DIFFERENT, smaller figure than that plus
    # CurrentPortionOfLongtermBorrowings=USD 90,000,000 - i.e. LongtermBorrowings alone is the
    # noncurrent-only portion, not the total, silently understating total debt by the current
    # maturities every time (the tuple above, mapping straight to "long_term_debt", has no way
    # to add a second concept's value on top of it). Deliberately did NOT simply retarget the
    # tuple above to "long_term_debt_noncurrent" instead of adding this duplicate: that would
    # let "Borrowings" (also a direct "long_term_debt" writer, listed further below) populate
    # first whenever both are present, silently dropping the more-precise LongtermBorrowings/
    # current-portion split - a real regression caught by
    # tests/unit/test_ifrs_borrowings_and_nci_aliases_20260908.py's existing
    # test_split_concepts_win_over_borrowings_fallback (asserts the split wins over Borrowings).
    # Keeping BOTH the direct mapping above (preserves that existing win-over-Borrowings
    # precedence) and this second fetch (only consumed by the equality check in
    # _fill_long_term_debt_from_noncurrent_current_split, never written directly) avoids the
    # regression while still fixing the current-maturities understatement.
    ("LongtermBorrowings", "long_term_debt_noncurrent"),
    # ADDED 2026-09-08 (same fix as immediately above): IFRS's current-maturities-of-long-term-
    # debt concept, the direct analog of us-gaap's "LongTermDebtCurrent" - 174 undismissed
    # filers. Same raw key ("long_term_debt_current") as that us-gaap concept so it's consumed
    # by the identical existing _fill_long_term_debt_from_noncurrent_current_split fallback,
    # fallback-only (never overwrites a real value; only fires when "long_term_debt" is still
    # unset after the direct-concept pass, e.g. no "Borrowings"/other combined total tagged).
    ("CurrentPortionOfLongtermBorrowings", "long_term_debt_current"),
    # ADDED 2026-09-08 (same triage batch): "CurrentBorrowingsAndCurrentPortionOfNoncurrent
    # Borrowings" - IFRS's COMBINED current-debt concept (short-term borrowings + current
    # maturities of long-term debt together), 158 undismissed filers. Live-confirmed via PLDT's
    # real companyfacts JSON (CIK 0000078150) FY2024: LongtermBorrowings (PHP 258,246,000,000)
    # + this concept (PHP 23,340,000,000) = PHP 281,586,000,000, an EXACT match to PLDT's own
    # separately-tagged combined "Borrowings" total for the same period - confirms this concept
    # is genuinely the correct current-side addend to sum with LongtermBorrowings, not a
    # narrower or broader figure. Mapped to the same "long_term_debt_current" raw key as
    # CurrentPortionOfLongtermBorrowings above; per this codebase's "first-populated-wins for
    # cross-concept collisions on the same raw key" rule (see
    # _aggregate_concepts_should_replace_entry's 2026-09-07 CVE fix comment), the
    # earlier-listed CurrentPortionOfLongtermBorrowings would win if a filer ever tagged both
    # for the same period - no filer checked (Agnico, PLDT) tags both, so this ordering is
    # low-risk/arbitrary rather than load-bearing.
    ("CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings", "long_term_debt_current"),
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
    # ADDED 2026-09-08 (goal session: scores-reload due-diligence audit, IFRS coverage-scan
    # follow-up): "Borrowings" is IFRS's single COMBINED debt concept for filers that don't
    # split current/noncurrent the way the LongtermBorrowings/ShorttermBorrowings pair above
    # assumes - live-confirmed via Unilever PLC's real companyfacts JSON (CIK 0000217410):
    # FY2025 (period end 2025-12-31) Borrowings=EUR 26,038,000,000, and Unilever tags NO
    # LongtermBorrowings/ShorttermBorrowings/CurrentBorrowings/NoncurrentBorrowings concept at
    # all - a real, ~EUR 26B debt load previously invisible to this extractor entirely for a
    # major global filer. Listed AFTER the split pair above (this aggregation's own
    # first-populated-wins tiebreak - live-verified via a real test that listing a fallback
    # BEFORE its more-precise sibling lets the fallback win when both are present for the same
    # period, the opposite of what's wanted - so unlike the "list fallback first" IFRS-alias
    # convention documented on the CurrentAssetsOtherThan... entry further up, a same-column
    # fallback here must be listed LAST for a filer reporting both to keep the split value).
    # Maps to the same long_term_debt raw key as "DebtLongtermAndShorttermCombinedAmount" (PGR,
    # us-gaap) uses for the identical no-current/noncurrent-split shape.
    #
    # CORRECTED 2026-09-08: the "listed after the split pair" reasoning above no longer
    # describes a same-raw-key race - LongtermBorrowings was retargeted (see its own comment
    # above) from "long_term_debt" to "long_term_debt_noncurrent", so this "Borrowings" entry
    # is now the ONLY concept in this list that writes "long_term_debt" directly during
    # aggregation. It still behaves as intended (a combined-total filer's real figure always
    # wins over the noncurrent+current fallback sum): the fallback in
    # _fill_long_term_debt_from_noncurrent_current_split only fires when "long_term_debt" is
    # still None post-aggregation, so a populated Borrowings value is never overwritten.
    ("Borrowings", "long_term_debt"),
    # ADDED 2026-09-09 (goal session: SEC/XBRL missing-data count under 700,
    # total_debt_not_itemized investigation): bank/financial-institution IFRS filers commonly
    # fund via debt securities issuance rather than generic "Borrowings" - live-confirmed via
    # KSPI (Kazakhstan bank)'s real companyfacts JSON tagging "DebtSecurities" (debt securities
    # issued, a real bank funding-side liability) while never tagging LongtermBorrowings/
    # ShorttermBorrowings/Borrowings at all. Listed LAST (after Borrowings) so any filer
    # reporting the more specific concepts above always keeps that value - same
    # last-listed-wins fallback convention as the "Borrowings" entry itself.
    ("DebtSecurities", "long_term_debt"),
    # ADDED 2026-09-09 (goal session: SEC/XBRL missing-data reduction, total_debt_not_itemized
    # investigation continuation): BMA (Banco Macro, an Argentine bank ADR filing 20-F) tags
    # NEITHER "Borrowings" NOR "DebtSecurities" NOR any LongtermBorrowings/ShorttermBorrowings
    # concept above - live-confirmed via its real companyfacts JSON (CIK 0001347426) that its
    # only debt-instrument-shaped liability concept is "SubordinatedLiabilities": continuous,
    # material, real values every fiscal year 2018-2024 (e.g. FY2024 period end 2024-12-31 =
    # ARS 417,675,451,000, ~4% of that year's total Liabilities of ARS 10,441,712,229,000 - a
    # plausible subordinated-notes tranche scale for a bank, not a placeholder or near-total
    # figure). BMA's broader "FinancialLiabilities"/"FinancialLiabilitiesAtAmortisedCost"
    # concepts were deliberately NOT aliased here instead - live-confirmed those include
    # customer deposits (BMA's real primary funding source as a bank), so mapping either to
    # long_term_debt would grossly overstate real debt, not just fill a gap. Listed LAST (after
    # DebtSecurities) so any filer reporting the more common concepts above always keeps that
    # value - same last-listed-wins fallback convention as DebtSecurities/Borrowings
    # themselves. Same semantic class as the existing us-gaap "SubordinatedDebt"/
    # "JuniorSubordinatedDebentureOwedToUnconsolidatedSubsidiaryTrust" fallback further below
    # (IBOC/HBT trust-preferred securities) - this is IFRS's equivalent concept name for the
    # same real instrument type.
    ("SubordinatedLiabilities", "long_term_debt"),
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
    # ADDED 2026-09-08 (goal session: XBRL coverage-scan backlog triage, 3rd batch this
    # session - CurrentLeaseLiabilities/NoncurrentLeaseLiabilities, 438/426 undismissed
    # filers, the single highest-count pair left in the backlog): NOT plain aliases to
    # "operating_lease_liability" - a filer reporting BOTH the combined "LeaseLiabilities"
    # concept above AND this split pair for the same fiscal year (live-confirmed via Agnico
    # Eagle's real companyfacts JSON, CIK 0000002809: FY2025 LeaseLiabilities=
    # USD 125,199,000 == CurrentLeaseLiabilities USD 30,480,000 +
    # NoncurrentLeaseLiabilities USD 94,719,000, exact match, same identity holds FY2023-2024
    # too) would have this plain-alias pair silently racing the combined concept for the same
    # target column on ordinary last-listed-wins semantics - harmless when they agree (as for
    # AEM), but not verified to always agree for every filer, and unnecessary risk when a
    # dedicated fallback-only mechanism (matching this file's own
    # _fill_long_term_debt_from_noncurrent_current_split precedent below) can express "only
    # sum the split when the combined concept found nothing" exactly. A real, non-trivial gap
    # exists for filers that tag ONLY the split pair, never the combined concept: a scan of
    # this session's full on-disk companyfacts cache found 38 such filers (POSCO Holdings,
    # LATAM Airlines, Fresenius Medical Care AG, Franco-Nevada, MakeMyTrip among them) -
    # live-confirmed via POSCO Holdings' real companyfacts JSON (CIK 0000889132): FY2024
    # (period end 2024-12-31) CurrentLeaseLiabilities=KRW 161,601,000,000 +
    # NoncurrentLeaseLiabilities=KRW 744,500,000,000, with zero "LeaseLiabilities" fact for
    # any fiscal year - a real, material combined lease liability (~KRW 906B) previously
    # invisible to this extractor entirely. Raw keys deliberately reuse this file's own
    # "current_lease_liabilities"/"noncurrent_lease_liabilities" _to_snake() output (not a
    # new naming scheme) - see _fill_operating_lease_liability_from_current_noncurrent_split
    # below for the summing logic.
    ("CurrentLeaseLiabilities", "current_lease_liabilities"),
    ("NoncurrentLeaseLiabilities", "noncurrent_lease_liabilities"),
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
        # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep, same session
        # this file's own balance_sheet_identity check flagged 887 symbol/years - ARXS,
        # ironically the very symbol this file's MembersEquity comment below cites as its
        # original evidence, was one of them): the "IncludingPortionAttributableTo
        # NoncontrollingInterest" fallback pattern already applied to StockholdersEquity/
        # PartnersCapital two entries below was never mirrored for MembersEquity - live-
        # confirmed via ARXS's own real companyfacts JSON (CIK 0002093536): its most recent
        # 10-Q (filed 2026-07-30, period end 2026-06-30) tags plain MembersEquity=$0 while
        # LimitedLiabilityCompanyLlcMembersEquityIncludingPortionAttributableToNoncontrolling
        # Interest=$4,467,558,000 for the SAME period - exactly matching Assets($7,006,652,000)
        # - Liabilities($2,539,094,000). Fallback-only (listed before "MembersEquity", same
        # last-listed-wins convention as StockholdersEquityIncludingPortionAttributableTo
        # NoncontrollingInterest above): fills only an LLC filer with zero real MembersEquity
        # facts for any period at all, never overwrites a present MembersEquity value - so
        # this does NOT by itself resolve ARXS's specific $0-vs-$4.47B period (that $0 is a
        # present, non-null fact under the winning concept name, ambiguous between a genuine
        # Up-C-style near-zero-parent-equity structure - see this file's own
        # balance_sheet_identity docstring on PROK/ATTO/FAC/LTGO/SCTX for that already-accepted
        # pattern - and an isolated filer tagging error; not enough evidence from one symbol to
        # override the general "parent-only figure wins when both present" precedent). Closes
        # the same class of gap ADM/AAON already got for StockholdersEquity for any OTHER LLC
        # filer that never tags plain MembersEquity at all.
        "LimitedLiabilityCompanyLlcMembersEquityIncludingPortionAttributableToNoncontrollingInterest",
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
        # FIXED 2026-09-07 (goal session: XBRL concept-coverage backlog sweep): the SAME
        # "noncurrent-alone understates real debt" gap the LongTermDebtCurrent fix above
        # already closed for the plain LongTermDebtNoncurrent concept, but for THIS
        # concept's own current-portion sibling instead. Live-confirmed via real SEC
        # companyfacts JSON: for filers that tag "LongTermDebtAndCapitalLeaseObligations"
        # (fetched above, fallback-only into long_term_debt as if it were the total) AND
        # this concept for the same fiscal year, with no plain LongTermDebt/
        # LongTermDebtNoncurrent/"...IncludingCurrentMaturities" fact present that year -
        # 258 distinct filers, 1,263 filer-years, including Adobe, AT&T, AbbVie, Best Buy,
        # Amphenol, and American Water Works - "LongTermDebtAndCapitalLeaseObligations" is
        # the NONCURRENT-only portion, not the total (e.g. AMD FY2015: noncurrent-tagged
        # concept=$2,032,000,000, this concept=$230,000,000 current maturities, real total
        # $2,262,000,000 - the current portion was silently dropped every such year).
        # _fill_long_term_debt_from_noncurrent_current_split() below sums both into
        # "long_term_debt" (same mechanism as the LongTermDebtNoncurrent/Current pair,
        # only firing as a second-priority fallback when that pair's own fill didn't
        # already resolve it) and pops both raw keys before returning.
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
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
        # filer). DE's smaller sibling concept "SecuredDebt" ("Short-term securitization
        # borrowings", $6,596,000,000 FY2025) was ORIGINALLY excluded here on the reasoning
        # that this loader's transform() has no summing mechanism for two concepts mapped
        # to the same target column (plain `row[db_field] = value` overwrite,
        # last-processed-wins, not additive) - SUPERSEDED 2026-09-09: added as a
        # fallback-only entry right below instead (never sums the two, but no longer
        # silently drops SecuredDebt for the ~399 OTHER filers that tag only it).
        "DebtCurrent",
        # ADDED 2026-09-09 (xbrl_concept_coverage_scan.py comment-leak fix follow-up: this
        # standard us-gaap concept was quoted in the DE comment above discussing what was
        # deliberately excluded, but never actually fetched - 400 real filers tag it
        # (scan-confirmed post-fix). Same generic-name caution as DebtCurrent immediately
        # above (fallback-only: only fills short_term_debt when no other, more specific
        # concept already did) - this is exactly the mechanism that resolves the DE
        # collision concern in that comment: DebtCurrent (processed first, listed above)
        # already fills short_term_debt for DE, so this entry's own fallback-only check
        # correctly skips DE and never overwrites; for a filer that tags ONLY SecuredDebt
        # (no CommercialPaper/ShortTermBorrowings/DebtCurrent/etc. at all), this now fills
        # a previously-NULL short_term_debt instead of silently doing nothing.
        "SecuredDebt",
        # FIXED 2026-09-03 (same sweep): EXPD (Expeditors International) tags its entire
        # real short-term debt under this concept - live-confirmed via real companyfacts
        # JSON: $53,068,000 FY2023 / $30,660,000 FY2024 / $30,263,000 FY2025, small but
        # real and continuous (a genuinely low-debt, asset-light freight-forwarding
        # business - EXPD has no other debt concept tagged anywhere in its companyfacts,
        # consistent with the real figure being this small, not a coverage gap masking a
        # larger number). Fallback-only, same generic-name caution as DebtCurrent above.
        "ShortTermBankLoansAndNotesPayable",
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
        # total_debt_not_itemized investigation): mortgage REITs finance almost entirely via
        # repurchase ("repo") agreements, a standard, companyfacts-exposed us-gaap concept
        # none of the LongTermDebt/CommercialPaper/DebtCurrent/etc. concepts above ever
        # capture - live-confirmed via real SEC companyconcept API data: AGNC Investment
        # Corp (CIK 0001423689) $60,798,000,000 FY2024/$50,426,000,000 FY2023, ARMOUR
        # Residential REIT (CIK 0001428205) $10,713,830,000 FY2024/$9,647,982,000 FY2023 -
        # both real, massive, and completely invisible to long_term_debt/short_term_debt
        # before this fix (every fiscal year NULL for all 4 debt-component columns despite
        # each being a multi-billion-dollar leveraged mortgage REIT). Repo agreements are
        # short-duration rolling financing (30-90 day typical maturity), so this targets
        # short_term_debt, same semantic class as CommercialPaper/ShortTermBorrowings above,
        # not long_term_debt. Fallback-only (see _DEBT_FALLBACK_ONLY_FIELDS in
        # load_financial_statements.py) so a filer that also reports a standard concept
        # keeps that value; live-checked neither AGNC nor ARR reports any other debt
        # concept, so no overwrite-collision risk for the two symbols this was found from.
        "SecuritiesSoldUnderAgreementsToRepurchase",
        # FIXED 2026-09-03 (same sweep, follow-up to the AGNC/ARR find above): SEVN (Seven
        # Hills Realty Trust, a commercial mortgage REIT) tags its real repo financing
        # under this DIFFERENT standard concept instead - live-confirmed via real
        # companyconcept API data: $417,796,000 FY2024 / $487,657,000 FY2025, previously
        # NULL for every debt-component column. Checked SEVN's companyfacts for the plain
        # "SecuritiesSoldUnderAgreementsToRepurchase" concept above too: not tagged at all,
        # so no overwrite-collision risk between the two. Same short-term-financing
        # semantic as the concept above (target: short_term_debt), fallback-only.
        "SecuredDebtRepurchaseAgreements",
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
        # ADDED 2026-09-09 (goal session: SEC/XBRL missing-data count under 700,
        # total_debt_not_itemized investigation): ETS real short-term-loan concept - live-
        # confirmed via ETS's real companyfacts JSON tagging "LoansPayable"/"LoansPayableCurrent"
        # (a real, if small, funding-side liability) while never tagging any of the concepts
        # above. Same either/or-alternative, plain-mapping convention as senior_notes/
        # notes_payable above (fallback-only, never wins over a more specific standard concept).
        "LoansPayable",
        "LoansPayableCurrent",
        # ADDED 2026-09-09 (xbrl_concept_coverage_scan.py comment-leak fix follow-up: this
        # standard us-gaap concept was quoted in the NotesPayable comment above ("no
        # NotesPayableCurrent sibling concept" for AFL/MAA), but never actually fetched -
        # 834 real filers tag it (scan-confirmed post-fix). Targets short_term_debt (the
        # current-portion split of a filer's notes payable, same relationship as
        # LongTermDebt/LongTermDebtCurrent). Fallback-only, same generic-name caution as
        # bare NotesPayable above - only fills short_term_debt when no more specific
        # concept (CommercialPaper/ShortTermBorrowings/SeniorNotesCurrent/DebtCurrent/etc.)
        # already did.
        "NotesPayableCurrent",
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
        # FIXED 2026-09-05 (goal session, same continuation as the debt-concept block
        # below): KBDC (Kayne Anderson BDC) has a real, current annual_balance_sheet row
        # every fiscal year (2022-2025: real total_assets $1.19B-$2.29B, real
        # stockholders_equity/NAV $592M-$1.11B, data_unavailable=FALSE) but long_term_debt
        # was NULL in every one - it never tags any of LongTermDebt/NotesPayable/
        # SecuredDebt/DebtInstrumentCarryingAmount, only
        # "LineOfCreditFacilityFairValueOfAmountOutstanding" (a fair-value, not
        # carrying-value, disclosure concept - unusual, but consistent with a BDC's
        # NAV-based balance sheet already carrying its investments AND liabilities at fair
        # value under ASC 946/825). Cross-validated via magnitude, not just presence:
        # FY2025 total_assets - stockholders_equity implies ~$1.177B total liabilities;
        # this concept's FY2025 value is $1.130B - a 96% match, confirming it's
        # (approximately) KBDC's entire real debt load, not a partial sub-figure.
        # Single-symbol-verified (not found on PFLT/PNNT/GAIN/MAIN/CSWC/NMFC/GSBD/BCSF/
        # NCDL, the other BDCs checked the same session). Listed BEFORE "LineOfCredit"
        # (deliberately, unlike every other addition this session which is appended after
        # its neighbors) so this far-more-complete fair-value figure wins this loader's
        # "first-populated-wins" fallback precedence for KBDC specifically - KBDC also
        # tags a much smaller "LineOfCredit" fact ($135M FY2025) that would otherwise
        # silently win and understate real debt by ~88%; no other filer in this session's
        # sample tags both concepts, so this reordering has no effect on DGICA/DGICB or
        # any other "LineOfCredit"-only filer.
        "LineOfCreditFacilityFairValueOfAmountOutstanding",
        # FIXED 2026-09-05 (goal session: "missing SEC/XBRL data" sweep, total_debt_not_itemized
        # investigation): Donegal Group (DGICA/DGICB, CIK 0000800457) - a small insurance
        # holding company - tags its only real debt instrument, a $35,000,000 revolving
        # credit facility, exclusively under this plain concept - live-confirmed via real SEC
        # companyfacts JSON (FY2025 balance; no LongTermDebt/NotesPayable/SubordinatedDebt/
        # any other debt concept above ever tagged). No Current/Noncurrent split reported, so
        # single-figure fallback, same convention as notes_payable/senior_notes above (target:
        # long_term_debt). Fallback-only (see _DEBT_FALLBACK_ONLY_FIELDS) - generic enough a
        # name that a filer reporting a real, more specific debt concept must keep that value.
        "LineOfCredit",
        # FIXED 2026-09-05 (goal session: "missing SEC/XBRL data" continuation,
        # total_debt_not_itemized investigation): ACHV (Achieve Life Sciences) and BENF
        # (Beneficient) - both real, active filers with real interest expense on file but
        # zero long_term_debt/short_term_debt ever - live-confirmed via real SEC
        # companyfacts JSON tagging their real convertible-note debt under the BARE
        # "ConvertibleDebt"/"ConvertibleDebtCurrent"/"ConvertibleDebtNoncurrent" concepts,
        # a DIFFERENT XBRL element from the already-fetched "ConvertibleNotesPayable"/
        # "ConvertibleLongTermNotesPayable" above: ACHV ConvertibleDebt $16.66M FY2023,
        # ConvertibleDebtCurrent $3.70M + ConvertibleDebtNoncurrent $11.19M FY2025 (split
        # reported starting FY2024). Bare "ConvertibleDebt" (no split) is a single-figure
        # fallback like NotesPayable/SeniorNotes above (target: long_term_debt); the
        # Current/Noncurrent pair follows the SeniorNotes/SeniorNotesCurrent convention
        # (targets: short_term_debt/long_term_debt respectively) since a filer reporting
        # the split never also reports the bare concept for the same fiscal year (same
        # non-collision reasoning as LongTermDebtCurrent's own comment above).
        "ConvertibleDebt",
        "ConvertibleDebtCurrent",
        "ConvertibleDebtNoncurrent",
        # BENF also tags a separate, larger real long-term debt instrument under this
        # concept - live-confirmed $117.9M FY2025/$96.8M FY2026, continuous and consistent
        # with Beneficient's real, publicly known debt scale; not tagged under any other
        # concept already fetched above for this filer (no overwrite-collision risk).
        # Single-figure fallback, same convention as NotesPayable/SeniorNotes.
        "OtherLongTermDebt",
        # FIXED 2026-09-05 (same continuation): SCM (Stellus Capital Investment Corp, a BDC)
        # tags a real, large secured term-debt tranche under this concept - live-confirmed
        # $299M FY2025/$325M FY2024, a DIFFERENT and much larger real instrument than its
        # own "NotesPayable" tag ($122.67M FY2025, its revolving credit facility) - both
        # genuinely outstanding simultaneously (same "two real instruments, no summing
        # mechanism" limitation already accepted for IBOC/HBT's SubordinatedDebt +
        # JuniorSubordinatedDebenture pair above). Single-symbol-verified (not found on
        # GAIN/MAIN/CSWC/NMFC/BCSF/ICMB/RWAY/SAR/NCDL, the other BDCs checked the same
        # session) - fallback-only, same convention as every concept above.
        "SecuredLongTermDebt",
        # ADDED 2026-08-26 (Quality pillar literature audit): needed for Altman Z''-Score's
        # Retained Earnings/Total Assets term (the one term not derivable from concepts
        # already fetched above). Standard, near-universal US-GAAP concept - every filer with
        # a statement of stockholders' equity reports it.
        # CORRECTION 2026-09-03: this WAS missing a taxonomy-variant fallback after all -
        # IFRS filers report the equivalent under ifrs-full "RetainedEarnings" instead, went
        # universally NULL for every one of them until _BALANCE_IFRS_ALIASES added it above.
        "RetainedEarningsAccumulatedDeficit",
        # ADDED 2026-09-07 (goal: SEC/XBRL missing-data audit, found via
        # scripts/xbrl_concept_coverage_scan.py's systematic gap scan): 3,392 real filers tag
        # this concept and it was never fetched at all - no accounts_payable-shaped column
        # existed anywhere in the schema before migration 1263. Live-confirmed via real SEC
        # companyfacts JSON: WMT FY2026 (period end 2026-01-31) = $63,061,000,000, TGT FY2026
        # (period end 2026-01-31) = $12,622,000,000 - both sane, material trade-payables
        # figures. No known taxonomy-variant/IFRS fallback verified yet (none appeared in the
        # coverage scan at any company-count threshold checked) - add one only with the same
        # live-evidence standard as every other fallback in this file, not by guessing a
        # plausible-sounding concept name.
        # ADDED 2026-09-07 (goal session: XBRL concept-coverage backlog sweep, found via
        # scripts/xbrl_concept_coverage_scan.py's systematic gap scan): 485 real filers tag
        # this concept and 223 of them (46%) - including Abbott Labs, Air Products and
        # Chemicals, Armstrong World Industries, Balchem, Brown-Forman - tag NO
        # "AccountsPayableCurrent" at all, live-confirmed against the real on-disk companyfacts
        # cache. Fallback-only (see _DEBT_FALLBACK_ONLY_FIELDS in field_mapping) so a filer
        # reporting the standard concept always keeps that value - listed BEFORE
        # "AccountsPayableCurrent" so the standard concept wins on last-listed-wins overwrite
        # when a filer reports both.
        "AccountsPayableTradeCurrent",
        "AccountsPayableCurrent",
        # ADDED 2026-09-07 (goal session: check_balance_sheet_identity NCI gap rootcaused -
        # see tie_out.py's check_balance_sheet_identity docstring): our schema's
        # stockholders_equity column stores the narrower parent-only concept, so any filer
        # with a material noncontrolling/minority interest fails
        # assets == liabilities + stockholders_equity by exactly that NCI amount - 15% of the
        # annual universe (761/5,078 symbols: XOM, CVX, KKR, APO, CB, RTX, BLK, NEE, D, ENB,
        # VOYA, FNF, IBKR, etc.), not an extraction bug. Live-confirmed via real SEC
        # companyfacts JSON: XOM directly tags this concept (not the combined
        # StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest variant) -
        # FY2009 (period end 2009-12-31) MinorityInterest=$4,823,000,000, exactly closing the
        # gap between XOM's assets ($233,323M) and liabilities+stockholders_equity ($117,931M
        # + $110,569M = $228,500M). Single directly-tagged concept, same convention as
        # accounts_payable above - no summing/derivation needed.
        "MinorityInterest",
        # ADDED 2026-09-09 (goal session: XBRL scan/tie-out exhaustiveness audit, migration
        # 1274): the check_balance_sheet_identity docstring's "PROK/ATTO/FAC/LTGO/SCTX-style"
        # mezzanine-equity population (modest assets/liabilities, huge negative
        # stockholders_equity, no noncontrolling_interest/MinorityInterest tagged either) was
        # left unfixed as "this schema has no column for at all". Live-confirmed via real SEC
        # companyfacts JSON that this concept closes it exactly: OBAI (Our Bond Inc) FY2025
        # residual $11,389,000 == TemporaryEquityCarryingAmountAttributableToParent
        # $11,389,000 for the same period; LTGO (Latigo Biotherapeutics) and SCTX (Scribe
        # Therapeutics) residuals match this same concept exactly too. This was previously
        # dismissed in xbrl_concept_coverage_dismissed.json under a copy-paste-wrong reason
        # ("stock-comp-plan footnote detail" - describes a different concept entirely, not
        # this one) - corrected by mapping it here instead. Single directly-tagged concept, no
        # summing/derivation needed, same convention as MinorityInterest above. PROK itself
        # tags a sibling concept (RedeemableNoncontrollingInterestEquityOtherCarryingAmount,
        # not this one) so its own gap is NOT expected to fully close from this alone.
        "TemporaryEquityCarryingAmountAttributableToParent",
    ]
    rows = _aggregate_concepts(
        client, symbol, concepts, period, ifrs_aliases=_BALANCE_IFRS_ALIASES, alias_groups=_EQUITY_ALIAS_GROUPS
    )
    _fill_long_term_debt_from_noncurrent_current_split(rows)
    _fill_operating_lease_liability_from_current_noncurrent_split(rows)
    if period == "annual":
        _fill_long_term_debt_from_segment_dimensional_facts(rows, client, symbol)
    _fill_cash_and_restricted_cash_combined(rows, client, symbol, period)
    _fill_cash_and_restricted_cash_combined_from_split(rows, client, symbol, period)
    _fill_liabilities_from_assets_minus_equity(rows, client, symbol, period)
    _fill_liabilities_from_ifrs_current_noncurrent_split(rows, client, symbol, period)
    return rows


def _fill_operating_lease_liability_from_current_noncurrent_split(rows: list[dict[str, Any]]) -> None:
    """Fallback-only: operating_lease_liability = CurrentLeaseLiabilities + NoncurrentLeaseLiabilities
    (both ifrs-full concepts, see the "CurrentLeaseLiabilities"/"NoncurrentLeaseLiabilities"
    comment in _BALANCE_IFRS_ALIASES above for the live evidence - Agnico Eagle's combined
    "LeaseLiabilities" concept exactly equals this pair's sum, and 38 real filers in this
    session's on-disk companyfacts cache, POSCO Holdings among them, tag ONLY this split pair
    and never the combined concept at all).

    Only fires when the primary "operating_lease_liability" column (from the combined
    "LeaseLiabilities" ifrs-full alias, or the us-gaap "OperatingLeaseLiability" concept, both
    fetched above) is still empty for that fiscal year - never overwrites a real value. Same
    "both halves must be present" discipline as
    _fill_income_tax_expense_from_current_deferred_split in sec_income_statement_fallbacks.py
    (not the LongTermDebtCurrent "defaults to 0 when absent" convention just above this
    function) - a filer with only one half tagged hasn't reported a lease-liability split this
    way, so summing a partial figure would silently understate real lease debt rather than
    leave an honest NULL. Mutates rows in place and always strips both raw keys.
    """
    for row in rows:
        current = row.pop("current_lease_liabilities", None)
        noncurrent = row.pop("noncurrent_lease_liabilities", None)
        if row.get("operating_lease_liability") is not None or current is None or noncurrent is None:
            continue
        row["operating_lease_liability"] = current + noncurrent


def _fill_liabilities_from_assets_minus_equity(
    rows: list[dict[str, Any]], client: Any, symbol: str, period: str
) -> None:
    """Derive `liabilities` = LiabilitiesAndStockholdersEquity - StockholdersEquity for a filer
    that stops tagging plain "Liabilities" for its most recent fiscal year/quarter but keeps
    tagging the standard cover-page total "LiabilitiesAndStockholdersEquity" concept (a real,
    balance-sheet-identity-guaranteed equivalent: Assets = Liabilities + StockholdersEquity =
    LiabilitiesAndStockholdersEquity by definition, so this is subtraction of two directly-tagged
    facts, not an estimate).

    ADDED 2026-09-08 (goal session: XBRL continuity gap triage follow-up - see
    scripts/triage_xbrl_continuity_gaps.py's SYNONYM_FOUND output). Live-confirmed via real SEC
    companyfacts JSON for all 4 affected filers found by that triage - SEI Investments (CIK
    0000350894), BioRestorative Therapies (0001505497), Datacentrex (0001853825), and Edesa
    Biotech (0001540159) - each has a real, current-period LiabilitiesAndStockholdersEquity fact
    (e.g. BioRestorative 2025-12-31: $4,079,635, EXACTLY matching that period's own Assets fact)
    plus a real StockholdersEquity fact for the same period, while plain "Liabilities" itself is
    absent. The earlier triage script's own SYNONYM_FOUND guess (mapping LiabilitiesCurrent
    directly to the total_liabilities column) was wrong - LiabilitiesCurrent is a genuinely
    smaller, current-only figure, not the total; this derivation is the actual fix.

    Also fills `assets` the same way (assets == LiabilitiesAndStockholdersEquity directly, no
    subtraction needed) when plain "Assets" is itself absent - live-confirmed SEI Investments'
    OWN most recent quarter (2026 Q2) has dropped "Assets" too, not just "Liabilities" (a filer
    that has fully stopped tagging the classified-balance-sheet concepts in favor of the
    cover-page total), so treating only the liabilities side as the gap would have been an
    incomplete fix for the same filer this function was written for.

    Fallback-only: only fills a fiscal year/quarter where the standard concept (already in
    `concepts` above) found nothing - never overwrites a real value.
    """
    combined_rows = _aggregate_concepts(client, symbol, ["LiabilitiesAndStockholdersEquity"], period)
    combined_by_key = {
        (r.get("fiscal_year"), r.get("fiscal_period")): r.get("liabilities_and_stockholders_equity")
        for r in combined_rows
    }
    for row in rows:
        total = combined_by_key.get((row.get("fiscal_year"), row.get("fiscal_period")))
        if total is None:
            continue
        if row.get("assets") is None:
            row["assets"] = total
        if row.get("liabilities") is None:
            equity = row.get("stockholders_equity")
            if equity is not None:
                row["liabilities"] = total - equity


def _fill_liabilities_from_ifrs_current_noncurrent_split(
    rows: list[dict[str, Any]], client: Any, symbol: str, period: str
) -> None:
    """Derive `liabilities` (total_liabilities) = CurrentLiabilities + NoncurrentLiabilities for
    an IFRS filer that splits its balance sheet into the two halves but never tags the combined
    ifrs-full:Liabilities total at all.

    ADDED 2026-09-09 (goal session: XBRL continuity checker follow-up, right after the FPI
    scanning-coverage fix - see scripts/xbrl_concept_continuity_scan.py's own 40-F/20-F
    ifrs-full-merge fix earlier this session). Live-confirmed via HUB Cyber Security Ltd.'s
    real companyfacts JSON (CIK 0001905660): FY2024 (period end 2024-12-31, form 20-F) tags
    CurrentLiabilities=USD 106,074,000 and NoncurrentLiabilities=USD 2,159,000 but has ZERO
    plain ifrs-full:Liabilities fact for that period - cross-checked against the SAME filing's
    directly-tagged EquityAndLiabilities (USD 27,416,000) minus Equity (USD -80,817,000) =
    USD 108,233,000, exactly matching the current+noncurrent sum, confirming this is the real
    total and not a partial figure.

    "CurrentLiabilities" is already fetched under _BALANCE_IFRS_ALIASES for the main
    `liabilities_current`/`current_liabilities` column, so only "NoncurrentLiabilities" needs a
    second lookup here (same secondary-aggregate-call pattern as
    _fill_liabilities_from_assets_minus_equity above). Fallback-only: only fills a fiscal
    year/quarter where the primary "Liabilities" alias found nothing, and only when BOTH halves
    are present - a filer with just one half tagged hasn't reported this split, so summing a
    partial figure would silently understate real liabilities rather than leave an honest NULL
    (same discipline as _fill_operating_lease_liability_from_current_noncurrent_split above).
    """
    noncurrent_rows = _aggregate_concepts(
        client, symbol, [], period, ifrs_aliases=[("NoncurrentLiabilities", "liabilities_noncurrent")]
    )
    noncurrent_by_key = {
        (r.get("fiscal_year"), r.get("fiscal_period")): r.get("liabilities_noncurrent") for r in noncurrent_rows
    }
    for row in rows:
        if row.get("liabilities") is not None:
            continue
        current = row.get("liabilities_current")
        noncurrent = noncurrent_by_key.get((row.get("fiscal_year"), row.get("fiscal_period")))
        if current is None or noncurrent is None:
            continue
        row["liabilities"] = current + noncurrent


def _fill_cash_and_restricted_cash_combined(rows: list[dict[str, Any]], client: Any, symbol: str, period: str) -> None:
    """Populate `cash_and_restricted_cash_combined` from us-gaap:CashCashEquivalentsRestricted
    CashAndRestrictedCashEquivalents - a SEPARATE aggregation pass, not reusable from the main
    concepts list above (migration 1267), because that same concept name already feeds
    `cash_and_equivalents` there as a least-preferred fallback (see this file's own comment on
    it above: "includes restricted cash where a filer only tags this combined figure") -
    _aggregate_concepts' one-raw-key-per-concept-name design means the same concept string
    can't ALSO target a second, different column in the same call.

    ADDED 2026-09-07 (goal session: tie-out check_cashflow_reconciliation follow-up, ADP live-
    confirmed - see migration 1267's own header for the full evidence). Per ASU 2016-18, a
    filer's cash-flow statement reconciles OCF+ICF+FCF to this COMBINED total when it holds
    material restricted cash (payroll processors, banks/trust companies), not to unrestricted
    cash_and_equivalents alone - tie_out.py's check_cashflow_reconciliation prefers this column
    (via COALESCE) when present. NULL for the (majority) of filers with no material restricted
    cash - a second real API/cache lookup per symbol, same as `_fill_long_term_debt_from_
    segment_dimensional_facts` above, but reads from the same already-fetched companyfacts
    cache so it costs no extra network I/O beyond the local disk read.
    """
    combined_rows = _aggregate_concepts(
        client, symbol, ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"], period
    )
    combined_by_key = {
        (r.get("fiscal_year"), r.get("fiscal_period")): r.get(
            "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents"
        )
        for r in combined_rows
    }
    for row in rows:
        key = (row.get("fiscal_year"), row.get("fiscal_period"))
        value = combined_by_key.get(key)
        if value is not None:
            row["cash_and_restricted_cash_combined"] = value


def _fill_cash_and_restricted_cash_combined_from_split(
    rows: list[dict[str, Any]], client: Any, symbol: str, period: str
) -> None:
    """Fallback-only: cash_and_restricted_cash_combined = cash_and_equivalents + RestrictedCash
    (or its current/noncurrent split), for filers that never tag the single combined
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents" concept
    `_fill_cash_and_restricted_cash_combined` above reads.

    ADDED 2026-09-08 (goal session: XBRL coverage-scan exhaustiveness audit - us-gaap:
    RestrictedCash/RestrictedCashCurrent were being silently swallowed by an over-broad
    "RestrictedCash" noise substring instead of being individually reviewed; see this
    concept's dismissal-reversal in xbrl_concept_coverage_dismissed.json's history and the
    NOISE_SUBSTRINGS comment in xbrl_concept_coverage.py). Live-confirmed via Eastman Kodak's
    real companyfacts JSON (CIK 0000031235): FY2025 CashAndCashEquivalentsAtCarryingValue =
    $337,000,000 + RestrictedCashCurrent = $9,000,000, zero
    CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents fact ever filed - the
    combined column was NULL for this real, material (2.7% of cash) restricted-cash balance
    before this fix.

    Only fires when the combined column is still empty for that fiscal year (never overwrites
    a real directly-tagged combined total) and an unrestricted-cash figure is already populated
    for that year - the restricted-cash addend is meaningless without a base to add it to. Reads
    the raw "cash_and_cash_equivalents_at_carrying_value"/"cash_and_due_from_banks" concept keys
    directly (this function runs before load_financial_statements.py's field_mapping stage folds
    those, plus this same function's own combined-concept fallback, into the single
    "cash_and_equivalents" column - see field_mapping's cash_and_equivalents entries). Tiered
    preference (first tier with any data for that fiscal year wins, no
    cross-tier summing - a filer only ever uses one of these tagging conventions):
    1. RestrictedCashCurrent + RestrictedCashNoncurrent (both default to 0 when only one half
       is tagged for that year).
    2. Bare "RestrictedCash" (single combined figure, no current/noncurrent split).
    3. Bare "RestrictedCashAndCashEquivalents" (alternate-label single figure some filers use
       instead of "RestrictedCash" - live-confirmed via Air Products' real companyfacts JSON,
       CIK 0000002969: FY2011 = $77,200,000, real material restricted-cash balance).
    4. Bare "RestrictedCashAndCashEquivalentsNoncurrent" alone (rare filers reporting only the
       noncurrent portion of this alternate label with no current-portion sibling tagged) - a
       closer approximation than leaving the figure at cash_and_equivalents alone.
    ifrs_aliases folds the IFRS analogs (Scully Royalty and others tag
    "ifrs-full:RestrictedCashAndCashEquivalents" bare, or split into Current/Noncurrent) into
    the same tiers so foreign private issuers get the identical fallback treatment.
    """
    concepts = [
        "RestrictedCash",
        "RestrictedCashCurrent",
        "RestrictedCashNoncurrent",
        "RestrictedCashAndCashEquivalents",
        "RestrictedCashAndCashEquivalentsNoncurrent",
    ]
    ifrs_aliases = [
        ("RestrictedCashAndCashEquivalents", "restricted_cash_and_cash_equivalents"),
        ("CurrentRestrictedCashAndCashEquivalents", "restricted_cash_current"),
        ("NoncurrentRestrictedCashAndCashEquivalents", "restricted_cash_noncurrent"),
    ]
    restricted_rows = _aggregate_concepts(client, symbol, concepts, period, ifrs_aliases=ifrs_aliases)
    restricted_by_key = {(r.get("fiscal_year"), r.get("fiscal_period")): r for r in restricted_rows}
    for row in rows:
        if row.get("cash_and_restricted_cash_combined") is not None:
            continue
        cash = row.get("cash_and_cash_equivalents_at_carrying_value")
        if cash is None:
            cash = row.get("cash_and_due_from_banks")
        if cash is None:
            continue
        restricted_row = restricted_by_key.get((row.get("fiscal_year"), row.get("fiscal_period")))
        if not restricted_row:
            continue
        current = restricted_row.get("restricted_cash_current")
        noncurrent = restricted_row.get("restricted_cash_noncurrent")
        if current is not None or noncurrent is not None:
            row["cash_and_restricted_cash_combined"] = cash + (current or 0) + (noncurrent or 0)
            continue
        bare = restricted_row.get("restricted_cash")
        if bare is not None:
            row["cash_and_restricted_cash_combined"] = cash + bare
            continue
        alt_bare = restricted_row.get("restricted_cash_and_cash_equivalents")
        if alt_bare is not None:
            row["cash_and_restricted_cash_combined"] = cash + alt_bare
            continue
        alt_noncurrent = restricted_row.get("restricted_cash_and_cash_equivalents_noncurrent")
        if alt_noncurrent is not None:
            row["cash_and_restricted_cash_combined"] = cash + alt_noncurrent


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

    Second, lower-priority pass (2026-09-07, XBRL concept-coverage backlog sweep):
    long_term_debt = LongTermDebtAndCapitalLeaseObligations + ...Current, the same
    noncurrent-alone understatement bug for XOM/CAT-style filers' OWN concept instead of
    the plain LongTermDebtNoncurrent one - see "LongTermDebtAndCapitalLeaseObligations
    Current"'s own comment in the concepts list above for the live evidence (258 filers,
    1,263 filer-years, Adobe/AT&T/AbbVie/Best Buy among them). Only fires when BOTH halves
    are present for that fiscal year (unlike the primary pair above, a missing current-
    portion tag here is left as the existing, already-correct single-figure fallback
    behavior - the field_mapping-level fallback-only mapping for
    "long_term_debt_and_capital_lease_obligations" alone, untouched by this function,
    still needs that raw key when there is no current-portion sibling to sum it with) and
    only when neither the primary pair above nor a real
    "long_term_debt_and_capital_lease_obligations_including_current_maturities" fact (a
    genuinely more authoritative combined-total concept, fetched separately) already
    resolved this fiscal year - guards against this lower-priority pair racing ahead of a
    better total that the field_mapping stage would otherwise have picked.

    Third pass (2026-09-08, IFRS current-portion-of-Borrowings triage): unlike
    LongTermDebtNoncurrent above, IFRS's "LongtermBorrowings" concept IS mapped directly to
    "long_term_debt" (see its own comment in the concepts list - deliberately kept that way so
    a filer reporting the precise split still outranks a same-period "Borrowings" combined-total
    fact, per this aggregation's first-populated-wins rule and
    test_ifrs_borrowings_and_nci_aliases_20260908.py's existing regression coverage) AND fetched
    a second time under the "long_term_debt_noncurrent" raw key purely so this function can
    detect that case. When "long_term_debt" already equals "noncurrent" exactly, it can only
    have come from LongtermBorrowings itself (Borrowings/other combined concepts would produce
    a different total) - safe to add the current-maturities addend on top without any risk of
    double-counting a Borrowings-sourced total (which already includes its own current portion
    and never equals the noncurrent-only figure).
    """
    for row in rows:
        noncurrent = row.pop("long_term_debt_noncurrent", None)
        current = row.pop("long_term_debt_current", None)
        if row.get("long_term_debt") is None and noncurrent is not None:
            row["long_term_debt"] = noncurrent + (current or 0)
        elif noncurrent is not None and current is not None and row.get("long_term_debt") == noncurrent:
            row["long_term_debt"] = noncurrent + current

        combined_current = row.pop("long_term_debt_and_capital_lease_obligations_current", None)
        if (
            row.get("long_term_debt") is None
            and combined_current is not None
            and row.get("long_term_debt_and_capital_lease_obligations") is not None
            and row.get("long_term_debt_and_capital_lease_obligations_including_current_maturities") is None
        ):
            row["long_term_debt"] = row.pop("long_term_debt_and_capital_lease_obligations") + combined_current
