"""Regression test: overridden run() methods must actually instantiate SLAMonitor.

Follow-up to [[sla_monitor_table_name_key_mismatches_fixed_20260823]]: PriceLoader,
VectorizedTechnicalLoader, ValueQualityGrowthMetricsLoader, and
EnhancedQualityGrowthMetricsLoader all fully override OptimalLoader.run() (different batching/
threading/per-symbol logic each) and never called super().run(), so they never got the
SLAMonitor start/log_status/publish_metric calls the base class does. Fixed 2026-08-23 by
wiring SLAMonitor directly into each loader's own run(). Exercising run() end-to-end for all
four would require mocking DB/network for each loader's very different internals - this pins
the actual regression (the wiring silently disappearing in a future edit) via source inspection
instead, same spirit as test_sla_monitor_table_name_keys_match_real_loaders.py's static checks.
"""

import inspect

from loaders.load_enhanced_quality_growth_metrics import EnhancedQualityGrowthMetricsLoader
from loaders.load_prices import PriceLoader
from loaders.load_technical_indicators import VectorizedTechnicalLoader
from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader
from utils.loaders.sla_monitor import LOADER_SLA_TARGETS


def _call_site_count(src: str, helper_call: str = "_log_sla_status()") -> int:
    """Count call sites only, excluding the `def _log_sla_status() -> None:` definition line
    itself (which also contains the literal substring "_log_sla_status()")."""
    return sum(1 for line in src.splitlines() if helper_call in line and "def " not in line)


def test_price_loader_run_instantiates_sla_monitor() -> None:
    src = inspect.getsource(PriceLoader.run)
    assert "SLAMonitor(self.table_name)" in src
    assert "sla_monitor.start()" in src
    assert src.count("sla_monitor.log_status(") >= 1
    assert _call_site_count(src) == 2  # circuit-breaker-halt and final-success return paths


def test_vectorized_technical_loader_run_instantiates_sla_monitor() -> None:
    src = inspect.getsource(VectorizedTechnicalLoader.run)
    assert "SLAMonitor(self.table_name)" in src
    assert "sla_monitor.start()" in src
    assert _call_site_count(src) == 4  # skip, success, RuntimeError, generic Exception


def test_value_quality_growth_loader_run_instantiates_sla_monitor() -> None:
    src = inspect.getsource(ValueQualityGrowthMetricsLoader.run)
    assert "SLAMonitor(self.table_name)" in src
    assert "sla_monitor.start()" in src
    assert _call_site_count(src) == 2  # success and fatal-exception paths


def test_enhanced_quality_growth_loader_run_instantiates_sla_monitor() -> None:
    src = inspect.getsource(EnhancedQualityGrowthMetricsLoader.run)
    assert "SLAMonitor(self.table_name)" in src
    assert "sla_monitor.start()" in src
    assert _call_site_count(src) == 3  # success + both fatal-exception paths


def test_value_metrics_and_quality_metrics_have_real_sla_entries() -> None:
    # These loaders' self.table_name values had no LOADER_SLA_TARGETS entry at all before
    # this fix, so even a correctly-wired SLAMonitor would have silently used the generic
    # 60/180/300 min fallback.
    assert "value_metrics" in LOADER_SLA_TARGETS
    assert "quality_metrics" in LOADER_SLA_TARGETS
    # Sanity: expected < warning < critical for both, and value_metrics (DB-only, ~30-40s
    # observed) should have a far tighter budget than quality_metrics (per-symbol yfinance
    # calls, ~114 min observed).
    for name in ("value_metrics", "quality_metrics"):
        expected, warning, critical = LOADER_SLA_TARGETS[name]
        assert expected < warning < critical
    assert LOADER_SLA_TARGETS["value_metrics"][2] < LOADER_SLA_TARGETS["quality_metrics"][0]
