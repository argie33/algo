"""Regression test: _validate_dependency_freshness must warn, not halt, on stale
enrichment-only dependencies (value_metrics, sec_segment_metrics, positioning_metrics,
stock_scores).

Bug (found 2026-08-18, live evidence): this function returned a full HALT (status=
"halted", halted=True) whenever any of these dependencies was one trading day behind -
but algo/orchestrator/phase1_data_freshness.py's own header docstring is explicit:
"Metric loaders (growth, quality, value, positioning, stability) are ENRICHMENT ONLY...
Stale metrics = WARNING only, trading continues." None of price_daily/technical_data_daily/
buy_sell_daily (the genuinely halt-worthy tables per that same docstring) are even checked
here. Live-confirmed: a real morning run halted entirely on value_metrics->sec_valuations
being one trading day behind - structurally near-unavoidable pre-close, since sec_valuations
values the latest CLOSED price and today's close doesn't exist yet during morning/intraday
hours - directly contradicting the file's own documented "trading continues" policy.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

from algo.orchestrator.phase1_data_freshness import _validate_dependency_freshness


class TestDependencyFreshnessWarnsNotHalts:
    def test_stale_enrichment_dependency_does_not_halt(self) -> None:
        run_date = date(2026, 8, 18)
        yesterday = run_date - timedelta(days=1)

        cur = MagicMock()

        def execute_side_effect(sql, *args, **kwargs):
            cur._last_sql = sql

        def fetchone_side_effect():
            sql = cur._last_sql
            if "MAX(" in sql:
                # Every dependency's data is one trading day behind - the exact scenario
                # that used to halt the whole phase sequence.
                return (yesterday,)
            if "data_loader_status" in sql:
                # No FAILED/TIMEOUT status - just genuinely one day behind.
                return ("COMPLETED",)
            return None

        cur.execute.side_effect = execute_side_effect
        cur.fetchone.side_effect = fetchone_side_effect

        log_calls = []
        result = _validate_dependency_freshness(cur, run_date, lambda *a, **kw: log_calls.append((a, kw)))

        assert result is None, (
            "stale enrichment-only dependencies must not halt Phase 1 - "
            "this module's own docstring says 'Stale metrics = WARNING only, trading continues'"
        )
        # A warning must still be logged so operators have visibility - just non-blocking.
        assert log_calls, "a warning should still be logged for visibility, even though it doesn't halt"
        logged_status = log_calls[0][0][2] if len(log_calls[0][0]) > 2 else None
        assert logged_status != "halt", "logged status must not be 'halt' - this is a warning, not a halt"

    def test_fresh_dependencies_pass_silently(self) -> None:
        run_date = date(2026, 8, 18)

        cur = MagicMock()

        def execute_side_effect(sql, *args, **kwargs):
            cur._last_sql = sql

        def fetchone_side_effect():
            sql = cur._last_sql
            if "MAX(" in sql:
                return (run_date,)
            if "data_loader_status" in sql:
                return ("COMPLETED",)
            return None

        cur.execute.side_effect = execute_side_effect
        cur.fetchone.side_effect = fetchone_side_effect

        result = _validate_dependency_freshness(cur, run_date, lambda *a, **kw: None)
        assert result is None
