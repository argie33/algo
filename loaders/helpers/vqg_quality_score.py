"""QualityScoreMixin._compute_quality_composite_score, extracted from vqg_quality.py
(2026-09-10, file-size ratchet: that file is past the hard ceiling - see
.file-size-baseline.json / .pre-commit-scripts/check_file_size_ratchet.py). Pure extraction,
no behavior change: this was the ~480-line composite-quality-score section of
_compute_quality_metrics - every scoring curve (roe_score/roa_score/gross_profitability_score/
roce_score/fcf_margin_score/asset_turnover_score/debt_to_equity_score/margin_volatility_score)
plus the raw gross_profitability/operating_profitability/accruals_ratio/fcf_margin/
asset_turnover ratio computations and the final weighted_score composite. Mutates
`failed_metrics`/`implausible_ratio_metrics` in place (same lists the caller already owns) and
returns a dict of the handful of values the caller's later reason-writing code still needs -
every other local computed here (the *_score curves themselves, quality_components) is
write-only once the final weighted_score is produced, so it stays inside this method.
"""

from typing import TYPE_CHECKING, Any

from utils.type_conversion import safe_float


def _owner() -> Any:
    from loaders import load_value_quality_growth_metrics as _owner_mod

    return _owner_mod


class QualityScoreMixin:
    """See module docstring. Mixed into ValueQualityGrowthMetricsLoader alongside
    QualityMetricsMixin - every `self.` call here resolves normally through the instance.
    """

    if TYPE_CHECKING:

        def _margin_curve(self, value: float, breakpoints: list[tuple[float, float]]) -> float: ...

        def _get_symbol_industry(self, symbol: str) -> str | None: ...

        def _nan_to_none(self, value: float | None) -> float | None: ...

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

        def _weighted_avg(
            self, components: list[tuple[float | None, float]], min_weight_pct: float = 0.0
        ) -> float | None: ...

    def _compute_quality_composite_score(  # noqa: C901
        self,
        symbol: str,
        metrics: dict[str, Any],
        stockholders_equity: float | None,
        total_assets: float | None,
        operating_income_for_margin: float | None,
        interest_expense: float | None,
        gross_profit_used: float | None,
        net_income: float | None,
        operating_cash_flow: float | None,
        revenue: float | None,
        free_cash_flow: float | None,
        margin_volatility: float | None,
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
    ) -> dict[str, Any]:
        """Compute the composite quality_score (and the raw ratio fields feeding it) - see
        module docstring. `metrics` is read (roe/roa/roce_pct/debt_to_equity) but not written
        here; the caller writes every metrics[...] key from this method's returned dict.
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
        if stockholders_equity is not None and stockholders_equity <= 0:
            # Negative/zero book equity: net_income/equity can land positive when both are
            # negative (distressed co. with a loss on a negative equity base), which the
            # >1000 implausibility bound in _ratio_with_implausible_fallback doesn't catch
            # since it isn't a scale artifact - it's a real ratio that's directionally
            # meaningless. Floors to worst score rather than inverting into a spuriously
            # high one, same treatment as debt_to_equity_score below for the same reason.
            roe_score = 0.0
        # FIXED 2026-09-07 (goal: stock_scores factor/composite sanity audit, JPM/BAC/WFC/C/GS
        # live-confirmed): same industrial-curve-applied-to-every-sector bug class as
        # debt_to_equity_score below, for a DIFFERENT input - ROA (net_income/total_assets)
        # is structurally deflated for depository banks by their huge deposit-funded balance
        # sheet (a healthy bank's ROA is ~1-1.5%; the (3.0,40)/(8.0,80)/(15.0,100) industrial
        # curve, calibrated for asset-light industrial/services margins, floors JPM's real
        # ROA=1.29% to a ~17 score, WFC's 0.99% to ~13, etc.) - not a quality problem, the same
        # leverage-by-design fact the debt_to_equity bank/insurer curve fix already accounts
        # for on the liability side. Insurers get their own, less extreme curve: P&C
        # underwriters (PGR/TRV/ALL live-confirmed ROA 4.4-9.2%) run meaningfully higher than
        # life insurers (MET/PRU live-confirmed ROA ~0.45%) whose reserve-heavy balance sheets
        # behave more bank-like - INSURANCE_UNDERWRITER_INDUSTRIES lumps both (same precedent
        # as debt_to_equity_score's single blended insurer curve just below), hand-calibrated
        # to credit P&C-typical ROA highly without being so generous it validates a genuinely
        # weak life-insurer ROA. Thresholds hand-set (not FM-backtested), same as every other
        # curve in this function.
        # FIXED 2026-09-07 (goal: stock_scores factor/composite sanity audit, 10-electric-
        # utility + water/gas-distribution live-confirmed): same bug class again, for
        # regulated rate-base utilities - see UTILITY_INDUSTRIES's own comment for the full
        # live-verified evidence (ROA clustered 2.26-3.67% across 16 symbols).
        _symbol_industry_for_roa = self._get_symbol_industry(symbol)
        if _symbol_industry_for_roa in _owner().DEPOSITORY_BANK_INDUSTRIES:
            _roa_breakpoints = [(0.85, 40.0), (1.3, 80.0), (1.7, 100.0)]  # recalibrated+IC-validated 20260907
        elif _symbol_industry_for_roa in _owner().INSURANCE_UNDERWRITER_INDUSTRIES:
            _roa_breakpoints = [(2.5, 40.0), (5.5, 80.0), (10.0, 100.0)]
        elif _symbol_industry_for_roa in _owner().UTILITY_INDUSTRIES:
            _roa_breakpoints = [(2.2, 40.0), (3.3, 80.0), (5.0, 100.0)]
        else:
            _roa_breakpoints = [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)]
        roa_score = self._margin_curve(metrics["roa"], _roa_breakpoints) if metrics["roa"] is not None else None
        if total_assets is not None and total_assets <= 0:
            roa_score = 0.0
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
        #
        # FIXED 2026-09-07 (goal: stock_scores factor/composite sanity audit, JPM/BAC/WFC/C/
        # GS/MS/MET/PRU live-confirmed): same industrial-curve-applied-to-every-sector bug
        # class as debt_to_equity_score/roa_score above, for the SAME underlying cause -
        # capital_employed (line ~1053-1054) already uses debt_for_roic=total_liabilities
        # for depository banks/insurers (see that override's own comment), so a bank's
        # capital_employed is ~its entire (deposit-funded, hence enormous) balance sheet,
        # structurally floors roce_pct into single digits regardless of real capital
        # efficiency (JPM=3.85%, BAC=3.40%, WFC=3.03%, C=3.87%, GS=12.55%, MS=4.21% - the
        # 8.0-floors-to-~19/25.0-caps-to-100 industrial curve scored JPM/BAC/WFC/C around
        # 15-20 despite GS's genuinely-higher 12.55% showing real cross-sectional variation
        # exists to reward). Insurers get the same single blended curve precedent as
        # debt_to_equity_score/roa_score's INSURANCE_UNDERWRITER_INDUSTRIES override (P&C
        # underwriters PGR/TRV/ALL live-confirmed 5.72-11.79% run meaningfully higher than
        # life insurers MET/PRU's ~0.82-0.85%, same reserve-heavy-balance-sheet split ROA's
        # curve already accounts for) - hand-calibrated to credit P&C-typical ROCE highly
        # without being so generous it validates a genuinely weak life-insurer ROCE.
        # Breakpoints hand-set (not FM-backtested), same as every other curve in this
        # function - this curve-scored roce_score is provisional only, see the quality_
        # components comment below: update_quality_sector_neutral_scores() overwrites the
        # final quality_score for every sector via sector-neutral z-scoring of raw roce_pct.
        # FIXED 2026-09-07 (goal: stock_scores factor/composite sanity audit, same
        # utility evidence as roa_score/debt_to_equity_score): capital_employed for a
        # regulated utility is ~its entire rate-base-financed balance sheet, same structural
        # compression as banks/insurers - live-confirmed ROCE 3.96-7.23% across the same
        # 16-symbol utility set (see UTILITY_INDUSTRIES's own comment).
        roce_pct_val = metrics.get("roce_pct")
        _symbol_industry_for_roce = self._get_symbol_industry(symbol)
        if _symbol_industry_for_roce in _owner().DEPOSITORY_BANK_INDUSTRIES:
            _roce_breakpoints = [(3.0, 40.0), (6.0, 75.0), (10.0, 100.0)]
        elif _symbol_industry_for_roce in _owner().INSURANCE_UNDERWRITER_INDUSTRIES:
            _roce_breakpoints = [(3.5, 40.0), (7.0, 80.0), (12.0, 100.0)]  # recalibrated+IC-validated 20260907
        elif _symbol_industry_for_roce in _owner().UTILITY_INDUSTRIES:
            _roce_breakpoints = [(5.2, 40.0), (8.0, 80.0), (13.0, 100.0)]
        else:
            _roce_breakpoints = [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)]
        roce_score = self._margin_curve(roce_pct_val, _roce_breakpoints) if roce_pct_val is not None else None
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
        anchor_fcf_margin_implausible = (
            fcf_margin_free_cash_flow is not None
            and fcf_margin_revenue is not None
            and fcf_margin_revenue > 0
            and abs(fcf_margin_free_cash_flow / fcf_margin_revenue * 100.0) > 1000
        )
        if (
            fcf_margin_free_cash_flow is None
            or fcf_margin_revenue is None
            or fcf_margin_revenue <= 0
            or anchor_fcf_margin_implausible
        ):
            # anchor_fcf_margin_implausible also routes here (not just None/<=0) - a
            # near-zero-revenue anchor year is an extraction artifact, not a real business
            # characteristic, and an older fiscal year can have a plausible pair even when
            # the anchor doesn't (same gap class as operating_margin/net_margin's
            # _find_plausible_cross_year_ratio, fixed 2026-09-05 - this metric has its own
            # inline cross-table (cash_flow+income_statement) query instead of reusing that
            # helper because it needs a join those single-table lookups don't).
            #
            # FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" sweep): neither side of
            # this JOIN filtered `data_unavailable`, so a disclaimed row's leftover stray
            # non-NULL free_cash_flow/revenue value could feed fcf_margin directly. Live-
            # confirmed 147 affected rows, e.g. BRK.A/BRK.B 2026 (free_cash_flow=$5.452B,
            # revenue=$63.137B, both flagged data_unavailable=TRUE) and CEG 2026.
            with _owner().DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT free_cash_flow, revenue
                    FROM annual_cash_flow acf
                    JOIN annual_income_statement ais
                      ON ais.symbol = acf.symbol AND ais.fiscal_year = acf.fiscal_year
                    WHERE acf.symbol = %s AND acf.free_cash_flow IS NOT NULL AND ais.revenue IS NOT NULL
                      AND acf.data_unavailable IS NOT TRUE AND ais.data_unavailable IS NOT TRUE
                      AND acf.fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                    ORDER BY acf.fiscal_year DESC
                    """,
                    (symbol,),
                )
                fallback_fcf_rows = cur.fetchall()

                # row[0]/row[1] are raw Decimal; must cast to float before arithmetic here -
                # `Decimal * float` raises TypeError, which propagates through this
                # function's outer try/except and wipes out EVERY quality_metrics field for
                # the symbol, not just fcf_margin.
                def _plausible_fcf_row(row: tuple[Any, Any]) -> bool:
                    return (
                        row[1] is not None and float(row[1]) > 0 and abs(float(row[0]) / float(row[1]) * 100.0) <= 1000
                    )

                fallback_fcf_row = next((row for row in fallback_fcf_rows if _plausible_fcf_row(row)), None)
                # FIXED 2026-09-06 (goal: "SEC/XBRL implausible values to zero" sweep):
                # previously only widened to the full-history query when the 3-year window
                # returned ZERO rows - a window that returns SOME rows, none of them
                # plausible (live-confirmed ALT: 2025/2023 both near-zero-revenue clinical-
                # stage artifacts), never got a chance to see its own genuinely plausible
                # older years (ALT 2010: FCF -$15.2M/revenue $21.0M, -72.6% margin, real and
                # representative) - the `next(..., fallback_fcf_rows[0])` default just
                # accepted the nearest IMPLAUSIBLE row instead, which then failed the
                # |margin|>1000 check below anyway and reported implausible_ratio despite a
                # real usable year existing further back. Only queries again when the
                # 3-year window didn't already yield a plausible candidate - the common case
                # (a plausible recent year) never pays for the extra round-trip.
                if fallback_fcf_row is None:
                    cur = None
                    with _owner().DatabaseContext("read") as cur:
                        cur.execute(
                            """
                            SELECT free_cash_flow, revenue
                            FROM annual_cash_flow acf
                            JOIN annual_income_statement ais
                              ON ais.symbol = acf.symbol AND ais.fiscal_year = acf.fiscal_year
                            WHERE acf.symbol = %s AND acf.free_cash_flow IS NOT NULL AND ais.revenue IS NOT NULL
                              AND acf.data_unavailable IS NOT TRUE AND ais.data_unavailable IS NOT TRUE
                            ORDER BY acf.fiscal_year DESC
                            """,
                            (symbol,),
                        )
                        full_history_rows = cur.fetchall()
                    fallback_fcf_row = next(
                        (row for row in full_history_rows if _plausible_fcf_row(row)),
                        fallback_fcf_rows[0]
                        if fallback_fcf_rows
                        else (full_history_rows[0] if full_history_rows else None),
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
        # FIXED 2026-09-07 (goal: stock_scores factor/composite sanity audit, JPM/GS/WFC/C
        # live-confirmed): fcf_margin_score is excluded (not scored) for depository banks -
        # their free_cash_flow (operating_cash_flow - capex) is dominated by loan
        # origination/deposit-balance swings unrelated to real operating profitability
        # (JPM live-confirmed fcf_margin=-81.00%, GS=-81.02%, WFC=-22.70%, C=-87.01% in the
        # same period BAC=+11.15% - the sign/magnitude is balance-sheet noise, not a real
        # profitability signal), the identical root cause tie_out.py's cashflow_reconciliation
        # check already exempts depository institutions from (see that check's own
        # _DEPOSITORY_INSTITUTION_SIC_CODES comment). metrics["fcf_margin"] itself is left
        # untouched (still computed/persisted/displayed) - only its contribution to
        # profitability_cluster_score is removed, same "raw value kept, not scored" treatment
        # asset_turnover_score already gets for Financial Services/Real Estate above.
        # ADDED 2026-09-07: same exclusion, extended to regulated utilities - continuous
        # grid/generation capex routinely drives FCF margin deeply negative (NEE -42%,
        # XEL -46%, D -44% live-confirmed) even for fundamentally healthy, dividend-growing
        # utilities. See UTILITY_INDUSTRIES's own comment for the full evidence.
        fcf_margin_score = (
            self._margin_curve(fcf_margin, [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)])
            if fcf_margin is not None
            and self._get_symbol_industry(symbol) not in _owner().DEPOSITORY_BANK_INDUSTRIES
            and self._get_symbol_industry(symbol) not in _owner().UTILITY_INDUSTRIES
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
        #
        # FIXED 2026-09-07 (goal: stock_scores factor/composite sanity audit): this
        # industrial-leverage curve was being fed the SAME debt_to_equity value the
        # depository-bank/insurance-underwriter override above deliberately inflates by
        # using total_liabilities (deposits/policy reserves) as the debt numerator - see
        # that override's comment. A deposit-funded bank sits at 8-15x by construction
        # (JPM/BAC/WFC live-verified at 10.25/11.21/10.85), so the 2.0-floors-to-0 curve
        # zeroed this component for essentially every bank/insurer in the universe
        # regardless of actual balance-sheet health, dragging down ~25-27% of their
        # Quality safety_cluster_score (see the Financial Services/Real Estate branch
        # below) no matter how well-capitalized they actually were. The curve's breakpoints
        # were never recalibrated when the metric definition changed for these two sectors.
        # Separate curves below, scaled to each sector's typical deposit/reserve-inclusive
        # range (banks ~8-15x, insurers ~2.5-11.5x per the override comment's live-verified
        # figures) rather than the industrial 0.5/1.0/2.0x scale.
        # FIXED 2026-09-07 (goal: stock_scores factor/composite sanity audit, 16-utility
        # live-confirmed): regulated rate-base utilities run 1.11-1.91x debt_to_equity by
        # design (regulators set allowed ROE against a rate base partly debt-financed) - see
        # UTILITY_INDUSTRIES's own comment. Unlike the bank/insurer overrides above, this
        # uses the SAME debt_to_equity value (long_term_debt-based, not total_liabilities) -
        # utilities don't get the deposit/reserve-style debt_for_roic override, so no
        # separate inflated-input caveat applies here, just a rescaled curve.
        debt_to_equity_val = metrics.get("debt_to_equity")
        _symbol_industry_for_de = self._get_symbol_industry(symbol)
        if debt_to_equity_val is None:
            debt_to_equity_score = None
        elif debt_to_equity_val < 0:
            debt_to_equity_score = 0.0
        elif _symbol_industry_for_de in _owner().DEPOSITORY_BANK_INDUSTRIES:
            debt_to_equity_score = max(0.0, min(100.0, 100.0 - (debt_to_equity_val / 20.0) * 100.0))
        elif _symbol_industry_for_de in _owner().INSURANCE_UNDERWRITER_INDUSTRIES:
            debt_to_equity_score = max(0.0, min(100.0, 100.0 - (debt_to_equity_val / 12.0) * 100.0))
        elif _symbol_industry_for_de in _owner().UTILITY_INDUSTRIES:
            debt_to_equity_score = max(0.0, min(100.0, 100.0 - (debt_to_equity_val / 4.0) * 100.0))
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
        # REWRITE 2026-09-07 ("best and brightest" scoring-methodology directive): this used
        # to be a sector-conditional structure - Financial Services/Real Estate/Utilities got
        # a 7-input two-cluster (profitability+safety) blend with asset_turnover_score dropped
        # entirely, because isolated FM testing under the OLD absolute-curve architecture found
        # asset_turnover hurt those sectors' signal. That finding doesn't carry over: it was
        # diagnosed against symbols scored on an industrial-calibrated absolute curve with zero
        # sector peer context, not against the sector-neutral z-score this composite now feeds
        # (see update_quality_sector_neutral_scores() below) - within-sector z-scoring compares
        # a bank's asset turnover to OTHER banks/insurers, not to industrials, which is a
        # different (and per Barra/AQR, the correct) comparison. One flat, uniformly-weighted
        # structure for every sector now, matching Risk/Momentum/Growth's own single-formula
        # convention and published multi-factor methodology (no per-sector aggregation shape).
        #
        # This composite is PROVISIONAL - update_quality_sector_neutral_scores() (further
        # below) unconditionally overwrites quality_score for every symbol, every sector, via
        # sector-neutral z-scoring of the raw metrics stored below. This flat structure exists
        # so a symbol still has a sane quality_score in the window between Pass 1 and that
        # batch pass (or if it's ever skipped), not because Pass 1's curve math is the final
        # word.
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
        # floor should treat this as thin data.
        min_quality_weight_pct = 40.0
        available_quality_weight = sum(w for v, w in quality_components if v is not None)
        weighted_score = self._weighted_avg(quality_components, min_weight_pct=min_quality_weight_pct)
        return {
            "gross_profitability": gross_profitability,
            "operating_profitability": operating_profitability,
            "operating_profitability_negative_equity": operating_profitability_negative_equity,
            "accruals_ratio": accruals_ratio,
            "fcf_margin": fcf_margin,
            "asset_turnover": asset_turnover,
            "weighted_score": weighted_score,
            "available_quality_weight": available_quality_weight,
            "min_quality_weight_pct": min_quality_weight_pct,
        }
