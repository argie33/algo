"""Composite quality_score computation helper for `_compute_quality_metrics`.

Split out of vqg_quality_metrics.py (2026-09-04, same pass as vqg_quality_ratios.py - see that
module's docstring). Pure extract-method refactor: no computation, curve breakpoint, weight, or
return value was changed from the original inline code. Every fix-history comment/live-verified
sample count/bound below is preserved byte-for-byte.

`QualityScoreMixin` provides `_compute_quality_composite_score`, covering (in the same order as
the original inline code): the per-metric scoring curves (roe/roa/roce/gross_profitability/
asset_turnover/debt_to_equity/margin_volatility), the "new phase 3" raw ratios this same block
first computes a value for (operating_profitability, gross_profitability, accruals_ratio,
fcf_margin, asset_turnover) together with their own `*_unavailable_reason` writes, the
sector-conditional (Financial Services/Real Estate vs universal) weighting structure, and the
final weighted `quality_score` + its own `quality_score_unavailable_reason`.

Mixed into QualityMetricsMixin via multiple inheritance, same pattern as vqg_symbol_gates.py's
SymbolGateMixin - every `self.` call here resolves normally through the final composed instance.
"""

from typing import TYPE_CHECKING, Any

from loaders.helpers.vqg_symbol_gates import SymbolGateMixin
from utils.type_conversion import safe_float


def _owner() -> Any:
    from loaders import load_value_quality_growth_metrics as _owner_mod

    return _owner_mod


