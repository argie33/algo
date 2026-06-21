#!/usr/bin/env python3
"""Test suite for config startup validation.

Verifies that the system fails-fast if critical safety thresholds are zero or missing.
This is Finding 3: Configuration Loading Validation fix.
"""

import sys
from pathlib import Path
from unittest import mock

import pytest


# Add project root to path
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)


class TestConfigCriticalThresholds:
    """Test that AlgoConfig detects zero/missing critical safety thresholds."""

    def test_valid_config_loads_without_error(self):
        """Config should load successfully with all thresholds set to safe values."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        assert config.get("min_signal_quality_score") >= 40
        assert config.get("min_swing_score") >= 30
        assert config.get("halt_drawdown_pct") != 0
        assert config.get("max_daily_loss_pct") != 0
        assert config.get("vix_max_threshold") != 0

    def test_critical_threshold_validation_catches_zero_signal_quality(self):
        """Should raise RuntimeError if min_signal_quality_score is zero."""
        from algo.infrastructure.config import AlgoConfig

        def mock_load_with_zero_sqs(self):
            self._config["min_signal_quality_score"] = 0

        patch_target = AlgoConfig, "_load_from_database"
        with mock.patch.object(*patch_target, mock_load_with_zero_sqs):
            with pytest.raises(RuntimeError, match="SAFETY GATE FAILURE"):
                AlgoConfig()

    def test_critical_threshold_validation_catches_zero_swing_score(self):
        """Should raise RuntimeError if min_swing_score is zero."""
        from algo.infrastructure.config import AlgoConfig

        def mock_load_with_zero_swing(self):
            self._config["min_swing_score"] = 0.0

        patch_target = AlgoConfig, "_load_from_database"
        with mock.patch.object(*patch_target, mock_load_with_zero_swing):
            with pytest.raises(RuntimeError, match="SAFETY GATE FAILURE"):
                AlgoConfig()

    def test_critical_threshold_validation_catches_zero_halt_drawdown(self):
        """Should raise RuntimeError if halt_drawdown_pct is zero."""
        from algo.infrastructure.config import AlgoConfig

        def mock_load_with_zero_halt(self):
            self._config["halt_drawdown_pct"] = 0

        patch_target = AlgoConfig, "_load_from_database"
        with mock.patch.object(*patch_target, mock_load_with_zero_halt):
            with pytest.raises(RuntimeError, match="SAFETY GATE FAILURE"):
                AlgoConfig()

    def test_critical_threshold_validation_catches_zero_max_daily_loss(self):
        """Should raise RuntimeError if max_daily_loss_pct is zero."""
        from algo.infrastructure.config import AlgoConfig

        def mock_load_with_zero_daily_loss(self):
            self._config["max_daily_loss_pct"] = 0

        patch_target = AlgoConfig, "_load_from_database"
        with mock.patch.object(*patch_target, mock_load_with_zero_daily_loss):
            with pytest.raises(RuntimeError, match="SAFETY GATE FAILURE"):
                AlgoConfig()

    def test_critical_threshold_validation_catches_zero_vix_threshold(self):
        """Should raise RuntimeError if vix_max_threshold is zero."""
        from algo.infrastructure.config import AlgoConfig

        def mock_load_with_zero_vix(self):
            self._config["vix_max_threshold"] = 0

        patch_target = AlgoConfig, "_load_from_database"
        with mock.patch.object(*patch_target, mock_load_with_zero_vix):
            with pytest.raises(RuntimeError, match="SAFETY GATE FAILURE"):
                AlgoConfig()

    def test_critical_threshold_validation_catches_missing_thresholds(self):
        """Should raise RuntimeError if critical thresholds are None."""
        from algo.infrastructure.config import AlgoConfig

        def mock_load_with_missing(self):
            self._config["min_signal_quality_score"] = None

        patch_target = AlgoConfig, "_load_from_database"
        with mock.patch.object(*patch_target, mock_load_with_missing):
            with pytest.raises(RuntimeError, match="SAFETY GATE FAILURE"):
                AlgoConfig()

    def test_critical_threshold_validation_error_message_is_informative(self):
        """Error message should guide user to check database and migration-033."""
        from algo.infrastructure.config import AlgoConfig

        def mock_load_with_zero(self):
            self._config["max_daily_loss_pct"] = 0

        patch_target = AlgoConfig, "_load_from_database"
        with mock.patch.object(*patch_target, mock_load_with_zero):
            with pytest.raises(RuntimeError) as exc_info:
                AlgoConfig()

            error_msg = str(exc_info.value)
            assert "SAFETY GATE FAILURE" in error_msg
            assert "max_daily_loss_pct" in error_msg
            assert "migration-033" in error_msg
            assert "database" in error_msg

    def test_all_critical_thresholds_listed_in_validation(self):
        """Verify all expected critical thresholds are checked at startup."""
        from algo.infrastructure.config import AlgoConfig

        critical_keys = {
            "min_signal_quality_score",
            "min_swing_score",
            "min_completeness_score",
            "min_volume_ma_50d",
            "min_avg_daily_dollar_volume",
            "earnings_blackout_days_before",
            "earnings_blackout_days_after",
            "halt_drawdown_pct",
            "max_daily_loss_pct",
            "vix_max_threshold",
        }

        config = AlgoConfig()
        for key in critical_keys:
            val = config.get(key)
            assert val is not None, f"Critical threshold {key} is None — should have default value"
            assert val != 0 and val != 0.0, f"Critical threshold {key} is zero — validation should have failed"

    def test_database_connection_failure_raises_error(self):
        """Should raise RuntimeError if database connection fails during config load."""
        from algo.infrastructure.config import AlgoConfig

        with mock.patch("algo.infrastructure.config.main.DatabaseContext") as mock_db:
            mock_db.return_value.__enter__.side_effect = ConnectionError("Database connection timeout")
            with pytest.raises(RuntimeError, match="Config initialization failed"):
                AlgoConfig()

    def test_database_query_failure_raises_error(self):
        """Should raise RuntimeError if database query fails during config load."""
        from algo.infrastructure.config import AlgoConfig

        with mock.patch("algo.infrastructure.config.main.DatabaseContext") as mock_db:
            mock_cursor = mock.MagicMock()
            mock_cursor.execute.side_effect = Exception("Database query error: syntax error")
            mock_db.return_value.__enter__.return_value = mock_cursor
            with pytest.raises(RuntimeError, match="cannot load safety thresholds from database"):
                AlgoConfig()


class TestConfigValidationSchema:
    """Test the validation schema for config range checking."""

    def test_schema_and_defaults_are_consistent(self):
        """All DEFAULTS keys should have SCHEMA entries with matching types."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        schema = config.VALIDATION_SCHEMA
        defaults = config.DEFAULTS

        for key in defaults:
            assert key in schema, f"Key {key} in DEFAULTS but not in VALIDATION_SCHEMA"

    def test_critical_keys_have_fail_closed_defaults(self):
        """All critical keys must have a fail_closed value in schema."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        for key, (dtype, min_val, max_val, is_critical, fail_closed) in config.VALIDATION_SCHEMA.items():
            if is_critical:
                assert fail_closed is not None, f"Critical key {key} must have a fail_closed default"
                if dtype in ("int", "float"):
                    # Fail-closed should be within valid range
                    if min_val is not None:
                        assert fail_closed >= min_val, f"Critical key {key}: fail_closed {fail_closed} < min {min_val}"
                    if max_val is not None:
                        assert fail_closed <= max_val, f"Critical key {key}: fail_closed {fail_closed} > max {max_val}"

    def test_validation_rejects_zero_signal_quality(self):
        """Should reject min_signal_quality_score = 0 as out of range."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        with pytest.raises(ValueError, match=r"below minimum\|CRITICAL SAFETY GATE"):
            config._validate_value("min_signal_quality_score", "0", "int")

    def test_validation_rejects_negative_min_swing_score(self):
        """Should reject negative swing score."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        with pytest.raises(ValueError, match="below minimum"):
            config._validate_value("min_swing_score", "-5.0", "float")

    def test_validation_rejects_halt_drawdown_positive(self):
        """Should reject positive halt_drawdown_pct (must be negative)."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        # Value 0 triggers critical safety gate (zero/near-zero not allowed for critical params)
        with pytest.raises(ValueError, match="CRITICAL SAFETY GATE"):
            config._validate_value("halt_drawdown_pct", "0", "float")
        # Value 10 (positive) triggers above maximum check
        with pytest.raises(ValueError, match="above maximum"):
            config._validate_value("halt_drawdown_pct", "10", "float")

    def test_validation_rejects_sector_drawdown_positive(self):
        """Should reject positive sector_drawdown_halt_pct (must be negative)."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        # Value 0 triggers critical safety gate (zero/near-zero not allowed for critical params)
        with pytest.raises(ValueError, match="CRITICAL SAFETY GATE"):
            config._validate_value("sector_drawdown_halt_pct", "0", "float")

    def test_validation_accepts_valid_percentages(self):
        """Should accept percentages within 0-100 range."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        assert config._validate_value("max_total_invested_pct", "95.0", "float")
        assert config._validate_value("min_completeness_score", "70", "int")

    def test_validation_rejects_percentage_over_100(self):
        """Should reject percentage values > 100."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        with pytest.raises(ValueError, match="above maximum"):
            config._validate_value("max_total_invested_pct", "150.0", "float")

    def test_validation_accepts_valid_negative_drawdown(self):
        """Should accept negative drawdown thresholds."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        assert config._validate_value("halt_drawdown_pct", "-20.0", "float")
        assert config._validate_value("sector_drawdown_halt_pct", "-12.0", "float")


