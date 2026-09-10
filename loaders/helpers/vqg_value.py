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
        MAX_PLAUSIBLE_FORWARD_PE_RATIO: float
        MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO: float
        _ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS: frozenset[str]

        def _unavailable_marker(self, table: str, symbol: str, reason: str | None = None) -> dict[str, Any]: ...

        def _fetch_positioning_metrics(self, symbol: str) -> tuple[float | None, str | None]: ...

    def _compute_dividend_and_payout_yield(  # noqa: C901 -- multi-tier fallback chain,
        # extracted verbatim from _build_value_metrics (which carried the same noqa) - not
        # entangled with anything else, left as one function rather than force-split further.
        self,
        symbol: str,
        market_cap: float | None,
        current_price: float | None,
    ) -> tuple[float | None, float | None, str | None]:
        """Dividend/net-payout yield fallback tiers (dividend_data / annual_cash_flow) plus
        the final dividend_yield_reason classification.

        EXTRACTED 2026-09-09 (goal: "SEC/XBRL missing data under 500" sweep) out of
        _build_value_metrics's inline body so it can also run from that method's
        no-income-statement early-return branch above: needs only market_cap/current_price
        (both already recovered there via _get_market_cap_without_income_statement, same
        as the existing market_cap/pb_ratio overrides in that branch) - no income-statement
        dependency at all. That branch used to return before ever reaching this logic, so a
        symbol whose sec_valuations row was flagged data_unavailable=True for
        "no_income_statement" (a real 10-K/10-Q on file, just no income-statement concepts
        tagged) could never get dividend_yield recovered from dividend_data/
        annual_cash_flow even when both are fully populated for it.

        Returns (dividend_yield, net_payout_yield, dividend_yield_reason) - reason is None
        when dividend_yield was recovered to a real (non-zero-non-payer) value.
        """
        dividend_yield: float | None = None
        net_payout_yield: float | None = None
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
                    dividend_yield = float(sec_div_row[0]) / 100.0
                    logger.debug(f"[VALUE_METRICS] {symbol}: Using SEC dividend_data: {dividend_yield:.2%}")
        except Exception as e:
            logger.debug(f"[VALUE_METRICS] {symbol}: SEC dividend_data fallback failed: {e}")

        # TIER 3 FALLBACK: aggregate dividends_paid / market_cap
        dividend_yield_implausible_from_cash_flow = False
        if dividend_yield is None and market_cap is not None and market_cap > 0:
            try:
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT dividends_paid FROM annual_cash_flow
                        WHERE symbol = %s AND dividends_paid IS NOT NULL AND dividends_paid > 0
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 2
                          AND data_unavailable IS NOT TRUE
                        ORDER BY fiscal_year DESC
                        """,
                        (symbol,),
                    )
                    cf_div_rows = cur.fetchall()
                    if cf_div_rows:
                        dividend_yield_implausible_from_cash_flow = True
                        for (cf_dividends_paid,) in cf_div_rows:
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

        # TIER for net_payout_yield: aggregate (dividends + buybacks) / market_cap
        if net_payout_yield is None and market_cap is not None and market_cap > 0:
            try:
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT dividends_paid, common_stock_repurchased FROM annual_cash_flow
                        WHERE symbol = %s
                          AND (COALESCE(dividends_paid, 0) > 0 OR COALESCE(common_stock_repurchased, 0) != 0)
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 2
                          AND data_unavailable IS NOT TRUE
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

        # TIER 4 FALLBACK for dividend_yield: sum trailing ~370 days of dividend_data.
        # dividend_per_share / current_price
        dividend_yield_implausible_from_ttm_dividend_data = False
        dividend_yield_no_ttm_payment = False
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
                    else:
                        dividend_yield_no_ttm_payment = True
            except Exception as e:
                logger.debug(f"[VALUE_METRICS] {symbol}: dividend_per_share TTM fallback failed: {e}")

        # Determine dividend yield reason: non-payer vs missing data
        dividend_yield_reason = None
        if dividend_yield is None:
            if dividend_yield_implausible_from_cash_flow or dividend_yield_implausible_from_ttm_dividend_data:
                dividend_yield_reason = "implausible_ratio"
            else:
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

                if has_dividend_history and dividend_yield_no_ttm_payment:
                    dividend_yield_reason = "dividend_lapsed_beyond_ttm_window"
                elif not has_dividend_history:
                    dividend_yield = 0.0
                    dividend_yield_reason = "non_dividend_paying_stock"
                else:
                    dividend_yield_reason = "missing_sec_data"

        # TIER for net_payout_yield: a confirmed non-dividend-payer with no recent buyback
        # either should get 0.0, not permanently NULL.
        if net_payout_yield is None and dividend_yield_reason == "non_dividend_paying_stock":
            try:
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT 1 FROM annual_cash_flow
                        WHERE symbol = %s
                          AND COALESCE(common_stock_repurchased, 0) != 0
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 2
                          AND data_unavailable IS NOT TRUE
                        LIMIT 1
                        """,
                        (symbol,),
                    )
                    has_recent_buyback = cur.fetchone() is not None
                if not has_recent_buyback:
                    net_payout_yield = 0.0
            except Exception as e:
                logger.debug(f"[VALUE_METRICS] {symbol}: net payout confirmed-non-payer fallback failed: {e}")

        return dividend_yield, net_payout_yield, dividend_yield_reason

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
            #
            # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): `not row_dict`
            # (sec_valuations has literally NO row for this symbol, not even a data_unavailable
            # marker one) has no `reason` to propagate at all - live-confirmed SPY has zero
            # sec_valuations rows (load_sec_valuations.py never even attempts a market-cap/EV
            # computation for it) and was falling all the way to the generic "missing_sec_data"
            # default, the same ETF-mislabeling class already fixed in vqg_quality.py/
            # vqg_growth.py's own zero-row early returns. Only meaningful in the `not row_dict`
            # branch - a real `data_unavailable=True` row already carries its own specific
            # `reason` via row_dict.get("reason") above, unaffected by this.
            fallback_reason = "etf_no_sec_filings" if not row_dict and symbol in self._get_etf_symbols() else None
            marker = self._unavailable_marker("value_metrics", symbol, reason=row_dict.get("reason") or fallback_reason)
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
            # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, sibling to
            # sec_valuations_income_context.py's _get_market_cap_without_income_statement):
            # sec_valuations' own "no_income_statement"/etc. data_unavailable marker can
            # still carry a real market_cap (price * shares_outstanding needs neither an
            # income statement nor this method's other tiers) - this method's own all-NULL
            # `_unavailable_marker("value_metrics", ...)` above discarded it unconditionally.
            # Live-confirmed AADX/DPC/SIND/PBLS/ADBT/ADIG/BSEM/AIB/KARD/AVEX/SSMR/CSQR/LFTO/
            # FCBM/HMH/LCLN/LIME/SECZ/SUJA all have a real row_dict["market_cap"] here despite
            # data_unavailable=True.
            if row_dict.get("market_cap") is not None:
                marker["market_cap"] = row_dict["market_cap"]
                marker["market_cap_unavailable_reason"] = None
            # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day
            # follow-up, sibling to the market_cap override above): pb_ratio only needs
            # current_price/shares_outstanding (already recovered above) and
            # annual_balance_sheet.stockholders_equity - no income-statement dependency
            # either. Skipped for a preferred/subordinated-debenture ticker (the override
            # just above already correctly recategorizes its pb_ratio reason as
            # "preferred_or_debt_security_no_common_equity_ratio" - a real business fact,
            # not a missing value, so it must not be clobbered by a real number here even
            # if sec_valuations happened to compute one).
            if row_dict.get("pb_ratio") is not None and symbol not in self._get_preferred_or_debt_security_symbols():
                marker["pb_ratio"] = row_dict["pb_ratio"]
                marker["pb_ratio_unavailable_reason"] = None
            # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day
            # follow-up): held_percent_institutions comes from positioning_metrics (13F
            # ownership data) - a completely separate feed from sec_valuations/SEC XBRL, but
            # `_fetch_positioning_metrics` is only ever called further down this method, past
            # this early return, so a sec_valuations data_unavailable row (of ANY reason, not
            # just no_income_statement) silently fell back to that reason instead of its own
            # real, more specific positioning_metrics status. Live-confirmed 17/19 symbols
            # hitting the no_income_statement gate (AADX/DPC/SIND/etc.) have a real, specific
            # "no_resolved_13f_holdings" reason recorded in positioning_metrics (correctly
            # "Ownership data unresolved" in /api/scores/coverage, not "Missing SEC/XBRL
            # data" - see coverage_category_rules.py) and 2/19 (AIB, FCBM) have a real,
            # computed institutional_ownership_pct that was being discarded outright.
            held_percent_institutions, held_percent_institutions_reason = self._fetch_positioning_metrics(symbol)
            if held_percent_institutions is not None:
                marker["held_percent_institutions"] = held_percent_institutions
                marker["held_percent_institutions_unavailable_reason"] = None
            elif held_percent_institutions_reason is not None:
                marker["held_percent_institutions_unavailable_reason"] = held_percent_institutions_reason
            # ADDED 2026-09-09 (goal: "SEC/XBRL missing data under 500" sweep, sibling to the
            # market_cap/pb_ratio overrides just above): dividend_yield/net_payout_yield need
            # only market_cap/current_price (both already recovered above in this same branch
            # via _get_market_cap_without_income_statement), not an income statement - this
            # early return used to discard dividend_data/annual_cash_flow fallback recovery
            # entirely for every "no_income_statement"-style data_unavailable row, even for
            # confirmed real dividend payers with a full dividend_data history on file.
            dividend_yield, net_payout_yield, dividend_yield_reason = self._compute_dividend_and_payout_yield(
                symbol, row_dict.get("market_cap"), row_dict.get("current_price")
            )
            if dividend_yield is not None:
                marker["dividend_yield"] = dividend_yield
                marker["dividend_yield_unavailable_reason"] = dividend_yield_reason
            if net_payout_yield is not None:
                marker["net_payout_yield"] = net_payout_yield
                marker["net_payout_yield_unavailable_reason"] = None
            return marker

        pe = row_dict.get("pe_ratio")
        pb = row_dict.get("pb_ratio")
        ps = row_dict.get("ps_ratio")
        peg = row_dict.get("peg_ratio")
        fcf_yield = row_dict.get("fcf_yield")
        enterprise_value = row_dict.get("enterprise_value")
        ev_ebitda = row_dict.get("ev_ebitda")
        ev_revenue = row_dict.get("ev_revenue")
        market_cap = row_dict.get("market_cap")
        intrinsic_value_per_share = row_dict.get("intrinsic_value_per_share")
        margin_of_safety_pct = row_dict.get("margin_of_safety_pct")
        current_price = row_dict.get("current_price")

        # dividend_yield/net_payout_yield TIER 2/3/4 fallbacks + final dividend_yield_reason
        # classification, extracted to _compute_dividend_and_payout_yield (2026-09-09) so the
        # same logic is reusable from this method's own no-income-statement early-return branch
        # above - see that method's docstring for the full history of these fallback tiers.
        dividend_yield, net_payout_yield, dividend_yield_reason = self._compute_dividend_and_payout_yield(
            symbol, market_cap, current_price
        )

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
        # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, comprehensive RIC-gap
        # scan): a registered investment company (see _get_registered_investment_company_
        # symbols()' docstring) has no debt concept to tag at all, same structural fact already
        # recategorized for quality_metrics.total_debt/roic_pct/roce_pct/debt_to_equity - this
        # chain used to reuse the "total_debt_not_itemized" branch below (same root gate,
        # _get_no_recent_debt_components_symbols()) without ever checking RIC first, and was
        # ALSO placed after the ebitda_raw None/<=0 checks below - a RIC's own EBITDA concept is
        # equally absent (no GAAP income statement at all), so it was silently outranked by
        # "ebitda_not_extracted"/"unprofitable_stock" whenever ebitda_raw happened to be None or
        # 0 instead of ever reaching this check. Live-confirmed CEV (a real ebitda>0 but no debt
        # concept RIC) was falling to the generic "total_debt_not_itemized" ("Missing SEC/XBRL
        # data") instead of "registered_investment_company_no_xbrl" ("Legitimate / not
        # applicable"). Moved to the front of this chain so it wins regardless of ebitda_raw's
        # own state, mirroring fcf_yield_reason_str's own RIC/etf-trust/royalty-trust priority
        # order just above in this file.
        #
        # FIXED same sweep, same-day follow-up: a physical commodity/currency/crypto trust
        # (etf_trust) or royalty trust has no EBITDA concept either (no operating business to
        # report income/expenses for) - same structural fact, added as siblings to the RIC check
        # here since neither was ever wired into this specific chain (fcf_yield/total_debt/
        # quality_metrics.ebitda already have all three). Live-confirmed 37 active etf_symbols
        # tickers (GLDM/BITW/CPER/USCI-class) stuck on "missing_sec_data"/"ebitda_not_extracted"
        # for ev_ebitda.
        if symbol in self._ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS:
            ev_ebitda_reason = "reit_special_entity"
        elif symbol in self._get_registered_investment_company_symbols():
            ev_ebitda_reason = "registered_investment_company_no_xbrl"
        elif symbol in self._get_etf_trust_no_stockholders_equity_symbols():
            ev_ebitda_reason = "etf_trust_no_gaap_financials"
        elif ebitda_raw is not None and ebitda_raw <= 0:
            ev_ebitda_reason = "unprofitable_stock"
        elif ebitda_raw is None:
            ev_ebitda_reason = "ebitda_not_extracted"
        # ebitda>0 present, enterprise_value missing or out of bounds: enterprise_value =
        # market_cap + total_debt - total_cash, so it fails whenever total_debt can't be
        # itemized - reuse the same gate quality_metrics.total_debt already uses.
        # FIXED 2026-09-06 (same sweep as ev_revenue's own fix just below in this file): the
        # windowed (exactly-3-real-years) gate alone misses recent IPOs/SPAC-mergers with fewer
        # real years where debt is nonetheless genuinely never itemized - OR in the full-history
        # sibling gate, same pattern already used elsewhere in this codebase for net_income/
        # current_assets/etc.
        elif (
            symbol in self._get_no_recent_debt_components_symbols()
            or symbol in self._get_never_tagged_debt_components_symbols()
        ):
            ev_ebitda_reason = "total_debt_not_itemized"
        elif _computed_ev_for_reason is not None and _computed_ev_for_reason <= 0:
            ev_ebitda_reason = "negative_enterprise_value"
        # ev_ebitda is one of the fields _sanity_check_market_cap nulls on a shares_outstanding
        # scale mismatch (see pb_ratio_reason below) - placed last so a real ebitda_raw<=0/
        # no-debt-itemized/negative-EV cause above still wins.
        elif row_dict.get("reason") == "shares_outstanding_scale_mismatch":
            ev_ebitda_reason = "shares_outstanding_scale_mismatch"
        # FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" follow-up, "implausible
        # values" sweep, same bug class already fixed today for pe_ratio/pb_ratio/ps_ratio/
        # ev_revenue): load_sec_valuations.py's own ev_ebitda computation silently rejects
        # any ratio outside 0..10000 (sec_valuations_yield_dcf.py's `if 0 < ev_ebitda <=
        # 10000`), but this reason chain never re-derived that bound - a real, positive
        # ebitda combined with a real, positive computed_ev can still fall outside 10000
        # (a near-zero-EBITDA blowup, same root shape as ps_ratio's near-zero-revenue-per-
        # share case) and fell through to generic "missing_sec_data" instead of
        # "implausible_ratio". Live-confirmed EFTY (implied ev_ebitda~11,973), AAOI
        # (~29,878), MHH (~55,880) - all 3 of the universe's remaining active
        # ev_ebitda "missing_sec_data" symbols besides HRI (separately fixed as a real
        # EBITDA-value bug) - SPY's ETF gap can't be fixed here at all: it has no
        # sec_valuations row, so it never reaches this per-symbol chain in the first place
        # (caught by load_value_quality_growth_metrics.py's earlier whole-row unavailable-
        # marker default instead) - confirmed live and via a failing test before removing
        # a same-shaped etf_symbols branch that would otherwise be dead code here.
        elif (
            ebitda_raw is not None
            and ebitda_raw > 0
            and _computed_ev_for_reason is not None
            and _computed_ev_for_reason > 0
            and (
                not (0 < (_computed_ev_for_reason / ebitda_raw) <= 10000)
                # FIXED 2026-09-05 (goal: "implausible values" sweep, same-day follow-up):
                # mirrors load_sec_valuations.py's own ev_ebitda EBITDA-per-share floor - a
                # real, positive EBITDA that's immaterial in absolute dollar terms (EBITDA/
                # share below $0.10, the same convention already established for EPS/BVPS/
                # RPS) implies an economically meaningless multiple even when the bare ratio
                # is technically under 10000. Live-confirmed HYNE: real $8,921 EBITDA
                # ($0.0012/share) against a real $76.3M enterprise value - ev_ebitda=8555.07,
                # in-bounds by the ceiling alone, correctly rejected by the floor.
                or (row_dict.get("shares_outstanding") and (ebitda_raw / row_dict["shares_outstanding"]) < 0.10)
            )
        ):
            ev_ebitda_reason = "implausible_ratio"
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
                # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, comprehensive
                # RIC-gap scan): royalty trusts (_ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS - NRT/
                # MTR/CRT/PBT/SBR/SJT) are the third member of this "no real cash-flow-statement
                # concepts" family alongside RIC/ETF-trust, and already get this exact
                # "reit_special_entity" recategorization in quality_metrics' fcf_margin sibling
                # chain (vqg_quality.py's royalty-trust block) - but this value_metrics chain
                # never checked it at all, unlike the RIC/ETF-trust checks just below (added
                # 2026-09-05). Live-confirmed all 6 active royalty-trust symbols stuck on
                # "missing_sec_data"/"no_recent_free_cash_flow_reported" for fcf_yield.
                "reit_special_entity"
                if symbol in self._ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS
                else "registered_investment_company_no_xbrl"
                if symbol in self._get_registered_investment_company_symbols()
                else "etf_trust_no_gaap_financials"
                if symbol in self._get_etf_trust_no_stockholders_equity_symbols()
                # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day
                # follow-up to the quality_metrics blank-check broad-loop fix): a pre-merger
                # blank-check SPAC (SIC 6770) has no real operating business - trust-account
                # interest income only, no capex/FCF concept to tag - same structural fact as
                # the RIC/ETF-trust/royalty-trust checks just above, fourth member of this "no
                # real cash-flow-statement concepts" family. Live-confirmed 16 active blank-
                # check symbols stuck on "capex_never_tagged_in_recent_filings" and 8 more on
                # "missing_sec_data" for fcf_yield alone (symbols with SOME other real value
                # computed, e.g. pe_ratio from trust interest income, so they never reached the
                # whole-row all_valuation_metrics_null fallback fixed earlier this session).
                else "no_revenue_reported"
                if symbol in self._get_blank_check_symbols()
                # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day
                # follow-up to the has_unsupported_currency_only_fact fix and its sec_
                # valuations.dcf_fcf/quality_metrics.free_cash_flow sibling recategorizations):
                # a foreign private issuer whose annual_cash_flow row was already tagged
                # "unsupported_currency_no_fx_rate" has a real, non-fabricatable ocf=None, not
                # a genuine loader gap - checked before the generic fallbacks below, same
                # priority as the RIC/ETF-trust/royalty-trust checks just above.
                else "unsupported_currency_no_fx_rate"
                if symbol in self._get_unsupported_currency_ocf_symbols()
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
                # FIXED 2026-09-07 (goal: "1600 missing XBRL" reduction sweep):
                # _get_structural_entity_type_exemptions() (broader SIC-code/entity_type CEF/
                # BDC/ETF-trust gate than the RIC/etf_trust/royalty-trust checks above, which
                # only cover their own narrower membership tests) was wired into quality_metrics
                # but never checked here. Live-confirmed 64 of 153 active-universe fcf_yield
                # "missing_sec_data" symbols are covered by this gate but fall through every
                # narrower check above to the generic fallback.
                else "entity_type_structurally_exempt_10k_filing"
                if symbol in self._get_structural_entity_type_exemptions()
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
        # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): dcf_fcf_reason is
        # preferred as "ground truth" above (see test_dcf_fcf_ground_truth_reason_preferred_
        # over_fcf_yield_20260905.py - its generic "missing_cash_flow_data" is still correctly
        # preferred over a wrong fcf_yield-based guess when fcf_yield is a real, sign-mismatched
        # value). But when fcf_yield is itself None, fcf_yield_reason_str carries a real,
        # specific cause (e.g. "registered_investment_company_no_xbrl",
        # "no_recent_free_cash_flow_reported") computed independently just above - letting the
        # generic ground-truth fallback win over THAT unconditionally blocked it from ever
        # surfacing. Live-confirmed on CURX/SLS/BTX/CEV and 300+ more universe symbols
        # (2026-09-06 DB scan): all had a specific fcf_yield reason available but were stuck on
        # the generic label solely because dcf_fcf_reason happened to equal it too.
        _specific_dcf_fcf_reason = (
            fcf_yield_reason_str
            if dcf_fcf_reason == "missing_cash_flow_data" and fcf_yield_reason_str
            else dcf_fcf_reason
        )
        intrinsic_value_reason = (
            (_specific_dcf_fcf_reason or intrinsic_value_reason_from_fcf_yield(fcf_yield, fcf_yield_reason_str))
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
                if self.MIN_PLAUSIBLE_FORWARD_PE_RATIO <= computed_forward_pe <= self.MAX_PLAUSIBLE_FORWARD_PE_RATIO:
                    forward_pe = computed_forward_pe
                elif computed_forward_pe > self.MAX_PLAUSIBLE_FORWARD_PE_RATIO:
                    logger.warning(
                        f"[VALUE_METRICS] {symbol}: forward_pe implausibly high "
                        f"({computed_forward_pe:.0f} > {self.MAX_PLAUSIBLE_FORWARD_PE_RATIO}), "
                        "excluding from Value scoring rather than storing a garbage value."
                    )
                    forward_pe_reason = "implausible_ratio"
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
            # FIXED 2026-09-07 (goal session: real-money-readiness audit): sec_valuations_
            # ratios.py's _compute_pe_ratio deliberately nulls a real, positive, plausible
            # pe_ratio when _pe_earnings_too_volatile/_pe_earnings_tax_benefit_inflated fire
            # (see those methods' own docstrings - live-confirmed BA/RILY and AES/RIGL/AXON),
            # but only logs a warning, recording no reason on the row - so this cascade, which
            # only ever sees a real positive latest_eps for these symbols, fell all the way
            # through to the generic "missing_sec_data" catch-all instead of the correct
            # "Implausible / rejected value" bucket (coverage_category_rules.py maps both
            # strings there, same bucket as eps_scale_mismatch/implausible_dcf_result above).
            # Re-derives both checks directly (same "recompute the real gate's logic here"
            # convention as every other guard in this cascade, e.g. the implausible_ratio pe/
            # pb/ps bound rechecks just below) since this loader is a different class than
            # SecValuationsLoader and has no access to its instance methods. Checked BEFORE the
            # implausible-ratio/unprofitable/never-tagged branches below: a real, in-bounds pe
            # that was excluded for earnings-quality reasons is a more specific, more accurate
            # cause than any of those generic fallbacks.
            _pe_too_volatile = False
            _pe_tax_benefit_inflated = False
            if latest_eps is not None and latest_eps > 0:
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT net_income FROM annual_income_statement
                        WHERE symbol = %s AND net_income IS NOT NULL AND data_unavailable IS NOT TRUE
                        ORDER BY fiscal_year DESC LIMIT 3
                        """,
                        (symbol,),
                    )
                    _volatility_rows = cur.fetchall()
                if len(_volatility_rows) >= 3:
                    _negative_years = sum(1 for (ni,) in _volatility_rows if ni < 0)
                    _pe_too_volatile = _negative_years >= 2
                if not _pe_too_volatile:
                    with _owner().DatabaseContext("read") as cur:
                        cur.execute(
                            """
                            SELECT pretax_income, income_tax_expense FROM annual_income_statement
                            WHERE symbol = %s AND pretax_income IS NOT NULL AND income_tax_expense IS NOT NULL
                              AND data_unavailable IS NOT TRUE
                            ORDER BY fiscal_year DESC LIMIT 1
                            """,
                            (symbol,),
                        )
                        _tax_row = cur.fetchone()
                    if _tax_row and len(_tax_row) == 2:
                        _pretax_income, _income_tax_expense = _tax_row
                        if _pretax_income is not None and _pretax_income > 0:
                            _pretax_f = float(_pretax_income)
                            _tax_f = float(_income_tax_expense)
                            _pe_tax_benefit_inflated = _tax_f < 0 and abs(_tax_f) >= 0.30 * _pretax_f
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
                "pe_earnings_too_volatile"
                if _pe_too_volatile
                else "pe_earnings_tax_benefit_inflated"
                if _pe_tax_benefit_inflated
                else "implausible_ratio"
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
                # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): registered
                # investment companies (closed-end funds, commodity trusts) file no 10-K/10-Q
                # and have no EPS by their fund/trust structure - same "no GAAP earnings_per_share
                # concept" fact as blank-check SPACs. Missing RIC gate lets these fall through to
                # generic "missing_sec_data" instead of correct "Legitimate / not applicable"
                # categorization. Live-confirmed via CEF symbols in value_metrics with 71 cases
                # of pe_ratio missing_sec_data where RIC check would resolve to
                # registered_investment_company_no_xbrl. Checked BEFORE generic fallback, same
                # priority pattern as fcf_yield and other value_metrics fields.
                else "registered_investment_company_no_xbrl"
                if symbol in self._get_registered_investment_company_symbols()
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
            # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): only pay for this
            # second query on the rare symbols with explosive apparent growth - same cheap-
            # pre-filter discipline sec_valuations_ratios.py's own _compute_peg_ratio uses
            # before it does the identical query to detect a low-base trough year. See
            # peg_ratio_reason_from_eps_history()'s own docstring for why this is needed at
            # all: without it, the low-base-effect rejection this mirrors falls through to
            # "missing_sec_data" instead of "peg_ratio_low_base_effect".
            other_positive_eps: list[float] | None = None
            if len(eps_rows) >= 2:
                ttm_eps_for_growth, prior_eps_for_growth = eps_rows[0][1], eps_rows[1][1]
                if (
                    prior_eps_for_growth is not None
                    and prior_eps_for_growth > 0
                    and ttm_eps_for_growth is not None
                    and ((ttm_eps_for_growth - prior_eps_for_growth) / abs(prior_eps_for_growth)) * 100 > 300
                ):
                    with _owner().DatabaseContext("read") as cur:
                        cur.execute(
                            """
                            SELECT earnings_per_share FROM annual_income_statement
                            WHERE symbol = %s AND earnings_per_share IS NOT NULL
                              AND earnings_per_share > 0 AND data_unavailable IS NOT TRUE
                            ORDER BY fiscal_year DESC
                            """,
                            (symbol,),
                        )
                        other_positive_eps = [
                            float(r[0]) for r in cur.fetchall() if float(r[0]) != prior_eps_for_growth
                        ]
            peg_ratio_reason = peg_ratio_reason_from_eps_history(eps_rows, other_positive_eps)
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
                # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day
                # follow-up to pe_ratio missing RIC gate fix): RICs file no 10-K/10-Q and have
                # no balance-sheet StockholdersEquity concept by their structure - same gate
                # pattern as pe_ratio. Checked BEFORE generic fallback.
                else "registered_investment_company_no_xbrl"
                if symbol in self._get_registered_investment_company_symbols()
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
                    # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day
                    # follow-up to pe_ratio/pb_ratio missing RIC gate fixes): RICs file no 10-K/10-Q
                    # and have no revenue reporting obligation - same structural gap. Checked BEFORE
                    # generic fallback.
                    else "registered_investment_company_no_xbrl"
                    if symbol in self._get_registered_investment_company_symbols()
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
                    # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): a
                    # registered investment company (see _get_registered_investment_company_
                    # symbols()' docstring) files no GAAP revenue/EV concepts at all - same
                    # structural fact already recategorized for total_debt/roic_pct/debt_to_
                    # equity and this file's own fcf_yield chain above. Live-confirmed SPMC:
                    # unlike SPY (dead-code case ruled out just below, no sec_valuations row at
                    # all), SPMC has a real row and was falling through this whole chain to the
                    # generic "missing_sec_data" (Missing SEC/XBRL data) instead of the correct
                    # "Legitimate / not applicable" label.
                    "registered_investment_company_no_xbrl"
                    if symbol in self._get_registered_investment_company_symbols()
                    else "no_revenue_reported"
                    if symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                    # enterprise_value = market_cap + total_debt - total_cash, so it fails
                    # whenever total_debt can't be itemized even when revenue is present.
                    # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): only the
                    # windowed (exactly-3-real-years) gate was checked here, missing the same
                    # "recent IPO/SPAC-merger with fewer real years" population every other
                    # never-tagged-sibling check in this file OR's in - live-verified 6
                    # additional active-universe rows recovered from the generic
                    # "missing_sec_data" catch-all.
                    else "total_debt_not_itemized"
                    if symbol in self._get_no_recent_debt_components_symbols()
                    or symbol in self._get_never_tagged_debt_components_symbols()
                    # Net cash exceeds market_cap + total_debt - see _computed_ev_for_reason.
                    else "negative_enterprise_value"
                    if _computed_ev_for_reason is not None and _computed_ev_for_reason <= 0
                    # Real $0 anchor-year revenue, distinct from "never any revenue" above.
                    else "zero_revenue_reported_this_period"
                    if symbol in self._get_zero_revenue_anchor_symbols()
                    # Real revenue exists in an earlier year, just not the current anchor year.
                    else "revenue_absent_from_anchor_year"
                    if symbol in self._get_revenue_absent_from_anchor_year_symbols()
                    # FIXED 2026-09-05 (goal session: "implausible values" sweep): load_sec_
                    # valuations.py's own ev_revenue computation now rejects a real revenue-per-
                    # share below MIN_PLAUSIBLE_PS_RATIO's $0.10 floor (same fix as ps_ratio,
                    # which divides by the identical ttm_revenue) - reuse ps_ratio's own
                    # implausibility check computed above rather than a second DB round-trip,
                    # since the two share the exact same real economic cause.
                    else "implausible_ratio"
                    if _ps_implausible_ratio
                    # ev_revenue is one of the fields _sanity_check_market_cap nulls on a shares-
                    # outstanding scale mismatch; placed last so a real revenue-shaped cause wins.
                    # NOTE: an etf_symbols fallback here (mirroring total_debt/total_cash's fix
                    # in vqg_quality.py) was considered and dropped - SPY (the only active
                    # symbol hitting this reason) has no sec_valuations row at all, so it never
                    # reaches this per-symbol chain in the first place (caught by
                    # load_value_quality_growth_metrics.py's earlier whole-row unavailable-
                    # marker default instead); confirmed via a failing test before removing what
                    # would otherwise be dead code.
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
