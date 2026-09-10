"""Orchestrator mixin (OrchestratorStartupMixin), extracted from orchestrator.py
(file-size ratchet split, 2026-09-10). Methods moved verbatim - no behavior change -
except call sites for names some test files patch at module level on
algo.orchestration.orchestrator (DatabaseContext/datetime/get_event_hub/run_phaseN)
now go through `_owner()` so that patching keeps working regardless of which mixin
file actually calls them; see `_owner()`'s own docstring. Mixed into Orchestrator via
multiple inheritance in orchestrator.py - every other `self.` call here resolves
normally through the instance regardless of which mixin file defines it.
"""

import json
import logging
import os
import signal
import time
from datetime import timedelta, timezone
from typing import TYPE_CHECKING, Any

import psycopg2

from algo.config.credential_manager import is_obviously_fake_alpaca_key
from algo.orchestration.phase_event_hub import PhaseCompletedEvent, PhaseStatus

if TYPE_CHECKING:
    from algo.orchestration._orchestrator_protocol import OrchestratorProtocol

    _Base = OrchestratorProtocol
else:
    _Base = object

logger = logging.getLogger(__name__)


def _owner() -> Any:
    """Lazy reference to the owner module (algo.orchestration.orchestrator), resolved at
    call time not import time. Several tests patch `algo.orchestration.orchestrator.
    DatabaseContext` / `.datetime` / `.get_event_hub` / `.run_phase1` / `.run_phase2` /
    `.run_phase9` directly (module-level monkeypatching) - a plain top-level import of
    those names in THIS file would bind this module's own separate copy, which those
    patches can never reach. Going through `_owner().X` always reads whatever the owner
    module's current attribute is, mocked or real - same pattern as loaders/helpers/
    vqg_quality.py's `_owner()` for the identical reason. Importing lazily (inside this
    function body, not at module level) also avoids a circular import, since the owner
    module is what imports THIS module.
    """
    from algo.orchestration import orchestrator as _owner_mod

    return _owner_mod


