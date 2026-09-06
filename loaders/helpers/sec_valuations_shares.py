"""Shares-outstanding resolution tier cascade for SecValuationsLoader.fetch_incremental,
extracted from load_sec_valuations.py (2026-09-05, file-size ratchet: that file is one of the
Tier-1 bloaters flagged for decomposition, see MEMORY.md's bloater_decomposition_strategy_20260905).
Method is verbatim, no logic changed - mixed into SecValuationsLoader, which still defines every
MIN_PLAUSIBLE_SHARES_OUTSTANDING/MAX_PLAUSIBLE_SHARES_OUTSTANDING/SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO
class constant and _fetch_live_dual_class_shares_outstanding/_fetch_live_fpi_shares_outstanding_yfinance
method (from ValuationSanityCheckMixin) this method reads/calls via `self`, so behavior is
unchanged - only the method body moved file.
"""

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


class SharesOutstandingResolutionMixin:
    """Tiered shares-outstanding resolution cascade for SecValuationsLoader. Not usable
    standalone - relies on class constants/methods defined on SecValuationsLoader itself and
    on the module-level `DUAL_CLASS_NO_SEPARATOR_ROOTS` constant in load_sec_valuations.py
    (imported locally inside the method, not at module level, to avoid a circular import -
    same pattern as ValuationSanityCheckMixin._sanity_check_market_cap's `_lsv` import).
    """

    # Type-only declarations (no values) so mypy resolves the `self.X` reads below - the real
    # values are class constants defined on SecValuationsLoader, the only class this mixin is
    # ever combined with.
    MIN_PLAUSIBLE_SHARES_OUTSTANDING: int
    MAX_PLAUSIBLE_SHARES_OUTSTANDING: int
    SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO: int

    # Type-only declarations (no bodies) so mypy resolves the cross-mixin `self.X(...)` calls
    # below - the real implementations live on ValuationSanityCheckMixin, which
    # SecValuationsLoader also mixes in.
    def _fetch_live_dual_class_shares_outstanding(self, symbol: str) -> float | None: ...

    def _fetch_live_fpi_shares_outstanding_yfinance(self, symbol: str) -> float | None: ...

    def _resolve_shares_outstanding(  # noqa: C901 -- pre-existing complexity debt, moved verbatim from fetch_incremental, not introduced by this extraction
        self,
        cur: Any,
        symbol: str,
        income_rows: list[tuple[Any, ...]],
        ttm_fiscal_year: int | None,
        ttm_eps_basic: Any,
        _ttm_net_income: Any,
        eps_substituted_from_row1: bool,
        is_foreign_private_issuer: bool,
        reported_shares_outstanding: Any,
    ) -> tuple[float | None, bool, bool, bool]:
        """Resolve shares_out via the tiered fallback cascade fetch_incremental has always used
        (reported basic -> derived net_income/eps -> older fiscal year -> company_info_sec ->
        diluted -> dei cover-page -> scale-mismatch cross-check -> dual-class/FPI yfinance),
        gated at every tier for the dual-class-sibling and foreign-private-issuer ambiguities
        documented inline below. Moved verbatim out of fetch_incremental - same `cur` (still
        inside that method's `with DatabaseContext("read") as cur:` block), same queries, same
        order, same early-return-free control flow (the actual "fail if still no shares
        outstanding" early return stays in fetch_incremental, which is the caller of this
        method, since it needs total_debt/total_cash/ebitda - not in scope here - for the
        unavailable marker).

        Returns (shares_out, has_dual_class_sibling, shares_out_from_dual_class_yfinance,
        shares_out_from_fpi_yfinance) - shares_out is None (or <=0) when every tier failed.
        """
        # Local import (not module-level): load_sec_valuations.py imports this mixin before
        # DUAL_CLASS_NO_SEPARATOR_ROOTS is defined further down in its own source, and this
        # module is imported BY load_sec_valuations.py, so a module-level import here would be
        # a true circular import - same fix already applied in
        # ValuationSanityCheckMixin._sanity_check_market_cap for the same reason.
        from loaders.load_sec_valuations import DUAL_CLASS_NO_SEPARATOR_ROOTS
        from utils.type_conversion import safe_float

        shares_out = None
        # Default False so this is always defined for the FPI-agnostic tiers
        # below (dei cover-page, diluted) even when is_foreign_private_issuer is
        # True and the block below never executes to compute a real value.
        has_dual_class_sibling = False
        if not is_foreign_private_issuer:
            # FIXED 2026-08-21 (goal session - "is BRK.B handled the right way"
            # end-to-end re-check): every tier in this block reads
            # annual_income_statement.shares_outstanding_basic/diluted (directly, or
            # derives from net_income/eps_basic which is equally class-specific) -
            # all four are vulnerable to the same dual-class ambiguity, not just the
            # net_income/eps proxy this was first found on. Live-confirmed: BRK.A's
            # 2021-2026 shares_outstanding_basic is correctly NULL (both prior fixes
            # this session), but the "older fiscal year" tier below reaches all the
            # way back to a real, pre-existing 2014 row (shares_outstanding_basic=
            # 1,643,456 - written years before any fix here existed, never
            # retroactively touched since those fixes only guard NEW writes) and
            # produced the identical wrong value for both BRK.A and BRK.B again.
            # Compute the sibling check once, up front, and gate every tier on it -
            # not just the one where this was first caught.
            base_root = symbol.split(".")[0]
            cur.execute(
                "SELECT 1 FROM stock_symbols WHERE active = true AND symbol != %s "
                "AND (symbol = %s OR symbol LIKE %s) LIMIT 1",
                (symbol, base_root, f"{base_root}.%"),
            )
            has_dual_class_sibling = cur.fetchone() is not None
            if not has_dual_class_sibling:
                # See DUAL_CLASS_NO_SEPARATOR_ROOTS' own module-level comment for the
                # curated-list rationale (DGICA/DGICB etc. - no "." separator, so the
                # dot-split check above never fires for them).
                no_sep_root = next(
                    (r for r in DUAL_CLASS_NO_SEPARATOR_ROOTS if symbol.startswith(r) and len(symbol) == len(r) + 1),
                    None,
                )
                if no_sep_root:
                    cur.execute(
                        "SELECT 1 FROM stock_symbols WHERE active = true AND symbol != %s "
                        "AND symbol LIKE %s AND length(symbol) = %s LIMIT 1",
                        (symbol, f"{no_sep_root}%", len(symbol)),
                    )
                    has_dual_class_sibling = cur.fetchone() is not None
            if (
                not has_dual_class_sibling
                and reported_shares_outstanding
                and self.MIN_PLAUSIBLE_SHARES_OUTSTANDING
                < reported_shares_outstanding
                < self.MAX_PLAUSIBLE_SHARES_OUTSTANDING
            ):
                shares_out = float(reported_shares_outstanding)
                logger.debug(f"[{symbol}] Using reported shares_outstanding_basic: {shares_out:,.0f}")

                # FIXED 2026-08-31 (goal: data-coverage sweep, HBIO follow-up to
                # sec_valuations_fpi_shares_out_missing_gate_fixed_20260831): the query
                # above that produced `reported_shares_outstanding` orders by "has
                # revenue/EPS/net_income" FIRST, fiscal_year DESC second - so
                # `income_rows[0]` (and the shares_outstanding_basic riding along with
                # it) is tied to whichever fiscal year has usable P&L data, not
                # necessarily the most recent fiscal year on file. A real stock split
                # correctly updates the LATEST year's share count immediately, but if
                # that latest year's P&L hasn't posted yet (a fresh partial filing),
                # this tier silently uses an OLDER, pre-split share count instead - the
                # same "stale share count" failure mode already fixed elsewhere in this
                # session (FUBO/GPUS/IHRT), just via a different mechanism (row
                # selection, not concept staleness). Live-confirmed via HBIO (Harvard
                # Bioscience): its FY2026 row has shares_outstanding_basic=4,552,305
                # (matching real ~4.55M shares) but no revenue yet, so the query above
                # picked FY2025's row instead - shares_outstanding_basic=44,391,000 (a
                # real, ~10x-larger PRE-split figure) - producing market_cap=$352.0M vs
                # real ~$34.4M. FY2026's row doesn't even appear in `income_rows` (LIMIT
                # 6, already exhausted by 6 revenue-bearing years) so this can't be
                # solved by scanning already-fetched data - one bounded extra query for
                # the single most recent fiscal year with ANY usable share count (not
                # gated on revenue). Only overrides when it's both a later fiscal_year
                # than the row already selected AND meaningfully different (>=1.3x, same
                # threshold as the reverse-split override in load_company_info_sec.py),
                # so ordinary dilution/buybacks between two adjacent years don't trigger
                # it.
                cur.execute(
                    """
                    SELECT shares_outstanding_basic, fiscal_year FROM annual_income_statement
                    WHERE symbol = %s AND shares_outstanding_basic > %s AND shares_outstanding_basic < %s
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol, self.MIN_PLAUSIBLE_SHARES_OUTSTANDING, self.MAX_PLAUSIBLE_SHARES_OUTSTANDING),
                )
                freshest_row = cur.fetchone()
                if freshest_row and freshest_row[0] and freshest_row[1] and freshest_row[1] > ttm_fiscal_year:
                    freshest_shares = float(freshest_row[0])
                    larger, smaller = max(shares_out, freshest_shares), min(shares_out, freshest_shares)
                    if smaller > 0 and larger / smaller >= 1.3:
                        logger.warning(
                            f"[{symbol}] shares_outstanding_basic from FY{ttm_fiscal_year} "
                            f"(the P&L-bearing row)={shares_out:,.0f} is staler than FY{freshest_row[1]}'s "
                            f"{freshest_shares:,.0f} (ratio {larger / smaller:.1f}x) - likely a stock "
                            "split/major share event between the two years; using the more recent count"
                        )
                        shares_out = freshest_shares

            # Fallback: compute shares outstanding from SEC financial data: shares = net_income / eps.
            # If both net_income and eps are available, we can compute shares directly from SEC audited data.
            # This mathematically reconstructs whatever share count the filer itself used
            # to compute EPS - if that was the same implausible pre-float figure rejected
            # above (live-confirmed: AIAI's derived value is ~1000, matching its rejected
            # reported shares_outstanding_basic exactly), the same floor must apply here too.
            #
            # FIXED 2026-08-21 (goal session - "is BRK.B handled the right way"
            # end-to-end re-check, same bug class as the dual-class shares_outstanding
            # fixes in load_company_info_sec.py/load_financial_statements.py): net_income
            # is a single whole-company figure shared by every share class, but eps_basic
            # is class-specific (BRK.A's EPS is ~1,500x BRK.B's) - this proxy silently
            # reconstructs whichever class's EPS our extraction happened to expose,
            # producing the SAME wrong shares_out for every sibling class regardless of
            # which ticker asked. Gated on has_dual_class_sibling (computed once, above,
            # alongside every other tier in this block).
            # FIXED 2026-08-31 (goal: data-coverage sweep, UROY follow-up to
            # sec_valuations_pl_row_coupled_stale_shares_hbio_fixed_20260831): this
            # "shares = net_income / eps" identity only holds when both operands come
            # from the SAME fiscal year - `ttm_eps_basic` can be silently substituted
            # from `income_rows[1]` (a DIFFERENT, older fiscal year) by the
            # `eps_substituted_from_row1` fallback above (added 2026-08-18 for a
            # different purpose - recovering pe_ratio/PEG when the anchor row's own EPS
            # isn't tagged yet), while `_ttm_net_income` stays the anchor row's own
            # value. Combining the two produces a mathematically meaningless number, not
            # a real share count. Live-confirmed via UROY (Uranium Royalty Corp): anchor
            # FY2026 has net_income=$40.249M but EPS not yet tagged, so EPS was
            # substituted from FY2025's -$0.04 - derived_shares_out =
            # 40,249,000/0.04 = 1,006,225,000 (a fabricated number, not UROY's real
            # ~381M shares per company_info_sec) - producing market_cap=$4.28B vs real
            # ~$1.6-1.67B. The PEG calculation elsewhere in this method already guards
            # against this exact cross-year mismatch via `ttm_eps_fiscal_year` - this
            # tier never had the same guard. Gated the same way: skip when EPS came from
            # a different fiscal year than net_income, same discipline as the
            # dual-class-sibling gate immediately below.
            if (
                not has_dual_class_sibling
                and not eps_substituted_from_row1
                and not shares_out
                and ttm_eps_basic
                and ttm_eps_basic != 0
                and _ttm_net_income
                and _ttm_net_income != 0
            ):
                try:
                    # Shares = Net Income / EPS (mathematical identity from SEC financial statements)
                    derived_shares_out = abs(float(_ttm_net_income) / float(ttm_eps_basic))
                    if (
                        self.MIN_PLAUSIBLE_SHARES_OUTSTANDING
                        < derived_shares_out
                        < self.MAX_PLAUSIBLE_SHARES_OUTSTANDING
                    ):
                        shares_out = derived_shares_out
                        logger.debug(f"[{symbol}] Computed shares_outstanding from income_statement: {shares_out:,.0f}")
                except (ValueError, ZeroDivisionError):
                    pass  # If computation fails, shares_out stays None and we fail below

            # Fallback: the LIMIT 2 rows above are the two most recent fiscal years, but
            # the most recent one is often a partial/estimate-stage filing with NULL
            # shares_outstanding_basic even though an older year has the real reported
            # value (same "latest year is empty" issue fixed for free_cash_flow in
            # load_value_quality_growth_metrics.py - live-confirmed for GPRO/JOUT/CWH/etc,
            # where FY2026 is NULL but FY2025 has a real share count). Search all fiscal
            # years, not just the two most recent, before falling back to company_info_sec.
            if not shares_out and not has_dual_class_sibling:
                cur.execute(
                    """
                    SELECT shares_outstanding_basic FROM annual_income_statement
                    WHERE symbol = %s AND shares_outstanding_basic > %s AND shares_outstanding_basic < %s
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol, self.MIN_PLAUSIBLE_SHARES_OUTSTANDING, self.MAX_PLAUSIBLE_SHARES_OUTSTANDING),
                )
                prior_shares_row = cur.fetchone()
                if prior_shares_row and prior_shares_row[0]:
                    shares_out = float(prior_shares_row[0])
                    logger.debug(
                        f"[{symbol}] Using shares_outstanding_basic from an older fiscal year: {shares_out:,.0f}"
                    )

        # If computation didn't work, try fetching from company_info_sec as fallback.
        # FIXED 2026-08-31 (goal: data-coverage sweep, PHAR/IONR/JZXN/MI follow-up to
        # sec_valuations_frozen_yfinance_snapshot_live_recheck_fixed_20260831): this tier
        # was the ONE domestic-SEC-sourced share-count tier in this whole cascade NOT
        # gated on `not is_foreign_private_issuer` - every sibling tier above/below it
        # (reported/derived/older-year/diluted) is explicitly gated for exactly the
        # ADS/home-market unit-mismatch risk this file's module docstring and dual-class
        # comments describe at length. `company_info_sec.shares_outstanding`'s OWN
        # extraction (load_company_info_sec.py) is *supposed* to already be restricted to
        # domestic forms, but that restriction has real gaps - live-confirmed via MI
        # (Marchex/similar micro-cap FPI): company_info_sec.shares_outstanding=5,065,150
        # landed here unguarded, producing market_cap=$12.46M vs yfinance's real live
        # $584,756 (21x too high) - correctly caught by the sanity check ONLY when its own
        # live-fetch succeeds; a batch run where that live-fetch transiently failed (rate
        # limit/circuit breaker) let this wrong value through completely unchecked, since
        # `_sanity_check_market_cap` has nothing to compare against when yf_market_cap is
        # None. Relying solely on "already guarded upstream" isn't enough defense-in-depth
        # for a value this consequential - this tier needs its own explicit gate too.
        if not shares_out and not is_foreign_private_issuer:
            cur.execute(
                """
                SELECT shares_outstanding FROM company_info_sec
                WHERE symbol = %s AND shares_outstanding > %s AND shares_outstanding < %s
                ORDER BY filing_date DESC LIMIT 1
                """,
                (symbol, self.MIN_PLAUSIBLE_SHARES_OUTSTANDING, self.MAX_PLAUSIBLE_SHARES_OUTSTANDING),
            )
            shares_row = cur.fetchone()
            if shares_row and shares_row[0]:
                shares_out = safe_float(shares_row[0], f"{symbol}.shares_outstanding", allow_none=False)
                logger.debug(f"[{symbol}] Fetched shares_outstanding from company_info_sec: {shares_out:,.0f}")

        # Last-resort fallback: the diluted share count (migration 1192). Some real
        # operating companies (live-confirmed: JOUT/Johnson Outdoors, 44 real 10-K
        # entries) only ever tag WeightedAverageNumberOfDilutedSharesOutstanding in
        # SEC XBRL, never the basic variant - every fallback above depends on basic
        # (directly or via the company_info_sec/net_income/eps proxies) and comes up
        # empty for these filers. Diluted is a real reported count, just not the
        # exact same measure as basic (differs by dilutive securities outstanding).
        # Gated the same as tiers 1-3 above - a foreign private issuer's diluted
        # count carries the identical home-market-units risk. Also gated on
        # has_dual_class_sibling (2026-08-21) - diluted shares are exactly as
        # class-specific as basic, so a dual-class filer's stale/ambiguous diluted
        # count is just as unsafe to trust.
        if not shares_out and not is_foreign_private_issuer and not has_dual_class_sibling:
            cur.execute(
                """
                SELECT shares_outstanding_diluted FROM annual_income_statement
                WHERE symbol = %s AND shares_outstanding_diluted > %s AND shares_outstanding_diluted < %s
                ORDER BY fiscal_year DESC LIMIT 1
                """,
                (symbol, self.MIN_PLAUSIBLE_SHARES_OUTSTANDING, self.MAX_PLAUSIBLE_SHARES_OUTSTANDING),
            )
            diluted_shares_row = cur.fetchone()
            if diluted_shares_row and diluted_shares_row[0]:
                shares_out = float(diluted_shares_row[0])
                logger.debug(
                    f"[{symbol}] Using shares_outstanding_diluted (no basic count reported): {shares_out:,.0f}"
                )

        # Final fallback: the SEC cover-page share count (migration 1195). Some real
        # operating companies (live-confirmed: GEF/Greif 19yrs, DGICA/Donegal Group
        # 18yrs, MC/Moelis 15yrs of real net_income) tag NO weighted-average or
        # CommonStockShares* concept at all in their us-gaap facts - the only
        # share-count data SEC XBRL has for them is the universal
        # dei:EntityCommonStockSharesOutstanding cover-page fact. Restricted to
        # domestic filing forms only inside sec_statements.py's _aggregate_concepts
        # (foreign 20-F/40-F filers report this in local/home-market units with no
        # ADS-ratio conversion - see that file's removed-IFRS-concept comment for the
        # exact 100-1000x-wrong-market-cap trap this avoids repeating).
        #
        # FIXED 2026-08-21: also gated on has_dual_class_sibling - live-confirmed
        # BRK.A/BRK.B both resolved to the identical 941,481 "shares" from this
        # exact tier once the three tiers above it were fixed, since
        # shares_outstanding_dei is populated by a separate extraction path
        # (sec_statements.py) never covered by those fixes. The cover-page fact is
        # exactly as class-specific as basic/diluted, so the same ambiguity applies.
        #
        # FIXED 2026-08-31, two independent same-day gaps in this same tier:
        #
        # (1) No recency bound (goal session: "VCIG tops the scores" follow-up into FPI
        # shares_outstanding - same bug class as load_company_info_sec.py's
        # _latest_shares_value() 2026-08-20 fix). This tier picked whatever fiscal year
        # had the MOST RECENT non-null shares_outstanding_dei with no check on how old
        # that fiscal year actually is - and since a foreign private issuer skips every
        # fresher SEC tier above (basic/diluted, current fiscal years), this was often the
        # ONLY SEC-sourced path reached. Live-confirmed: ENIC resolved to its FY2017 dei
        # value (8 years stale, 49.09B shares) with FY2018-2024 all NULL; CEPU to FY2019
        # (6 years stale, 1.51B shares); AIFU to FY2022 (1.07B shares) despite FY2023-2025
        # basic/diluted showing a real, much smaller, current count (~2.6M-10.1M - AIFU
        # genuinely restructured/consolidated its share count since FY2022, making the
        # FY2022 dei figure doubly wrong: stale AND pre-restructuring). All three fed
        # sec_valuations.shares_outstanding with data_source='sec_audited', silently
        # implying SEC-audited-and-current when it was neither. Fixed the same way as the
        # company_info_sec precedent: the query below rejects a candidate more than 2
        # years (fiscal_year >= this year - 2) older than today, falling through to the
        # FPI-yfinance live-fetch tier instead of trusting a stale figure. Same live class
        # separately confirmed via GENI (Genius Sports): its ONLY shares_outstanding_dei
        # entry across all fiscal years is FY2021's 18,500,000 (a SPAC-de-merger-year
        # founder/sponsor-share figure) against ~254.76M real current shares - a ~14x
        # UNDERcount (mirror image of the FUBO/GPUS/IHRT OVERcounts fixed elsewhere),
        # closed by this same bound.
        #
        # (2) Missing the `not is_foreign_private_issuer` gate every other domestic-SEC-
        # sourced tier in this cascade has (PHAR/IONR/JZXN follow-up - see the
        # company_info_sec fallback tier's own comment above for the full rationale).
        # Live-confirmed via IONR (ioneer Ltd, ADS)/JZXN/PHAR (Pharming, 1 ADS = 10
        # ordinary shares): all three genuine FPIs whose shares_outstanding_dei
        # nonetheless holds a plain ordinary-share count (2,325,614,708 / 11,011,389 /
        # 701,680,440 respectively - sec_statements.py's "domestic forms only"
        # restriction on this concept has a real gap for these filers), producing market
        # caps 10-30x too high. Correctly caught by the sanity check ONLY when its live
        # yfinance re-check succeeds - a batch run where that transiently failed (rate
        # limit/circuit breaker) let all three through unchecked. Gating here too (not
        # relying solely on the upstream restriction) means these symbols now correctly
        # fall through to the FPI live-yfinance tier below instead, live-tested as
        # accurate for PHAR (yfinance sharesOutstanding=70,778,124, correctly
        # ADS-adjusted).
        if not shares_out and not has_dual_class_sibling and not is_foreign_private_issuer:
            cur.execute(
                """
                SELECT shares_outstanding_dei, fiscal_year FROM annual_income_statement
                WHERE symbol = %s AND shares_outstanding_dei > %s AND shares_outstanding_dei < %s
                AND fiscal_year >= %s
                ORDER BY fiscal_year DESC LIMIT 1
                """,
                (
                    symbol,
                    self.MIN_PLAUSIBLE_SHARES_OUTSTANDING,
                    self.MAX_PLAUSIBLE_SHARES_OUTSTANDING,
                    date.today().year - 2,
                ),
            )
            dei_shares_row = cur.fetchone()
            if dei_shares_row and dei_shares_row[0]:
                most_recent_fiscal_year = income_rows[0][0]
                dei_fiscal_year = dei_shares_row[1]
                if most_recent_fiscal_year - dei_fiscal_year > 2:
                    logger.debug(
                        f"[{symbol}] shares_outstanding_dei cover-page count from fiscal_year "
                        f"{dei_fiscal_year} is too stale (symbol has data through "
                        f"{most_recent_fiscal_year}) - skipping rather than trusting a "
                        f"multi-year-old figure, same bound as load_company_info_sec.py's "
                        f"_latest_shares_value() staleness fix"
                    )
                else:
                    shares_out = float(dei_shares_row[0])
                    logger.debug(
                        f"[{symbol}] Using shares_outstanding_dei cover-page count (no us-gaap "
                        f"share concept reported): {shares_out:,.0f}"
                    )

        # FIXED 2026-08-20 (goal: finance-accuracy audit): MAX_PLAUSIBLE_SHARES_OUTSTANDING
        # (100 billion) is calibrated to catch truly absurd derived values (see
        # test_sec_valuations_shares_outstanding_ceiling.py's NMR case, ~2.94e15) but is
        # far too generous to catch a per-filing 1000x XBRL scale error for a small/mid-cap
        # filer - a value like 6.07 billion or 82.5 billion passes the ceiling untouched
        # even though it's still wrong by 3-4 orders of magnitude for that specific
        # company. Live-confirmed: LARK (Landmark Bancorp)'s FY2025
        # shares_outstanding_basic=6,070,662,000 (real count ~6.1M - LARK's OWN FY2026 row
        # and its own shares_outstanding_dei both independently agree on ~6.1M, proving the
        # FY2025 tag itself is what's mis-scaled); RPAY (Repay Holdings) mis-scaled the same
        # way across every fiscal year on file (82.5B/85.6B/89.9B vs company_info_sec's
        # independently-extracted 6.47M). Both fed sec_valuations.market_cap in the
        # hundreds of billions (LARK $195.5B, RPAY $304.5B) for real small-caps, corrupting
        # ps_ratio/fcf_yield. company_info_sec.shares_outstanding comes from a separate
        # extraction path (see load_company_info_sec.py) - when it's available and
        # disagrees with the resolved shares_out by more than
        # SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO in either direction, that's a much
        # stronger signal of a stale/mis-scaled value than the bare ceiling catches, so
        # prefer it (see that constant's own comment for the 2026-08-25 20x->10x
        # lowering and the WHLR/FUBO evidence behind it). Only for domestic filers - a
        # foreign private issuer's company_info_sec figure carries the same
        # home-market-units risk as everywhere else in this method.
        if shares_out and not is_foreign_private_issuer:
            cur.execute(
                """
                SELECT shares_outstanding FROM company_info_sec
                WHERE symbol = %s AND shares_outstanding > %s AND shares_outstanding < %s
                ORDER BY filing_date DESC LIMIT 1
                """,
                (symbol, self.MIN_PLAUSIBLE_SHARES_OUTSTANDING, self.MAX_PLAUSIBLE_SHARES_OUTSTANDING),
            )
            cross_check_row = cur.fetchone()
            if cross_check_row and cross_check_row[0]:
                cross_check_shares = float(cross_check_row[0])
                larger = max(shares_out, cross_check_shares)
                smaller = min(shares_out, cross_check_shares)
                if smaller > 0 and larger / smaller > self.SHARES_OUTSTANDING_SCALE_MISMATCH_RATIO:
                    logger.warning(
                        f"[{symbol}] shares_outstanding scale mismatch: resolved={shares_out:,.0f} "
                        f"vs company_info_sec={cross_check_shares:,.0f} (ratio {larger / smaller:.0f}x) "
                        f"- preferring company_info_sec as the independently-extracted value"
                    )
                    shares_out = cross_check_shares

        # DELIBERATE, NARROW EXCEPTION to this file's "SEC data only, yfinance never a
        # value source" rule (see module docstring) - added 2026-08-22 after live-
        # verifying against real SEC EDGAR data that the exception is structurally
        # unavoidable: data.sec.gov's companyfacts convenience API flattens each
        # concept to ONE value per CIK+period and does not expose XBRL dimensional/
        # segment axes at all, so for a true dual-class filer it CANNOT distinguish one
        # share class's count from another - not a bug in our extraction, a real gap in
        # the only SEC data source this loader has access to (see
        # dual_class_primary_ticker_shares_outstanding_structural_gap_found_20260822 in
        # memory for the live BRK.A/BRK.B verification that established this: SEC has
        # carried NO per-class share data for Berkshire since 2011). Every tier above
        # this point is deliberately disabled for has_dual_class_sibling=True (see each
        # tier's own 2026-08-21 comment) specifically to avoid attributing one class's
        # SEC-reported count to its sibling - that gate stays exactly as strict. This
        # tier only fires when every one of those SEC-sourced paths has already been
        # exhausted and failed, for this narrow case alone. yfinance queries per-LISTING
        # (ticker), not per-company, so it naturally resolves the correct class-specific
        # value instead of SEC's collapsed one - live-verified 2026-08-22: BRK-A/BRK-B,
        # AGM/AGM-A, and BIO/BIO-B each independently resolve to a market_cap
        # (shares x price) matching its sibling's within a few percent, the strongest
        # available sanity check that these are genuinely distinct correct values, not
        # a copy of the parent/sibling figure. Marked via a distinct data_source value
        # below so this narrow exception stays visible/auditable, never silently blended
        # into the "sec_audited" label the rest of this file's output uses.
        shares_out_from_dual_class_yfinance = False
        if not shares_out and has_dual_class_sibling:
            dual_class_shares = self._fetch_live_dual_class_shares_outstanding(symbol)
            if (
                dual_class_shares
                and self.MIN_PLAUSIBLE_SHARES_OUTSTANDING < dual_class_shares < self.MAX_PLAUSIBLE_SHARES_OUTSTANDING
            ):
                shares_out = dual_class_shares
                shares_out_from_dual_class_yfinance = True
                logger.debug(
                    f"[{symbol}] Using yfinance per-class shares_outstanding (dual-class "
                    f"sibling, SEC companyfacts has no per-class data): {shares_out:,.0f}"
                )

        # THIRD narrow, deliberate exception to this file's "SEC data only" rule - ADDED
        # 2026-08-27 (goal: recover the market_cap data gap found live - 945 universe
        # symbols with market_cap=NULL, 81% (768) tagged
        # foreign_private_issuer_shares_unavailable, 99% of those still actively
        # tradable with a live price in the last 5 trading days - not delisted, a
        # permanent structural gap this fallback closes for most of them). Every
        # SEC-sourced tier above is deliberately gated off for FPIs (home-market-vs-ADS
        # unit-mismatch risk - see the tier comments above); this is the exact same
        # "SEC's own API structurally cannot carry the data we need" situation as
        # dual-class shares just above, not a new category of risk. yfinance queries
        # per-LISTING (the ADS ticker itself), so its sharesOutstanding is already on
        # the correct ADS/USD basis - same reasoning that already justifies using
        # yfinance for the dual-class case and for this file's existing FPI live
        # market_cap/PE sanity-check (_fetch_live_fpi_yfinance_check_values). Marked via
        # a distinct data_source value below, same transparency convention as the
        # dual-class exception - never silently blended into "sec_audited".
        shares_out_from_fpi_yfinance = False
        if not shares_out and is_foreign_private_issuer:
            fpi_shares = self._fetch_live_fpi_shares_outstanding_yfinance(symbol)
            if (
                fpi_shares
                and self.MIN_PLAUSIBLE_SHARES_OUTSTANDING < fpi_shares < self.MAX_PLAUSIBLE_SHARES_OUTSTANDING
            ):
                shares_out = fpi_shares
                shares_out_from_fpi_yfinance = True
                logger.debug(
                    f"[{symbol}] Using yfinance shares_outstanding (foreign private "
                    f"issuer, no usable SEC-tagged share count): {shares_out:,.0f}"
                )

        return (
            shares_out,
            has_dual_class_sibling,
            shares_out_from_dual_class_yfinance,
            shares_out_from_fpi_yfinance,
        )
