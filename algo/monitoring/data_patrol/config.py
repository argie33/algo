#!/usr/bin/env python3
"""Patrol configuration management - loads thresholds from algo_config table."""

import logging
from typing import Any, Dict, Optional, Union, cast


logger = logging.getLogger(__name__)

# Severity levels
INFO, WARN, ERROR, CRIT = "info", "warn", "error", "critical"


class PatrolConfig:
    """Load and cache patrol configuration from algo_config table."""

    def __init__(self, cur=None):
        self._config_cache: Dict[str, Any] = {}
        self._loaded = False
        if cur:
            self.load(cur)

    def load(self, cur) -> None:
        """Load configuration from algo_config table."""
        try:
            cur.execute("SELECT key, value FROM algo_config")
            rows = cur.fetchall()
            for row in rows:
                key, value = row[0], row[1]
                if value is None:
                    continue
                # Try to parse as number
                try:
                    if "." in str(value):
                        self._config_cache[key] = float(value)
                    else:
                        self._config_cache[key] = int(value)
                except (ValueError, TypeError):
                    self._config_cache[key] = value
            self._loaded = True
        except Exception as e:
            logger.warning(f"Could not load patrol config: {e}")
            self._loaded = False

    def get(self, key: str, default: Optional[Union[int, float, str]] = None) -> Optional[Union[int, float, str]]:
        """Get config value with fallback to default."""
        if key in self._config_cache:
            return cast(Union[int, float, str], self._config_cache[key])
        return default

    def get_staleness_windows(self) -> Dict[str, Any]:
        """Get all staleness thresholds in days."""
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

    def get_coverage_thresholds(self) -> Dict[str, Any]:
        """Get coverage ratio thresholds."""
        return {
            "error_pct": self.get("patrol_coverage_error_threshold_pct", 95),
            "warn_pct": self.get("patrol_coverage_warning_threshold_pct", 90),
        }

    def get_price_sanity_config(self) -> Dict[str, Any]:
        """Get OHLC/price sanity thresholds."""
        return {
            "max_daily_move_pct": self.get("patrol_max_daily_move_pct", 0.5),
            "max_daily_move_count": self.get("patrol_max_daily_move_count", 10),
        }

    def get_volume_config(self) -> Dict[str, Any]:
        """Get volume sanity thresholds."""
        return {
            "low_threshold": self.get("patrol_low_volume_threshold", 1000),
            "high_threshold": self.get("patrol_high_volume_threshold", 100000000),
            "new_low_alert": self.get("patrol_new_low_volume_alert", 5),
        }

    def get_quality_config(self) -> Dict[str, Any]:
        """Get data quality thresholds."""
        return {
            "max_null_pct": self.get("patrol_max_null_pct_threshold", 5),
            "zero_symbols_error": self.get("patrol_new_zero_symbols_error", 10),
            "zero_symbols_warn": self.get("patrol_new_zero_symbols_warn", 5),
            "identical_ohlc_threshold": self.get("patrol_identical_ohlc_threshold", 50),
        }

    def get_cross_validation_config(self) -> Dict[str, Any]:
        """Get cross-validation thresholds."""
        return {
            "price_mismatch_pct": self.get("patrol_price_xval_mismatch_pct", 2),
            "top_n_symbols": self.get("patrol_xval_top_n_symbols", 50),
        }

    def get_corporate_actions_config(self) -> Dict[str, Any]:
        """Get corporate actions detection config."""
        return {
            "lookback_days": self.get("patrol_corporate_action_lookback_days", 90),
            "drop_ratio": self.get("patrol_corporate_action_drop_ratio", -0.30),
        }

    def get_loader_contracts(self) -> Dict[str, Dict[str, Any]]:
        """Get loader contracts with expected output thresholds."""
        return {
            "price_daily": {
                "condition": "date >= CURRENT_DATE - INTERVAL '14 days'",
                "min_rows": self.get("patrol_price_daily_14d_min", 40000),
                "severity": ERROR,
                "description": "Daily price data should be ~5000 symbols × 14 days",
            },
            "technical_data_daily": {
                "condition": "date >= CURRENT_DATE - INTERVAL '14 days'",
                "min_rows": self.get("patrol_technical_daily_14d_min", 40000),
                "severity": ERROR,
                "description": "Technical indicators should match price coverage",
            },
            "buy_sell_daily": {
                "condition": "date >= CURRENT_DATE - INTERVAL '14 days'",
                "min_rows": self.get("patrol_buy_sell_daily_14d_min", 800),
                "severity": ERROR,
                "description": "Pine signals should produce 50+ per day minimum",
            },
            "trend_template_data": {
                "condition": "date >= CURRENT_DATE - INTERVAL '14 days'",
                "min_rows": self.get("patrol_trend_14d_min", 16000),
                "severity": ERROR,
                "description": "Trend template covers 4900+ symbols × 14 days",
            },
            "signal_quality_scores": {
                "condition": "date >= CURRENT_DATE - INTERVAL '14 days'",
                "min_rows": self.get("patrol_sqs_14d_min", 16000),
                "severity": WARN,
                "description": "SQS should match trend coverage",
            },
        }

    def as_dict(self) -> Dict[str, Any]:
        """Return all config as a dict (for logging)."""
        return {
            "staleness_windows": self.get_staleness_windows(),
            "coverage_thresholds": self.get_coverage_thresholds(),
            "price_sanity": self.get_price_sanity_config(),
            "volume_sanity": self.get_volume_config(),
            "quality": self.get_quality_config(),
            "cross_validation": self.get_cross_validation_config(),
            "corporate_actions": self.get_corporate_actions_config(),
        }
