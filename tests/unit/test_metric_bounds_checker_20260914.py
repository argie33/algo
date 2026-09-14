"""Regression tests for MetricBoundsChecker
(algo/monitoring/data_patrol/checks/metric_bounds.py).

Added 2026-09-14 (Yahoo-metric coverage sweep): stability_metrics/positioning_metrics/
insider_transaction_velocity/growth_metrics's forward fields/dividend_data/
analyst_sentiment_analysis were all CAPTURED but had zero correctness/bounds validation - only
staleness coverage. Same review-queue philosophy as score_ratio_outliers.py's own tests.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.metric_bounds import MetricBoundsChecker
from algo.monitoring.data_patrol.config import ERROR, INFO, WARN, PatrolConfig


def _checker() -> MetricBoundsChecker:
    return MetricBoundsChecker(PatrolConfig())


def _cursor(fetchone_rows: list[dict], fetchall_sequence: list[list[dict]]) -> MagicMock:
    """fetchone_rows: one per COUNT(*) call. fetchall_sequence: one list per SELECT ... query,
    consumed in call order."""
    cur = MagicMock()
    cur.fetchone.side_effect = fetchone_rows
    cur.fetchall.side_effect = fetchall_sequence
    return cur


class TestStabilityMetricsBounds:
    def test_all_clean_logs_info_for_every_subcheck(self) -> None:
        # 1 COUNT(*) + 6 volatility fields + 1 max_drawdown + 1 beta = 9 queries total.
        cur = _cursor([{"total": 100}], [[] for _ in range(8)])
        checker = _checker()
        checker.check_stability_metrics_bounds(cur)
        assert len(checker.results) == 8
        assert all(r.severity == INFO for r in checker.results)

    def test_negative_volatility_logs_error_with_flagged_symbols(self) -> None:
        fetchall_seq = [[{"symbol": "BADVOL", "val": -0.5}]] + [[] for _ in range(7)]
        cur = _cursor([{"total": 100}], fetchall_seq)
        checker = _checker()
        checker.check_stability_metrics_bounds(cur)
        vol_result = checker.results[0]
        assert vol_result.severity == ERROR
        assert vol_result.details["flagged_symbols"] == [
            {
                "symbol": "BADVOL",
                "value": -0.5,
                "reason": "volatility_30d < 0 is mathematically impossible for a variance-derived measure",
            }
        ]

    def test_impossible_drawdown_logs_error(self) -> None:
        fetchall_seq = [[] for _ in range(6)] + [[{"symbol": "BADDD", "val": -150.0}]] + [[]]
        cur = _cursor([{"total": 100}], fetchall_seq)
        checker = _checker()
        checker.check_stability_metrics_bounds(cur)
        dd_result = checker.results[6]
        assert dd_result.severity == ERROR
        assert dd_result.details["flagged_symbols"][0]["symbol"] == "BADDD"

    def test_extreme_beta_logs_warn_not_error(self) -> None:
        fetchall_seq = [[] for _ in range(7)] + [[{"symbol": "LEVERAGED", "val": 12.0}]]
        cur = _cursor([{"total": 100}], fetchall_seq)
        checker = _checker()
        checker.check_stability_metrics_bounds(cur)
        beta_result = checker.results[7]
        assert beta_result.severity == WARN
        assert beta_result.details["flagged_symbols"][0]["symbol"] == "LEVERAGED"


class TestPositioningMetricsBounds:
    def test_all_clean_logs_info(self) -> None:
        # 1 COUNT(*) + 2 hard-capped pct fields + (2 uncapped pct fields * 2 queries each) +
        # 1 short_ratio = 8 queries.
        cur = _cursor([{"total": 100}], [[] for _ in range(7)])
        checker = _checker()
        checker.check_positioning_metrics_bounds(cur)
        assert all(r.severity == INFO for r in checker.results)

    def test_ownership_over_100_pct_logs_error(self) -> None:
        fetchall_seq = [[{"symbol": "OVEROWNED", "val": 150.0}]] + [[] for _ in range(6)]
        cur = _cursor([{"total": 100}], fetchall_seq)
        checker = _checker()
        checker.check_positioning_metrics_bounds(cur)
        result = checker.results[0]
        assert result.severity == ERROR
        assert "can't own more than 100%" in result.details["flagged_symbols"][0]["reason"]

    def test_short_percent_of_float_over_300_logs_warn(self) -> None:
        # order: [inst_own, top10] hard-capped (2), then [short_interest_pct neg, short_interest_pct
        # over300, short_percent_of_float neg, short_percent_of_float over300], then short_ratio.
        fetchall_seq = [[], [], [], [], [], [{"symbol": "SQUEEZED", "val": 350.0}], []]
        cur = _cursor([{"total": 100}], fetchall_seq)
        checker = _checker()
        checker.check_positioning_metrics_bounds(cur)
        squeeze_results = [r for r in checker.results if r.severity == WARN]
        assert len(squeeze_results) == 1
        assert squeeze_results[0].details["flagged_symbols"][0]["symbol"] == "SQUEEZED"

    def test_negative_short_ratio_logs_error(self) -> None:
        fetchall_seq = [[] for _ in range(6)] + [[{"symbol": "NEGRATIO", "val": -1.0}]]
        cur = _cursor([{"total": 100}], fetchall_seq)
        checker = _checker()
        checker.check_positioning_metrics_bounds(cur)
        result = checker.results[-1]
        assert result.severity == ERROR
        assert result.details["flagged_symbols"][0]["symbol"] == "NEGRATIO"


class TestInsiderVelocityBounds:
    def test_all_clean_logs_info(self) -> None:
        cur = _cursor([{"total": 100}], [[], [], []])
        checker = _checker()
        checker.check_insider_velocity_bounds(cur)
        assert len(checker.results) == 3
        assert all(r.severity == INFO for r in checker.results)

    def test_negative_ratio_logs_error(self) -> None:
        cur = _cursor([{"total": 100}], [[{"symbol": "NEGBSR", "val": -0.5}], [], []])
        checker = _checker()
        checker.check_insider_velocity_bounds(cur)
        assert checker.results[0].severity == ERROR
        assert checker.results[0].details["flagged_symbols"][0]["symbol"] == "NEGBSR"

    def test_confidence_score_out_of_range_logs_error(self) -> None:
        cur = _cursor([{"total": 100}], [[], [], [{"symbol": "BADCONF", "val": 150.0}]])
        checker = _checker()
        checker.check_insider_velocity_bounds(cur)
        result = checker.results[-1]
        assert result.severity == ERROR
        assert result.details["flagged_symbols"][0]["symbol"] == "BADCONF"


class TestGrowthMetricsForwardFieldMagnitude:
    def test_all_clean_logs_info(self) -> None:
        cur = _cursor([{"total": 100}], [[] for _ in range(5)])
        checker = _checker()
        checker.check_growth_metrics_forward_field_magnitude(cur)
        assert len(checker.results) == 5
        assert all(r.severity == INFO for r in checker.results)

    def test_extreme_magnitude_logs_warn(self) -> None:
        fetchall_seq = [[{"symbol": "DXSHAPED", "val": 3000.0}]] + [[] for _ in range(4)]
        cur = _cursor([{"total": 100}], fetchall_seq)
        checker = _checker()
        checker.check_growth_metrics_forward_field_magnitude(cur)
        result = checker.results[0]
        assert result.severity == WARN
        assert result.details["flagged_symbols"][0]["symbol"] == "DXSHAPED"


class TestDividendDataBounds:
    def test_all_clean_logs_info(self) -> None:
        cur = _cursor([{"total": 100}], [[], [], []])
        checker = _checker()
        checker.check_dividend_data_bounds(cur)
        assert len(checker.results) == 3
        assert all(r.severity == INFO for r in checker.results)

    def test_negative_dividend_per_share_logs_error(self) -> None:
        cur = _cursor([{"total": 100}], [[{"symbol": "NEGDIV", "val": -1.0}], [], []])
        checker = _checker()
        checker.check_dividend_data_bounds(cur)
        assert checker.results[0].severity == ERROR

    def test_yield_over_25_pct_logs_warn(self) -> None:
        cur = _cursor([{"total": 100}], [[], [], [{"symbol": "HIGHYIELD", "val": 40.0}]])
        checker = _checker()
        checker.check_dividend_data_bounds(cur)
        result = checker.results[-1]
        assert result.severity == WARN
        assert result.details["flagged_symbols"][0]["symbol"] == "HIGHYIELD"


class TestAnalystSentimentBounds:
    def test_all_clean_logs_info(self) -> None:
        cur = _cursor([{"total": 100}], [[], []])
        checker = _checker()
        checker.check_analyst_sentiment_bounds(cur)
        assert len(checker.results) == 2
        assert all(r.severity == INFO for r in checker.results)

    def test_nonpositive_target_price_logs_error(self) -> None:
        cur = _cursor([{"total": 100}], [[{"symbol": "BADTARGET", "val": 0.0}], []])
        checker = _checker()
        checker.check_analyst_sentiment_bounds(cur)
        assert checker.results[0].severity == ERROR

    def test_extreme_upside_logs_warn(self) -> None:
        cur = _cursor([{"total": 100}], [[], [{"symbol": "MOONSHOT", "val": 800.0}]])
        checker = _checker()
        checker.check_analyst_sentiment_bounds(cur)
        result = checker.results[-1]
        assert result.severity == WARN
        assert result.details["flagged_symbols"][0]["symbol"] == "MOONSHOT"


class TestErrorHandling:
    def test_query_failure_in_run_logs_error_not_raise(self) -> None:
        cur = MagicMock()

        def _execute_side_effect(sql: str, *args: object, **kwargs: object) -> None:
            if "SAVEPOINT" in sql:
                return None
            raise RuntimeError("db down")

        cur.execute.side_effect = _execute_side_effect
        checker = _checker()
        results = checker.run(cur)
        assert any(r.severity == ERROR for r in results)
        # every subcheck should have failed the same way, one ERROR result each
        assert len(results) == 6


class TestRunExecutesAllSubchecks:
    def test_run_covers_all_six_subchecks_without_crashing(self) -> None:
        cur = MagicMock()
        cur.fetchone.return_value = {"total": 100}
        cur.fetchall.return_value = []
        checker = _checker()
        results = checker.run(cur)
        assert isinstance(results, list)
        assert all(r.severity != ERROR for r in results)
