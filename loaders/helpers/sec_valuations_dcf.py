"""DCF valuation math for SecValuationsLoader, extracted from load_sec_valuations.py
(2026-09-05, file-size ratchet: that file is one of the Tier-1 bloaters flagged for
decomposition). Methods are verbatim, no logic changed - mixed into SecValuationsLoader,
which still defines every DCF_*/MIN_INTRINSIC_VALUE_PER_SHARE/MAX_INTRINSIC_VALUE_PER_SHARE
class constant and _risk_free_rate_cache/_equity_risk_premium_cache instance attribute these
methods read via `self`, so behavior is unchanged - only the method bodies moved file.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DcfValuationMixin:
    """DCF discount-rate, growth-driver, and intrinsic-value computation methods for
    SecValuationsLoader. Not usable standalone - relies on class constants and cache
    attributes defined on SecValuationsLoader itself.
    """

    # Type-only declarations (no values) so mypy resolves the `self.X` reads below - the real
    # values are class constants/instance attributes defined on SecValuationsLoader, the only
    # class this mixin is ever combined with.
    DCF_DEFAULT_RISK_FREE_RATE: float
    DCF_EQUITY_RISK_PREMIUM: float
    DCF_DEFAULT_BETA: float
    DCF_BLUME_ADJUSTMENT_WEIGHT: float
    DCF_MIN_EQUITY_RISK_PREMIUM_APPLIED: float
    DCF_TERMINAL_GROWTH_RATE: float
    DCF_MIN_DISCOUNT_TERMINAL_SPREAD: float
    DCF_MAX_DISCOUNT_RATE: float
    DCF_VIX_LOOKBACK_YEARS: int
    DCF_MIN_EQUITY_RISK_PREMIUM: float
    DCF_MAX_EQUITY_RISK_PREMIUM: float
    DCF_GROWTH_FLOOR: float
    DCF_GROWTH_CEILING: float
    DCF_FORECAST_YEARS: int
    MIN_INTRINSIC_VALUE_PER_SHARE: float
    MAX_INTRINSIC_VALUE_PER_SHARE: float
    _risk_free_rate_cache: float | None
    _equity_risk_premium_cache: float | None

    def _compute_discount_rate(
        self,
        beta: float | None,
        risk_free_rate: float | None,
        equity_risk_premium: float | None = None,
    ) -> float:
        """CAPM cost of equity: risk_free_rate + Blume-adjusted-beta x equity_risk_premium.

        Replaces the old flat 10%/yr DCF_DISCOUNT_RATE (see its removal comment above) with a
        risk-adjusted rate so a high-beta, high-risk name gets a real risk-adjusted cost of
        capital instead of borrowing a safe/average company's discount rate (which would
        systematically overstate its intrinsic value), and vice versa for a genuinely
        low-risk name.

        equity_risk_premium: ADDED 2026-08-25 (goal: DCF audit follow-up - dynamic ERP, see
        DCF_MIN_EQUITY_RISK_PREMIUM's docstring above for the full rationale/derivation).
        Defaults to None -> DCF_EQUITY_RISK_PREMIUM (the static 5% anchor), so every existing
        caller/test that only passes beta/risk_free_rate keeps computing the exact same rate
        as before. Live calls from _compute_valuations pass the VIX-scaled dynamic value from
        _get_equity_risk_premium().
        """
        rfr = self.DCF_DEFAULT_RISK_FREE_RATE if risk_free_rate is None else risk_free_rate
        erp = self.DCF_EQUITY_RISK_PREMIUM if equity_risk_premium is None else equity_risk_premium
        raw_beta = self.DCF_DEFAULT_BETA if beta is None else beta
        adjusted_beta = self.DCF_BLUME_ADJUSTMENT_WEIGHT * raw_beta + (1 - self.DCF_BLUME_ADJUSTMENT_WEIGHT) * 1.0
        rate = rfr + adjusted_beta * erp
        floor = max(
            rfr + self.DCF_MIN_EQUITY_RISK_PREMIUM_APPLIED,
            self.DCF_TERMINAL_GROWTH_RATE + self.DCF_MIN_DISCOUNT_TERMINAL_SPREAD,
        )
        return max(floor, min(self.DCF_MAX_DISCOUNT_RATE, rate))

    def _get_risk_free_rate(self, cur: Any) -> float:
        """Live 10-year Treasury yield (economic_data.DGS10) as the CAPM risk-free rate.

        Cached on the instance for the lifetime of this loader run - this doesn't change
        intra-day and querying it once per symbol (5,000+ times a run) would be pure waste.
        Falls back to the most recent reading within 10 days (FRED doesn't publish on
        weekends/holidays) rather than requiring an exact today's-date row, and to
        DCF_DEFAULT_RISK_FREE_RATE on the rare day even that's unavailable.
        """
        if self._risk_free_rate_cache is not None:
            return self._risk_free_rate_cache
        cur.execute(
            """
            SELECT value FROM economic_data
            WHERE series_id = 'DGS10' AND date >= CURRENT_DATE - INTERVAL '10 days' AND value IS NOT NULL
            ORDER BY date DESC LIMIT 1
            """
        )
        row = cur.fetchone()
        # DGS10 is published as a percentage (e.g. 4.71 meaning 4.71%) - convert to decimal.
        self._risk_free_rate_cache = (
            float(row[0]) / 100.0 if row and row[0] is not None else self.DCF_DEFAULT_RISK_FREE_RATE
        )
        return self._risk_free_rate_cache

    def _get_equity_risk_premium(self, cur: Any) -> float:
        """VIX-scaled dynamic equity risk premium: DCF_EQUITY_RISK_PREMIUM x (current VIX /
        long-run average VIX), clamped to [DCF_MIN_EQUITY_RISK_PREMIUM, DCF_MAX_EQUITY_RISK_
        PREMIUM] - see that constant's docstring above for the full derivation (why VIX, why
        those bounds, why not a trailing-realized-return premium instead).

        Cached on the instance for the lifetime of this loader run, same rationale as
        _get_risk_free_rate immediately above. Falls back to the most recent VIXCLS reading
        within 90 days (live-checked: this DB's VIXCLS feed runs ~60 days behind CURRENT_DATE,
        well past DGS10's ~4-day lag - a tight window here would silently fall back to the
        static default on every single run, defeating the point) rather than requiring an
        exact today's-date row. Falls back to DCF_EQUITY_RISK_PREMIUM outright when either the
        current reading or the long-run average is unavailable (new/empty economic_data table,
        e.g. in a fresh test DB).
        """
        if self._equity_risk_premium_cache is not None:
            return self._equity_risk_premium_cache
        cur.execute(
            """
            SELECT value FROM economic_data
            WHERE series_id = 'VIXCLS' AND date >= CURRENT_DATE - INTERVAL '90 days' AND value IS NOT NULL
            ORDER BY date DESC LIMIT 1
            """
        )
        current_row = cur.fetchone()
        cur.execute(
            """
            SELECT AVG(value) FROM economic_data
            WHERE series_id = 'VIXCLS' AND date >= CURRENT_DATE - INTERVAL '%s years' AND value IS NOT NULL
            """,
            (self.DCF_VIX_LOOKBACK_YEARS,),
        )
        avg_row = cur.fetchone()
        current_vix = float(current_row[0]) if current_row and current_row[0] is not None else None
        avg_vix = float(avg_row[0]) if avg_row and avg_row[0] is not None else None
        if current_vix is None or avg_vix is None or avg_vix <= 0:
            self._equity_risk_premium_cache = self.DCF_EQUITY_RISK_PREMIUM
            return self._equity_risk_premium_cache
        scaled = self.DCF_EQUITY_RISK_PREMIUM * (current_vix / avg_vix)
        self._equity_risk_premium_cache = max(
            self.DCF_MIN_EQUITY_RISK_PREMIUM, min(self.DCF_MAX_EQUITY_RISK_PREMIUM, scaled)
        )
        return self._equity_risk_premium_cache

    def _get_net_borrowing_for_dcf(self, cur: Any, symbol: str) -> float | None:
        """Change in total balance-sheet debt (long_term_debt + short_term_debt +
        operating_lease_liability + finance_lease_liability, same components as total_debt
        above) between the two most recent fiscal years, when they're genuinely ADJACENT
        (fiscal_year apart by exactly 1) - an additive correction toward a true FCFE
        (OCF - CapEx - SBC + Net Borrowing) instead of the zero-net-borrowing-assumed proxy
        this DCF has used until now.

        FIXED 2026-08-25 (goal: DCF audit follow-up - true FCFE via net borrowing, previously
        deferred in dcf_growth_fade_live_verified_and_remaining_items_reassessed_20260825 as
        needing debt issuance/repayment cash-flow data this pipeline doesn't fetch - confirmed
        via a schema check of annual_cash_flow that no such concept is collected, only a
        blended financing_cash_flow that also mixes in equity/dividends). Uses the
        balance-sheet debt-LEVEL change instead - a standard practitioner proxy for net
        borrowing (issued minus repaid) when the cash-flow statement's own financing detail
        isn't available, mathematically exact absent other balance-sheet effects (FX
        remeasurement, fair-value adjustments on convertible debt, etc.) that this proxy can't
        see and doesn't attempt to correct for.

        The adjacency requirement is the safety guard: this file's own comments elsewhere
        document real filers switching which XBRL debt concept they tag between fiscal years
        (CAT/XOM/DKNG - see total_debt's docstring above) - comparing two non-adjacent years
        (a multi-year gap where a tag switch is more likely to have happened) risked reading a
        tag-switch artifact as a "borrowing" event. Requiring the two years be exactly 1 fiscal
        year apart doesn't eliminate that risk (an adjacent-year tag switch is possible too,
        just less common) but meaningfully bounds it versus comparing whatever two years happen
        to have data.

        FIXED same day (live-caught via a 500-symbol universe spot-check before committing):
        the newest-year query originally accepted a row with ANY ONE component non-NULL (same
        "at least one real value" leniency total_debt's own query above uses, reasonable for
        picking a single best year). Live-confirmed via AAPL this is WRONG for a two-year
        delta: AAPL's current in-progress fiscal year has real long_term_debt/short_term_debt
        but NULL operating_lease_liability/finance_lease_liability (not yet tagged - the same
        "current interim year isn't fully filed yet" gap this file fixes elsewhere for capex/
        fcf_yield), while the prior complete year has all four populated. Treating NULL-this-
        year-real-last-year as "$0 of lease debt now" manufactured a spurious -$28B "paydown"
        that was actually just missing data, not a real deleveraging event. Fixed: a
        component's null-ness must MATCH between the two years (both present or both absent)
        for every one of the four components, or the whole comparison is skipped - a component
        that's null in both years is a real "no debt of that kind" data point, safe to treat
        as 0 either way, but a mismatch is a completeness gap, not a borrowing signal, and no
        real net-borrowing figure can be extracted from it.

        Returns None (falls back to the existing OCF-CapEx-SBC proxy unchanged) when fewer
        than 2 usable, adjacent, component-comparable years exist - the common case for a
        newer filer, one with sparse balance-sheet history, or (per the fix above) a current
        fiscal year that isn't fully tagged yet.
        """
        cur.execute(
            """
            SELECT fiscal_year, long_term_debt, short_term_debt, operating_lease_liability, finance_lease_liability
            FROM annual_balance_sheet
            WHERE symbol = %s AND fiscal_year IS NOT NULL AND data_unavailable IS NOT TRUE
              AND (long_term_debt IS NOT NULL OR short_term_debt IS NOT NULL
                   OR operating_lease_liability IS NOT NULL OR finance_lease_liability IS NOT NULL)
            ORDER BY fiscal_year DESC LIMIT 1
            """,
            (symbol,),
        )
        newest_row = cur.fetchone()
        if not newest_row:
            return None
        newest_year = newest_row[0]
        newest_components = newest_row[1:]
        cur.execute(
            """
            SELECT long_term_debt, short_term_debt, operating_lease_liability, finance_lease_liability
            FROM annual_balance_sheet
            WHERE symbol = %s AND fiscal_year = %s AND data_unavailable IS NOT TRUE
              AND (long_term_debt IS NOT NULL OR short_term_debt IS NOT NULL
                   OR operating_lease_liability IS NOT NULL OR finance_lease_liability IS NOT NULL)
            """,
            (symbol, newest_year - 1),
        )
        prior_row = cur.fetchone()
        if not prior_row:
            return None
        if any(
            (newest_c is None) != (prior_c is None)
            for newest_c, prior_c in zip(newest_components, prior_row, strict=True)
        ):
            return None
        newest_debt = sum(float(c) if c is not None else 0.0 for c in newest_components)
        prior_debt = sum(float(c) if c is not None else 0.0 for c in prior_row)
        return newest_debt - prior_debt

    @staticmethod
    def _compute_avg_fcf_fallback(
        cash_rows: list[tuple[Any, Any, Any, Any, Any]], is_capex_exempt: bool
    ) -> float | None:
        """Average FCF (OCF - CapEx - Stock-Based Comp) across up to 3 fetched fiscal years,
        skipping any year with unusable ocf/capex - used when the latest year alone can't
        produce a usable FCF (negative, or capex not yet tagged - see fetch_incremental's
        `cash_rows` query, most recent 3 fiscal years DESC).

        cash_rows: (operating_cash_flow, capex, dividends_paid, stock_based_compensation,
        common_stock_repurchased) tuples, most recent year first (dividends_paid/
        common_stock_repurchased unused here, kept for call-site tuple-unpacking convenience -
        common_stock_repurchased added 2026-08-26 for net_payout_yield, see
        _compute_valuations - this widened every mock fixture across the sec_valuations test
        family that constructs cash_rows directly; see that migration's own commit for the
        full list of touched test files).
        is_capex_exempt: depository institutions / the insurance capex-exempt allowlist
        never report capex - treat it as 0 rather than unknowable for every year, not just
        the latest (see DEPOSITORY_INSTITUTION_SIC_CODES/INSURANCE_CAPEX_EXEMPT_SYMBOLS).

        FIXED 2026-08-25 (goal: "finance best practices" methodology audit): OCF already adds
        stock-based compensation back as a non-cash expense, but SBC is a real economic cost to
        existing shareholders via future dilution - the "Owner Earnings" convention (and most
        practitioner FCF/DCF models for SBC-heavy issuers, esp. tech) deducts it rather than
        treating OCF-CapEx as clean free cash flow. `stock_based_compensation` was already
        collected in annual_cash_flow but never used anywhere in this file before now. Treated
        as 0 when NULL (not skipped like a NULL capex is) - unlike capex, which this file's own
        comments document as commonly un-tagged for a still-open interim fiscal year, a NULL
        SBC overwhelmingly means "this filer has none to report" (true for most non-tech/non-
        growth sectors) rather than a timing gap - treating it as unknowable would incorrectly
        null out the FCF fallback for the common case of a company that simply doesn't grant
        stock comp.

        FIXED 2026-08-24 (goal: "missing_cash_flow_data" coverage audit): this used to
        require >=2 usable years to compute an "average" - reasonable when the gap is just
        the current, still-open fiscal year (the common case this fallback was built for),
        but real filers can lag capex tagging TWO years deep at once, not just one.
        Live-confirmed via VLO (Valero): capex is real and correctly extracted for FY2024
        ($2.057B, matches Valero's public figure) via the "PaymentsToAcquireProductiveAssets"
        concept fallback, but NULL for FY2025/FY2026 (both not yet re-tagged in the
        3-fiscal-year fetch window) - leaving only 1 usable year, below the old >=2 floor,
        so avg_fcf_fallback stayed None and both fcf_yield and margin_of_safety were
        permanently NULL despite a real, recent, correctly-extracted FCF figure sitting
        right there. Same root cause as COIN and likely a meaningful slice of the 543
        universe symbols carrying margin_of_safety_unavailable_reason='missing_cash_flow_data'
        (live DB scan, 2026-08-24). A single real recent year is still far better than a
        permanent NULL - "average" of 1 value is just that value, so `sum/len` is correct
        unchanged; only the floor moved from >=2 to >=1.
        """
        yearly_fcfs = []
        for row_ocf, row_capex, _row_dividends, row_sbc, _row_buyback in cash_rows:
            if row_ocf is None:
                continue
            if row_capex is None:
                if not is_capex_exempt:
                    continue
                row_capex = 0
            row_sbc = 0 if row_sbc is None else row_sbc
            yearly_fcfs.append(float(row_ocf) - float(row_capex) - float(row_sbc))
        return sum(yearly_fcfs) / len(yearly_fcfs) if len(yearly_fcfs) >= 1 else None

    @staticmethod
    def _compute_multi_year_eps_cagr(income_rows: list[tuple[Any, ...]]) -> float | None:
        """Multi-year EPS CAGR used as the DCF's growth driver instead of the bare single-year
        TTM-vs-prior-year delta (see the LIMIT-6 comment on the income_rows query in
        fetch_incremental) - smooths past a one-off blip in either the newest or oldest usable
        year, same rationale _compute_avg_fcf_fallback already applies to FCF.

        income_rows: the (fiscal_year, revenue, net_income, earnings_per_share, ...) tuples
        fetch_incremental fetches, ORDER BY tier then fiscal_year DESC, up to 6 rows. Rows with
        a NULL or non-positive earnings_per_share are dropped first (CAGR isn't meaningful
        across a sign change or through a missing year - same requirement PEG's own growth_rate
        already imposes on prior_year_eps/ttm_eps); a tier-1 row (no revenue/EPS/net_income at
        all - see the query's ORDER BY CASE) always has a NULL earnings_per_share and is
        dropped here too, so the remaining rows stay in fiscal_year DESC order without needing
        a separate sort. Requires the newest and oldest surviving rows to be >=3 fiscal years
        apart - below that, a 2-year-apart CAGR is arithmetically identical to the existing
        single-year delta, so let that stand unchanged rather than silently duplicating it
        under a different name. Only the two endpoints matter; a gap year missing from the
        fetched window (e.g. row 4 has a NULL EPS) doesn't block the calculation.

        Returns None (falls back to the existing single-year delta) when fewer than 2 usable
        years exist, or they're not >=3 fiscal years apart.
        """
        eps_by_year = [(int(row[0]), float(row[3])) for row in income_rows if row[3] is not None and float(row[3]) > 0]
        if len(eps_by_year) < 2:
            return None
        newest_year, newest_eps = eps_by_year[0]
        oldest_year, oldest_eps = eps_by_year[-1]
        n_years = newest_year - oldest_year
        if n_years < 3:
            return None
        return float(((newest_eps / oldest_eps) ** (1 / n_years) - 1) * 100)

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
    ) -> tuple[float | None, float | None]:
        """Two-stage FCFE DCF: 5-year explicit forecast of `fcf`, discounted at a CAPM cost of
        equity (see _compute_discount_rate), plus a Gordon Growth terminal value at
        DCF_TERMINAL_GROWTH_RATE, divided by shares_out.

        equity_risk_premium: ADDED 2026-08-25 (goal: DCF audit follow-up - dynamic ERP). See
        DCF_MIN_EQUITY_RISK_PREMIUM's docstring for the full rationale. Defaults to None ->
        _compute_discount_rate's own default (the static DCF_EQUITY_RISK_PREMIUM), so every
        existing caller/test is unaffected; live calls from _compute_valuations pass the
        VIX-scaled value from _get_equity_risk_premium().

        FIXED 2026-08-25 (goal: DCF audit follow-up - growth-rate fade, previously deferred as
        real-blast-radius in dcf_sbc_and_multi_year_eps_cagr_fixed_20260825): the explicit
        forecast used to hold `eps_growth_pct` flat for all 5 years, then drop straight to
        DCF_TERMINAL_GROWTH_RATE (2.5%) in the terminal-value formula - an abrupt one-year
        cliff from (say) 15%/yr to 2.5%/yr, not how a real high-growth company's growth
        actually decays. Replaced with a Damodaran-style linear fade: year 1 uses
        `eps_growth_pct` in full, year DCF_FORECAST_YEARS uses DCF_TERMINAL_GROWTH_RATE
        exactly (so the explicit forecast's last year already matches the terminal value's own
        growth assumption - no discontinuity at the handoff), with each year in between
        interpolated linearly. A company already growing at/below the terminal rate now fades
        *up* to it just as mechanically as a high-growth company fades down - both are the
        same linear interpolation, not a special case.

        Returns (intrinsic_value_per_share, margin_of_safety_pct) - both None when fcf/
        shares_out/current_price aren't usable or the result is implausible. A missing/
        unusable eps_growth_pct defaults to flat 0%/yr rather than skipping the DCF entirely:
        FCF, shares, and price are the primary drivers and are independently available even
        when EPS history isn't (unlike peg_ratio, which requires a positive prior_year_eps to
        be meaningful at all). beta/risk_free_rate default to DCF_DEFAULT_BETA/
        DCF_DEFAULT_RISK_FREE_RATE when not supplied (test/caller convenience) - live calls
        from _compute_valuations always pass the symbol's real beta and the live Treasury rate.
        """
        if (
            fcf is None
            or fcf <= 0
            or shares_out is None
            or shares_out <= 0
            or current_price is None
            or current_price <= 0
        ):
            return None, None

        growth_rate = 0.0 if eps_growth_pct is None else eps_growth_pct / 100.0
        growth_rate = max(self.DCF_GROWTH_FLOOR, min(self.DCF_GROWTH_CEILING, growth_rate))
        discount_rate = self._compute_discount_rate(beta, risk_free_rate, equity_risk_premium)

        pv_explicit = 0.0
        fcf_year = fcf
        for year in range(1, self.DCF_FORECAST_YEARS + 1):
            fade_frac = (year - 1) / (self.DCF_FORECAST_YEARS - 1) if self.DCF_FORECAST_YEARS > 1 else 1.0
            year_growth_rate = growth_rate - (growth_rate - self.DCF_TERMINAL_GROWTH_RATE) * fade_frac
            fcf_year = fcf_year * (1 + year_growth_rate)
            pv_explicit += fcf_year / ((1 + discount_rate) ** year)

        terminal_value = (fcf_year * (1 + self.DCF_TERMINAL_GROWTH_RATE)) / (
            discount_rate - self.DCF_TERMINAL_GROWTH_RATE
        )
        pv_terminal = terminal_value / ((1 + discount_rate) ** self.DCF_FORECAST_YEARS)
        intrinsic_per_share = (pv_explicit + pv_terminal) / shares_out

        if not (self.MIN_INTRINSIC_VALUE_PER_SHARE <= intrinsic_per_share < self.MAX_INTRINSIC_VALUE_PER_SHARE):
            logger.debug(f"[{symbol}] DCF intrinsic value implausible ({intrinsic_per_share:.2f}), marking as NULL")
            return None, None

        # Deeply negative margins of safety (e.g. AMD/MPWR/MU-scale megacaps where the DCF's
        # conservative growth-fade disagrees hard with the market's growth-priced multiple) are a
        # real, if extreme, signal - not data corruption - so this bound only screens for
        # formula breakdown (division by a near-zero intrinsic_per_share), not "surprising" results.
        margin_of_safety_pct = (intrinsic_per_share - current_price) / intrinsic_per_share * 100
        if not (-100_000 <= margin_of_safety_pct <= 1000):
            logger.debug(f"[{symbol}] Margin of safety out of bounds ({margin_of_safety_pct:.0f}%), marking as NULL")
            return round(intrinsic_per_share, 2), None

        return round(intrinsic_per_share, 2), round(margin_of_safety_pct, 2)
