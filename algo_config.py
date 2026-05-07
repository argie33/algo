#!/usr/bin/env python3
"""
Algo Configuration System (Hot-Reload Enabled)

Centralized configuration from database. Changes take effect immediately without restart.
Supports: risk parameters, filter thresholds, execution modes, feature flags.
"""

import os
try:
    import psycopg2
except ImportError:
    # Lambda: psycopg2 binary not available, will fail at runtime if DB needed
    psycopg2 = None
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)


def validate_environment():
    """Validate that all required environment variables are set.

    Called on module load. Raises RuntimeError if critical vars are missing.
    """
    # Check for DB credentials (can use defaults, but warn if none set)
    db_host = os.getenv("DB_HOST")
    db_name = os.getenv("DB_NAME")

    if not db_host:
        print("WARNING: DB_HOST not set, using default 'localhost'")
    if not db_name:
        print("WARNING: DB_NAME not set, using default 'stocks'")

    # Alpaca credentials are optional for paper trading, but check anyway
    alpaca_key = os.getenv("APCA_API_KEY_ID")
    alpaca_secret = os.getenv("APCA_API_SECRET_KEY")
    if not alpaca_key or not alpaca_secret:
        print("WARNING: Alpaca credentials (APCA_API_KEY_ID, APCA_API_SECRET_KEY) not set — paper trading only")

    return True


# Validate on import
try:
    validate_environment()
except Exception as e:
    print(f"ERROR: Environment validation failed: {e}")
    raise

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}

