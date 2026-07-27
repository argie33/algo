#!/usr/bin/env python3
"""Regression test for a real data-provenance gap: migration 1022 added
stability_metrics.data_source with a documented intended value ("computed_from_price_daily" -
see the migration's own COMMENT ON COLUMN) and built an index on it, but
RiskMetricsLoader._persist_stability_metrics() never included the column in its INSERT/
UPDATE at all - confirmed live via direct DB query: all 5,481 existing rows have
data_source=NULL, unlike every sibling factor table (quality_metrics/growth_metrics/
value_metrics/positioning_metrics all correctly tag 'sec_audited'/'finra'/'sec_13f'/'none').
A documented provenance column that silently never gets written is exactly the kind of
messy, misleading data-quality gap this data source doesn't need more of.
"""

from datetime import date, timezone
from unittest.mock import MagicMock, patch

from loaders.load_risk_metrics_daily import RiskMetricsLoader


class TestStabilityMetricsDataSourceIsWritten:
    def test_persist_writes_computed_from_price_daily_data_source(self):
        row = {
            "symbol": "AAPL",
            "volatility_30d": 0.25,
            "volatility_60d": 0.22,
            "volatility_252d": 0.20,
            "beta": 1.1,
            "debt_to_assets": 0.3,
            "created_at": date(2026, 7, 27).isoformat(),
            "data_unavailable": False,
            "reason": None,
            "reason_type": None,
            "beta_unavailable_reason": None,
            "volatility_30d_unavailable_reason": None,
            "volatility_60d_unavailable_reason": None,
            "volatility_252d_unavailable_reason": None,
        }

        mock_cur = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur
        mock_ctx.__exit__.return_value = False

        loader = RiskMetricsLoader()
        with patch("loaders.load_risk_metrics_daily.DatabaseContext", return_value=mock_ctx):
            loader._persist_stability_metrics(row)

        sql, params = mock_cur.execute.call_args[0]
        assert "data_source" in sql
        assert "computed_from_price_daily" in params, (
            "stability_metrics.data_source must be written as 'computed_from_price_daily' "
            "per migration 1022's own documented column semantics"
        )
