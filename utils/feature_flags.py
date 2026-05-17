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

from config.credential_helper import get_db_config
from config.env_loader import load_env
import logging
import os
from utils.db_connection import get_db_connection
from config.credential_helper import get_db_password, get_db_config
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum
from pathlib import Path

from utils.structured_logger import get_logger

logger = logging.getLogger(__name__)

logger = get_logger(__name__)

def create_feature_flags_table():
    """Create feature_flags table if it doesn't exist."""
    try:
        conn = get_db_connection()
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

def initialize_safe_defaults():
    """Initialize feature flags with safe (fail-closed) defaults.

    Called on system startup to ensure all critical feature flags are set.
    Safe defaults = conservative behavior that prevents accidental trades.
    """
    try:
        flags = FeatureFlags()
        flags.connect()

        initialized_count = 0
        for flag_name, (flag_type, default_value, description) in DEFAULT_FEATURE_FLAGS.items():
            # Check if flag already exists
            with flags.conn.cursor() as cur:
                cur.execute("""
                    SELECT value FROM feature_flags WHERE flag_name = %s
                """, (flag_name,))
                existing = cur.fetchone()

            # Only set if doesn't exist (preserve any manual overrides)
            if not existing:
                flags.set_flag(flag_name, flag_type, default_value, description)
                initialized_count += 1

        flags.disconnect()

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

    flags.disconnect()
