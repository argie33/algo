"""ValueMetricsMixin._build_value_metrics, extracted from
load_value_quality_growth_metrics.py (2026-09-05, file-size-ratchet compliance split).

Computes the `value_metrics` table (PE, PB, PS, PEG, FCF yield, dividend yield, DCF
intrinsic value) from sec_valuations + financial-statement history. Moved verbatim - no
behavior change - except `DatabaseContext(...)` call sites now go through `_owner()` (see
that helper's own docstring for why).

Mixed into ValueQualityGrowthMetricsLoader via multiple inheritance alongside
QualityMetricsMixin/GrowthMetricsMixin - every `self.` call here resolves normally through
the instance regardless of which mixin file defines it.
"""

import logging
from typing import TYPE_CHECKING, Any

from loaders.helpers.vqg_shared import (
    get_loader_timestamp,
    intrinsic_value_reason_from_fcf_yield,
    peg_ratio_reason_from_eps_history,
)
from loaders.helpers.vqg_symbol_gates import SymbolGateMixin
from utils.type_conversion import safe_float


def _owner() -> Any:
    """Lazy reference to the owner module, resolved at call time (not import time).

    Two reasons this indirection exists, both load-bearing:
    (1) DatabaseContext: dozens of existing unit tests monkeypatch
    ``loaders.load_value_quality_growth_metrics.DatabaseContext`` directly. A module-level
    ``from utils.db.context import DatabaseContext`` here would bind this module's own
    separate copy of the name, which those patches can never reach - going through
    ``_owner().DatabaseContext`` always reads whatever the owner module's current attribute
    is, mocked or real.
    (2) Avoids importing anything from the owner module at THIS module's top level, which
    is what caused a real circular-import crash on 2026-09-05 (see
    vqg_and_stock_scores_dead_split_files_deleted_20260905 in memory): when the owner is run
    as a script (``python loaders/load_value_quality_growth_metrics.py``) rather than
    imported as a package, it registers under ``sys.modules["__main__"]``, not its dotted
    path - a top-level `from loaders.load_value_quality_growth_metrics import X` here then
    re-imports the owner from scratch while it's still mid-import, before this class exists
    yet, raising ImportError. Importing lazily inside a function body sidesteps this
    entirely since it only runs after both modules have finished importing.
    """
    from loaders import load_value_quality_growth_metrics as _owner_mod

    return _owner_mod


logger = logging.getLogger("loaders.load_value_quality_growth_metrics")


