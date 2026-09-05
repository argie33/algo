#!/usr/bin/env python3
"""
Algo Configuration System (Hot-Reload Enabled)

Centralized configuration from database. Changes take effect immediately without restart.
Supports: risk parameters, filter thresholds, execution modes, feature flags.
"""

import logging
import threading
import time
from typing import Any, cast

import psycopg2

from algo.config.credential_validator import assert_credentials
from algo.infrastructure.config.config_defaults_1 import CONFIG_DEFAULTS_1
from algo.infrastructure.config.config_defaults_2 import CONFIG_DEFAULTS_2
from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


def validate_environment() -> None:
    """Validate that all required environment variables are set at startup.

    Fails FAST with RuntimeError if any critical credential is missing.
    This prevents the app from starting and trading with incomplete credentials.
    """
    try:
        assert_credentials(on_failure="raise")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Credential validation failed: {e}")
        raise RuntimeError(f"Critical credential error: {e}") from e


# DEFERRED: Validate environment only when actually connecting to RDS/AWS,
# not at module import time. This allows loaders to run in dev environments
# without full production credentials configured locally.
# validate_environment() is called at connection time in db/connection.py


class AlgoConfig:
    """Configuration manager with hot-reload from database.

    CONFIGURATION SOURCE PRECEDENCE (Priority Order - Highest to Lowest)
    ====================================================================

    All configuration values are resolved in this exact order:

    TIER 1 (Highest Priority): DATABASE
    ├─ Source: algo_config table (PostgreSQL)
    ├─ Hotreloadable: YES - changes apply immediately without Lambda redeploy
    ├─ Method: get_field(key) queries latest value from algo_config
    ├─ Example: UPDATE algo_config SET value='60' WHERE key='min_signal_quality_score'
    ├─ Tracking: _sources[key] = "database"
    └─ Use Case: Production hotfix (e.g., raise risk gate without deploying Lambda)

    TIER 2 (Medium Priority): OVERRIDE
    ├─ Source: Programmatic overrides (testing, manual intervention)
    ├─ Hotreloadable: YES (in-memory, clears on Lambda cold start)
    ├─ Method: set_override(key, value) or direct dict manipulation
    ├─ Example: AlgoConfig().set_override("algo_enabled", False)
    ├─ Tracking: _sources[key] = "override"
    └─ Use Case: Temporary disable during incident response

    TIER 3 (Lowest Priority): DEFAULTS
    ├─ Source: AlgoConfig.DEFAULTS dict (defined in this file)
    ├─ Hotreloadable: NO - requires code push + Lambda redeploy
    ├─ Method: Direct access to DEFAULTS dict
    ├─ Example: AlgoConfig.DEFAULTS["max_positions"][0]
    ├─ Tracking: _sources[key] = "default_fallback"
    └─ Use Case: Initialization when database value not yet set

    CRITICAL CONSTRAINT:
    ====================
    Environment variables are NOT used for dynamic configuration.
    All configuration that needs to be hotreloadable must go in the algo_config table.
    Environment variables are reserved for deployment settings (ORCHESTRATOR_EXECUTION_MODE, etc.)

    Examples of what goes WHERE:
    ├─ Database: min_signal_quality_score, max_positions, base_risk_pct (frequently tuned)
    ├─ Override: algo_enabled flag during incident response
    ├─ Defaults: All filter thresholds, risk parameters (baseline)
    └─ Environment: ORCHESTRATOR_EXECUTION_MODE, ORCHESTRATOR_DRY_RUN, AWS_REGION

    Implementation Note:
    ====================
    The _sources dict tracks which tier each value came from. This enables:
    1. Debugging: "Is this value from database or default?"
    2. Monitoring: "Which configs are overridden?"
    3. Auditing: "What was the effective config at time T?"
    """

    # Import validation schema from separate module (extracted for maintainability)
    from ..config_schema import VALIDATION_SCHEMA

    # Default configuration values
    # Format: (value, type, description, category) - category enables metadata-driven grouping
    DEFAULTS: dict[str, tuple[Any, ...]] = {**CONFIG_DEFAULTS_1, **CONFIG_DEFAULTS_2}

    def __init__(self) -> None:
        import os
        import time

        t0 = time.time()
        logger.info("[AlgoConfig] __init__ starting")
        self._config: dict[str, Any] = {}
        self._sources: dict[str, str] = {}  # Track source of each config value: "default" or "database"
        self._validate_schema_consistency()
        self._load_defaults()
        t1 = time.time()
        logger.info(f"[AlgoConfig] defaults loaded in {t1 - t0:.2f}s")

        # Load from database, but make it optional for paper trading mode
        is_paper_trading = os.getenv("ALPACA_PAPER_TRADING", "true").strip().lower() != "false"
        try:
            self._load_from_database()
            t2 = time.time()
            logger.info(f"[AlgoConfig] database loaded in {t2 - t1:.2f}s, total {t2 - t0:.2f}s")
            # CRITICAL: Detect if config database load failed (all values still at defaults)
            self._detect_config_db_failure()
        except Exception as e:
            if is_paper_trading:
                # Paper trading: database failure is not blocking, use defaults
                logger.warning(
                    f"[AlgoConfig] Database loading failed in paper mode (non-blocking): {e}. "
                    f"Using default configuration values."
                )
                t2 = time.time()
                logger.info(f"[AlgoConfig] Using defaults due to DB unavailability, total {t2 - t0:.2f}s")
            else:
                # Live trading: database failure is blocking (fail-fast)
                logger.critical(f"[AlgoConfig] Database loading FAILED in live mode (blocking): {e}")
                raise RuntimeError(
                    f"[CRITICAL] Configuration database unavailable in LIVE TRADING MODE. "
                    f"Cannot proceed without valid configuration. "
                    f"Ensure database is accessible and algo_config table is populated. "
                    f"Root cause: {e}"
                ) from e

        self._validate_critical_thresholds()
        t_crit = time.time()
        logger.info(f"[AlgoConfig] critical threshold validation completed in {t_crit - t2:.2f}s")
        self._validate_config_interdependencies()
        t3 = time.time()
        logger.info(f"[AlgoConfig] interdependency validation completed in {t3 - t_crit:.2f}s")
        self._audit_config_sources()

    @property
    def risk(self) -> Any:
        if not hasattr(self, "_risk_config"):
            from .risk_config import RiskConfig

            self._risk_config = RiskConfig(self)
        return self._risk_config

    @property
    def circuit_breaker(self) -> Any:
        if not hasattr(self, "_circuit_breaker_config"):
            from .circuit_breaker_config import CircuitBreakerConfig

            self._circuit_breaker_config = CircuitBreakerConfig(self)
        return self._circuit_breaker_config

    @property
    def data_patrol(self) -> Any:
        if not hasattr(self, "_data_patrol_config"):
            from .data_patrol_config import DataPatrolConfig

            self._data_patrol_config = DataPatrolConfig(self)
        return self._data_patrol_config

    @property
    def timeout(self) -> Any:
        if not hasattr(self, "_timeout_config"):
            from .timeout_config import TimeoutConfig

            self._timeout_config = TimeoutConfig(self)
        return self._timeout_config

    @property
    def execution(self) -> Any:
        if not hasattr(self, "_execution_config"):
            from .execution_config import ExecutionConfig

            self._execution_config = ExecutionConfig(self)
        return self._execution_config

    @property
    def economic_stress(self) -> Any:
        if not hasattr(self, "_economic_stress_config"):
            from .economic_stress_config import EconomicStressConfig

            self._economic_stress_config = EconomicStressConfig(self)
        return self._economic_stress_config

    @property
    def trading(self) -> Any:
        if not hasattr(self, "_trading_config"):
            from .trading_config import TradingConfig

            self._trading_config = TradingConfig(self)
        return self._trading_config

    def _validate_schema_consistency(self) -> None:
        """Verify that VALIDATION_SCHEMA and DEFAULTS are in sync.

        Every key in DEFAULTS must be in VALIDATION_SCHEMA (with type consistency).
        Every critical key in VALIDATION_SCHEMA must be in DEFAULTS.
        Raises RuntimeError if inconsistencies are found.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Check that all DEFAULTS keys have corresponding VALIDATION_SCHEMA entries
        for key, default_entry in self.DEFAULTS.items():
            # Handle both 3-tuple (value, type, desc) and 4-tuple (value, type, desc, category)
            default_type = default_entry[1] if len(default_entry) >= 2 else str
            if key not in self.VALIDATION_SCHEMA:
                errors.append(f"  {key}: in DEFAULTS but NOT in VALIDATION_SCHEMA (type: {default_type})")
            else:
                schema_type, _, _, _, _ = self.VALIDATION_SCHEMA[key]
                # Relaxed check: int/float can be interchanged in numeric contexts
                if default_type != schema_type:
                    if not ((default_type in ("int", "float")) and (schema_type in ("int", "float"))):
                        errors.append(
                            f"  {key}: type mismatch - DEFAULTS has {default_type} but SCHEMA has {schema_type}"
                        )

        # Check that all critical SCHEMA keys are in DEFAULTS
        for key, (_schema_type, _, _, is_critical, _) in self.VALIDATION_SCHEMA.items():
            if key not in self.DEFAULTS:
                if is_critical:
                    errors.append(f"  {key}: CRITICAL in SCHEMA but NOT in DEFAULTS (must have a safe default)")
                else:
                    warnings.append(f"  {key}: in SCHEMA but NOT in DEFAULTS (non-critical, will use schema default)")

        if errors:
            error_msg = (
                "FATAL: Configuration schema/defaults mismatch detected.\n"
                "This prevents proper validation of safety thresholds.\n\n"
                + "\n".join(errors)
                + "\n\nAction: Fix VALIDATION_SCHEMA and DEFAULTS to be consistent."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        if warnings:
            logger.warning("[AlgoConfig] Schema/defaults consistency warnings:\n" + "\n".join(warnings))

    def _load_defaults(self) -> None:
        """Load default configuration."""
        for key, default_entry in self.DEFAULTS.items():
            # Handle both 3-tuple and 4-tuple formats
            value, dtype = default_entry[0], default_entry[1]
            self._config[key] = self._parse_value(value, dtype)
            self._sources[key] = "default"

    def _load_from_database(self) -> None:
        """Load configuration from database, overriding defaults.

        If a critical safety threshold is invalid, rejects the value and uses the
        fail-closed default instead, then logs an alert for the admin to fix it.
        """
        t0 = time.time()
        logger.info("[AlgoConfig] _load_from_database() starting")
        try:
            t_conn_start = time.time()
            with DatabaseContext("read", timeout=15) as cur:
                t_conn_done = time.time()
                logger.info(f"[AlgoConfig] database connection took {t_conn_done - t_conn_start:.2f}s")

                # CRITICAL FIX: Use value_type column (renamed from data_type in schema)
                # Fallback for old schemas that lack value_type column entirely
                try:
                    cur.execute("SELECT key, value, value_type FROM algo_config")
                except psycopg2.ProgrammingError:
                    # value_type column doesn't exist in very old schemas - use fallback
                    # CRITICAL: Must rollback transaction before retrying (PostgreSQL aborts on failed queries)
                    cur.connection.rollback()
                    cur.execute("SELECT key, value, NULL::VARCHAR as value_type FROM algo_config")
                rows = cur.fetchall()
                logger.info(f"[AlgoConfig] loaded {len(rows)} config rows from DB")

                invalid_critical_values = []
                for row in rows:
                    # CRITICAL: Check for dict-like interface, not exact dict type.
                    # psycopg2.extras.DictRow is dict-like but not isinstance(dict).
                    # Fail if row lacks dictionary interface (would crash on row["key"] below).
                    if not hasattr(row, "__getitem__") or not hasattr(row, "get"):
                        raise TypeError(
                            f"Expected dict-like row from DictCursor, got {type(row).__name__}. "
                            f"This indicates cursor configuration mismatch. Check DatabaseContext cursor_factory."
                        )
                    key = row["key"]
                    value = row["value"]
                    dtype = row.get("value_type")
                    if value is not None:
                        try:
                            # Use value_type if set, otherwise normalize PostgreSQL type or infer from content
                            if dtype:
                                # Check if it looks like a schema type (int, float, bool, string) vs PostgreSQL type
                                if dtype in ("int", "float", "bool", "string"):
                                    normalized_dtype = dtype
                                else:
                                    # PostgreSQL type name - normalize it
                                    normalized_dtype = self._normalize_db_type(dtype)
                            else:
                                # value_type is NULL - infer from value content
                                normalized_dtype = self._infer_type_from_value(value)

                            self._validate_value(key, value, normalized_dtype)
                            self._config[key] = self._parse_value(value, normalized_dtype)
                            self._sources[key] = "database"
                        except ValueError as e:
                            # Check if this is a critical safety threshold
                            schema_info = self.VALIDATION_SCHEMA.get(key)
                            if schema_info and schema_info[3]:  # is_critical
                                # FAIL FAST: Critical safety thresholds must not fallback to defaults.
                                # If database value is corrupted, system should not start trading.
                                error_msg = (
                                    f"CRITICAL: Safety threshold '{key}' has invalid value in database. "
                                    f"Error: {e}\n"
                                    f"This is critical safety gate. NO trading without valid configuration.\n"
                                    f"Admin MUST restore a valid value to '{key}' in algo_config table.\n"
                                    f"Expected type: {schema_info[0]}, range: {schema_info[1]}"
                                )
                                logger.critical(error_msg)
                                invalid_critical_values.append(f"  {key}={value}: {e}")
                                # Re-raise as RuntimeError to force fatal failure during init
                                raise RuntimeError(error_msg) from e
                            else:
                                logger.warning(
                                    f"[AlgoConfig] NON-CRITICAL Invalid config {key}={value}: {e}. "
                                    f"This is not a safety gate, using default. "
                                    f"Consider fixing in database for consistency."
                                )
                                self._sources[key] = "default_fallback"

                if invalid_critical_values:
                    # This should never be reached since we raise above, but keep as safety net
                    logger.warning(
                        "[AlgoConfig] ALERT: Non-critical config values were invalid:\n"
                        + "\n".join(invalid_critical_values)
                    )

                self._validate_r_multiple_ordering()
                t_end = time.time()
                logger.info(f"[AlgoConfig] _load_from_database() completed in {t_end - t0:.2f}s")
        except ValueError as e:
            logger.error(f"Config validation error: {e}")
            raise
        except (
            psycopg2.DatabaseError,
            psycopg2.OperationalError,
            ConnectionError,
            Exception,
        ) as e:
            logger.error(f"CRITICAL: Failed to load config from database: {e}")
            raise RuntimeError(
                f"Config initialization failed: cannot load safety thresholds from database. "
                f"System will not trade with undefined safety configuration. Caused by: {e}"
            ) from e

    def _infer_type_from_value(self, value: Any) -> str:
        """Infer configuration value type from content when type is not specified.

        Heuristic: check content to determine if it's int, float, bool, or string.
        This handles cases where value_type in database is NULL.
        """
        if value is None:
            return "string"

        str_value = str(value).strip().lower()

        # Check for boolean
        if str_value in ("true", "false", "yes", "no", "1", "0"):
            return "bool"

        # Check for numeric types
        try:
            # Try int first
            int(str_value)
            return "int"
        except ValueError:
            try:
                # Try float
                float(str_value)
                return "float"
            except ValueError:
                # Default to string
                return "string"

    def _normalize_db_type(self, db_type: str | None) -> str:
        """Convert PostgreSQL type names to schema type names.

        Database stores PostgreSQL native types like 'integer', 'double precision', etc.
        Schema expects Python type names like 'int', 'float', 'bool', 'string'.
        """
        if db_type is None:
            return "string"

        db_type_lower = db_type.lower().strip()

        # Map PostgreSQL types to schema types
        type_mapping: dict[str, str] = {
            "integer": "int",
            "int": "int",
            "bigint": "int",
            "smallint": "int",
            "double precision": "float",
            "double": "float",
            "float": "float",
            "numeric": "float",
            "decimal": "float",
            "boolean": "bool",
            "bool": "bool",
            "text": "string",
            "varchar": "string",
            "string": "string",
            "character varying": "string",
        }

        return type_mapping.get(db_type_lower, "string")

    def _parse_value(self, value: Any, dtype: str) -> Any:
        if dtype == "int":
            return int(value)
        elif dtype == "float":
            return float(value)
        elif dtype == "bool":
            return str(value).lower() in ("true", "1", "yes")
        else:
            return str(value)

    def _validate_value(self, key: str, value: Any, dtype: str) -> bool:
        """Validate that a config value is within acceptable bounds using schema.

        If key is not in schema, performs backward-compatible basic validation.
        Raises ValueError if validation fails.
        """
        # Use validation schema if available; otherwise fall back to basic checks
        if key not in self.VALIDATION_SCHEMA:
            logger.warning(f"[CONFIG VALIDATE] Key {key!r} not in validation schema  - using basic checks")
            return True

        schema_type, min_val, max_val, is_critical, fail_closed = self.VALIDATION_SCHEMA[key]

        # Type mismatch check
        if dtype != schema_type:
            # For backward compatibility, allow int/float interchangeably in numeric contexts
            if not ((dtype in ("int", "float")) and (schema_type in ("int", "float"))):
                raise ValueError(f"{key}: type mismatch. Expected {schema_type}, got {dtype}")

        # Parse value for range checking (skip bool/string which have no min/max)
        if schema_type in ("int", "float"):
            try:
                f_val = float(value)
            except (ValueError, TypeError) as e:
                raise ValueError(f"{key}: Cannot parse {value!r} as numeric") from e

            # Critical safety gates: for critical params, check near-zero FIRST (highest priority)
            if is_critical and abs(f_val) < 0.001:
                # Include "below minimum" context if this also violates min bound
                if min_val is not None and f_val < min_val:
                    raise ValueError(
                        f"{key}: below minimum|CRITICAL SAFETY GATE - cannot be zero or near-zero "
                        f"(would disable safety protection). Min allowed: {min_val}. "
                        f"Reverting to safe default {fail_closed}."
                    )
                raise ValueError(
                    f"{key}: CRITICAL SAFETY GATE - cannot be zero or near-zero "
                    f"(would disable safety protection). Reverting to safe default {fail_closed}."
                )

            # Validate range if bounds are defined (for non-critical or non-near-zero values)
            if min_val is not None and f_val < min_val:
                raise ValueError(f"{key}: {f_val} is below minimum {min_val}")
            if max_val is not None and f_val > max_val:
                raise ValueError(f"{key}: {f_val} is above maximum {max_val}")

        return True

    def _validate_r_multiple_ordering(self) -> None:
        """Verify t1 < t2 < t3 R-multiple targets (called after full config load)."""
        try:
            # Fail-fast: R-multiples are critical and must be explicitly configured
            t1_val = self._config.get("t1_target_r_multiple")
            t2_val = self._config.get("t2_target_r_multiple")
            t3_val = self._config.get("t3_target_r_multiple")

            if t1_val is None or t2_val is None or t3_val is None:
                raise ValueError(
                    f"CRITICAL: R-multiple config missing. "
                    f"Required: t1_target_r_multiple, t2_target_r_multiple, t3_target_r_multiple. "
                    f"Found: t1={t1_val}, t2={t2_val}, t3={t3_val}. "
                    f"Cannot use defaults (1.5, 3.0, 4.0) - must be explicitly configured."
                )

            t1 = float(t1_val)
            t2 = float(t2_val)
            t3 = float(t3_val)
            if not (t1 < t2 < t3):
                raise ValueError(
                    f"R-multiple ordering broken: t1={t1} t2={t2} t3={t3}. Required: t1 < t2 < t3 for position sizing."
                )
        except (TypeError, ValueError) as e:
            logger.error(f"Config validation failed: {e}")
            raise

    def _detect_config_db_failure(self) -> None:
        """CRITICAL: Detect if config database failed silently.

        If ALL configuration values still at defaults (source='default'),
        this indicates the database load failed completely. Raise error instead
        of silently running with cached/old config.
        """
        if not self._sources:
            logger.warning("[AlgoConfig] No config sources tracked - unable to verify database load")
            return

        # Count how many configs came from database vs defaults
        db_sources = sum(1 for src in self._sources.values() if src == "database")
        default_sources = sum(1 for src in self._sources.values() if src == "default")
        total_sources = len(self._sources)

        logger.info(
            f"[AlgoConfig] Config load summary: {db_sources} from database, "
            f"{default_sources} defaults, total {total_sources}"
        )

        # CRITICAL: All config still at defaults = database load failed
        if db_sources == 0 and default_sources > 0:
            raise RuntimeError(
                f"[CONFIG CRITICAL] Database config load FAILED. "
                f"ALL {default_sources} configuration values are still at hardcoded defaults. "
                f"This indicates algo_config table is unreachable or empty. "
                f"Cannot proceed with trading using cached/default config. "
                f"Action: Verify database connectivity and algo_config table is properly populated."
            )

        # WARNING: Mostly defaults (>75% not loaded) indicates partial database failure
        if total_sources > 0 and (default_sources / total_sources) > 0.75:
            message = (
                f"[CONFIG WARNING] PARTIAL database load failure: {default_sources}/{total_sources} configs "
                f"still at defaults ({(default_sources / total_sources) * 100:.0f}%). "
                f"Database may be slow/degraded. Verify algo_config table has all required values."
            )
            logger.critical(message)
            # BUG FOUND 2026-09-01 (/goal session): unlike the full-failure case just above
            # (db_sources == 0), which raises and is fail-fast/blocking in live mode, this
            # partial-failure branch only ever logged - the same "computed but never delivered"
            # alert gap already found and fixed today in load_market_constituents.py and Phase
            # 9's risk-alert path. A degraded (not fully down) DB during live trading means the
            # system silently keeps running on mostly-HARDCODED-DEFAULT safety/position-sizing
            # thresholds - not the tuned production values - with nothing but a log line an
            # operator would have to be actively watching to catch. Alerting is best-effort here
            # (config loading itself must not fail because notify() failed), matching every
            # other notify()-wiring fix from today's sweep.
            try:
                from algo.reporting import notify

                notify(
                    severity="warning",
                    title="Partial Config Database Load Failure",
                    message=message,
                    details={"default_sources": default_sources, "total_sources": total_sources},
                )
            except (ValueError, TypeError, RuntimeError) as notify_err:
                logger.error(f"[AlgoConfig] Failed to send partial-database-load-failure alert: {notify_err}")

    def _validate_critical_thresholds(self) -> None:
        """Fail-fast validation: critical safety thresholds must be within safe ranges.

        Checks all keys marked as critical in VALIDATION_SCHEMA. Raises RuntimeError
        if any critical threshold is missing, zero, or out of valid range.
        """
        errors: list[str] = []
        warnings: list[str] = []

        for key, (
            _schema_type,
            min_val,
            max_val,
            is_critical,
            fail_closed,
        ) in self.VALIDATION_SCHEMA.items():
            if not is_critical:
                continue  # Skip non-critical params

            current_value = self._config.get(key)

            # Missing or None
            if current_value is None:
                errors.append(
                    f"  {key}: not configured (None). Safe default: {fail_closed}. Range: [{min_val}, {max_val}]"
                )
                continue

            # Convert to comparable type
            try:
                f_val = float(current_value)
            except (ValueError, TypeError):
                errors.append(f"  {key}: cannot parse value {current_value!r}. Safe default: {fail_closed}")
                continue

            # Zero/near-zero (disables safety gate)
            if abs(f_val) < 0.001:
                errors.append(
                    f"  {key} = {f_val}: ZERO or near-zero (disables safety gate). "
                    f"Safe default: {fail_closed}. Range: [{min_val}, {max_val}]"
                )
                continue

            # Out of range
            if min_val is not None and f_val < min_val:
                errors.append(f"  {key} = {f_val}: below minimum {min_val}. Safe default: {fail_closed}")
            if max_val is not None and f_val > max_val:
                errors.append(f"  {key} = {f_val}: above maximum {max_val}. Safe default: {fail_closed}")

        if errors:
            error_msg = (
                "SAFETY GATE FAILURE: Critical configuration thresholds are invalid.\n"
                "System will not trade with corrupt safety configuration.\n"
                "These thresholds prevent trading unsuitable stocks and during dangerous market conditions.\n\n"
                "Invalid thresholds:\n"
                + "\n".join(errors)
                + "\n\nAction: Restore valid thresholds in database before trading.\n"
                "Run: python migrations/runner.py up (migration-033) to restore safe defaults\n"
                "OR manually fix the database values per CLAUDE.md -> Trading Safety Configuration"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        if warnings:
            logger.warning("[AlgoConfig] Critical threshold warnings:\n" + "\n".join(warnings))

    def _validate_config_interdependencies(self) -> None:  # noqa: C901
        """Validate configuration interdependencies at startup.

        Checks for conflicting values that create impossible or dead-code scenarios.
        Raises ValueError for hard constraints; warns for soft conflicts.
        """
        try:
            # Validate all required config keys exist upfront
            required_keys = [
                "max_positions",
                "max_position_size_pct",
                "max_total_invested_pct",
                "vix_caution_threshold",
                "vix_max_threshold",
                "vix_alert_threshold",
                "halt_drawdown_pct",
                "risk_reduction_at_minus_5",
                "risk_reduction_at_minus_10",
                "risk_reduction_at_minus_15",
                "risk_reduction_at_minus_20",
                "earnings_blackout_days_before",
                "earnings_blackout_days_after",
                "max_stop_distance_pct",
                "base_risk_pct",
                "max_daily_loss_pct",
                "max_weekly_loss_pct",
                "min_completeness_score",
                "min_signal_quality_score",
                "min_stock_price",
            ]
            missing = [k for k in required_keys if k not in self._config or self._config[k] is None]
            if missing:
                raise ValueError(
                    f"Critical config keys missing (required for validation): {missing}. "
                    f"Ensure AlgoConfig defaults are loaded and database values override them correctly."
                )

            # Position geometry: max_positions * max_position_size_pct <= max_total_invested_pct
            max_pos = float(self._config["max_positions"])
            max_pos_size_pct = float(self._config["max_position_size_pct"])
            max_total_pct = float(self._config["max_total_invested_pct"])

            theoretical_max_from_position_size = (
                max_total_pct / max_pos_size_pct if max_pos_size_pct > 0 else float("inf")
            )
            if max_pos > theoretical_max_from_position_size:
                logger.warning(
                    f"Config conflict: max_positions={max_pos} * "
                    f"max_position_size_pct={max_pos_size_pct}% = "
                    f"{max_pos * max_pos_size_pct}% > max_total_invested_pct={max_total_pct}%. "
                    f"Geometric maximum is {theoretical_max_from_position_size:.1f} positions."
                )

            # VIX thresholds: caution < max (hard constraint)
            vix_caution = float(self._config["vix_caution_threshold"])
            vix_max = float(self._config["vix_max_threshold"])
            vix_alert = float(self._config["vix_alert_threshold"])

            if vix_caution >= vix_max:
                raise ValueError(
                    f"Config error: vix_caution_threshold ({vix_caution}) must be < vix_max_threshold ({vix_max})"
                )

            if vix_alert >= vix_max:
                logger.warning(
                    f"Config: vix_alert_threshold ({vix_alert}) >= vix_max_threshold ({vix_max}). "
                    "Alert will never trigger (max threshold reached first)."
                )

            if vix_caution >= vix_alert:
                logger.warning(
                    f"Config: vix_caution_threshold ({vix_caution}) >= "
                    f"vix_alert_threshold ({vix_alert}). Caution will trigger before alert."
                )

            # Drawdown thresholds: halt_drawdown must be negative or zero (represents loss)
            halt_dd = float(self._config["halt_drawdown_pct"])
            r_at_minus_5 = float(self._config["risk_reduction_at_minus_5"])
            r_at_minus_10 = float(self._config["risk_reduction_at_minus_10"])
            r_at_minus_15 = float(self._config["risk_reduction_at_minus_15"])
            r_at_minus_20 = float(self._config["risk_reduction_at_minus_20"])

            if halt_dd > 0:
                raise RuntimeError(
                    f"[CONFIG SAFETY GATE CORRUPTION] halt_drawdown_pct is positive ({halt_dd}). "
                    f"This should be negative or zero (representing a loss threshold). "
                    f"Positive value would halt trading at positive returns, disabling the drawdown protection. "
                    f"Action: Fix halt_drawdown_pct in algo_config table (should be -5 to -20)."
                )

            if not (r_at_minus_20 <= r_at_minus_15 <= r_at_minus_10 <= r_at_minus_5):
                logger.warning(
                    f"Config: Risk reduction thresholds not ordered: "
                    f"-5%={r_at_minus_5}, -10%={r_at_minus_10}, "
                    f"-15%={r_at_minus_15}, -20%={r_at_minus_20}. "
                    f"Expected: -5% >= -10% >= -15% >= -20%"
                )

            # Earnings blackout: both should be non-negative
            eb_before = int(self._config["earnings_blackout_days_before"])
            eb_after = int(self._config["earnings_blackout_days_after"])

            if eb_before < 0 or eb_after < 0:
                logger.warning(
                    f"Config: Earnings blackout days should be non-negative (before={eb_before}, after={eb_after})"
                )

            # Stop loss: max_stop_distance_pct should be positive and reasonable
            max_stop = float(self._config["max_stop_distance_pct"])
            if max_stop <= 0:
                logger.warning(f"Config: max_stop_distance_pct ({max_stop}) should be positive")
            if max_stop > 50:
                logger.warning(f"Config: max_stop_distance_pct ({max_stop}) is very wide (typical range 5-20%)")

            # Risk percentages: should be positive
            base_risk = float(self._config["base_risk_pct"])
            if base_risk <= 0:
                logger.warning(f"Config: base_risk_pct ({base_risk}) should be positive")
            if base_risk > 5:
                logger.warning(f"Config: base_risk_pct ({base_risk}) is very high (typical: 0.5-2%)")

            # Daily/weekly loss caps must be positive - zero values disable risk protection
            daily_loss = float(self._config["max_daily_loss_pct"])
            weekly_loss = float(self._config["max_weekly_loss_pct"])

            if daily_loss <= 0 or weekly_loss <= 0:
                raise RuntimeError(
                    f"[CONFIG SAFETY GATE CORRUPTION] Critical risk parameters are zero or negative: "
                    f"max_daily_loss_pct={daily_loss}, max_weekly_loss_pct={weekly_loss}. "
                    f"This disables all daily and weekly loss protections. "
                    f"Cannot start trading system with broken risk gates. "
                    f"Action: Restore valid values in algo_config table."
                )

            if daily_loss >= weekly_loss:
                logger.warning(
                    f"Config: max_daily_loss_pct ({daily_loss}) >= max_weekly_loss_pct ({weekly_loss}). "
                    "Daily limit will trigger before weekly limit."
                )

            # Minimum thresholds should be non-negative
            min_completeness = int(self._config["min_completeness_score"])
            min_signal_quality = int(self._config["min_signal_quality_score"])
            min_stock_price = float(self._config["min_stock_price"])

            if min_completeness < 0 or min_signal_quality < 0 or min_stock_price < 0:
                logger.warning(
                    f"Config: Score/price thresholds should be non-negative "
                    f"(completeness={min_completeness}, signal_quality={min_signal_quality}, "
                    f"stock_price={min_stock_price})"
                )

            # Loader rate limit thresholds: EOD < Morning (due to 85-min vs 450-min budget)
            # FAIL-FAST: Rate limits must be explicitly configured for proper circuit breaker operation
            eod_threshold_val = self._config.get("loader_rate_limit_circuit_break_threshold_eod")
            morning_threshold_val = self._config.get("loader_rate_limit_circuit_break_threshold_morning")

            if eod_threshold_val is None:
                raise ValueError(
                    "CRITICAL: loader_rate_limit_circuit_break_threshold_eod config missing. "
                    "Circuit breaker requires explicit rate limit threshold for EOD pipeline. "
                    "Check config and ensure this threshold is set."
                )
            if morning_threshold_val is None:
                raise ValueError(
                    "CRITICAL: loader_rate_limit_circuit_break_threshold_morning config missing. "
                    "Circuit breaker requires explicit rate limit threshold for morning pipeline. "
                    "Check config and ensure this threshold is set."
                )

            eod_threshold = int(eod_threshold_val)
            morning_threshold = int(morning_threshold_val)

            if eod_threshold >= morning_threshold:
                logger.warning(
                    f"Config: loader_rate_limit_circuit_break_threshold_eod ({eod_threshold}s) >= "
                    f"loader_rate_limit_circuit_break_threshold_morning ({morning_threshold}s). "
                    f"EOD has tighter deadline (85 min vs 450 min). Consider: eod < morning."
                )

            if eod_threshold > 600:
                logger.critical(
                    f"Config: loader_rate_limit_circuit_break_threshold_eod ({eod_threshold}s = "
                    f"{eod_threshold / 60:.0f} min) exceeds safe limit (600s = 10 min). "
                    f"EOD window is only 85 min total. Reduce to <= 600s to ensure completion."
                )

            logger.info("[AlgoConfig] Interdependency validation passed")

        except ValueError as e:
            logger.error(f"[AlgoConfig] FATAL: {e}")
            raise
        except (ZeroDivisionError, TypeError) as e:
            logger.warning(f"[AlgoConfig] Interdependency validation error: {e}")

    def get_critical_thresholds_summary(self) -> dict[str, dict[str, Any]]:
        """Return a dict of all critical safety thresholds and their current values.

        Useful for monitoring, dashboards, and admin verification.
        Format: {key: {"value": X, "min": Y, "max": Z, "source": "database"}}
        """
        summary: dict[str, dict[str, Any]] = {}
        for key, (
            _schema_type,
            min_val,
            max_val,
            is_critical,
            fail_closed,
        ) in self.VALIDATION_SCHEMA.items():
            if is_critical:
                summary[key] = {
                    "value": self._config.get(key),
                    "min": min_val,
                    "max": max_val,
                    "safe_default": fail_closed,
                    "source": self._sources.get(key, "unknown"),
                }
        return summary

    def _audit_config_sources(self) -> None:
        """Log audit trail of config sources and critical threshold status.

        Helps detect silent fallbacks, schema inconsistencies, and unsafe thresholds.
        """
        num_db = sum(1 for s in self._sources.values() if s == "database")
        num_default = sum(1 for s in self._sources.values() if s == "default")
        num_fallback = sum(1 for s in self._sources.values() if s == "default_fallback")
        num_fail_closed = sum(1 for s in self._sources.values() if s == "fail_closed_default")

        logger.info(
            f"[AlgoConfig] SOURCES: {num_db} from database, {num_default} using defaults, "
            f"{num_fallback} fallback-to-default (invalid DB values), "
            f"{num_fail_closed} fail-closed-defaults (critical safety gates)"
        )

        # Log critical threshold status
        summary = self.get_critical_thresholds_summary()
        logger.info("[AlgoConfig] CRITICAL SAFETY THRESHOLDS (startup verification):")
        for key in sorted(summary.keys()):
            info = summary[key]
            logger.info(
                f"  {key:40s} = {info['value']:>15} "
                f"[{info['min']}, {info['max']}] "
                f"(source: {info['source']:15s} safe_default: {info['safe_default']})"
            )

        # Warn if any critical thresholds are using defaults or fail-closed
        problematic = [k for k, info in summary.items() if info["source"] in ("default", "fail_closed_default")]
        if problematic:
            logger.warning(
                f"[AlgoConfig] ALERT: {len(problematic)} critical thresholds NOT loaded from database "
                f"(using defaults/fail-closed): {sorted(problematic)}. "
                f"Verify algo_config table is properly populated."
            )

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with type validation.

        FIXED Issue #8: Validates that the retrieved value matches the expected type.
        If value is missing, returns default. If value exists but has wrong type,
        logs error and returns fail-closed default from VALIDATION_SCHEMA (if critical)
        or the default parameter (if non-critical).

        WARNING: Providing a hardcoded default parameter can hide config load failures.
        Ensures the default matches DEFAULTS to detect misalignment in code.
        """
        if default is not None and key in self.DEFAULTS:
            default_value, _, _ = self.DEFAULTS[key][:3]
            parsed_default = self._parse_value(default_value, self.DEFAULTS[key][1])
            if parsed_default != default:
                logger.warning(
                    f"[CONFIG] Default mismatch for {key!r}: code has {default!r} but DEFAULTS has {parsed_default!r}"
                )

        value = self._config.get(key)
        if value is None:
            # Check if this is a critical parameter - fail-fast if missing
            if key in self.VALIDATION_SCHEMA:
                is_critical = self.VALIDATION_SCHEMA[key][3]
                if is_critical:
                    raise RuntimeError(
                        f"Critical configuration parameter {key!r} not found in database. "
                        f"This value is required for system safety. Set via config.set() to configure."
                    )
            # If no value in database and no override default provided, use DEFAULTS dict
            if default is None and key in self.DEFAULTS:
                default_value, default_type = self.DEFAULTS[key][:2]
                return self._parse_value(default_value, default_type)
            return default

        # FIXED Issue #8: Validate type safety at retrieval time
        # FIXED Cluster 6: Detect runtime safety gate corruption (zero critical values)
        if key in self.VALIDATION_SCHEMA:
            expected_type = self.VALIDATION_SCHEMA[key][0]
            is_critical = self.VALIDATION_SCHEMA[key][3]
            fail_closed_value = self.VALIDATION_SCHEMA[key][4] if len(self.VALIDATION_SCHEMA[key]) > 4 else None

            # Check if value has correct type
            type_ok = self._check_type(value, expected_type)
            if not type_ok:
                error_msg = (
                    f"[CONFIG TYPE ERROR] {key!r} has type {type(value).__name__}, "
                    f"expected {expected_type}. Value: {value!r}"
                )
                logger.error(error_msg)

                # Return fail-closed value for critical thresholds
                if is_critical and fail_closed_value is not None:
                    logger.warning(
                        f"[CONFIG TYPE ERROR] {key!r} is critical  - returning fail-closed value {fail_closed_value!r}"
                    )
                    return fail_closed_value
                else:
                    # For non-critical values, fall back to DEFAULTS the same way the
                    # missing-value branch above does -- previously this returned the
                    # caller's raw `default` parameter (None unless the caller happened
                    # to pass one explicitly), silently discarding a perfectly good
                    # DEFAULTS entry just because the DB's raw text value didn't parse
                    # to the expected Python type. Confirmed live: algo_config stores
                    # all values as TEXT ("true"/"false" strings), so any bool key whose
                    # DB row wasn't parsed into a real Python bool before reaching
                    # self._config hit this exact path -- e.g. `alpaca_paper_trading`
                    # returning None broke Phase 9 reconciliation's trading-mode check
                    # on every run despite DEFAULTS having a correct fallback.
                    if default is None and key in self.DEFAULTS:
                        default_value, default_type = self.DEFAULTS[key][:2]
                        return self._parse_value(default_value, default_type)
                    return default

            # Detect safety gate corruption at runtime (critical value set to zero after startup)
            if is_critical and expected_type in ("int", "float"):
                try:
                    f_val = float(value)
                    if abs(f_val) < 0.001:
                        logger.error(
                            f"[CONFIG SAFETY GATE CORRUPTION] Critical parameter {key!r} = {f_val} (zero/near-zero). "
                            f"This disables a safety protection. Returning fail-closed value {fail_closed_value}. "
                            f"Action: Restore valid value in database or run migration-033 to reset to safe defaults."
                        )
                        if fail_closed_value is not None:
                            return fail_closed_value
                except (ValueError, TypeError):
                    pass  # Type validation already caught this above

        return value

    def __getitem__(self, key: str) -> Any:
        """Enable dict-like access: config[key]."""
        value = self._config.get(key)
        if value is None:
            raise KeyError(f"Configuration key {key!r} not found")
        return value

    def __setitem__(self, key: str, value: Any) -> None:
        """Enable dict-like assignment: config[key] = value (in-memory only)."""
        self._config[key] = value
        self._sources[key] = "runtime_override"

    def __contains__(self, key: str) -> bool:
        """Enable membership testing: key in config."""
        return key in self._config

    def _check_type(self, value: Any, expected_type: str) -> bool:
        if expected_type == "int":
            return isinstance(value, int) and not isinstance(value, bool)
        elif expected_type == "float":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        elif expected_type == "bool":
            return isinstance(value, bool)
        elif expected_type == "string":
            return isinstance(value, str)
        return True  # Unknown types pass through

    def override(self, key: str, value: Any) -> None:
        """Apply an in-memory-only override (env var wins over DB). No DB write, no audit.

        Used for command-line args and event-level test overrides that should not persist.
        """
        if key not in self.DEFAULTS:
            logger.warning(f"[CONFIG OVERRIDE] Unknown key {key!r}  - ignored")
            return
        _, dtype, _ = self.DEFAULTS[key][:3]
        try:
            self._validate_value(key, str(value), dtype)
            self._config[key] = self._parse_value(str(value), dtype)
            self._sources[key] = "override"
            logger.info(f"[CONFIG OVERRIDE] {key} = {value} ({dtype})")
        except ValueError as e:
            logger.error(f"[CONFIG OVERRIDE] Invalid value for {key}: {e}  - ignored")

    def set(self, key: str, value: Any, value_type: str, description: str = "", changed_by: str = "system") -> bool:
        """Set configuration value in database, memory, and audit log.

        For critical safety thresholds: if the value is invalid, rejects it and instead
        writes the fail-closed safe default. Returns False to signal that the requested
        value was rejected.

        Args:
            key: Configuration key
            value: New value
            value_type: Type ('int', 'float', 'bool', 'string')
            description: Description (only used for new keys)
            changed_by: Actor making the change (for audit trail)

        Returns: bool (success if value was set as requested; False if rejected/fail-closed)
        """
        try:
            # Validate the requested value
            self._validate_value(key, str(value), value_type)
            final_value = value
            was_fail_closed = False

        except ValueError as e:
            # Value is invalid. For critical thresholds, apply fail-closed default.
            schema_info = self.VALIDATION_SCHEMA.get(key)
            if schema_info and schema_info[3]:  # is_critical
                _, _, _, _, fail_closed = schema_info
                logger.error(
                    f"ALERT: Admin attempted to set critical safety gate {key} = {value}. "
                    f"REJECTED (invalid): {e}. "
                    f"Applying fail-closed default {fail_closed} instead. "
                    f"Actor: {changed_by}"
                )
                final_value = fail_closed
                was_fail_closed = True
            else:
                # Non-critical: just reject and return False
                logger.error(f"Error: Invalid config value for {key}: {e}")
                return False

        try:
            with DatabaseContext("write") as cur:
                # Capture old value for audit trail
                cur.execute("SELECT value FROM algo_config WHERE key = %s", (key,))
                row = cur.fetchone()
                old_value = row["value"] if row else None

                # CRITICAL FIX: Check if value_type column exists before using it
                # Schema always has value_type (not data_type) - use correct column name
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'algo_config' AND column_name = 'value_type'
                """)
                has_value_type_col = cur.fetchone() is not None

                # Upsert config value (use final_value which may be fail-closed default)
                if has_value_type_col:
                    cur.execute(
                        """
                        INSERT INTO algo_config (key, value, value_type, updated_at, updated_by)
                        VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s)
                        ON CONFLICT (key) DO UPDATE SET
                            value = EXCLUDED.value,
                            value_type = EXCLUDED.value_type,
                            updated_at = CURRENT_TIMESTAMP,
                            updated_by = EXCLUDED.updated_by
                    """,
                        (key, str(final_value), value_type, changed_by),
                    )
                else:
                    # Fallback for very old schemas without value_type column
                    cur.execute(
                        """
                        INSERT INTO algo_config (key, value, updated_at, updated_by)
                        VALUES (%s, %s, CURRENT_TIMESTAMP, %s)
                        ON CONFLICT (key) DO UPDATE SET
                            value = EXCLUDED.value,
                            updated_at = CURRENT_TIMESTAMP,
                            updated_by = EXCLUDED.updated_by
                    """,
                        (key, str(final_value), changed_by),
                    )

                # Write audit trail (note: include original requested value if fail-closed)
                # Skip no-op writes (old_value == final_value, not fail-closed): callers like
                # run_local_orchestrator.py's per-run "force paper mode" guard call set() on
                # every single orchestrator run regardless of whether the value already matches,
                # which had flooded algo_config_audit with ~1900 identical "paper -> paper"
                # rows (97% of the table) - burying real changes like the 2026-07-20
                # min_win_rate_pct restoration under noise and defeating the audit trail's
                # purpose of surfacing actual risk-parameter changes.
                audit_note = " (FAIL-CLOSED from invalid request)" if was_fail_closed else ""
                if was_fail_closed or old_value != str(final_value):
                    try:
                        cur.execute(
                            """
                            INSERT INTO algo_config_audit (config_key, old_value, new_value, changed_by, changed_at)
                            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                        """,
                            (key, old_value, str(final_value) + audit_note, changed_by),
                        )
                    except psycopg2.errors.UndefinedTable as audit_err:
                        # Genuinely missing table (e.g. a fresh DB before migrations run) is
                        # survivable, but silent at DEBUG level hid this real degraded state -
                        # a live finance system should never lose its config-change audit trail
                        # without someone noticing (2026-08-24 real-money-readiness audit: found
                        # this except was also swallowing unrelated DB errors - transient
                        # connection issues, deadlocks, real bugs - for the config_key/old_value/
                        # new_value/changed_by INSERT below, indistinguishable from the "table
                        # doesn't exist" case this was written for. Table has existed and held
                        # 1,998 rows since well before this fix, so that original justification
                        # is stale; narrowed to the specific exception it actually describes).
                        logger.warning(f"[CONFIG] audit_config table missing, audit trail not recorded: {audit_err}")

            self._config[key] = self._parse_value(str(final_value), value_type)
            self._sources[key] = "database" if not was_fail_closed else "fail_closed_default"
            if was_fail_closed:
                logger.warning(
                    f"[CONFIG SET - FAIL-CLOSED] {key}: requested {value}, set to safe default {final_value}, "
                    f"actor={changed_by}"
                )
                return False
            else:
                logger.info(f"[CONFIG SET] {key} = {final_value} (was {old_value}), actor={changed_by}")
                return True

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for compatibility with code expecting dict."""
        return dict(self._config)

    def initialize_defaults(self) -> bool:
        try:
            with DatabaseContext("write") as cur:
                for key, entry in self.DEFAULTS.items():
                    value, dtype, desc = entry[:3]
                    cur.execute(
                        """
                        INSERT INTO algo_config (key, value, value_type, description, updated_at, updated_by)
                        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, 'system')
                        ON CONFLICT (key) DO NOTHING
                    """,
                        (key, value, dtype, desc),
                    )
            logger.info(f"[OK] Initialized {len(self.DEFAULTS)} config defaults")
            return True
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def reload(self) -> None:
        """Reload configuration from database with full validation.

        Ensures hot-reloaded values pass the same critical safety checks as startup.
        Invalidates cached specialist configs (RiskConfig, CircuitBreakerConfig, DataPatrolConfig, TradingConfig, etc.)
        so they re-read updated values on next access.
        """
        self._config.clear()
        self._sources.clear()
        # Invalidate specialist config caches so they refresh on next access
        if hasattr(self, "_risk_config"):
            delattr(self, "_risk_config")
        if hasattr(self, "_circuit_breaker_config"):
            delattr(self, "_circuit_breaker_config")
        if hasattr(self, "_data_patrol_config"):
            delattr(self, "_data_patrol_config")
        if hasattr(self, "_timeout_config"):
            delattr(self, "_timeout_config")
        if hasattr(self, "_trading_config"):
            delattr(self, "_trading_config")
        if hasattr(self, "_execution_config"):
            delattr(self, "_execution_config")
        if hasattr(self, "_economic_stress_config"):
            delattr(self, "_economic_stress_config")
        self._load_defaults()
        self._load_from_database()
        self._validate_critical_thresholds()
        self._validate_config_interdependencies()
        self._audit_config_sources()
        logger.info("[AlgoConfig] Reload completed with validation")

    def __repr__(self) -> str:
        return f"<AlgoConfig {len(self._config)} keys>"