class OrchestratorStartupMixin(_Base):
    def _resolve_execution_mode(self, env_execution_mode: str, db_execution_mode: str | None) -> str | None:
        """Set self.execution_mode per env var > database > default precedence.

        Returns a mismatch message if env_execution_mode and db_execution_mode disagree
        (caller sends it as a real alert once self.alerts exists), else None.

        Warn (and alert) on mismatch rather than crash here - crashing on mismatch can cause
        cascading failures if database gets out of sync. The separate, stricter
        _validate_startup_configuration() check (called later, from run()) DOES fail fast on
        any mismatch before any phase executes - this is not a replacement for that, it's an
        earlier signal for the case where run() hasn't been called yet, or crashes silently.

        SAFETY (2026-09-06, real-money-readiness audit): a mismatch here used to only get a
        logger.warning - but the dashboard/API (lambda/api/routes/algo_handlers/config.py)
        reads execution_mode ONLY from the database row, with zero visibility into this env
        var. If the two ever disagree, the dashboard shows the WRONG mode indefinitely (not
        just until a restart) - an operator could see "paper" while the orchestrator process
        is actually running "auto". A log line nobody may ever read isn't an acceptable
        control for that gap, so the caller now also sends a real alert.
        """
        if env_execution_mode:
            logger.info(f"[STARTUP] ORCHESTRATOR_EXECUTION_MODE env var set: {env_execution_mode}")
            self.execution_mode = env_execution_mode
            if db_execution_mode and env_execution_mode != db_execution_mode.lower():
                mismatch_msg = (
                    f"execution_mode mismatch: env var '{env_execution_mode}' != database "
                    f"'{db_execution_mode}'. Using env var (has precedence), but the dashboard "
                    f"reads only the database value and will show the WRONG mode until this is "
                    f"reconciled. Set the database to match to avoid confusion."
                )
                logger.warning(f"[STARTUP] {mismatch_msg}")
                return mismatch_msg
            return None
        if db_execution_mode:
            self.execution_mode = db_execution_mode
            logger.info(
                f"[STARTUP] ORCHESTRATOR_EXECUTION_MODE env var not set, using database config: {self.execution_mode}"
            )
            return None
        # Only fallback to paper if database also doesn't have it set
        self.execution_mode = "paper"
        logger.info(
            f"[STARTUP] ORCHESTRATOR_EXECUTION_MODE env var not set and no database config, defaulting to: {self.execution_mode}"
        )
        return None

    def _validate_startup_configuration(self) -> None:
        """CRITICAL: Validate all required configuration at startup.

        Checks:
        1. OrchestratorConfig values are valid (timeouts, thresholds, ranges)
        2. execution_mode is set and valid (paper/review/auto)
        3. For live trading: Alpaca credentials available (API key + secret)
        4. Required config keys present

        Raises RuntimeError if any validation fails.
        """
        logger.info("[STARTUP VALIDATION] Checking required configuration...")

        # 0. Validate OrchestratorConfig values (timeouts, thresholds, etc.)
        from algo.config.orchestrator_config import OrchestratorConfig

        is_valid, config_errors = OrchestratorConfig.validate()
        if not is_valid:
            error_msg = "\n  ".join(config_errors)
            raise RuntimeError(
                f"[STARTUP] CRITICAL: OrchestratorConfig validation failed. Fix environment variables or config values:\n  {error_msg}"
            )
        logger.info(f"[OK] OrchestratorConfig validated: {len(config_errors) == 0}")

        # 1. Validate execution_mode FIRST
        # BUG FOUND 2026-07-28: this validation (and compute_run_mode_label's real-money
        # risk check, in run()) used to accept "live" as an equally-valid third value
        # alongside "paper"/"auto" - but algo/trading/executor_strategies.py's
        # create_execution_mode_strategy(), the ONLY place execution_mode actually turns
        # into trading behavior, has never registered a "live" strategy (only paper/
        # review/auto). "live" - the single most natural word an operator/Terraform var
        # would pick for "real money mode" - would pass this startup check clean, then
        # crash deep inside TradeExecutor.__init__ the moment Phase 6 (exit execution,
        # always_run) instantiated it. "auto" is this system's one real live-trading
        # strategy (see AutoExecutionMode's own ALGO_LIVE_TRADING/ALPACA_PAPER_TRADING
        # safety-gate logic) - reject "live" explicitly here rather than silently alias
        # it, since dozens of call sites (executor_entry_handler.py,
        # executor_exit_handler.py, reconciliation.py) do literal `== "auto"` string
        # checks against the raw config value that an alias could silently bypass.
        #
        # SEPARATE GAP, same discovery: "review" mode IS a real, fully-implemented strategy
        # (executor_strategies.py's ReviewExecutionMode; executor.py's execute_entry creates a
        # distinct "pending" order for manual review - see its own `execution_mode == "review"`
        # branch; order_manager.py's send_exit early-returns for it same as paper) - but this
        # check never accepted it, so the only way to reach it was for a caller to bypass
        # Orchestrator entirely. Added below alongside the "live" rejection.
        #
        # THIRD GAP, same class, found immediately after: "dry" has always been one of only 4
        # values algo/infrastructure/config/execution_config.py's get_execution_mode() accepts
        # (paper|dry|review|auto), and order_manager.py/executor.py both already branch on it
        # explicitly (treated identically to "paper" - LOCAL-only order, never reaches Alpaca)
        # - but this check never accepted it either, so a config actually set to "dry" would
        # pass nothing here, then crash inside TradeExecutor.__init__'s
        # create_execution_mode_strategy() call (which also never registered it, now fixed
        # alongside this). Added below too.
        # CRITICAL: Verify env var execution_mode matches DB config execution_mode.
        # Root cause (2026-07-28): env var controls the banner and initial value, but actual
        # trading behavior uses DB config exclusively. If they disagree, operator is misled
        # about whether this run risks real money. Must fail fast to prevent silent trading
        # mode confusion (e.g., operator believes it's paper trading due to env var but DB
        # is set to auto/live, so real orders execute without operator realizing).
        env_execution_mode = self.execution_mode
        db_execution_mode = self.config.get("execution_mode")
        if env_execution_mode and db_execution_mode and env_execution_mode != db_execution_mode:
            raise RuntimeError(
                f"[STARTUP] execution_mode mismatch: "
                f"env var (ORCHESTRATOR_EXECUTION_MODE) is '{env_execution_mode}' "
                f"but database config is '{db_execution_mode}'. "
                f"These must match - actual trading behavior uses the database value, "
                f"but the banner and scheduling info use the env var. "
                f"This mismatch risks silent real-money trading confusion. "
                f"Set both to the same value and redeploy."
            )

        # Use self.execution_mode which was set by __init__ precedence logic (env var > DB > default)
        # This is the ACTUAL value being used for trading after precedence is applied
        execution_mode = self.execution_mode
        execution_mode_descriptions = {
            "paper": "Paper trading (Alpaca sandbox endpoint)",
            "dry": "Dry run (no Alpaca calls, local-only orders)",
            "review": "Manual review mode (pending orders, no auto execution)",
            "auto": "Live trading (Alpaca live or paper endpoint based on config)",
        }
        if not execution_mode or execution_mode not in execution_mode_descriptions:
            raise RuntimeError(
                f"[STARTUP] CRITICAL: execution_mode must be one of: "
                f"{', '.join(execution_mode_descriptions.keys())}. "
                f"('auto' is the real-trading mode - 'live' is NOT a supported value despite the name). "
                f"Current value: {execution_mode!r}. Configure 'execution_mode' in algo_config table."
            )
        mode_desc = execution_mode_descriptions[execution_mode]
        logger.info(f"[OK] execution_mode validated: {execution_mode} → {mode_desc}")

        # 2. Validate Alpaca credentials whenever orders are actually sent to Alpaca.
        # execution_mode == "auto" sends real orders to Alpaca's PAPER endpoint when
        # alpaca_paper_trading=True, and to the LIVE endpoint when False - both need valid
        # credentials to authenticate. Only "paper"/"dry"/"review" execution_mode never talks
        # to Alpaca at all (see executor.py's _submit_and_validate_order). Previously this
        # skipped validation entirely whenever alpaca_paper_trading=True, regardless of
        # execution_mode - so an "auto" + paper-trading config (a normal, common combination)
        # passed startup validation with no credentials, then failed later and confusingly
        # when Phase 8 Entry Execution actually tried to place an order and got a 401. That's
        # exactly the fail-fast violation this validator exists to prevent.
        if execution_mode == "auto":
            try:
                from algo.config.credential_manager import CredentialManager

                is_paper_trading = self.config.get("alpaca_paper_trading")
                if is_paper_trading is None:
                    raise RuntimeError(
                        "[STARTUP] CRITICAL: alpaca_paper_trading key must be explicitly set in algo_config. "
                        "Never assume defaults for trading mode. Set to True for paper trading, False for live."
                    )
                # Credentials are required regardless of is_paper_trading: it only selects
                # which Alpaca endpoint "auto" mode sends orders to (paper vs live), not
                # whether an authenticated request happens at all. Alpaca creds are stored as
                # fields inside the algo/alpaca secret, not as their own top-level
                # Secrets Manager entries -- get_alpaca_credentials() is the
                # accessor that knows this (get_password("APCA_API_KEY_ID") would
                # look for a secret literally named that, which never exists).
                api_key = None
                api_secret = None
                try:
                    alpaca_creds = CredentialManager().get_alpaca_credentials()
                    api_key = alpaca_creds.get("key")
                    api_secret = alpaca_creds.get("secret")
                except ValueError as e:
                    logger.debug(f"[STARTUP] get_alpaca_credentials() failed: {e}")

                # For LOCAL_MODE (development), also check algo_config table
                if (not api_key or not api_secret) and os.getenv("LOCAL_MODE") == "true":
                    logger.info("[LOCAL_MODE] Checking algo_config for Alpaca credentials...")
                    try:
                        with _owner().DatabaseContext("read") as cur:
                            cur.execute("SELECT value FROM algo_config WHERE key = %s", ["alpaca_api_key"])
                            result = cur.fetchone()
                            if result is not None and result[0]:
                                api_key = result[0]

                            cur.execute("SELECT value FROM algo_config WHERE key = %s", ["alpaca_api_secret"])
                            result = cur.fetchone()
                            if result is not None and result[0]:
                                api_secret = result[0]

                        if api_key and api_secret:
                            logger.info("[LOCAL_MODE] Loaded Alpaca credentials from algo_config")
                            # Set env vars so rest of code sees them
                            os.environ["APCA_API_KEY_ID"] = api_key
                            os.environ["APCA_API_SECRET_KEY"] = api_secret
                    except Exception as e:
                        logger.debug(f"[LOCAL_MODE] Could not load from algo_config: {e}")

                if not api_key or not api_secret:
                    raise RuntimeError(
                        f"[STARTUP] CRITICAL: Alpaca credentials missing for execution_mode={execution_mode!r} "
                        f"(alpaca_paper_trading={is_paper_trading}). 'auto' mode sends orders to Alpaca and "
                        "requires valid credentials, whether targeting the paper or live endpoint. "
                        "Configure APCA_API_KEY_ID and APCA_API_SECRET_KEY via AWS Secrets Manager or environment."
                    )

                # CRITICAL FIX: Reject obviously test/fake credentials
                # Test credentials like "PK0123456789ABCDEF" or "test_*" will fail at runtime
                # Fail here at startup with clear message instead of later during trading
                # See is_obviously_fake_alpaca_key()'s docstring (module level, above) for why
                # this uses a sequential-placeholder pattern check rather than an exact length.
                if is_obviously_fake_alpaca_key(api_key):
                    raise RuntimeError(
                        "[STARTUP] CRITICAL: Detected TEST/FAKE Alpaca credentials (starts with PK followed by a "
                        "sequential hex placeholder). "
                        "Cannot trade with test credentials in 'auto' mode. "
                        "This indicates the system is using database fallback credentials instead of real ones. "
                        "REQUIRED: Set real APCA_API_KEY_ID and APCA_API_SECRET_KEY in environment or AWS Secrets Manager. "
                        "Get real credentials from https://app.alpaca.markets/paper/dashboard/settings/api"
                    )
                if api_secret.startswith("test_"):
                    raise RuntimeError(
                        "[STARTUP] CRITICAL: Detected TEST/FAKE Alpaca secret (starts with 'test_'). "
                        "Cannot trade with test credentials in 'auto' mode. "
                        "REQUIRED: Set real APCA_API_SECRET_KEY in environment or AWS Secrets Manager. "
                        "Get real credentials from https://app.alpaca.markets/paper/dashboard/settings/api"
                    )

                logger.info(f"[OK] Alpaca credentials validated for execution_mode={execution_mode!r}")
            except ValueError as e:
                raise RuntimeError(f"[STARTUP] Credential validation failed: {e}") from e
            except RuntimeError as e:
                # CRITICAL: Never silently fall back to paper mode on credential failures
                # This masks security degradation and operator loses awareness of auth issues
                logger.critical(
                    f"[CREDENTIAL VALIDATION FAILED] {e}. "
                    "Live trading configured but credentials unavailable. "
                    "Halting orchestrator. Configure credentials or set execution_mode to 'paper'."
                )
                raise RuntimeError(
                    f"[ORCHESTRATOR HALT] Credential validation failed: {e}. "
                    "Cannot proceed with trading when credentials unavailable. "
                    "Set execution_mode=paper or provide valid AWS credentials."
                ) from e
        else:
            logger.info("[OK] Paper trading mode - Alpaca credentials not required")
            # WARNING: Even in paper mode, check if test credentials are present
            # These will fail when switching to production (execution_mode='auto')
            if os.getenv("LOCAL_MODE") == "true":
                try:
                    with _owner().DatabaseContext("read") as cur:
                        cur.execute("SELECT value FROM algo_config WHERE key = %s", ["alpaca_api_key"])
                        result = cur.fetchone()
                        if result and result[0] and result[0].startswith("PK"):
                            logger.warning(
                                "[STARTUP] WARNING: Test/fake Alpaca credentials detected in database "
                                "(alpaca_api_key starts with 'PK'). System is in paper mode now, but these "
                                "credentials will FAIL when switching to 'auto' mode for production trading. "
                                "To prepare for production: Get real credentials from "
                                "https://app.alpaca.markets/paper/dashboard/settings/api and set "
                                "APCA_API_KEY_ID + APCA_API_SECRET_KEY environment variables."
                            )
                except Exception as e:
                    logger.debug(f"[STARTUP] Could not check credentials: {e}")

        # 3. Validate required config keys exist (only truly critical ones)
        try:
            # Only validate critical config keys; others have sensible defaults
            critical_keys = [
                "min_signal_quality_score",
                "min_completeness_score",
            ]
            missing = []
            for key in critical_keys:
                val = self.config.get(key)
                if val is None:
                    missing.append(key)
            if missing:
                logger.warning(
                    f"[STARTUP] Missing optional config keys: {', '.join(missing)}. "
                    "These will use default values. For production, add these to algo_config table."
                )
            else:
                logger.info("[OK] All critical config keys present")
        except Exception as e:
            # FIXED: Config validation IS critical - these errors must not be silently skipped
            if "CRITICAL" in str(e):
                raise
            logger.error(f"[STARTUP] Config validation FAILED (CRITICAL): {e}")
            raise RuntimeError(
                f"[ORCHESTRATOR] Config validation failed - cannot proceed with trading. "
                f"Error: {e}. Check: (1) Environment variables set, "
                f"(2) AWS Secrets Manager accessible, (3) Config keys in database."
            ) from e

        # 4. Validate database schema (required tables and views)
        try:
            with _owner().DatabaseContext("read") as cur:
                # Check algo_positions table exists (critical for portfolio monitoring)
                # Note: algo_positions is a BASE TABLE, not a view
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'algo_positions' AND table_schema = 'public'
                    ) AS table_exists
                    """)
                row = cur.fetchone()
                if not row or not row.get("table_exists"):
                    logger.error(
                        "[STARTUP] CRITICAL: algo_positions table NOT found. "
                        "This table is required for portfolio monitoring. "
                        "Run migrations to create required database objects."
                    )
                    raise RuntimeError(
                        "[ORCHESTRATOR] Required database table 'algo_positions' not found. "
                        "Run database migrations before starting orchestrator."
                    )
                else:
                    logger.info("[OK] Database schema validation passed: algo_positions table exists")
        except RuntimeError:
            raise
        except Exception as e:
            # FIXED: Database schema validation IS critical - cannot proceed without it
            logger.error(f"[STARTUP] Database schema validation FAILED (CRITICAL): {e}")
            raise RuntimeError(
                f"[ORCHESTRATOR] Cannot validate database schema: {e}. "
                f"Check: (1) Database connection working, "
                f"(2) Migrations have run, (3) Required views exist."
            ) from e

    def _verify_alpaca_account_type(self) -> None:
        """CRITICAL: Verify Alpaca account type matches execution_mode.

        This prevents catastrophic errors where:
        - execution_mode='auto' is set but account is paper trading (orders won't execute for real)
        - execution_mode='paper' is set but account is LIVE (real money at risk during testing)

        Requirements:
        - execution_mode='auto' MUST have alpaca_paper_trading=False and real live account
        - execution_mode='paper' works with any account type
        - execution_mode='dry'/'review' don't call Alpaca API

        Raises RuntimeError if verification fails.
        """
        execution_mode = self.config.get("execution_mode", "paper")
        alpaca_paper_trading = self.config.get("alpaca_paper_trading", True)

        # Skip for modes that don't call Alpaca API
        if execution_mode in ("dry", "review"):
            logger.info(f"[OK] {execution_mode} mode - Alpaca account type not checked (no API calls)")
            return

        # For paper mode, any account type is acceptable
        if execution_mode == "paper":
            logger.info("[OK] paper mode - Alpaca account type not enforced (paper trading)")
            return

        # CRITICAL: For auto mode, must have real account
        if execution_mode == "auto":
            if alpaca_paper_trading is True:
                logger.critical(
                    "[ACCOUNT TYPE MISMATCH] CRITICAL: execution_mode='auto' but alpaca_paper_trading=True. "
                    "This means orders will be submitted to Alpaca's PAPER endpoint, not real account. "
                    "NO REAL MONEY RISK, but this is likely a configuration error. "
                    "For live trading: Set alpaca_paper_trading=False in algo_config. "
                    "For paper trading: Set execution_mode='paper' instead."
                )
                raise RuntimeError(
                    "[STARTUP] CRITICAL: Mode/Account Type Mismatch. "
                    "execution_mode=auto requires alpaca_paper_trading=False for live trading, "
                    "or execution_mode should be 'paper' for paper trading."
                )

            if alpaca_paper_trading is False:
                logger.info(
                    "[OK] LIVE TRADING MODE VERIFIED: execution_mode='auto' with alpaca_paper_trading=False. "
                    "Orders will execute on the LIVE Alpaca account. REAL MONEY AT RISK."
                )
                return

            # If neither True nor False (None or unexpected), fail fast
            raise RuntimeError(
                "[STARTUP] CRITICAL: alpaca_paper_trading is not explicitly set to True or False. "
                "Cannot determine if live or paper trading. Set explicitly in algo_config table."
            )

        # Unexpected execution_mode (should have been caught by _validate_startup_configuration)
        logger.error(
            f"[ACCOUNT TYPE CHECK] Unexpected execution_mode={execution_mode!r}. "
            f"This should have been caught by _validate_startup_configuration()."
        )

    def _verify_database_isolation_level(self) -> None:
        """CRITICAL: Verify PostgreSQL transaction isolation level is suitable for trading.

        Entry/exit operations use FOR UPDATE row locks to prevent concurrent modifications.
        These locks ONLY WORK with READ COMMITTED or stricter isolation levels.

        If database is misconfigured to READ UNCOMMITTED:
        - FOR UPDATE locks are silently ignored
        - Concurrent Phase 6 (exits) and Phase 8 (entries) can corrupt position state
        - Data integrity failure results in incorrect risk calculations

        Requirements:
        - Minimum: READ COMMITTED (default)
        - Recommended: REPEATABLE READ (safer, still allows concurrent access)
        - Strictest: SERIALIZABLE (all-or-nothing, but slower)

        Raises RuntimeError if isolation level is insufficient.
        """
        try:
            with _owner().DatabaseContext("read", timeout=5) as cur:
                cur.execute("SHOW default_transaction_isolation")
                result = cur.fetchone()
                isolation = result[0].lower() if result and result[0] else None

                if not isolation:
                    raise ValueError("SHOW isolation query returned empty result")

                # Map PostgreSQL isolation level names to their strictness ranking
                valid_levels = {
                    "read committed": 1,
                    "repeatable read": 2,
                    "serializable": 3,
                }

                if isolation not in valid_levels:
                    logger.critical(
                        f"[DB ISOLATION CRITICAL] Invalid isolation level detected: '{isolation}'. "
                        f"Valid levels: {', '.join(valid_levels.keys())}. "
                        f"This indicates either a misconfigured database or a PostgreSQL version issue."
                    )
                    raise RuntimeError(
                        f"[STARTUP] Invalid PostgreSQL isolation level: '{isolation}'. "
                        f"Configure 'default_transaction_isolation' in PostgreSQL to one of: "
                        f"{', '.join(valid_levels.keys())}"
                    )

                # READ UNCOMMITTED is too weak but PostgreSQL doesn't actually support it as a
                # real value (it silently promotes to READ COMMITTED) - the `isolation not in
                # valid_levels` check above already catches any unrecognized session-level
                # setting, so every value reaching this point is >= read committed.
                logger.info(
                    f"[OK] Database transaction isolation verified: '{isolation}' (sufficient for FOR UPDATE row locks)"
                )

        except RuntimeError:
            raise
        except TimeoutError as e:
            logger.critical(
                "[DB ISOLATION TIMEOUT] Could not verify isolation level - database timeout. "
                "Connection pool may be exhausted or database unavailable."
            )
            raise RuntimeError(
                "[STARTUP] Could not verify database isolation level (timeout). "
                "Check database connectivity and connection pool health."
            ) from e
        except Exception as e:
            logger.critical(f"[DB ISOLATION ERROR] Unexpected error during isolation check: {type(e).__name__}: {e}")
            raise RuntimeError(
                f"[STARTUP] Could not verify database isolation level: {type(e).__name__}: {e}. "
                f"This is a critical safety check - cannot proceed without it."
            ) from e

    def _validate_required_tables(self, cur: Any) -> bool:
        """FIXED Issue #23: Validate that all required tables exist before running phases.

        Returns: True if all tables exist, False if any critical table is missing.
        """
        required_tables = [
            "price_daily",  # Phase 1, Phase 5 signal generation
            "trend_template_data",  # Phase 5 (SignalComputer - Minervini, Weinstein)
            "sector_ranking",  # Phase 3b (sector rotation)
            "market_health_daily",  # Phase 3b (exposure), Phase 4 (distribution days)
            "market_exposure_daily",  # Phase 3b (entry constraints)
            "algo_audit_log",  # Audit trail
        ]

        try:
            missing_tables = []
            found_tables = []
            for table_name in required_tables:
                try:
                    # Check if table exists by querying information_schema in public schema
                    cur.execute(
                        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s",
                        (table_name,),
                    )
                    if cur.fetchone():
                        found_tables.append(table_name)
                    else:
                        missing_tables.append(table_name)
                        logger.error(f"[TABLE-CHECK] Missing required table: {table_name}")
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.error(f"[TABLE-CHECK] Failed to check table {table_name}: {e}")
                    missing_tables.append(table_name)

            if missing_tables:
                logger.error(f"[TABLE-CHECK] Cannot proceed: missing {len(missing_tables)} tables: {missing_tables}")
                self.log_phase_result(
                    0,
                    "table_validation",
                    "halt",
                    f"Missing tables: {', '.join(missing_tables)}",
                )
                return False

            logger.info(
                f"[TABLE-CHECK] All {len(required_tables)} required tables exist [OK] - {', '.join(found_tables[:3])}..."
            )
            return True

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    # ---------- Logging helpers ----------

    def _acquire_run_lock(self, lock_timeout_seconds: int = 60) -> bool:
        """Acquire distributed lock to prevent concurrent orchestrator runs.

        FIXED Issue #8: Uses DynamoDB conditional writes instead of filesystem locks
        for correct distributed locking in Fargate ECS tasks (no shared filesystem).

        CRITICAL FIX 2026-07-30: Increased default timeout from 5s to 60s. Orchestrator
        runs typically take 470+ seconds. Previous 5s timeout caused lock acquisition
        failures when multiple runs were scheduled close together (e.g., morning/afternoon
        runs) - second run would fail immediately even though first run was still executing.
        60s gives reasonable time for previous run to complete before giving up.

        Args:
            lock_timeout_seconds: How long to retry acquiring lock (default 60s, was 5s)

        Returns: True if lock acquired, False if another active instance holds it.
        """
        self._lock_acquired = self.lock_manager.acquire(timeout_seconds=lock_timeout_seconds)
        return bool(self._lock_acquired)

    def _release_run_lock(self) -> None:
        """Release the distributed lock."""
        if self._lock_acquired:
            self.lock_manager.release()

    def _install_shutdown_handler(self) -> None:
        """Convert SIGTERM into a controlled exception so run()'s finally block still
        releases the run lock on a graceful-shutdown signal.

        CRITICAL FIX: there was no signal handling anywhere in this module - a killed
        process (Ctrl+C sends SIGINT, which Python already raises as KeyboardInterrupt and
        run()'s try/finally already handles correctly; but SIGTERM - sent by process
        managers/orchestration tooling for graceful shutdown, and effectively by some
        shell-level `timeout` implementations on Windows) terminates the process immediately
        with no chance for the finally block to run. Confirmed live 2026-07-27: a killed
        local orchestrator test run left the orchestrator-run-lock row held for its full
        TTL (at the time, whatever get_lock_manager()'s then-current default was - now an
        explicit 1800s, see this class's __init__ for why), blocking every subsequent run
        attempt until the TTL expired or someone manually deleted the row. This closes the
        SIGTERM gap; a hard SIGKILL can never run any Python code (not fixable at this layer)
        and still relies on the existing TTL expiry as the backstop.
        signal.signal() only works from the main thread - if invoked elsewhere (e.g. a
        non-main-thread Lambda invocation path), fails soft and leaves the TTL as the only
        recovery mechanism, same as before this fix.
        """
        self._prior_sigterm_handler = None

        def _handle_shutdown_signal(signum: int, frame: Any) -> None:
            raise SystemExit(f"Received signal {signum} - shutting down and releasing run lock")

        try:
            self._prior_sigterm_handler = signal.signal(signal.SIGTERM, _handle_shutdown_signal)
        except (ValueError, AttributeError, OSError) as e:
            logger.debug(f"Could not install SIGTERM handler (non-fatal, TTL still bounds lock staleness): {e}")

    def _restore_shutdown_handler(self) -> None:
        """Restore whatever SIGTERM handler (if any) was in place before this run."""
        if getattr(self, "_prior_sigterm_handler", None) is not None:
            try:
                signal.signal(signal.SIGTERM, self._prior_sigterm_handler)
            except (ValueError, AttributeError, OSError):
                pass

    def _save_orchestrator_run_status(self, overall_status: str, halt_reason: str | None = None) -> None:
        """Save orchestrator run status to algo_orchestrator_runs table.

        Extracted common method to avoid duplication of this INSERT statement.
        Used in both market hours guard block and main execution log.

        Args:
            overall_status: Status value ('degraded', 'success', 'halted', etc.)
            halt_reason: Optional reason why orchestrator halted or degraded
        """
        try:
            execution_time = time.time() - self.run_start
            with _owner().DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO algo_orchestrator_runs
                    (run_id, run_date, overall_status, started_at, completed_at, execution_time_seconds, halt_reason)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id) DO NOTHING
                    """,
                    (
                        self.run_id,
                        self.run_date,
                        overall_status,
                        _owner().datetime.now(timezone.utc) - timedelta(seconds=execution_time),
                        _owner().datetime.now(timezone.utc),
                        execution_time,
                        halt_reason or "",
                    ),
                )
            logger.debug(
                f"[EXECUTION_LOG] Wrote to algo_orchestrator_runs: run_id={self.run_id} status={overall_status}"
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"[EXECUTION_LOG] Could not write to algo_orchestrator_runs: {e}")

    def log_phase_start(self, phase_num: int | str, name: str) -> None:
        if self.verbose:
            logger.info(f"\n{'=' * 70}")
            logger.info(f"PHASE {phase_num}: {name}")
            logger.info(f"{'=' * 70}")

    def log_phase_result(self, phase_num: int | str, name: str, status: str, summary: str) -> None:
        self.phase_results[phase_num] = {
            "name": name,
            "status": status,
            "summary": summary,
        }
        # FIXED Issue #6: Also log to execution tracker for audit trail
        self.execution_tracker.log_phase_result(phase_num, name, status, summary)
        if self.verbose:
            logger.info(f"\n-> Phase {phase_num} {status}: {summary}")

        # Publish phase event to EventHub for dashboard/API subscribers
        try:
            hub = _owner().get_event_hub()
            phase_status = PhaseStatus(status)
            event = PhaseCompletedEvent(
                phase_num=phase_num,
                phase_name=name,
                status=phase_status,
                summary=summary,
            )
            hub.publish(event)
        except (ValueError, Exception) as e:
            logger.debug(f"Could not publish phase event: {e}")

        try:
            with _owner().DatabaseContext("write") as cur:
                # Normalize phase name: convert "ENTRY EXECUTION" -> "entry_execution"
                normalized_name = name.lower().replace(" ", "_")
                cur.execute(
                    """
                    INSERT INTO algo_audit_log (action_type, action_date, details, actor, status, created_at)
                    VALUES (%s, CURRENT_TIMESTAMP, %s, 'orchestrator', %s, CURRENT_TIMESTAMP)
                    """,
                    (
                        f"phase_{phase_num}_{normalized_name}",
                        json.dumps({"run_id": self.run_id, "summary": summary}),
                        status,
                    ),
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.critical(f"Audit log persistence CRITICAL FAILURE: {e}")
            raise RuntimeError(f"[AUDIT] Failed to persist phase log (data integrity risk): {e}") from e

    # ---------- Phase implementations ----------
