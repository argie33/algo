#!/usr/bin/env python3
"""
Master Orchestrator - Daily Trading Workflow (institutional desk style)

Runs the complete day's logic in 7 explicit phases. Each phase has a clear
contract: what it consumes, what it produces, what makes it fail-closed
(halt the whole pipeline) vs fail-open (log and continue).

PHASE 1 — DATA FRESHNESS CHECK
  Confirms our market data is recent enough to make decisions on.
  FAIL-CLOSED: stale data > 7 days -> halt.

PHASE 2 — CIRCUIT BREAKERS
  Runs all kill-switch checks (drawdown, daily loss, consecutive losses,
  total open risk, VIX, market stage, weekly loss).
  FAIL-CLOSED on any breaker firing.

PHASE 3 — POSITION MONITOR (existing positions first)
  For every open position:
    - Refresh current price + P&L
    - Compute trailing stop (only ratchets up)
    - Score health (RS, sector, time decay, earnings proximity, etc.)
    - PROPOSE actions: HOLD / RAISE_STOP / EARLY_EXIT
  FAIL-OPEN: log errors but continue.

PHASE 4 — EXIT EXECUTION
  Apply exit decisions from Phase 3 (full and partial) and from the
  exit_engine's tiered targets / stops / time / Minervini-break logic.
  FAIL-OPEN per position.

PHASE 5 — SIGNAL GENERATION (new entries)
  Evaluate today's BUY signals through:
    - Tiers 1-5 (data quality, market, trend template, SQS, portfolio fit)
    - Tier 6 (multi-factor advanced filters: momentum/quality/catalyst/risk)
  Rank by composite score, take top N up to max_positions cap minus
  current open positions.
  FAIL-OPEN: log and proceed with whatever passed.

PHASE 6 — ENTRY EXECUTION
  For each ranked candidate, in priority order:
    - Final pre-flight checks (still no duplicate, room left, etc.)
    - TradeExecutor.execute_trade() with idempotency
  FAIL-OPEN per trade.

PHASE 7 — RECONCILIATION & SNAPSHOT
  Pull live Alpaca account data, sync positions, calculate P&L,
  create daily portfolio snapshot.
  FAIL-OPEN: log if Alpaca down.

After every phase, results are written to algo_audit_log so the dashboard
can show exactly what happened and when.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.credential_helper import (
    get_db_password,
    get_db_config,
    DEFAULT_DB_HOST,
    DEFAULT_DB_PORT,
    DEFAULT_DB_USER,
    DEFAULT_DB_NAME,
)


import os
import tempfile
import time
import json
from utils.db_connection import get_db_connection
import psycopg2.extensions
from psycopg2 import pool as psycopg2_pool
import traceback
from datetime import datetime, date as _date, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple, Union
from algo.algo_alerts import AlertManager
from algo.algo_market_calendar import MarketCalendar
from algo.algo_sql_safety import assert_safe_table, assert_safe_column
from utils.trade_status import PositionStatus
import logging
from utils.monitoring_context import TimeBlock, log_metrics_summary, clear_metrics_buffer
from config.env_loader import load_env

logger = logging.getLogger(__name__)


class Orchestrator:
    """Daily workflow runner with explicit phases."""

    HALT_FLAG_PATH = str(Path(tempfile.gettempdir()) / 'algo_orchestrator_halt')

    def __init__(self, config: Optional[Any] = None, run_date: Optional[_date] = None, dry_run: bool = False, verbose: bool = True, init_db: bool = True) -> None:
        from algo.algo_config import get_config
        self.config = config or get_config()
        self.run_date = run_date or _date.today()
        self.dry_run = dry_run
        self.verbose = verbose
        self.phase_results = {}
        self.run_id = f"RUN-{self.run_date.isoformat()}-{datetime.now().strftime('%H%M%S')}"
        self.lock_file = Path(tempfile.gettempdir()) / 'algo_orchestrator.lock'
        self._lock_acquired = False
        self.db_failure_counter_file = Path(tempfile.gettempdir()) / 'algo_db_failures.txt'
        self.degraded_mode = False  # B4: Circuit breaker for DB failures
        self.alerts = AlertManager()

        # maxconn=25 supports 40+ concurrent loaders (typical max concurrent = ~30-35)
        try:
            self.db_pool = psycopg2_pool.ThreadedConnectionPool(
                minconn=5, maxconn=25, **get_db_config()
            )
        except Exception as e:
            logger.warning(f"Failed to create connection pool: {e}. Using fallback.")
            self.db_pool = None

        if init_db:
            self._ensure_schema_initialized()
            self._initialize_feature_flags()

    def _get_conn(self, max_retries: int = 3) -> psycopg2.extensions.connection:
        """Get database connection from pool with exponential backoff retry.

        Retries with exponential backoff (100ms, 200ms, 400ms) if pool is exhausted.
        Falls back to direct connection after retries exhausted.
        """
        import time
        if self.db_pool:
            for attempt in range(max_retries):
                try:
                    return self.db_pool.getconn()
                except psycopg2_pool.PoolError as e:
                    if attempt < max_retries - 1:
                        wait_ms = 100 * (2 ** attempt)  # 100ms, 200ms, 400ms
                        logger.debug(f"Pool exhausted (attempt {attempt + 1}/{max_retries}), retrying in {wait_ms}ms")
                        time.sleep(wait_ms / 1000.0)
                    else:
                        logger.warning(f"Pool exhausted after {max_retries} retries, using direct connection")
        return get_db_connection()

    def _put_conn(self, conn: Optional[psycopg2.extensions.connection]) -> None:
        """Return a connection to the pool."""
        if self.db_pool and conn:
            try:
                self.db_pool.putconn(conn)
            except Exception:
                try:
                    conn.close()
                except Exception as e:

                    logger.error(f"Unhandled exception: {e}")

    def cleanup(self) -> None:
        """Close the connection pool on shutdown."""
        if self.db_pool:
            try:
                self.db_pool.closeall()
            except Exception as e:
                logger.warning(f"Error closing pool: {e}")

    # ---------- Database health monitoring (B4) ----------

    def _check_db_connectivity(self) -> bool:
        """Test if database is reachable. Returns True if OK, False if failed."""
        conn = None
        cur = None
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"  [ERROR] Database connectivity check failed: {e}")
            return False
        finally:
            if cur:
                try:
                    cur.close()
                except Exception as e:

                    logger.error(f"Unhandled exception: {e}")
            self._put_conn(conn)

    def _increment_db_failure_counter(self) -> int:
        """Increment failure counter. If >= 3 consecutive failures, enter degraded mode."""
        try:
            current = 0
            if self.db_failure_counter_file.exists():
                current = int(self.db_failure_counter_file.read_text().strip() or 0)
            current += 1
            self.db_failure_counter_file.write_text(str(current))
            return current
        except Exception:
            return 1

    def _check_halt_flag(self) -> bool:
        """Check for halt flag file. Returns True if halt was requested."""
        if os.path.exists(self.HALT_FLAG_PATH):
            logger.critical("HALT FLAG DETECTED — stopping all trading phases immediately")
            self.log_phase_result(0, 'halt_flag_detected', 'halted', 'External halt flag detected and respected')
            return True
        return False

    def _reset_db_failure_counter(self) -> None:
        """Reset counter on successful DB connection."""
        try:
            if self.db_failure_counter_file.exists():
                self.db_failure_counter_file.unlink()
        except Exception as e:

            logger.error(f"Unhandled exception: {e}")

    def _ensure_schema_initialized(self) -> None:
        """Initialize database schema if not already present. Idempotent."""
        conn = None
        cur = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            cur.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN ('stock_symbols', 'algo_positions', 'algo_trades')
            """)
            result = cur.fetchone()
            table_count = result[0] if result else 0

            if table_count >= 3:
                if self.verbose:
                    logger.info("  [SCHEMA] Database schema already initialized")
                return

            if self.verbose:
                logger.info("  [SCHEMA] Initializing database schema...")

            import init_database
            init_database.main()

            if self.verbose:
                logger.info("  [SCHEMA] Database schema initialized successfully")
        except Exception as e:
            if self.verbose:
                logger.error(f"  [WARN] Schema initialization check failed: {e}")
        finally:
            if cur:
                try:
                    cur.close()
                except Exception as e:

                    logger.error(f"Unhandled exception: {e}")
            if conn:
                try:
                    conn.close()
                except Exception as e:

                    logger.error(f"Unhandled exception: {e}")

    def _initialize_feature_flags(self) -> None:
        """Initialize feature flags with safe defaults on startup."""
        try:
            from utils.feature_flags import initialize_safe_defaults, create_feature_flags_table
            # Ensure table exists
            create_feature_flags_table()
            initialize_safe_defaults()
        except Exception as e:
            if self.verbose:
                logger.warning(f"  [WARN] Feature flag initialization failed: {e}")
            # Don't fail the orchestrator if flags aren't available

    def _check_data_patrol(self, cur: Any) -> bool:
        """Check data patrol results. Fail-closed if critical/error findings.

        Only checks the LATEST patrol run (not accumulated from all runs in 24h).
        Returns: True if patrol OK, False if critical/error issues found.
        """
        # In DEV mode, skip strict patrol checks to allow testing with partial data
        if os.getenv('DEV_MODE', '').lower() in ('true', '1', 'yes'):
            logger.info("  [DEV MODE] Skipping strict data patrol checks")
            return True

        try:
            cur.execute("""
                SELECT patrol_run_id FROM data_patrol_log
                ORDER BY created_at DESC LIMIT 1
            """)
            latest_run = cur.fetchone()
            if not latest_run:
                if self.verbose:
                    logger.warning("  [WARN] No patrol data available")
                return True

            latest_run_id = latest_run[0]

            # Now get results for only this run
            cur.execute("""
                SELECT MAX(severity) as worst_severity,
                       COUNT(*) as total_findings,
                       COUNT(CASE WHEN severity = 'critical' THEN 1 END) as critical_count,
                       COUNT(CASE WHEN severity = 'error' THEN 1 END) as error_count,
                       COUNT(CASE WHEN severity = 'warn' THEN 1 END) as warn_count,
                       COUNT(CASE WHEN severity = 'info' THEN 1 END) as info_count
                FROM data_patrol_log
                WHERE patrol_run_id = %s
            """, (latest_run_id,))
            row = cur.fetchone()

            if not row or not row[0]:
                # No patrol findings (shouldn't happen, but safe to proceed)
                if self.verbose:
                    logger.info("  [PATROL] No findings in latest patrol")
                return True

            worst_severity, total_findings, critical_count, error_count, warn_count, info_count = row

            if self.verbose:
                logger.info(f"  [PATROL] {latest_run_id}: {total_findings} findings "
                            f"(critical={critical_count}, error={error_count}, warn={warn_count})")

            # Fetch flagged findings for alerting
            cur.execute("""
                SELECT check_name, severity, target_table, message
                FROM data_patrol_log
                WHERE patrol_run_id = %s AND severity IN ('critical', 'error')
                ORDER BY severity DESC
            """, (latest_run_id,))
            flagged = [{'check': r[0], 'severity': r[1], 'target': r[2], 'message': r[3]}
                       for r in cur.fetchall()]

            # Send alerts on CRITICAL or ERROR
            if critical_count > 0 or error_count > 0:
                self.alerts.send_patrol_alert(
                    latest_run_id,
                    {'critical': critical_count, 'error': error_count, 'warn': warn_count, 'info': info_count},
                    flagged
                )

            # FAIL-CLOSED: critical findings always block
            if critical_count and critical_count > 0:
                if self.verbose:
                    logger.info(f"  [HALT] Data patrol found {critical_count} CRITICAL issues")
                self.log_phase_result(1, 'data_patrol', 'halt',
                                      f'Critical data quality issues: {critical_count} critical findings')
                return False

            # FAIL-CLOSED: too many errors block in auto mode
            if error_count and error_count > 2:
                if self.verbose:
                    logger.error(f"  [HALT] Data patrol found {error_count} ERROR issues")
                self.log_phase_result(1, 'data_patrol', 'halt',
                                      f'Data quality errors: {error_count} findings')
                return False

            # Warnings are just logged, not blocking
            if error_count == 1 or error_count == 2:
                if self.verbose:
                    logger.error(f"  [WARN] Data patrol found {error_count} error(s)")

            return True

        except Exception as e:
            # If patrol check fails, fail-closed (don't trade on uncertain data)
            logger.error(f"  [HALT] Data patrol check failed: {e}")
            self.log_phase_result(1, 'data_patrol', 'halt',
                                  f'Patrol execution error: {str(e)[:100]}')
            return False

    # ---------- Logging helpers ----------

    def _acquire_run_lock(self, lock_timeout_seconds: int = 3600) -> bool:
        """Acquire exclusive lock to prevent concurrent orchestrator runs.

        Uses file-based locking with PID checking and timestamp-based expiration.
        If another instance holds the lock but:
        - Its PID is dead, OR
        - The lock timestamp is older than lock_timeout_seconds
        Then steal the lock and continue.

        Args:
            lock_timeout_seconds: Maximum age of lock before forcing acquisition (default 1 hour)

        Returns: True if lock acquired, False if another active instance holds it.
        """
        import json

        if self.lock_file.exists():
            try:
                lock_content = self.lock_file.read_text().strip()
                if lock_content:
                    # Lock format: JSON with pid and timestamp
                    try:
                        lock_data = json.loads(lock_content)
                        old_pid = lock_data.get('pid')
                        lock_timestamp = lock_data.get('timestamp', time.time())
                        lock_age = time.time() - lock_timestamp

                        if self._pid_alive(old_pid) and lock_age < lock_timeout_seconds:
                            logger.error(f"ERROR: Orchestrator already running (PID {old_pid}, lock age {lock_age:.0f}s)")
                            return False
                        else:
                            if not self._pid_alive(old_pid):
                                logger.info(f"Stale lock from dead PID {old_pid} — acquiring")
                            else:
                                logger.warning(f"Lock timeout: PID {old_pid} lock age {lock_age:.0f}s > {lock_timeout_seconds}s limit — forcing acquisition")
                    except (json.JSONDecodeError, ValueError):
                        old_pid = int(lock_content)
                        if self._pid_alive(old_pid):
                            logger.error(f"ERROR: Orchestrator already running (PID {old_pid})")
                            return False
                        else:
                            logger.info(f"Stale lock from PID {old_pid} — acquiring")
            except Exception as e:
                logger.warning(f"Warning: Could not read lock file: {e}")

        # Acquire lock with timestamp
        try:
            lock_data = {
                'pid': os.getpid(),
                'timestamp': time.time()
            }
            self.lock_file.write_text(json.dumps(lock_data))
            self._lock_acquired = True
            if self.verbose:
                logger.info(f"Lock acquired (PID {os.getpid()})")
            return True
        except Exception as e:
            logger.error(f"ERROR: Could not create lock file: {e}")
            return False

    def _release_run_lock(self) -> None:
        """Release the run lock."""
        if self._lock_acquired and self.lock_file.exists():
            try:
                self.lock_file.unlink()
                self._lock_acquired = False
            except Exception as e:

                logger.error(f"Unhandled exception: {e}")

    def log_phase_start(self, phase_num: int, name: str) -> None:
        if self.verbose:
            logger.info(f"\n{'='*70}")
            logger.info(f"PHASE {phase_num}: {name}")
            logger.info(f"{'='*70}")

    def log_phase_result(self, phase_num: int, name: str, status: str, summary: str) -> None:
        self.phase_results[phase_num] = {
            'name': name,
            'status': status,
            'summary': summary,
        }
        if self.verbose:
            logger.info(f"\n-> Phase {phase_num} {status}: {summary}")
        conn = None
        cur = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO algo_audit_log (action_type, action_date, details, actor, status, created_at)
                VALUES (%s, CURRENT_TIMESTAMP, %s, 'orchestrator', %s, CURRENT_TIMESTAMP)
                """,
                (
                    f'phase_{phase_num}_{name}',
                    json.dumps({'run_id': self.run_id, 'summary': summary}),
                    status,
                ),
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"Warning: Could not persist audit log entry: {e}")
        finally:
            if cur:
                try:
                    cur.close()
                except Exception as e:

                    logger.error(f"Unhandled exception: {e}")
            if conn:
                try:
                    conn.close()
                except Exception as e:

                    logger.error(f"Unhandled exception: {e}")

    # ---------- Pipeline Health & Visibility ----------

    def _check_pipeline_health(self, cur: Any) -> None:
        """Check that all required tables have recent data for signal processing."""
        if not cur:
            return

        try:
            # Count recent rows (from last 5 days) in each critical table
            required_tables = {
                'price_daily': 'price_daily (OHLCV)',
                'buy_sell_daily': 'buy_sell_daily (entry signals)',
                'trend_template_data': 'trend_template_data (Minervini/Weinstein scores)',
                'technical_data_daily': 'technical_data_daily (MA/RSI/ATR)',
                'signal_quality_scores': 'signal_quality_scores (SQS >= 40 gate)',
                'swing_trader_scores': 'swing_trader_scores (final ranking)',
                'market_health_daily': 'market_health_daily (Tier 2 gate)',
                'sector_ranking': 'sector_ranking (Tier 6 context)',
                'industry_ranking': 'industry_ranking (Tier 6 context)',
                'stock_scores': 'stock_scores (Tier 6 scoring)',
            }

            five_days_ago = self.run_date - timedelta(days=5)
            status = {}

            for table, description in required_tables.items():
                try:
                    # Count rows added in the last 5 days
                    if table == 'price_daily':
                        assert_safe_table(table)
                        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE date >= %s", (five_days_ago,))
                    elif table in ('buy_sell_daily', 'trend_template_data', 'technical_data_daily',
                                  'signal_quality_scores', 'swing_trader_scores', 'market_health_daily',
                                  'sector_ranking', 'industry_ranking', 'stock_scores'):
                        # Different tables use different date column names
                        if table == 'stock_scores':
                            col = 'updated_at'
                        elif table in ('sector_ranking', 'industry_ranking'):
                            col = 'date_recorded'
                        else:
                            col = 'date'
                        assert_safe_table(table)
                        assert_safe_column(col)
                        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} >= %s", (five_days_ago,))
                    else:
                        assert_safe_table(table)
                        cur.execute(f"SELECT COUNT(*) FROM {table} LIMIT 1")

                    row = cur.fetchone()
                    count = row[0] if row else 0
                    status[table] = count
                    flag = '[OK]' if count > 0 else '[EMPTY]'
                    if self.verbose:
                        logger.info(f"    {flag} {description:50s}: {count:,} rows (5d)")
                except Exception as e:
                    status[table] = 0
                    if self.verbose:
                        logger.warning(f"    [ERROR] {description}: {e}")

            # Alert if any critical table is empty
            empty_tables = [t for t, c in status.items() if c == 0]
            if empty_tables:
                empty_desc = ', '.join([required_tables[t] for t in empty_tables])
                logger.error(f"  [ALERT] Pipeline missing data in: {empty_desc}")
                logger.error(f"  Run the loaders to populate: {', '.join(empty_tables)}")
                self.alerts.critical(
                    f"Pipeline data gap: {empty_desc}. No signals can pass filters until data is loaded."
                )

        except Exception as e:
            logger.warning(f"Pipeline health check failed: {e}")

    def _report_signal_waterfall(self) -> None:
        """Log signal count at each filter tier for visibility on rejections."""
        conn = None
        cur = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            # Count total BUY signals for today
            cur.execute(
                "SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s AND signal = 'BUY'",
                (self.run_date,)
            )
            total_signals = cur.fetchone()[0] or 0

            # Count from trend_template_data where Stage 2 exists
            # (Stage 2 check is in filter_pipeline, using pre-filtered signals)
            cur.execute(
                """SELECT COUNT(DISTINCT symbol) FROM trend_template_data
                   WHERE date = %s AND weinstein_stage = 2""",
                (self.run_date,)
            )
            stage2_count = cur.fetchone()[0] or 0

            # Count rejections at each tier from filter_rejection_log (if table exists)
            tier_rejections = {}
            try:
                for tier_num, tier_name in enumerate(['Tier 1', 'Tier 2', 'Tier 3', 'Tier 4', 'Tier 5', 'Tier 6'], 1):
                    cur.execute(
                        f"SELECT COUNT(DISTINCT symbol) FROM filter_rejection_log WHERE eval_date = %s AND rejected_at_tier = %s",
                        (self.run_date, tier_num)
                    )
                    rejected = cur.fetchone()[0] or 0
                    tier_rejections[tier_name] = rejected
            except Exception:
                # Table may not exist or columns different; skip
                for tier_name in ['Tier 1', 'Tier 2', 'Tier 3', 'Tier 4', 'Tier 5', 'Tier 6']:
                    tier_rejections[tier_name] = 0

            # Final qualified count
            qualified = getattr(self, '_qualified_trades', [])
            final_count = len(qualified)

            if self.verbose or total_signals > 0:
                logger.info(f"\n  [WATERFALL] Signal filtering on {self.run_date}:")
                logger.info(f"    Total BUY signals:        {total_signals:4d}")
                logger.info(f"    Stage 2 (pre-pipeline):   {stage2_count:4d}")
                logger.info(f"    Tier 1 rejected:          {tier_rejections.get('Tier 1', 0):4d}")
                logger.info(f"    Tier 2 rejected:          {tier_rejections.get('Tier 2', 0):4d}")
                logger.info(f"    Tier 3 rejected:          {tier_rejections.get('Tier 3', 0):4d}")
                logger.info(f"    Tier 4 rejected:          {tier_rejections.get('Tier 4', 0):4d}")
                logger.info(f"    Tier 5 rejected:          {tier_rejections.get('Tier 5', 0):4d}")
                logger.info(f"    Tier 6 rejected:          {tier_rejections.get('Tier 6', 0):4d}")
                logger.info(f"    Final qualified trades:   {final_count:4d}")
                logger.info(f"  Interpretation: {self._interpret_waterfall(total_signals, stage2_count, tier_rejections, final_count)}")

        except Exception as e:
            logger.warning(f"Signal waterfall report failed: {e}")
        finally:
            if cur:
                try:
                    cur.close()
                except Exception as e:

                    logger.error(f"Unhandled exception: {e}")
            if conn:
                try:
                    conn.close()
                except Exception as e:

                    logger.error(f"Unhandled exception: {e}")

    def _interpret_waterfall(self, total: int, stage2: int, tier_rejections: Dict[str, int], final: int) -> str:
        """Interpret the signal waterfall to help diagnose 'no trades' situations."""
        if total == 0:
            return "No BUY signals generated today. Check buy_sell_daily loader or market conditions."
        if stage2 == 0:
            return f"{total} signals exist but NONE are Stage 2. RSI<30 in Stage 2 stocks is rare. Check market stage."
        if final > 0:
            return f"[OK] {final} candidates qualified. Ready to execute."

        # Find the biggest rejection point
        max_reject_tier = max(tier_rejections, key=tier_rejections.get) if tier_rejections else "Unknown"
        max_reject_count = tier_rejections.get(max_reject_tier, 0)
        return f"Stage 2 signals exist but {max_reject_count} rejected at {max_reject_tier}. Review config thresholds."

    # ---------- Phase implementations ----------

    def phase_1_data_freshness(self) -> bool:
        self.log_phase_start(1, 'DATA FRESHNESS CHECK')
        logger.debug(f"Phase 1: Starting data freshness check for run_date={self.run_date}")
        conn = None
        cur = None
        try:
            try:
                from algo.algo_pipeline_health import PipelineHealth
                health = PipelineHealth()
                health.connect()
                status = health.get_pipeline_status()
                health.log_health_check(status)
                health.disconnect()
                logger.debug(f"Phase 1: Pipeline health check complete - {status.healthy_count}/{status.total_count} healthy")

                if self.verbose:
                    logger.info(f"  [HEALTH] Pipeline: {status.healthy_count}/{status.total_count} tables healthy "
                               f"({status.coverage_pct:.0f}%)")

                # Log any critical alerts
                for alert in status.critical_alerts:
                    logger.error(f"  [CRITICAL] {alert}")
                    self.log_phase_result(1, 'pipeline_health', 'halt', alert)
                    return False

                # Log warnings but don't fail
                for warning in status.warnings:
                    logger.warning(f"  [WARNING] {warning}")

            except Exception as e:
                logger.warning(f"  [WARN] Pipeline health check failed: {e}")
                # Don't fail-close on health check error, let other checks handle it

            conn = get_db_connection()
            cur = conn.cursor()
            logger.debug("Phase 1: Database connection established")

            # In DEV mode, skip strict SLA/loader health checks
            if os.getenv('DEV_MODE', '').lower() in ('true', '1', 'yes'):
                logger.debug("Phase 1: Running in DEV mode - skipping strict SLA checks")
                logger.info("  [DEV MODE] Skipping SLA and loader health checks")
            else:
                try:
                    from utils.monitoring.loader_sla_tracker import get_tracker
                    tracker = get_tracker()
                    all_critical_ok, failures = tracker.check_critical_loaders()

                    if not all_critical_ok:
                        failure_msg = "; ".join(failures)
                        self.log_phase_result(1, 'loader_sla_check', 'halt',
                                              f'Critical loaders failed SLA: {failure_msg}')
                        logger.critical(f"Algo halted: {failure_msg}")
                        return False

                    logger.info("  [OK] All critical loaders have fresh data")

                except Exception as e:
                    logger.warning(f"  [WARN] SLA check failed: {e}")
                    # Don't fail-close on SLA check error, just warn

                try:
                    from algo.algo_loader_monitor import LoaderMonitor
                    monitor = LoaderMonitor()
                    monitor.connect()
                    try:
                        monitor.cur.execute("SELECT DISTINCT symbol FROM stock_scores WHERE composite_score > 50 LIMIT 5")
                        critical_symbols = [row[0] for row in monitor.cur.fetchall()]
                        if not critical_symbols:
                            critical_symbols = None
                        findings = monitor.audit_all(critical_symbols=critical_symbols)

                        critical_findings = [f for f in findings if f[0] == 'CRITICAL']
                        error_findings = [f for f in findings if f[0] == 'ERROR']

                        if critical_findings or error_findings:
                            self.alerts.send_loader_alert(findings)

                        if critical_findings:
                            messages = [f[2] for f in critical_findings]
                            self.log_phase_result(1, 'loader_health', 'halt',
                                                  f'Loader critical: {"; ".join(messages)}')
                            return False

                        # Fail-closed on ERROR if it's a data volume issue (ONLY for live trading on current date)
                        volume_error = [e for e in error_findings if 'low_daily_load_volume' in e[1]]
                        if volume_error:
                            from datetime import date
                            is_live_trading = (self.run_date == date.today())
                            for _, _, msg in volume_error:
                                if '0 symbols' in msg and is_live_trading:  # Only fail on live trading
                                    self.log_phase_result(1, 'loader_health', 'halt',
                                                          f'No data loaded today: {msg}')
                                    return False
                                elif not is_live_trading and self.verbose:
                                    logger.info(f"  [SKIP] Load volume check (historical run): {msg}")

                        # Other errors are just warnings
                        if error_findings and self.verbose:
                            for sev, check, msg in error_findings:
                                if 'low_daily_load_volume' not in check:
                                    logger.warning(f"  [LOADER ERROR] {check}: {msg}")
                    finally:
                        monitor.disconnect()
                except Exception as e:
                    logger.warning(f"  [WARN] Loader health check failed: {e}")
                    # Don't fail-close on monitor error, just warn
            cur.execute(
                """
                SELECT
                    (SELECT MAX(date) FROM price_daily WHERE symbol = 'SPY') AS spy_latest,
                    (SELECT MAX(date) FROM market_health_daily) AS mh_latest,
                    (SELECT MAX(date) FROM trend_template_data) AS tt_latest,
                    (SELECT MAX(date) FROM signal_quality_scores) AS sqs_latest,
                    (SELECT MAX(date) FROM buy_sell_daily) AS buys_latest
                """
            )
            row = cur.fetchone()
            if not row:
                logger.error("DATA FRESHNESS: Critical query returned no results")
                self.log_phase_result(1, 'data_freshness', 'error', 'Could not query data freshness')
                return False

            spy_date, mh_date, tt_date, sqs_date, buys_date = row
            checks = {
                'SPY price data': spy_date,
                'Market health': mh_date,
                'Trend template': tt_date,
                'Signal quality scores': sqs_date,
                'Buy/sell signals': buys_date,
            }
            table_keys = {
                'SPY price data': 'price_daily',
                'Market health': 'market_health_daily',
                'Trend template': 'trend_template_data',
                'Signal quality scores': 'signal_quality_scores',
                'Buy/sell signals': 'buy_sell_daily',
            }
            # In DEV_MODE, be lenient about data staleness (allow up to 365 days old)
            is_dev_mode = os.getenv('DEV_MODE', '').lower() in ('true', '1', 'yes')
            max_stale = 365 if is_dev_mode else int(self.config.get('max_data_staleness_days', 3))
            stale_items = []

            try:
                from algo.algo_metrics import MetricsPublisher
                _metrics = MetricsPublisher(dry_run=self.dry_run)
            except Exception:
                _metrics = None

            for name, d in checks.items():
                if d is None and not is_dev_mode:
                    # In DEV_MODE, allow missing data; in production fail
                    stale_items.append(f"{name}: missing")
                    if _metrics:
                        _metrics.put_data_freshness(table_keys[name], 999)
                elif d is not None:
                    age = (self.run_date - d).days
                    if _metrics:
                        _metrics.put_data_freshness(table_keys[name], age)
                    if age > max_stale and not is_dev_mode:
                        stale_items.append(f"{name}: {age}d old")
                    if self.verbose:
                        flag = '[OK]' if age <= max_stale else '[STALE]'
                        logger.info(f"  {flag} {name:25s}: latest {d} ({age}d ago)")

            if _metrics:
                _metrics.flush()

            if stale_items:
                self.alerts.send_position_alert(
                    'DATA',
                    'STALE_DATA_HALT',
                    f'Data freshness check failed. Stale items: {"; ".join(stale_items)}',
                    {'stale_items': stale_items, 'max_age_days': max_stale}
                )
                self.log_phase_result(1, 'data_freshness', 'fail',
                                      f'Stale: {"; ".join(stale_items)}')
                return False

            patrol_ok = self._check_data_patrol(cur)

            if not patrol_ok:
                return False

            # Margin health check (Phase 1 - production safeguard)
            try:
                from algo.algo_margin_monitor import MarginMonitor
                mm = MarginMonitor()
                margin_info = mm.get_margin_usage()
                if margin_info and margin_info['margin_usage_pct'] > 70:
                    self.alerts.send_position_alert(
                        'ACCOUNT',
                        'MARGIN_ALERT',
                        f'Margin usage {margin_info["margin_usage_pct"]:.1f}% (threshold: 70%)',
                        margin_info
                    )
                    if self.verbose:
                        logger.warning(f"  [MARGIN] Usage {margin_info['margin_usage_pct']:.1f}% - approaching limit")
                elif self.verbose and margin_info:
                    logger.info(f"  [OK] Margin: {margin_info['margin_usage_pct']:.1f}% usage")
            except Exception as e:
                logger.warning(f'Margin check failed: {e}')

            # Pipeline health check: verify all required tables have recent data
            self._check_pipeline_health(cur)

            self.log_phase_result(1, 'data_freshness', 'success',
                                  'All data fresh within window')
            return True
        except Exception as e:
            self.log_phase_result(1, 'data_freshness', 'error', str(e))
            return False
        finally:
            if cur:
                try:
                    cur.close()
                except Exception as e:

                    logger.error(f"Unhandled exception: {e}")
            if conn:
                try:
                    conn.close()
                except Exception as e:

                    logger.error(f"Unhandled exception: {e}")

    def phase_2_circuit_breakers(self) -> bool:
        self.log_phase_start(2, 'CIRCUIT BREAKERS')
        try:
            from algo.algo_circuit_breaker import CircuitBreaker
            cb = CircuitBreaker(self.config)
            result = cb.check_all(self.run_date)

            if self.verbose:
                for name, state in result['checks'].items():
                    flag = '[HALT]' if state.get('halted') else '[OK]  '
                    logger.info(f"  {flag} {name:22s}: {state.get('reason', '')}")

            # Publish per-breaker CloudWatch metrics (non-blocking)
            try:
                with MetricsPublisher(dry_run=self.dry_run) as _m:
                    for name, state in result.get('checks', {}).items():
                        _m.put_circuit_breaker(name, bool(state.get('halted')))
            except Exception as e:

                logger.error(f"Unhandled exception: {e}")

            try:
                from algo.algo_market_events import MarketEventHandler
                meh = MarketEventHandler(self.config)
                cb_result = meh.check_market_circuit_breaker()
                if cb_result and cb_result.get('triggered'):
                    halt_level = cb_result.get('level', '?')
                    halt_reason = cb_result.get('reason', 'circuit breaker triggered')
                    if self.verbose:
                        logger.info(f"  [HALT] circuit_breaker_L{halt_level:>1s}: {halt_reason}")
                    self.alerts.send_position_alert(
                        'PORTFOLIO',
                        'MARKET_CIRCUIT_BREAKER',
                        f'Market circuit breaker L{halt_level} triggered: {halt_reason}',
                        {'level': halt_level, 'reason': halt_reason}
                    )
                    self.log_phase_result(2, 'market_circuit_breaker', 'halt',
                                        f'L{halt_level} breaker active: {halt_reason}')
                    return False
            except Exception as e:
                self.log_phase_result(2, 'market_circuit_breaker', 'warn', f'check failed: {e}')

            if result['halted']:
                halt_reasons = result.get("halt_reasons", ["unknown"])
                self.alerts.send_position_alert(
                    'PORTFOLIO',
                    'ACCOUNT_CIRCUIT_BREAKER',
                    f'Account circuit breaker triggered: {"; ".join(halt_reasons)}',
                    {'halt_reasons': halt_reasons}
                )
                self.log_phase_result(2, 'circuit_breakers', 'halt',
                                      f'Halted: {"; ".join(halt_reasons)}')
                return False
            self.log_phase_result(2, 'circuit_breakers', 'success', 'all clear')
            return True
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result(2, 'circuit_breakers', 'error', str(e))
            return False

    def phase_3_position_monitor(self) -> List[Dict[str, Any]]:
        self.log_phase_start(3, 'POSITION MONITOR')
        try:
            from algo.algo_position_monitor import PositionMonitor
            from algo.algo_market_events import MarketEventHandler
            monitor = PositionMonitor(self.config)

            try:
                meh = MarketEventHandler(self.config)
                open_positions = monitor.get_open_positions() or []
                halts_found = []
                for pos in open_positions:
                    halt_check = meh.check_single_stock_halt(pos.get('symbol') or pos.get('name', ''))
                    if halt_check and halt_check.get('halted'):
                        symbol = pos.get('symbol') or pos.get('name', '')
                        halts_found.append(symbol)
                        if self.verbose:
                            logger.warning(f"  [WARN] {symbol} halted — pending orders cancelled")
                if halts_found:
                    self.log_phase_result(3, 'single_stock_halts', 'warn',
                                        f'{len(halts_found)} symbols halted: {", ".join(halts_found)}')
            except Exception as e:
                logger.warning(f"Halt check failed for position: {e}")
                self.log_phase_result(3, 'halt_check_error', 'warn', f'Halt check failed: {str(e)[:100]}')

            stale_result = monitor.check_stale_orders(self.run_date)
            if stale_result['status'] == 'STALE_ORDERS_FOUND':
                self.alerts.send_position_alert(
                    'STALE_ORDERS',
                    'STALE_ORDER_ALERT',
                    f'{stale_result["count"]} orders pending >1 hour',
                    {'orders': stale_result['count']}
                )

            recommendations = monitor.review_positions(self.run_date)

            n_raise_stop = sum(1 for r in recommendations if r['action'] == 'RAISE_STOP')
            n_early_exit = sum(1 for r in recommendations if r['action'] == 'EARLY_EXIT')
            n_hold = sum(1 for r in recommendations if r['action'] == 'HOLD')
            self.log_phase_result(
                3, 'position_monitor', 'success',
                f'{len(recommendations)} positions: {n_hold} hold, {n_raise_stop} raise-stop, {n_early_exit} early-exit',
            )
            self._position_recs = recommendations
            return True
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result(3, 'position_monitor', 'error', str(e))
            self._position_recs = []
            return True   # fail-open

    def phase_3a_reconciliation(self) -> Dict[str, Any]:
        """Check that DB positions match Alpaca account holdings.

        FAIL-OPEN: alerts on divergence but doesn't block trading.
        """
        self.log_phase_start('3a', 'POSITION RECONCILIATION')
        try:
            from algo.algo_reconciliation import PositionReconciler
            reconciler = PositionReconciler()
            result = reconciler.reconcile()

            if result.get('status') in ('skipped', 'error'):
                self.log_phase_result('3a', 'reconciliation', 'alert',
                                      result.get('reason', 'unknown issue'))
            elif result.get('critical_count', 0) > 0:
                self.alerts.send_position_alert(
                    'RECONCILIATION',
                    'CRITICAL',
                    f'{result["critical_count"]} untracked Alpaca positions',
                    result.get('issues', [])[:5]
                )
                self.log_phase_result('3a', 'reconciliation', 'alert',
                                      f'Critical divergence: {result["critical_count"]} issues')
            elif result.get('error_count', 0) > 0:
                self.alerts.send_position_alert(
                    'RECONCILIATION',
                    'ERROR',
                    f'{result["error_count"]} missing/closed positions in Alpaca',
                    result.get('issues', [])[:5]
                )
                self.log_phase_result('3a', 'reconciliation', 'alert',
                                      f'{result["error_count"]} position errors')
            else:
                self.log_phase_result('3a', 'reconciliation', 'success',
                                      f'{result.get("db_positions", 0)} positions reconciled OK')
            return True  # fail-open
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result('3a', 'reconciliation', 'error', str(e))
            return True  # fail-open

    def phase_3b_exposure_policy(self) -> Dict[str, Any]:
        """Apply market exposure tier policy to existing positions.

        Tighten stops on extended winners, force partial profits, and force-exit
        losers when in CORRECTION tier — all per the active exposure regime.
        """
        self.log_phase_start('3b', 'EXPOSURE POLICY ACTIONS')
        try:
            # Refresh market exposure first
            from algo.algo_market_exposure import MarketExposure
            from algo.algo_market_exposure_policy import ExposurePolicy
            me = MarketExposure()
            exposure = me.compute(self.run_date)
            logger.info(f"  Exposure: {exposure['exposure_pct']}% ({exposure['regime']})")
            if exposure.get('halt_reasons'):
                logger.info(f"  Halt reasons: {'; '.join(exposure['halt_reasons'])}")

            policy = ExposurePolicy(self.config)
            constraints = policy.get_entry_constraints(self.run_date)
            self._exposure_constraints = constraints
            if constraints:
                logger.info(f"  Tier: {constraints['tier_name']} — {constraints['description']}")
                logger.info(f"    risk_mult={constraints['risk_multiplier']}, "
                            f"max_new/day={constraints['max_new_positions_today']}, "
                            f"min_grade={constraints['min_swing_grade']}, "
                            f"halt_entries={constraints['halt_new_entries']}")

            actions = policy.review_existing_positions(self.run_date)
            self._exposure_actions = actions

            if not actions:
                logger.info(f"  No exposure-policy actions for {len(getattr(self, '_position_recs', []))} open positions")
                self.log_phase_result('3b', 'exposure_policy', 'success',
                                      f'tier={constraints["tier_name"] if constraints else "n/a"}, no actions')
                return True

            counts = {'tighten_stop': 0, 'partial_exit': 0, 'force_exit': 0}
            for action in actions:
                counts[action['action']] = counts.get(action['action'], 0) + 1

            logger.info(f"\n  {len(actions)} exposure-policy actions:")
            for a in actions:
                logger.info(f"    {a['symbol']:6s} -> {a['action'].upper():15s} "
                            f"R={a.get('r_multiple', 0):+.2f}  {a['reason']}")

            self.log_phase_result(
                '3b', 'exposure_policy', 'success',
                f"tier={constraints['tier_name']}, "
                f"{counts.get('tighten_stop', 0)} tighten, "
                f"{counts.get('partial_exit', 0)} partial, "
                f"{counts.get('force_exit', 0)} force_exit"
            )
            return True
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result('3b', 'exposure_policy', 'error', str(e))
            self._exposure_actions = []
            self._exposure_constraints = None
            return True  # fail-open

    def phase_4_exit_execution(self) -> List[Dict[str, Any]]:
        self.log_phase_start(4, 'EXIT EXECUTION')
        if self._check_halt_flag():
            return False
        try:
            from algo.algo_trade_executor import TradeExecutor
            from algo.algo_exit_engine import ExitEngine

            # Detect Phase 3 crash: if position monitor errored, _position_recs is []
            # but we may have real open positions. Log a critical alert so we know.
            position_recs = getattr(self, '_position_recs', None)
            if position_recs is None:
                logger.critical("Phase 4: _position_recs not set — Phase 3 may not have run")
            elif len(position_recs) == 0:
                # "no positions" from "Phase 3 crashed with fail-open"
                try:
                    conn_chk = get_db_connection()
                    with conn_chk:
                        with conn_chk.cursor() as cur_chk:
                            cur_chk.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
                            open_count = cur_chk.fetchone()[0]
                    if open_count > 0:
                        logger.error(
                            f"Phase 4: _position_recs is empty but {open_count} open positions exist "
                            "— Phase 3 likely crashed (fail-open). Early-exit logic will be skipped."
                        )
                except Exception as e:

                    logger.error(f"Unhandled exception: {e}")

            executor = TradeExecutor(self.config)
            exit_count = 0
            stop_raises = 0
            errors = 0

            # 4a-prime. Apply exposure-policy actions FIRST (highest priority)
            for action in getattr(self, '_exposure_actions', []):
                try:
                    if self.dry_run:
                        if self.verbose:
                            logger.info(f"  [DRY-RUN] {action['symbol']}: {action['action'].upper()} "
                                        f"({action['reason']})")
                        continue

                    if action['action'] == 'force_exit':
                        # Fetch current price for accurate P&L
                        cur_price = 0
                        try:
                            conn_tmp = get_db_connection()
                            try:
                                cur_tmp = conn_tmp.cursor()
                                cur_tmp.execute(
                                    "SELECT current_price FROM algo_positions WHERE position_id = %s",
                                    (action['position_id'],),
                                )
                                row_tmp = cur_tmp.fetchone()
                                cur_price = float(row_tmp[0]) if row_tmp and row_tmp[0] else 0
                            finally:
                                cur_tmp.close()
                        except Exception as e:
                            logger.warning(f"  Warning: Could not fetch price for force_exit: {e}")
                        finally:
                            try:
                                conn_tmp.close()
                            except Exception as e:

                                logger.error(f"Unhandled exception: {e}")

                        if cur_price <= 0:
                            logger.error(f"  ERROR: force_exit cannot proceed — no valid current price")
                            continue

                        result = executor.exit_trade(
                            trade_id=action['trade_id'],
                            exit_price=cur_price,
                            exit_reason=action['reason'],
                            exit_fraction=1.0,
                            exit_stage='exposure_force_exit',
                        )
                        if result.get('success'):
                            exit_count += 1
                            logger.info(f"  EXPOSURE FORCE-EXIT: {result.get('message', action['symbol'])}")
                        else:
                            errors += 1

                    elif action['action'] == 'partial_exit':
                        # Need current price — fetch
                        cur_price = 0
                        try:
                            conn = get_db_connection()
                            try:
                                cur = conn.cursor()
                                cur.execute(
                                    "SELECT current_price FROM algo_positions WHERE position_id = %s",
                                    (action['position_id'],),
                                )
                                row = cur.fetchone()
                                cur_price = float(row[0]) if row and row[0] else 0
                            finally:
                                cur.close()
                        except Exception as e:
                            logger.warning(f"  Warning: Could not fetch current price for {action['position_id']}: {e}")
                        finally:
                            try:
                                conn.close()
                            except Exception as e:

                                logger.error(f"Unhandled exception: {e}")
                        if cur_price > 0:
                            result = executor.exit_trade(
                                trade_id=action['trade_id'],
                                exit_price=cur_price,
                                exit_reason=action['reason'],
                                exit_fraction=action.get('exit_fraction', 0.5),
                                exit_stage='exposure_partial',
                                new_stop_price=action.get('new_stop'),
                            )
                            if result.get('success'):
                                exit_count += 1
                                logger.info(f"  EXPOSURE PARTIAL: {result['message']}")

                    elif action['action'] == 'tighten_stop':
                        try:
                            conn = get_db_connection()
                            try:
                                cur = conn.cursor()
                                cur.execute(
                                    "UPDATE algo_positions SET current_stop_price = %s WHERE position_id = %s",
                                    (action['new_stop'], action['position_id']),
                                )
                                conn.commit()
                                stop_raises += 1
                                if self.verbose:
                                    logger.info(f"  EXPOSURE TIGHTEN {action['symbol']}: stop -> ${action['new_stop']:.2f}")
                            finally:
                                cur.close()
                        except Exception as e:
                            errors += 1
                            logger.error(f"  Tighten failed for {action['symbol']}: {e}")
                        finally:
                            try:
                                conn.close()
                            except Exception as e:

                                logger.error(f"Unhandled exception: {e}")
                except Exception as e:
                    errors += 1
                    logger.error(f"  Error on exposure action {action.get('symbol')}: {e}")

            # 4a. Apply position monitor recommendations (early exits + stop raises)
            for rec in getattr(self, '_position_recs', []):
                try:
                    if self.dry_run:
                        if self.verbose:
                            logger.info(f"  [DRY-RUN] {rec['symbol']}: {rec['action']} ({rec['action_reason']})")
                        continue

                    if rec['action'] == 'EARLY_EXIT':
                        result = executor.exit_trade(
                            trade_id=rec['trade_id'],
                            exit_price=rec['current_price'],
                            exit_reason=rec['action_reason'],
                            exit_fraction=1.0,
                            exit_stage='early_exit',
                        )
                        if result.get('success'):
                            exit_count += 1
                            if self.verbose:
                                logger.info(f"  EARLY EXIT: {result['message']}")
                        else:
                            errors += 1
                    elif rec['action'] == 'RAISE_STOP' and rec.get('new_stop_recommended'):
                        conn = None
                        cur = None
                        try:
                            conn = get_db_connection()
                            cur = conn.cursor()
                            cur.execute(
                                "UPDATE algo_positions SET current_stop_price = %s "
                                "WHERE position_id = %s AND status = %s",
                                (rec['new_stop_recommended'], rec['position_id'], PositionStatus.OPEN.value),
                            )
                            conn.commit()
                            stop_raises += 1
                            if self.verbose:
                                logger.info(f"  RAISED STOP {rec['symbol']}: ${rec['active_stop']:.2f} -> ${rec['new_stop_recommended']:.2f}")
                        except Exception as e:
                            errors += 1
                            logger.error(f"  Stop-raise failed for {rec['symbol']}: {e}")
                        finally:
                            if cur:
                                try:
                                    cur.close()
                                except Exception as e:

                                    logger.error(f"Unhandled exception: {e}")
                            if conn:
                                try:
                                    conn.close()
                                except Exception as e:

                                    logger.error(f"Unhandled exception: {e}")
                except Exception as e:
                    errors += 1
                    logger.error(f"  Error on {rec.get('symbol')}: {e}")

            # 4b. Exit engine — tiered targets, stops, time, Minervini break
            if not self.dry_run:
                engine = ExitEngine(self.config)
                engine_exits = engine.check_and_execute_exits(self.run_date)
                exit_count += engine_exits

            self.log_phase_result(
                4, 'exit_execution', 'success',
                f'{exit_count} exits, {stop_raises} stop-raises, {errors} errors',
            )
            return True
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result(4, 'exit_execution', 'error', str(e))
            return False  # FAIL-CLOSED: Exit failures could leave positions unbalanced

    def phase_4b_pyramid_adds(self) -> List[Dict[str, Any]]:
        """Add to winners (Livermore) — runs after exits, before new entries."""
        self.log_phase_start('4b', 'PYRAMID ADDS (winners)')
        try:
            from algo.algo_pyramid import PyramidEngine
            engine = PyramidEngine(self.config)
            recs = engine.evaluate_pyramid_adds(self.run_date)

            if not recs:
                self.log_phase_result('4b', 'pyramid_adds', 'success', 'No qualifying adds')
                return True

            executed = 0
            for r in recs:
                if self.dry_run:
                    logger.info(f"  [DRY-RUN] PYRAMID {r['symbol']} #{r['add_number']}: "
                                f"+{r['add_size_shares']} sh @ ${r['add_price']:.2f}")
                    continue
                result = engine.execute_add(r)
                if result.get('success'):
                    executed += 1
                    logger.info(f"  PYRAMID: {result['message']}")

            self.log_phase_result('4b', 'pyramid_adds', 'success',
                                  f'{len(recs)} recommended, {executed} executed')
            return True
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result('4b', 'pyramid_adds', 'error', str(e))
            return True

    def phase_5_signal_generation(self) -> List[Dict[str, Any]]:
        self.log_phase_start(5, 'SIGNAL GENERATION & RANKING')
        if self._check_halt_flag():
            return False
        try:
            from algo.algo_filter_pipeline import FilterPipeline
            exposure_mult = 1.0
            if hasattr(self, '_exposure_constraints') and self._exposure_constraints:
                exposure_mult = self._exposure_constraints.get('risk_multiplier', 1.0)
            pipeline = FilterPipeline(exposure_risk_multiplier=exposure_mult)
            qualified = pipeline.evaluate_signals(self.run_date)

            self._qualified_trades = qualified

            # Signal count waterfall report (for visibility on where signals die)
            self._report_signal_waterfall()

            self.log_phase_result(
                5, 'signal_generation', 'success',
                f'{len(qualified)} qualified trades after all 6 tiers',
            )
            self.phase_results[5]['signals_evaluated'] = len(qualified)
            return True
        except RuntimeError as e:
            logger.critical(f"PHASE 5 HALT — portfolio value unavailable, no new entries: {e}")
            try:
                with MetricsPublisher(dry_run=self.dry_run) as _m:
                    _m.put_circuit_breaker('PortfolioValueUnavailable', fired=True)
            except Exception as e:

                logger.error(f"Unhandled exception: {e}")
            self.log_phase_result(5, 'signal_generation', 'halt', str(e))
            self._qualified_trades = []
            return True
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result(5, 'signal_generation', 'error', str(e))
            self._qualified_trades = []
            return True

    def phase_6_entry_execution(self) -> List[Dict[str, Any]]:
        self.log_phase_start(6, 'ENTRY EXECUTION')
        if self._check_halt_flag():
            return False
        try:
            executor = TradeExecutor(self.config)
            qualified = getattr(self, '_qualified_trades', [])
            constraints = getattr(self, '_exposure_constraints', None)

            # PRE-TRADE DATA QUALITY GATE: Verify all required data is fresh and complete
            data_quality_ok, dq_issues, dq_warnings = self._validate_pre_trade_data_quality()
            if not data_quality_ok:
                self.log_phase_result(
                    6, 'entry_execution', 'halt',
                    f'Data quality gate failed: {"; ".join(dq_issues)}'
                )
                return False
            if dq_warnings:
                logger.warning(f"Data quality warnings: {'; '.join(dq_warnings)}")

            # Apply exposure tier entry constraints
            if constraints and constraints.get('halt_new_entries'):
                self.log_phase_result(
                    6, 'entry_execution', 'success',
                    f"Tier '{constraints['tier_name']}' halts new entries — 0 entries"
                )
                return True

            # Filter qualified trades by min_swing_grade and min_swing_score
            if constraints:
                min_score = constraints.get('min_swing_score', 60.0)
                grade_order = ['F', 'D', 'C', 'B', 'A', 'A+']
                min_grade = constraints.get('min_swing_grade', 'B')
                min_grade_idx = grade_order.index(min_grade) if min_grade in grade_order else 3
                before = len(qualified)
                # Safe grade lookup: unknown grades default to 'F' (worst grade)
                def get_grade_idx(grade):
                    try:
                        return grade_order.index(grade) if grade in grade_order else grade_order.index('F')
                    except ValueError:
                        return grade_order.index('F')
                qualified = [
                    t for t in qualified
                    if (t.get('swing_score', 0) >= min_score and
                        get_grade_idx(t.get('swing_grade', 'F')) >= min_grade_idx)
                ]
                if len(qualified) < before:
                    logger.info(f"  Tier filter: {before} -> {len(qualified)} "
                                f"(min_score={min_score}, min_grade={min_grade})")

            # Determine open slots
            conn = None
            cur = None
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = %s", (PositionStatus.OPEN.value,))
                open_count = cur.fetchone()[0] or 0
            except Exception:
                open_count = 0
            finally:
                if cur:
                    try:
                        cur.close()
                    except Exception as e:

                        logger.error(f"Unhandled exception: {e}")
                if conn:
                    try:
                        conn.close()
                    except Exception as e:

                        logger.error(f"Unhandled exception: {e}")
            max_positions = int(self.config.get('max_positions', 12))
            open_slots = max(0, max_positions - open_count)

            # Apply daily entry cap from exposure tier
            if constraints:
                daily_cap = constraints.get('max_new_positions_today', 5)
                open_slots = min(open_slots, daily_cap)

            logger.info(f"  Open positions: {open_count}/{max_positions}, slots available: {open_slots}")
            if constraints:
                logger.info(f"  Tier '{constraints['tier_name']}' caps daily entries at {constraints['max_new_positions_today']}")

            if open_slots == 0:
                self.log_phase_result(6, 'entry_execution', 'success',
                                      f'No room (already {open_count}/{max_positions} or daily cap)')
                return True
            if not qualified:
                self.log_phase_result(6, 'entry_execution', 'success',
                                      'No qualified trades meet tier requirements')
                return True

            # Margin entry gate (Phase 6 - production safeguard)
            try:
                mm = MarginMonitor()
                can_enter, margin_reason = mm.can_enter_new_position()
                if not can_enter:
                    self.log_phase_result(
                        6, 'entry_execution', 'success',
                        f'Margin gate blocked entries: {margin_reason}'
                    )
                    return True
                elif self.verbose:
                    logger.info(f"  [OK] Margin gate: Can enter new positions")
            except Exception as e:
                logger.warning(f'Margin gate check failed: {e}')

            entered = 0
            blocked = 0
            errors = 0
            for trade in qualified[:open_slots]:
                if self.dry_run:
                    if self.verbose:
                        logger.info(f"  [DRY-RUN] WOULD ENTER {trade['symbol']}: "
                                    f"{trade['shares']}sh @ ${trade['entry_price']:.2f} "
                                    f"stop ${trade['stop_loss_price']:.2f}")
                    continue
                try:
                    # Pull stage_phase + base_type detail from advanced components
                    adv = trade.get('advanced_components', {}) or {}
                    setup = (trade.get('swing_components', {}) or {}).get('setup_quality', {}).get('detail', {})
                    trend_d = (trade.get('swing_components', {}) or {}).get('trend_quality', {}).get('detail', {})

                    stop_method = getattr(trade, 'stop_method', None) or 'base_type_stop'
                    stop_reasoning = getattr(trade, 'stop_reasoning', None)

                    result = executor.execute_trade(
                        symbol=trade['symbol'],
                        entry_price=trade['entry_price'],
                        shares=trade['shares'],
                        stop_loss_price=trade['stop_loss_price'],
                        target_1_price=trade.get('target_1_price'),
                        target_2_price=trade.get('target_2_price'),
                        target_3_price=trade.get('target_3_price'),
                        signal_date=self.run_date,
                        sqs=int(trade.get('sqs', 0)),
                        trend_score=int(trade.get('trend_score', 0)),
                        # Reasoning metadata:
                        swing_score=trade.get('swing_score'),
                        swing_grade=trade.get('swing_grade'),
                        base_type=setup.get('base_type'),
                        base_quality=setup.get('base_quality'),
                        stage_phase=trend_d.get('phase'),
                        sector=trade.get('sector'),
                        industry=trade.get('industry'),
                        rs_percentile=(adv.get('relative_strength', {}) or {}).get('value'),
                        market_exposure_at_entry=constraints.get('exposure_pct') if constraints else None,
                        exposure_tier_at_entry=constraints.get('tier_name') if constraints else None,
                        stop_method=stop_method,
                        stop_reasoning=stop_reasoning,
                        swing_components=trade.get('swing_components'),
                        advanced_components=trade.get('advanced_components'),
                    )
                    if result.get('success'):
                        entered += 1
                        if self.verbose:
                            logger.info(f"  ENTERED: {result['message']}")
                    elif result.get('duplicate'):
                        blocked += 1
                    else:
                        errors += 1
                        logger.error(f"  Failed {trade['symbol']}: {result.get('message')}")
                except Exception as e:
                    errors += 1
                    logger.error(f"  Exception on {trade['symbol']}: {e}", exc_info=True)

            # Circuit breaker: if >50% of trades fail in a batch, halt
            if len(qualified) > 2 and errors > 0:
                failure_rate = errors / (entered + blocked + errors)
                if failure_rate > 0.5:
                    logger.critical(f"BATCH FAILURE RATE {failure_rate:.0%} exceeds 50% threshold ({errors}/{entered + blocked + errors}) — halting Phase 6")
                    self.log_phase_result(6, 'entry_execution', 'error', f'Batch failure rate {failure_rate:.0%} ({errors} of {entered + blocked + errors})')
                    return False  # FAIL-CLOSED on batch failures

            self.log_phase_result(
                6, 'entry_execution', 'success',
                f'{entered} entered, {blocked} blocked (duplicates), {errors} errors',
            )
            self.phase_results[6]['trades_executed'] = entered
            return True
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result(6, 'entry_execution', 'error', str(e))
            return False  # FAIL-CLOSED: Entry execution failures could result in partial positions

    def phase_7_reconcile(self) -> Dict[str, Any]:
        self.log_phase_start(7, 'RECONCILIATION & SNAPSHOT')
        if self._check_halt_flag():
            return False
        try:
            from algo.algo_daily_reconciliation import DailyReconciliation
            recon = DailyReconciliation(self.config)
            result = recon.run_daily_reconciliation(self.run_date)
            status = 'success' if result.get('success') else 'error'
            summary = (
                f'Portfolio ${result.get("portfolio_value", 0):,.2f}, '
                f'{result.get("positions", 0)} positions, '
                f'unrealized P&L ${result.get("unrealized_pnl", 0):+,.2f}'
            ) if result.get('success') else result.get('error', 'unknown')
            self.log_phase_result(7, 'reconciliation', status, summary)

            # Compute and log live performance metrics (Phase 4)
            perf_status = 'warn'
            perf_summary = 'N/A'
            try:
                from algo.algo_performance import LivePerformance
                perf = LivePerformance(self.config)
                perf_report = perf.generate_daily_report(self.run_date)
                if perf_report and perf_report.get('status') == 'ok':
                    perf_status = 'success'
                    perf_summary = (
                        f"Sharpe {perf_report.get('rolling_sharpe_252d', 'N/A')}, "
                        f"Win rate {perf_report.get('win_rate_50t', 'N/A')}%, "
                        f"Expectancy {perf_report.get('expectancy', 'N/A')}"
                    )
                elif perf_report:
                    perf_summary = perf_report.get('message', 'insufficient data')
                else:
                    perf_summary = 'failed to generate report'
            except Exception as e:
                perf_summary = f'error: {str(e)[:60]}'
            finally:
                self.log_phase_result(7, 'performance', perf_status, perf_summary)

            risk_status = 'warn'
            risk_summary = 'N/A'
            try:
                from algo.algo_var import PortfolioRisk
                risk = PortfolioRisk(self.config)
                risk_report = risk.generate_daily_risk_report(self.run_date)
                if risk_report and risk_report.get('status') == 'ok':
                    risk_status = 'success'
                    var_pct = risk_report.get('var_metrics', {}).get('var_pct', 'N/A') if risk_report.get('var_metrics') else 'N/A'
                    conc_pct = risk_report.get('concentration', {}).get('top_5_concentration_pct', 'N/A') if risk_report.get('concentration') else 'N/A'
                    alerts_count = len(risk_report.get('alerts', []))
                    risk_summary = (
                        f"VaR {var_pct}%, Concentration {conc_pct}%"
                        + (f", {alerts_count} alerts" if alerts_count else "")
                    )
                elif risk_report:
                    risk_summary = risk_report.get('message', 'insufficient data')
                else:
                    risk_summary = 'failed to generate report'
            except Exception as e:
                risk_summary = f'error: {str(e)[:60]}'
            finally:
                self.log_phase_result(7, 'risk_metrics', risk_status, risk_summary)

            self.phase_results.setdefault(7, {})['open_positions'] = result.get('positions', 0)
            return True
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result(7, 'reconciliation', 'error', str(e))
            return True

    # ---------- Main entrypoint ----------

    def run(self) -> Dict[str, Any]:
        logger.info(f"\n{'#'*70}")
        logger.info(f"#   ALGO ORCHESTRATOR — {self.run_date}  ({'DRY RUN' if self.dry_run else 'LIVE'})")
        logger.info(f"#   run_id: {self.run_id}")
        logger.info(f"{'#'*70}")

        # Loudly warn if DEV_MODE is active — this bypasses all data freshness and patrol gates
        if os.getenv('DEV_MODE', '').lower() in ('true', '1', 'yes'):
            logger.critical("=" * 70)
            logger.critical("[WARNING]  DEV_MODE=true IS ACTIVE — ALL DATA QUALITY GATES ARE BYPASSED")
            logger.critical("   Do NOT run with DEV_MODE in production or with real capital.")
            logger.critical("=" * 70)
            if not self.dry_run:
                raise RuntimeError(
                    "ABORT: DEV_MODE=true with ORCHESTRATOR_DRY_RUN=false is not allowed. "
                    "Set ORCHESTRATOR_DRY_RUN=true or disable DEV_MODE before running live trading."
                )

        if not MarketCalendar.is_trading_day(self.run_date):
            status = MarketCalendar.market_status(datetime.combine(self.run_date, datetime.min.time()))
            logger.info(f"\n⏸️  Market closed: {status['reason']}")
            logger.info("Skipping all trading phases.\n")
            return {'success': False, 'error': f"Market closed: {status['reason']}"}

        # Concurrency lock — prevent two orchestrators running at once
        # which would risk duplicate trades or double-counting circuit breakers
        if not self._acquire_run_lock():
            logger.error(f"\nABORT: Could not acquire run lock. Another orchestrator instance is running.")
            return {'success': False, 'error': 'Lock acquisition failed'}

        try:
            logger.info("\nRunning critical data patrol checks...")
            try:
                from algo.algo_data_patrol import DataPatrol
                patrol = DataPatrol()
                patrol.run(quick=True)  # Only run the 5 critical checks, not the full 16-check suite
            except Exception as e:
                logger.error(f"  [WARN] Data patrol failed: {e}")


            if not self._check_db_connectivity():
                failures = self._increment_db_failure_counter()
                if failures >= 3:
                    self.degraded_mode = True
                    logger.error(f"\n[CRITICAL] Database down for {failures} consecutive runs — ENTERING DEGRADED MODE")
                    logger.info("Skipping all trading phases. Continuing with monitoring only.")
                    try:
                        from algo.algo_notifications import notify
                        notify(
                            'critical',
                            title='Database Circuit Breaker Activated',
                            message=f'DB unreachable for {failures} runs. System in degraded mode. No trading.'
                        )
                    except Exception as e:

                        logger.error(f"Unhandled exception: {e}")
                    # Still try to reconcile and alert
                    self.phase_7_reconcile()
                    return self._final_report()
                else:
                    logger.error(f"\n[ERROR] Database connectivity failed ({failures}/3). Will halt if persists.")
                    return self._final_report()
            else:
                self._reset_db_failure_counter()

            if getattr(self, 'skip_freshness', False):
                logger.info("\nNOTE: Phase 1 freshness gate skipped (--skip-freshness flag set).")
                self.log_phase_result(1, 'freshness_bypassed', 'override',
                                     '--skip-freshness flag used — data freshness check skipped')
            else:
                try:
                    with TimeBlock("phase_1_data_freshness"):
                        if not self.phase_1_data_freshness():
                            logger.error("\nFAIL-CLOSED: Data freshness check failed. Halting pipeline.")
                            self.log_phase_result(1, 'data_freshness', 'fail', 'Stale or missing critical data')
                            return self._final_report()
                except Exception as e:
                    logger.error(f"\nERROR in phase 1 (data freshness): {e}. Halting pipeline.")
                    self.log_phase_result(1, 'data_freshness', 'error', str(e))
                    return self._final_report()

            with TimeBlock("phase_2_circuit_breakers"):
                phase_2_passed = self.phase_2_circuit_breakers()

            if not phase_2_passed:
                logger.info("\nHALT: Circuit breaker fired. Will still review positions but skip new entries.")
                self.phase_3a_reconciliation()
                self.phase_3_position_monitor()
                self.phase_3b_exposure_policy()
                self.phase_4_exit_execution()
                self.phase_7_reconcile()
                return self._final_report()

            # Phase 3a: Reconciliation
            try:
                with TimeBlock("phase_3a_reconciliation"):
                    self.phase_3a_reconciliation()
                logger.info("[OK] Phase 3a (Reconciliation) completed")
            except Exception as e:
                logger.error(f"✗ Phase 3a (Reconciliation) failed: {e}", exc_info=True)
                self.log_phase_result(3, 'reconciliation', 'error', str(e))

            # Phase 3: Position Monitor
            try:
                with TimeBlock("phase_3_position_monitor"):
                    self.phase_3_position_monitor()
                logger.info("[OK] Phase 3 (Position Monitor) completed")
            except Exception as e:
                logger.error(f"✗ Phase 3 (Position Monitor) failed: {e}", exc_info=True)
                self.log_phase_result(3, 'position_monitor', 'error', str(e))

            # Phase 3b: Exposure Policy
            try:
                with TimeBlock("phase_3b_exposure_policy"):
                    self.phase_3b_exposure_policy()
                logger.info("[OK] Phase 3b (Exposure Policy) completed")
            except Exception as e:
                logger.error(f"✗ Phase 3b (Exposure Policy) failed: {e}", exc_info=True)
                self.log_phase_result('3b', 'exposure_policy', 'error', str(e))

            # Phase 4: Exit Execution
            try:
                with TimeBlock("phase_4_exit_execution"):
                    result = self.phase_4_exit_execution()
                    if result is False:
                        logger.critical("HALT: Phase 4 (Exit Execution) returned False — stopping pipeline")
                        return self._final_report()
                logger.info("[OK] Phase 4 (Exit Execution) completed")
            except Exception as e:
                logger.error(f"✗ Phase 4 (Exit Execution) failed: {e}", exc_info=True)
                self.log_phase_result(4, 'exit_execution', 'error', str(e))

            # Phase 4b: Pyramid Adds
            try:
                with TimeBlock("phase_4b_pyramid_adds"):
                    self.phase_4b_pyramid_adds()
                logger.info("[OK] Phase 4b (Pyramid Adds) completed")
            except Exception as e:
                logger.error(f"✗ Phase 4b (Pyramid Adds) failed: {e}", exc_info=True)
                self.log_phase_result('4b', 'pyramid_adds', 'error', str(e))

            # Phase 5: Signal Generation
            try:
                with TimeBlock("phase_5_signal_generation"):
                    result = self.phase_5_signal_generation()
                    if result is False:
                        logger.critical("HALT: Phase 5 (Signal Generation) returned False — stopping pipeline")
                        return self._final_report()
                logger.info("[OK] Phase 5 (Signal Generation) completed")
            except Exception as e:
                logger.error(f"✗ Phase 5 (Signal Generation) failed: {e}", exc_info=True)
                self.log_phase_result(5, 'signal_generation', 'error', str(e))

            # Phase 6: Entry Execution
            try:
                with TimeBlock("phase_6_entry_execution"):
                    result = self.phase_6_entry_execution()
                    if result is False:
                        logger.critical("HALT: Phase 6 (Entry Execution) returned False — stopping pipeline")
                        return self._final_report()
                logger.info("[OK] Phase 6 (Entry Execution) completed")
            except Exception as e:
                logger.error(f"✗ Phase 6 (Entry Execution) failed: {e}", exc_info=True)
                self.log_phase_result(6, 'entry_execution', 'error', str(e))

            # Phase 7: Reconciliation (fail-open — doesn't execute trades, just records state)
            try:
                with TimeBlock("phase_7_reconciliation"):
                    result = self.phase_7_reconcile()
                # Phase 7 is fail-open: if reconciliation fails, we still finalize the report
                # (positions may already be executed, so we must sync state)
                logger.info("[OK] Phase 7 (Reconciliation) completed")
            except Exception as e:
                logger.error(f"✗ Phase 7 (Reconciliation) failed: {e}", exc_info=True)
                self.log_phase_result(7, 'reconciliation', 'error', str(e))

            # Log performance metrics at end
            log_metrics_summary()
            return self._final_report()
        finally:
            self._release_run_lock()

    def _validate_pre_trade_data_quality(self) -> Tuple[bool, List[str], List[str]]:
        """
        Gate: Verify all required data is fresh and complete before trading.

        Checks:
        1. All required tables have data for today (or most recent if testing)
        2. Price data is recent (< 1 hour old)
        3. No critical NULLs in signal columns
        4. Symbol coverage > 80% of active universe
        5. Technical data is fresh

        For historical testing: Uses most recent available data if run_date is in past
        For production: Requires data for current trading day

        Returns:
            (passes: bool, blocking_issues: list, warnings: list)
        """
        issues = []
        warnings = []
        conn = None
        cur = None

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            today = self.run_date

            # For testing with historical dates: use most recent data if run_date is in past
            is_historical_test = today < _date.today()
            if is_historical_test:
                cur.execute("SELECT MAX(date) FROM price_daily")
                latest_date = cur.fetchone()[0]
                if latest_date and latest_date > today:
                    logger.info(f"  [TEST MODE] Using latest available data ({latest_date}) instead of run_date ({today})")
                    today = latest_date

            # Hard blocks: data required before trading
            required_hard = [
                ('price_daily', 'Price data'),
                ('technical_data_daily', 'Technical indicators'),
                ('buy_sell_daily', 'Signal data'),
            ]
            # Soft checks: post-trade tables, only warn if missing (they get populated by orchestrator after trades)
            required_soft = [
                ('market_exposure_daily', 'Market exposure data'),
                ('algo_risk_daily', 'Risk calculations'),
            ]

            for table, description in required_hard:
                assert_safe_table(table)
                cur.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE date = %s",
                    (today,)
                )
                count = cur.fetchone()[0]
                if count == 0:
                    issues.append(f"{description} missing for {today}")
                else:
                    logger.debug(f"  [OK] {table}: {count} rows for {today}")

            for table, description in required_soft:
                assert_safe_table(table)
                if table == 'algo_risk_daily':
                    cur.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE report_date = %s",
                        (today,)
                    )
                else:
                    cur.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE date = %s",
                        (today,)
                    )
                count = cur.fetchone()[0]
                if count == 0:
                    warnings.append(f"{description} not available (will be populated after trading)")
                else:
                    logger.debug(f"  [OK] {table}: {count} rows for today")

            cur.execute(
                "SELECT MAX(created_at) FROM price_daily WHERE date = %s",
                (today,)
            )
            result = cur.fetchone()
            if result and result[0]:
                age_hours = (datetime.now() - result[0]).total_seconds() / 3600
                if age_hours > 24:
                    issues.append(f"Price data too stale: {age_hours:.1f} hours old")
                elif age_hours > 1:
                    warnings.append(f"Price data is {age_hours:.1f} hours old")
            else:
                issues.append("No price data found")

            cur.execute(
                "SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s AND (symbol IS NULL OR signal IS NULL)",
                (today,)
            )
            null_count = cur.fetchone()[0]
            if null_count > 0:
                issues.append(f"Signal data has {null_count} critical NULLs")

            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
                (today,)
            )
            covered = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM stock_symbols WHERE is_sp500 = TRUE"
            )
            total = cur.fetchone()[0]
            if total > 0:
                coverage = (covered / total) * 100
                if coverage < 80:
                    issues.append(f"Low symbol coverage: {covered}/{total} ({coverage:.1f}%)")
                elif coverage < 95:
                    warnings.append(f"Symbol coverage: {covered}/{total} ({coverage:.1f}%)")

            cur.execute(
                "SELECT MAX(created_at) FROM technical_data_daily WHERE date = %s",
                (today,)
            )
            result = cur.fetchone()
            if result and result[0]:
                age_hours = (datetime.now() - result[0]).total_seconds() / 3600
                if age_hours > 12:
                    issues.append(f"Technical data stale: {age_hours:.1f} hours old")
            else:
                issues.append("No technical data found")

            # Expand from H6 stock_scores check to include quality_metrics and value_metrics

            # 6a. Quality metrics (momentum, volatility, RSI, etc.)
            cur.execute(
                "SELECT COUNT(*) FROM quality_metrics WHERE DATE(created_at) = %s",
                (today,)
            )
            quality_count = cur.fetchone()[0]
            if quality_count < (covered * 0.80):  # At least 80% of covered symbols
                issues.append(f"Quality metrics incomplete: {quality_count}/{covered} symbols ({(quality_count/max(covered,1)*100):.0f}%)")

            # 6b. Value metrics (PE, PB, PS ratios)
            cur.execute(
                "SELECT COUNT(*) FROM value_metrics WHERE DATE(created_at) = %s",
                (today,)
            )
            value_count = cur.fetchone()[0]
            if value_count < (covered * 0.70):  # At least 70% of covered symbols (PE coverage is lower)
                warnings.append(f"Value metrics incomplete: {value_count}/{covered} symbols ({(value_count/max(covered,1)*100):.0f}%)")

            # 6c. Stock scores data completeness (scores must have >80% component coverage)
            # data_completeness field ranges 0.0-1.0 (1.0 = all 6 score components available, 0.8+ = acceptable)
            cur.execute(
                "SELECT COUNT(*) FROM stock_scores WHERE updated_at = %s AND data_completeness >= 0.8",
                (today,)
            )
            complete_scores = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM stock_scores WHERE updated_at = %s",
                (today,)
            )
            total_scores = cur.fetchone()[0]
            if total_scores > 0:
                completeness_pct = (complete_scores / total_scores) * 100
                if completeness_pct < 50:
                    issues.append(f"Stock scores incomplete: only {completeness_pct:.1f}% have >=80% component coverage")
                elif completeness_pct < 80:
                    warnings.append(f"Stock scores: {completeness_pct:.1f}% have full component coverage (ideal: >80%)")
            else:
                warnings.append("Stock scores not available for today (quality_metrics or value_metrics missing)")

            passes = len(issues) == 0
            return passes, issues, warnings

        except Exception as e:
            logger.error(f"Data quality check failed: {e}", exc_info=True)
            return False, [f"Data quality check error: {e}"], []
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def _is_market_open_or_imminent(self, window_min: int = 30) -> bool:
        """Return True if US equity market is open right now OR opens within
        `window_min` minutes. Queries Alpaca's /v2/clock — authoritative for
        holidays, half-days, etc. In auto mode, fails closed (returns False) on
        API failure so we don't trade when market status is unknown."""
        try:
            import requests
            if credential_manager is None:
                return False  # Fail-closed: can't get credentials
            key = credential_manager.get_alpaca_credentials()["key"]
            secret = credential_manager.get_alpaca_credentials()["secret"]
            base = os.getenv('APCA_API_BASE_URL')
            if not base:
                raise ValueError("APCA_API_BASE_URL environment variable not set — refusing to trade without explicit endpoint configuration")
            if not key or not secret:
                mode = (self.config.get('execution_mode', 'paper') if isinstance(self.config, dict) else 'paper').lower()
                if mode == 'auto':
                    return False  # Auto mode: fail-closed if can't verify market hours
                return True  # Paper mode: permit
            r = requests.get(
                f'{base}/v2/clock',
                headers={'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret},
                timeout=5,
            )
            r.raise_for_status()
            clock = r.json()
            if clock.get('is_open'):
                return True
            # Imminent open?
            from datetime import datetime, timezone
            next_open_str = clock.get('next_open')  # ISO 8601 with TZ
            if not next_open_str:
                return False
            next_open = datetime.fromisoformat(next_open_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            mins_to_open = (next_open - now).total_seconds() / 60.0
            return 0 <= mins_to_open <= window_min
        except Exception as e:
            mode = (self.config.get('execution_mode', 'paper') if isinstance(self.config, dict) else 'paper').lower()
            if mode == 'auto':
                logger.error(f"  [ERROR] market-hours check failed: {e} — failing closed (no entries in auto mode)")
                return False
            logger.error(f"  [warn] market-hours check failed: {e} — proceeding in {mode} mode")
            return True

    def _pid_alive(self, pid):
        """Check if a PID is still running (cross-platform)."""
        try:
            if os.name == 'nt':
                # Windows
                import subprocess
                result = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}'],
                    capture_output=True, text=True, timeout=5,
                )
                return str(pid) in result.stdout
            else:
                # POSIX — kill -0 just checks existence
                os.kill(pid, 0)
                return True
        except Exception:
            return False

    def _final_report(self):
        logger.info(f"\n{'#'*70}")
        logger.info(f"#   FINAL REPORT — {self.run_id}")
        logger.info(f"{'#'*70}")
        for n, info in sorted(self.phase_results.items(), key=lambda x: str(x[0])):
            status_flag = {
                'success': '[OK] ',
                'halt':    '[HALT]',
                'fail':    '[FAIL]',
                'error':   '[ERR] ',
            }.get(info['status'], '[?]   ')
            logger.info(f"  {status_flag} Phase {n}: {info['name']:22s} — {info['summary']}")
        logger.info(f"{'#'*70}\n")

        result = {
            'run_id': self.run_id,
            'run_date': self.run_date.isoformat(),
            'phases': self.phase_results,
            'success': all(p['status'] in ('success', 'halt') for p in self.phase_results.values()),
        }

        # Publish CloudWatch metrics (non-blocking — never let metrics interrupt trading)
        try:
            from algo.algo_metrics import MetricsPublisher
            with MetricsPublisher(dry_run=self.dry_run) as m:
                m.put_orchestrator_result(result['success'], self.phase_results)

                # Signal count from phase 5 summary
                phase5 = self.phase_results.get(5, {})
                signals = phase5.get('signals_evaluated', 0)
                if isinstance(signals, int):
                    m.put_signal_count(signals)

                # Trade count from phase 6 summary
                phase6 = self.phase_results.get(6, {})
                trades = phase6.get('trades_executed', 0)
                if isinstance(trades, int):
                    m.put_trade_count(trades)

                # Open position count from phase 7
                phase7 = self.phase_results.get(7, {})
                positions = phase7.get('open_positions', 0)
                if isinstance(positions, int):
                    m.put_open_positions(positions)

        except Exception as e:
            # Never let metrics publishing interrupt trading results
            logger.error("CloudWatch metric publish failed: %s", e)

        return result


if __name__ == "__main__":
    load_env()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    from utils.config_validator import validate_at_startup
    validate_at_startup()

    import argparse
    parser = argparse.ArgumentParser(description='Run daily algo workflow')
    parser.add_argument('--date', type=str, help='Run date (YYYY-MM-DD)', default=None)
    parser.add_argument('--dry-run', action='store_true', help='Plan only, no real trades')
    parser.add_argument('--quiet', action='store_true', help='Reduce output')
    parser.add_argument('--skip-freshness', action='store_true',
                        help='Skip phase 1 data freshness gate (testing only — never use for live trading)')
    args = parser.parse_args()

    run_date = _date.fromisoformat(args.date) if args.date else None
    orch = Orchestrator(run_date=run_date, dry_run=args.dry_run, verbose=not args.quiet)
    try:
        if args.skip_freshness:
            orch.skip_freshness = True
            logger.warning("WARNING: --skip-freshness is set. Data may be stale. Do NOT use for live trading.")
        final = orch.run()
        sys.exit(0 if final['success'] else 1)
    finally:
        orch.cleanup()