class TestConfigFailClosedBehavior:
    """Test fail-closed behavior when invalid critical values are set."""

    def test_set_invalid_critical_value_uses_fail_closed_default(self):
        """Should apply fail-closed default when setting invalid critical value."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        # Attempt to set critical threshold to zero
        success = config.set("min_signal_quality_score", "0", "int", changed_by="test")
        # Should fail the set (return False)
        assert not success, "set() should return False when applying fail-closed default"
        # But config should be set to safe default
        assert config.get("min_signal_quality_score") == 60, (
            "Should revert to fail-closed default 60 when 0 is attempted"
        )

    def test_set_out_of_range_critical_value_uses_fail_closed_default(self):
        """Should apply fail-closed default when setting out-of-range critical value."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        # Attempt to set critical threshold above max
        success = config.set("min_signal_quality_score", "200", "int", changed_by="test")
        assert not success
        assert config.get("min_signal_quality_score") == 60

    def test_set_valid_critical_value_succeeds(self):
        """Should accept valid critical values."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        success = config.set("min_signal_quality_score", "75", "int", changed_by="test")
        assert success, "set() should return True for valid values"
        assert config.get("min_signal_quality_score") == 75

    def test_set_non_critical_invalid_value_fails_cleanly(self):
        """Should reject invalid non-critical values without fail-closed."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        success = config.set("max_trades_per_day", "1000", "int", changed_by="test")
        assert not success, "set() should return False for out-of-range non-critical value"
        # Old value should be preserved
        assert config.get("max_trades_per_day") == 5


