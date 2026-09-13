"""Regression test for `_get_data_quality` (lambda/api/routes/algo_handlers/market/
data_quality.py).

BUG FOUND 2026-09-13 (goal session: comprehensive patrol/quarantine audit): this endpoint
used to partition data_patrol_log rows ONLY by target_table, keeping the single
most-recently-inserted row per table regardless of which check_name produced it. Many
distinct DataPatrol checks write findings against the same table (e.g. 9 different check
modules target annual_income_statement), so whichever check happened to insert last for a
table silently hid every other check's finding for that table - including a CRITICAL from
one check being masked by a later INFO/WARN from an unrelated check on the same table.

'lambda' is a Python keyword, so the module under test is loaded via importlib rather than a
normal `from lambda...` import.
"""

import importlib
from datetime import datetime
from unittest.mock import MagicMock

data_quality_module = importlib.import_module("lambda.api.routes.algo_handlers.market.data_quality")


def _mock_cursor(rows: list[dict]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = rows
    return cur


class TestDataQualityPerCheckRollup:
    def test_critical_from_one_check_not_masked_by_later_warn_on_same_table(self) -> None:
        """A later-inserted WARN from one check must not hide an earlier CRITICAL from a
        different check targeting the same table - the exact AXIL-shaped masking this fix
        closes."""
        cur = _mock_cursor(
            [
                {
                    "table_name": "annual_income_statement",
                    "check_name": "tie_out_identity_annual",
                    "severity": "critical",
                    "message": "gross_profit identity violated",
                    "data_detail": None,
                    "created_at": datetime(2026, 9, 13, 10, 0, 0),
                    "rn": 1,
                },
                {
                    "table_name": "annual_income_statement",
                    "check_name": "reverse_merger_shell_revenue_discontinuity",
                    "severity": "warn",
                    "message": "152 symbols show a rename-boundary revenue jump",
                    "data_detail": None,
                    "created_at": datetime(2026, 9, 13, 11, 0, 0),
                    "rn": 1,
                },
            ]
        )

        response = data_quality_module._get_data_quality(cur)

        table_statuses = response["data"]["items"]
        assert len(table_statuses) == 1
        assert table_statuses[0]["table"] == "annual_income_statement"
        # The critical finding must win the table-level rollup even though the warn finding
        # was inserted later (higher created_at) - this is exactly what the old
        # `ORDER BY created_at DESC` / rn==1-per-table logic got wrong.
        assert table_statuses[0]["severity"] == "critical"
        assert table_statuses[0]["status"] == "failed"

        # Both distinct (table, check) findings must count in the summary - not collapsed
        # into one, which would undercount how many checks are actually flagging something.
        assert response["data"]["summary"]["critical"] == 1
        assert response["data"]["summary"]["warnings"] == 1
        assert response["data"]["accuracy_check"] == "failed"

    def test_different_tables_each_get_their_own_worst_status(self) -> None:
        cur = _mock_cursor(
            [
                {
                    "table_name": "annual_income_statement",
                    "check_name": "statistical_anomaly",
                    "severity": "healthy",
                    "message": "no anomalies",
                    "data_detail": None,
                    "created_at": datetime(2026, 9, 13, 10, 0, 0),
                    "rn": 1,
                },
                {
                    "table_name": "price_daily",
                    "check_name": "staleness",
                    "severity": "error",
                    "message": "price_daily stale",
                    "data_detail": None,
                    "created_at": datetime(2026, 9, 13, 10, 0, 0),
                    "rn": 1,
                },
            ]
        )

        response = data_quality_module._get_data_quality(cur)

        by_table = {row["table"]: row for row in response["data"]["items"]}
        assert by_table["annual_income_statement"]["status"] == "passed"
        assert by_table["price_daily"]["status"] == "warning"
        assert response["data"]["summary"]["total_tables_checked"] == 2
