#!/usr/bin/env python3
"""
Algo Configuration System (Hot-Reload Enabled)

Centralized configuration from database. Changes take effect immediately without restart.
Supports: risk parameters, filter thresholds, execution modes, feature flags.
"""

import os
import time
import logging
import threading
from typing import Any
from config.credential_validator import assert_credentials
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)


def validate_environment():
    """Validate that all required environment variables are set."""
    try:
        assert_credentials(on_failure="warn")
    except Exception as e:
        logger.error(f"Credential validation failed: {e}")
        raise RuntimeError(f"Critical credential error: {e}")


try:
    validate_environment()
except Exception as e:
    logger.error(f"ERROR: Environment validation failed: {e}")
    raise


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
        'halt_drawdown_pct': ('20.0', 'float', 'Portfolio drawdown % to halt trading (CB1)'),
        'risk_reduction_at_minus_5': ('0.75', 'float', 'Risk % at -5% drawdown'),
        'risk_reduction_at_minus_10': ('0.5', 'float', 'Risk % at -10% drawdown'),
        'risk_reduction_at_minus_15': ('0.25', 'float', 'Risk % at -15% drawdown'),
        'risk_reduction_at_minus_20': ('0.0', 'float', 'Risk % at -20% drawdown (halt)'),

        # Filter Thresholds
        'min_completeness_score': ('70', 'int', 'Minimum data completeness % (Minervini standard)'),
        'min_stock_price': ('5.0', 'float', 'Minimum stock price $'),
        'min_signal_quality_score': ('60', 'int', 'Minimum SQS 0-100 (signal quality gate)'),
        'min_volume_ma_50d': ('300000', 'int', 'Minimum 50-day avg volume'),
        'min_avg_daily_dollar_volume': ('500000', 'float', 'Minimum daily dollar volume for liquidity gate'),
        'require_stock_stage_2': ('true', 'bool', 'Require Stage 2 trend template'),
        'max_stop_distance_pct': ('12.0', 'float', 'Max stop distance % from entry'),
        'max_positions_per_sector': ('10', 'int', 'Max concurrent positions in one sector'),
        'max_positions_per_industry': ('8', 'int', 'Max concurrent positions in one industry'),
        'min_swing_score': ('55.0', 'float', 'Min swing trader score to enter (regime manager may raise this)'),
        'min_swing_grade': ('', 'string', 'Min swing grade override (empty=use exposure tier default; set to F for testing to bypass grade gate)'),
        'max_total_invested_pct': ('95.0', 'float', 'Max % of portfolio in open positions'),

        # Market Conditions
        'max_distribution_days': ('4', 'int', 'Max market distribution days'),
        'require_stage_2_market': ('false', 'bool', 'Require market Stage 2 at Tier 2 (disabled: CB6 blocks Stage 4; per-stock weinstein_stage=2 check and exposure policy manage regime risk)'),
        'vix_max_threshold': ('35.0', 'float', 'VIX level to halt trading'),
        'vix_alert_threshold': ('30.0', 'float', 'VIX level to trigger RED alert (dashboard display)'),
        'vix_caution_threshold': ('25.0', 'float', 'VIX level to reduce positions'),
        'vix_caution_risk_reduction': ('0.75', 'float', 'Risk multiplier when VIX > caution threshold'),
        'put_call_bullish_threshold': ('0.8', 'float', 'Put/Call ratio bullish threshold (<= for bullish)'),
        'put_call_fearful_threshold': ('1.0', 'float', 'Put/Call ratio fearful threshold (>= for fearful)'),
        'upvol_good_threshold': ('60.0', 'float', 'Up volume % threshold for good market (>= for GREEN)'),
        'upvol_caution_threshold': ('50.0', 'float', 'Up volume % threshold for caution (>= for YELLOW)'),
        'breadth_good_threshold': ('50', 'int', 'NH-NL difference threshold for good breadth (>= for GREEN)'),
        'breadth_caution_threshold': ('0', 'int', 'NH-NL difference threshold for caution (>= for YELLOW)'),
        'yield_curve_good_threshold': ('0.5', 'float', 'Yield curve slope for bullish signal (>= for GREEN)'),
        'beta_warning_threshold': ('1.2', 'float', 'Portfolio beta threshold for caution (>= for WARNING)'),
        'beta_caution_threshold': ('0.8', 'float', 'Portfolio beta threshold for bullish (>= for YELLOW)'),

        # Entry Rules (Minervini)
        'require_sma50_above_sma200': ('true', 'bool', 'Price and MA alignment'),
        'min_percent_from_52w_low': ('0.0', 'float', 'Min % from 52w low (Minervini standard)'),
        'max_percent_from_52w_high': ('25.0', 'float', 'Max % from 52w high'),
        'min_trend_template_score': ('6', 'int', 'Min Minervini score 0-8 (score 6 allows consolidating bases through; migration-006 lowered from 7)'),

        # Entry Quality Gates (Sprint 2)
        'max_signal_age_days': ('3', 'int', 'Reject BUY signals older than N days'),
        'min_close_quality_pct': ('40.0', 'float', 'Close must be in upper N% of range'),
        'min_breakout_volume_ratio': ('1.25', 'float', 'Volume must be N x 50-day average'),
        'require_weekly_stage_2': ('false', 'bool', 'Require weekly chart Stage 2'),
        'min_rs_line_slope_days': ('10', 'int', 'Days for RS line slope check'),
        'max_rs_pct_from_60d_high': ('15.0', 'float', 'Max % RS-line below 60d high (Minervini strict = 5%)'),
        'rs_slope_gate_enabled': ('false', 'bool', 'Hard-gate T3 on RS line trending up (false=warn-only; consolidating bases show flat RS by design)'),
        'volume_decay_gate_enabled': ('false', 'bool', 'Hard-gate T3 on volume decay into breakout (false=warn-only; accumulation naturally shows drying volume)'),

        # Exit Rules
        'require_target_pullback': ('false', 'bool', 'Require 2%+ pullback before partial profit exits at T1/T2 (false = exit immediately at target)'),
        't1_target_r_multiple': ('1.5', 'float', 'Tier 1 profit target R-mult'),
        't2_target_r_multiple': ('3.0', 'float', 'Tier 2 profit target R-mult'),
        't3_target_r_multiple': ('4.0', 'float', 'Tier 3 profit target R-mult'),

        # Imported Position Defaults (when ATR calculation fails)
        'imported_position_default_stop_loss_pct': ('5.0', 'float', 'Default stop loss % for imported positions'),
        'imported_position_default_target_1_pct': ('5.0', 'float', 'Default target 1 % for imported positions'),
        'imported_position_default_target_2_pct': ('10.0', 'float', 'Default target 2 % for imported positions'),
        'imported_position_default_target_3_pct': ('15.0', 'float', 'Default target 3 % for imported positions'),
        'min_hold_days': ('1', 'int', 'Minimum days to hold'),
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

        # Pyramid Entry (Sprint 3)
        'pyramid_enabled': ('true', 'bool', 'Enable multi-entry pyramiding'),
        'pyramid_split_pct': ('50,33,17', 'string', 'Entry size split %'),
        'pyramid_add_1_gain_pct': ('2.0', 'float', 'Gain % to trigger Add #1'),
        'pyramid_add_2_gain_pct': ('3.0', 'float', 'Additional gain % to trigger Add #2'),

        # Drawdown Re-engagement (Sprint 3)
        're_engage_recovery_pct': ('8.0', 'float', '% recovery from peak to resume trading'),
        're_engage_min_days': ('5', 'int', 'Min days after halt before re-engagement'),
        'require_ftd_to_re_engage': ('true', 'bool', 'Require Follow-Through Day signal'),

        # Circuit Breaker Thresholds (CB)
        'max_daily_loss_pct': ('2.0', 'float', 'Max daily loss % before halt'),
        'max_consecutive_losses': ('3', 'int', 'Max consecutive losing trades'),
        'min_win_rate_pct': ('40.0', 'float', 'Min win rate % to trade'),
        'max_total_risk_pct': ('4.0', 'float', 'Max total open risk %'),
        'max_weekly_loss_pct': ('5.0', 'float', 'Max weekly loss % before halt'),
        'max_data_staleness_days': ('3', 'int', 'Max data age in days'),
        'daily_profit_cap_pct': ('2.0', 'float', 'Daily profit cap %'),
        'sector_drawdown_halt_pct': ('-12.0', 'float', 'Sector drawdown % to halt trading'),

        # Position Monitoring & Re-entry
        'position_halt_flag_count': ('2', 'int', 'Flags to propose early exit'),
        'max_reentries_per_name': ('2', 'int', 'Max times to re-enter same symbol'),
        'min_days_before_reentry_same_symbol': ('5', 'int', 'Days to wait before re-entering symbol'),

        # Economic Calendar
        'halt_entries_before_major_release_minutes': ('60', 'int', 'Halt entries N minutes before major release'),

        # Earnings Blackout
        'earnings_blackout_days_before': ('7', 'int', 'Days before earnings to block entries'),
        'earnings_blackout_days_after': ('3', 'int', 'Days after earnings to block entries'),

        'min_price_history_days': ('200', 'int', 'Min trading days of price history (IPO age gate — Minervini avoids stocks <1yr post-IPO)'),
        'min_daily_volume_shares': ('500000', 'int', 'Minimum daily volume shares'),
        'max_spread_pct': ('0.5', 'float', 'Maximum bid-ask spread %'),
        'min_market_cap_millions': ('300.0', 'float', 'Minimum market cap $M'),
        'min_float_millions': ('50.0', 'float', 'Minimum float shares $M'),
        'max_short_interest_pct': ('30.0', 'float', 'Maximum short interest %'),

        # Advanced Filters
        'block_days_before_earnings': ('5', 'int', 'Block entries N days before earnings'),
        'max_extension_above_50ma_pct': ('15.0', 'float', 'Max extension above 50-DMA %'),
        'strong_sector_top_n': ('5', 'int', 'Top N sectors count as strong'),
        'require_strong_sector': ('false', 'bool', 'Require market sector to be strong before entering'),
        'min_adv_shares': ('50000', 'int', 'Minimum average daily volume (shares)'),
        'min_adv_dollars': ('500000', 'float', 'Minimum average daily dollar volume'),
        'min_order_size_dollars': ('100.0', 'float', 'Minimum order size in dollars'),
        'max_pyramid_adds': ('3', 'int', 'Maximum number of additional pyramid entries'),
        'phase1_min_coverage_pct': ('75', 'int', 'Phase 1: Minimum data coverage %'),
        'phase1_min_symbol_count': ('8000', 'int', 'Phase 1: Minimum symbol count for healthy coverage'),

        # Swing Trader Score Weights (Minervini Research-Weighted Composite)
        'swing_weight_setup': ('25', 'int', 'Swing score: Setup quality weight %'),
        'swing_weight_trend': ('20', 'int', 'Swing score: Trend quality weight %'),
        'swing_weight_momentum': ('20', 'int', 'Swing score: Momentum/RS weight %'),
        'swing_weight_volume': ('12', 'int', 'Swing score: Volume weight %'),
        'swing_weight_fundamentals': ('10', 'int', 'Swing score: Fundamentals weight %'),
        'swing_weight_sector': ('8', 'int', 'Swing score: Sector/industry weight %'),
        'swing_weight_multi_timeframe': ('5', 'int', 'Swing score: Multi-timeframe weight %'),
        'swing_min_trend_score': ('5', 'int', 'Swing score: Minimum Minervini trend score 0-8'),
        'swing_min_industry_rank': ('100', 'int', 'Swing score: Industry rank threshold (<=)'),
        'swing_days_to_earnings_block': ('5', 'int', 'Swing score: Block entries N days to earnings'),
        'swing_grade_threshold_aplus': ('85', 'int', 'Swing score: A+ grade threshold (score >= this value)'),
        'swing_grade_threshold_a': ('75', 'int', 'Swing score: A grade threshold (score >= this value)'),
        'swing_grade_threshold_b': ('65', 'int', 'Swing score: B grade threshold (score >= this value)'),
        'swing_grade_threshold_c': ('55', 'int', 'Swing score: C grade threshold (score >= this value)'),
        'swing_grade_threshold_d': ('45', 'int', 'Swing score: D grade threshold (score >= this value)'),
        'advanced_filters_grade_threshold_aplus': ('90', 'int', 'Advanced filters: A+ grade threshold (score >= this value)'),
        'advanced_filters_grade_threshold_a': ('80', 'int', 'Advanced filters: A grade threshold (score >= this value)'),
        'advanced_filters_grade_threshold_b': ('70', 'int', 'Advanced filters: B grade threshold (score >= this value)'),
        'advanced_filters_grade_threshold_c': ('60', 'int', 'Advanced filters: C grade threshold (score >= this value)'),
        'advanced_filters_grade_threshold_d': ('50', 'int', 'Advanced filters: D grade threshold (score >= this value)'),

        # Risk Metrics Calculation (M3 - Risk Thresholds)
        'var_percentile': ('5', 'int', 'Percentile for VaR calculation (5 = 95% confidence, measures 5th percentile loss)'),
        'cvar_percentile': ('5', 'int', 'Percentile for CVaR calculation (5 = worst 5% of days)'),
        'stressed_var_percentile': ('10', 'int', 'Percentile for stressed VaR (10 = worst 10% of days)'),
        'dashboard_grade_threshold_a': ('80', 'int', 'Dashboard signals: A grade threshold (score >= this value)'),
        'dashboard_grade_threshold_b': ('60', 'int', 'Dashboard signals: B grade threshold (score >= this value)'),
        'dashboard_grade_threshold_c': ('40', 'int', 'Dashboard signals: C grade threshold (score >= this value)'),

        # Execution Mode
        'execution_mode': ('auto', 'string', 'paper|dry|review|auto'),
        'alpaca_paper_trading': ('false', 'bool', 'Use Alpaca paper account'),
        'max_trades_per_day': ('5', 'int', 'Max new trades per day'),
        'default_portfolio_value': ('100000.0', 'float', 'Bootstrap portfolio value when Alpaca unreachable and no snapshot (Alpaca paper starts at $100k)'),

        # Feature Flags
        'enable_algo': ('true', 'bool', 'Enable algo trading'),
        'enable_backtesting': ('false', 'bool', 'Enable backtest mode'),
        'verbose_logging': ('true', 'bool', 'Detailed logging'),

        # Network Configuration
        'api_request_timeout_seconds': ('5', 'int', 'HTTP request timeout (seconds) for Alpaca/FRED/market data APIs'),
        'db_connection_timeout_seconds': ('15', 'int', 'Database connection timeout (seconds) — RDS Proxy adds latency'),

        # Failsafe Configuration
        'failsafe_ecs_timeout_sec': ('180', 'int', 'Max seconds to wait for ECS task to reach RUNNING state (Fargate provisioning under load: 45-150s)'),
        'failsafe_grace_period_minutes': ('240', 'int', 'Grace period before triggering second failsafe (min). Morning window 2-9:30AM=450min; expected load ~285min; allows 2:00+240m=6:00 expiry, second loader 6:00+285m≈11:30am (acceptable). Must be <390 (450-60 Phase 2-7 buffer). Too long: no retry time. Too short: false positives if load is slow.'),
    }

    def __init__(self):
        import time
        t0 = time.time()
        logger.info("[AlgoConfig] __init__ starting")
        self._config = {}
        self._load_defaults()
        t1 = time.time()
        logger.info(f"[AlgoConfig] defaults loaded in {t1-t0:.2f}s")
        self._load_from_database()
        t2 = time.time()
        logger.info(f"[AlgoConfig] database loaded in {t2-t1:.2f}s, total {t2-t0:.2f}s")

    def _load_defaults(self):
        """Load default configuration."""
        for key, (value, dtype, desc) in self.DEFAULTS.items():
            self._config[key] = self._parse_value(value, dtype)

    def _load_from_database(self):
        """Load configuration from database, overriding defaults."""
        t0 = time.time()
        logger.info("[AlgoConfig] _load_from_database() starting")
        try:
            t_conn_start = time.time()
            with DatabaseContext('read', timeout=15) as cur:
                t_conn_done = time.time()
                logger.info(f"[AlgoConfig] database connection took {t_conn_done-t_conn_start:.2f}s")

                cur.execute("SELECT key, value, value_type FROM algo_config")
                rows = cur.fetchall()
                logger.info(f"[AlgoConfig] loaded {len(rows)} config rows from DB")

                for key, value, dtype in rows:
                    if value is not None:
                        try:
                            self._validate_value(key, value, dtype)
                            self._config[key] = self._parse_value(value, dtype)
                        except ValueError as e:
                            logger.warning(f"Warning: Invalid config {key}={value}: {e} — using default")
                self._validate_r_multiple_ordering()
                t_end = time.time()
                logger.info(f"[AlgoConfig] _load_from_database() completed in {t_end-t0:.2f}s")
        except Exception as e:
            logger.warning(f"Warning: Could not load config from DB: {e}")
            logger.info("  Using defaults...")

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
        # Percentage values: 0-100 (skip string types like pyramid_split_pct, drawdown/halt thresholds)
        is_drawdown_or_halt = 'drawdown' in key.lower() or 'halt' in key.lower()
        if 'pct' in key.lower() and dtype != 'string' and not is_drawdown_or_halt:
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

        # R-multiples: positive, reasonable range
        if 'r_multiple' in key.lower():
            f_val = float(value) if isinstance(value, (int, float, str)) else value
            if f_val < 0.5 or f_val > 10:
                raise ValueError(f'{key}: {f_val} out of range [0.5-10]')

        # Pyramid split: must be comma-separated numbers summing to 100
        if key == 'pyramid_split_pct' and dtype == 'string':
            try:
                parts = [float(p.strip()) for p in str(value).split(',')]
                total = sum(parts)
                if abs(total - 100.0) > 1.0:
                    raise ValueError(f'{key}: parts sum to {total:.1f}, must equal 100')
            except ValueError as e:
                if 'sum' in str(e) or 'equal' in str(e):
                    raise
                raise ValueError(f'{key}: expected comma-separated numbers like "50,33,17"')

        return True

    def _validate_r_multiple_ordering(self):
        """Verify t1 < t2 < t3 R-multiple targets (called after full config load)."""
        try:
            t1 = float(self._config.get('t1_target_r_multiple', 1.5))
            t2 = float(self._config.get('t2_target_r_multiple', 3.0))
            t3 = float(self._config.get('t3_target_r_multiple', 4.0))
            if not (t1 < t2 < t3):
                logging.getLogger(__name__).warning(
                    f'Config: R-multiple targets not ordered (t1={t1} t2={t2} t3={t3}). '
                    f'Expected t1 < t2 < t3.'
                )
        except (TypeError, ValueError):
            pass

    def get(self, key, default=None):
        """Get configuration value with validation of hardcoded defaults.

        WARNING: Providing a hardcoded default parameter can hide config load failures.
        Ensures the default matches DEFAULTS to detect misalignment in code.
        """
        if default is not None and key in self.DEFAULTS:
            default_value, _, _ = self.DEFAULTS[key]
            parsed_default = self._parse_value(default_value, self.DEFAULTS[key][1])
            if parsed_default != default:
                logger.warning(
                    f"[CONFIG] Default mismatch for {key!r}: "
                    f"code has {default!r} but DEFAULTS has {parsed_default!r}"
                )
        return self._config.get(key, default)

    def override(self, key: str, value: Any) -> None:
        """Apply an in-memory-only override (env var wins over DB). No DB write, no audit.

        Used for command-line args and event-level test overrides that should not persist.
        """
        if key not in self.DEFAULTS:
            logger.warning(f"[CONFIG OVERRIDE] Unknown key {key!r} — ignored")
            return
        _, dtype, _ = self.DEFAULTS[key]
        try:
            self._validate_value(key, str(value), dtype)
            self._config[key] = self._parse_value(str(value), dtype)
            logger.info(f"[CONFIG OVERRIDE] {key} = {value} ({dtype})")
        except ValueError as e:
            logger.error(f"[CONFIG OVERRIDE] Invalid value for {key}: {e} — ignored")

    def set(self, key, value, value_type, description="", changed_by="system"):
        """Set configuration value in database, memory, and audit log.

        Args:
            key: Configuration key
            value: New value
            value_type: Type ('int', 'float', 'bool', 'string')
            description: Description (only used for new keys)
            changed_by: Actor making the change (for audit trail)

        Returns: bool (success)
        """
        try:
            self._validate_value(key, str(value), value_type)

            with DatabaseContext('write') as cur:
                # Capture old value for audit trail
                cur.execute("SELECT value FROM algo_config WHERE key = %s", (key,))
                row = cur.fetchone()
                old_value = row[0] if row else None

                # Upsert config value
                cur.execute("""
                    INSERT INTO algo_config (key, value, value_type, description, updated_at, updated_by)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        value_type = EXCLUDED.value_type,
                        description = EXCLUDED.description,
                        updated_at = CURRENT_TIMESTAMP,
                        updated_by = EXCLUDED.updated_by
                """, (key, str(value), value_type, description, changed_by))

                # Write audit trail
                cur.execute("""
                    INSERT INTO algo_config_audit (config_key, old_value, new_value, changed_by, changed_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                """, (key, old_value, str(value), changed_by))

            self._config[key] = self._parse_value(str(value), value_type)
            logger.info(f"[CONFIG SET] {key} = {value} (was {old_value}), actor={changed_by}")
            return True
        except ValueError as e:
            logger.error(f"Error: Invalid config value for {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error setting config {key}: {e}")
            return False

    def initialize_defaults(self):
        """Initialize all default configs in database."""
        try:
            with DatabaseContext('write') as cur:
                for key, (value, dtype, desc) in self.DEFAULTS.items():
                    cur.execute("""
                        INSERT INTO algo_config (key, value, value_type, description, updated_at, updated_by)
                        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, 'system')
                        ON CONFLICT (key) DO NOTHING
                    """, (key, value, dtype, desc))
            logger.info(f"[OK] Initialized {len(self.DEFAULTS)} config defaults")
            return True
        except Exception as e:
            logger.error(f"Error initializing defaults: {e}")
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


