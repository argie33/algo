"""Tests for QualityBatchMixin.update_quality_sector_neutral_scores() and its supporting
_margin_curve (loaders/helpers/vqg_quality_batch.py).

REBUILT 2026-09-17 (factor-purity pivot: MSCI -> AQR only, user directive - "we are not
using industry standard AQR yet for all the factors... get rid of the msci and all this
other shit") to match Asness/Frazzini/Pedersen 2019 "Quality Minus Junk" (see
vqg_quality_batch.py's own docstring for the full citation and the real 4-leg construction:
Profitability/Growth/Safety/Payout, each a re-standardized sum of z-scored sub-components,
then a re-standardized sum of the available legs, +/-3 winsorize, percentile scale).
SUPERSEDES the prior version of this file, which pinned the reconciliation arithmetic of the
MSCI 3-variable Quality Index (ROE/Debt-to-Equity/Earnings-Variability) that construction has
replaced - that construction no longer exists in the live code.

Row shape (matches the real SELECT in update_quality_sector_neutral_scores() exactly):
(symbol, roe, roa, debt_to_equity, quality_score_old, earnings_variability,
 gross_profitability, gross_margin, accruals_ratio, roe_trend, gross_margin_trend,
 net_payout_yield).
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
    roe_trend: float | None = None,
    gross_margin_trend: float | None = None,
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
        roe_trend,
        gross_margin_trend,
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
    """End-to-end test against a fully mocked DB, driving the real AQR QMJ construction
    (universe-wide sub-component z-scores -> per-leg re-standardized sum -> composite
    re-standardized sum -> +/-3 winsorize -> percentile scale)."""

    def test_single_symbol_all_legs_reconciles_to_neutral_50(self) -> None:
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
            roe_trend=1.0,
            gross_margin_trend=1.0,
            net_payout_yield=2.0,
        )
        updates = dict(_run_with_mocked_rows([row]))
        assert updates["ONLY"] == 50.0

    def test_two_peers_higher_roe_scores_higher(self) -> None:
        # Every other sub-component identical for both - only ROE (a Profitability leg
        # sub-component) differs. The symbol with the higher ROE must score higher.
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
        # (-3.0) within the Profitability leg, not scored as if it were genuinely excellent.
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

    def test_thin_single_leg_produces_no_score(self) -> None:
        # QUALITY_MIN_LEGS_AVAILABLE=2 - a symbol with only the Payout leg available (net_
        # payout_yield alone) is a thinner sample than one scored off multiple legs and must
        # not renormalize up to a full-confidence score, same principle as GROWTH_MIN_FIELDS_
        # AVAILABLE / VALUE_MIN_WEIGHT elsewhere in this codebase.
        row = _row("THIN", net_payout_yield=2.0)
        assert _run_with_mocked_rows([row]) == []

    def test_two_legs_available_still_scores(self) -> None:
        # Profitability (via gross_profitability) + Safety (via earnings_variability) is 2
        # legs - clears QUALITY_MIN_LEGS_AVAILABLE even with ROE/debt_to_equity/growth/payout
        # all missing.
        rows = [
            _row("TWO_LEGS", gross_profitability=20.0, earnings_variability=10.0),
            _row("PEER", gross_profitability=5.0, earnings_variability=30.0),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        assert "TWO_LEGS" in updates

    def test_negative_debt_to_equity_floors_to_worst(self) -> None:
        # Negative D/E (negative book equity) is real distress, floored to -3.0 within the
        # Safety leg like Value's own negative-book-value treatment - not treated as
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
            roe_trend=1.0,
            gross_margin_trend=1.0,
            net_payout_yield=2.0,
            quality_score_old=50.0,
        )
        assert _run_with_mocked_rows([row]) == []
