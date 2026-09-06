"""FCF/dividend/net-payout yield, enterprise-value multiples, and the DCF intrinsic-value glue
for SecValuationsLoader._compute_valuations, extracted from load_sec_valuations.py (2026-09-05,
file-size ratchet: that file is one of the Tier-1 bloaters flagged for decomposition, see
MEMORY.md's bloater_decomposition_strategy_20260905). Kept as ONE cohesive method (not split
further per-field) because these fields share mutable local state across the whole block -
`entity_market_cap` feeds fcf_yield/dividend_yield/net_payout_yield/enterprise_value, and
`fcf_base`/`dcf_fcf_base` thread from the FCF-yield calc into the DCF call - splitting further
would mean either duplicating that derivation per method or passing it in twice, more
error-prone than the fewer/larger split used here for pe/pb/ps/peg's independent ratios (see
sec_valuations_ratios.py). Logic is byte-for-byte verbatim (only the `result["x"] = ...`
assignments became a dict this method returns, and mid-block reads of `result["market_cap"]`/
`result["enterprise_value"]` became local variables) - mixed into SecValuationsLoader, which
still defines every MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO/DCF_NET_BORROWING_MAX_FCF_MULTIPLE/
DCF_NET_BORROWING_MIN_RETAINED_FRACTION class constant and _compute_dcf_intrinsic_value method
(from DcfValuationMixin) this method reads/calls via `self`, so behavior is unchanged.
"""

