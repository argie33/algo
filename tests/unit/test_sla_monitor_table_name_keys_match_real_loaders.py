"""Regression test: LOADER_SLA_TARGETS keys must match a real loader's self.table_name.

SLAMonitor is instantiated as `SLAMonitor(self.table_name)` (utils/optimal_loader.py) and looks
up `LOADER_SLA_TARGETS.get(loader_name, <generic 60/180/300 min default>)`. Two keys were wrong
and had been silently falling through to that generic, far more lenient default:

- "stock_prices_daily" - no loader's table_name has ever been this; the real price loader
  (loaders/load_prices.py::PriceLoader) sets self.table_name = "price_daily".
- "sector_ranking" - a real table, but one of load_sector_industry_daily.py's 3 output_tables,
  not its primary self.table_name ("sector_performance"), which SLAMonitor actually keys on.

See [[sla_monitor_table_name_key_mismatches_fixed_20260823]] in memory: fixing the key alone
does not restore live telemetry for either loader, since both fully override run() and never
call super().run() (which is where SLAMonitor is instantiated) - a separate, larger,
deliberately-deferred gap. This test only pins that the config dict itself is internally
correct, so a future refactor that stops overriding run() gets the right threshold immediately
instead of reintroducing this exact silent mismatch.
"""

from loaders.load_prices import PriceLoader
from loaders.load_sector_industry_daily import SectorIndustryDailyLoader
from utils.loaders.sla_monitor import LOADER_SLA_TARGETS


def test_price_loader_table_name_has_its_own_sla_entry() -> None:
    loader = PriceLoader.__new__(PriceLoader)
    loader.table_name = "price_daily"
    assert loader.table_name in LOADER_SLA_TARGETS
    assert "stock_prices_daily" not in LOADER_SLA_TARGETS


def test_sector_industry_daily_loader_table_name_has_its_own_sla_entry() -> None:
    loader = SectorIndustryDailyLoader.__new__(SectorIndustryDailyLoader)
    loader.table_name = "sector_performance"
    assert loader.table_name in LOADER_SLA_TARGETS
