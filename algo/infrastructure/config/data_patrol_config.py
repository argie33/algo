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

from utils.validation.freshness_config import get_freshness_rule

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
        return self.parent.set(key, value, value_type, description, changed_by)

    def get_staleness_windows(self) -> dict[str, int]:
        """Get data patrol staleness thresholds (days) for all data types.

        CRITICAL: Thresholds are derived from utils/validation/freshness_config.py
        to ensure data_patrol and freshness_config agree on what "stale" means.
        Do NOT hardcode separate thresholds here — always reference freshness_config.

        Returns:
            {
                "price_daily": 1,          # from freshness_config
                "technical_data_daily": 1,
                "buy_sell_daily": 1,
                "trend_template_data": 1,
                "signal_quality_scores": 1,
                "market_health_daily": 1,
                "stock_scores": 1,
                "algo_risk_daily": 1,
                ...
            }
        """
        # Map patrol table names to freshness_config table names
        table_name_map = {
            "price_daily": "price_daily",
            "technical_data_daily": "technical_data_daily",
            "buy_sell_daily": "buy_sell_daily",
            "trend_data": "trend_template_data",
            "signal_quality_scores": "signal_quality_scores",
            "market_health": "market_health_daily",
            "stock_scores": "stock_scores",
            "aaii_sentiment": "aaii_sentiment",
            "growth_metrics": "growth_metrics_daily",
            "earnings_history": "earnings_history_daily",
            "sector_ranking": "sector_ranking_daily",
            "industry_ranking": "industry_ranking_daily",
            "insider_transactions": "insider_transactions_daily",
            "analyst_upgrades": "analyst_upgrades_daily",
        }

        windows = {}
        for patrol_name, fresh_table_name in table_name_map.items():
            # Try to get from freshness_config first
            rule = get_freshness_rule(fresh_table_name)
            if rule:
                max_age = rule.get("max_age_days")
                if max_age is None:
                    raise RuntimeError(
                        f"[CONFIG CRITICAL] freshness_config rule for '{fresh_table_name}' "
                        f"missing 'max_age_days' key. Data staleness thresholds are required for safety."
                    )
                windows[patrol_name] = max_age
            else:
                # No fallback - this is a critical configuration issue
                raise RuntimeError(
                    f"[CONFIG CRITICAL] Table '{fresh_table_name}' not found in freshness_config.FRESHNESS_RULES. "
                    f"Data staleness thresholds must be defined in one place (freshness_config.py), not duplicated. "
                    f"Add '{fresh_table_name}' to FRESHNESS_RULES with max_age_days."
                )

        return windows

    def get_coverage_thresholds(self) -> dict[str, int]:
        """Get data patrol coverage ratio thresholds.

        CRITICAL: These thresholds control when data patrol alerts fire.
        Missing configuration is a critical safety issue.

        Returns:
            {
                "error_pct": 95,   # Alert error threshold
                "warn_pct": 90,    # Alert warning threshold
            }
        """
        error_pct = self.get("patrol_coverage_error_threshold_pct")
        warn_pct = self.get("patrol_coverage_warning_threshold_pct")

        if error_pct is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_coverage_error_threshold_pct is missing. "
                "Data coverage thresholds must be explicitly configured, not defaulted."
            )
        if warn_pct is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_coverage_warning_threshold_pct is missing. "
                "Data coverage thresholds must be explicitly configured, not defaulted."
            )

        return {
            "error_pct": error_pct,
            "warn_pct": warn_pct,
        }

    def get_price_sanity_config(self) -> dict[str, Any]:
        """Get data patrol OHLC/price sanity thresholds.

        CRITICAL: These thresholds detect corrupted price data (impossible price moves).
        Missing configuration could allow obviously bad data into the system.

        Returns:
            {
                "max_daily_move_pct": 0.5,    # Max daily move %
                "max_daily_move_count": 10,   # Max count of >50% moves
            }
        """
        max_move_pct = self.get("patrol_max_daily_move_pct")
        max_move_count = self.get("patrol_max_daily_move_count")

        if max_move_pct is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_max_daily_move_pct is missing. "
                "Price sanity thresholds must be explicitly configured to detect data corruption."
            )
        if max_move_count is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_max_daily_move_count is missing. "
                "Price sanity thresholds must be explicitly configured to detect data corruption."
            )

        return {
            "max_daily_move_pct": max_move_pct,
            "max_daily_move_count": max_move_count,
        }

    def get_volume_config(self) -> dict[str, Any]:
        """Get data patrol volume sanity thresholds.

        CRITICAL: These thresholds detect volume anomalies and data quality issues.
        Missing configuration could allow suspicious volume data into calculations.

        Returns:
            {
                "low_threshold": 1000,
                "high_threshold": 100000000,
                "new_low_alert": 5,
            }
        """
        low_thresh = self.get("patrol_low_volume_threshold")
        high_thresh = self.get("patrol_high_volume_threshold")
        new_low_alert = self.get("patrol_new_low_volume_alert")

        if low_thresh is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_low_volume_threshold is missing. "
                "Volume sanity checks must be explicitly configured."
            )
        if high_thresh is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_high_volume_threshold is missing. "
                "Volume sanity checks must be explicitly configured."
            )
        if new_low_alert is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_new_low_volume_alert is missing. "
                "Volume anomaly detection must be explicitly configured."
            )

        return {
            "low_threshold": low_thresh,
            "high_threshold": high_thresh,
            "new_low_alert": new_low_alert,
        }

    def get_quality_config(self) -> dict[str, Any]:
        """Get data patrol quality thresholds.

        CRITICAL: These thresholds detect incomplete/duplicate data patterns.
        Missing configuration could allow data quality issues to go undetected.

        Returns:
            {
                "max_null_pct": 5,
                "zero_symbols_error": 10,
                "zero_symbols_warn": 5,
                "identical_ohlc_threshold": 50,
            }
        """
        max_null = self.get("patrol_max_null_pct_threshold")
        zero_err = self.get("patrol_new_zero_symbols_error")
        zero_warn = self.get("patrol_new_zero_symbols_warn")
        identical = self.get("patrol_identical_ohlc_threshold")

        if max_null is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_max_null_pct_threshold is missing. "
                "NULL tolerance thresholds must be explicitly configured."
            )
        if zero_err is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_new_zero_symbols_error is missing. "
                "Data coverage error thresholds must be explicitly configured."
            )
        if zero_warn is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_new_zero_symbols_warn is missing. "
                "Data coverage warning thresholds must be explicitly configured."
            )
        if identical is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_identical_ohlc_threshold is missing. "
                "Duplicate OHLC detection must be explicitly configured."
            )

        return {
            "max_null_pct": max_null,
            "zero_symbols_error": zero_err,
            "zero_symbols_warn": zero_warn,
            "identical_ohlc_threshold": identical,
        }

    def get_cross_validation_config(self) -> dict[str, Any]:
        """Get data patrol cross-validation thresholds.

        CRITICAL: These thresholds detect price data mismatches across sources.
        Missing configuration could allow data inconsistencies to go undetected.

        Returns:
            {
                "price_mismatch_pct": 2,
                "top_n_symbols": 50,
            }
        """
        mismatch = self.get("patrol_price_xval_mismatch_pct")
        top_n = self.get("patrol_xval_top_n_symbols")

        if mismatch is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_price_xval_mismatch_pct is missing. "
                "Price cross-validation thresholds must be explicitly configured."
            )
        if top_n is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_xval_top_n_symbols is missing. "
                "Cross-validation scope must be explicitly configured."
            )

        return {
            "price_mismatch_pct": mismatch,
            "top_n_symbols": top_n,
        }

    def get_corporate_actions_config(self) -> dict[str, Any]:
        """Get data patrol corporate actions detection config.

        CRITICAL: These parameters control split/dividend detection, which affects
        price normalization and technical indicator accuracy.

        Returns:
            {
                "lookback_days": 90,
                "drop_ratio": -0.30,
            }
        """
        lookback = self.get("patrol_corporate_action_lookback_days")
        drop = self.get("patrol_corporate_action_drop_ratio")

        import logging as _logging

        _log = _logging.getLogger(__name__)

        if lookback is None:
            # Default documented in docstring; migration 106 adds this key to algo_config.
            # Log CRITICAL so ops can see the missing key but don't crash DataPatrol entirely.
            _log.critical(
                "[CONFIG CRITICAL] patrol_corporate_action_lookback_days missing from algo_config — "
                "using default 90. Apply migration 106 to fix."
            )
            lookback = 90
        if drop is None:
            _log.critical(
                "[CONFIG CRITICAL] patrol_corporate_action_drop_ratio missing from algo_config — "
                "using default -0.30. Apply migration 106 to fix."
            )
            drop = -0.30

        return {
            "lookback_days": lookback,
            "drop_ratio": drop,
        }

    def get_loader_contracts(self) -> dict[str, dict[str, Any]]:
        """Get data patrol loader contracts with expected output thresholds.

        CRITICAL: These contracts define minimum data coverage for each loader.
        Missing configuration is a safety issue—data patrol cannot monitor if contracts are undefined.

        Returns:
            {
                "price_daily": {
                    "condition": "date >= CURRENT_DATE - get_interval_sql('14d')",
                    "min_rows": 40000,
                    "severity": "error",
                    "description": "Daily price data should be ~5000 symbols x 14 days",
                },
                ... (other loader contracts)
            }
        """
        severity_error = "error"

        # Extract all loader contract thresholds with explicit fail-fast
        price_14d = self.get("patrol_price_daily_14d_min")
        tech_14d = self.get("patrol_technical_daily_14d_min")
        buysell_14d = self.get("patrol_buy_sell_daily_14d_min")
        trend_14d = self.get("patrol_trend_14d_min")
        mkt_exp = self.get("patrol_market_exposure_daily_min")

        if price_14d is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_price_daily_14d_min is missing. "
                "Price loader contract must be explicitly configured."
            )
        if tech_14d is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_technical_daily_14d_min is missing. "
                "Technical data loader contract must be explicitly configured."
            )
        if buysell_14d is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_buy_sell_daily_14d_min is missing. "
                "Buy/sell signal loader contract must be explicitly configured."
            )
        if trend_14d is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_trend_14d_min is missing. "
                "Trend template loader contract must be explicitly configured."
            )
        if mkt_exp is None:
            raise RuntimeError(
                "[CONFIG CRITICAL] patrol_market_exposure_daily_min is missing. "
                "Market exposure loader contract must be explicitly configured."
            )

        return {
            "price_daily": {
                "condition": "date >= CURRENT_DATE - get_interval_sql('14d')",
                "min_rows": price_14d,
                "severity": severity_error,
                "description": "Daily price data should be ~5000 symbols x 14 days",
            },
            "technical_data_daily": {
                "condition": "date >= CURRENT_DATE - get_interval_sql('14d')",
                "min_rows": tech_14d,
                "severity": severity_error,
                "description": "Technical indicators should match price coverage",
            },
            "buy_sell_daily": {
                "condition": "date >= CURRENT_DATE - get_interval_sql('14d')",
                "min_rows": buysell_14d,
                "severity": severity_error,
                "description": "Pine signals should produce 50+ per day minimum",
            },
            "trend_template_data": {
                "condition": "date >= CURRENT_DATE - get_interval_sql('14d')",
                "min_rows": trend_14d,
                "severity": severity_error,
                "description": "Trend template covers 4900+ symbols x 14 days",
            },
            "market_exposure_daily": {
                "condition": "date >= (SELECT MAX(date) - get_interval_sql('1d') FROM price_daily)",
                "min_rows": mkt_exp,
                "severity": severity_error,
                "description": "Market regime indicators must match latest trading day in price_daily (within 1 day lag)",
            },
        }

    def __repr__(self) -> str:
        return f"<DataPatrolConfig {len(self.get_staleness_windows())} staleness keys>"
