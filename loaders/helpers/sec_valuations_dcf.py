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
    # values are the class constants just below (moved here verbatim from
    # SecValuationsLoader itself 2026-09-05, file-size ratchet decomposition - same class
    # either way via Python's MRO, so `self.DCF_X` reads on SecValuationsLoader and on
    # SecValuationYieldDcfMixin, which declares its own subset of these same names for mypy,
    # are unaffected) and the two cache instance attributes, still defined on
    # SecValuationsLoader itself (see that class's own comment on them).
    _risk_free_rate_cache: float | None
    _equity_risk_premium_cache: float | None

    # DCF constants (migration 1208, Value factor goal 2026-08-17)
    #
    # FIXED 2026-08-20 (goal: finance-accuracy audit): DCF_DISCOUNT_RATE used to be a single
    # flat 10%/yr applied to every company in the universe regardless of risk - a mega-cap
    # utility and a small-cap biotech got the exact same cost of capital. That's not
    # industry-standard DCF practice: the discount rate for an equity-cash-flow DCF should be
    # a risk-adjusted cost of equity (CAPM: risk-free rate + beta x equity risk premium), not
    # one guessed constant for the whole universe. Replaced with a live, per-symbol CAPM rate -
    # see _compute_discount_rate() below. DCF_DISCOUNT_RATE itself is gone; DCF_EQUITY_RISK_
    # PREMIUM/DCF_DEFAULT_RISK_FREE_RATE/DCF_BLUME_ADJUSTMENT_WEIGHT/DCF_DEFAULT_BETA replace it.
    DCF_TERMINAL_GROWTH_RATE = 0.025
    DCF_GROWTH_FLOOR = -0.10
    DCF_GROWTH_CEILING = 0.15
    DCF_FORECAST_YEARS = 5
    MAX_INTRINSIC_VALUE_PER_SHARE = 1_000_000.0  # $1M/share - no real per-share DCF exceeds this
    # Below $1/share the DCF output is degenerate rather than a real valuation - it's the
    # fcf_base-near-cancellation bug class (same root cause as DCF_NET_BORROWING_MIN_RETAINED_FRACTION,
    # e.g. IMMR/ARM/COMP: a healthy company's FCF nearly exactly offset by a one-time item leaves a
    # tiny positive fcf_base that DCFs out to pennies/share). A $0.01-$0.99 "intrinsic value" isn't
    # informative even as a number, so both fields are nulled here rather than only margin_of_safety_pct.
    MIN_INTRINSIC_VALUE_PER_SHARE = 1.0

    # Long-run US equity risk premium (Damodaran/Ibbotson-style estimate - the ~4-6% range is
    # the standard academic/practitioner convention for the market's average excess return
    # over Treasuries; 5.0% sits at the middle of that range). Used as the fallback/test
    # default when _get_equity_risk_premium() below can't produce a live reading - see that
    # method's docstring for why this is no longer the value live runs actually use.
    DCF_EQUITY_RISK_PREMIUM = 0.05
    # FIXED 2026-08-25 (goal: DCF audit follow-up - dynamic ERP, previously deferred as "a
    # much bigger data undertaking" in dcf_growth_rate_fade_landed_20260825/
    # dual_class_dcf_entity_fcf_shares_mismatch_fixed_20260825): a proper Damodaran-style
    # *implied* ERP (solving for the discount rate that equates the S&P 500's current level to
    # its expected cash flows) needs index-level dividend/buyback yield and a forward earnings
    # growth estimate - live-checked economic_data's full series inventory and neither exists
    # anywhere in this pipeline (only raw SP500 index level and DGS-series Treasury yields are
    # fetched), so that route is still genuinely out of reach without a new data source.
    # VIXCLS (CBOE VIX close), however, IS already in economic_data (26 years, 2000-present)
    # and is itself a forward-looking, options-implied measure of the market's expected risk
    # (Whaley's "investor fear gauge") - unlike a trailing-realized-return premium (rejected:
    # backward-looking, would make the DCF noisier without being more accurate), VIX already
    # prices in forward risk the same way implied ERP is supposed to, just via a different
    # market (options, not equities). Scaling the static 5.0% anchor by current VIX / its own
    # long-run average gives a genuinely dynamic, live, forward-looking ERP without requiring
    # data this pipeline doesn't have - same spirit as _get_risk_free_rate's live DGS10 feed,
    # applied to the other CAPM input that was still a hardcoded constant.
    #
    # Bounds keep the result within Damodaran's own published yearly implied-ERP history
    # (his S&P 500 implied ERP series has run roughly 2%-8% since 1960, only approaching the
    # top of that band in acute crises like 2008) - an unclamped VIX ratio could otherwise push
    # the multiplier far outside that real historical range during a 2020-COVID-style vol
    # spike (VIXCLS peaked at 82.69 in this DB's own history) or an unusually complacent
    # stretch (VIXCLS low of 9.14), neither of which real implied ERP ever actually reached.
    DCF_MIN_EQUITY_RISK_PREMIUM = 0.03
    DCF_MAX_EQUITY_RISK_PREMIUM = 0.08
    # Long-run VIX average lookback - the full ~26-year history on file (not just a recent
    # window) so a multi-year low- or high-vol REGIME doesn't get compared only against
    # itself (e.g. averaging only the last 3 calm years would understate how elevated "normal"
    # VIX really is over a full cycle, permanently inflating the dynamic ERP relative to that
    # regime). economic_data's VIXCLS starts 2000-01-03, so this comfortably covers the whole
    # series without hardcoding a start date.
    DCF_VIX_LOOKBACK_YEARS = 25

    # Sanity bound on _get_net_borrowing_for_dcf's result relative to the DCF's own fcf_base
    # (OCF - CapEx - SBC) - live-caught (500-symbol universe spot-check, same day, before
    # committing) BWXT: a real, small ($50-500M/yr OCF) industrial company whose
    # operating_lease_liability data jumps to an implausible $44B in one fiscal year (almost
    # certainly a pre-existing XBRL extraction bug elsewhere in this pipeline - annual_balance_
    # sheet already carries this bad figure into total_debt/enterprise_value/ev_ebitda today,
    # independent of this fix - not something this net-borrowing feature caused, but something
    # it would otherwise blindly amplify into an even more absurd DCF result). A company's real
    # net borrowing in a single year, however large, is essentially never dozens-to-hundreds of
    # times its own operating cash flow scale (BWXT's $24B swing was ~50x its most recent real
    # annual OCF) - genuine large financing events (AMZN's real $72B swing, live-confirmed
    # plausible against Amazon's own ~$100-160B OCF scale) stay within a much smaller multiple.
    # 10x is generous enough to avoid rejecting a real large one-time raise for a company with a
    # temporarily weak FCF year, while still catching an order-of-magnitude data-quality outlier
    # like BWXT's.
    DCF_NET_BORROWING_MAX_FCF_MULTIPLE = 10.0
    # FIXED 2026-09-04 (goal: SEC/XBRL "implausible values" audit, live-confirmed via IMMR):
    # the 10x ceiling above only guards against net_borrowing being implausibly LARGE relative
    # to fcf_base - it says nothing about net_borrowing nearly CANCELLING fcf_base out. IMMR's
    # real FY2026 fcf_base ($32.102M, OCF-CapEx-SBC, genuinely healthy - fcf_yield=12.92%) and
    # net_borrowing (-$32.098M, a single large debt-repayment year, well within the 10x bound)
    # combine to a dcf_fcf_base of ~$4,000 - still technically positive, so it slips past the
    # DCF's own `fcf <= 0` null-out gate, but that near-zero base then compounds through all
    # DCF_FORECAST_YEARS plus the terminal value, producing an intrinsic_value_per_share that
    # rounds to $0.00 - a misleading "worthless" signal for a real, cash-generative company,
    # not an honest "no DCF available" result. A full sign-flip to negative was already handled
    # (fcf<=0 gate nulls it, see test_net_borrowing_pushing_fcf_negative_leaves_dcf_none_
    # not_a_crash) - this catches the same "one-time financing event shouldn't anchor a
    # multi-year perpetuity" problem one step earlier, before it degenerates into a near-zero
    # (rather than negative) base. 0.15 is conservative: every symbol checked in the live
    # $0.00-$0.30/share tier that wasn't near-total cancellation retained >=60% of fcf_base.
    DCF_NET_BORROWING_MIN_RETAINED_FRACTION = 0.15
    # Fallback risk-free rate (approx. long-run average 10Y Treasury yield) - used only as a
    # test/caller default and on the rare day economic_data has no recent DGS10 reading. Live
    # runs use the actual current 10Y yield via _get_risk_free_rate() below, not this constant.
    DCF_DEFAULT_RISK_FREE_RATE = 0.045
    # Blume adjustment (Bloomberg/Merrill Lynch convention): shrinks a raw regression beta
    # 2/3 of the way toward the market average of 1.0. Individual-stock raw betas are noisy
    # (small sample, name-specific events) - shrinking toward 1.0 is the standard industry
    # correction rather than trusting a raw estimate (or a whole-universe flat rate) outright.
    DCF_BLUME_ADJUSTMENT_WEIGHT = 2.0 / 3.0
    # Assumed market-average risk when a symbol has no computed beta (stability_metrics.beta
    # NULL - e.g. insufficient price history). Beta=1.0 is the standard "unknown risk, assume
    # average" convention, not a guess biased toward either overvaluing or undervaluing.
    DCF_DEFAULT_BETA = 1.0
    # Cost of equity must exceed the risk-free rate by at least this much - equities are
    # inherently riskier than Treasuries, so CAPM should never produce a discount rate at or
    # below the risk-free rate even for a very low/negative-beta name.
    DCF_MIN_EQUITY_RISK_PREMIUM_APPLIED = 0.01
    # Sanity ceiling on the resulting discount rate - prevents degenerate terminal-value math
    # (or a silently absurd near-zero intrinsic value) on an extreme/noisy beta outlier.
    DCF_MAX_DISCOUNT_RATE = 0.25
    # Minimum spread the discount rate must keep above DCF_TERMINAL_GROWTH_RATE (2.5%). Gordon
    # Growth's terminal_value = fcf * (1+g) / (discount_rate - g) is a genuine singularity as
    # discount_rate approaches g: it blows up to an absurd multiple just below the singularity,
    # goes negative at/below it, and produces a negative intrinsic_per_share that the plausibility
    # guard then silently swallows as None. This isn't theoretical - this system's own DGS10
    # history includes a 0.52% reading (2020 COVID-era), and rfr+MIN_EQUITY_RISK_PREMIUM_APPLIED
    # alone doesn't keep the rate away from g in that regime (a low-beta name could land at ~2.2%,
    # under the 2.5% terminal growth rate). A 3pp floor above g keeps the terminal multiple
    # bounded to a sane range in any real-world rate environment while still leaving genuine
    # risk-based discount-rate differences visible above the floor.
    DCF_MIN_DISCOUNT_TERMINAL_SPREAD = 0.03

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
