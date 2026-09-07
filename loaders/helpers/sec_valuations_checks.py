"""Live yfinance cross-checks, plausibility sanity checks, and the data-unavailable-marker
builder for SecValuationsLoader, extracted from load_sec_valuations.py (2026-09-05,
file-size ratchet: that file is one of the Tier-1 bloaters flagged for decomposition).
Methods are verbatim, no logic changed - mixed into SecValuationsLoader.
"""

import logging
from datetime import date, timedelta
from itertools import pairwise
from typing import Any

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class ValuationSanityCheckMixin:
    """yfinance live cross-check fetches, market-cap/PE plausibility sanity checks, and the
    data_unavailable marker builder for SecValuationsLoader. Not usable standalone.

    `_sanity_check_market_cap` reads DUAL_CLASS_YFINANCE_COMBINED_MARKET_CAP_SYMBOLS via a
    LOCAL (in-method) `import loaders.load_sec_valuations as _lsv`, not a module-level one,
    because load_sec_valuations.py imports THIS module before that module-level constant is
    defined further down in its own source. FIXED 2026-09-05 (goal session: "implausible
    values" sweep) - a module-level `import loaders.load_sec_valuations as _lsv` at the top of
    this file still crashed at IMPORT time with "cannot import name 'ValuationSanityCheckMixin'
    from partially initialized module" (a true circular import, not just a deferred-attribute-
    access problem) whenever this module was imported before load_sec_valuations.py already had
    a head start (e.g. `python loaders/load_sec_valuations.py` / `python -m
    loaders.load_sec_valuations`, both broken since this file's creation at `5e306dab3`, per
    local reproduction of the scheduler's exact `python loaders/load_sec_valuations.py`
    invocation) - the `import` statement itself, not just the attribute access, needed to be
    deferred until the method actually runs, by which point load_sec_valuations.py has finished
    executing and is present in sys.modules under its real name.
    """

    def _fetch_live_fpi_yfinance_check_values(self, symbol: str) -> tuple[float | None, float | None]:
        """Live market_cap/trailingPE for a foreign private issuer, for sanity-check use only.

        Never a value source for pe_ratio/market_cap themselves (those stay 100% SEC-derived
        per this file's module docstring) - only used to validate/reject an already-computed
        SEC-derived value. Fails open (returns None, None) on any fetch error: a sanity check
        that can't run is not itself a reason to block valuation output. Uses the same shared
        cross-ECS-task IP circuit breaker as utils/external/yfinance_financials.py/
        yfinance_analyst_ratings.py (this loader can run for thousands of symbols across a
        full pipeline run, same coordination requirement as those callers).
        """
        try:
            from utils.external.yfinance_analyst_ratings import _get_module_worker
            from utils.external.yfinance_circuit_breaker import (
                YFinanceStillBannedError,
                get_circuit_breaker,
            )
            from utils.external.yfinance_symbol import to_yfinance_symbol

            circuit_breaker = get_circuit_breaker()
            try:
                circuit_breaker.wait_or_raise()
            except YFinanceStillBannedError as e:
                logger.debug(f"[{symbol}] yfinance shared IP ban active, skipping FPI sanity-check fetch: {e}")
                return None, None

            # FIXED 2026-08-29: fetches via the shared _YfinanceAttrProcessWorker (see
            # utils/external/yfinance_analyst_ratings.py) rather than an in-process
            # yf.Ticker(...).info call wrapped in socket.setdefaulttimeout() - that timeout
            # has no effect on a curl_cffi hang (yfinance 0.2.40+ requires curl_cffi, not
            # built on Python's socket module) - same root cause fixed at 4 other call
            # sites this session. A TimeoutError from the worker is caught by the generic
            # except below like any other fetch failure - this function already fails
            # open on any error, so no special-casing needed.
            info = _get_module_worker().fetch(to_yfinance_symbol(symbol), "info", timeout_seconds=10.0)
        except Exception as e:
            error_str = str(e).lower()
            if any(kw in error_str for kw in ("429", "rate", "too many", "invalid crumb", "unauthorized")):
                try:
                    get_circuit_breaker().report_rate_limit_error()
                except Exception:
                    pass
            logger.debug(f"[{symbol}] Live FPI yfinance sanity-check fetch failed (non-fatal): {e}")
            return None, None

        try:
            get_circuit_breaker().report_success()
        except Exception:
            pass
        if not isinstance(info, dict):
            return None, None
        mcap = info.get("marketCap")
        pe = info.get("trailingPE")
        yf_market_cap = float(mcap) if isinstance(mcap, (int, float)) and mcap > 0 else None
        yf_pe_ratio = float(pe) if isinstance(pe, (int, float)) and pe > 0 else None
        return yf_market_cap, yf_pe_ratio

    # ADDED 2026-08-22 (goal session - real-money-readiness audit): the one narrow, deliberate
    # exception to this file's "SEC data only, yfinance never a value source" rule - see the
    # call site's comment (in _resolve_shares_outstanding-equivalent block above) and
    # dual_class_primary_ticker_shares_outstanding_structural_gap_found_20260822 in memory for
    # the full justification (SEC's companyfacts API structurally cannot carry per-share-class
    # data for a true dual-class filer - live-verified against BRK.A/BRK.B).
    def _fetch_live_dual_class_shares_outstanding(self, symbol: str) -> float | None:
        """Live per-ticker shares_outstanding for a dual-class sibling, from yfinance.

        ONLY called when has_dual_class_sibling=True and every SEC-derived tier above has
        already failed - never a substitute for a real SEC value when one exists. yfinance
        queries per-LISTING (ticker), not per-company like SEC's companyfacts API, so it
        naturally resolves the correct class-specific count. Fails open (returns None) on any
        fetch error, same as _fetch_live_fpi_yfinance_check_values above - a fetch failure here
        just means this symbol stays data_unavailable, not a reason to block the whole run.
        """
        try:
            from utils.external.yfinance_analyst_ratings import _get_module_worker
            from utils.external.yfinance_circuit_breaker import (
                YFinanceStillBannedError,
                get_circuit_breaker,
            )
            from utils.external.yfinance_symbol import to_yfinance_symbol

            circuit_breaker = get_circuit_breaker()
            try:
                circuit_breaker.wait_or_raise()
            except YFinanceStillBannedError as e:
                logger.debug(f"[{symbol}] yfinance shared IP ban active, skipping dual-class shares fetch: {e}")
                return None

            # FIXED 2026-08-29: see _fetch_live_fpi_yfinance_check_values's identical fix
            # above for why the process-isolated worker replaces socket.setdefaulttimeout().
            info = _get_module_worker().fetch(to_yfinance_symbol(symbol), "info", timeout_seconds=10.0)
        except Exception as e:
            error_str = str(e).lower()
            if any(kw in error_str for kw in ("429", "rate", "too many", "invalid crumb", "unauthorized")):
                try:
                    get_circuit_breaker().report_rate_limit_error()
                except Exception:
                    pass
            logger.debug(f"[{symbol}] Live dual-class yfinance shares fetch failed (non-fatal): {e}")
            return None

        try:
            get_circuit_breaker().report_success()
        except Exception:
            pass
        if not isinstance(info, dict):
            return None
        shares = info.get("sharesOutstanding")
        return float(shares) if isinstance(shares, (int, float)) and shares > 0 else None

    # ADDED 2026-08-27 (goal: recover the market_cap data gap - 768 foreign private issuer
    # symbols with market_cap=NULL, 99% still actively tradable). Third narrow exception to
    # this file's "SEC data only" rule - see the call site's comment above for the full
    # justification (SEC's 20-F/companyfacts data structurally lacks a usable US-GAAP shares
    # tag for most FPIs, the same class of gap as dual-class shares just above).
    def _fetch_live_fpi_shares_outstanding_yfinance(self, symbol: str) -> float | None:
        """Live per-ticker shares_outstanding for a foreign private issuer, from yfinance.

        ONLY called when is_foreign_private_issuer=True and every SEC-derived tier above has
        already failed - never a substitute for a real SEC value when one exists. yfinance
        queries per-LISTING (the ADS ticker), so its sharesOutstanding is already on the
        correct ADS/USD basis, avoiding the home-market-units mismatch every SEC-sourced tier
        above is gated off to avoid. Fails open (returns None) on any fetch error, same as
        _fetch_live_dual_class_shares_outstanding/_fetch_live_fpi_yfinance_check_values above -
        a fetch failure here just means this symbol stays data_unavailable, not a reason to
        block the whole run.
        """
        try:
            from utils.external.yfinance_analyst_ratings import _get_module_worker
            from utils.external.yfinance_circuit_breaker import (
                YFinanceStillBannedError,
                get_circuit_breaker,
            )
            from utils.external.yfinance_symbol import to_yfinance_symbol

            circuit_breaker = get_circuit_breaker()
            try:
                circuit_breaker.wait_or_raise()
            except YFinanceStillBannedError as e:
                logger.debug(f"[{symbol}] yfinance shared IP ban active, skipping FPI shares fetch: {e}")
                return None

            # FIXED 2026-08-29: see _fetch_live_fpi_yfinance_check_values's identical fix
            # above for why the process-isolated worker replaces socket.setdefaulttimeout().
            info = _get_module_worker().fetch(to_yfinance_symbol(symbol), "info", timeout_seconds=10.0)
        except Exception as e:
            error_str = str(e).lower()
            if any(kw in error_str for kw in ("429", "rate", "too many", "invalid crumb", "unauthorized")):
                try:
                    get_circuit_breaker().report_rate_limit_error()
                except Exception:
                    pass
            logger.debug(f"[{symbol}] Live FPI yfinance shares fetch failed (non-fatal): {e}")
            return None

        try:
            get_circuit_breaker().report_success()
        except Exception:
            pass
        if not isinstance(info, dict):
            return None
        shares = info.get("sharesOutstanding")
        return float(shares) if isinstance(shares, (int, float)) and shares > 0 else None

    # FIXED 2026-08-20 (goal: finance-accuracy audit): shares_outstanding can be wrong by a
    # factor neither the plausibility ceiling nor the company_info_sec cross-check (both
    # earlier in this file) catches - both can independently derive from the SAME
    # underlying mis-scaled SEC concept and agree with each other while both being wrong.
    # Live-confirmed: ONC (BeOne Medicines) computed market_cap=$534.3B here, while
    # company_info_sec's shares_outstanding (1.478B) agreed with the SEC-derived value
    # (1.418B) within the existing 20x cross-check tolerance - both sourced from the same
    # mis-scaled concept. yfinance_snapshot.market_cap (a genuinely independent,
    # differently-sourced figure) shows ONC's real market cap is ~$31.0B - a 17x gap. A
    # DB-wide scan found 92 symbols with a >10x mismatch against yfinance_snapshot.market_cap
    # (up to 792x for MTLS). This file's own module docstring is explicit that yfinance must
    # never be a VALUE source here ("No fallback to yfinance (SEC data only)"), so this only
    # uses it as a validity check: a >10x disagreement nulls every field that depends on
    # shares_outstanding (market_cap, pb_ratio, ps_ratio, fcf_yield, dividend_yield,
    # net_payout_yield (ADDED 2026-08-26 - same entity_market_cap denominator as
    # dividend_yield, same exposure to this bug), enterprise_value, ev_ebitda, ev_revenue,
    # intrinsic_value_per_share, margin_of_safety_pct) rather than presenting a number now
    # positively known to likely be
    # wrong - pe_ratio/peg_ratio are untouched since they don't depend on shares_outstanding
    # at all. 10x (not the shares-cross-check's 20x) because this is comparing two fully
    # independent extraction pipelines, not two paths that can share a root cause - a real,
    # non-buggy 10x+ gap between SEC-audited and yfinance market cap would itself be a strong
    # sign of stale/wrong data on one side, worth losing the metric over.
    def _sanity_check_market_cap(
        self, symbol: str, result: dict[str, Any], yf_market_cap: float | None, yf_market_cap_is_live: bool = False
    ) -> None:
        market_cap = result.get("market_cap")
        if market_cap is None or market_cap <= 0:
            return
        if yf_market_cap is None:
            return
        # FIXED 2026-09-03 (goal session continuation, KELYB-discovered): for a thin sibling
        # class of a multi-class ticker family, yfinance's market_cap/sharesOutstanding
        # reflects the COMBINED-entity share count (shared across every class' ticker symbol
        # by the data vendor) rather than that specific class' own float - live-confirmed both
        # via the frozen yfinance_snapshot table AND a fresh live re-fetch (both agree, so this
        # is NOT the staleness case the live-refetch fallback below already handles).
        # Live-confirmed: KELYB's own SEC-derived market_cap ($76.7M, 3,295,941 real Class B
        # shares per company_info_sec x price) vs yfinance's $808M-830M for the SAME ticker -
        # but company_info_sec's own class-specific counts sum correctly across siblings
        # (KELYA 30,915,587 + KELYB 3,295,941 = 34,211,528, matching Kelly Services' real
        # combined ~34.6M shares outstanding per public filings) - confirming our class-
        # specific number is the correct one and yfinance's is the combined-entity total
        # mislabeled per-class. Same pattern for LBTYB (LBTYA+LBTYB+LBTYK sums to 335.0M vs the
        # combined DB total of 337.9M, within 0.9%). Registry restricted to individually
        # confirmed thin-class tickers only - do NOT add a symbol here without the same
        # sibling-sum cross-check; a genuinely mis-scaled shares_outstanding bug (this check's
        # real purpose, e.g. the already-fixed ONC case) would NOT sum correctly with its
        # siblings this cleanly.
        import loaders.load_sec_valuations as _lsv

        if symbol in _lsv.DUAL_CLASS_YFINANCE_COMBINED_MARKET_CAP_SYMBOLS:
            return
        ratio = max(market_cap, yf_market_cap) / min(market_cap, yf_market_cap)
        if ratio <= 10:
            return
        # FIXED 2026-08-31 (goal: data-coverage sweep): yf_market_cap here almost always comes
        # from the yfinance_snapshot table read at the top of fetch_incremental, which has had
        # NO active writer since Session 275 (see that read's own comment) - live-confirmed
        # 100% of its 4,683 rows are frozen at 2026-07-04/07-12, 7-8 weeks stale as of this fix.
        # A >10x disagreement against an 8-week-old number is exactly what normal price
        # movement produces for any volatile small/mid-cap - NOT evidence of a mis-scaled
        # shares_outstanding. Live-confirmed via AMRN: SEC-derived market_cap=$5.86B (price
        # $13.97 x 419.5M shares, both independently correct) was rejected against the frozen
        # table's $312M (implying $0.74/share, nowhere near the real price) - AMRN's real
        # market cap is ~$6.00B per live external quotes, i.e. the SEC-derived value was right
        # and the frozen table was wrong. This hit 66 active symbols (FUBO, GENI and other
        # real, liquid names among them, not just illiquid micro-caps). Before finalizing a
        # rejection on a *stale* comparison value, get one live number and re-check against
        # that instead - bounded to only the ~rejection-path symbols (not the whole universe)
        # so this doesn't multiply live-fetch volume on a full run. yf_market_cap_is_live=True
        # (FPI / >$50B-ceiling tiers) means this IS already a live number - no help there,
        # already the best signal available; keep it as-is and reject as before.
        if not yf_market_cap_is_live:
            live_mcap, _live_pe = self._fetch_live_fpi_yfinance_check_values(symbol)
            if live_mcap is not None:
                yf_market_cap = live_mcap
                ratio = max(market_cap, yf_market_cap) / min(market_cap, yf_market_cap)
                if ratio <= 10:
                    return
        logger.warning(
            f"[{symbol}] market_cap sanity check failed: SEC-derived=${market_cap:,.0f} vs "
            f"yfinance=${yf_market_cap:,.0f} (ratio {ratio:.0f}x) - shares_outstanding is "
            f"likely mis-scaled; nulling shares_outstanding-dependent fields"
        )
        for field in (
            "market_cap",
            "pb_ratio",
            "ps_ratio",
            "fcf_yield",
            "dividend_yield",
            "net_payout_yield",
            "enterprise_value",
            "ev_ebitda",
            "ev_revenue",
            "intrinsic_value_per_share",
            "margin_of_safety_pct",
        ):
            result[field] = None
        if result.get("reason") is None:
            result["reason"] = "shares_outstanding_scale_mismatch"
        # Mirror _compute_valuations' own "all key metrics null" consistency check (it already
        # ran once before this nulling and may have passed on a metric this method just
        # cleared) - re-evaluate so a row that's now genuinely all-NULL is correctly flagged
        # data_unavailable instead of silently claiming success with nothing but a symbol/price.
        key_metrics = [result.get("pe_ratio"), result.get("pb_ratio"), result.get("ps_ratio"), result.get("fcf_yield")]
        if all(m is None for m in key_metrics):
            result["data_unavailable"] = True

    # FIXED 2026-08-20 (goal: finance-accuracy audit, ONC follow-up): pe_ratio doesn't depend
    # on shares_outstanding (current_price / ttm_eps only), so _sanity_check_market_cap above
    # correctly leaves it untouched - but that also means a separately-mis-scaled ttm_eps
    # (a different SEC concept, same underlying class of per-filing XBRL scale bug) survives
    # completely unguarded. Live-confirmed: ONC (BeOne Medicines) still shows pe_ratio=1884.30
    # after the market_cap fix, vs yfinance's pe_ratio=67.58 for the same company - a ~28x
    # gap. A DB-wide scan found 38 symbols with a >10x pe_ratio mismatch against
    # yfinance_snapshot.pe_ratio. Same validity-check-only discipline as market_cap (never a
    # yfinance value substitution - see that method's docstring): nulls pe_ratio and its
    # sole dependent, peg_ratio, on a >10x disagreement.
    def _sanity_check_pe_ratio(
        self, symbol: str, result: dict[str, Any], yf_pe_ratio: float | None, yf_value_is_live: bool = False
    ) -> None:
        pe_ratio = result.get("pe_ratio")
        if pe_ratio is None or pe_ratio <= 0:
            return
        if yf_pe_ratio is None:
            return
        ratio = max(pe_ratio, yf_pe_ratio) / min(pe_ratio, yf_pe_ratio)
        if ratio <= 10:
            return
        # FIXED 2026-08-31 (goal: data-coverage sweep) - same frozen-yfinance_snapshot false-
        # positive fixed in _sanity_check_market_cap above (see that method's comment for the
        # full 66-symbol/AMRN evidence): pe_ratio moves with price just like market_cap does,
        # so an 7-8-week-stale comparison value is just as unreliable here. One bounded live
        # re-check before committing to a rejection.
        if not yf_value_is_live:
            _live_mcap, live_pe = self._fetch_live_fpi_yfinance_check_values(symbol)
            if live_pe is not None:
                yf_pe_ratio = live_pe
                ratio = max(pe_ratio, yf_pe_ratio) / min(pe_ratio, yf_pe_ratio)
                if ratio <= 10:
                    return
        # FIXED 2026-09-05 (goal session: "get SEC/XBRL missing data to zero" campaign,
        # eps_scale_mismatch refinement - see
        # eps_scale_mismatch_mostly_stale_annual_vs_live_ttm_not_true_scale_bug_20260905 in
        # memory): most rejections here are NOT a genuine XBRL scale-tagging bug - `pe_ratio`
        # is computed from `ttm_eps_basic`, which despite its name is just the latest ANNUAL
        # EPS (see load_sec_valuations.py's own "ttm_eps_basic" naming), while `yf_pe_ratio`
        # is a real rolling trailing-twelve-month figure. For a symbol whose earnings moved a
        # lot since that stale annual period, comparing a stale-annual-EPS PE against a live
        # TTM PE produces a large, real divergence with NO scale-tagging error involved - a
        # measurement-window mismatch, not a mis-scaled fact. A prior investigation into this
        # concluded a genuine TTM-from-quarters rescue wasn't feasible because it checked the
        # wrong column (`quarterly_income_statement.eps`, which is dead - never a mapping
        # target, 0/186099 rows populated); the real column, `earnings_per_share`, is 95%
        # populated. If the trailing 4 real quarters (by `period_end`, not the fiscal_year/
        # fiscal_quarter pair alone - see migration 1256's non-December-fiscal-year-end
        # ordering fix) are present, recent, and sum to a genuine trailing-twelve-month EPS
        # that reconciles with yfinance's live TTM PE, this was never a scale bug - keep the
        # original SEC-derived pe_ratio/peg_ratio rather than nulling them (does NOT replace
        # pe_ratio with the quarterly-derived figure - peg_ratio's growth-rate calculation
        # upstream already assumes pe_ratio came from the annual-EPS path, so swapping the
        # value here would silently desync the two; this only rescues the sanity check itself).
        ttm_eps_from_quarters = self._compute_ttm_eps_from_quarters(symbol)
        if ttm_eps_from_quarters is not None and ttm_eps_from_quarters > 0:
            current_price = result.get("current_price")
            if current_price is not None and current_price > 0:
                pe_from_quarters = current_price / ttm_eps_from_quarters
                ratio = max(pe_from_quarters, yf_pe_ratio) / min(pe_from_quarters, yf_pe_ratio)
                if ratio <= 10:
                    logger.info(
                        f"[{symbol}] pe_ratio sanity check false positive avoided: annual-EPS-"
                        f"based PE={pe_ratio:.2f} vs yfinance={yf_pe_ratio:.2f} diverged, but a "
                        f"true trailing-4-quarter EPS reconciles (PE={pe_from_quarters:.2f}) - "
                        f"keeping original SEC-derived pe_ratio/peg_ratio (measurement-window "
                        f"mismatch, not a scale bug)"
                    )
                    return
        logger.warning(
            f"[{symbol}] pe_ratio sanity check failed: SEC-derived={pe_ratio:.2f} vs "
            f"yfinance={yf_pe_ratio:.2f} (ratio {ratio:.0f}x) - ttm_eps is likely mis-scaled; "
            f"nulling pe_ratio/peg_ratio"
        )
        result["pe_ratio"] = None
        result["peg_ratio"] = None
        if result.get("reason") is None:
            result["reason"] = "eps_scale_mismatch"
        key_metrics = [result.get("pe_ratio"), result.get("pb_ratio"), result.get("ps_ratio"), result.get("fcf_yield")]
        if all(m is None for m in key_metrics):
            result["data_unavailable"] = True

    def _compute_ttm_eps_from_quarters(self, symbol: str) -> float | None:
        """Sum of the 4 most recent real quarterly `earnings_per_share` values, ordered by
        actual `period_end` date (not the fiscal_year/fiscal_quarter pair - see migration
        1256's non-December-fiscal-year-end ordering fix elsewhere in this codebase for why
        that pair alone doesn't give true chronological order for every filer).

        Returns None (not a partial/best-effort sum) unless all 4 most recent quarters are
        present with a real value AND the most recent one is within ~400 days (a normal
        annual reporting cadence plus slack for late filers) - a genuine TTM figure needs all
        4 real quarters, and a stale set of "recent" quarters would just reintroduce the same
        stale-vs-live measurement-window problem this exists to fix.
        """
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT period_end, earnings_per_share
                FROM quarterly_income_statement
                WHERE symbol = %s AND data_unavailable IS NOT TRUE AND period_end IS NOT NULL
                ORDER BY period_end DESC
                LIMIT 4
                """,
                (symbol,),
            )
            rows = cur.fetchall()
        if len(rows) != 4:
            return None
        most_recent_period_end = rows[0][0]
        if most_recent_period_end is None or (date.today() - most_recent_period_end) > timedelta(days=400):
            return None
        if any(r[1] is None for r in rows):
            return None
        # Guard against a restated/duplicate-filing row for one quarter masking a missing
        # quarter elsewhere: "4 most recent rows by period_end" is only a true TTM sum if
        # those 4 period_ends are 4 distinct quarters spaced ~91 days apart, not two rows
        # for the same reporting period plus a gap where a real quarter was never loaded.
        period_ends = [r[0] for r in rows]
        if len(set(period_ends)) != 4:
            return None
        for earlier, later in pairwise(period_ends):
            gap_days = (earlier - later).days
            if not (60 <= gap_days <= 120):
                return None
        return float(sum(r[1] for r in rows))

    def _get_total_cash_and_debt(self, cur: Any, symbol: str) -> tuple[float | None, float | None]:
        """Pure balance-sheet total_cash/total_debt lookup - no income-statement dependency,
        so callable even before annual_income_statement has any usable row.

        FIXED 2026-09-02 (goal: "get all the data we need" full-coverage audit): extracted
        from fetch_incremental's main flow so the "no_income_statement" early-return
        (immediately below the income_rows fetch) can reuse these exact same queries instead
        of losing both pure balance-sheet facts to an accidental control-flow gap - live-
        confirmed AADX has a real, current, non-flagged cash_and_equivalents ($18.1M FY2026)
        but zero usable annual_income_statement rows, so total_cash/total_debt were nulled out
        purely because the "no income statement" exit ran first, not because the balance-sheet
        data was actually missing. Same "these two don't need X" principle the 2026-08-19
        total_debt/total_cash/ebitda-before-every-gate fix already established for the
        shares_outstanding/price gates below (see fetch_incremental's own "MOVED 2026-08-19"
        comment) - this closes the identical gap at the one gate that fix's own docstring
        explicitly (and, it turns out, incorrectly) assumed had "no balance-sheet query even
        run yet". ebitda is NOT included here - it genuinely needs operating_income/
        depreciation/amortization from the income statement, so it correctly stays NULL when
        income_rows is empty.
        """
        # FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep,
        # total_cash "missing_sec_data" investigation): the ORDER BY below used to only
        # distinguish NULL from non-NULL, treating an explicit 0 the same as a real
        # positive balance - live-confirmed via AM (Antero Midstream, $10.8B mkt cap) and
        # AR (Antero Resources, $12.3B): each has a real, current, non-flagged
        # cash_and_equivalents=$180,435,000/$210,000,000 for its most recent completed
        # fiscal year, but a NEWER (partial/interim-derived) fiscal_year row exists with
        # cash_and_equivalents=0 (while that same row's total_assets/current_liabilities/
        # etc are real, non-zero - not a stub row, just missing this one field for the
        # most recent period) - the plain "fiscal_year DESC, prefer non-NULL" ordering
        # picked that $0 row over the real $180M/$210M one, exactly the "current-year stub
        # clobbers a real prior value" bug class already fixed elsewhere this session (see
        # the AMZN 10-Q TTM stub-row fix). DB-wide scan found 12 symbols with this exact
        # shape (most recent fiscal_year row has cash=0 while an earlier one has a real
        # non-zero value): AKTX/AM/AR/BGR/CDIO/INDO/LEGO/MAIA/NGS/ROC/SOAR/VLOS. Same
        # non-NULL-vs-real-nonzero tiering the debt query just below already uses (that one
        # was correct from the start) - preferring a real nonzero balance over a same-or-
        # later-year explicit zero, but still falling back to a genuine zero (a company
        # that really holds no cash, which does happen) when no nonzero year exists at all.
        cur.execute(
            """
            SELECT cash_and_equivalents
            FROM annual_balance_sheet
            WHERE symbol = %s AND fiscal_year IS NOT NULL AND data_unavailable IS NOT TRUE
            ORDER BY (CASE
                        WHEN cash_and_equivalents IS NOT NULL AND cash_and_equivalents != 0
                        THEN 0
                        WHEN cash_and_equivalents IS NOT NULL
                        THEN 1
                        ELSE 2
                      END), fiscal_year DESC
            LIMIT 1
            """,
            (symbol,),
        )
        cash_row2 = cur.fetchone()
        total_cash = cash_row2[0] if cash_row2 else None

        cur.execute(
            """
            SELECT
                long_term_debt,
                short_term_debt,
                operating_lease_liability,
                finance_lease_liability
            FROM annual_balance_sheet
            WHERE symbol = %s AND fiscal_year IS NOT NULL AND data_unavailable IS NOT TRUE
            ORDER BY (CASE
                        WHEN long_term_debt IS NOT NULL
                        THEN 0
                        WHEN COALESCE(long_term_debt, 0) + COALESCE(short_term_debt, 0)
                             + COALESCE(operating_lease_liability, 0)
                             + COALESCE(finance_lease_liability, 0) != 0
                        THEN 1
                        WHEN long_term_debt IS NOT NULL OR short_term_debt IS NOT NULL
                             OR operating_lease_liability IS NOT NULL
                             OR finance_lease_liability IS NOT NULL
                        THEN 2
                        ELSE 3
                      END), fiscal_year DESC
            LIMIT 1
            """,
            (symbol,),
        )
        debt_row = cur.fetchone()
        if debt_row:
            debt_components = debt_row
            total_debt = None if all(c is None for c in debt_components) else sum(c or 0 for c in debt_components)
        else:
            total_debt = None

        return total_cash, total_debt

    def _get_market_cap_without_income_statement(
        self, cur: Any, symbol: str
    ) -> tuple[float | None, float | None, float | None]:
        """Pure price * shares_outstanding lookup - no income-statement dependency, so
        callable even before annual_income_statement has any usable row.

        FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, sibling to
        _get_total_cash_and_debt's 2026-09-02 fix): market_cap only needs a live price
        (price_daily) and a share count (company_info_sec.shares_outstanding - the same
        tier _resolve_shares_outstanding itself falls back to when the income-statement
        tiers are unavailable) - neither depends on annual_income_statement having any
        rows. Live-confirmed 19/22 symbols hitting the "no_income_statement" early return
        (AADX, DPC, SIND, PBLS, ADBT, ADIG, BSEM, AIB, KARD, AVEX, SSMR, CSQR, LFTO, FCBM,
        HMH, LCLN, LIME, SECZ, SUJA) have a real, current (2026-09-04) price_daily row and
        a real company_info_sec.shares_outstanding, both nulled out purely because this
        early return ran before fetch_incremental ever reached its own price/shares_out
        queries - the exact same "these fields don't need X" gap total_cash/total_debt
        already had fixed here.

        Returns (current_price, shares_outstanding, market_cap) - any/all None when either
        input is missing (a company_info_sec shares_outstanding_unavailable_reason, no
        recent price_daily row, etc.).
        """
        cur.execute(
            """
            SELECT close FROM price_daily
            WHERE symbol = %s AND close IS NOT NULL AND close > 0
            ORDER BY date DESC LIMIT 1
            """,
            (symbol,),
        )
        price_row = cur.fetchone()
        current_price = float(price_row[0]) if price_row and price_row[0] else None

        cur.execute(
            "SELECT shares_outstanding FROM company_info_sec WHERE symbol = %s AND shares_outstanding IS NOT NULL AND shares_outstanding > 0",
            (symbol,),
        )
        shares_row = cur.fetchone()
        shares_outstanding = float(shares_row[0]) if shares_row else None

        market_cap = current_price * shares_outstanding if current_price and shares_outstanding else None
        return current_price, shares_outstanding, market_cap

    def _unavailable_marker(
        self,
        symbol: str,
        reason: str,
        total_debt: float | None = None,
        total_cash: float | None = None,
        ebitda: float | None = None,
        current_price: float | None = None,
        shares_outstanding: float | None = None,
        market_cap: float | None = None,
    ) -> dict[str, Any]:
        """Return data_unavailable marker for symbol.

        total_debt/total_cash/ebitda/current_price/shares_outstanding/market_cap are
        optional overrides (2026-08-19, extended 2026-09-06 for the latter three): these
        are pure balance-sheet/price/share-count figures that don't need every other
        field this marker nulls out - see fetch_incremental's "MOVED 2026-08-19" comment
        and _get_market_cap_without_income_statement's docstring. Callers that genuinely
        have nothing yet simply omit them and get the same all-NULL behavior as before.
        """
        return {
            "symbol": symbol,
            "computed_at": date.today().isoformat(),
            "data_unavailable": True,
            "reason": reason,
            "data_source": "none",
            # All metrics NULL except the overridable ones above
            "current_price": current_price,
            "shares_outstanding": shares_outstanding,
            "market_cap": market_cap,
            "total_debt": total_debt,
            "total_cash": total_cash,
            "enterprise_value": None,
            "ebitda": ebitda,
            "pe_ratio": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "peg_ratio": None,
            "fcf_yield": None,
            "dividend_yield": None,
            "net_payout_yield": None,
            "ev_ebitda": None,
            "ev_revenue": None,
            "intrinsic_value_per_share": None,
            "margin_of_safety_pct": None,
        }
