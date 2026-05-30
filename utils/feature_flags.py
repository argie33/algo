#!/usr/bin/env python3
"""
Feature Flags - Enable/disable features without code deploy

Enables:
- Disable broken signal tier (Tier 2 generating false signals? Disable in 10 sec)
- A/B testing (Tier 5 variant A vs variant B, measure win rate)
- Gradual rollout (start with 10% of signals, ramp to 100%)
- Quick rollback (revert to previous setting in 1 command)

Flags stored in database (easy to toggle without deploy):
- Can enable/disable per signal tier
- Can enable/disable per symbol
- Can set A/B test variant
- Queryable in real-time
"""

from config.credential_manager import get_db_config, get_db_password
import logging
import os
from utils.database_context import DatabaseContext
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


class FeatureFlagType(Enum):
    """Types of feature flags."""
    SIGNAL_TIER = "signal_tier"  # Enable/disable signal filter tier
    A_B_TEST = "ab_test"  # A/B test variant selection
    SYMBOL_OVERRIDE = "symbol_override"  # Per-symbol enable/disable
    ROLLOUT = "rollout"  # Gradual rollout (% of trades)


class FeatureFlags:
    """Manage feature flags for safe signal control."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_updated_at = None
        self._cache_ttl_seconds = 30  # Refresh cache every 30 seconds

    def set_flag(
        self,
        flag_name: str,
        flag_type: str,
        value: Any,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Set a feature flag value.

        Args:
            flag_name: Name of the flag (e.g., "tier_2_enabled", "ab_test_variant_a")
            flag_type: Type of flag (SIGNAL_TIER, A_B_TEST, etc.)
            value: The value to set (bool, int, str, etc.)
            description: Human-readable description
            metadata: Optional extra context

        Returns:
            True if set successfully
        """
        try:
            import json
            metadata_json = json.dumps(metadata or {})

            with DatabaseContext('write') as cur:
                cur.execute("""
                    INSERT INTO feature_flags
                    (flag_name, flag_type, value, description, metadata, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (flag_name) DO UPDATE SET
                        value = EXCLUDED.value,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                """, (
                    flag_name,
                    flag_type,
                    str(value),
                    description,
                    metadata_json,
                ))
                cur.connection.commit()

            # Clear cache
            self._cache.clear()

            logger.info("Feature flag updated", extra={
                "flag_name": flag_name,
                "value": value,
                "type": flag_type,
            })

            return True

        except Exception as e:
            logger.error(f"Failed to set flag: {e}")
            return False

    def get_flag(self, flag_name: str, default: Any = None) -> Any:
        """Get a feature flag value (with TTL cache)."""
        try:
            from datetime import datetime as dt
            now = dt.now()
            cache_expired = (
                self._cache_updated_at is None or
                (now - self._cache_updated_at).total_seconds() > self._cache_ttl_seconds
            )

            if flag_name in self._cache and not cache_expired:
                return self._cache[flag_name]

            # Refresh cache if expired
            if cache_expired:
                self._cache.clear()
                self._cache_updated_at = now

            with DatabaseContext() as cur:
                cur.execute("""
                    SELECT value, enabled FROM feature_flags
                    WHERE flag_name = %s
                    ORDER BY updated_at DESC
                    LIMIT 1
                """, (flag_name,))

                row = cur.fetchone()
                if row:
                    value, enabled = row[0], row[1]
                    # If flag is disabled, return False; otherwise parse and return value
                    if not enabled:
                        self._cache[flag_name] = False
                        return False
                    if isinstance(value, str):
                        if value.lower() in ('true', 'false'):
                            value = value.lower() == 'true'
                        elif value.isdigit():
                            value = int(value)
                    self._cache[flag_name] = value
                    return value

            return default

        except Exception as e:
            logger.warning(f"Failed to get flag {flag_name}: {e}")
            return default

    def is_enabled(self, flag_name: str, default: bool = True) -> bool:
        """Check if a feature is enabled."""
        value = self.get_flag(flag_name, default)
        return value in (True, 'true', '1', 1)

    def disable_flag(self, flag_name: str) -> bool:
        """Disable a flag immediately (emergency disable)."""
        return self.set_flag(flag_name, "emergency_disable", False,
                            description=f"Emergency disable at {datetime.now().isoformat()}")

    def enable_flag(self, flag_name: str) -> bool:
        """Re-enable a flag."""
        return self.set_flag(flag_name, "enable", True)

    def list_flags(self) -> List[Dict[str, Any]]:
        """Get all feature flags."""
        try:
            with DatabaseContext() as cur:
                cur.execute("""
                    SELECT flag_name, flag_type, value, description, enabled, updated_at
                    FROM feature_flags
                    ORDER BY updated_at DESC
                """)

                columns = [desc[0] for desc in cur.description]
                results = []
                for row in cur.fetchall():
                    results.append(dict(zip(columns, row)))
                return results

        except Exception as e:
            logger.error(f"Failed to list flags: {e}")
            return []

    def get_signal_tier_enabled(self, tier: int) -> bool:
        """Check if a signal tier is enabled."""
        return self.is_enabled(f"signal_tier_{tier}_enabled", default=True)

    def get_ab_test_variant(self, test_name: str, default: str = "control") -> str:
        """Get A/B test variant."""
        return self.get_flag(f"ab_test_{test_name}_variant", default)

    def get_rollout_percentage(self, feature_name: str, default: int = 100) -> int:
        """Get rollout percentage (0-100)."""
        pct = self.get_flag(f"rollout_{feature_name}_pct", default)
        try:
            return int(pct)
        except (ValueError, TypeError):
            return default


