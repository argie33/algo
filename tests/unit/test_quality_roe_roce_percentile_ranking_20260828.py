"""Tests for ValueQualityGrowthMetricsLoader.update_quality_sector_neutral_scores() and its
supporting _margin_curve (loaders/load_value_quality_growth_metrics.py).

REBUILT 2026-09-16 (factor-purity sweep, user: "we do what the industry does only") to match
MSCI's real, published Quality Indexes Methodology (see vqg_quality_batch.py's own docstring
for the full citation and the 3-step construction: universe-wide z-score per variable ->
equal-weighted composite (ROE mandatory) -> sector-relative z-score of the composite ->
+/-3 winsorize -> percentile scale). SUPERSEDES the prior version of this file, which pinned
the reconciliation arithmetic of the 8-component AQR/MSCI blend this method used from
2026-09-07 through 2026-09-15 - that construction no longer exists in the live code.

Row shape (matches the real SELECT in update_quality_sector_neutral_scores() exactly):
(symbol, sector, industry, roe, roa, roce_pct, fcf_margin, debt_to_equity, margin_volatility,
 asset_turnover, gross_profitability, quality_score_old, is_fpi, market_cap,
 earnings_variability). roa/roce_pct/fcf_margin/margin_volatility/asset_turnover/
gross_profitability are still SELECTed (other consumers still read quality_metrics'
raw columns) but only roe/roa (sign-flip guard)/debt_to_equity/earnings_variability actually
feed the live score - see vqg_quality_batch.py's own docstring for why.
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
    roe: float | None,
    roa: float | None,
    debt_to_equity: float | None,
    earnings_variability: float | None,
    quality_score_old: float = 1.0,
    sector: str = "Technology",
) -> tuple:
    return (
        symbol,
        sector,
        None,  # industry
        roe,
        roa,
        None,  # roce_pct - unused by live scoring
        None,  # fcf_margin - unused by live scoring
        debt_to_equity,
        None,  # margin_volatility - unused by live scoring
        None,  # asset_turnover - unused by live scoring
        None,  # gross_profitability - unused by live scoring
        quality_score_old,
        False,  # is_fpi
        None,  # market_cap
        earnings_variability,
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
    """End-to-end test against a fully mocked DB, driving the real MSCI 3-variable
    construction (universe-wide per-leg z-score -> composite -> sector-relative -> +/-3
    winsorize -> percentile scale)."""

    def test_single_symbol_all_legs_reconciles_to_neutral_50(self) -> None:
        # A lone symbol, no peers anywhere: universe-wide z-score is 0.0 for lack of anything
        # to compare against (singleton pool), and the sector-relative composite z-score is
        # ALSO 0.0 for the same reason -> zscore_to_percentile_scale maps 0.0 to neutral 50.0.
        row = _row("ONLY", roe=15.0, roa=10.0, debt_to_equity=0.5, earnings_variability=10.0)
        updates = dict(_run_with_mocked_rows([row]))
        assert updates["ONLY"] == 50.0

    def test_two_peers_higher_roe_scores_higher(self) -> None:
        # Same D/E and Earnings Variability for both - only ROE differs. The symbol with the
        # cheaper (higher) ROE must score higher.
        rows = [
            _row("HIGH_ROE", roe=30.0, roa=10.0, debt_to_equity=0.5, earnings_variability=10.0),
            _row("LOW_ROE", roe=5.0, roa=10.0, debt_to_equity=0.5, earnings_variability=10.0),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        assert updates["HIGH_ROE"] > updates["LOW_ROE"]

    def test_roe_sign_flip_distress_floors_to_worst(self) -> None:
        # Positive ROE but negative ROA is the classic double-negative-sign-flip artifact
        # (negative equity, negative net income) - floored to the worst z-score (-3.0, MSCI's
        # own winsorization bound), not scored as if it were genuinely excellent.
        rows = [
            _row("DISTRESS", roe=900.0, roa=-40.0, debt_to_equity=0.5, earnings_variability=10.0),
            _row("HEALTHY", roe=15.0, roa=10.0, debt_to_equity=0.5, earnings_variability=10.0),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        assert updates["DISTRESS"] < updates["HEALTHY"]

    def test_roe_missing_produces_no_score_even_with_other_legs_present(self) -> None:
        # MSCI Appendix II Case 1/4: ROE is MANDATORY - missing ROE means no score at all,
        # even when BOTH Debt-to-Equity and Earnings Variability are present.
        row = _row("NOROE", roe=None, roa=None, debt_to_equity=0.5, earnings_variability=10.0)
        assert _run_with_mocked_rows([row]) == []

    def test_debt_to_equity_alone_missing_still_scores_from_remaining_two(self) -> None:
        # MSCI Appendix II Case 3: D/E missing, ROE + Earnings Variability still score.
        rows = [
            _row("NODE", roe=15.0, roa=10.0, debt_to_equity=None, earnings_variability=10.0),
            _row("PEER", roe=15.0, roa=10.0, debt_to_equity=0.5, earnings_variability=10.0),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        assert "NODE" in updates

    def test_negative_debt_to_equity_floors_to_worst(self) -> None:
        # Negative D/E (negative book equity) is real distress, floored to -3.0 like Value's
        # own negative-book-value treatment - not excluded/renormalized away.
        rows = [
            _row("NEGDE", roe=15.0, roa=10.0, debt_to_equity=-0.5, earnings_variability=10.0),
            _row("HEALTHY", roe=15.0, roa=10.0, debt_to_equity=0.5, earnings_variability=10.0),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        assert updates["NEGDE"] < updates["HEALTHY"]

    def test_all_components_missing_produces_no_update(self) -> None:
        row = _row("EMPTY", roe=None, roa=None, debt_to_equity=None, earnings_variability=None)
        assert _run_with_mocked_rows([row]) == []

    def test_score_unchanged_produces_no_write(self) -> None:
        # Same shape as the lone-symbol case above, but quality_score_old already matches the
        # recomputed 50.0 - no write should be issued (this pass never rewrites a row whose
        # recomputed score is identical, to avoid needless updated_at churn every run).
        row = _row("SAME", roe=15.0, roa=10.0, debt_to_equity=0.5, earnings_variability=10.0, quality_score_old=50.0)
        assert _run_with_mocked_rows([row]) == []