# Global config instance (thread-safe)
_instance = None
_instance_lock = threading.Lock()


def get_config():
    """Get or create global config instance (thread-safe).

    Uses double-checked locking to prevent race conditions during initialization.
    """
    global _instance
    if _instance is None:
        with _instance_lock:
            # Double-check pattern to avoid race conditions
            if _instance is None:
                _instance = AlgoConfig()
    return _instance


def reset_config() -> None:
    """Reset singleton — call at Lambda invocation start so config is fresh each run.

    This ensures warm Lambda invocations reload config from the DB, picking up
    any changes made between invocations (e.g., lowering a risk threshold).
    Thread-safe reset using lock.
    """
    global _instance
    with _instance_lock:
        _instance = None
    logger.info("[AlgoConfig] Singleton reset — will reload from DB on next get_config() call")


def get_api_timeout() -> int:
    """Get API request timeout in seconds.

    Checks (in order): API_TIMEOUT env var, algo_config DB, default 5s.
    """
    env_val = os.getenv('API_TIMEOUT')
    if env_val:
        return int(env_val)
    return get_config().get('api_request_timeout_seconds', 5)


def get_db_timeout() -> int:
    """Get database connection timeout in seconds.

    Checks (in order): DB_TIMEOUT_SECONDS env var, algo_config DB, default 15s.
    """
    env_val = os.getenv('DB_TIMEOUT_SECONDS')
    if env_val:
        return int(env_val)
    return get_config().get('db_connection_timeout_seconds', 15)


def get_market_data_timeout() -> int:
    """Get market data API timeout in seconds."""
    return int(os.getenv('MARKET_DATA_TIMEOUT', '10'))


def get_alpaca_timeout() -> int:
    """Get Alpaca API timeout in seconds."""
    return int(os.getenv('ALPACA_TIMEOUT', '5'))


def get_webhook_timeout() -> int:
    """Get webhook timeout in seconds."""
    return int(os.getenv('WEBHOOK_TIMEOUT', '5'))


def get_subprocess_timeout() -> int:
    """Get subprocess timeout in seconds."""
    return int(os.getenv('SUBPROCESS_TIMEOUT', '5'))


def get_alpaca_base_url() -> str:
    """Get Alpaca API base URL from unified config.

    Delegates to config/alpaca_config.py (single source of truth).
    """
    from config.alpaca_config import get_alpaca_base_url as get_unified_url
    return get_unified_url()


if __name__ == "__main__":
    config = get_config()
    config.initialize_defaults()
    logger.info("\nConfiguration Summary:")
    logger.info("=" * 60)
    for key, val in sorted(config.to_dict().items()):
        logger.info(f"  {key:.<40} {val}")
    logger.info("=" * 60)
