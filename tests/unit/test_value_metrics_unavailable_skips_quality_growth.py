"""Regression test: a data_unavailable value_row must not discard quality/growth writes.

Found live 2026-07-28: ValueQualityGrowthMetricsLoader.run() computes value_dict,
quality_dict, and growth_dict independently in fetch_incremental() (different source
queries - sec_valuations vs annual_balance_sheet/income_statement joins), but run() had
an early `continue` whenever value_row was data_unavailable, before ever reaching the
quality/growth inserts below it. This discarded already-computed quality_row/growth_row
data entirely - not even an unavailable marker was written - for any symbol whose value
metrics failed. Confirmed live: 44 symbols (odd-suffix tickers like WSO.B, TAP.A) had a
real value_metrics row (data_unavailable=True) with zero corresponding row in
quality_metrics/growth_metrics at all. This is the same bug class the adjacent
"always upsert the unavailable marker" governance fix already closed for the
quality/growth-specific unavailable case - just one level up, in the value-unavailable
branch that wrapped it.
"""

from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    loader._watermark = MagicMock()
    return loader


def _unavailable_value_row(symbol="WSO.B"):
    return {"symbol": symbol, "data_unavailable": True, "reason": "no_sec_valuations"}


def _real_quality_row(symbol="WSO.B"):
    return {
        "symbol": symbol,
        "roe": 12.0,
        "roa": 6.0,
        "operating_margin": 9.0,
        "net_margin": 7.5,
        "debt_to_equity": 0.4,
        "data_unavailable": False,
        "reason": None,
        "updated_at": "2026-07-28",
    }


def _real_growth_row(symbol="WSO.B"):
    return {
        "symbol": symbol,
        "revenue_growth_1y": 5.0,
        "data_unavailable": False,
        "reason": None,
        "updated_at": "2026-07-28",
    }


class TestValueUnavailableStillWritesQualityAndGrowth:
    def test_quality_and_growth_inserted_when_value_metrics_unavailable(self):
        loader = _make_loader()
        symbol = "WSO.B"
        value_row = _unavailable_value_row(symbol)
        quality_row = _real_quality_row(symbol)
        growth_row = _real_growth_row(symbol)

        with (
            patch.object(loader, "fetch_incremental", return_value=[(value_row, quality_row, growth_row)]),
            patch.object(loader, "_insert_value_metrics") as mock_insert_value,
            patch.object(loader, "_insert_quality_metrics") as mock_insert_quality,
            patch.object(loader, "_insert_growth_metrics") as mock_insert_growth,
            patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx,
            patch("utils.loaders.status_manager.DatabaseContext") as mock_status_db_ctx,
            patch("utils.loaders.config.get_default_parallelism", return_value=1),
        ):
            mock_cur = MagicMock()
            # Mock fetchone to return appropriate values based on query pattern
            def mock_fetchone_fn():
                last_sql = mock_cur.execute.call_args[0][0] if mock_cur.execute.called else ""
                if "symbol_count, symbols_loaded, completion_pct" in last_sql:
                    return (1, 1, 100.0)  # safety check for mark_completed
                elif "COUNT(*)" in last_sql:
                    return (1,)  # count query for mark_running
                return (1,)  # default single value

            # Use infinite generator so it never runs out of values
            mock_cur.fetchone.side_effect = lambda: mock_fetchone_fn()
            mock_cur.rowcount = 1
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            mock_status_db_ctx.return_value.__enter__.return_value = mock_cur

            result = loader.run([symbol])

        mock_insert_value.assert_called_once_with(mock_cur, value_row)
        mock_insert_quality.assert_called_once_with(mock_cur, quality_row)
        mock_insert_growth.assert_called_once_with(mock_cur, growth_row)
        assert result["quality_metrics"] == 1
        assert result["growth_metrics"] == 1
        assert result["symbols_failed"] == 1
        assert result["symbols_succeeded"] == 0
