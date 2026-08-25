"""Regression test for the 2026-08-25 fix (goal session, monitoring-vs-enforcement
consistency audit): PositionMonitor.check_sector_concentration() used a hardcoded `> 3`
positions threshold, completely independent of and inconsistent with the actual ENFORCED
limit - pretrade_checks.py's max_positions_per_sector (config-driven, live value well above
3). This monitor's own "HIGH_CONCENTRATION" advisory alert could fire on a portfolio state
pretrade_checks.py considers entirely within limits, or vice versa if the configured limit
were ever lowered below 3.

check_sector_concentration() now reads the same max_positions_per_sector config key
pretrade_checks.py enforces, via a parameterized `HAVING COUNT(...) > %s` instead of a
hardcoded literal.
"""

from algo.monitoring.position_monitor import PositionMonitor


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.last_query = None
        self.last_params = None

    def execute(self, query, params=None):
        self.last_query = query
        self.last_params = params

    def fetchall(self):
        return self._rows


class TestSectorConcentrationUsesConfiguredThreshold:
    def test_threshold_param_matches_configured_max_positions_per_sector(self):
        monitor = PositionMonitor(config={"max_positions_per_sector": 10})
        cur = _FakeCursor(rows=[])
        monitor.check_sector_concentration(cur=cur)
        assert cur.last_params == (10,), (
            f"expected the HAVING clause to be parameterized with the configured "
            f"max_positions_per_sector (10), got {cur.last_params!r}"
        )
        assert "%s" in cur.last_query
        assert "> 3" not in cur.last_query, "hardcoded '> 3' threshold must not remain in the query"

    def test_below_configured_threshold_reports_ok(self):
        monitor = PositionMonitor(config={"max_positions_per_sector": 10})
        # 5 positions in one sector - below the configured limit of 10, must NOT alert
        # (pre-fix, this would have incorrectly alerted since 5 > the old hardcoded 3).
        cur = _FakeCursor(rows=[])  # HAVING > 10 correctly filters this out server-side
        result = monitor.check_sector_concentration(cur=cur)
        assert result["status"] == "OK"
        assert result["sectors"] == []

    def test_above_configured_threshold_reports_high_concentration(self):
        monitor = PositionMonitor(config={"max_positions_per_sector": 3})
        cur = _FakeCursor(rows=[("Technology", 5)])
        result = monitor.check_sector_concentration(cur=cur)
        assert result["status"] == "HIGH_CONCENTRATION"
        assert result["sectors"] == [("Technology", 5)]

    def test_missing_config_raises(self):
        monitor = PositionMonitor(config={})
        cur = _FakeCursor(rows=[])
        try:
            monitor.check_sector_concentration(cur=cur)
            raise AssertionError("expected RuntimeError for missing max_positions_per_sector config")
        except RuntimeError as e:
            assert "max_positions_per_sector" in str(e)