class TestConfigCriticalThresholdsSummary:
    """Test critical thresholds summary method for monitoring."""

    def test_get_critical_thresholds_summary_includes_all_critical_keys(self):
        """Summary should include all critical thresholds."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        summary = config.get_critical_thresholds_summary()

        expected_critical = {
            "min_signal_quality_score",
            "min_swing_score",
            "min_completeness_score",
            "min_volume_ma_50d",
            "min_avg_daily_dollar_volume",
            "earnings_blackout_days_before",
            "earnings_blackout_days_after",
            "halt_drawdown_pct",
            "sector_drawdown_halt_pct",
            "max_daily_loss_pct",
            "vix_max_threshold",
            "base_risk_pct",
            "max_position_size_pct",
        }

        for key in expected_critical:
            assert key in summary, f"Critical key {key} missing from summary"

    def test_critical_thresholds_summary_format(self):
        """Summary should have required fields."""
        from algo.infrastructure.config import AlgoConfig

        config = AlgoConfig()
        summary = config.get_critical_thresholds_summary()

        # Pick one critical key to verify structure
        key = "min_signal_quality_score"
        assert key in summary
        assert "value" in summary[key]
        assert "min" in summary[key]
        assert "max" in summary[key]
        assert "safe_default" in summary[key]
        assert "source" in summary[key]
