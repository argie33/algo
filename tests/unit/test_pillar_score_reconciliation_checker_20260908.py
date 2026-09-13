"""Regression tests for PillarScoreReconciliationChecker
(algo/monitoring/data_patrol/checks/pillar_score_reconciliation.py).

Added 2026-09-08 (goal: score sanity audit follow-up to composite_score_reconciliation.py).
Covers: exact match, a real divergence (flagged WARN), a divergence beyond the rounding budget
(flagged ERROR), and exception handling.

EXTENDED 2026-09-13 (goal: "ways to catch when the data/calcs are wrong" session) - the check
now splits flagged rows into confirmed-fresh (quality_metrics.updated_at <= stock_scores' last
reload watermark - a real bug) vs unverified/pending-reload (source updated AFTER the last
reload - benign lag), reusing a data_loader_status.last_success_at watermark read via a second
cur.fetchone() call. _mock_cursor now also stubs fetchone for that watermark query; _row() takes
an explicit updated_at so each test controls which side of the watermark its row falls on.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.pillar_score_reconciliation import (
    PillarScoreReconciliationChecker,
)
from algo.monitoring.data_patrol.config import ERROR, INFO, WARN, PatrolConfig

_WATERMARK = datetime(2026, 9, 8, 12, 0, 0)
_BEFORE_WATERMARK = _WATERMARK - timedelta(hours=1)  # source updated before last reload -> "fresh" (real bug)
_AFTER_WATERMARK = _WATERMARK + timedelta(hours=1)  # source updated after last reload -> pending-reload (benign)


def _checker() -> PillarScoreReconciliationChecker:
    return PillarScoreReconciliationChecker(PatrolConfig())


def _mock_cursor(rows: list[dict], watermark: datetime | None = _WATERMARK) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = rows
    cur.fetchone.return_value = {"last_success_at": watermark} if watermark is not None else None
    return cur


def _row(
    symbol: str,
    stock_scores_quality_score: float,
    quality_metrics_quality_score: float,
    updated_at: datetime = _BEFORE_WATERMARK,
) -> dict:
    return {
        "symbol": symbol,
        "date": "2026-09-08",
        "stock_scores_quality_score": stock_scores_quality_score,
        "quality_metrics_quality_score": quality_metrics_quality_score,
        "updated_at": updated_at,
    }


class TestPillarScoreReconciliation:
    def test_matching_scores_not_flagged(self) -> None:
        # FIXED 2026-09-10: a clean pass still logs one INFO result (not []) so a prior WARN/
        # ERROR finding for this check can be superseded/resolved on the next patrol run - see
        # pillar_score_reconciliation.py's module-level comment for the full rationale.
        cur = _mock_cursor([_row("MATCH", 72.5, 72.5)])
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == INFO

    def test_rounding_noise_not_flagged(self) -> None:
        cur = _mock_cursor([_row("ROUND", 72.50, 72.505)])
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == INFO

    def test_stale_stock_scores_flagged_warn(self) -> None:
        # stock_scores.quality_score is 0.5 points behind a since-updated quality_metrics.
        cur = _mock_cursor([_row("STALE", 70.0, 70.5)])
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == WARN
        assert results[0].details["examples"][0]["symbol"] == "STALE"

    def test_large_divergence_flagged_error(self) -> None:
        # 30 points off, and the source (quality_metrics) was updated BEFORE stock_scores' last
        # reload - stock_scores had the chance to pick this up and didn't. A real, unreloaded
        # rewrite (e.g. broker-dealer fcf_margin exclusion landing in quality_metrics without
        # stock_scores being reloaded from it), not benign pending-reload lag.
        cur = _mock_cursor([_row("GS", 30.0, 60.0)])
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == ERROR
        assert results[0].details["confirmed_fresh"] == 1
        assert results[0].details["unverified_stale"] == 0
        # ADDED (quarantine wiring fix): confirmed-fresh + over-error-bar must be quarantinable.
        flagged_symbols = results[0].details["flagged_symbols"]
        assert [f["symbol"] for f in flagged_symbols] == ["GS"]
        assert "reason" in flagged_symbols[0]

    def test_large_divergence_pending_reload_not_escalated_to_error(self) -> None:
        # Same 30-point divergence as test_large_divergence_flagged_error, but the source
        # (quality_metrics) was updated AFTER stock_scores' last successful reload watermark -
        # stock_scores hasn't had the chance to pick it up yet. Live-caught 2026-09-13: this
        # exact shape (4522 symbols) was firing ERROR before this fix.
        cur = _mock_cursor([_row("GS", 30.0, 60.0, updated_at=_AFTER_WATERMARK)])
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == WARN
        assert results[0].details["confirmed_fresh"] == 0
        assert results[0].details["unverified_stale"] == 1
        # A pending-reload-lag symbol must never be quarantined - it isn't a confirmed bug.
        assert results[0].details["flagged_symbols"] == []

    def test_mixed_fresh_and_stale_only_quarantines_the_fresh_one(self) -> None:
        # GS is a confirmed-fresh, over-error-bar divergence; MS has the identical divergence
        # but is only pending-reload (unverified) - only GS may end up in flagged_symbols even
        # though the aggregate finding severity (driven by GS) is ERROR for both.
        cur = _mock_cursor(
            [
                _row("GS", 30.0, 60.0, updated_at=_BEFORE_WATERMARK),
                _row("MS", 30.0, 60.0, updated_at=_AFTER_WATERMARK),
            ]
        )
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == ERROR
        flagged_symbols = results[0].details["flagged_symbols"]
        assert [f["symbol"] for f in flagged_symbols] == ["GS"]

    def test_no_watermark_treated_as_unverified(self) -> None:
        # No data_loader_status row for stock_scores at all - can't distinguish pending-reload
        # from a real bug, so stays WARN (conservative), not silently ERROR.
        cur = _mock_cursor([_row("GS", 30.0, 60.0)], watermark=None)
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == WARN
        assert results[0].details["confirmed_fresh"] == 0
        assert results[0].details["unverified_stale"] == 1

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.fetchall.side_effect = RuntimeError("schema drift")
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == ERROR
        assert "schema drift" in results[0].message
