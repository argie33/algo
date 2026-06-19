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
            assert "CRITICAL" in error_msg
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
            assert val is not None, (
                f"Critical threshold {key} is None — "
                "should have default value"
            )
            assert (
                val != 0 and val != 0.0
            ), (
                f"Critical threshold {key} is zero — "
                "validation should have failed"
            )
