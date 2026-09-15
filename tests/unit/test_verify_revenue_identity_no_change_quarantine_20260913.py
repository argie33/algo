"""Regression test for scripts/verify_and_fix_revenue_identity.py's
`revenue_identity_reload_no_change` CheckResult severity.

Originally (2026-09-13) this asserted severity="error" plus a deduplicated `flagged_symbols`
list, added so a CRIT/ERROR finding without flagged_symbols wouldn't halt the entire pipeline
under algo/monitoring/data_patrol/quarantine.py's contract (ERROR without flagged_symbols is
not quarantinable, so Phase 1 would halt everyone for this one check instead of quarantining
just the affected symbols).

**REVERSED 2026-09-14** (found live: an --apply run against the full flagged population
quarantined 378 symbols, including large real companies like ADM/AIG). The "no_change after a
live reload" population is the same 1.35x-tolerance set tie_out_identity_quarterly.py's own
check logs as a WARN-tier review queue precisely because most of it is genuine filer-side
restatement inconsistency (quarterly_revenue_extreme_dismissed.json already documents dozens
of exactly this shape), not a code bug - a reload correctly re-fetches the same real,
inconsistent data either way, so "unchanged" does not distinguish a real bug from a dismissable
non-bug. Auto-quarantining on this signal alone was the actual defect; the 2026-09-13 fix just
made that defect efficient instead of catastrophic. Now severity="warn" (doesn't quarantine or
halt anything - purely a review-queue log entry) and flagged_symbols is gone entirely, matching
tie_out_identity_quarterly.py's own treatment of this same population.
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
                return float(row["annual_revenue_before"])
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


class TestRevenueIdentityReloadNoChangeIsReviewQueueNotAutoQuarantine:
    def test_no_change_is_warn_severity_not_error(self) -> None:
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

        assert no_change_result.severity == "warn"
        assert no_change_result.details["count"] == 3
        # No flagged_symbols - a WARN finding here must not auto-quarantine anything, since
        # "unchanged by reload" cannot distinguish a real extraction bug from a genuine,
        # already-dismissable filer-side restatement inconsistency.
        assert "flagged_symbols" not in no_change_result.details

    def test_no_flagged_rows_yields_zero_count(self) -> None:
        results = _run_with_no_change_rows({})
        no_change_result = next(r for r in results if r.check_name == "revenue_identity_reload_no_change")
        assert no_change_result.details["count"] == 0
        assert "flagged_symbols" not in no_change_result.details
