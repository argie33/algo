"""Tests for QualityBatchMixin.update_quality_sector_neutral_scores() and its supporting
_margin_curve (loaders/helpers/vqg_quality_batch.py).

RESTORED 2026-09-17 (MSCI-fidelity reversion - see vqg_quality_batch.py's own
"RESTORED TO MSCI'S REAL 3-VARIABLE QUALITY INDEX" docstring for the full record). This
SUPERSEDES a same-day intermediate version of this file that had been rebuilt for an AQR
Quality Minus Junk (QMJ) 4/3-leg pivot; that pivot was itself reverted the same day in favor
of MSCI fidelity for Value/Momentum/Quality, so the QMJ leg-based construction this file used
to describe no longer exists in the live code.

Construction is now MSCI's real 3-variable Quality Index: z-score ROE, Debt-to-Equity and
Earnings-Variability UNIVERSE-WIDE (market-cap-weighted), equal-weighted composite of the
available variables (ROE mandatory - Appendix II Cases 1/4; D/E or Earnings-Variability alone
still scores per Cases 2/3), re-standardize the composite universe-wide, +/-3 winsorize,
percentile scale. gross_profitability/net_payout_yield/accruals_ratio are QMJ-era fields kept
in the row shape for backward-compat fixture shape only - they are not read by the current
construction.

Row shape (matches the real SELECT in update_quality_sector_neutral_scores() exactly):
(symbol, roe, roa, debt_to_equity, quality_score_old, earnings_variability,
 gross_profitability, gross_margin, accruals_ratio, net_payout_yield).
"""

from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader as L


class TestMarginCurveStillUsedByPass1:
    """_margin_curve is now Pass-1-only (PROVISIONAL scoring in vqg_quality.py, always
    overwritten by update_quality_sector_neutral_scores) - still pinned here since this file
    owns the shared definition."""

    def test_roe_breakpoints(self) -> None:
        assert L._margin_curve(10.0, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)]) == 50.0
        assert L._margin_curve(20.0, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)]) == 85.0
        assert L._margin_curve(40.0, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)]) == 100.0
        assert L._margin_curve(151.91, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)]) == 100.0

    def test_negative_value_floors_at_zero(self) -> None:
        assert L._margin_curve(-5.0, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)]) == 0.0


def _row(
    symbol: str,
    roe: float | None = None,
    roa: float | None = None,
    debt_to_equity: float | None = None,
    earnings_variability: float | None = None,
    gross_profitability: float | None = None,
    gross_margin: float | None = None,
    accruals_ratio: float | None = None,
    net_payout_yield: float | None = None,
    quality_score_old: float = 1.0,
) -> tuple:
    return (
        symbol,
        roe,
        roa,
        debt_to_equity,
        quality_score_old,
        earnings_variability,
        gross_profitability,
        gross_margin,
        accruals_ratio,
        net_payout_yield,
    )


def _run_with_mocked_rows(rows: list[tuple]) -> list[tuple[str, float]]:
    mock_cur = MagicMock()
    # side_effect, not return_value: update_quality_sector_neutral_scores ALSO calls
    # _withhold_quality_below_floor(), a second SELECT reusing this same mocked cursor - a
    # shared return_value would spuriously re-serve the main rows as "below the liquidity
    # floor" too. Only the first fetchall() (the correction pass) sees `rows`.
    mock_cur.fetchall.side_effect = [rows, []]
    with (
        patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_ctx,
        patch("loaders.load_value_quality_growth_metrics.execute_values") as mock_execute_values,
    ):
        mock_ctx.return_value.__enter__.return_value = mock_cur
        loader = L.__new__(L)  # bypass __init__, this method has no instance state dependency
        loader.update_quality_sector_neutral_scores()
    if not mock_execute_values.called:
        return []
    _cur_arg, _sql, updates = mock_execute_values.call_args[0][:3]
    return list(updates)


