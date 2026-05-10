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

import logging
import os
import psycopg2
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum
from pathlib import Path
from dotenv import load_dotenv

from credential_manager import get_credential_manager
from structured_logger import get_logger

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logger = get_logger(__name__)
credential_manager = get_credential_manager()

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
    }


class FeatureFlagType(Enum):
    """Types of feature flags."""
    SIGNAL_TIER = "signal_tier"  # Enable/disable signal filter tier
    A_B_TEST = "ab_test"  # A/B test variant selection
    SYMBOL_OVERRIDE = "symbol_override"  # Per-symbol enable/disable
    ROLLOUT = "rollout"  # Gradual rollout (% of trades)


class FeatureFlags:
    """Manage feature flags for safe signal control."""

    def __init__(self):
        self.conn = None
        self._cache: Dict[str, Any] = {}
        self._cache_updated_at = None

    def connect(self):
        """Connect to database."""
        if not self.conn:
            self.conn = psycopg2.connect(**_get_db_config())

    def disconnect(self):
        """Disconnect from database."""
        if self.conn:
            self.conn.close()
            self.conn = None

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
            self.connect()

            import json
            metadata_json = json.dumps(metadata or {})

            with self.conn.cursor() as cur:
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
                self.conn.commit()

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
        """Get a feature flag value."""
        try:
            self.connect()

            # Try cache first
            if flag_name in self._cache:
                return self._cache[flag_name]

            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT value FROM feature_flags
                    WHERE flag_name = %s
                    AND enabled = true
                    ORDER BY updated_at DESC
                    LIMIT 1
                """, (flag_name,))

                row = cur.fetchone()
                if row:
                    value = row[0]
                    # Parse value back to bool if it was boolean
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
            self.connect()

            with self.conn.cursor() as cur:
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


# Create feature_flags table
def create_feature_flags_table():
    """Create feature_flags table if it doesn't exist."""
    try:
        conn = psycopg2.connect(**_get_db_config())
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS feature_flags (
                    id SERIAL PRIMARY KEY,
                    flag_name VARCHAR(255) UNIQUE NOT NULL,
                    flag_type VARCHAR(50) NOT NULL,
                    value TEXT NOT NULL,
                    description TEXT,
                    metadata JSONB DEFAULT '{}',
                    enabled BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_feature_flags_name ON feature_flags(flag_name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_feature_flags_type ON feature_flags(flag_type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_feature_flags_updated ON feature_flags(updated_at DESC)")
            conn.commit()
            conn.close()
            logger.info("Feature flags table created")
    except Exception as e:
        logger.error(f"Failed to create feature flags table: {e}")


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
            print("No feature flags set yet")
        else:
            print(f"\n{'FLAG NAME':<40} {'TYPE':<20} {'VALUE':<15} {'ENABLED':<10}")
            print("=" * 85)
            for flag in all_flags:
                print(f"{flag['flag_name']:<40} {flag['flag_type']:<20} "
                      f"{flag['value']:<15} {str(flag['enabled']):<10}")

    elif args.enable:
        success = flags.enable_flag(args.enable)
        print(f"{'✓' if success else '✗'} Flag '{args.enable}' enabled")

    elif args.disable:
        success = flags.disable_flag(args.disable)
        print(f"{'✓' if success else '✗'} Flag '{args.disable}' disabled (EMERGENCY)")

    elif args.set:
        flag_name, flag_type, value = args.set
        success = flags.set_flag(flag_name, flag_type, value)
        print(f"{'✓' if success else '✗'} Flag '{flag_name}' set to '{value}'")

    elif args.get:
        value = flags.get_flag(args.get)
        print(f"{args.get} = {value}")

    else:
        parser.print_help()

    flags.disconnect()
