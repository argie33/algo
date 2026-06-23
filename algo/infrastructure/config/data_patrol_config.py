#!/usr/bin/env python3
"""Data patrol configuration (staleness, coverage, quality thresholds).

Manages all data quality monitoring parameters independently from RiskConfig.
Data platform team can tune patrol thresholds without coordinating with risk team.

Categories:
- Staleness windows (patrol_staleness_* for each data type)
- Coverage thresholds (error/warn percentages)
- Data sanity checks (OHLC moves, volume ranges, null percentages)
- Cross-validation thresholds (price mismatches)
- Corporate action detection (splits/dividends)
- Loader contracts (expected row counts, severity levels)

Delegates all DB access to parent AlgoConfig._config dict.
Provides logical grouping methods for convenience.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig

logger = logging.getLogger(__name__)


class DataPatrolConfig:
    """Configuration for data quality monitoring and validation."""

    def __init__(self, parent: "AlgoConfig") -> None:
        """Initialize DataPatrolConfig with parent AlgoConfig.

        Args:
            parent: Parent AlgoConfig instance (holds _config dict and DB connection)
        """
        self.parent = parent

    def get(self, key: str, default: Any = None) -> Any:
        """Get data patrol configuration value.

        Delegates to parent AlgoConfig.get(), which handles:
        - Type validation via VALIDATION_SCHEMA
        - Fallback to defaults
        - Fail-closed values for critical thresholds

        Args:
            key: Configuration key (e.g., "patrol_staleness_price_daily")
            default: Default value if key missing

        Returns:
            Configuration value or default
        """
        return self.parent.get(key, default)

    def set(
        self,
        key: str,
        value: Any,
        value_type: str,
        description: str = "",
        changed_by: str = "system",
    ) -> bool:
        """Set data patrol configuration value (writes to DB).

        For critical thresholds (e.g., staleness windows):
        - If value invalid, applies fail-closed default instead
        - Returns False to signal rejection

        Args:
            key: Configuration key
            value: New value
            value_type: Type ('int', 'float', 'bool', 'string')
            description: Description (only used for new keys)
            changed_by: Actor making change (for audit trail)

        Returns:
            True if value was set as requested; False if rejected/fail-closed
        """
        return self.parent.set(key, value, value_type, description, changed_by)  # type: ignore[no-any-return]

    def get_staleness_windows(self) -> dict[str, int]:
        """Get data patrol staleness thresholds (days) for all data types.

        Returns:
            {
                "price_daily": 7,
                "technical_data_daily": 7,
                "buy_sell_daily": 7,
                "trend_data": 7,
                "signal_quality_scores": 7,
                "market_health": 7,
                "sector_ranking": 7,
                "industry_ranking": 7,
                "insider_transactions": 30,
                "analyst_upgrades": 30,
                "stock_scores": 7,
                "aaii_sentiment": 7,
                "growth_metrics": 30,
                "earnings_history": 120,
            }
        """
        return {
            "price_daily": self.get("patrol_staleness_price_daily", 7),
            "technical_data_daily": self.get("patrol_staleness_technical_daily", 7),
            "buy_sell_daily": self.get("patrol_staleness_buy_sell_daily", 7),
            "trend_data": self.get("patrol_staleness_trend_data", 7),
            "signal_quality_scores": self.get("patrol_staleness_signal_quality_scores", 7),
            "market_health": self.get("patrol_staleness_market_health", 7),
            "sector_ranking": self.get("patrol_staleness_sector_ranking", 7),
            "industry_ranking": self.get("patrol_staleness_industry_ranking", 7),
            "insider_transactions": self.get("patrol_staleness_insider_transactions", 30),
            "analyst_upgrades": self.get("patrol_staleness_analyst_upgrades", 30),
            "stock_scores": self.get("patrol_staleness_stock_scores", 7),
            "aaii_sentiment": self.get("patrol_staleness_aaii_sentiment", 7),
            "growth_metrics": self.get("patrol_staleness_growth_metrics", 30),
            "earnings_history": self.get("patrol_staleness_earnings_history", 120),
        }

    def get_coverage_thresholds(self) -> dict[str, int]:
        """Get data patrol coverage ratio thresholds.

        Returns:
            {
                "error_pct": 95,   # Alert error threshold
                "warn_pct": 90,    # Alert warning threshold
            }
        """
        return {
            "error_pct": self.get("patrol_coverage_error_threshold_pct", 95),
            "warn_pct": self.get("patrol_coverage_warning_threshold_pct", 90),
        }

    def get_price_sanity_config(self) -> dict[str, Any]:
        """Get data patrol OHLC/price sanity thresholds.

        Returns:
            {
                "max_daily_move_pct": 0.5,    # Max daily move %
                "max_daily_move_count": 10,   # Max count of >50% moves
            }
        """
        return {
            "max_daily_move_pct": self.get("patrol_max_daily_move_pct", 0.5),
            "max_daily_move_count": self.get("patrol_max_daily_move_count", 10),
        }

    def get_volume_config(self) -> dict[str, Any]:
        """Get data patrol volume sanity thresholds.

        Returns:
            {
                "low_threshold": 1000,
                "high_threshold": 100000000,
                "new_low_alert": 5,
            }
        """
        return {
            "low_threshold": self.get("patrol_low_volume_threshold", 1000),
            "high_threshold": self.get("patrol_high_volume_threshold", 100000000),
            "new_low_alert": self.get("patrol_new_low_volume_alert", 5),
        }

    def get_quality_config(self) -> dict[str, Any]:
        """Get data patrol quality thresholds.

        Returns:
            {
                "max_null_pct": 5,
                "zero_symbols_error": 10,
                "zero_symbols_warn": 5,
                "identical_ohlc_threshold": 50,
            }
        """
        return {
            "max_null_pct": self.get("patrol_max_null_pct_threshold", 5),
            "zero_symbols_error": self.get("patrol_new_zero_symbols_error", 10),
            "zero_symbols_warn": self.get("patrol_new_zero_symbols_warn", 5),
            "identical_ohlc_threshold": self.get("patrol_identical_ohlc_threshold", 50),
        }

    def get_cross_validation_config(self) -> dict[str, Any]:
        """Get data patrol cross-validation thresholds.

        Returns:
            {
                "price_mismatch_pct": 2,
                "top_n_symbols": 50,
            }
        """
        return {
            "price_mismatch_pct": self.get("patrol_price_xval_mismatch_pct", 2),
            "top_n_symbols": self.get("patrol_xval_top_n_symbols", 50),
        }

    def get_corporate_actions_config(self) -> dict[str, Any]:
        """Get data patrol corporate actions detection config.

        Returns:
            {
                "lookback_days": 90,
                "drop_ratio": -0.30,
            }
        """
        return {
            "lookback_days": self.get("patrol_corporate_action_lookback_days", 90),
            "drop_ratio": self.get("patrol_corporate_action_drop_ratio", -0.30),
        }

    def get_loader_contracts(self) -> dict[str, dict[str, Any]]:
        """Get data patrol loader contracts with expected output thresholds.

        Returns:
            {
                "price_daily": {
                    "condition": "date >= CURRENT_DATE - INTERVAL '14 days'",
                    "min_rows": 40000,
                    "severity": "error",
                    "description": "Daily price data should be ~5000 symbols x 14 days",
                },
                ... (other loader contracts)
            }
        """
        severity_warn, severity_error = "warn", "error"
        return {
            "price_daily": {
                "condition": "date >= CURRENT_DATE - INTERVAL '14 days'",
                "min_rows": self.get("patrol_price_daily_14d_min", 40000),
                "severity": severity_error,
                "description": "Daily price data should be ~5000 symbols x 14 days",
            },
            "technical_data_daily": {
                "condition": "date >= CURRENT_DATE - INTERVAL '14 days'",
                "min_rows": self.get("patrol_technical_daily_14d_min", 40000),
                "severity": severity_error,
                "description": "Technical indicators should match price coverage",
            },
            "buy_sell_daily": {
                "condition": "date >= CURRENT_DATE - INTERVAL '14 days'",
                "min_rows": self.get("patrol_buy_sell_daily_14d_min", 800),
                "severity": severity_error,
                "description": "Pine signals should produce 50+ per day minimum",
            },
            "trend_template_data": {
                "condition": "date >= CURRENT_DATE - INTERVAL '14 days'",
                "min_rows": self.get("patrol_trend_14d_min", 16000),
                "severity": severity_error,
                "description": "Trend template covers 4900+ symbols x 14 days",
            },
            "market_exposure_daily": {
                "condition": "date >= CURRENT_DATE - INTERVAL '2 days'",
                "min_rows": self.get("patrol_market_exposure_daily_2d_min", 2),
                "severity": severity_error,
                "description": "Market regime indicators updated after market close",
            },
            "market_breadth_daily": {
                "condition": "date >= CURRENT_DATE - INTERVAL '2 days'",
                "min_rows": self.get("patrol_market_breadth_2d_min", 100),
                "severity": severity_warn,
                "description": "Market breadth (% up, down, neutral) 1-4 records/day",
            },
        }

    def __repr__(self) -> str:
        return f"<DataPatrolConfig {len(self.get_staleness_windows())} staleness keys>"