class ValueMetricsMixin(SymbolGateMixin):
    """See module docstring.

    Inherits SymbolGateMixin (also a base of ValueQualityGrowthMetricsLoader itself - a
    diamond, harmless since it's the same class both times) purely so mypy can see the
    `_get_*_symbols` gate methods called via `self.` below; the handful of other
    cross-mixin/owner-class members are declared type-checking-only below.
    """

    if TYPE_CHECKING:
        MIN_PLAUSIBLE_FORWARD_PE_RATIO: float
        MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO: float

        def _unavailable_marker(self, table: str, symbol: str, reason: str | None = None) -> dict[str, Any]: ...

        def _fetch_positioning_metrics(self, symbol: str) -> tuple[float | None, str | None]: ...

    def _build_value_metrics(  # noqa: C901 -- net_payout_yield's TIER 2 fallback pushed this
        # pre-existing multi-tier function over the complexity threshold; self-contained, not
        # entangled with the existing tiers, so left in place rather than force-extracted.
        self,
        symbol: str,
        sec_val_row: Any,
    ) -> dict[str, Any]:
        """Build value_metrics from SEC valuations (yfinance-free).

        All metrics from SEC-audited data. dividend_yield comes from load_sec_valuations.py's
        SEC "PaymentsOfDividends" cash-flow concept / market_cap.
        """
        # Extract SEC-derived valuations (all from sec_valuations table)
        # Using dict access - tuple fallback violates fail-fast governance
        row_dict = dict(sec_val_row) if sec_val_row and hasattr(sec_val_row, "__getitem__") else {}
        if not row_dict or row_dict.get("data_unavailable"):  # data_unavailable flag (was index 2)
            # Propagate the specific reason load_sec_valuations.py already computed (e.g.
            # "shares_outstanding_unavailable") rather than a generic "missing_sec_data" -
            # falls back to the generic reason only when sec_valuations has no row at all.
            marker = self._unavailable_marker("value_metrics", symbol, reason=row_dict.get("reason"))
            # A preferred/subordinated-debenture ticker (see
            # _get_preferred_or_debt_security_symbols()'s docstring) never gets a
            # sec_valuations row at all (load_sec_valuations.py doesn't compute market-cap/EV
            # for these child tickers), so this early return was the ONLY code path reachable
            # for them - the same gate's per-field wiring further below (pe_ratio_reason/
            # pb_ratio_reason/ps_ratio_reason/peg_ratio's own cascades) is correct but
            # unreachable dead code for this exact case. Same "wrong, not missing" reasoning,
            # applied here instead. Deliberately excludes dividend_yield (a preferred's fixed
            # coupon / its own market price is a real, meaningful yield - see that gate's own
            # docstring) and every other field (market_cap/EV/intrinsic_value etc. haven't been
            # vetted the same way) - only overriding the four ratios that gate already covers.
            if symbol in self._get_preferred_or_debt_security_symbols():
                for field in ("pe_ratio", "pb_ratio", "ps_ratio", "peg_ratio"):
                    if marker.get(f"{field}_unavailable_reason") is not None:
                        marker[f"{field}_unavailable_reason"] = "preferred_or_debt_security_no_common_equity_ratio"
            return marker

        pe = row_dict.get("pe_ratio")
        pb = row_dict.get("pb_ratio")
        ps = row_dict.get("ps_ratio")
        peg = row_dict.get("peg_ratio")
        fcf_yield = row_dict.get("fcf_yield")
        dividend_yield = row_dict.get("dividend_yield")
        net_payout_yield = row_dict.get("net_payout_yield")
        enterprise_value = row_dict.get("enterprise_value")
        ev_ebitda = row_dict.get("ev_ebitda")
        ev_revenue = row_dict.get("ev_revenue")
        market_cap = row_dict.get("market_cap")
        intrinsic_value_per_share = row_dict.get("intrinsic_value_per_share")
        margin_of_safety_pct = row_dict.get("margin_of_safety_pct")

        # yfinance_snapshot has had no live writer for a long time (frozen table) - dropping
        # any fallback that reads it only removes stale/frozen values, doesn't touch anything live.
        if dividend_yield is None:
            # TIER 2 FALLBACK: Try SEC dividend_data (most recent dividend)
            try:
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT dividend_yield_pct FROM dividend_data
                        WHERE symbol = %s AND data_unavailable = FALSE AND dividend_yield_pct IS NOT NULL
                        ORDER BY ex_dividend_date DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    sec_div_row = cur.fetchone()
                    if sec_div_row:
                        # FIX 2026-09-04 (goal: "Missing SEC/XBRL data" reduction - same
                        # Decimal/float class as the fcf_margin fallback fix elsewhere in this
                        # file): sec_div_row[0] is a raw psycopg2 Decimal (dividend_yield_pct is
                        # NUMERIC) - `Decimal / 100.0` raises TypeError, silently caught by this
                        # block's own try/except below and logged at debug level, so this SEC
                        # dividend_data fallback tier never actually populated dividend_yield for
                        # any symbol that reached it.
                        dividend_yield = float(sec_div_row[0]) / 100.0  # Convert percentage to decimal
                        logger.debug(f"[VALUE_METRICS] {symbol}: Using SEC dividend_data: {dividend_yield:.2%}")
            except Exception as e:
                logger.debug(f"[VALUE_METRICS] {symbol}: SEC dividend_data fallback failed: {e}")

        # TIER 3 FALLBACK 2026-08-18 (goal: "no SEC data"/loader audit): the dividend_data
        # table (per-share/ex-dividend-date XBRL concepts) and annual_cash_flow (the
        # financing-activities "dividends paid" cash-flow-statement line, sourced
        # independently by load_financial_statements.py) are two separate extractions -
        # live-confirmed 153 universe symbols (incl. HSBC, SHEL, BHP, VOD - all real,
        # well-known dividend payers) had a real, recent, positive annual_cash_flow.
        # dividends_paid figure while dividend_data had no usable row, so the reason logic
        # below fell through to "non_dividend_paying_stock" - a factually wrong
        # classification for a company that demonstrably paid a real dividend, not just a
        # missing-data label. Aggregate yield = total dividends paid / market cap is a
        # standard, real approximation (no per-share/shares-outstanding intermediate
        # needed - both cancel out), same "recover a real value instead of a misleading
        # non-payer label" precedent as the dividend_data TIER 2 fallback above.
        # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit): the TIER 3
        # fallback below already independently confirms - via this exact aggregate-yield
        # computation - a case entirely distinct from "no dividend data": a REAL dividends_
        # paid figure and a REAL market_cap producing a REAL ratio that's simply too large to
        # be a genuine current yield (live-confirmed BGSF 37.3%, CMCT 60.1%, CMTG 53.2% -
        # small/distressed-price companies whose historical dividend now dwarfs a since-
        # collapsed market cap). That fact was computed and then silently discarded (just a
        # debug log) instead of being propagated to dividend_yield_reason below, which instead
        # fell through to the generic "missing_sec_data" - the same "real value, deliberately
        # rejected as implausible" mislabel class already fixed elsewhere in this file, just
        # not yet wired here. `implausible_ratio` is a different, already-correctly-bucketed
        # coverage category ("Implausible / rejected value") than "missing_sec_data" ("Missing
        # SEC/XBRL data") - this is a real headline-relevant fix, not just a diagnostic one.
        dividend_yield_implausible_from_cash_flow = False
        if dividend_yield is None and market_cap is not None and market_cap > 0:
            try:
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT dividends_paid FROM annual_cash_flow
                        WHERE symbol = %s AND dividends_paid IS NOT NULL AND dividends_paid > 0
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 2
                        ORDER BY fiscal_year DESC
                        """,
                        (symbol,),
                    )
                    cf_div_rows = cur.fetchall()
                    # FIXED 2026-09-05 (goal session: "implausible values" sweep, same gap class
                    # as fcf_margin/ps_ratio/pe_ratio/pb_ratio): this used to check only the
                    # single most recent qualifying year (LIMIT 1) - a real but tiny/artifact-
                    # scale dividends_paid figure in that one year could reject the whole
                    # fallback even when an ALSO-within-window older year has a genuinely
                    # representative figure. Still bounded to the same 2-year recency window
                    # (deliberate - a stale multi-year-old dividend shouldn't drive a current
                    # yield), just no longer gives up after the first candidate.
                    if cf_div_rows:
                        dividend_yield_implausible_from_cash_flow = True
                        for (cf_dividends_paid,) in cf_div_rows:
                            # market_cap here can be a real but badly-scaled shares_outstanding
                            # figure sec_valuations itself already refused to compute a ratio
                            # against (a scale mismatch inflates the yield) - bound matches
                            # load_sec_valuations.py's own primary dividend_yield bound.
                            candidate = float(cf_dividends_paid) / float(market_cap)
                            if 0 < candidate <= self.MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO:
                                dividend_yield = candidate
                                dividend_yield_implausible_from_cash_flow = False
                                logger.debug(
                                    f"[VALUE_METRICS] {symbol}: Using annual_cash_flow.dividends_paid "
                                    f"aggregate yield: {dividend_yield:.2%}"
                                )
                                break
                        else:
                            logger.debug(
                                f"[VALUE_METRICS] {symbol}: annual_cash_flow dividend fallback - "
                                "no within-window candidate produced a plausible yield, leaving NULL"
                            )
            except Exception as e:
                logger.debug(f"[VALUE_METRICS] {symbol}: annual_cash_flow dividend fallback failed: {e}")

        # TIER 2 FALLBACK for net_payout_yield - same rationale as the dividend TIER 3 fallback
        # above: aggregate (dividends + buybacks) / market_cap when sec_valuations.
        # net_payout_yield is NULL but annual_cash_flow has raw dividends_paid/
        # common_stock_repurchased. No curated buyback-specific table exists, so this is the
        # only fallback tier for this field.
        if net_payout_yield is None and market_cap is not None and market_cap > 0:
            try:
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT dividends_paid, common_stock_repurchased FROM annual_cash_flow
                        WHERE symbol = %s
                          AND (COALESCE(dividends_paid, 0) > 0 OR COALESCE(common_stock_repurchased, 0) != 0)
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 2
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    cf_payout_row = cur.fetchone()
                    if cf_payout_row:
                        cf_div, cf_buyback = cf_payout_row
                        total_payout = (0.0 if cf_div is None else float(cf_div)) + (
                            0.0 if cf_buyback is None else abs(float(cf_buyback))
                        )
                        # Bound is tighter (50%) than sec_valuations' own fresh computation
                        # (150%, which has upstream cross-checks this fallback lacks): this
                        # fallback's market_cap can be a broken shares_outstanding figure
                        # sec_valuations itself already refused to compute a ratio against -
                        # real shareholder-return companies rarely exceed 15-20%/yr anyway.
                        if 0 < total_payout / float(market_cap) <= 0.5:
                            net_payout_yield = total_payout / float(market_cap)
                            logger.debug(
                                f"[VALUE_METRICS] {symbol}: Using annual_cash_flow "
                                f"dividends+buybacks aggregate net payout yield: {net_payout_yield:.2%}"
                            )
                        elif total_payout > 0:
                            logger.debug(
                                f"[VALUE_METRICS] {symbol}: annual_cash_flow net payout yield "
                                f"out of bounds ({total_payout / float(market_cap):.2%}), leaving NULL"
                            )
            except Exception as e:
                logger.debug(f"[VALUE_METRICS] {symbol}: annual_cash_flow net payout fallback failed: {e}")

        # forward_pe = current_price / consensus forward EPS, joined from analyst_earnings_estimates
        # (load_sec_valuations.py stays SEC-only by design; SEC filings never carry forward estimates).
        # ebitda is only ever None when operating_income itself is unavailable (D&A is additive,
        # never required for the ebitda computation) - and when ebitda IS present but <= 0, that's
        # a real negative/zero-EBITDA company where EV/EBITDA isn't a meaningful ratio, same
        # "not applicable" class as non_dividend_paying_stock, not missing data.
        ebitda_raw = row_dict.get("ebitda")
        # load_sec_valuations.py only ever persists enterprise_value when market_cap + total_debt
        # - total_cash > 0 - a net-cash-rich filer (cash alone exceeds market_cap + debt)
        # computes a negative/zero EV there, a genuine "not a meaningful ratio" case (EV/EBITDA
        # and EV/Revenue undefined), not a data gap. Approximates load_sec_valuations.py's
        # entity-wide EV formula with the per-class market_cap already persisted here - used
        # only for labeling, never for a computed value.
        _computed_ev_for_reason = (
            market_cap + (row_dict.get("total_debt") or 0) - (row_dict.get("total_cash") or 0)
            if market_cap is not None
            else None
        )
        if ebitda_raw is not None and ebitda_raw <= 0:
            ev_ebitda_reason = "unprofitable_stock"
        elif ebitda_raw is None:
            ev_ebitda_reason = "ebitda_not_extracted"
        # ebitda>0 present, enterprise_value missing or out of bounds: enterprise_value =
        # market_cap + total_debt - total_cash, so it fails whenever total_debt can't be
        # itemized - reuse the same gate quality_metrics.total_debt already uses.
        elif symbol in self._get_no_recent_debt_components_symbols():
            ev_ebitda_reason = "total_debt_not_itemized"
        elif _computed_ev_for_reason is not None and _computed_ev_for_reason <= 0:
            ev_ebitda_reason = "negative_enterprise_value"
        # ev_ebitda is one of the fields _sanity_check_market_cap nulls on a shares_outstanding
        # scale mismatch (see pb_ratio_reason below) - placed last so a real ebitda_raw<=0/
        # no-debt-itemized/negative-EV cause above still wins.
        elif row_dict.get("reason") == "shares_outstanding_scale_mismatch":
            ev_ebitda_reason = "shares_outstanding_scale_mismatch"
        else:
            ev_ebitda_reason = "missing_sec_data"

        # fcf_yield's own specific reason, computed once here so both fcf_yield_unavailable_reason
        # below and intrinsic_value_reason_from_fcf_yield() show the same real, already-categorized
        # cause instead of two different labels for one fact.
        #
        # ADDED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" sweep): the RIC/ETF-
        # trust checks quality_metrics.fcf_margin's sibling chain already has (vqg_quality.py,
        # ~line 2144/1676) were never wired into this value_metrics chain - same structural
        # fact (a closed-end fund or physical commodity/crypto trust files no GAAP cash-flow
        # statement at all), just missed in a different file. Live-sampled the "Missing SEC/
        # XBRL data" fcf_yield bucket (146 symbols) and found real CEFs (ETO/EIC/BTT/KTF/GUT/
        # TYG-class) and ETF trusts (SLV/IAU/GBTC, all confirmed present in etf_symbols) mixed
        # in with genuine gaps - checked first, same priority order as the quality_metrics
        # sibling.
        fcf_yield_reason_str = (
            (
                "registered_investment_company_no_xbrl"
                if symbol in self._get_registered_investment_company_symbols()
                else "etf_trust_no_gaap_financials"
                if symbol in self._get_etf_trust_no_stockholders_equity_symbols()
                else "no_recent_free_cash_flow_reported"
                if symbol in self._get_no_recent_free_cash_flow_symbols()
                or symbol in self._get_never_tagged_free_cash_flow_symbols()
                else "capex_never_tagged_in_recent_filings"
                if symbol in self._get_no_recent_capex_symbols()
                # fcf_yield is also nulled by _sanity_check_market_cap's shares_outstanding
                # scale-mismatch guard (fcf_yield divides by market_cap); this also flows into
                # intrinsic_value/margin_of_safety's reasons below, which derive from this value.
                else "shares_outstanding_scale_mismatch"
                if row_dict.get("reason") == "shares_outstanding_scale_mismatch"
                else "missing_sec_data"
            )
            if fcf_yield is None
            else None
        )

        # intrinsic_value_per_share reason: prefer sec_valuations.dcf_fcf_unavailable_reason
        # (migration 1258) - the DCF's own ground-truth fcf sign, recorded where it's actually
        # known - over the fcf_yield-based guess below. fcf_yield's own FCF base never receives
        # the DCF-only net-borrowing adjustment dcf_fcf_base does, so the two can have opposite
        # signs (live-confirmed via APTV/AER/ASB and 14 other symbols: fcf_yield positive, real
        # DCF fcf negative/None from a balance-sheet debt swing) - the fcf_yield-based guess
        # below stays only as a fallback for rows load_sec_valuations.py hasn't reprocessed yet.
        dcf_fcf_reason = row_dict.get("dcf_fcf_unavailable_reason")
        intrinsic_value_reason = (
            (dcf_fcf_reason or intrinsic_value_reason_from_fcf_yield(fcf_yield, fcf_yield_reason_str))
            if intrinsic_value_per_share is None
            else None
        )
        if margin_of_safety_pct is None:
            # load_sec_valuations.py's _compute_dcf_intrinsic_value computes intrinsic_per_share
            # and margin_of_safety_pct together as a pair - the ONLY way to get a real
            # intrinsic_per_share alongside a None margin_of_safety_pct is its explicit
            # `-100_000 <= margin_of_safety_pct <= 1000` bounds rejection (implausible DCF result),
            # not a missing-data case - 100% precise, not a probabilistic gate.
            margin_of_safety_reason = (
                intrinsic_value_reason if intrinsic_value_per_share is None else "implausible_dcf_result"
            )
        else:
            margin_of_safety_reason = None

        forward_pe = None
        # A real analyst forward-EPS estimate for a company projected to LOSE money next year
        # (common for biotech/EV/early-growth names) correctly leaves forward_pe undefined
        # (price / negative earnings isn't a valid multiple) - distinguish that from genuinely
        # having zero analyst coverage rather than lumping both under "no_analyst_estimates".
        forward_pe_reason = "no_analyst_estimates"
        current_price = row_dict.get("current_price")
        if current_price is not None and current_price > 0:
            with _owner().DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT forward_eps FROM analyst_earnings_estimates
                    WHERE symbol = %s AND data_unavailable = FALSE
                    ORDER BY date DESC LIMIT 1
                    """,
                    (symbol,),
                )
                fe_row = cur.fetchone()
            forward_eps = fe_row[0] if fe_row else None
            if forward_eps is not None and forward_eps > 0:
                computed_forward_pe = float(current_price) / float(forward_eps)
                if computed_forward_pe >= self.MIN_PLAUSIBLE_FORWARD_PE_RATIO:
                    forward_pe = computed_forward_pe
                else:
                    logger.warning(
                        f"[VALUE_METRICS] {symbol}: forward_pe implausibly low "
                        f"({computed_forward_pe:.4f} < {self.MIN_PLAUSIBLE_FORWARD_PE_RATIO}), "
                        "excluding from Value scoring rather than letting a single extreme value rank #1."
                    )
                    forward_pe_reason = "implausibly_low_forward_pe"
            elif forward_eps is not None:
                forward_pe_reason = "negative_forward_eps"

        # Validate: at least one core metric must be non-None. forward_pe counts toward
        # "available" even if historical SEC PE/PB/PS/FCF is missing - an unprofitable company
        # with analyst forward EPS guidance still has a usable forward valuation metric.
        core_metrics = [pe, pb, ps, fcf_yield, forward_pe]
        if all(m is None for m in core_metrics):
            return self._unavailable_marker("value_metrics", symbol)

        # TIER 4 FALLBACK for dividend_yield 2026-08-28 (goal: "get this data" - dividend yield
        # showing "SEC data not available" for confirmed real payers). Root cause: dividend_data.
        # dividend_yield_pct is 0/91569 populated universe-wide (live-confirmed) - no writer for
        # this repo has ever set it, so TIER 2 above (which filters on it being non-NULL) can
        # never match anything, for any symbol. TIER 3's annual_cash_flow.dividends_paid is also
        # unpopulated for many real payers (live-confirmed on SPG/RS/CNK, all real, well-known
        # dividend stocks with 5 straight quarters of real dividend_per_share on file and zero
        # rows written to annual_cash_flow's dividends_paid). dividend_data.dividend_per_share
        # itself IS populated (86859 rows) and unused by any fallback tier. Sum trailing ~370
        # days of per-share payments (covers a full year of quarterly cadence with slack for
        # reporting lag) and divide by current_price - the standard trailing dividend yield
        # calculation. Live-confirmed this recovers 47 of the universe's 66 remaining
        # "missing_sec_data" dividend_yield rows, incl. SPG/RS/CNK. Same 0-100% plausibility
        # bound as TIER 3 (share-count/market-cap scale errors aren't a risk here since this
        # tier never divides by market_cap, but a bad per-share figure or stock split artifact
        # could still produce nonsense).
        # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit, same gap class
        # as TIER 3's own implausible-ratio wiring just above - added the same day that fix was
        # made, just never mirrored here since this tier predates it by over a week): an
        # out-of-bounds candidate here used to just log-and-discard, exactly like TIER 3 before
        # its fix - so a real, positive dividend_per_share/current_price combination that's
        # simply too large to be a genuine yield (a stale/pre-split per-share figure against a
        # since-changed price, or a preferred/unit security's real payout dwarfing a common-
        # equivalent price) fell through to the generic "missing_sec_data" instead of
        # "implausible_ratio". Live-confirmed CVKD: real $16.50/share quarterly payments (4
        # straight quarters within the trailing-370-day window) against a $1.22 price implies a
        # ~2705% yield - real data, correctly rejected, mislabeled all the same.
        dividend_yield_implausible_from_ttm_dividend_data = False
        if dividend_yield is None and current_price is not None and current_price > 0:
            try:
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT SUM(dividend_per_share) FROM dividend_data
                        WHERE symbol = %s AND data_unavailable = FALSE
                          AND dividend_per_share IS NOT NULL
                          AND ex_dividend_date > CURRENT_DATE - INTERVAL '370 days'
                        """,
                        (symbol,),
                    )
                    ttm_row = cur.fetchone()
                    ttm_dividends = ttm_row[0] if ttm_row else None
                    if ttm_dividends is not None and ttm_dividends > 0:
                        candidate = float(ttm_dividends) / float(current_price)
                        if 0 < candidate <= self.MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO:
                            dividend_yield = candidate
                            logger.debug(
                                f"[VALUE_METRICS] {symbol}: Using dividend_data.dividend_per_share "
                                f"TTM/current_price yield: {dividend_yield:.2%}"
                            )
                        else:
                            dividend_yield_implausible_from_ttm_dividend_data = True
                            logger.debug(
                                f"[VALUE_METRICS] {symbol}: dividend_per_share TTM fallback yield "
                                f"out of bounds ({candidate:.2%}), leaving NULL"
                            )
            except Exception as e:
                logger.debug(f"[VALUE_METRICS] {symbol}: dividend_per_share TTM fallback failed: {e}")

        # Determine dividend yield reason: non-payer vs missing data
        # If dividend_yield is None, check if stock is a known dividend payer
        dividend_yield_reason = None
        if dividend_yield is None:
            if dividend_yield_implausible_from_cash_flow or dividend_yield_implausible_from_ttm_dividend_data:
                dividend_yield_reason = "implausible_ratio"
            else:
                # Must filter data_unavailable=FALSE: load_dividend_data.py writes an explicit
                # "confirmed no dividend" marker row for every symbol it checks, not just payers -
                # without the filter those marker rows would look like real payment history.
                # 2-year recency window on ex_dividend_date so a stock that discontinued its
                # dividend years ago reads as "not a data gap, a stock characteristic" too, same
                # as one that never paid at all.
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT 1 FROM dividend_data
                        WHERE symbol = %s AND data_unavailable = FALSE
                          AND ex_dividend_date > CURRENT_DATE - INTERVAL '2 years'
                        LIMIT 1
                        """,
                        (symbol,),
                    )
                    has_dividend_history = cur.fetchone() is not None

                # Confirmed non-payers get dividend_yield=0.0 (semantically correct), not NULL,
                # with the reason tracked for transparency.
                if not has_dividend_history:
                    dividend_yield = 0.0
                    dividend_yield_reason = "non_dividend_paying_stock"
                else:
                    dividend_yield_reason = "missing_sec_data"

        # TIER 3 FALLBACK for net_payout_yield: a confirmed non-dividend-payer (dividend_yield_
        # reason == "non_dividend_paying_stock") with no recent buyback either should get 0.0,
        # not permanently NULL - NULL silently drops the symbol out of _score_value's weighted
        # average (the `is not None` gate there) instead of scoring it at the low end. Same
        # 2-year recency window as TIER 2's buyback check, same `!= 0` convention (sign isn't
        # guaranteed consistent).
        if net_payout_yield is None and dividend_yield_reason == "non_dividend_paying_stock":
            try:
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT 1 FROM annual_cash_flow
                        WHERE symbol = %s
                          AND COALESCE(common_stock_repurchased, 0) != 0
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 2
                        LIMIT 1
                        """,
                        (symbol,),
                    )
                    has_recent_buyback = cur.fetchone() is not None
                if not has_recent_buyback:
                    net_payout_yield = 0.0
            except Exception as e:
                logger.debug(f"[VALUE_METRICS] {symbol}: net payout confirmed-non-payer fallback failed: {e}")

        # load_sec_valuations.py only computes pe_ratio when ttm_eps > 0 (a negative/zero-EPS
        # company has no meaningful P/E, same "not applicable" class as
        # non_dividend_paying_stock). peg_ratio requires pe_ratio, so it inherits the same
        # reason when pe_ratio itself is the blocker.
        #
        # This query must mirror load_sec_valuations.py's real anchor-row selection's
        # `data_unavailable IS NOT TRUE` filter - without it, a most-recent fiscal year flagged
        # data_unavailable (e.g. 'incomplete_sec_filing_income') can still carry a stray
        # non-null EPS value that the real valuation engine skips (falling back to the prior,
        # complete year) but this query would pick up, wrongly concluding "not unprofitable,
        # must be a data gap" instead of matching the real computation's actual answer.
        pe_ratio_reason = None
        if pe is None and symbol in self._get_preferred_or_debt_security_symbols():
            # See _get_preferred_or_debt_security_symbols()'s docstring: this ticker's real
            # EPS on file belongs to its parent's common stock, not to itself - a P/E computed
            # from it would be wrong, not just missing.
            pe_ratio_reason = "preferred_or_debt_security_no_common_equity_ratio"
        elif pe is None and row_dict.get("reason") == "eps_scale_mismatch":
            # load_sec_valuations.py's _sanity_check_pe_ratio already deliberately nulls
            # pe_ratio/peg_ratio and records this specific reason (a >10x SEC-vs-yfinance PE
            # disagreement - a mis-scaled ttm_eps, not a missing one); reuse it instead of
            # re-deriving from annual_income_statement, which finds a real-looking EPS (the
            # mis-scale is in ttm_eps's computation, not the raw tagged value) and would
            # otherwise fall through to a generic "missing_sec_data" label. `eps_scale_mismatch`
            # is already mapped in scores.py's _categorize_reason to "Implausible / rejected value".
            pe_ratio_reason = "eps_scale_mismatch"
        elif pe is None:
            with _owner().DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT earnings_per_share FROM annual_income_statement
                    WHERE symbol = %s AND earnings_per_share IS NOT NULL
                      AND data_unavailable IS NOT TRUE
                    ORDER BY fiscal_year DESC LIMIT 1
                    """,
                    (symbol,),
                )
                eps_row = cur.fetchone()
            latest_eps = eps_row[0] if eps_row else None
            # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit): mirrors
            # load_sec_valuations.py's own pe_ratio bounds check (MIN_PLAUSIBLE_PE_RATIO..10000)
            # - a real, positive, tiny EPS (near-zero-denominator) produces a real but
            # astronomically large P/E that gets silently rejected there (just a warning log,
            # no reason recorded), so this cascade never learned the true cause and fell
            # through to "missing_sec_data". Live-confirmed KLIC (Kulicke & Soffa): FY2025
            # earnings_per_share=$0.0040 (real, positive) against current_price=$81.62 implies
            # pe_ratio=20,405 - the exact >10000 rejection. Same "real value, deliberately
            # rejected as implausible" mislabel class already fixed for dividend_yield this
            # session - implausible_ratio is a different, already-correctly-bucketed coverage
            # category than missing_sec_data, so this is headline-relevant, not just cosmetic.
            _pe_implausible_from_eps = False
            if latest_eps is not None and latest_eps > 0:
                _current_price = row_dict.get("current_price")
                if _current_price is not None and float(_current_price) > 0:
                    _implied_pe = float(_current_price) / float(latest_eps)
                    # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit,
                    # same fix as ps_ratio's identical gap just below): this only re-checked
                    # the implied-pe bounds, missing load_sec_valuations.py's OTHER real
                    # rejection criterion (ttm_eps < 0.10) - a tiny EPS combined with an
                    # equally tiny price can produce an implied_pe that lands comfortably
                    # inside 0.05..10000 even though the real computation rejected it via the
                    # EPS floor, so this fell through to "missing_sec_data" instead of
                    # "implausible_ratio".
                    if _implied_pe > 10000 or _implied_pe < 0.05 or float(latest_eps) < 0.10:
                        _pe_implausible_from_eps = True
            pe_ratio_reason = (
                "implausible_ratio"
                if _pe_implausible_from_eps
                else "unprofitable_stock"
                if latest_eps is not None and latest_eps <= 0
                # `eps_row is None` (this query already searches full history, no fiscal-year
                # window) means ZERO fiscal years have a real earnings_per_share value - distinct
                # from "found a value but pe still came out null" (price/ttm-anchor mismatch,
                # which correctly stays "missing_sec_data"). Foreign 20-F/IFRS filers and
                # MLP/unit-structure filers (e.g. "net income per unit" instead of EPS) commonly
                # never tag an EPS concept at all despite having real net_income every year.
                else "eps_never_tagged_in_filings"
                if eps_row is None
                # A positive EPS was found, but not in the symbol's own SEC-selected anchor
                # fiscal year (see _get_eps_absent_from_anchor_year_symbols()'s docstring,
                # e.g. BRK.A/BRK.B) - label-only, distinct from the true "anchor year has it,
                # pe still null for some other reason" case below.
                else "eps_absent_from_anchor_year"
                if symbol in self._get_eps_absent_from_anchor_year_symbols()
                else "missing_sec_data"
            )

        peg_ratio_reason: str | None
        if peg is None and pe is not None:
            with _owner().DatabaseContext("read") as cur:
                # Must mirror the real peg_ratio computation's `data_unavailable IS NOT TRUE`
                # filter (same bug class as pe_ratio_reason above) - without it a stray non-NULL
                # EPS on an incomplete/unfiled fiscal year could be compared as if it were the
                # real TTM or prior-year figure, disagreeing with what actually decided peg_ratio.
                cur.execute(
                    """
                    SELECT fiscal_year, earnings_per_share FROM annual_income_statement
                    WHERE symbol = %s AND earnings_per_share IS NOT NULL
                      AND data_unavailable IS NOT TRUE
                    ORDER BY fiscal_year DESC LIMIT 2
                    """,
                    (symbol,),
                )
                eps_rows = cur.fetchall()
            peg_ratio_reason = peg_ratio_reason_from_eps_history(eps_rows)
        else:
            peg_ratio_reason = pe_ratio_reason if peg is None and pe is None else None

        # load_sec_valuations.py only computes pb_ratio when stockholders_equity > 0; a real
        # negative book value (buybacks/accumulated deficit) is "not applicable", not missing.
        pb_ratio_reason = None
        if pb is None and symbol in self._get_preferred_or_debt_security_symbols():
            # See _get_preferred_or_debt_security_symbols()'s docstring - same "wrong, not
            # missing" reasoning as pe_ratio_reason above, for book value per share.
            pb_ratio_reason = "preferred_or_debt_security_no_common_equity_ratio"
        elif pb is None:
            with _owner().DatabaseContext("read") as cur:
                # Must mirror load_sec_valuations.py's real book_value query's `data_unavailable
                # IS NOT TRUE` filter, else an unfiled fiscal year's stray value can drive this
                # reason independent of what the real pb_ratio computation actually saw.
                cur.execute(
                    """
                    SELECT stockholders_equity
                    FROM annual_balance_sheet
                    WHERE symbol = %s AND fiscal_year IS NOT NULL AND data_unavailable IS NOT TRUE
                    ORDER BY (CASE WHEN stockholders_equity IS NOT NULL THEN 0 ELSE 1 END), fiscal_year DESC
                    LIMIT 1
                    """,
                    (symbol,),
                )
                equity_row = cur.fetchone()
            latest_book_value = equity_row[0] if equity_row else None
            # The query above deliberately has no `stockholders_equity IS NOT NULL` filter, so a
            # symbol with balance-sheet rows but stockholders_equity NULL in all of them still
            # yields a non-None equity_row (a 1-tuple wrapping None) — check latest_book_value,
            # not equity_row, to catch this "never tagged" case.
            _pb_shares_out = safe_float(row_dict.get("shares_outstanding"), f"{symbol}.pb_reason_shares_outstanding")
            _pb_current_price = safe_float(row_dict.get("current_price"), f"{symbol}.pb_reason_current_price")
            # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit, same fix
            # as pe_ratio/ps_ratio's identical gap above/below): a real book-value-per-share
            # below $0.10 (MIN_PLAUSIBLE_PB_RATIO's sibling floor, load_sec_valuations.py's
            # own pb computation) can still imply a pb comfortably inside 0.05..1000 - the
            # bare implied-pb bounds check below misses that floor and falls through to
            # "missing_sec_data" instead of "implausible_ratio".
            _pb_bvps_below_floor = (
                latest_book_value is not None
                and latest_book_value > 0
                and _pb_shares_out is not None
                and _pb_shares_out > 0
                and (float(latest_book_value) / _pb_shares_out) < 0.10
            )
            pb_ratio_reason = (
                "negative_book_value"
                if latest_book_value is not None and latest_book_value <= 0
                # A resolved equity value but pb still null (MLPs tagging "Partners' Capital"
                # instead of "StockholdersEquity", or ADRs with no extracted field at all) is a
                # genuine "never tagged" case, not an ambiguous remainder.
                else "stockholders_equity_never_tagged_in_filings"
                if latest_book_value is None
                # Recompute the same MIN_PLAUSIBLE_PB_RATIO(0.05..1000) bound load_sec_
                # valuations.py's pb computation applies but leaves unrecorded on rejection, so a
                # real book value/share count that just falls outside it reads as implausible
                # rather than a generic extraction gap.
                else "implausible_ratio"
                if (
                    _pb_bvps_below_floor
                    or (
                        latest_book_value > 0
                        and _pb_shares_out is not None
                        and _pb_current_price is not None
                        and _pb_shares_out > 0
                        and not (0.05 <= (_pb_current_price / (float(latest_book_value) / _pb_shares_out)) <= 1000)
                    )
                )
                # _sanity_check_market_cap (load_sec_valuations.py) nulls pb/ps/market_cap/
                # fcf_yield/ev_ebitda/ev_revenue/intrinsic_value/margin_of_safety together on a
                # >10x SEC-vs-yfinance market_cap disagreement, recording
                # shares_outstanding_scale_mismatch on the row — but that reason is only checked
                # in the whole-row-unavailable early return, not here when the row still resolves
                # (e.g. pe_ratio survived independently). Placed last so a more specific real
                # gate above (e.g. genuine negative_book_value) always wins.
                else "shares_outstanding_scale_mismatch"
                if row_dict.get("reason") == "shares_outstanding_scale_mismatch"
                else "missing_sec_data"
            )

        # load_sec_valuations.py's ps computation rejects (silently, no reason recorded) any
        # ratio outside MIN_PLAUSIBLE_PS_RATIO(0.05..10000); recheck that bound here so a real,
        # positive revenue combined with an out-of-bounds share count/price reads as
        # "implausible_ratio" rather than a generic missing-data fallback.
        #
        # FIXED 2026-09-05 (goal session: "implausible values" sweep): the ORDER BY only
        # required revenue IS NOT NULL, so a real but NEGATIVE most-recent-year revenue (BWMX/
        # Betterware de Mexico live-confirmed: FY2022 revenue=-$543.3M, likely a restatement/
        # writeback artifact on this IFRS filer, with real POSITIVE revenue $7.2B/$10.1B in the
        # two years just before it) got picked as "the latest revenue" - the `_ps_latest_revenue
        # > 0` guard below then correctly refused to use it for the implausible-ratio check, but
        # never fell back to the real positive figure sitting one fiscal year earlier, silently
        # dropping to the generic "missing_sec_data" fallback instead of "implausible_ratio" or
        # a real computed check. Same "prefer a real positive value even if not the newest" tiered
        # preference already used throughout this file's other reason-derivation queries (e.g.
        # _get_revenue_available_elsewhere_symbols and siblings) - positive revenue now ranks
        # ahead of a merely-non-null one, so a negative anchor year no longer masks a real
        # positive figure from an adjacent year.
        _ps_implausible_ratio = False
        if ps is None:
            _ps_shares_out = safe_float(row_dict.get("shares_outstanding"), f"{symbol}.ps_reason_shares_outstanding")
            _ps_current_price = safe_float(row_dict.get("current_price"), f"{symbol}.ps_reason_current_price")
            with _owner().DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT revenue
                    FROM annual_income_statement
                    WHERE symbol = %s AND fiscal_year IS NOT NULL AND data_unavailable IS NOT TRUE
                    ORDER BY (CASE WHEN revenue IS NOT NULL AND revenue > 0 THEN 0
                                   WHEN revenue IS NOT NULL THEN 1
                                   ELSE 2 END), fiscal_year DESC
                    LIMIT 1
                    """,
                    (symbol,),
                )
                _ps_revenue_row = cur.fetchone()
            _ps_latest_revenue = (
                safe_float(_ps_revenue_row[0], f"{symbol}.ps_reason_revenue") if _ps_revenue_row else None
            )
            if (
                _ps_latest_revenue is not None
                and _ps_latest_revenue > 0
                and _ps_shares_out is not None
                and _ps_current_price is not None
                and _ps_shares_out > 0
            ):
                # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit):
                # this used to only re-check the implied-ps bounds (0.05..10000), missing
                # load_sec_valuations.py's OTHER real rejection criterion added the same
                # session (e27a2d96f) - a real revenue-per-share below $0.10 (MIN_PLAUSIBLE_
                # PS_RATIO's sibling floor, same rationale as pe_ratio's EPS floor above).
                # A tiny per-share revenue combined with a normal share count/price commonly
                # yields an implied ps comfortably inside 0.05..10000 (e.g. rps=$0.02 against
                # an $8.82 price implies ps=431, well within bounds) even though
                # load_sec_valuations.py itself rejected it via the rps<0.10 floor - so this
                # cascade fell through to the generic "missing_sec_data" label instead of
                # "implausible_ratio". Live-confirmed ABSI (Absci Corp): FY2025 revenue=
                # $2.8M/136.8M shares = $0.0205/share, real and used elsewhere (ev_revenue=
                # 425.28 on the same row), yet ps_ratio_unavailable_reason came back
                # "missing_sec_data". A live DB scan found 132 of 133 universe ps_ratio
                # "missing_sec_data" symbols have real, positive revenue on file - this exact
                # unmirrored floor, not a genuine data gap.
                _ps_rps = _ps_latest_revenue / _ps_shares_out
                _ps_implied = _ps_current_price / _ps_rps if _ps_rps > 0 else None
                if _ps_rps < 0.10 or _ps_implied is None or not (0.05 <= _ps_implied <= 10000):
                    _ps_implausible_ratio = True

        # Fetch held_percent fields from positioning_metrics (FIXED 2026-08-18)
        held_percent_institutions, held_percent_institutions_reason = self._fetch_positioning_metrics(symbol)

        # No yfinance fallback remains for pe/pb/ps/fcf_yield/dividend/ev/market_cap/
        # intrinsic_value - always SEC-sourced. forward_pe is the one exception (computed from
        # analyst_earnings_estimates, real yfinance consensus data), so it needs its own
        # composite label rather than a blanket "sec_audited" - feeds
        # lambda/api/routes/scores.py's data-source coverage dashboard.
        overall_data_source = "sec_audited_except_forward_pe_yfinance" if forward_pe is not None else "sec_audited"

        return {
            "symbol": symbol,
            "pe_ratio": pe,
            "pb_ratio": pb,
            "ps_ratio": ps,
            "peg_ratio": peg,
            "dividend_yield": dividend_yield,
            "net_payout_yield": net_payout_yield,
            "fcf_yield": fcf_yield,
            "forward_pe": forward_pe,
            "enterprise_value": enterprise_value,
            "ev_ebitda": ev_ebitda,
            "ev_revenue": ev_revenue,
            "market_cap": market_cap,
            "intrinsic_value_per_share": intrinsic_value_per_share,
            "margin_of_safety_pct": margin_of_safety_pct,
            "value_score": None,  # Computed in load_stock_scores, copied here for convenience
            "pe_ratio_unavailable_reason": pe_ratio_reason,
            "pb_ratio_unavailable_reason": pb_ratio_reason,
            "ps_ratio_unavailable_reason": (
                (
                    # See _get_preferred_or_debt_security_symbols()'s docstring - same "wrong,
                    # not missing" reasoning as pe_ratio_reason/pb_ratio_reason above, for
                    # revenue per share.
                    "preferred_or_debt_security_no_common_equity_ratio"
                    if symbol in self._get_preferred_or_debt_security_symbols()
                    else "no_revenue_reported"
                    if symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    # Real $0 anchor-year revenue, distinct from "never any revenue in 3
                    # years" above - see _get_zero_revenue_anchor_symbols()'s own docstring.
                    else "zero_revenue_reported_this_period"
                    if symbol in self._get_zero_revenue_anchor_symbols()
                    # Real revenue exists in an earlier year, just not the current anchor
                    # year - see _get_revenue_absent_from_anchor_year_symbols()'s docstring.
                    else "revenue_absent_from_anchor_year"
                    if symbol in self._get_revenue_absent_from_anchor_year_symbols()
                    # ps_ratio is one of the fields _sanity_check_market_cap nulls on a shares-
                    # outstanding scale mismatch (see pb_ratio_reason above).
                    else "shares_outstanding_scale_mismatch"
                    if row_dict.get("reason") == "shares_outstanding_scale_mismatch"
                    else "implausible_ratio"
                    if _ps_implausible_ratio
                    else "missing_sec_data"
                )
                if ps is None
                else None
            ),
            "peg_ratio_unavailable_reason": peg_ratio_reason,
            "dividend_yield_unavailable_reason": dividend_yield_reason,
            # Computed once above (fcf_yield_reason_str) so this and intrinsic_value_reason show
            # the same specific cause - see intrinsic_value_reason_from_fcf_yield()'s docstring.
            "fcf_yield_unavailable_reason": fcf_yield_reason_str,
            "forward_pe_unavailable_reason": forward_pe_reason if forward_pe is None else None,
            "ev_ebitda_unavailable_reason": ev_ebitda_reason if ev_ebitda is None else None,
            "ev_revenue_unavailable_reason": (
                (
                    "no_revenue_reported"
                    if symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    # enterprise_value = market_cap + total_debt - total_cash, so it fails
                    # whenever total_debt can't be itemized even when revenue is present.
                    else "total_debt_not_itemized"
                    if symbol in self._get_no_recent_debt_components_symbols()
                    # Net cash exceeds market_cap + total_debt - see _computed_ev_for_reason.
                    else "negative_enterprise_value"
                    if _computed_ev_for_reason is not None and _computed_ev_for_reason <= 0
                    # Real $0 anchor-year revenue, distinct from "never any revenue" above.
                    else "zero_revenue_reported_this_period"
                    if symbol in self._get_zero_revenue_anchor_symbols()
                    # Real revenue exists in an earlier year, just not the current anchor year.
                    else "revenue_absent_from_anchor_year"
                    if symbol in self._get_revenue_absent_from_anchor_year_symbols()
                    # ev_revenue is one of the fields _sanity_check_market_cap nulls on a shares-
                    # outstanding scale mismatch; placed last so a real revenue-shaped cause wins.
                    else "shares_outstanding_scale_mismatch"
                    if row_dict.get("reason") == "shares_outstanding_scale_mismatch"
                    else "missing_sec_data"
                )
                if ev_revenue is None
                else None
            ),
            "market_cap_unavailable_reason": (
                (
                    # market_cap is the first field _sanity_check_market_cap nulls on a shares-
                    # outstanding scale mismatch, and has no other real gate to defer to, so this
                    # can be checked unconditionally rather than as a last-resort fallback.
                    "shares_outstanding_scale_mismatch"
                    if row_dict.get("reason") == "shares_outstanding_scale_mismatch"
                    else "missing_sec_data"
                )
                if market_cap is None
                else None
            ),
            "intrinsic_value_unavailable_reason": intrinsic_value_reason,
            "margin_of_safety_unavailable_reason": margin_of_safety_reason,
            "held_percent_institutions": held_percent_institutions,
            "held_percent_institutions_unavailable_reason": held_percent_institutions_reason
            if held_percent_institutions is None
            else None,
            "data_unavailable": False,
            "data_source": overall_data_source,
            "updated_at": get_loader_timestamp(),
        }
