"""Post-transform share-count / derived-EPS validation methods for
ConsolidatedFinancialStatementsLoader, split out of loaders/helpers/financial_statements_validation.py
(2026-09-07, new-file cap: that combined file was 992 lines, over the 800-line NEW_FILE_CAP in
check_file_size_ratchet.py) into two cohesive halves by sub-topic - this one covers
shares_outstanding_basic/diluted/dei cross-checks and the derived-EPS fallback; the sibling
loaders/helpers/financial_statements_value_validation.py covers EPS/net_income/gross_profit/
debt/goodwill/revenue plausibility checks. Both mix into ConsolidatedFinancialStatementsLoader
alongside each other. Pure code motion, no method body changed - see that module's own history
for the original extraction rationale (both halves came from the same commit that moved this
group out of load_financial_statements.py, itself pinned at the 2000-line hard ceiling with
zero headroom - see check_file_size_ratchet.py's HARD_CEILING).

Relies on attributes/methods defined on ConsolidatedFinancialStatementsLoader itself
(self.table_name, self.statement_type, self.period, self._bulk_insert_mgr,
self._explicit_null_rejections, self._record_explicit_null_rejection) - not usable standalone,
same convention as loaders/helpers/sec_valuations_ratios.py's SecValuationRatiosMixin.
"""

import logging
import statistics
from typing import Any

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

# KNOWN-BAD FPI YFINANCE-FALLBACK SHARE COUNTS (added 2026-09-09, /goal session: "factor
# leaders and laggards still seem off" investigation). This registry exists because
# _reject_implausible_shares_outstanding below has a structural blind spot: its relative
# cross-check needs company_info_sec.shares_outstanding as an independent reference, and
# its absolute ceiling (500B) is calibrated loosely enough to admit genuine mega-caps -
# neither catches a symbol whose ENTIRE data chain (price context, EPS, shares_outstanding)
# is self-consistently sourced from yfinance with NO independent second source at all
# (company_info_sec.shares_outstanding is NULL precisely because this class of symbol - a
# true foreign private issuer with no SEC 10-K/20-F on file, only reachable via
# sec_base.py's _try_yfinance_fallback - never has SEC-derived data to extract it from).
# A wrong-but-internally-consistent number sails through every existing guard.
#
# SKHY (SK hynix, an unsponsored OTC ADR) live-confirmed this way: shares_outstanding_basic/
# diluted=~6.9-7.1B agrees with its own net_income/diluted_eps in every fiscal year 2022-2025
# (so every same-row/cross-year internal-consistency check this file already has correctly
# finds nothing wrong) but implies a $1.32T market cap and pb_ratio=15.78/ps_ratio=19.58 in
# value_metrics (load_sec_valuations.py) - both wildly outside SK hynix's real-world range
# (public real-time quotes put its market cap closer to ~$130-150B, pb/ps in the low
# single digits, roughly a 9-10x gap on every metric). Root cause is UNCONFIRMED - the ~9.75x
# gap is suggestive of an ADS/ordinary-share ratio yfinance itself mis-reports for this
# specific unsponsored OTC ticker (the same real-world phenomenon
# DOMESTIC_FILER_ADS_RATIO_OVERRIDES/FPI_EPS_ADS_RATIO_OVERRIDES in load_sec_valuations.py
# exist to correct), but that registry only ever adjusts SEC-XBRL-tagged EPS to match an
# ADS-basis price/shares_out already resolved from SEC data - SKHY has no SEC filings to
# adjust in the first place, so it's structurally out of that registry's scope. Rather than
# guess a ratio without the same real-filing/press-release confirmation every entry in those
# two registries required before shipping, this follows the more conservative established
# precedent instead (same as an un-cross-checkable shares_outstanding_scale_mismatch case
# elsewhere in this codebase): reject the confidently-wrong share count rather than publish
# it. Revisit if/when a genuinely independent share-count source for unsponsored OTC ADRs is
# added - do not add a symbol here without the same live-evidence standard (an implied
# market cap/pb/ps multiple many-fold outside the company's real-world public range).
KNOWN_BAD_FPI_YFINANCE_SHARES_OUTSTANDING: frozenset[str] = frozenset(
    {
        "SKHY",  # SK hynix (unsponsored OTC ADR) - see module-level comment above
    }
)


