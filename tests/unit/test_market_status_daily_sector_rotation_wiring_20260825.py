"""Regression test for the 2026-08-25 fix wiring SectorRotationDetector into the scheduled
pipeline (see [[sector_rotation_signal_orphaned_never_scheduled_fixed_20260825]] in memory).

algo/signals/sector_rotation.py's SectorRotationDetector was only ever invoked manually via
`if __name__ == "__main__"` with a hardcoded date - never by any scheduled loader. Its output
table, sector_rotation_signal, fed a real Phase 8 pre-entry health check
(_check_sector_weak() in phase8_preentry_health_check.py) that queries it for TODAY's date on
every entry candidate. With nothing writing fresh rows, that query always found no row for
today and silently, permanently returned "not weak" - one of Phase 8's 4 pre-entry health
checks was dead weight with no visibility that it had gone dark.

Fixed by calling SectorRotationDetector().compute(eval_date) from
MarketStatusDailyLoader._compute_market_exposure(), the same place/pattern already used for
CapitalRouting().compute() - a non-fatal satellite computation that must not fail the primary
exposure computation everything else depends on.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_market_status_daily import MarketStatusDailyLoader


def _make_loader():
    loader = MarketStatusDailyLoader()
    loader._persist_market_exposure = MagicMock()  # avoid a real DB write
    return loader


class TestSectorRotationWiredIntoMarketStatusRun:
    def test_sector_rotation_computed_for_eval_date(self):
        loader = _make_loader()
        mock_result = {"regime": "confirmed_uptrend", "exposure_pct": 70.0, "raw_score": 70.0}
        with (
            patch("algo.risk.market_exposure.MarketExposure") as mock_exposure_cls,
            patch("algo.risk.capital_routing.CapitalRouting"),
            patch("algo.signals.sector_rotation.SectorRotationDetector") as mock_rotation_cls,
        ):
            mock_exposure_cls.return_value.compute.return_value = mock_result
            loader._compute_market_exposure(date(2026, 8, 25), {})
            mock_rotation_cls.return_value.compute.assert_called_once_with(date(2026, 8, 25))

    def test_sector_rotation_failure_does_not_fail_exposure_computation(self):
        """A broken/unavailable sector_ranking history (e.g. dataset too young, transient DB
        error) must not take down the primary exposure computation - same non-fatal contract
        as the CapitalRouting call it's modeled on."""
        loader = _make_loader()
        mock_result = {"regime": "confirmed_uptrend", "exposure_pct": 70.0, "raw_score": 70.0}
        with (
            patch("algo.risk.market_exposure.MarketExposure") as mock_exposure_cls,
            patch("algo.risk.capital_routing.CapitalRouting"),
            patch("algo.signals.sector_rotation.SectorRotationDetector") as mock_rotation_cls,
        ):
            mock_exposure_cls.return_value.compute.return_value = mock_result
            mock_rotation_cls.return_value.compute.side_effect = RuntimeError("sector_ranking unavailable")
            result = loader._compute_market_exposure(date(2026, 8, 25), {})
            assert result["exposure_pct"] == 70.0
            assert not result.get("data_unavailable")

    def test_sector_rotation_signal_declared_as_output_table(self):
        assert "sector_rotation_signal" in MarketStatusDailyLoader.output_tables

    def test_output_tables_matches_registry(self):
        from loaders.loader_registry import all_tables

        registry_tables = set(all_tables("load_market_status_daily.py"))
        declared = {MarketStatusDailyLoader.table_name, *MarketStatusDailyLoader.output_tables}
        assert declared == registry_tables
