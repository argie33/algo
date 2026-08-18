"""Regression test: _insert_quality_metrics must not clobber the analyst-revision columns.

Found live 2026-08-18 during a "which factor inputs are missing the most" audit
(scripts/audit_unavailable_reasons.py): estimate_revision_direction, revision_activity_30d,
estimate_momentum_60d/90d, and revision_trend_score are computed exclusively by
load_enhanced_quality_growth_metrics.py from live yfinance eps_trend/eps_revisions data
(see tests/unit/test_load_enhanced_quality_growth_metrics_revision_fields.py) and written via
a partial `UPDATE quality_metrics SET ... WHERE symbol = %s` covering only the fields it
computed. But ValueQualityGrowthMetricsLoader (this file) never computes these 5 fields
itself, and its own _insert_quality_metrics INSERT ... ON CONFLICT (symbol) DO UPDATE
unconditionally included all 5 columns in both the column list and the SET clause, sourced
from row.get(...) which is always None here. Since quality_metrics is a single-row-per-symbol
snapshot table (ON CONFLICT (symbol), not (symbol, date)) and this loader runs far more often
than the enhanced one, every value_quality_growth run wiped these 5 columns back to NULL -
live-confirmed universe-wide coverage for estimate_momentum_60d collapsed to 0-43/5719 rows
within the hour after a same-day enhanced-loader run had just populated ~95%+ of the universe.

A stale comment already claimed this was "Fixed 2026-08-18 ... no longer includes them in its
column list" without the SQL actually being changed - this test pins the real fix so it can't
silently regress again.
"""

from unittest.mock import MagicMock

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader

CLOBBERED_FIELDS = [
    "estimate_revision_direction",
    "revision_activity_30d",
    "estimate_momentum_60d",
    "estimate_momentum_90d",
    "revision_trend_score",
]


def _loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _row(symbol="AAPL") -> dict:
    return {
        "symbol": symbol,
        "roe": 12.0,
        "operating_margin": 9.0,
        "net_margin": 7.5,
        "debt_to_equity": 0.4,
        "data_unavailable": False,
        "reason": None,
        "updated_at": "2026-08-18",
        # Deliberately absent: the 5 analyst-revision fields and their _unavailable_reason
        # siblings - matching what this loader's own metrics dict actually produces (it never
        # computes them), same as production.
    }


class TestInsertQualityMetricsDoesNotTouchAnalystRevisionColumns:
    def test_sql_column_list_excludes_analyst_revision_fields(self):
        loader = _loader()
        mock_cur = MagicMock()

        loader._insert_quality_metrics(mock_cur, _row())

        sql = mock_cur.execute.call_args[0][0]
        for field in CLOBBERED_FIELDS:
            assert f" {field}," not in sql and f" {field} " not in sql, (
                f"{field} must not appear in quality_metrics INSERT column list - "
                "only load_enhanced_quality_growth_metrics.py may write it"
            )
            assert f"{field} = EXCLUDED.{field}" not in sql, (
                f"{field} must not be in the ON CONFLICT SET clause - it clobbers real "
                "analyst-revision data back to NULL on every run"
            )
            assert f"{field}_unavailable_reason" not in sql, (
                f"{field}_unavailable_reason must not be touched either - it's reset "
                "alongside the value column by the same bug"
            )

    def test_placeholder_count_matches_column_count(self):
        """Guards against an off-by-one between the column list and the VALUES tuple -
        the kind of mismatch that's easy to introduce when hand-editing a 90-column INSERT."""
        loader = _loader()
        mock_cur = MagicMock()

        loader._insert_quality_metrics(mock_cur, _row())

        sql, params = mock_cur.execute.call_args[0]
        values_start = sql.index("VALUES (") + len("VALUES (")
        values_end = sql.index(")", values_start)
        placeholder_count = sql[values_start:values_end].count("%s")

        assert placeholder_count == len(params)