class FinancialStatementsShareCountValidationMixin:
    """Shares-outstanding/derived-EPS validation methods for ConsolidatedFinancialStatementsLoader.
    Not usable standalone - relies on attributes/methods defined on that class.
    """

    # Type-only declarations (no values) so mypy resolves the self.X reads below - the real
    # values/methods are defined on ConsolidatedFinancialStatementsLoader, the only class this
    # mixin is ever combined with.
    table_name: str
    statement_type: str
    period: str
    _bulk_insert_mgr: Any
    _explicit_null_rejections: Any

    def _record_explicit_null_rejection(self, row: dict[str, Any], field: str, reason: str) -> None: ...

    def _reject_implausible_shares_outstanding(self, transformed: list[dict[str, Any]]) -> None:
        """Reject shares_outstanding_basic/diluted values that are confidently wrong due to
        SEC's companyfacts API not always normalizing a filer's "reported in thousands"
        inline-XBRL scale attribute. Mutates `transformed` in place.

        FIXED 2026-08-21 (goal session - broad shares_outstanding cross-check audit,
        follow-up to the BRK.A/HEI dual-class fix): live-confirmed against HUB Group's real
        companyfacts JSON (CIK 0000940942): WeightedAverageNumberOfSharesOutstandingBasic
        for FY2025Q3 is tagged val=60066 (a real share count in the tens of millions
        reported "in thousands", not 60,066 actual shares). ~95 active symbols showed this
        exact ~1,000x-too-small pattern when cross-checked against
        company_info_sec.shares_outstanding (an independently-extracted, unaffected
        source). Rejects values below MIN_PLAUSIBLE_SHARES_OUTSTANDING (100,000, same floor
        already used in load_company_info_sec.py) rather than relying on a downstream
        consumer's guard to always be present.

        FIXED 2026-08-21 (same session, follow-up): the absolute floor above only catches
        the thousands-scale bug for SMALLER companies - a large-cap's real share count
        divided by 1000 can easily still clear 100,000 (e.g. NTNX's real ~270M shares,
        stored as 267,479 - "267,479 thousand" per the unconverted XBRL scale= attribute -
        sails right past the floor). Bulk cross-check of
        annual_income_statement.earnings_per_share against
        net_income/shares_outstanding_basic surfaced 891 rows where the implied EPS is
        ~1,000x the reported EPS - live-confirmed NTNX FY2025 exactly this way: stored
        shares_outstanding_basic=267,479 vs company_info_sec's independently-extracted
        270,320,509 (real value, ~1010x higher). Extends the guard with a relative
        cross-check against company_info_sec.shares_outstanding (the same independent
        source load_sec_valuations.py's own 20x scale-mismatch guard already trusts for
        exactly this purpose), not just an absolute floor.

        FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" / tie-out sweep): the
        relative cross-check just below only runs when company_info_sec.shares_outstanding
        has a real value for the symbol - NMR (Nomura Holdings, a Japanese 20-F filer) has
        NULL there, so its shares_outstanding_diluted sailed straight through with no upper
        bound at all. Live-verified via SEC's own companyfacts API
        (WeightedAverageNumberOfDilutedSharesOutstanding, CIK0001163653): the RAW SEC-tagged
        fact itself is 3,041,190,068,000,000 "shares" for FY2026 (and every other fiscal
        year on file, 2018-2026) - a real filer/filing-agent XBRL tagging error on SEC's
        side, not an extraction bug in this codebase (net_income and diluted_eps for the
        same rows are both correct and consistent with each other: implied share count
        net_income/diluted_eps ~= 3.04 BILLION, exactly 1,000,000x smaller than the tagged
        3.04 QUADRILLION). An absolute ceiling closes this gap independent of whether a
        reference value exists. Calibrated against every real value already in this
        table (2026-09-06 DB scan): the largest genuine share counts on file are NVDA
        (~24.5-25.1B, real post-split), MFG/Mizuho Financial (~24.5-25.4B, another large
        Japanese bank ADR), CIGI (~36-38B), AKTX (~24-67B) and UXIN (~63B) - all comfortably
        under 100B even for the most heavily-diluted real filers. 500B leaves ~7x headroom
        above the largest genuine value in this table while still catching NMR's (and any
        similar) many-orders-of-magnitude tagging error.

        FIXED 2026-09-07 (goal: "run all the tie-outs" sweep): `shares_outstanding_dei`
        added as a third guarded field - it sits in this exact same fallback chain (see
        transform()'s `shares = diluted or basic or dei`) but was never covered by this
        guard, so a filer/filing-agent tagging error on the DEI cover-page concept could
        sail straight through into EPS derivation whenever basic/diluted were both missing.
        Live-confirmed via EEFT's (Euronet Worldwide) own filed 10-K XBRL (CIK 0001029199,
        accn 0001213900-21-010724): dei:EntityCommonStockSharesOutstanding tagged as
        52,752,851,000,000,000 for FY2020 - the filer's own three FY2020 10-Qs on file all
        show a real ~52.2-52.3M share count, so this is the exact same "many-orders-of-
        magnitude tagging error" class as NMR's diluted-shares case above, just on a
        different concept. 1,313 annual rows found beyond a 3x/0.33x ratio vs
        shares_outstanding_basic in a live DB scan, several within noise of an exact
        ~1,000,000x multiple (EEFT/EIX/PRTS/FOSL/NNBR/PNNT) - the same systematic shape as
        the "reported in thousands, squared" pattern this guard already exists for.
        """
        min_plausible_shares_outstanding = 100_000
        max_plausible_shares_outstanding = 500_000_000_000
        for row in transformed:
            symbol = row.get("symbol")
            if symbol in KNOWN_BAD_FPI_YFINANCE_SHARES_OUTSTANDING:
                for field in ("shares_outstanding_basic", "shares_outstanding_diluted", "shares_outstanding_dei"):
                    if row.get(field) is not None:
                        logger.warning(
                            f"[{self.table_name}] {symbol} FY{row.get('fiscal_year')}: {field} "
                            "rejected via KNOWN_BAD_FPI_YFINANCE_SHARES_OUTSTANDING registry "
                            "(self-consistent yfinance-fallback data, no independent reference "
                            "available to verify against - see that registry's own docstring)."
                        )
                        row[field] = None
                        self._record_explicit_null_rejection(row, field, "known_bad_fpi_yfinance_shares_outstanding")
                continue
            for field in ("shares_outstanding_basic", "shares_outstanding_diluted", "shares_outstanding_dei"):
                val = row.get(field)
                if val is not None and 0 < val < min_plausible_shares_outstanding:
                    logger.warning(
                        f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                        f"{field}={val:,.0f} is implausibly small (< {min_plausible_shares_outstanding:,}) "
                        "- likely an unconverted 'reported in thousands' XBRL value SEC's "
                        "companyfacts API didn't normalize. Rejecting rather than storing a "
                        "confidently-wrong share count."
                    )
                    row[field] = None
                    self._record_explicit_null_rejection(row, field, "implausible_shares_outstanding_scale_error")
                elif val is not None and val > max_plausible_shares_outstanding:
                    logger.warning(
                        f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                        f"{field}={val:,.0f} is implausibly large (> {max_plausible_shares_outstanding:,}) "
                        "- likely a real filer/filing-agent XBRL tagging error (e.g. NMR's "
                        "~1,000,000x-too-large tagged share count). Rejecting rather than "
                        "storing a confidently-wrong share count."
                    )
                    row[field] = None
                    self._record_explicit_null_rejection(row, field, "implausible_shares_outstanding_scale_error")

        shares_check_symbols = sorted({str(row.get("symbol")) for row in transformed if row.get("symbol")})
        reference_shares: dict[str, float] = {}
        if shares_check_symbols:
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT symbol, shares_outstanding FROM company_info_sec "
                        "WHERE symbol = ANY(%s) AND shares_outstanding > 0",
                        (shares_check_symbols,),
                    )
                    reference_shares = {sym: float(val) for sym, val in cur.fetchall()}
            except Exception as e:
                logger.debug(f"[{self.table_name}] company_info_sec cross-check lookup failed (non-fatal): {e}")

        if not reference_shares:
            return
        for row in transformed:
            symbol = row.get("symbol")
            reference = reference_shares.get(symbol) if symbol else None
            if not reference:
                continue
            for field in ("shares_outstanding_basic", "shares_outstanding_diluted", "shares_outstanding_dei"):
                val = row.get(field)
                if val is None or val <= 0:
                    continue
                ratio = reference / float(val)
                if ratio > 20 or ratio < 1 / 20:
                    # BUG FOUND 2026-08-21 (goal session - log-accuracy audit): `{ratio:.0f}x`
                    # only reads sensibly when val is too SMALL (ratio > 1). When val is too
                    # LARGE instead (ratio < 1, e.g. ALMU FY2026's shares_outstanding_basic=
                    # 17,354,370,000 vs company_info_sec's 18,305,335 - the ~1000x-too-large
                    # mirror image of the same scale bug), `ratio:.0f` rounds to "0x",
                    # printing the nonsensical "disagrees ... by 0x" - live-confirmed 241
                    # occurrences in a single run. Report the magnitude symmetrically
                    # (always >= 1x) and say which side is off so the log is actually usable
                    # for diagnosing which direction the scale error went.
                    times_off = ratio if ratio >= 1 else 1 / ratio
                    direction = "too small" if ratio >= 1 else "too large"
                    logger.warning(
                        f"[{self.table_name}] {symbol} FY{row.get('fiscal_year')}: {field}={val:,.0f} "
                        f"disagrees with company_info_sec.shares_outstanding={reference:,.0f} - "
                        f"{field} looks {times_off:.0f}x {direction} - likely an unconverted "
                        "'reported in thousands' XBRL scale error the absolute floor above didn't "
                        "catch. Rejecting rather than storing a confidently-wrong share count."
                    )
                    row[field] = None
                    self._record_explicit_null_rejection(row, field, "implausible_shares_outstanding_scale_error")

    def _reject_diluted_shares_below_basic(self, transformed: list[dict[str, Any]]) -> None:
        """Reject shares_outstanding_diluted when it's materially BELOW the same row's
        shares_outstanding_basic. Mutates `transformed` in place.

        FOUND 2026-09-07 (goal session: quarterly_diluted_ge_basic_shares tie-out check
        triage, 59 flagged symbol/quarters): diluted share count can never be meaningfully
        less than basic - GAAP defines diluted as basic plus dilutive potential shares (or,
        in a net-loss period, antidilution rules require diluted to simply equal basic, never
        go below it). A row where diluted << basic is a confidently-wrong value, the same
        "filer/filing-agent XBRL tagging error" class _reject_implausible_shares_outstanding
        already exists to catch via an external company_info_sec cross-check - this adds the
        same-row cross-check that catch doesn't cover, since company_info_sec only holds one
        CURRENT share count per symbol and is unreliable for a heavily-diluted small-cap's
        older historical quarters (post-split/reload the current count can differ by 10-100x
        from a several-year-old quarter, in either direction, defeating that ratio check).

        Live-confirmed via direct SEC EDGAR companyfacts fetch (not a code bug, a genuine
        filer tagging error already present in the raw fetched data): ADIL FY2022 Q2 tagged
        WeightedAverageNumberOfDilutedSharesOutstanding=972,641 against a real
        shares_outstanding_basic=24,316,031 (ratio ~25.0x) and FY2022 Q3 tagged
        1,028,982 against 25,724,557 (ratio ~25.0x again) - the same suspiciously exact ~25x
        factor in two independent quarters is a scale/tagging error, not real dilution.
        ABTC FY2020 Q1/Q3 show a smaller but still implausible ~2.2x gap the other way.

        Deliberately does NOT reject the common, legitimate case: many net-loss-quarter
        filers correctly report antidilution by tagging a diluted count numerically equal to
        (or negligibly different from, e.g. AA FY2016 Q1-Q3's 182,000,000 vs
        182,471,195 - a real filer-rounded display value, live-confirmed against AA's own
        companyfacts JSON, ratio ~1.003x) basic - the 20% tolerance below only fires on a
        gap far too large for rounding or a real dilutive-securities computation to explain.
        """
        max_plausible_shortfall = 0.20  # diluted may be up to 20% below basic before rejecting
        for row in transformed:
            basic = row.get("shares_outstanding_basic")
            diluted = row.get("shares_outstanding_diluted")
            if basic is None or diluted is None or basic <= 0 or diluted <= 0:
                continue
            if diluted < basic * (1 - max_plausible_shortfall):
                ratio = basic / diluted
                fiscal_quarter = row.get("fiscal_quarter")
                period_label = f"FY{row.get('fiscal_year')}" + (f"Q{fiscal_quarter}" if fiscal_quarter else "")
                logger.warning(
                    f"[{self.table_name}] {row.get('symbol')} {period_label}: "
                    f"shares_outstanding_diluted={diluted:,.0f} is {ratio:.1f}x BELOW "
                    f"shares_outstanding_basic={basic:,.0f} - diluted can never be materially "
                    "less than basic under GAAP. Likely a filer/filing-agent XBRL tagging "
                    "error. Rejecting rather than storing a confidently-wrong share count."
                )
                row["shares_outstanding_diluted"] = None
                self._record_explicit_null_rejection(row, "shares_outstanding_diluted", "diluted_below_basic_shares")

    def _reject_shares_outstanding_basic_diluted_dei_same_row_mismatch(self, transformed: list[dict[str, Any]]) -> None:
        """Reject shares_outstanding_basic/diluted when they disagree by >5x with the SAME
        row's shares_outstanding_dei. Mutates `transformed` in place.

        FOUND 2026-09-07 (goal session: stock_scores factor/composite sanity sweep, live-
        confirmed via SOAR): unlike _reject_implausible_shares_outstanding's company_info_sec
        cross-check (an independent, possibly stale/different-dated reference the 20x
        threshold is deliberately generous about) or _reject_diluted_shares_below_basic's
        basic-vs-diluted check (which legitimately differ due to dilutive securities), basic/
        diluted and dei come from the SAME filing/row here - dei is the cover-page share count
        as of the filing date, basic/diluted are the weighted-average share count for the
        fiscal period the same filing covers. These can differ moderately from real buybacks/
        issuances during the year, but not by many multiples.

        SOAR FY2025: shares_outstanding_basic=shares_outstanding_diluted=4,386,829 against the
        SAME row's shares_outstanding_dei=38,895,663 (~8.87x) and the independent
        company_info_sec.shares_outstanding=53,633,248 (~12.2x, under
        _reject_implausible_shares_outstanding's 20x threshold and so not caught there) -
        diluted_eps computed from the understated share count came out $1.18 instead of a
        real ~$0.13, crushing pe_ratio to 0.20 and making SOAR the single most "undervalued"
        name in the whole universe (value_score=100.0) on a confidently-wrong share count.
        Cross-checked the rest of the same live 0<PE<1 cluster (31 symbols) this same-session
        sweep surfaced: every other symbol's basic/diluted-vs-dei ratio was under 2.5x (real
        reporting-date variance), SOAR alone at 12.23x - an isolated same-filing tagging
        error, not evidence the existing 20x cross-check threshold itself needs lowering.
        """
        max_plausible_ratio = 5.0
        for row in transformed:
            dei = row.get("shares_outstanding_dei")
            if dei is None or dei <= 0:
                continue
            for field in ("shares_outstanding_basic", "shares_outstanding_diluted"):
                val = row.get(field)
                if val is None or val <= 0:
                    continue
                ratio = dei / float(val) if val < dei else float(val) / dei
                if ratio > max_plausible_ratio:
                    logger.warning(
                        f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                        f"{field}={val:,.0f} disagrees with the SAME row's "
                        f"shares_outstanding_dei={dei:,.0f} by {ratio:.1f}x - too large a gap "
                        "for a same-filing cover-page-vs-weighted-average difference to "
                        "explain. Likely a filer/filing-agent XBRL tagging error. Rejecting "
                        "rather than storing a confidently-wrong share count."
                    )
                    row[field] = None
                    self._record_explicit_null_rejection(
                        row, field, "shares_outstanding_basic_diluted_dei_same_row_mismatch"
                    )

    def _fill_derived_eps(self, transformed: list[dict[str, Any]]) -> None:
        """Fill earnings_per_share when the filer never tagged EarningsPerShareBasic/Diluted
        at all, using data this same row already carries. Mutates `transformed` in place.

        ADDED 2026-09-01 (goal: data-loading gap investigation). Live-verified DB-wide: 7,397
        annual_income_statement rows have revenue but NULL earnings_per_share; 77 of those
        already carry a real diluted_eps (a different XBRL concept, EarningsPerShareDiluted,
        mapped to its own column since the 2026-07-28 fix above but never used as a fallback
        for earnings_per_share itself) and 4,434 have net_income plus a usable share count
        that could derive one. Both recover real signal that growth_metrics/quality_metrics/
        value_metrics currently discard outright (eps_growth_1y/3y/5y, EPS-based quality
        inputs) purely because one specific EPS tag was never filed - the filer still reported
        net income and share count, which is all EPS is defined as.

        Order matters: called AFTER _reject_implausible_shares_outstanding (so the shares this
        derives from have already survived both the absolute-floor and the company_info_sec
        cross-check scale guards above) and BEFORE _reject_implausible_eps (so a still-bad
        derived value gets the same implied-shares/absolute-magnitude rejection a directly-
        reported one would). Both source and derived values come from the SAME row/filing, so
        unlike the shares=net_income/eps derivation in load_sec_valuations.py (which mixed
        values that turned out to come from inconsistently-converted sources, see that file's
        MAX_PLAUSIBLE_SHARES_OUTSTANDING comment for the NMR case) there's no cross-source
        currency/scale mismatch possible here - net_income and shares_outstanding_basic/
        diluted are both this filer's own same-period, same-currency figures.

        Never overwrites a real reported earnings_per_share - only fills when it's still None
        after direct XBRL mapping.

        CROSS-CHECKS ADDED 2026-09-01 (same pass, live-caught while sanity-checking derived
        values before backfilling): dividing by a scale-corrupted share count would derive a
        plausible-looking-but-wrong EPS, and neither existing guard reliably catches that here
        - _reject_implausible_shares_outstanding's company_info_sec cross-check only fires when
        a reference row exists (foreign large-caps without one, e.g. VALE, sail through), and
        the absolute floor (100,000) doesn't catch a corrupted value that's still comfortably
        above it (VALE's own FY2008 shares_outstanding_basic=5,062,148 would derive
        ~$2,611/share, ~1030x its own FY2009 row of 5,212,406,000). So before dividing:
        1. Cross-check against company_info_sec.shares_outstanding when a reference exists
           (same 20x threshold as _reject_implausible_shares_outstanding above).
        2. Otherwise cross-check against this SAME symbol's OWN other fiscal years already
           present in this batch (same idea as EPS_SPLIT_GUARD_CLEAN_MULTIPLES's adjacent-year
           scan in load_value_quality_growth_metrics.py, applied here to catch a scale error
           rather than a real split).
        3. If NEITHER cross-check has anything to compare against (a symbol with exactly one
           ever-fetched share-count data point and no company_info_sec row - live-confirmed on
           ATHS: shares_outstanding_basic=203,805 alone would derive an uncorroborated
           ~$13,301/share), don't derive at all rather than trust a single, uncorroborated
           number - same "missing scores are better than fabricated heuristics" governance this
           file already applies elsewhere, just applied to a single input instead of a score.
        """
        # First fill the zero-risk diluted_eps fallback - no cross-check needed, it's already a
        # real reported XBRL value under a different concept.
        needs_division: list[dict[str, Any]] = []
        # FIXED 2026-09-05 (goal session: "missing SEC/XBRL data" continuation, Visa
        # investigation): a filer whose EPS/weighted-average-share concepts are tagged
        # EXCLUSIVELY with a required dimension (live-confirmed via Visa's real SEC data:
        # its 2025 10-K's own R-file plainly shows "us-gaap:EarningsPerShareBasic"/
        # "WeightedAverageNumberOfSharesOutstandingBasic" with real values on the primary
        # income statement, but all three concepts 404 on SEC's own live companyconcept
        # API and are entirely absent from companyfacts - the same aggregation gap this
        # loader's own get_income_statement() draws from) has NONE of shares_outstanding_
        # diluted/basic/dei on this row at all, so the existing needs_division gate above
        # never even considers it - despite company_info_sec.shares_outstanding having a
        # real, independently-extracted value (Visa: 1,687,629,770, via that loader's own
        # dei:EntityCommonStockSharesOutstanding/filing-text fallback chain, a completely
        # separate, non-dimensional extraction path). Tracked separately from
        # needs_division since there is no per-row share count to corroborate the
        # company_info_sec reference AGAINST here (the whole point is none exists) - the
        # reference is used directly, trusting its own already-applied plausibility floor
        # (MIN_PLAUSIBLE_SHARES_OUTSTANDING, load_sec_valuations.py) rather than guessed.
        #
        # KNOWN LIMITATION (found 2026-09-05, same investigation, verified against Visa's
        # own real numbers before shipping): company_info_sec.shares_outstanding is a
        # SINGLE current snapshot, not a per-fiscal-year history - every fiscal year for a
        # symbol that reaches this tier divides by the exact same share count. This is
        # fine for a single-year consumer (pe_ratio's TTM EPS), but for a MULTI-YEAR
        # consumer (growth_metrics' eps_growth_1y/3y/5y, which compares two derived years
        # against each other), the constant divisor cancels out of the ratio entirely -
        # the resulting "EPS growth rate" becomes mathematically identical to net_income
        # growth, silently losing any real EPS growth contributed by share buybacks
        # (or diluted by issuance). Live-quantified via Visa (an active repurchaser):
        # real FY25-vs-FY24 basic EPS growth was +4.93% ($10.22 vs $9.74, both real
        # reported values) - derived-from-this-tier growth using the same net_income
        # figures would only show +1.62%, roughly 1/3 of the real rate. Not fabricated or
        # wrong-signed, just a real, quantifiable floor on precision for any buyback-
        # active symbol in this tier's population - the true fix (recovering the exact
        # per-year reported EPS) requires parsing each fiscal year's raw XBRL instance
        # document for a StatementClassOfStockAxis-dimensioned EarningsPerShareBasic fact
        # (confirmed technically feasible via Visa's real filing - see this session's
        # notes - but needs the same per-symbol dimensional-member verification the
        # sec_xbrl_segments.py segment-revenue fixes already do one company at a time,
        # not a blanket rule), deliberately not attempted here.
        needs_reference_only_division: list[dict[str, Any]] = []
        for row in transformed:
            if row.get("earnings_per_share") is not None:
                continue
            diluted = row.get("diluted_eps")
            if diluted is not None:
                row["earnings_per_share"] = diluted
                continue
            net_income = row.get("net_income")
            if net_income is None:
                continue
            # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep, PJT
            # follow-up): shares_outstanding_diluted/basic (period weighted-average concepts)
            # are the preferred denominator, but a filer that never tags EITHER - live-
            # confirmed via PJT Partners (net_income real every year 2019-2026, no
            # EarningsPerShareBasic/Diluted OR any WeightedAverageNumberOfShares* concept
            # anywhere in its real companyfacts history since 2016) - can still have a real,
            # non-fabricated share count via dei:EntityCommonStockSharesOutstanding (the
            # mandatory SEC cover-page fact, a point-in-time count rather than a period
            # average, but the same "genuinely reported, not guessed" standard already applied
            # to shares_outstanding_dei elsewhere in this codebase as a last-resort shares
            # source). Last in the fallback chain - never overrides a real period-average count.
            shares = (
                row.get("shares_outstanding_diluted")
                or row.get("shares_outstanding_basic")
                or row.get("shares_outstanding_dei")
            )
            if shares is None or shares <= 0:
                # FIXED 2026-09-05 (same Visa investigation, caught by this file's own
                # regression suite before shipping): shares is None here for TWO very
                # different reasons that look identical at this point in the pipeline -
                # (a) genuinely never tagged (Visa's real case), or (b) a real value WAS
                # tagged but _reject_implausible_shares_outstanding (which runs before
                # this method - see this function's own docstring) already nulled it for
                # being a scale-corrupted VALE-style outlier. Using company_info_sec
                # directly is only safe for (a) - for (b), the filer's own reporting for
                # this exact fiscal year is already known-unreliable, so silently
                # substituting a different source's share count would defeat the
                # rejection that just ran. Skip whenever this exact row+field pair is in
                # _explicit_null_rejections (case (b)); a bare `shares is None` case that
                # was never even in the raw fetch (case (a)) never appears there.
                pk_cols = list(self._bulk_insert_mgr.primary_key)
                pk_key = tuple(row.get(pk) for pk in pk_cols)
                was_rejected = any(
                    tuple(pk_values.get(pk) for pk in pk_cols) == pk_key
                    and field in ("shares_outstanding_basic", "shares_outstanding_diluted")
                    for pk_values, field in self._explicit_null_rejections
                )
                # A field that's present but non-positive (e.g. an explicit 0, not simply
                # absent) is itself a known-bad reported value, the same "don't trust this
                # filing's own share count, but don't just substitute a different source
                # either" situation as an explicit rejection above - not the "never tagged
                # at all" case company_info_sec is meant to fill in for.
                _share_field_values = (
                    row.get(f)
                    for f in ("shares_outstanding_diluted", "shares_outstanding_basic", "shares_outstanding_dei")
                )
                any_field_reported_non_positive = any(v is not None and v <= 0 for v in _share_field_values)
                if not was_rejected and not any_field_reported_non_positive:
                    needs_reference_only_division.append(row)
                continue
            needs_division.append(row)

        if not needs_division and not needs_reference_only_division:
            return

        # Only issue the company_info_sec round-trip when at least one row actually needs it -
        # same "skip the query in the common healthy case" pattern the downgrade-guard lookup
        # above already uses.
        symbols_needing_division = sorted(
            {str(row["symbol"]) for row in (*needs_division, *needs_reference_only_division) if row.get("symbol")}
        )
        reference_shares: dict[str, float] = {}
        if symbols_needing_division:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT symbol, shares_outstanding FROM company_info_sec "
                    "WHERE symbol = ANY(%s) AND shares_outstanding > 0",
                    (symbols_needing_division,),
                )
                reference_shares = {sym: float(val) for sym, val in cur.fetchall()}

        shares_history_by_symbol: dict[str, list[float]] = {}
        for row in transformed:
            symbol = row.get("symbol")
            if not symbol:
                continue
            for field in ("shares_outstanding_diluted", "shares_outstanding_basic", "shares_outstanding_dei"):
                val = row.get(field)
                if val:
                    shares_history_by_symbol.setdefault(str(symbol), []).append(float(val))

        for row in needs_division:
            net_income = row["net_income"]
            shares = (
                row.get("shares_outstanding_diluted")
                or row.get("shares_outstanding_basic")
                or row.get("shares_outstanding_dei")
            )
            assert shares is not None  # narrows for mypy; needs_division's filter already guarantees this
            symbol = str(row.get("symbol") or "")

            reference = reference_shares.get(symbol)
            if reference:
                ratio = reference / float(shares)
                if ratio > 20 or ratio < 1 / 20:
                    continue
            else:
                siblings = [v for v in shares_history_by_symbol.get(symbol, []) if v != float(shares)]
                if not siblings:
                    continue
                ratio = statistics.median(siblings) / float(shares)
                if ratio > 20 or ratio < 1 / 20:
                    continue
            row["earnings_per_share"] = float(net_income) / float(shares)

        for row in needs_reference_only_division:
            symbol = str(row.get("symbol") or "")
            reference = reference_shares.get(symbol)
            if not reference:
                continue
            row["earnings_per_share"] = float(row["net_income"]) / reference