class TestUpdateQualitySectorNeutralScoresReconciliation:
    """End-to-end test against a fully mocked DB, driving the real MSCI 3-variable Quality
    Index construction (universe-wide ROE/Debt-to-Equity/Earnings-Variability z-scores ->
    equal-weighted composite (ROE mandatory) -> re-standardized universe-wide -> +/-3
    winsorize -> percentile scale)."""

    def test_single_symbol_all_variables_reconciles_to_neutral_50(self) -> None:
        # A lone symbol, no peers anywhere: every universe-wide z-score is 0.0 for lack of
        # anything to compare against (singleton pool) -> zscore_to_percentile_scale maps
        # 0.0 to neutral 50.0.
        row = _row(
            "ONLY",
            roe=15.0,
            roa=10.0,
            debt_to_equity=0.5,
            earnings_variability=10.0,
            gross_profitability=20.0,
            gross_margin=40.0,
            accruals_ratio=1.0,
            net_payout_yield=2.0,
        )
        updates = dict(_run_with_mocked_rows([row]))
        assert updates["ONLY"] == 50.0

    def test_two_peers_higher_roe_scores_higher(self) -> None:
        # Every other variable identical for both - only ROE differs. The symbol with the
        # higher ROE must score higher.
        rows = [
            _row(
                "HIGH_ROE",
                roe=30.0,
                roa=10.0,
                debt_to_equity=0.5,
                earnings_variability=10.0,
                gross_profitability=20.0,
                gross_margin=40.0,
                accruals_ratio=1.0,
            ),
            _row(
                "LOW_ROE",
                roe=5.0,
                roa=10.0,
                debt_to_equity=0.5,
                earnings_variability=10.0,
                gross_profitability=20.0,
                gross_margin=40.0,
                accruals_ratio=1.0,
            ),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        assert updates["HIGH_ROE"] > updates["LOW_ROE"]

    def test_roe_sign_flip_distress_floors_to_worst(self) -> None:
        # Positive ROE but negative ROA is the classic double-negative-sign-flip artifact
        # (negative equity, negative net income) - floored to the worst z-score contribution
        # (-3.0) for ROE, not scored as if it were genuinely excellent.
        rows = [
            _row(
                "DISTRESS",
                roe=900.0,
                roa=-40.0,
                debt_to_equity=0.5,
                earnings_variability=10.0,
                gross_profitability=20.0,
                gross_margin=40.0,
                accruals_ratio=1.0,
            ),
            _row(
                "HEALTHY",
                roe=15.0,
                roa=10.0,
                debt_to_equity=0.5,
                earnings_variability=10.0,
                gross_profitability=20.0,
                gross_margin=40.0,
                accruals_ratio=1.0,
            ),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        assert updates["DISTRESS"] < updates["HEALTHY"]

    def test_roe_missing_produces_no_score(self) -> None:
        # ROE IS MANDATORY (MSCI Appendix II Cases 1/4) - a symbol with only non-scored
        # QMJ-era fields (net_payout_yield) populated, and no ROE, gets no score at all
        # regardless of what else is present.
        row = _row("THIN", net_payout_yield=2.0)
        assert _run_with_mocked_rows([row]) == []

    def test_roe_plus_one_variable_still_scores(self) -> None:
        # ROE + Earnings-Variability (Debt-to-Equity missing) is one of MSCI's Appendix II
        # 2-of-3 substitution cases (Case 2/3) - still scores off an equal-weighted average
        # of the 2 available variables.
        rows = [
            _row("ROE_PLUS_ONE", roe=20.0, roa=10.0, earnings_variability=10.0),
            _row("PEER", roe=5.0, roa=10.0, earnings_variability=30.0),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        assert "ROE_PLUS_ONE" in updates

    def test_negative_debt_to_equity_floors_to_worst(self) -> None:
        # Negative D/E (negative book equity) is real distress, floored to -3.0 for that
        # variable, like Value's own negative-book-value treatment - not treated as
        # spuriously "great, zero leverage".
        rows = [
            _row(
                "NEGDE",
                roe=15.0,
                roa=10.0,
                debt_to_equity=-0.5,
                earnings_variability=10.0,
                gross_profitability=20.0,
                gross_margin=40.0,
                accruals_ratio=1.0,
            ),
            _row(
                "HEALTHY",
                roe=15.0,
                roa=10.0,
                debt_to_equity=0.5,
                earnings_variability=10.0,
                gross_profitability=20.0,
                gross_margin=40.0,
                accruals_ratio=1.0,
            ),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        assert updates["NEGDE"] < updates["HEALTHY"]

    def test_all_components_missing_produces_no_update(self) -> None:
        row = _row("EMPTY")
        assert _run_with_mocked_rows([row]) == []

    def test_score_unchanged_produces_no_write(self) -> None:
        # Same shape as the lone-symbol case above, but quality_score_old already matches the
        # recomputed 50.0 - no write should be issued (this pass never rewrites a row whose
        # recomputed score is identical, to avoid needless updated_at churn every run).
        row = _row(
            "SAME",
            roe=15.0,
            roa=10.0,
            debt_to_equity=0.5,
            earnings_variability=10.0,
            gross_profitability=20.0,
            gross_margin=40.0,
            accruals_ratio=1.0,
            net_payout_yield=2.0,
            quality_score_old=50.0,
        )
        assert _run_with_mocked_rows([row]) == []
