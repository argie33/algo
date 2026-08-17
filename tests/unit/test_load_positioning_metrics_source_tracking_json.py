"""Regression test for a 2026-08-17 "source_tracking always dropped" bug in
load_positioning_metrics.py (loader-review goal, SEC-vs-yfinance audit continuation).

fetch_incremental() has always built a `source_tracking` dict (per-field provenance -
which of short_interest/institutional/insider came from FINRA/SEC 13F/SEC Form 4, vs
"unavailable") on every row, but positioning_metrics never had a matching DB column, so
utils/bulk_insert_manager.py's schema-introspection filter silently dropped it from every
single write (logged as a routine WARNING, once per symbol - real log spam, zero rows ever
persisted). Migration 1207 adds the column, but a raw dict written via bulk_insert_manager's
csv.DictWriter path serializes with Python's repr() (single-quoted keys), which is not valid
JSON and would fail to insert into a JSONB column - so the loader itself must json.dumps()
the dict first, same pattern already used for `components`/`data_sources` in
load_stock_scores.py.
"""

import json
from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_positioning_metrics import PositioningMetricsLoader


def _make_loader() -> PositioningMetricsLoader:
    return PositioningMetricsLoader.__new__(PositioningMetricsLoader)


class _EmptyCursor:
    """Every query returns no rows - drives short_interest/institutional/insider all to
    "unavailable", the simplest deterministic path through fetch_incremental()."""

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        pass

    def fetchall(self) -> list[tuple[Any, ...]]:
        return []

    def fetchone(self) -> tuple[Any, ...] | None:
        return None


def _fake_db_context() -> MagicMock:
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=_EmptyCursor())
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


class TestSourceTrackingIsJsonSerialized:
    def test_source_tracking_is_a_json_string_not_a_raw_dict(self) -> None:
        loader = _make_loader()
        with (
            patch("loaders.load_positioning_metrics.DatabaseContext", return_value=_fake_db_context()),
            patch.object(loader, "_compute_ad_rating", return_value=(None, "insufficient_price_history")),
        ):
            rows = loader.fetch_incremental("ZZZZ", date(2026, 1, 1))

        assert len(rows) == 1
        source_tracking = rows[0]["source_tracking"]
        assert isinstance(source_tracking, str), (
            "source_tracking must be json.dumps()-serialized before reaching bulk_insert_manager - "
            "a raw dict serializes via csv writer's repr()/str() (single-quoted keys), which is not "
            "valid JSON and would fail to insert into the JSONB column added in migration 1207"
        )
        assert json.loads(source_tracking) == {
            "short_interest": "unavailable",
            "institutional": "unavailable",
            "insider": "unavailable",
        }