import logging
from typing import TYPE_CHECKING, Any

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class SecValuationYieldDcfMixin:
    """FCF/dividend/net-payout yield, EV/EBITDA, EV/Revenue, and DCF intrinsic-value/margin-of-
    safety computation for SecValuationsLoader. Not usable standalone - relies on class
    constants and the _compute_dcf_intrinsic_value method defined on SecValuationsLoader
    itself (the latter via DcfValuationMixin).
    """

    # Type-only declarations (no values) so mypy resolves the `self.X` reads below - the real
    # values are class constants/methods defined on SecValuationsLoader, the only class this
    # mixin is ever combined with.
    MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO: float
    DCF_NET_BORROWING_MAX_FCF_MULTIPLE: float
    DCF_NET_BORROWING_MIN_RETAINED_FRACTION: float
    MIN_PLAUSIBLE_PS_RATIO: float

    # Type-only declaration, TYPE_CHECKING-only so it exists for mypy but never shadows the
    # real method at runtime - the real implementation lives on DcfValuationMixin, which
    # SecValuationsLoader also mixes in (and lists before this mixin, so MRO would find the
    # real one first regardless - TYPE_CHECKING keeps that a non-issue either way).
    if TYPE_CHECKING:

        def _compute_dcf_intrinsic_value(
            self,
            symbol: str,
            fcf: float | None,
            eps_growth_pct: float | None,
            shares_out: float | None,
            current_price: float | None,
            beta: float | None = None,
            risk_free_rate: float | None = None,
            equity_risk_premium: float | None = None,
        ) -> tuple[float | None, float | None]: ...

    def _compute_yield_and_dcf_fields(  # noqa: C901 -- pre-existing complexity debt, moved verbatim from _compute_valuations, not introduced by this extraction
        self,
        symbol: str,
        current_price: float,
        market_cap: float | None,
        ttm_eps: float | None,
        ttm_revenue: float | None,
        ocf: float | None,
        capex: float | None,
        prior_year_eps: float | None,
        dividends_paid: float | None,
        total_debt: float | None,
        total_cash: float | None,
        ebitda: float | None,
        avg_fcf_fallback: float | None,
        beta: float | None,
        risk_free_rate: float | None,
        entity_shares_out: float | None,
        stock_based_compensation: float | None,
        dcf_eps_cagr_pct: float | None,
        equity_risk_premium: float | None,
        net_borrowing: float | None,
        common_stock_repurchased: float | None,
    ) -> dict[str, Any]:
        """Compute fcf_yield, dividend_yield, net_payout_yield, enterprise_value, ev_ebitda,
        ev_revenue, intrinsic_value_per_share, margin_of_safety_pct, and
        dcf_fcf_unavailable_reason - moved verbatim out of _compute_valuations. `market_cap` is
        that method's already-computed `result["market_cap"]` (current_price x this ticker's
        own, possibly class-specific, shares_out); every other parameter is unchanged from
        _compute_valuations' own signature. Returns a dict with exactly those 9 keys, all
        possibly None - the caller merges it into its own `result` dict.
        """
        # Local import (not module-level): load_sec_valuations.py imports this mixin before
        # MAX_ABSOLUTE_DOLLAR_VALUE is defined further down in its own source, and this module
        # is imported BY load_sec_valuations.py, so a module-level import here would be a true
        # circular import - same fix already applied in
        # SharesOutstandingResolutionMixin._resolve_shares_outstanding for
        # DUAL_CLASS_NO_SEPARATOR_ROOTS, and in ValuationSanityCheckMixin._sanity_check_market_cap
        # for the same reason.
        from loaders.load_sec_valuations import MAX_ABSOLUTE_DOLLAR_VALUE

        result: dict[str, Any] = {
            "fcf_yield": None,
            "dividend_yield": None,
            "net_payout_yield": None,
            "enterprise_value": None,
            "ev_ebitda": None,
            "ev_revenue": None,
            "intrinsic_value_per_share": None,
            "margin_of_safety_pct": None,
            "dcf_fcf_unavailable_reason": None,
        }

        # FCF Yield = Free Cash Flow ÷ Market Cap
        # FCF = Operating Cash Flow - Capital Expenditures - Stock-Based Compensation
        #
        # FIXED 2026-08-25 (goal: "finance best practices" methodology audit): OCF already
        # adds SBC back as a non-cash expense, but SBC is a real economic cost via future
        # dilution ("Owner Earnings" convention - see _compute_avg_fcf_fallback's docstring
        # for the full rationale). Treated as 0 when None (most non-SBC filers simply don't
        # tag the concept - unlike capex, whose None/timing-lag handling is the FIXED comment
        # immediately below).
        #
        # FIXED 2026-08-22 (goal session - coverage-bucket root-cause audit): `ocf`/`capex`
        # here are always the SINGLE latest fiscal_year row (fetch_incremental's `cash_rows[0]`)
        # - for the current, still-open fiscal year (e.g. 2026 while that year is in progress),
        # a full-year capex figure genuinely hasn't been filed yet, so capex is None and this
        # unconditionally left fcf_yield NULL even when the immediately preceding COMPLETE
        # fiscal year had perfectly good ocf/capex on file. Live-confirmed: BAX, VTR, STM, CWT,
        # FAF, UMH, ESE, MWA (and ~1574 symbols universe-wide, ~30% of the tracked universe) -
        # all real, established companies with a real, complete prior-year FCF figure already in
        # annual_cash_flow - permanently NULL here purely because the current interim year's
        # capex isn't tagged yet. Same "current partial year masks real prior-year data" bug
        # class already fixed for margin_of_safety/intrinsic_value_per_share via
        # `avg_fcf_fallback` (see fcf_base a few lines below) - that fallback was computed and
        # passed into this function all along, just never wired up for fcf_yield itself.
        sbc = 0.0 if stock_based_compensation is None else stock_based_compensation
        fcf = ocf - capex - sbc if ocf is not None and capex is not None else None
        if fcf is None and avg_fcf_fallback is not None:
            fcf = avg_fcf_fallback
        # FIXED 2026-08-25 (dual-class entity-wide-FCF fix, see entity_shares_out_for_fcf's
        # definition above): fcf is entity-wide, so it must be paired with an entity-wide
        # market cap (current_price x entity_shares_out_for_fcf), not result["market_cap"]
        # (current_price x this ticker's own class-specific shares_out) - otherwise a minority
        # share class's fcf_yield is inflated by the same ratio its share count understates the
        # full entity (live-confirmed: TAP.A was 936%, should read close to TAP's own ~14%).
        entity_market_cap = current_price * entity_shares_out if entity_shares_out else None
        if fcf is not None and entity_market_cap and entity_market_cap > 0:
            fcf_yield_pct = (fcf / entity_market_cap) * 100
            # Only store if within reasonable bounds (-1000% to +1000%)
            # Extreme values indicate data errors or tiny market caps
            if -1000 <= fcf_yield_pct <= 1000:
                result["fcf_yield"] = round(fcf_yield_pct, 2)
            else:
                logger.debug(f"[{symbol}] FCF yield out of bounds ({fcf_yield_pct:.1f}%), marking as NULL")

        # Dividend Yield = Dividends Paid ÷ Market Cap (stored as a decimal fraction, e.g.
        # 0.03 = 3% - matches load_stock_scores.py._score_value's existing "decimal ->
        # percent" conversion for this field; NOT the same convention as fcf_yield above,
        # which is stored as a percentage already).
        # FIXED 2026-08-25 (same dual-class entity-wide fix as fcf_yield above):
        # dividends_paid is the entity-wide total dollar amount from the cash flow statement
        # (no per-class breakdown exists in SEC data, same as ocf/capex) - paired with
        # entity_market_cap for the same reason fcf_yield was, otherwise a minority class's
        # dividend_yield is inflated the same way fcf_yield was.
        if dividends_paid and dividends_paid > 0 and entity_market_cap and entity_market_cap > 0:
            div_yield = dividends_paid / entity_market_cap
            if 0 < div_yield <= self.MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO:
                result["dividend_yield"] = round(div_yield, 4)
            else:
                logger.debug(f"[{symbol}] Dividend yield out of bounds ({div_yield:.2%}), marking as NULL")

        # Net Payout (Shareholder) Yield = (Dividends Paid + Buybacks) ÷ Market Cap - ADDED
        # 2026-08-26 (goal: full Value pillar re-audit). Same decimal-fraction convention as
        # dividend_yield above (0.03 = 3%), same entity-wide-market-cap dual-class pairing.
        # "Total payout yield" (Boudoukh/Michaely/Richardson/Roberts 2007) / O'Shaughnessy's
        # "Shareholder Yield" - captures buybacks alongside dividends, which dividend_yield
        # alone misses (most large-cap US firms have shifted a meaningful share of shareholder
        # returns to buybacks since the 1980s). Own Fama-MacBeth validation
        # (algo/research/fama_macbeth_value_factors.py, 2026-08-26): univariate t=3.27,
        # multivariate t=3.05 (jointly with the live Value inputs) - stronger than
        # dividend_yield's own t=1.55-2.28, and dividend_yield's own multivariate coefficient
        # flips negative once net_payout_yield is present (its positive univariate signal was
        # actually payout information net_payout_yield now captures better). common_stock_
        # repurchased defaults to None for backward-compat callers/tests - net_payout_yield
        # then reduces to dividends-only (same number dividend_yield computes), never worse
        # than not having this field at all.
        buyback = 0.0 if common_stock_repurchased is None else abs(common_stock_repurchased)
        dividends = 0.0 if dividends_paid is None or dividends_paid <= 0 else dividends_paid
        total_payout = dividends + buyback
        if total_payout > 0 and entity_market_cap and entity_market_cap > 0:
            payout_yield = total_payout / entity_market_cap
            # BOUND TIGHTENED 150%->50% same day, later pass: live-confirmed DDT still passed
            # this gate at a real, non-broken market cap ($412M, real ~15.6M shares) with a
            # 143.82% payout yield - not the shares-outstanding-scale bug the equivalent
            # load_value_quality_growth_metrics.py fallback bound was tightened for, more
            # likely a raw common_stock_repurchased extraction issue (e.g. a multi-year figure
            # picked up as one year's), but the same "no real company legitimately buys back +
            # dividends more than half its market cap in a year" bound catches it regardless of
            # root cause - kept consistent with that fallback's now-50% bound rather than
            # leaving this (more-trusted) path more permissive for no principled reason.
            if 0 < payout_yield <= 0.5:
                result["net_payout_yield"] = round(payout_yield, 4)
            else:
                logger.debug(f"[{symbol}] Net payout yield out of bounds ({payout_yield:.2%}), marking as NULL")

        # Enterprise Value = Market Cap + Total Debt - Cash & Equivalents
        # FIXED 2026-08-25 (same dual-class entity-wide fix as fcf_yield above): total_debt/
        # total_cash are entity-wide (balance sheet has no per-class breakdown), so pairing
        # them with a class-specific market_cap understated EV for a minority class the same
        # way it inflated fcf_yield/the DCF - EV/EBITDA and EV/Revenue (both entity-wide
        # ebitda/revenue) inherited the distortion. entity_market_cap (current_price x
        # entity-wide shares) is also just the more standard definition of "enterprise value
        # of the company" to begin with - EV is conceptually a whole-company figure, not a
        # single share class's. Falls back to result["market_cap"] only in the pathological
        # case entity_market_cap is unset (current_price/shares_out themselves missing,
        # which already guards result["market_cap"] being None above).
        if market_cap is not None:
            equity_val = entity_market_cap if entity_market_cap else market_cap
            debt_val = total_debt if total_debt else 0
            cash_val = total_cash if total_cash else 0
            ev = equity_val + debt_val - cash_val
            if ev > 0 and abs(ev) < MAX_ABSOLUTE_DOLLAR_VALUE:
                result["enterprise_value"] = round(ev, 2)
            else:
                logger.debug(f"[{symbol}] Enterprise value non-positive or implausible ({ev:.0f}), marking as NULL")

        # EV / EBITDA Ratio
        #
        # FIXED 2026-09-05 (goal session: "implausible values" sweep, same bug class as
        # ev_revenue/pe_ratio/pb_ratio/ps_ratio just below/above): the bare 0..10000 ceiling
        # doesn't catch a real, positive EBITDA that's simply immaterial in absolute dollar
        # terms - unlike revenue/book-value/EPS, EBITDA has no natural "per-something"
        # denominator of its own, but a real company's EBITDA-per-share below the same $0.10
        # floor already established for EPS/BVPS/RPS is exactly as economically meaningless a
        # multiple. Live-confirmed HYNE: real $8,921 EBITDA (EBITDA/share=$0.0012) against a
        # real $76.3M enterprise value - ev_ebitda=8555.07, technically under 10000, accepted
        # as valid. Same shape confirmed for MAGH/QRHC/MCTA/WYFI/MAMK/EVN/GORO/OIO (all real
        # EBITDA-per-share well under $0.01). Reuses the established $0.10 convention rather
        # than inventing a new threshold.
        if result["enterprise_value"] and ebitda and ebitda > 0:
            ev_ebitda = result["enterprise_value"] / ebitda
            _ev_ebitda_per_share_ok = entity_shares_out is None or (ebitda / entity_shares_out) >= 0.10
            if 0 < ev_ebitda <= 10000 and _ev_ebitda_per_share_ok:
                result["ev_ebitda"] = round(ev_ebitda, 2)
            else:
                logger.debug(f"[{symbol}] EV/EBITDA out of bounds ({ev_ebitda:.0f}), marking as NULL")

        # EV / Revenue Ratio
        #
        # FIXED 2026-09-05 (goal session: "implausible values" sweep): the bare 0..10000 bound
        # is the same ceiling ps_ratio uses (both divide by the identical ttm_revenue), but
        # this never got ps_ratio's OTHER real rejection criterion - a real revenue-per-share
        # below $0.10 (MIN_PLAUSIBLE_PS_RATIO's sibling floor) implies an economically
        # meaningless EV/Revenue multiple that's nonetheless technically under 10000. Live-
        # confirmed ABSI (Absci Corp): real FY2025 revenue $2.8M against 136.8M shares =
        # $0.0205/share - the exact same tiny-revenue-per-share shape ps_ratio's own fix
        # rejects, yet ev_revenue=425.28 (a real number, computed correctly, just not a
        # meaningful valuation multiple) was accepted here on the same row ps_ratio was
        # correctly nulled on. Reuses ps_ratio's own $0.10 floor rather than inventing a new
        # threshold - same revenue, same real economic problem, same fix.
        if result["enterprise_value"] and ttm_revenue and ttm_revenue > 0:
            ev_revenue = result["enterprise_value"] / ttm_revenue
            # entity_shares_out unavailable is a genuinely separate, rarer gap (already covered
            # by ev_revenue_unavailable_reason's own shares_outstanding_scale_mismatch/missing
            # handling elsewhere) - only apply the extra per-share floor when a real share count
            # exists to check it against, same "don't demand data this computation doesn't
            # fundamentally need" discipline as everywhere else in this codebase.
            _ev_revenue_per_share_ok = entity_shares_out is None or (ttm_revenue / entity_shares_out) >= 0.10
            if 0 < ev_revenue <= 10000 and _ev_revenue_per_share_ok:
                result["ev_revenue"] = round(ev_revenue, 2)
            else:
                logger.debug(f"[{symbol}] EV/Revenue out of bounds ({ev_revenue:.0f}), marking as NULL")

        # Intrinsic Value / Margin of Safety: 2-stage FCFE DCF (migration 1208, Value factor
        # goal 2026-08-17). Reuses the same FCF base (OCF - CapEx - SBC, see the 2026-08-25
        # "finance best practices" fix on fcf_yield above) as FCF yield above so this
        # stays consistent with the other value metrics instead of introducing a second FCF
        # definition. Growth basis: the same YoY EPS delta peg_ratio uses, UNLESS a multi-year
        # EPS CAGR is available (dcf_eps_cagr_pct - see _compute_multi_year_eps_cagr), which is
        # preferred for the DCF specifically since it smooths past a one-off blip in either
        # endpoint year the way avg_fcf_fallback already does for FCF - peg_ratio's own
        # growth_rate above is untouched, it deliberately stays single-year (see that
        # calculation's own comment). See _compute_dcf_intrinsic_value for why a missing/
        # unusable growth rate defaults to flat 0%/yr here instead of blocking the DCF the way
        # peg_ratio is blocked.
        # FIXED 2026-08-18 (coverage): a single negative-FCF year (capex-heavy or cash-flow-
        # lumpy, common for real capital-intensive/cyclical businesses) used to zero out the
        # DCF outright even when the company is normally FCF-positive. Standard DCF practice
        # normalizes FCF over multiple years for exactly this reason - fall back to the
        # 3-year average FCF (fetch_incremental's avg_fcf_fallback) only when the latest
        # year alone is unusable and the multi-year average is positive; fcf_yield above is
        # deliberately left on the latest year only (it's meant to reflect current cash
        # generation, not a smoothed figure).
        fcf_base = ocf - capex - sbc if ocf is not None and capex is not None else None
        if (fcf_base is None or fcf_base <= 0) and avg_fcf_fallback is not None and avg_fcf_fallback > 0:
            fcf_base = avg_fcf_fallback
        # net_borrowing (see this parameter's own docstring above): DCF-only additive
        # correction toward a true FCFE, never applied to fcf_yield above. Bounded to
        # DCF_NET_BORROWING_MAX_FCF_MULTIPLE x |fcf_base| - see that constant's docstring
        # (BWXT live-caught data-quality outlier) - an implausibly large net_borrowing relative
        # to the entity's own cash-flow scale is silently skipped (falls back to fcf_base
        # unadjusted) rather than corrupting the DCF with what's almost certainly bad
        # upstream balance-sheet data, not a genuine financing event.
        dcf_fcf_base = fcf_base
        # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): distinguishes "fcf_base
        # itself was never computable" from "fcf_base was real but the net-borrowing distortion
        # check below nulled dcf_fcf_base anyway" - live-confirmed CASH/TRN and 170 of 384
        # universe-wide dcf_fcf_unavailable_reason='missing_cash_flow_data' rows have a real,
        # positive fcf_base (proven by their own real, non-NULL fcf_yield, which is computed from
        # the SAME fcf_base before any net-borrowing adjustment) - the cash-flow data was never
        # missing at all, only the DCF-specific near-cancellation guard two lines below rejected
        # it. The reason block further down used to test only `dcf_fcf_base is None`, which can't
        # tell these two causes apart, so it mislabeled every one of these 170 as a genuine SEC/
        # XBRL data gap instead of the deliberate methodology choice it actually is.
        dcf_fcf_nulled_by_net_borrowing = False
        if (
            fcf_base is not None
            and net_borrowing is not None
            and fcf_base != 0
            and abs(net_borrowing) <= self.DCF_NET_BORROWING_MAX_FCF_MULTIPLE * abs(fcf_base)
        ):
            candidate_fcf_base = fcf_base + net_borrowing
            # See DCF_NET_BORROWING_MIN_RETAINED_FRACTION's docstring above (IMMR live
            # evidence): a candidate that's still positive but has been nearly cancelled out
            # by net_borrowing must be treated the same as a full negative flip - null the DCF
            # (fcf=None hits the same `fcf is None` gate _compute_dcf_intrinsic_value already
            # uses for `fcf <= 0`) rather than anchor a multi-year perpetuity on a near-zero,
            # one-time-financing-event-distorted base. A genuine negative flip is unaffected
            # (falls through to the else branch unchanged, still caught by that same gate).
            if fcf_base > 0 and 0 < candidate_fcf_base < self.DCF_NET_BORROWING_MIN_RETAINED_FRACTION * fcf_base:
                dcf_fcf_base = None
                dcf_fcf_nulled_by_net_borrowing = True
            else:
                dcf_fcf_base = candidate_fcf_base
        eps_growth_pct = None
        if prior_year_eps is not None and prior_year_eps != 0 and ttm_eps is not None:
            eps_growth_pct = ((ttm_eps - prior_year_eps) / abs(prior_year_eps)) * 100
        dcf_growth_pct = dcf_eps_cagr_pct if dcf_eps_cagr_pct is not None else eps_growth_pct
        # entity_shares_out (not shares_out): fcf_base is entity-wide, same reasoning as
        # fcf_yield's entity_market_cap fix just above.
        result["intrinsic_value_per_share"], result["margin_of_safety_pct"] = self._compute_dcf_intrinsic_value(
            symbol,
            dcf_fcf_base,
            dcf_growth_pct,
            entity_shares_out,
            current_price,
            beta,
            risk_free_rate,
            equity_risk_premium,
        )
        # Ground-truth reason for WHY the DCF's own fcf input was unusable, recorded here where
        # dcf_fcf_base's real value is known - see migration 1258's docstring for the full
        # rationale (fcf_yield's own FCF base never receives the net-borrowing adjustment
        # dcf_fcf_base does, so it can have the opposite sign and mislead a downstream reason
        # guess). Only meaningful when intrinsic_value_per_share came back NULL; a real
        # computed value needs no reason.
        if result["intrinsic_value_per_share"] is None:
            if dcf_fcf_base is None and dcf_fcf_nulled_by_net_borrowing:
                # ADDED 2026-09-06 (see dcf_fcf_nulled_by_net_borrowing's own comment above):
                # fcf_base was real here - this isn't a data gap, it's the DCF deliberately
                # declining to anchor a perpetuity on a base a one-time financing event nearly
                # cancelled out. Same "computed but rejected as implausible" class as
                # implausible_dcf_result below, not "Missing SEC/XBRL data".
                result["dcf_fcf_unavailable_reason"] = "dcf_fcf_nulled_by_net_borrowing_distortion"
            elif dcf_fcf_base is None:
                # FIXED 2026-09-05 (goal session: "implausible values" sweep): a REIT (SIC
                # 6798) or insurance carrier (SIC 6311/6321/6331/6351/6361/6399) structurally
                # never tags a meaningful capex figure the way an operating company does -
                # same real business-model fact already recognized for quality_metrics' own
                # "reit_special_entity" label throughout vqg_quality.py (see sec_base.py's
                # _get_reit_symbols/_get_insurance_symbols for the identical SIC-code
                # rationale) - this DCF ground-truth reason never checked for it, so these
                # fell to the generic "missing_cash_flow_data" instead of the same
                # "Legitimate / not applicable" label the rest of the codebase already gives
                # this exact entity-type fact. Queried directly here (not via
                # sec_base.py's bulk-cached helpers) since SecValuationsLoader doesn't mix in
                # that class - this branch is only reached for the rare missing-fcf-base
                # case, not once per symbol.
                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT sic_code FROM company_info_sec WHERE symbol = %s",
                        (symbol,),
                    )
                    sic_row = cur.fetchone()
                sic_code = sic_row[0] if sic_row else None
                result["dcf_fcf_unavailable_reason"] = (
                    "reit_special_entity"
                    if sic_code in (6798, 6311, 6321, 6331, 6351, 6361, 6399)
                    else "missing_cash_flow_data"
                )
            elif dcf_fcf_base <= 0:
                result["dcf_fcf_unavailable_reason"] = "negative_free_cash_flow"
            else:
                result["dcf_fcf_unavailable_reason"] = "implausible_dcf_result"

        return result
