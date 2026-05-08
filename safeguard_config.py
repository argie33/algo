#!/usr/bin/env python3
"""Centralized safeguard configuration management.

All production safeguard thresholds and settings in one place.
Can be loaded from environment, config file, or database.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any
import json

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)


class SafeguardConfig:
    """Unified safeguard configuration."""

    def __init__(self, config_file=None, env_override=True):
        self.config_file = config_file
        self.env_override = env_override
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from multiple sources (priority order)."""
        config = self._get_defaults()

        # Load from file if provided
        if self.config_file and Path(self.config_file).exists():
            config.update(self._load_from_file(self.config_file))

        # Override with environment variables if enabled
        if self.env_override:
            config.update(self._load_from_env())

        return config

    def _get_defaults(self) -> Dict[str, Any]:
        """Return default safeguard configuration."""
        return {
            # LIQUIDITY CHECKS
            'liquidity_enabled': True,
            'min_daily_volume_shares': 1000000.0,
            'max_spread_pct': 0.5,
            'min_market_cap_millions': 300.0,
            'min_float_millions': 10.0,
            'max_short_interest_pct': 30.0,

            # EARNINGS BLACKOUT
            'earnings_enabled': True,
            'earnings_blackout_days_before': 7,
            'earnings_blackout_days_after': 7,
            'earnings_stop_atr_mult': 2.0,

            # MARGIN MONITORING
            'margin_enabled': True,
            'margin_alert_pct': 70.0,
            'margin_halt_pct': 80.0,
            'margin_check_interval_minutes': 1,

            # ECONOMIC CALENDAR
            'economic_calendar_enabled': True,
            'halt_entries_before_major_release_minutes': 60,
            'economic_impact_levels': ['high', 'medium'],

            # ALERTS & NOTIFICATIONS
            'alerts_enabled': True,
            'alert_channels': ['log', 'database'],  # log, email, slack, database, sms
            'alert_email': os.getenv('SAFEGUARD_ALERT_EMAIL', ''),
            'alert_slack_webhook': os.getenv('SAFEGUARD_SLACK_WEBHOOK', ''),
            'alert_twilio_number': os.getenv('SAFEGUARD_TWILIO_NUMBER', ''),
            'alert_email_on_blocks': True,
            'alert_slack_on_critical': True,

            # AUDIT LOGGING
            'audit_logging_enabled': True,
            'audit_log_level': 'INFO',  # DEBUG, INFO, WARNING, ERROR
            'persist_to_database': True,
            'log_retention_days': 90,

            # PERFORMANCE METRICS
            'track_metrics': True,
            'metrics_calculation_window': 30,  # days
            'metrics_target_false_positive_rate': 0.02,  # 2%

            # RISK SCORING
            'risk_scoring_enabled': True,
            'risk_alert_threshold': 8.0,  # out of 10
            'risk_position_limit_pct': 15.0,  # max % of portfolio

            # FEATURE FLAGS
            'fail_open': True,  # Continue if safeguard check fails
            'dry_run_mode': False,
            'log_block_decisions': True,
            'persist_metrics': True,

            # THRESHOLDS (Can be tuned after paper trading)
            'strict_mode': False,  # When True, tighten all thresholds by 20%
        }

    def _load_from_file(self, filepath: str) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load config file {filepath}: {e}")
            return {}

    def _load_from_env(self) -> Dict[str, Any]:
        """Load configuration from environment variables (SAFEGUARD_* prefix)."""
        config = {}
        for key, value in os.environ.items():
            if not key.startswith('SAFEGUARD_'):
                continue

            config_key = key[10:].lower()  # Remove SAFEGUARD_ prefix

            # Type conversion
            if value.lower() in ('true', 'false'):
                config[config_key] = value.lower() == 'true'
            elif value.replace('.', '').isdigit():
                try:
                    config[config_key] = float(value) if '.' in value else int(value)
                except ValueError:
                    config[config_key] = value
            else:
                config[config_key] = value

        return config

    def get(self, key: str, default=None) -> Any:
        """Get configuration value."""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value (runtime override)."""
        self._config[key] = value

    def is_enabled(self, safeguard: str) -> bool:
        """Check if safeguard is enabled."""
        return self.get(f'{safeguard}_enabled', True)

    def apply_strict_mode(self) -> None:
        """Tighten all thresholds by 20% for strict mode."""
        if self.get('strict_mode'):
            self.set('min_daily_volume_shares', int(self.get('min_daily_volume_shares') * 1.2))
            self.set('max_spread_pct', self.get('max_spread_pct') * 0.8)
            self.set('min_market_cap_millions', int(self.get('min_market_cap_millions') * 1.2))
            self.set('min_float_millions', int(self.get('min_float_millions') * 1.2))
            self.set('margin_halt_pct', self.get('margin_halt_pct') * 0.95)
            self.set('margin_alert_pct', self.get('margin_alert_pct') * 0.95)

    def to_dict(self) -> Dict[str, Any]:
        """Export configuration as dictionary."""
        return self._config.copy()

    def to_json(self) -> str:
        """Export configuration as JSON."""
        return json.dumps(self._config, indent=2, default=str)

    def save_to_file(self, filepath: str) -> None:
        """Save current configuration to file."""
        with open(filepath, 'w') as f:
            json.dump(self._config, f, indent=2, default=str)


def get_safeguard_config(config_file=None) -> SafeguardConfig:
    """Factory function to get global safeguard config."""
    return SafeguardConfig(config_file=config_file)


if __name__ == "__main__":
    config = get_safeguard_config()

    print("Current Safeguard Configuration:")
    print("-" * 70)
    for key, value in sorted(config.to_dict().items()):
        print(f"  {key:45s} = {value}")

    print("\n" + "-" * 70)
    print(f"Enabled safeguards:")
    print(f"  Liquidity:    {config.is_enabled('liquidity')}")
    print(f"  Earnings:     {config.is_enabled('earnings')}")
    print(f"  Margin:       {config.is_enabled('margin')}")
    print(f"  Economic:     {config.is_enabled('economic_calendar')}")