# Global config instance (thread-safe)
_instance = None
_instance_lock = threading.Lock()


def get_config() -> AlgoConfig:
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
    """Reset singleton  - call at Lambda invocation start so config is fresh each run.

    This ensures warm Lambda invocations reload config from the DB, picking up
    any changes made between invocations (e.g., lowering a risk threshold).
    Thread-safe reset using lock.
    """
    global _instance
    with _instance_lock:
        _instance = None
    logger.info("[AlgoConfig] Singleton reset  - will reload from DB on next get_config() call")


def get_api_timeout() -> int:
    return cast(int, get_config().timeout.get_api_timeout())


def get_db_timeout() -> int:
    return cast(int, get_config().timeout.get_db_timeout())


def get_market_data_timeout() -> int:
    return cast(int, get_config().timeout.get_market_data_timeout())


def get_alpaca_timeout() -> int:
    return cast(int, get_config().timeout.get_alpaca_timeout())


def get_webhook_timeout() -> int:
    return cast(int, get_config().timeout.get_webhook_timeout())


def get_subprocess_timeout() -> int:
    return cast(int, get_config().timeout.get_subprocess_timeout())


def get_alpaca_base_url(execution_mode: str | None = None) -> str:
    """Get Alpaca API base URL from unified config.

    Delegates to config/api_endpoints.py (single source of truth for all external APIs).

    BUG FOUND 2026-07-28: this wrapper is re-exported as `algo.infrastructure.get_alpaca_base_url`
    - a natural top-level import path - but previously called the delegate with NO execution_mode
    argument, always falling into its weakest fallback branch (bare APCA_API_BASE_URL-presence
    check, no ALGO_LIVE_TRADING acknowledgment required) regardless of what a caller actually
    passed. No current caller reaches this path (every real call site imports directly from
    config.api_endpoints instead), but it was a live footgun on a common import surface for
    real-money account routing. Now forwards execution_mode so anyone who does reach for this
    wrapper gets the same full live-intent gate as the properly-imported version.
    """
    from algo.config.api_endpoints import get_alpaca_base_url as get_unified_url

    return get_unified_url(execution_mode)


if __name__ == "__main__":
    config = get_config()
    config.initialize_defaults()
    logger.info("\nConfiguration Summary:")
    logger.info("=" * 60)
    for key, val in sorted(config.to_dict().items()):
        logger.info(f"  {key:.<40} {val}")
    logger.info("=" * 60)
