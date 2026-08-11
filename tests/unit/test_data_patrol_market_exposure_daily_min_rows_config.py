"""Regression test for the 2026-08-11 fix: `patrol_market_exposure_daily_min`'s only real
consumer (DataPatrolConfig.get_loader_contracts()) uses it as a `min_rows` threshold against
market_exposure_daily, a table with exactly 1 row/day by design over a ~2-day lookback window.
The key's DEFAULTS/schema entries described an unrelated "market exposure minimum daily %"
concept (float, 0-100, default 10.0) that was never actually wired to anything - meanwhile the
live DB had the key set to 80 (a plausible value under the stale % description), so the loader
contract demanded 80+ rows from a table that can never have more than ~2, an unconditional
permanent ERROR every day. The DEFAULTS entry must describe and default to the row-count
semantics that are actually used.
"""

from algo.infrastructure.config import main as config_main
from algo.infrastructure.config_schema import VALIDATION_SCHEMA


class TestMarketExposureDailyMinRowsConfig:
    def test_defaults_value_is_a_small_row_count_not_a_percent(self):
        default_value, value_type, _description, _category = config_main.AlgoConfig.DEFAULTS[
            "patrol_market_exposure_daily_min"
        ]
        assert value_type == "int", (
            "market_exposure_daily is a 1-row/day table checked over a ~2-day window - the "
            "contract's min_rows must be a small int, not the old float-percent semantics"
        )
        assert int(default_value) <= 10, (
            f"default {default_value} is far too high for a table with ~1 row/day over a "
            "~2-day lookback window - this was the exact bug (DB had it at 80)"
        )

    def test_validation_schema_range_matches_row_count_semantics(self):
        value_type, min_val, max_val, _is_critical, _fail_closed = VALIDATION_SCHEMA["patrol_market_exposure_daily_min"]
        assert value_type == "int"
        assert max_val <= 10, "range must reflect a small row-count contract, not a 0-100 percent"