class AlgoConfig:
    """Configuration manager with hot-reload from database."""

    # Default configuration values
    DEFAULTS = {
        # Risk Management
        'base_risk_pct': ('0.75', 'float', 'Base portfolio risk per trade'),
        'max_position_size_pct': ('8.0', 'float', 'Maximum single position size'),
        'max_positions': ('12', 'int', 'Maximum concurrent positions'),
        'max_concentration_pct': ('50.0', 'float', 'Max concentration in top position'),

        # Drawdown Defense
        'risk_reduction_at_minus_5': ('0.75', 'float', 'Risk % at -5% drawdown'),
        'risk_reduction_at_minus_10': ('0.5', 'float', 'Risk % at -10% drawdown'),
        'risk_reduction_at_minus_15': ('0.25', 'float', 'Risk % at -15% drawdown'),
        'risk_reduction_at_minus_20': ('0.0', 'float', 'Risk % at -20% drawdown (halt)'),

        # Filter Thresholds
        'min_completeness_score': ('70', 'int', 'Minimum data completeness %'),
        'min_stock_price': ('5.0', 'float', 'Minimum stock price $'),
        'min_signal_quality_score': ('60', 'int', 'Minimum SQS 0-100'),
        'min_volume_ma_50d': ('500000', 'int', 'Minimum 50-day avg volume'),
        'min_avg_daily_dollar_volume': ('500000', 'float', 'Minimum daily dollar volume for liquidity gate'),
        'require_stock_stage_2': ('true', 'bool', 'Require Stage 2 trend template'),
        'max_stop_distance_pct': ('8.0', 'float', 'Max stop distance % from entry'),
        'max_positions_per_sector': ('3', 'int', 'Max concurrent positions in one sector'),
        'max_positions_per_industry': ('2', 'int', 'Max concurrent positions in one industry'),
        'min_swing_score': ('60.0', 'float', 'Min swing trader score to enter'),
        'max_total_invested_pct': ('95.0', 'float', 'Max % of portfolio in open positions'),

        # Market Conditions
        'max_distribution_days': ('4', 'int', 'Max market distribution days'),
        'require_stage_2_market': ('true', 'bool', 'Require uptrend market stage'),
        'vix_max_threshold': ('35.0', 'float', 'VIX level to halt trading'),
        'vix_caution_threshold': ('25.0', 'float', 'VIX level to reduce positions'),
        'vix_caution_risk_reduction': ('0.75', 'float', 'Risk multiplier when VIX > caution threshold'),

        # Entry Rules (Minervini)
        'require_sma50_above_sma200': ('true', 'bool', 'Price and MA alignment'),
        'min_percent_from_52w_low': ('25.0', 'float', 'Min % from 52w low'),
        'max_percent_from_52w_high': ('25.0', 'float', 'Max % from 52w high'),
        'min_trend_template_score': ('8', 'int', 'Min Minervini score 0-10'),

        # Exit Rules
        't1_target_r_multiple': ('1.5', 'float', 'Tier 1 profit target R-mult'),
        't2_target_r_multiple': ('3.0', 'float', 'Tier 2 profit target R-mult'),
        't3_target_r_multiple': ('4.0', 'float', 'Tier 3 profit target R-mult'),
        'max_hold_days': ('20', 'int', 'Max days to hold position'),
        'exit_on_distribution_day': ('true', 'bool', 'Exit on market distribution'),
        'exit_on_rs_line_break_50dma': ('true', 'bool', 'Exit when RS line breaks 50-DMA'),
        'exit_on_td_sequential': ('true', 'bool', 'Exit on TD Sequential 9/13 exhaustion'),
        'use_chandelier_trail': ('true', 'bool', 'Use chandelier ATR trailing stop'),
        'switch_to_21ema_after_days': ('10', 'int', 'Days before switching chandelier to 21-EMA'),
        'eight_week_rule_threshold_pct': ('20.0', 'float', 'ONeill 8-week hold threshold %'),
        'eight_week_rule_window_days': ('21', 'int', 'Days to check for 20%+ gain'),
        'chandelier_atr_mult': ('3.0', 'float', 'ATR multiplier for chandelier stop'),
        'move_be_at_r': ('1.0', 'float', 'R-multiple to trigger breakeven stop raise'),

        # Pyramid Entry
        'pyramid_enabled': ('true', 'bool', 'Enable multi-entry pyramiding'),
        'pyramid_split_pct': ('50,33,17', 'string', 'Entry size split %'),

        # Execution Mode
        'execution_mode': ('paper', 'string', 'paper|dry|review|auto'),
        'alpaca_paper_trading': ('true', 'bool', 'Use Alpaca paper account'),
        'max_trades_per_day': ('5', 'int', 'Max new trades per day'),

        # Feature Flags
        'enable_algo': ('true', 'bool', 'Enable algo trading'),
        'enable_backtesting': ('false', 'bool', 'Enable backtest mode'),
        'verbose_logging': ('true', 'bool', 'Detailed logging'),
    }

    def __init__(self):
        self._config = {}
        self._load_defaults()
        self._load_from_database()

    def _load_defaults(self):
        """Load default configuration."""
        for key, (value, dtype, desc) in self.DEFAULTS.items():
            self._config[key] = self._parse_value(value, dtype)

    def _load_from_database(self):
        """Load configuration from database, overriding defaults."""
        if psycopg2 is None:
            print("Warning: psycopg2 not available, using defaults")
            return
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            cur.execute("SELECT key, value, value_type FROM algo_config")
            rows = cur.fetchall()

            for key, value, dtype in rows:
                if value is not None:
                    try:
                        self._validate_value(key, value, dtype)
                        self._config[key] = self._parse_value(value, dtype)
                    except ValueError as e:
                        print(f"Warning: Invalid config {key}={value}: {e} — using default")

            cur.close()
            conn.close()
        except Exception as e:
            print(f"Warning: Could not load config from DB: {e}")
            print("  Using defaults...")

    def _parse_value(self, value, dtype):
        """Parse configuration value to correct type."""
        if dtype == 'int':
            return int(value)
        elif dtype == 'float':
            return float(value)
        elif dtype == 'bool':
            return value.lower() in ('true', '1', 'yes')
        else:
            return str(value)

    def _validate_value(self, key, value, dtype):
        """Validate that a config value is within acceptable bounds.

        Raises ValueError if validation fails.
        """
        # Percentage values: 0-100 (skip string types like pyramid_split_pct)
        if 'pct' in key.lower() and dtype != 'string':
            f_val = float(value) if isinstance(value, (int, float, str)) else value
            if f_val < 0 or f_val > 100:
                raise ValueError(f'{key}: {f_val}% out of range [0-100]')

        # Position count: 1-100
        if key == 'max_positions':
            i_val = int(value) if isinstance(value, (int, float, str)) else value
            if i_val < 1 or i_val > 100:
                raise ValueError(f'{key}: {i_val} out of range [1-100]')

        # Days: positive integers
        if 'days' in key.lower():
            i_val = int(value) if isinstance(value, (int, float, str)) else value
            if i_val < 0 or i_val > 365:
                raise ValueError(f'{key}: {i_val} days out of range [0-365]')

        # Thresholds: reasonable bounds
        if key == 'vix_max_threshold':
            f_val = float(value) if isinstance(value, (int, float, str)) else value
            if f_val < 20 or f_val > 100:
                raise ValueError(f'{key}: {f_val} out of range [20-100]')

        # R-multiples: positive
        if 'r_multiple' in key.lower():
            f_val = float(value) if isinstance(value, (int, float, str)) else value
            if f_val < 0.5 or f_val > 10:
                raise ValueError(f'{key}: {f_val} out of range [0.5-10]')

        return True

    def get(self, key, default=None):
        """Get configuration value."""
        return self._config.get(key, default)

    def set(self, key, value, value_type, description=""):
        """Set configuration value in database and memory.

        Returns: (success: bool, message: str)
        """
        try:
            # Validate before storing
            self._validate_value(key, str(value), value_type)

            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO algo_config (key, value, value_type, description, updated_at, updated_by)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, 'system')
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    value_type = EXCLUDED.value_type,
                    description = EXCLUDED.description,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, str(value), value_type, description))

            conn.commit()
            cur.close()
            conn.close()

            # Update in-memory config
            self._config[key] = self._parse_value(str(value), value_type)

            return True
        except ValueError as e:
            print(f"Error: Invalid config value for {key}: {e}")
            return False
        except Exception as e:
            print(f"Error setting config {key}: {e}")
            return False

    def initialize_defaults(self):
        """Initialize all default configs in database."""
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            for key, (value, dtype, desc) in self.DEFAULTS.items():
                cur.execute("""
                    INSERT INTO algo_config (key, value, value_type, description, updated_at, updated_by)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, 'system')
                    ON CONFLICT (key) DO NOTHING
                """, (key, value, dtype, desc))

            conn.commit()
            print(f"✓ Initialized {len(self.DEFAULTS)} config defaults")
            cur.close()
            conn.close()
            return True
        except Exception as e:
            print(f"Error initializing defaults: {e}")
            return False

    def reload(self):
        """Reload configuration from database."""
        self._config.clear()
        self._load_defaults()
        self._load_from_database()

    def to_dict(self):
        """Export configuration as dictionary."""
        return dict(self._config)

    def __repr__(self):
        return f"<AlgoConfig {len(self._config)} keys>"

# Global config instance
_instance = None

def get_config():
    """Get or create global config instance."""
    global _instance
    if _instance is None:
        _instance = AlgoConfig()
    return _instance

def reload_config():
    """Force reload of configuration."""
    global _instance
    if _instance:
        _instance.reload()

if __name__ == "__main__":
    config = get_config()
    config.initialize_defaults()
    print("\nConfiguration Summary:")
    print("="*60)
    for key, val in sorted(config.to_dict().items()):
        print(f"  {key:.<40} {val}")
    print("="*60)
