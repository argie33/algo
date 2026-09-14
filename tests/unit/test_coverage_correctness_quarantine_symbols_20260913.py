"""Tests for coverage_correctness.py's _fetch_open_quarantine_symbols (goal session 2026-09-13:
follow-up to "is a count enough, or do we need to track anything else" - the correctness-
coverage panel previously only exposed an aggregate open_quarantine_count per table, with no way
to see which symbols are quarantined or why/how-long without leaving the panel).
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from routes.scores_handlers.coverage_correctness import (
    _MAX_QUARANTINE_EXAMPLES_PER_TABLE,
    _fetch_open_quarantine_symbols,
)


class TestFetchOpenQuarantineSymbols:
    def test_groups_rows_by_table_with_reason_and_age(self):
        cur = MagicMock()
        detected = datetime(2026, 9, 1, tzinfo=timezone.utc)
        cur.fetchall.return_value = [
            ("quality_metrics", "AAA", "negative OHLC price", "critical", detected, 12.0, 1),
            ("quality_metrics", "BBB", "bad high/low", "error", detected, 12.0, 2),
        ]

        result = _fetch_open_quarantine_symbols(cur, ["quality_metrics"])

        assert result == {
            "quality_metrics": [
                {
                    "symbol": "AAA",
                    "reason": "negative OHLC price",
                    "severity": "critical",
                    "detected_at": detected.isoformat(),
                    "days_open": 12.0,
                },
                {
                    "symbol": "BBB",
                    "reason": "bad high/low",
                    "severity": "error",
                    "detected_at": detected.isoformat(),
                    "days_open": 12.0,
                },
            ]
        }

    def test_no_open_quarantine_rows_yields_empty_dict(self):
        cur = MagicMock()
        cur.fetchall.return_value = []

        assert _fetch_open_quarantine_symbols(cur, ["quality_metrics"]) == {}

    def test_query_caps_rows_per_table_via_window_function(self):
        cur = MagicMock()
        cur.fetchall.return_value = []

        _fetch_open_quarantine_symbols(cur, ["quality_metrics"])

        sql = cur.execute.call_args.args[0]
        assert f"rn <= {_MAX_QUARANTINE_EXAMPLES_PER_TABLE}" in sql
        assert "resolved_at IS NULL" in sql
        assert "HAVING COUNT(DISTINCT target_table) = 1" in sql
