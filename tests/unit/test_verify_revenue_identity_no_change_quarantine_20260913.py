"""Regression test for the 2026-09-13 fix (goal session: "is bad data quarantine handled
right" audit): scripts/verify_and_fix_revenue_identity.py's `revenue_identity_reload_no_change`
CheckResult is severity="error" with no `flagged_symbols`, so under
algo/monitoring/data_patrol/quarantine.py's own contract (a CRIT/ERROR finding without a
non-empty flagged_symbols list is NOT quarantinable) Phase 1 would halt the ENTIRE pipeline
for this finding instead of quarantining just the symbols with a currently-reproducing
extraction bug - even though this check already knows exactly which symbols they are.

`run()` now includes a deduplicated `flagged_symbols` list (one entry per affected symbol,
covering every fiscal year that symbol failed on) on that CheckResult's details.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from scripts.verify_and_fix_revenue_identity import run


class _FakeConn:
    def cursor(self, cursor_factory: Any = None) -> MagicMock:
        return MagicMock()

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


def _run_with_no_change_rows(by_symbol: dict[str, list[dict[str, Any]]]) -> list[Any]:
    """Runs `run(apply=True)` with `_flagged_rows` stubbed to `by_symbol` and
    `_current_annual_revenue` stubbed to always return the same "before" value (forcing
    every row into the no_change bucket), then returns the CheckResult list passed to
    PatrolLogger.log_results."""
    captured: dict[str, list[Any]] = {}

    def fake_log_results(self: Any, cur: Any, results: list[Any]) -> None:
        captured["results"] = results

    def fake_current_annual_revenue(cur: Any, symbol: str, fiscal_year: int) -> float:
        for row in by_symbol[symbol]:
            if row["fiscal_year"] == fiscal_year:
                return row["annual_revenue_before"]
        raise AssertionError(f"no stub row for {symbol}/{fiscal_year}")

    with (
        patch("utils.db.connection.get_db_connection", return_value=_FakeConn()),
        patch("scripts.verify_and_fix_revenue_identity._flagged_rows", return_value=by_symbol),
        patch(
            "scripts.verify_and_fix_revenue_identity._current_annual_revenue", side_effect=fake_current_annual_revenue
        ),
        patch("scripts.verify_and_fix_revenue_identity._reload_batch", return_value=True),
        patch("algo.monitoring.data_patrol.logger.PatrolLogger.log_results", new=fake_log_results),
    ):
        run(limit=None, symbols_override=None, apply=True)

    return captured["results"]


class TestRevenueIdentityReloadNoChangeQuarantine:
    def test_flagged_symbols_present_and_deduplicated(self) -> None:
        by_symbol = {
            "AAA": [
                {"fiscal_year": 2024, "quarters_sum": 100.0, "annual_revenue_before": 50.0},
                {"fiscal_year": 2023, "quarters_sum": 90.0, "annual_revenue_before": 45.0},
            ],
            "BBB": [
                {"fiscal_year": 2024, "quarters_sum": 200.0, "annual_revenue_before": 80.0},
            ],
        }
        results = _run_with_no_change_rows(by_symbol)
        no_change_result = next(r for r in results if r.check_name == "revenue_identity_reload_no_change")

        assert no_change_result.severity == "error"
        assert no_change_result.details["count"] == 3
        flagged = no_change_result.details["flagged_symbols"]
        flagged_symbols = [f["symbol"] for f in flagged]
        assert flagged_symbols == ["AAA", "BBB"]  # deduplicated, one entry per symbol
        aaa_reason = next(f["reason"] for f in flagged if f["symbol"] == "AAA")
        assert "2023" in aaa_reason and "2024" in aaa_reason

    def test_no_flagged_rows_yields_empty_flagged_symbols(self) -> None:
        results = _run_with_no_change_rows({})
        no_change_result = next(r for r in results if r.check_name == "revenue_identity_reload_no_change")
        assert no_change_result.details["flagged_symbols"] == []