class QualityScoreMixin(SymbolGateMixin):
    """See module docstring. TYPE_CHECKING stubs mirror vqg_quality_metrics.py's - only the
    cross-mixin members (defined directly on ValueQualityGrowthMetricsLoader) this file's
    methods actually call via `self.` are declared.
    """

    if TYPE_CHECKING:

        def _nan_to_none(self, value: float | None) -> float | None: ...

        def _get_symbol_sector(self, symbol: str) -> str | None: ...

        def _margin_curve(self, value: float, breakpoints: list[tuple[float, float]]) -> float: ...

        def _weighted_avg(
            self, components: list[tuple[float | None, float]], min_weight_pct: float = 0.0
        ) -> float | None: ...

        def _ratio_with_implausible_fallback(
            self,
            symbol: str,
            numerator: float | None,
            denominator: float | None,
            numerator_field: str,
            denominator_field: str,
            *,
            denominator_must_be_positive: bool = False,
        ) -> tuple[float | None, bool]: ...

    def _compute_quality_composite_score(
        self,
        symbol: str,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
        margin_volatility: float | None,
        stockholders_equity: float | None,
        interest_expense: float | None,
        total_assets: float | None,
        net_income: float | None,
        operating_cash_flow: float | None,
        revenue: float | None,
        free_cash_flow: float | None,
        operating_income_for_margin: float | None,
        no_operating_income_concept: bool,
        no_gross_profit_concept: bool,
        gross_profit_used: float | None,
    ) -> None:
        """Compute the composite quality_score and its constituent phase-3 ratio fields.

        Writes metrics["gross_profitability"] (+reason), ["operating_profitability"]
        (+reason), ["accruals_ratio"] (+reason), ["margin_volatility"] (+reason),
        ["fcf_margin"] (+reason), ["asset_turnover"] (+reason), ["quality_score"], and
        ["quality_score_unavailable_reason"] - identical to the original inline code.
        """
        # Compute composite quality_score from available metrics
        # Score is average of available metrics (0-100 scale)
        # debt_to_assets is "lower is better" so it's converted to a comparable
        # higher-is-better score before joining the same clamp-and-average as the
        # raw percentage metrics below (100 - debt_to_assets%, e.g. 30% debt -> 70).
        #
        # NOTE: debt_to_assets is positively signed vs forward return in FM testing
        # (higher leverage -> higher forward return), the opposite of this "low debt is
        # good" inversion - a genuine, unresolved literature tension (Modigliani-Miller
        # leverage-beta effect vs. the distress-risk anomaly), not miscalibration. Left
        # unchanged pending a real distress-risk proxy (e.g. Altman Z-score) to resolve it.
        # debt_to_assets_score is no longer scored (replaced by debt_to_equity_score, see
        # that field's comment near roic_pct/roce_pct below) - metrics["debt_to_assets"]
        # itself is still persisted/displayed. Same for interest_coverage_score (dead after
        # interest_coverage was dropped from quality_components) - metrics
        # ["interest_coverage"] is still persisted independently.

        # roe/roa/operating_margin/net_margin are rescaled onto domain-informed curves
        # (not fed in as raw percentage points) - a flat 0-100=percentage mapping requires
        # a 100% margin to hit 100, a threshold no real business reaches, which
        # structurally compressed quality_score toward ~20-50 regardless of actual quality
        # and defeated min_composite_score's intended selectivity. This is a scale fix only
        # - the underlying roe/roa/operating_margin/net_margin values feeding
        # fama_macbeth_quality_factors.py are untouched. Thresholds are hand-set, not
        # FM-backtested (calibration, not a new empirical claim).
        roe_score = (
            self._margin_curve(metrics["roe"], [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)])
            if metrics["roe"] is not None
            else None
        )
        roa_score = (
            self._margin_curve(metrics["roa"], [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)])
            if metrics["roa"] is not None
            else None
        )
        # operating_margin_score/net_margin_score are not scored - operating_margin and
        # net_margin are still fetched/stored/displayed for reference, but neither carries
        # independent signal once ROA is controlled for (see
        # quality_operating_net_margin_no_independent_signal_over_roa_20260826 in MEMORY.md).

        # Quality pillar composition follows a literature-informed denominator-sharing
        # check (Novy-Marx 2013, Fama-French 2015 RMW, Sloan 1996, QMJ 2013): ROE
        # (NI/BookEquity) overlaps with FF's Operating Profitability ((Rev-COGS-SGA-
        # Interest)/BookEquity, same denominator), and ROA (NI/Assets) overlaps with
        # Novy-Marx's Gross Profitability ((Rev-COGS)/Assets, same denominator).
        # Cash-flow ROA (OCF/Assets) is not independent once ROA and Accruals Ratio
        # ((NI-OCF)/Assets, Sloan 1996) are both present - it's their exact linear
        # difference. operating_margin/net_margin (r=0.91, both profit/revenue ratios) are
        # the other genuinely redundant pair; roe/debt_to_assets (r=0.82) is a DIFFERENT,
        # DuPont-mechanical overlap the literature treats as fine to keep.
        #
        # No separate SG&A field exists in this pipeline - operating_income (GAAP, already
        # nets out COGS+SG&A) minus interest_expense is the available proxy for FF's
        # (Rev-COGS-SGA-Interest) construction.
        # operating_profitability_score/roic_score/accruals_score are not scored (failed
        # this repo's |t|>2 bar, or replaced by a more robust alternative - roic_score ->
        # roce_score, see below). The raw values are still computed and persisted for
        # display - only the scoring curves and composite weight are removed. See
        # weighted_score below for the full final composite.
        #
        # operating_income_for_margin falls back to the EBIT approximation (pretax_income +
        # interest_expense) for 40-F-style filers that never tag OperatingIncomeLoss - same
        # fallback operating_margin/operating_margin_trend already use.
        #
        # Guarded at |ratio|>1000 like every sibling ratio in this file - a near-zero
        # stockholders_equity base can otherwise blow this up multiple orders of magnitude.
        #
        # A negative or zero stockholders_equity denominator (real, common for mature
        # buyback-heavy filers) makes this ratio mathematically undefined - same "real
        # business-state fact, not an absent SEC concept" case pb_ratio/roic_pct/roce_pct
        # carve out via negative_book_value/negative_invested_capital/
        # negative_capital_employed. Reuses "negative_book_value" rather than a new string.
        operating_profitability_negative_equity = stockholders_equity is not None and stockholders_equity <= 0
        operating_profitability = None
        if operating_income_for_margin is not None and stockholders_equity is not None and stockholders_equity > 0:
            computed_operating_profitability = (
                (operating_income_for_margin - (interest_expense or 0.0)) / stockholders_equity * 100.0
            )
            if abs(computed_operating_profitability) > 1000:
                failed_metrics.append("operating_profitability")
                implausible_ratio_metrics.append("operating_profitability")
            else:
                operating_profitability = float(computed_operating_profitability)
        # Novy-Marx (2013, JFE) "gross profitability" - a firm that converts revenue to
        # gross profit efficiently relative to its asset base is a genuine quality signal
        # independent of the margin-based ratios already scored here. Guarded at
        # |ratio|>1000 like the sibling ratios in this file (near-zero total_assets can
        # otherwise blow this up multiple orders of magnitude).
        # Reuses gross_profit_used (same numerator gross_margin already recovers via
        # fallback) instead of a separate lookup. Banks/REITs and some real filers (e.g.
        # REGN, JAZZ) structurally never tag a gross-profit-style income statement at all -
        # distinguished from a genuine loader gap via no_gross_profit_concept below.
        gross_profit_for_profitability = gross_profit_used
        gross_profitability = None
        if gross_profit_for_profitability is not None and total_assets is not None and total_assets > 0:
            computed_gross_profitability = gross_profit_for_profitability / total_assets * 100.0
            if abs(computed_gross_profitability) > 1000:
                failed_metrics.append("gross_profitability")
                implausible_ratio_metrics.append("gross_profitability")
            else:
                gross_profitability = float(computed_gross_profitability)
        # Breakpoints are a domain-judgment fit to the live distribution, not FM-fit to
        # inflection points.
        gross_profitability_score = (
            self._margin_curve(gross_profitability, [(10.0, 40.0), (25.0, 75.0), (50.0, 100.0)])
            if gross_profitability is not None
            else None
        )
        # Near-zero total_assets can blow this ratio up arbitrarily; same |ratio|>1000 guard
        # as gross_profitability/operating_profitability/fcf_margin.
        accruals_ratio = None
        if net_income is not None and operating_cash_flow is not None and total_assets is not None and total_assets > 0:
            computed_accruals_ratio = (net_income - operating_cash_flow) / total_assets * 100.0
            if abs(computed_accruals_ratio) > 1000:
                failed_metrics.append("accruals_ratio")
                implausible_ratio_metrics.append("accruals_ratio")
            else:
                accruals_ratio = float(computed_accruals_ratio)
        # ROCE score: same curve shape as the old roic_score (both are "return on capital
        # deployed" measures, similar scale) - see the roce_pct computation's own comment
        # (near roic_pct above) for why ROCE replaces ROIC in the composite.
        roce_pct_val = metrics.get("roce_pct")
        roce_score = (
            self._margin_curve(roce_pct_val, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)])
            if roce_pct_val is not None
            else None
        )
        # FCF Margin (free_cash_flow / revenue): cash-conversion efficiency net of capex,
        # independent of Accruals Ratio (never nets out capex). Replaces accruals_score in
        # the composite.
        #
        # The anchor fiscal year is chosen for balance-sheet freshness first, so it can have
        # free_cash_flow present but revenue not yet extracted (or vice versa) even though a
        # jointly-valid pair exists in an earlier year - the fallback below checks both
        # sides' None-ness, not just the numerator's, and is scoped to LOCAL variables
        # (fcf_margin_free_cash_flow/fcf_margin_revenue) rather than overwriting the global
        # free_cash_flow/revenue, which also feed fcf_to_net_income and fcf_growth_yoy and
        # must stay aligned to the anchor year for those.
        #
        # Each fallback tier scans every candidate year and picks the most recent one that's
        # actually plausible (|margin|<=1000), not just the single nearest year - an older
        # plausible year can sit behind a nearer implausible one (e.g. a near-zero-revenue
        # year).
        fcf_margin_free_cash_flow = free_cash_flow
        fcf_margin_revenue = revenue
        if fcf_margin_free_cash_flow is None or fcf_margin_revenue is None or fcf_margin_revenue <= 0:
            with _owner().DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT free_cash_flow, revenue
                    FROM annual_cash_flow acf
                    JOIN annual_income_statement ais
                      ON ais.symbol = acf.symbol AND ais.fiscal_year = acf.fiscal_year
                    WHERE acf.symbol = %s AND acf.free_cash_flow IS NOT NULL AND ais.revenue IS NOT NULL
                      AND acf.fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                    ORDER BY acf.fiscal_year DESC
                    """,
                    (symbol,),
                )
                fallback_fcf_rows = cur.fetchall()
                if not fallback_fcf_rows:
                    cur.execute(
                        """
                        SELECT free_cash_flow, revenue
                        FROM annual_cash_flow acf
                        JOIN annual_income_statement ais
                          ON ais.symbol = acf.symbol AND ais.fiscal_year = acf.fiscal_year
                        WHERE acf.symbol = %s AND acf.free_cash_flow IS NOT NULL AND ais.revenue IS NOT NULL
                        ORDER BY acf.fiscal_year DESC
                        """,
                        (symbol,),
                    )
                    fallback_fcf_rows = cur.fetchall()
            # row[0]/row[1] are raw Decimal; must cast to float before arithmetic here -
            # `Decimal * float` raises TypeError, which propagates through this function's
            # outer try/except and wipes out EVERY quality_metrics field for the symbol, not
            # just fcf_margin.
            fallback_fcf_row = next(
                (
                    row
                    for row in fallback_fcf_rows
                    if row[1] is not None and float(row[1]) > 0 and abs(float(row[0]) / float(row[1]) * 100.0) <= 1000
                ),
                fallback_fcf_rows[0] if fallback_fcf_rows else None,
            )
            if fallback_fcf_row:
                fcf_margin_free_cash_flow = self._nan_to_none(
                    safe_float(fallback_fcf_row[0], f"{symbol}.free_cash_flow_fallback_year", allow_none=True)
                )
                fcf_margin_revenue = self._nan_to_none(
                    safe_float(fallback_fcf_row[1], f"{symbol}.revenue_fcf_margin_fallback_year", allow_none=True)
                )
        fcf_margin = None
        if fcf_margin_free_cash_flow is not None and fcf_margin_revenue is not None and fcf_margin_revenue > 0:
            computed_fcf_margin = fcf_margin_free_cash_flow / fcf_margin_revenue * 100.0
            if abs(computed_fcf_margin) > 1000:
                failed_metrics.append("fcf_margin")
                implausible_ratio_metrics.append("fcf_margin")
            else:
                fcf_margin = float(computed_fcf_margin)
        fcf_margin_score = (
            self._margin_curve(fcf_margin, [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)])
            if fcf_margin is not None
            else None
        )
        # Asset Turnover (Revenue / Total Assets, x100 - same "ratio-as-percentage" storage
        # convention as gross_profitability). Breakpoints: 0.3x (capital-intensive/utilities)
        # maps to 40, 0.8x (typical industrial) to 75, 1.5x+ (retail/services) to 100 -
        # domain-judgment, not FM-fit to inflection points.
        # Uses the same cross-year implausible-ratio fallback as roe/roa - see
        # _find_plausible_cross_year_ratio's docstring.
        asset_turnover, _asset_turnover_implausible = self._ratio_with_implausible_fallback(
            symbol, revenue, total_assets, "revenue", "total_assets", denominator_must_be_positive=True
        )
        if asset_turnover is None and _asset_turnover_implausible:
            failed_metrics.append("asset_turnover")
            implausible_ratio_metrics.append("asset_turnover")
        asset_turnover_score = (
            self._margin_curve(asset_turnover, [(30.0, 40.0), (80.0, 75.0), (150.0, 100.0)])
            if asset_turnover is not None
            else None
        )
        # Debt-to-Equity score: inverted (lower leverage = higher score), 0.5 maps to 75,
        # 1.0 to 50, 2.0+ to 0. Negative D/E (negative book equity, real financial distress)
        # floors to 0 rather than inverting into a spuriously high score.
        debt_to_equity_val = metrics.get("debt_to_equity")
        if debt_to_equity_val is None:
            debt_to_equity_score = None
        elif debt_to_equity_val < 0:
            debt_to_equity_score = 0.0
        else:
            debt_to_equity_score = max(0.0, min(100.0, 100.0 - (debt_to_equity_val / 2.0) * 100.0))
        # Margin volatility (QMJ 2013 Safety leg proxy): precomputed by the caller from
        # multi-year income_rows this function doesn't have (see _compute_margin_volatility).
        # Inverted curve: LOWER volatility (more stable margins) scores higher.
        # Must read the `margin_volatility` parameter directly, NOT `metrics.get(
        # "margin_volatility")` - that dict key is only written later in this function (see
        # the PERSISTED block below), so reading it here always returns None.
        margin_volatility_val = margin_volatility
        margin_volatility_score = (
            100.0 - self._margin_curve(margin_volatility_val, [(5.0, 20.0), (15.0, 60.0), (30.0, 100.0)])
            if margin_volatility_val is not None
            else None
        )

        # operating_margin_trend/net_margin_trend/roe_trend/payout_ratio/interest_coverage
        # score curves, equity_cluster/asset_cluster, debt_to_assets_score, roic_score, and
        # a flat accruals_score are all deliberately NOT scored (confirmed insignificant or
        # superseded per FM re-testing) even though raw values are still persisted:
        # debt_to_assets -> debt_to_equity_score, roic -> roce_score, accruals ->
        # fcf_margin_score. See _score_quality's docstring in load_stock_scores.py.
        #
        # Altman Z''-Score is not scored: it's a DISCRETE distress-triage classifier in the
        # literature, not meant to be continuously averaged into a magnitude-weighted
        # composite alongside ROA/ROE/margin ratios. A discrete distress-flag use may
        # belong on GOVERNANCE's trading-eligibility checks instead, separate from the
        # continuous quality_score - deliberately left open.
        #
        # Weights are set from both full-sample t-stat magnitude and a half-split
        # time-stability check - a component whose t-stat holds up identically across both
        # eras is weighted higher relative to its raw t-stat than one whose apparent
        # strength was concentrated in a short/recent window. debt_to_equity/roa/roce/
        # fcf_margin/roe (the "core five", 80% of the composite) have either the strongest
        # full-sample evidence or the best demonstrated time-stability. current_ratio was
        # tested and deliberately excluded (sign-flips across the half-split).
        # min_quality_weight_pct below is calibrated to ~40% of the composite's nominal
        # weight sum - above any thin-sample case found so far.
        #
        # Financial Services and Real Estate use a 7-input, two-cluster (profitability +
        # safety) structure instead of the flat 8-input tiered average - asset_turnover_score
        # is the one input confirmed (via isolated testing) to actively hurt Quality's
        # signal for these two sectors. Matches AQR QMJ's own profitability/safety cluster
        # construction. Both clusters and the top-level blend are internally renormalized
        # (same _weighted_avg helper) - a symbol missing part of one cluster still scores
        # off whatever it has.
        #
        # update_quality_roe_roce_percentiles() (further below) assumes every symbol was
        # scored via the flat 8-input structure - it does NOT reconcile through this
        # two-cluster structure, so it explicitly SKIPS Financial Services/Real Estate
        # symbols (see its own SQL filter); those symbols keep the Pass-1 curve-based
        # ROE/ROCE scores rather than the cross-sectional-percentile correction.
        sector = self._get_symbol_sector(symbol)
        if sector in ("Financial Services", "Real Estate"):
            profitability_cluster_score = self._weighted_avg(
                [
                    (roe_score, 1.0),
                    (roa_score, 1.0),
                    (roce_score, 1.0),
                    (fcf_margin_score, 1.0),
                    (gross_profitability_score, 1.0),
                ],
                min_weight_pct=2.0,  # >=2 of 5 available - proportional to the 40%-of-101 floor below
            )
            safety_cluster_score = self._weighted_avg(
                [(debt_to_equity_score, 1.0), (margin_volatility_score, 1.0)],
                min_weight_pct=1.0,  # >=1 of 2 available
            )
            # Cluster weights (69/25, summing to 94 = universal branch's 101 minus
            # asset_turnover's 7) reflect each cluster's ACTUAL share of the universal
            # branch's nominal weight - a flat 1.0/1.0 split previously let a single
            # cluster, down to one raw field once its own internal floor was barely
            # cleared, produce a full undiscounted quality_score (e.g. an Oil Royalty
            # Trust scoring 97 off margin_volatility alone with every other input NULL).
            quality_components = [(profitability_cluster_score, 69.0), (safety_cluster_score, 25.0)]
            # Proportional to the universal branch's 40/101 (~39.6%) floor: 40 * (94/101) =
            # 37.2. Safety alone is only 25 points (below this floor), so a safety-only
            # symbol correctly returns None instead of a single-field score.
            min_quality_weight_pct = 37.2
        else:
            quality_components = [
                (roe_score, 11.0),
                (roa_score, 18.0),
                (roce_score, 18.0),
                (fcf_margin_score, 15.0),
                (debt_to_equity_score, 18.0),
                (margin_volatility_score, 7.0),
                (asset_turnover_score, 7.0),
                (gross_profitability_score, 7.0),
            ]
        # COMPLETENESS FLOOR: without it, renormalizing over 1-3 available components lets
        # a single extreme raw ratio (e.g. an oil/gas royalty trust's ROA of 700%+) drive
        # quality_score to 100.00 even though data_completeness/GOVERNANCE's eligibility
        # floor should treat this as thin data. Only applies to the universal (non-FS/RE)
        # branch - the sector-conditional branch sets its own proportional floor inline.
        if sector not in ("Financial Services", "Real Estate"):
            min_quality_weight_pct = 40.0
        available_quality_weight = sum(w for v, w in quality_components if v is not None)
        weighted_score = self._weighted_avg(quality_components, min_weight_pct=min_quality_weight_pct)

        metrics["gross_profitability"] = gross_profitability
        metrics["gross_profitability_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "gross_profitability" in implausible_ratio_metrics
                else "reit_special_entity"
                if no_gross_profit_concept
                else "no_revenue_reported"
                if symbol in self._get_blank_check_symbols()
                or symbol in self._get_no_recent_revenue_symbols()
                or symbol in self._get_never_tagged_revenue_symbols()
                else "no_recent_total_assets_reported"
                if total_assets is None
                and (
                    symbol in self._get_no_recent_total_assets_symbols()
                    or symbol in self._get_never_tagged_total_assets_symbols()
                )
                else "missing_sec_data"
            )
            if gross_profitability is None
            else None
        )
        metrics["operating_profitability"] = operating_profitability
        metrics["operating_profitability_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "operating_profitability" in implausible_ratio_metrics
                else "negative_book_value"
                if operating_profitability_negative_equity
                else "reit_special_entity"
                if no_operating_income_concept
                # Label-only: the anchor year's income statement can lack operating_income
                # (and its EBIT fallback) even when the symbol reports it in other years.
                else "operating_income_absent_from_anchor_year"
                if operating_income_for_margin is None
                and symbol in self._get_operating_income_available_elsewhere_symbols()
                # operating_profitability_negative_equity only fires when stockholders_equity
                # is a real value <=0 - stays False (not caught) when equity is None.
                else "stockholders_equity_not_reported"
                if stockholders_equity is None
                and (
                    symbol in self._get_no_recent_stockholders_equity_symbols()
                    or symbol in self._get_never_tagged_stockholders_equity_symbols()
                )
                else "operating_income_not_itemized"
                if symbol in self._get_no_recent_operating_income_symbols()
                or symbol in self._get_never_tagged_operating_income_symbols()
                else "missing_sec_data"
            )
            if operating_profitability is None
            else None
        )
        metrics["accruals_ratio"] = accruals_ratio
        metrics["accruals_ratio_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "accruals_ratio" in implausible_ratio_metrics
                else "no_recent_operating_cash_flow_reported"
                if operating_cash_flow is None and symbol in self._get_no_recent_operating_cash_flow_symbols()
                # Label-only: operating_cash_flow is None because the anchor year's own
                # cash-flow row is unavailable, not because the symbol lacks real OCF.
                else "operating_cash_flow_absent_from_anchor_year"
                if operating_cash_flow is None and symbol in self._get_operating_cash_flow_available_elsewhere_symbols()
                else "no_recent_total_assets_reported"
                if total_assets is None
                and (
                    symbol in self._get_no_recent_total_assets_symbols()
                    or symbol in self._get_never_tagged_total_assets_symbols()
                )
                else "missing_sec_data"
            )
            if accruals_ratio is None
            else None
        )
        metrics["margin_volatility"] = margin_volatility
        metrics["margin_volatility_unavailable_reason"] = "insufficient_history" if margin_volatility is None else None
        # Gate on `X is None` directly (not `"X" in failed_metrics`) - the compute blocks
        # above don't append fcf_margin/asset_turnover to failed_metrics when inputs are
        # merely missing (only when the |ratio|>1000 bound fires), so gating on
        # failed_metrics left many rows with a NULL value and no reason recorded.
        metrics["fcf_margin"] = fcf_margin
        metrics["fcf_margin_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "fcf_margin" in implausible_ratio_metrics
                # fcf_margin's own cross-year fallback (fcf_margin_free_cash_flow/
                # fcf_margin_revenue above) already looks past the anchor row, so a
                # remaining None here means both inputs are genuinely absent across recent
                # fiscal years, not just off the anchor.
                else "no_recent_free_cash_flow_reported"
                if symbol in self._get_no_recent_free_cash_flow_symbols()
                or symbol in self._get_never_tagged_free_cash_flow_symbols()
                else "no_revenue_reported"
                if symbol in self._get_no_recent_revenue_symbols() or symbol in self._get_never_tagged_revenue_symbols()
                else "missing_sec_data"
            )
            if fcf_margin is None
            else None
        )
        metrics["asset_turnover"] = asset_turnover
        metrics["asset_turnover_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "asset_turnover" in implausible_ratio_metrics
                else "no_revenue_reported"
                if symbol in self._get_no_recent_revenue_symbols() or symbol in self._get_never_tagged_revenue_symbols()
                else "no_recent_total_assets_reported"
                if total_assets is None
                and (
                    symbol in self._get_no_recent_total_assets_symbols()
                    or symbol in self._get_never_tagged_total_assets_symbols()
                )
                # Label-only: revenue is None because the balance-sheet anchor year's own
                # income-statement row is unavailable, not because the symbol lacks real
                # revenue - the windowed gate above already ruled that out.
                else "revenue_absent_from_anchor_year"
                if revenue is None and symbol in self._get_revenue_available_elsewhere_symbols()
                else "missing_sec_data"
            )
            if asset_turnover is None
            else None
        )

        # An unprofitable company still has a real, computed quality score (0,
        # after clamping) - that's honest data, not missing data. Do not mark
        # data_unavailable just because every component came out <= 0.
        if weighted_score is not None:
            metrics["quality_score"] = float(min(100.0, max(0.0, weighted_score)))

        # Score can be partial; only mark unavailable if ALL metrics failed OR the
        # available weight didn't clear the completeness floor above (thin-sample
        # extrapolation, not honest partial data - see quality_components' own comment).
        if weighted_score is None and available_quality_weight < min_quality_weight_pct:
            metrics["quality_score_unavailable_reason"] = "insufficient_completeness"
        else:
            metrics["quality_score_unavailable_reason"] = None