# Safe default feature flags (fail-closed / conservative)
DEFAULT_FEATURE_FLAGS = {
    # Signal Pipeline - All enabled by default (safe = enabled)
    'signal_tier_1_enabled': ('signal_tier', True, 'Enable Tier 1: Data Quality Gates'),
    'signal_tier_2_enabled': ('signal_tier', True, 'Enable Tier 2: Market Health Gates'),
    'signal_tier_3_enabled': ('signal_tier', True, 'Enable Tier 3: Trend Template Confirmation'),
    'signal_tier_4_enabled': ('signal_tier', True, 'Enable Tier 4: Signal Quality Scores'),
    'signal_tier_5_enabled': ('signal_tier', True, 'Enable Tier 5: Portfolio Health'),

    # Risk Management - All enabled by default (conservative = enabled)
    'circuit_breaker_enabled': ('signal_tier', True, 'Enable circuit breaker on extreme VIX/breadth'),
    'earnings_blackout_enabled': ('signal_tier', True, 'Enable earnings date blackout'),
    'position_sizing_enabled': ('signal_tier', True, 'Enable dynamic position sizing by tier'),
    'max_position_size_pct': ('rollout', 8.0, 'Maximum single position size as % of portfolio'),
    'base_risk_pct': ('rollout', 0.75, 'Base portfolio risk per trade'),

    # Trading Execution
    'paper_trading_mode': ('signal_tier', True, 'Use paper trading (safe = true)'),
    'require_manual_approval': ('signal_tier', False, 'Require manual approval before trades'),
    'execute_trades': ('signal_tier', True, 'Execute trades (false = dry-run only)'),

    # Data Quality
    'skip_missing_data': ('signal_tier', True, 'Skip trades when key data is missing'),
    'require_current_prices': ('signal_tier', True, 'Require current market prices (< 1 day old)'),

    # A/B Testing & Rollout
    'rollout_new_signals_pct': ('rollout', 100, 'Percentage of new signals to evaluate (0-100)'),
    'ab_test_tier_5_variant': ('ab_test', 'control', 'Variant for Tier 5 A/B test: control or experimental'),
}


def create_feature_flags_table():
    """Feature flags table is now created in utils/init_database.py (AUTHORITATIVE).

    This function is kept for backwards compatibility but does nothing.
    """
    pass


def initialize_safe_defaults():
    """Initialize feature flags with safe (fail-closed) defaults.

    Called on system startup to ensure all critical feature flags are set.
    Safe defaults = conservative behavior that prevents accidental trades.
    """
    try:
        flags = FeatureFlags()
        initialized_count = 0

        for flag_name, (flag_type, default_value, description) in DEFAULT_FEATURE_FLAGS.items():
            with DatabaseContext() as cur:
                cur.execute("""
                    SELECT value FROM feature_flags WHERE flag_name = %s
                """, (flag_name,))
                existing = cur.fetchone()

            # Only set if doesn't exist (preserve any manual overrides)
            if not existing:
                flags.set_flag(flag_name, flag_type, default_value, description)
                initialized_count += 1

        if initialized_count > 0:
            logger.info(f"Initialized {initialized_count} feature flags with safe defaults")

        return True
    except Exception as e:
        logger.error(f"Failed to initialize feature flags: {e}")
        return False


# Singleton
_flags = None


def get_flags() -> FeatureFlags:
    """Get singleton feature flags manager."""
    global _flags
    if _flags is None:
        _flags = FeatureFlags()
    return _flags


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Feature flags manager")
    parser.add_argument('--create-table', action='store_true', help='Create feature_flags table')
    parser.add_argument('--list', action='store_true', help='List all flags')
    parser.add_argument('--enable', metavar='FLAG', help='Enable a flag')
    parser.add_argument('--disable', metavar='FLAG', help='Disable a flag (emergency)')
    parser.add_argument('--set', nargs=3, metavar=('FLAG', 'TYPE', 'VALUE'),
                        help='Set a flag: --set tier_2_enabled signal_tier true')
    parser.add_argument('--get', metavar='FLAG', help='Get a flag value')

    args = parser.parse_args()

    flags = get_flags()

    if args.create_table:
        create_feature_flags_table()

    elif args.list:
        all_flags = flags.list_flags()
        if not all_flags:
            logger.info("No feature flags set yet")
        else:
            logger.info(f"\n{'FLAG NAME':<40} {'TYPE':<20} {'VALUE':<15} {'ENABLED':<10}")
            logger.info("=" * 85)
            for flag in all_flags:
                logger.info(f"{flag['flag_name']:<40} {flag['flag_type']:<20} "
                      f"{flag['value']:<15} {str(flag['enabled']):<10}")

    elif args.enable:
        success = flags.enable_flag(args.enable)
        logger.info(f"{'✓' if success else '✗'} Flag '{args.enable}' enabled")

    elif args.disable:
        success = flags.disable_flag(args.disable)
        logger.info(f"{'✓' if success else '✗'} Flag '{args.disable}' disabled (EMERGENCY)")

    elif args.set:
        flag_name, flag_type, value = args.set
        success = flags.set_flag(flag_name, flag_type, value)
        logger.info(f"{'✓' if success else '✗'} Flag '{flag_name}' set to '{value}'")

    elif args.get:
        value = flags.get_flag(args.get)
        logger.info(f"{args.get} = {value}")

    else:
        parser.print_help()
