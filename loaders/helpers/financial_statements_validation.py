"""Post-transform data-quality validation/rejection sweep methods for
ConsolidatedFinancialStatementsLoader, extracted verbatim from load_financial_statements.py
(2026-09-07, file-size ratchet: that file was pinned at the 2000-line hard ceiling in
.file-size-baseline.json with zero headroom - see check_file_size_ratchet.py's HARD_CEILING).

Every method here operates on the already-fetched, already-transformed `transformed` row
list (called from transform(), just below where this block used to live) to reject
confidently-wrong values a filer/filing-agent XBRL tagging error produced (implausible
share counts, EPS, gross profit, debt, goodwill, revenue scale mismatches, etc.) before the
rows are persisted - a cohesive "post-transform sanity sweep" group, not an arbitrary
line-count split. Pure code motion: no method body changed, only moved file and got wrapped
in this mixin class. Relies on attributes/methods defined on ConsolidatedFinancialStatementsLoader
itself (self.table_name, self.statement_type, self.period, self._bulk_insert_mgr,
self._explicit_null_rejections, self._record_explicit_null_rejection) - not usable standalone,
same convention as loaders/helpers/sec_valuations_ratios.py's SecValuationRatiosMixin.
"""

import logging
import statistics
from typing import Any

from utils.bulk_insert_manager import BulkInsertManager
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class FinancialStatementsValidationMixin:
    """Post-transform rejection/sanity-check methods for ConsolidatedFinancialStatementsLoader.
    Not usable standalone - relies on attributes/methods defined on that class.
    """

    # Type-only declarations (no values) so mypy resolves the self.X reads below - the real
    # values/methods are defined on ConsolidatedFinancialStatementsLoader, the only class this
    # mixin is ever combined with.
    table_name: str
    statement_type: str
    period: str
    _bulk_insert_mgr: BulkInsertManager
    _explicit_null_rejections: list[tuple[dict[str, Any], str]]

    def _record_explicit_null_rejection(self, row: dict[str, Any], field: str, reason: str) -> None:
        raise NotImplementedError

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

    def _reject_implausible_eps(self, transformed: list[dict[str, Any]]) -> None:
        """Reject earnings_per_share/diluted_eps values that are confidently wrong due to
        filer-side XBRL tagging errors, not a SEC API normalization issue like the shares
        guard above. Mutates `transformed` in place.

        FOUND 2026-08-23 (goal session: real-money-readiness "why does earnings_per_share
        say -$24,852,333/share" audit): live-confirmed via GIBO's real companyfacts JSON -
        the filer itself tagged EarningsPerShareBasic under the correct "USD/shares" unit
        but with the SAME raw value as that year's NetIncomeLoss (FY2023: both exactly
        -12,117,569; FY2024: both exactly -24,852,333) - i.e. the filer's own XBRL reports
        total net income as if it were per-share, not a unit-parsing bug on our side (no
        currency/unit filter would catch this - the unit tag is correct, the underlying
        number is wrong). Also live-confirmed on BTTC, HQ, GROY, BRUN, and EP's FY2013/2014
        (eps==net_income exactly), plus a related /1000 variant (FLOC: eps=32,729 vs
        net_income=32,729,000 - implied ~1,000 shares). No consumer downstream (growth_metrics'
        eps_growth_*) reliably catches this: the resulting YoY growth RATIO between two
        similarly-corrupted years can look like an ordinary percentage (GIBO's eps_growth_1y
        computed a plausible-looking -100.00), so a wrong-by-millions per-share value was
        reaching stock_scores/growth_metrics undetected. Implied-shares floor deliberately
        low (10,000) - BRK.A (~1.6M real shares) and foreign large-caps reporting in local
        currency (BSAC ~471M CLP shares, EC ~2.06B COP shares) all clear it comfortably;
        only implies-basically-no-real-float cases like the ones above trip it.
        """
        min_plausible_implied_shares = 10_000
        # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep, eps_
        # reconciliation follow-up): the implied-shares floor above only catches the
        # "eps==net_income" extreme (implies basically zero real shares) - it does NOT catch
        # a filer-side decimal/scale error that lands on a still-plausible-looking implied
        # share count. Live-confirmed via NRC (National Research Corporation, CIK 0000070487):
        # FY2025 10-K tags EarningsPerShareDiluted=$50.00 against real NetIncomeLoss=
        # $11,600,000 - implied_shares = 232,000, comfortably above the 10,000 floor (so the
        # check above never fires), but NRC's OWN real weighted-average diluted share count
        # for the SAME row is 22,396,000 - a ~96x gap, and $50/share is obviously wrong for a
        # company whose real diluted EPS is ~$0.52 (a real, filed 10-K/Q shows the correct
        # scale in adjacent periods: FY2024 diluted_eps=$1.04 against 23,743,000 shares, an
        # entirely normal-looking figure). Unlike the shares_outstanding guard above, this
        # row already carries its own real share count from the SAME extraction - a much
        # tighter, symbol-specific cross-check than the earlier absolute floor, so a generous
        # 10x tolerance (well outside any real dilution/NCI/preferred-dividend spread, which
        # tie_out.py's own eps_reconciliation check already tolerates at 15%) still leaves no
        # room for a genuine EPS to trip it while catching this exact scale-error shape.
        eps_shares_field = {
            "earnings_per_share": "shares_outstanding_basic",
            "diluted_eps": "shares_outstanding_diluted",
        }
        max_implied_vs_reported_shares_ratio = 10.0
        # BUG FOUND 2026-08-31 (goal session: "let's check the logs" sweep of live loader
        # output): SWK/UAMY quarterly rows hit the raw NUMERIC(12,4) column-overflow guard in
        # sec_base.py instead of this smarter rejection (e.g. "earnings_per_share=150330000")
        # - live-confirmed the reason: this function's implied-shares check requires
        # net_income to be present and non-zero for the SAME row, but a quarterly row can
        # have net_income missing/None while still carrying a garbage per-share value from
        # the identical filer-side mistagging bug this function already exists to catch. The
        # `continue` above skipped the whole row, so the garbage value reached the DB-insert
        # layer's overflow guard instead - which fails safe (data_unavailable) but with a
        # worse error and none of the informative "why" this function provides. Add an
        # absolute-magnitude fallback that doesn't need net_income at all: no real company has
        # ever reported anywhere near $1,000,000/share EPS in a single period (BRK.A's real
        # historical extremes, driven by unrealized investment gains, stay under $200,000/share
        # even in exceptional years - this floor leaves >5x headroom above that).
        max_plausible_abs_eps = 1_000_000
        for row in transformed:
            net_income = row.get("net_income")
            has_net_income = net_income is not None and net_income != 0
            for field in ("earnings_per_share", "diluted_eps"):
                eps = row.get(field)
                if eps is None or eps == 0:
                    continue
                if has_net_income:
                    assert net_income is not None  # narrows for mypy; has_net_income already guarantees this
                    implied_shares = abs(float(net_income) / float(eps))
                    if implied_shares < min_plausible_implied_shares:
                        logger.warning(
                            f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                            f"{field}={eps} implies only {implied_shares:,.0f} shares outstanding "
                            f"against net_income={net_income:,.0f} - implausibly low for any real "
                            "public float. Filer-side XBRL tagging error (raw net income reported "
                            "as per-share), not a currency/scale issue. Rejecting rather than "
                            "storing a confidently-wrong per-share value."
                        )
                        row[field] = None
                        self._record_explicit_null_rejection(row, field, "implausible_eps_filer_tagging_error")
                        continue
                    reported_shares = row.get(eps_shares_field[field])
                    if reported_shares is not None and float(reported_shares) > 0:
                        shares_ratio = max(implied_shares, float(reported_shares)) / min(
                            implied_shares, float(reported_shares)
                        )
                        if shares_ratio > max_implied_vs_reported_shares_ratio:
                            logger.warning(
                                f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                                f"{field}={eps} implies {implied_shares:,.0f} shares against "
                                f"net_income={net_income:,.0f}, but this row's own "
                                f"{eps_shares_field[field]}={float(reported_shares):,.0f} - a "
                                f"{shares_ratio:,.0f}x gap. Filer-side decimal/scale tagging error "
                                "(NRC-shaped: a plausible-looking implied share count that still "
                                "disagrees with this row's own real share count), not a currency/"
                                "scale issue. Rejecting rather than storing a confidently-wrong "
                                "per-share value."
                            )
                            row[field] = None
                            self._record_explicit_null_rejection(row, field, "implausible_eps_filer_tagging_error")
                            continue
                if abs(float(eps)) > max_plausible_abs_eps:
                    logger.warning(
                        f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                        f"{field}={eps} exceeds ${max_plausible_abs_eps:,}/share - implausible for "
                        "any real filer regardless of net_income availability (net_income was "
                        f"{'unavailable/zero' if not has_net_income else f'{net_income:,.0f}'} for "
                        "this row, so the implied-shares cross-check above couldn't run). Same "
                        "filer-side XBRL tagging error class, caught via absolute magnitude "
                        "instead. Rejecting rather than storing a confidently-wrong per-share "
                        "value or letting it hit the raw column-overflow guard downstream."
                    )
                    row[field] = None
                    self._record_explicit_null_rejection(row, field, "implausible_eps_filer_tagging_error")

    def _reject_scale_mismatched_net_income(self, transformed: list[dict[str, Any]]) -> None:
        """Reject `net_income` when it's a clean 1,000x or 1,000,000x-too-small multiple of
        (pretax_income - income_tax_expense) - the same filer-side "reported in thousands/
        millions under a whole-dollar concept" scale error `_reject_implausible_eps`'s own
        docstring already names (the FLOC case: eps=32,729 vs net_income=32,729,000), just
        caught here from the other side of that same identity, for rows where pretax_income/
        income_tax_expense happen to carry the correct scale while net_income itself doesn't.

        FOUND 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep, pretax_to_
        net_income follow-up - this identity's own 593-symbol tie-out failure count hadn't
        moved all session despite several sibling fixes landing). Live-confirmed via 3 of
        this check's own top offenders: MVBF (pretax=$36,850,000, tax=$9,928,000,
        net_income=$26,922 - pretax-tax=$26,922,000, an EXACT 1,000x match), KWY
        (pretax=-$14,004,000, tax=-$3,752,000, net_income=-$10,252 - pretax-tax=-$10,252,000,
        exact match), NXPL (pretax=-$10,463,000, tax=$0, net_income=-$10,463 - exact match).
        Unlike `_reject_implausible_eps`'s fp=None non-integer detector (which catches this
        exact bug shape but only for EPS, and only for proxy-statement-sourced facts), this
        targets net_income directly, regardless of source form, since a clean multiplicative
        match against this row's own pretax_income/income_tax_expense is precise enough on
        its own - no reliance on the fact's form/fp (already gone by the time `transformed`
        rows reach this stage).

        Deliberately does NOT attempt to "fix" the value by multiplying it back up: with
        `pretax_income - income_tax_expense` itself sometimes wrong instead (ambiguous from
        magnitude alone, same as `_reject_implausible_eps`'s MVBF/TE-shaped mirror case),
        nulling is the same "honest NULL over a confidently-wrong number" choice made
        throughout this file - either value being wrong corrupts the same downstream ratios
        (ROE, net_margin, ...) equally, so which one gets nulled doesn't change the outcome.
        Tolerance (20% of the scaled comparison, not tie_out.py's tighter 10%/$500K) is
        deliberately loose: this only needs to recognize "unmistakably the same multiplicative
        family", not reconcile the identity precisely - genuine NCI/discontinued-operations
        noise this file's own pretax_to_net_income WARN check already tolerates can push a
        real match a few points off 1,000x/1,000,000x without this guard losing confidence
        that it's still the same scale-error shape.
        """
        min_plausible_abs_expected = 100_000.0
        scale_tolerance_pct = 0.20
        for row in transformed:
            net_income = row.get("net_income")
            pretax_income = row.get("pretax_income")
            income_tax_expense = row.get("income_tax_expense")
            if net_income is None or net_income == 0 or pretax_income is None or income_tax_expense is None:
                continue
            expected = float(pretax_income) - float(income_tax_expense)
            if abs(expected) < min_plausible_abs_expected:
                continue
            for scale in (1_000, 1_000_000):
                scaled_net_income = float(net_income) * scale
                relative_error = abs(scaled_net_income - expected) / abs(expected)
                if relative_error <= scale_tolerance_pct:
                    logger.warning(
                        f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                        f"net_income={net_income:,.0f} is a {scale:,}x-too-small match against "
                        f"pretax_income({pretax_income:,.0f}) - income_tax_expense("
                        f"{income_tax_expense:,.0f}) = {expected:,.0f} (net_income*{scale:,} = "
                        f"{scaled_net_income:,.0f}, {relative_error:.1%} residual). Filer-side "
                        "scale tagging error (reported in thousands/millions under a whole-"
                        "dollar concept), not a currency issue. Rejecting rather than storing a "
                        "confidently-wrong net_income."
                    )
                    row["net_income"] = None
                    self._record_explicit_null_rejection(row, "net_income", "net_income_scale_error")
                    break

    def _reject_implausible_gross_profit(self, transformed: list[dict[str, Any]]) -> None:
        """Reject `gross_profit` when it exceeds revenue by more than 3x while cost_of_revenue
        is a real, positive figure - not a tolerance/measurement-noise check like
        algo/monitoring/data_patrol/checks/tie_out.py's own gross_profit_identity WARN (2%
        tolerance, still exploratory per that file's own docstring), but a hard mathematical
        impossibility check: gross_profit = revenue - cost_of_revenue, so with a real positive
        cost_of_revenue on the same row, gross_profit can never legitimately exceed revenue at
        all, let alone by 3x+.

        FOUND 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep, gross_profit_
        identity follow-up). Live-confirmed via HCTI: FY2025 10-K/A tags GrossProfit=
        $1,235,000,000 against real revenue=$13,891,000 and cost_of_revenue=$12,001,000 (real
        FY2025 gross profit is ~$1.89M - HCTI's own Q2 2026 10-Q shows a comparable-scale
        $4.459M half-year gross profit, confirming the real business is nowhere near
        $1.235B) - an ~89x overstatement, a filer/filing-agent tagging error in the amendment
        itself. Not a clean round-multiple scale error (unlike `_reject_scale_mismatched_
        net_income` above) - no single scale factor to detect, so this uses the simpler
        "impossible under the definitional identity" signal instead. 3x threshold (not 1x)
        deliberately leaves room for a company reporting an adjusted/non-strictly-definitional
        gross profit figure that legitimately differs somewhat from the raw subtraction -
        only rejects an extreme, order-of-magnitude-style violation.
        """
        max_plausible_gross_profit_to_revenue_ratio = 3.0
        for row in transformed:
            revenue = row.get("revenue")
            cost_of_revenue = row.get("cost_of_revenue")
            gross_profit = row.get("gross_profit")
            if revenue is None or revenue <= 0 or cost_of_revenue is None or cost_of_revenue <= 0:
                continue
            if gross_profit is None:
                continue
            if float(gross_profit) > float(revenue) * max_plausible_gross_profit_to_revenue_ratio:
                logger.warning(
                    f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                    f"gross_profit={gross_profit:,.0f} exceeds {max_plausible_gross_profit_to_revenue_ratio:.0f}x "
                    f"revenue({revenue:,.0f}) while cost_of_revenue({cost_of_revenue:,.0f}) is a real positive "
                    "figure - mathematically impossible under gross_profit = revenue - cost_of_revenue. "
                    "Filer-side tagging error, not a currency/scale issue with a clean multiple. Rejecting "
                    "rather than storing a confidently-wrong gross_profit."
                )
                row["gross_profit"] = None
                self._record_explicit_null_rejection(row, "gross_profit", "implausible_gross_profit_scale_error")

    def _reject_stale_gross_profit_without_fresh_concept(self, transformed: list[dict[str, Any]]) -> None:
        """Force-null a stale `gross_profit` value for any (symbol, fiscal_year) where this
        run's fresh SEC extraction has both revenue and cost_of_revenue but no fresh
        gross_profit fact of its own. Mutates nothing in `transformed` directly - records the
        rejection so post_run() force-nulls the DB column, bypassing preserve_on_missing_
        fields' COALESCE (see the 2026-08-23 fix comment in __init__ for why that's necessary
        for a deliberate rejection, as opposed to a transient fetch gap).

        ADDED 2026-09-06 (goal session: tie-out-checker follow-up on the gross_profit_identity
        magnitude-bug lead flagged by algo/monitoring/data_patrol/checks/tie_out.py's Round 2
        docstring). Live-confirmed via real SEC companyfacts JSON: ABBV/GILD/AMGN/ABT's only
        "GrossProfit" XBRL facts are a supplementary Q4-only quarterly-data-table stub (e.g.
        ABBV FY2024: start=2024-10-01/end=2024-12-31, a 91-day span) - correctly rejected by
        the annual span_days<330 check in sec_statements_entry_resolution.py, so the CURRENT
        extraction code produces no gross_profit value for these filers at all (confirmed via a
        direct get_income_statement() call: fresh rows have revenue/cost_of_revenue populated,
        no "gross_profit" key). The non-NULL gross_profit already stored for these rows
        (ABBV FY2025: $12.066B, live-identified by the tie-out checker as failing revenue
        ($61.16B) - cost_of_revenue($18.204B) ~= gross_profit by a ~3.6x margin - the real
        implied figure is ~$42.96B) is a leftover from BEFORE that span check existed, silently
        protected ever since by preserve_on_missing_fields' COALESCE. fetch_incremental()
        always refetches a symbol's FULL XBRL history in one company-facts API call (no
        incremental date cutoff), so this run's absence of a gross_profit fact for a fiscal
        year that DOES have fresh revenue/cost_of_revenue is not the kind of transient gap
        preserve_on_missing_fields exists to protect - the concept genuinely produces no usable
        annual value for this filer/year under the current, correct code, so any stored value
        must be stale. Same force-null-bypasses-COALESCE mechanism as
        _reject_implausible_eps/_reject_implausible_shares_outstanding above; post_run()'s
        UPDATE is a no-op for a row where gross_profit is already NULL, so this is safe to run
        unconditionally for every annual income-statement row with fresh revenue and
        cost_of_revenue, not just the 4 symbols found so far. Annual-only (self.period ==
        "annual") - quarterly's own real Q4 GrossProfit fact legitimately has this same ~90-day
        span, so quarterly extraction isn't affected by (or exposed to) this bug.
        """
        if self.period != "annual":
            return
        for row in transformed:
            if row.get("revenue") is None or row.get("cost_of_revenue") is None or row.get("gross_profit") is not None:
                continue
            self._record_explicit_null_rejection(row, "gross_profit", "gross_profit_stale_no_fresh_annual_concept")

    def _reject_implausible_debt_field(self, transformed: list[dict[str, Any]], field: str) -> None:
        """Reject `field` (long_term_debt or short_term_debt) when it exceeds total_assets by
        more than 20x, on the same row - not a tolerance/measurement-noise check like
        algo/monitoring/data_patrol/checks/tie_out.py's own check_long_term_debt_le_total_
        liabilities WARN, but a hard sanity floor: no real operating company carries debt more
        than 20x its own total assets.

        FOUND 2026-09-07 (goal session: live tie-out run against production DB surfaced 62
        annual long_term_debt_le_total_liabilities violations; digging into the worst ones
        found this instead). Live-confirmed via real SEC companyfacts JSON: VGAS (Verde Clean
        Fuels) FY2023 tags us-gaap:ConvertibleDebt=$40,963,000,000 as of 2023-03-31 in a Q1
        2024 10-Q's prior-period comparative column - VGAS's own real total_assets that year
        is ~$31.9M (10-K FY2023, filed 2024-03-28), a company with zero plausible path to
        $40.96B in convertible debt. A DB-wide sweep found 61 similar symbol-years (BGDE:
        $28.1 TRILLION vs $133M assets; AM: $2.89 TRILLION vs $6.28B assets; CTGO: $44.68B vs
        $58.6M assets) - all fallback-only concepts (ConvertibleDebt/OtherLongTermDebt/
        SecuredLongTermDebt/etc., see sec_balance_sheet.py's concept list), all a filer/filing-
        agent XBRL tagging error, not a clean round-multiple scale error (unlike
        `_reject_scale_mismatched_net_income`) - same "impossible under a hard sanity bound"
        signal as `_reject_implausible_gross_profit` above, just for debt-vs-assets instead of
        gross-profit-vs-revenue. NOTE: BGDE/AM were previously one-off DB-patched (memory:
        skm_bgde_am_orphaned_ltd, 2026-09-06) but had already recurred by this session - a
        one-time DB UPDATE doesn't survive the next incremental re-fetch of the same bad SEC
        source fact, so this needs a persistent extraction-time guard, not just another patch.
        20x deliberately leaves room for genuinely highly-levered financials/BDCs/REITs (which
        legitimately run high debt-to-assets) while still rejecting order-of-magnitude filer
        errors.
        """
        if self.statement_type != "balance":
            return
        max_plausible_debt_to_assets_ratio = 20.0
        for row in transformed:
            total_assets = row.get("total_assets")
            value = row.get(field)
            if total_assets is None or total_assets <= 0 or value is None:
                continue
            if float(value) > float(total_assets) * max_plausible_debt_to_assets_ratio:
                logger.warning(
                    f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                    f"{field}={value:,.0f} exceeds {max_plausible_debt_to_assets_ratio:.0f}x "
                    f"total_assets({total_assets:,.0f}) - filer-side XBRL tagging error, not a "
                    "real debt figure. Rejecting rather than storing a confidently-wrong value."
                )
                row[field] = None
                self._record_explicit_null_rejection(row, field, "implausible_debt_vs_total_assets_scale_error")

    def _reject_implausible_goodwill(self, transformed: list[dict[str, Any]]) -> None:
        """Reject `goodwill` when it exceeds `total_assets` on the same row - not a
        tolerance/measurement-noise check like algo/monitoring/data_patrol/checks/tie_out.py's
        own goodwill_le_total_assets WARN, but a hard mathematical impossibility: goodwill is
        one of the line items summed INTO total_assets on a balance sheet, so it can never
        legitimately exceed total_assets, not even slightly - unlike
        `_reject_implausible_debt_field`'s 20x tolerance (real companies can carry debt many
        times their asset base), there is no legitimate multiple here at all.

        FOUND 2026-09-07 (goal session: tie-out score-sanity audit, goodwill_le_total_assets
        live triage). Live-confirmed via real SEC companyfacts JSON, all from the filer's OWN
        real, primary-form (10-K/20-F) filing, not a comparative echo or wrong-period bug in
        this pipeline's extraction: ILLR FY2024 tags Goodwill=$1,005,778,000 against its own
        same-filing Assets=$50,578,000 (a ~20x overstatement); BTCT (foreign private issuer,
        20-F) FY2022 tags Goodwill=$192,962,000 against Assets that never exceed ~$40M in any
        surrounding period; MTC (20-F) tags the identical Goodwill=$108,218,586 across THREE
        straight fiscal years (2023/2024/2025) while Assets is only ~$18.4M - the frozen,
        unchanging-for-3-years figure is itself a signature of a stale/comparative value the
        filer's own XBRL never actually updated. Small tolerance (1.05x) rather than an exact
        0x to allow trivial same-period rounding noise between the two facts' filing contexts,
        not because a real excess is ever legitimate.
        """
        if self.statement_type != "balance":
            return
        max_plausible_goodwill_to_assets_ratio = 1.05
        for row in transformed:
            total_assets = row.get("total_assets")
            goodwill = row.get("goodwill")
            if total_assets is None or total_assets <= 0 or goodwill is None:
                continue
            if float(goodwill) > float(total_assets) * max_plausible_goodwill_to_assets_ratio:
                logger.warning(
                    f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                    f"goodwill={goodwill:,.0f} exceeds total_assets({total_assets:,.0f}) - "
                    "mathematically impossible (goodwill is one of the line items summed into "
                    "total_assets). Filer-side tagging error or stale comparative, not a real "
                    "figure. Rejecting rather than storing a confidently-wrong value."
                )
                row["goodwill"] = None
                self._record_explicit_null_rejection(row, "goodwill", "implausible_goodwill_exceeds_total_assets")

    # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero"/tie-out sweep, gross_profit_
    # identity follow-up to the ABBV/GILD/AMGN/ABT stale-stub fix above): live-confirmed via
    # real SEC companyfacts JSON that Centene (CNC) and Elevance Health (ELV) - both managed-
    # care health insurers, SIC "Hospital & Medical Service Plans" - tag their OWN "GrossProfit"/
    # "CostOfGoodsAndServicesSold" XBRL concepts to a narrow, real sub-calculation (their non-
    # premium service-fee segments only, ~$2.7-21B) that EXCLUDES their dominant cost line -
    # medical claims/benefits expense, tagged separately as PolicyholderBenefitsAndClaims
    # IncurredHealthCare/BenefitsLossesAndExpenses (CNC FY2023 $118.9B, ELV H1'26-annualized
    # ~$193B) - which this pipeline never maps to cost_of_revenue at all. Unlike HCTI's
    # gross_profit bug above (a filing-agent tagging ERROR, not a real number at all), CNC's/
    # ELV's $2.67B/$21.2B "GrossProfit"/"CostOfGoodsAndServicesSold" figures ARE real, filer-
    # reported facts - just not economically comparable to a retailer's gross margin, since they
    # cover only a small slice of the filer's true cost structure. Live-cross-checked their real
    # peers to confirm this is NOT a blanket "insurers are all wrong" issue: MOH/HUM (no
    # GrossProfit tag at all, correctly NULL already) and UNH/CI/CVS (real, meaningful
    # CostOfGoodsAndServicesSold figures for their own genuine PBM/retail-pharmacy product
    # segments, ~50-55% of revenue - a real, comparable cost ratio, not this bug) are unaffected
    # and must NOT be touched by this fix. A curated, individually-verified rejection (same
    # discipline as this file's other symbol-specific overrides) rather than a SIC-wide null,
    # which would incorrectly also blank UNH/CI/CVS's real PBM segment cost data.
    _PARTIAL_SEGMENT_GROSS_PROFIT_MANAGED_CARE_SYMBOLS = frozenset({"CNC", "ELV"})

    def _reject_partial_segment_gross_profit_for_managed_care_insurers(self, transformed: list[dict[str, Any]]) -> None:
        """Force-null gross_profit/cost_of_revenue for the curated managed-care symbols above -
        see that constant's own comment for the live SEC-data verification."""
        if self.statement_type != "income":
            return
        for row in transformed:
            if row.get("symbol") not in self._PARTIAL_SEGMENT_GROSS_PROFIT_MANAGED_CARE_SYMBOLS:
                continue
            for field in ("gross_profit", "cost_of_revenue"):
                if row.get(field) is None:
                    continue
                row[field] = None
                self._record_explicit_null_rejection(row, field, "managed_care_partial_segment_cost_not_total")

    # ADDED 2026-09-07 (goal: stock_scores factor/composite sanity audit + tie-out CI sweep,
    # gross_profit_identity live re-check after the CNC/ELV/TYGO fixes): live-confirmed via
    # real SEC companyfacts JSON that Altria (MO) is the MIRROR IMAGE of CNC/ELV's bug - here
    # `GrossProfit` is the real, complete, filer-tagged total (matches Revenue exactly minus
    # Altria's true cost of sales), but `CostOfGoodsAndServicesSold` is the PARTIAL concept:
    # every single fiscal year 2016-2025 (`data.sec.gov/api/xbrl/companyconcept/
    # CIK0000764180/us-gaap/CostOfGoodsAndServicesSold.json` vs `.../GrossProfit.json` vs
    # `.../RevenueFromContractWithCustomerExcludingAssessedTax.json`), Revenue - COGS !=
    # GrossProfit by a large, growing margin (FY2025: $23.279B - $5.597B = $17.682B tagged-
    # COGS-implied gross profit vs. the real, filer-tagged GrossProfit of only $14.542B - a
    # $3.14B gap, this pipeline's own `gross_profit_identity` tie-out check's residual).
    # Peer-checked to confirm this is Altria-specific, NOT a tobacco/excise-tax-industry-wide
    # pattern: Philip Morris International (PM, CIK 0001413329) reconciles EXACTLY for the
    # same FY2025 period ($40.648B revenue - $13.366B COGS = $27.282B GrossProfit, to the
    # dollar) - a real, comparable filer in the same industry with the identical excise-tax-
    # exclusion revenue concept shows no such gap, ruling out an industry-wide accounting
    # convention as the explanation. Curated single-symbol rejection (same discipline as
    # _PARTIAL_SEGMENT_GROSS_PROFIT_MANAGED_CARE_SYMBOLS above) - only cost_of_revenue is
    # nulled here, NOT gross_profit, since GrossProfit is the reliable, complete figure in
    # this case (opposite of CNC/ELV, where GrossProfit itself was the partial concept).
    #
    # ADDED 2026-09-07 (same goal session, gross_profit_identity live triage continuation,
    # batch 21-45 by residual): ZIM Integrated Shipping (ZIM, CIK 0001654126, a container-
    # shipping line filing 20-F under IFRS) - live-confirmed via real SEC companyfacts JSON:
    # ifrs-full "RevenueFromContractsWithCustomers" ($6.9042B FY2025) - "CostOfSales"
    # ($4.4608B) implies a $2.4434B gross profit (35.4% margin), but the real, filer-tagged
    # "GrossProfit" is only $1.3209B (19.1% margin) - a $1.1225B gap, exactly this pipeline's
    # own gross_profit_identity residual. Unlike TTEK/TAP (a single missing additive concept
    # that reconciles the gap exactly - see _fill_cost_of_revenue_from_other_operating_cost()),
    # an exhaustive scan of every ifrs-full concept for this exact fiscal-year period found NO
    # single concept matching the $1.1225B gap (TransportationExpense $2.1021B and FuelExpense
    # $1.1467B are both real, large, separately-tagged shipping-specific cost lines, but neither
    # alone nor their sum closes the gap exactly) - ruling out the clean-sum pattern. The lower,
    # real GrossProfit figure is corroborated as the reliable one: GrossProfit ($1.3209B) -
    # ProfitLossFromOperatingActivities ($1.016B) = $304.9M, a plausible SG&A-scale residual,
    # while CostOfSales's implied 35.4% gross margin is implausibly high for bulk container
    # shipping's well-known thin-margin economics. No good SEC-registered direct peer exists
    # (most major container lines - Maersk, COSCO, CMA CGM, Hapag-Lloyd - aren't SEC-listed) so
    # this is verified via internal consistency (the operating-income cross-check above) rather
    # than a peer comparison, same as this constant's original MO entry when it predated the PM
    # peer-check precedent.
    _PARTIAL_COST_OF_REVENUE_SYMBOLS = frozenset({"MO", "ZIM"})

    def _reject_partial_cost_of_revenue(self, transformed: list[dict[str, Any]]) -> None:
        """Force-null cost_of_revenue (keeping gross_profit) for the curated symbols above -
        see that constant's own comment for the live SEC-data verification."""
        if self.statement_type != "income":
            return
        for row in transformed:
            if row.get("symbol") not in self._PARTIAL_COST_OF_REVENUE_SYMBOLS:
                continue
            if row.get("cost_of_revenue") is None:
                continue
            row["cost_of_revenue"] = None
            self._record_explicit_null_rejection(row, "cost_of_revenue", "cost_of_revenue_partial_concept_not_total")

    def _reject_scale_mismatched_revenue(self, transformed: list[dict[str, Any]]) -> None:
        """Reject `revenue` when it's a clean power-of-10 multiple (100x/1000x/10000x, within
        1%) of (cost_of_revenue + gross_profit) - the same magic-ratio detection already
        proven safe in sec_statements_entry_resolution.py's frame_magnitude_scale_guard (the
        IPAR fix), applied to this pipeline's own concept-priority chain instead of SEC's
        frame-preference tiebreak.

        FOUND 2026-09-06 (goal: score/tie-out sanity audit, gross_profit_identity's current
        top-flagged-by-magnitude non-CNC/ELV offender). Live-confirmed via TYGO's (Tigo
        Energy) real SEC companyfacts JSON: the filer's OWN XBRL genuinely mistags
        RevenueFromContractWithCustomerExcludingAssessedTax at exactly 1000x the correct value
        for every single fiscal year on record (2022: $81.323B tagged vs. $81.323M real;
        2023/2024/2025 same shape) - NOT an extraction-side wrong-context bug like the tie-out
        checker's other gross_profit_identity leads (CNC/ELV, ABBV/GILD/AMGN/ABT): TYGO's own
        "Revenues" concept for the identical periods is correctly tagged every time, and
        _INCOME_FIELD_MAPPING's documented "ExcludingAssessedTax must win when both are
        present" priority (correct for the overwhelming majority of filers, where
        ExcludingAssessedTax is the more precise net-revenue figure) picks the corrupted one
        for this filer specifically. cost_of_revenue/gross_profit are unaffected (both come
        from separate, correctly-tagged concepts), so their sum is the independent, trustworthy
        anchor to validate revenue against - exactly the same role gross_profit_identity's
        `implied_gross_profit` plays in algo/monitoring/data_patrol/checks/tie_out.py, just run
        pre-storage instead of as a post-hoc read-only WARN. DB-wide live scan confirmed this
        exact 1000x pattern currently affects only TYGO (4 rows total, all its own fiscal
        years) - not a systemic bug, so this guard is expected to fire rarely; a legitimate
        filer's revenue vs. cost_of_revenue+gross_profit will essentially never land within 1%
        of an exact power of 10 by chance.
        """
        for row in transformed:
            revenue = row.get("revenue")
            cost_of_revenue = row.get("cost_of_revenue")
            gross_profit = row.get("gross_profit")
            if revenue is None or cost_of_revenue is None or gross_profit is None:
                continue
            implied_revenue = float(cost_of_revenue) + float(gross_profit)
            if implied_revenue == 0 or revenue == 0:
                continue
            ratio = abs(float(revenue)) / abs(implied_revenue)
            if ratio < 1:
                ratio = 1 / ratio
            if any(abs(ratio - power) / power < 0.01 for power in (100, 1000, 10000)):
                logger.warning(
                    f"[{self.table_name}] {row.get('symbol')} FY{row.get('fiscal_year')}: "
                    f"revenue={revenue:,.0f} is a {ratio:.0f}x-scaled outlier vs. "
                    f"cost_of_revenue+gross_profit={implied_revenue:,.0f} - likely a filer-side "
                    "XBRL tagging error on the higher-priority revenue concept, not a real "
                    "business figure. Rejecting rather than storing a confidently-wrong value."
                )
                row["revenue"] = None
                self._record_explicit_null_rejection(row, "revenue", "revenue_scale_mismatch_vs_cogs_plus_gp")
