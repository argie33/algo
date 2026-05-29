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

from config.credential_manager import (
    get_db_password,
    get_db_config,
    DEFAULT_DB_PORT,
    DEFAULT_DB_USER,
    DEFAULT_DB_NAME,
)
from algo.algo_config import get_subprocess_timeout


import os
import tempfile
import time
import json
from utils.database_context import DatabaseContext
import psycopg2.extensions
from psycopg2 import pool as psycopg2_pool
from datetime import datetime, date as _date, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple, Union
from algo.algo_alerts import AlertManager
from algo.algo_market_calendar import MarketCalendar
from algo.algo_sql_safety import assert_safe_table, assert_safe_column
from algo.algo_trade_executor import TradeExecutor
import logging
from utils.monitoring_context import TimeBlock, log_metrics_summary, clear_metrics_buffer

logger = logging.getLogger(__name__)


class Orchestrator:
    """Daily workflow runner with explicit phases."""

    HALT_FLAG_PATH = str(Path(tempfile.gettempdir()) / 'algo_orchestrator_halt')

    def __init__(self, config: Optional[Any] = None, run_date: Optional[_date] = None, dry_run: bool = False, verbose: bool = True) -> None:
        from algo.algo_config import get_config
        self.config = config or get_config()

        # Override execution_mode from environment variable if set
        env_execution_mode = os.getenv('ORCHESTRATOR_EXECUTION_MODE', '').strip().lower()
        if env_execution_mode:
            self.config._config['execution_mode'] = env_execution_mode
            logger.info(f"[ENV] Execution mode overridden via ORCHESTRATOR_EXECUTION_MODE: {env_execution_mode}")

        self.run_date = run_date or _date.today()
        self.dry_run = dry_run
        self.verbose = verbose
        self.phase_results = {}
        self.run_id = f"RUN-{self.run_date.isoformat()}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
        # FIXED Issue #8: Use DynamoDB lock manager instead of filesystem lock for distributed locking in Fargate
        from utils.dynamodb_lock_manager import DynamoDBLockManager
        self.lock_manager = DynamoDBLockManager()
        self._lock_acquired = False
        self.db_failure_counter_file = Path(tempfile.gettempdir()) / 'algo_db_failures.txt'
        self.degraded_mode = False  # B4: Circuit breaker for DB failures
        self.alerts = AlertManager()

        # maxconn=100 supports 40+ concurrent loaders with buffer
        # In dry-run mode, database is optional; fail gracefully if unavailable
        self.db_pool = None
        try:
            logger.info("[POOL] Creating ThreadedConnectionPool with minconn=1, maxconn=100")
            self.db_pool = psycopg2_pool.ThreadedConnectionPool(
                minconn=1, maxconn=100, **get_db_config()
            )
            logger.info("[POOL] ThreadedConnectionPool created successfully")
        except Exception as e:
            if self.dry_run:
                logger.info(f"[DRY-RUN] Database unavailable: {e}. Proceeding with planning mode.")
                self.degraded_mode = True
            else:
                logger.warning(f"Failed to create connection pool: {e}. Using fallback.")
                self.db_pool = None

        logger.info("[ORCHESTRATOR] About to initialize feature flags")
        self._initialize_feature_flags()
        logger.info("[ORCHESTRATOR] Feature flags initialized")

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
            except Exception as pool_err:
                logger.debug(f"Failed to return connection to pool: {pool_err}")
                try:
                    conn.close()
                except Exception as close_err:
                    logger.debug(f"Failed to close connection after pool error: {close_err}")

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
                except Exception as close_err:
                    logger.debug(f"Failed to close cursor: {close_err}")
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

    def _initialize_feature_flags(self) -> None:
        """Initialize feature flags with safe defaults on startup."""
        # In AWS Lambda, skip feature flag initialization (uses defaults only)
        if os.getenv('AWS_LAMBDA_FUNCTION_NAME'):
            logger.info("[FEATURE_FLAGS] Skipping initialization in Lambda (using defaults)")
            return

        try:
            from utils.feature_flags import initialize_safe_defaults, create_feature_flags_table
            # Ensure table exists
            create_feature_flags_table()
            initialize_safe_defaults()
        except Exception as e:
            if self.verbose:
                logger.warning(f"  [WARN] Feature flag initialization failed: {e}")
            # Don't fail the orchestrator if flags aren't available

    def _validate_required_tables(self, cur: Any) -> bool:
        """FIXED Issue #23: Validate that all required tables exist before running phases.

        Returns: True if all tables exist, False if any critical table is missing.
        """
        required_tables = [
            'price_daily',
            'technical_data_daily',
            'buy_sell_daily',
            'signal_quality_scores',
            'market_health_daily',
            'algo_audit_log',
        ]

        try:
            missing_tables = []
            for table_name in required_tables:
                try:
                    # Check if table exists by querying information_schema
                    cur.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = %s LIMIT 1", (table_name,))
                    if not cur.fetchone():
                        missing_tables.append(table_name)
                        logger.error(f"[TABLE-CHECK] Missing required table: {table_name}")
                except Exception as e:
                    logger.error(f"[TABLE-CHECK] Failed to check table {table_name}: {e}")
                    missing_tables.append(table_name)

            if missing_tables:
                logger.error(f"[TABLE-CHECK] Cannot proceed: missing tables {missing_tables}")
                self.log_phase_result(0, 'table_validation', 'halt', f'Missing tables: {", ".join(missing_tables)}')
                return False

            logger.info(f"[TABLE-CHECK] All {len(required_tables)} required tables exist ✓")
            return True

        except Exception as e:
            logger.error(f"[TABLE-CHECK] Error validating tables: {e}")
            return False

    def _check_data_freshness(self, cur: Any) -> bool:
        """FIXED Issue #9: Validate that all critical data is fresh (from today or yesterday).

        Checks:
        - Prices exist for the last trading day (loaders load previous day's close)
        - Technical indicators computed for the last trading day
        - Signals generated for the last trading day
        - Signal quality scores available
        - Market health computed for the last trading day

        Returns: True if data is fresh, False if critical data is stale.
        """
        try:
            # Loaders fetch data for the PREVIOUS trading day (not today).
            # E.g., at 9:30 AM ET today, we have yesterday's close available.
            from algo.algo_market_calendar import MarketCalendar

            expected_date = self.run_date - timedelta(days=1)
            # If run_date is Monday, we need Friday's data (skip weekend)
            for _ in range(10):
                if MarketCalendar.is_trading_day(expected_date):
                    break
                expected_date -= timedelta(days=1)

            checks = {
                'price_daily': "SELECT COUNT(*) FROM price_daily WHERE date = %s",
                'technical_data_daily': "SELECT COUNT(*) FROM technical_data_daily WHERE date = %s",
                'buy_sell_daily': "SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s",
                'signal_quality_scores': "SELECT COUNT(*) FROM signal_quality_scores WHERE date = %s",
                'market_health_daily': "SELECT COUNT(*) FROM market_health_daily WHERE date >= CURRENT_DATE - INTERVAL '2 days'",
            }

            freshness_ok = True
            for table_name, query in checks.items():
                try:
                    cur.execute(query, (expected_date,))

                    count = cur.fetchone()[0]
                    if count == 0:
                        logger.error(f"[FRESHNESS] {table_name} has no data for {expected_date}")
                        freshness_ok = False
                    else:
                        if self.verbose:
                            logger.info(f"[FRESHNESS] {table_name}: {count} rows for {expected_date}")
                except Exception as e:
                    logger.error(f"[FRESHNESS] Failed to check {table_name}: {e}")
                    freshness_ok = False

            if not freshness_ok:
                logger.error("[FRESHNESS] Critical data is stale — blocking orchestrator")
                self.log_phase_result(1, 'data_freshness', 'halt', 'Critical data is not fresh (missing prices, technicals, or signals)')
                return False

            return True

        except Exception as e:
            logger.error(f"[FRESHNESS] Error checking data freshness: {e}")
            return False

    def _check_data_patrol(self, cur: Any) -> bool:
        """Check data patrol results. Fail-closed if critical/error findings.

        Only checks the LATEST patrol run (not accumulated from all runs in 24h).
        Skips stale patrol findings — if the latest patrol ran before the previous
        trading day, old findings are not representative of current data quality.
        Returns: True if patrol OK, False if critical/error issues found.
        """
        try:
            cur.execute("""
                SELECT patrol_run_id, MAX(created_at) AS run_at FROM data_patrol_log
                GROUP BY patrol_run_id
                ORDER BY MAX(created_at) DESC LIMIT 1
            """)
            latest_run = cur.fetchone()
            if not latest_run:
                if self.verbose:
                    logger.info("No patrol data available")
                return True

            latest_run_id, latest_run_at = latest_run

            # Skip stale patrol findings — only apply patrol check if the patrol
            # ran on or after the previous trading day. Old patrol results (e.g.
            # "signal_quality_scores EMPTY" from days ago) are not actionable and
            # would incorrectly block the orchestrator on fresh data.
            try:
                from algo.algo_market_calendar import MarketCalendar
                expected_patrol_date = self.run_date - timedelta(days=1)
                for _ in range(10):
                    if MarketCalendar.is_trading_day(expected_patrol_date):
                        break
                    expected_patrol_date -= timedelta(days=1)
            except Exception:
                expected_patrol_date = self.run_date - timedelta(days=1)
                while expected_patrol_date.weekday() >= 5:
                    expected_patrol_date -= timedelta(days=1)

            patrol_date = latest_run_at.date() if hasattr(latest_run_at, 'date') else self.run_date
            if patrol_date < expected_patrol_date:
                logger.warning(
                    f"[PATROL] Latest patrol ({latest_run_id}, {patrol_date}) is older than "
                    f"expected ({expected_patrol_date}) — skipping stale findings"
                )
                return True  # Stale patrol: don't block on old findings

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
                if self.verbose:
                    logger.info("No findings in latest patrol")
                return True

            worst_severity, total_findings, critical_count, error_count, warn_count, info_count = row

            if self.verbose:
                logger.info(f"Patrol {latest_run_id}: {total_findings} findings "
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

            if flagged:
                logger.warning(f"Patrol found {len(flagged)} critical/error findings")
                for f in flagged:
                    logger.warning(f"  {f['severity'].upper()}: {f['check']} on {f['target']}: {f['message'][:120]}")

            # Send alerts on CRITICAL or ERROR
            if critical_count > 0 or error_count > 0:
                self.alerts.send_patrol_alert(
                    latest_run_id,
                    {'critical': critical_count, 'error': error_count, 'warn': warn_count, 'info': info_count},
                    flagged
                )

            # FAIL-CLOSED: critical findings always block
            if critical_count > 0:
                logger.info(f"[PATROL_HALT] Blocking orchestrator due to {critical_count} critical findings")
                if self.verbose:
                    logger.info(f"  [HALT] Data patrol found {critical_count} CRITICAL issues")
                self.log_phase_result(1, 'data_patrol', 'halt',
                                      f'Critical data quality issues: {critical_count} critical findings')
                return False

            # FAIL-CLOSED: only CRITICAL blocks in LIVE mode. Errors are warnings.
            # (Errors like incomplete price_daily coverage don't block - we proceed with available data)
            if error_count > 0:
                if self.verbose:
                    logger.warning(f"  [PATROL] Data patrol found {error_count} error(s) - proceeding with available data")

            return True

        except Exception as e:
            # If patrol check fails, fail-closed (don't trade on uncertain data)
            logger.error(f"  [HALT] Data patrol check failed: {e}")
            self.log_phase_result(1, 'data_patrol', 'halt',
                                  f'Patrol execution error: {str(e)[:100]}')
            return False

    # ---------- Logging helpers ----------

    def _acquire_run_lock(self, lock_timeout_seconds: int = 5) -> bool:
        """Acquire distributed lock to prevent concurrent orchestrator runs.

        FIXED Issue #8: Uses DynamoDB conditional writes instead of filesystem locks
        for correct distributed locking in Fargate ECS tasks (no shared filesystem).

        Args:
            lock_timeout_seconds: How long to retry acquiring lock (default 5s)

        Returns: True if lock acquired, False if another active instance holds it.
        """
        self._lock_acquired = self.lock_manager.acquire(timeout_seconds=lock_timeout_seconds)
        return self._lock_acquired

    def _release_run_lock(self) -> None:
        """Release the distributed lock."""
        if self._lock_acquired:
            self.lock_manager.release()

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
            conn = self._get_conn()
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
            self._put_conn(conn)

    # ---------- Pipeline Health & Visibility ----------

    def _check_pipeline_health(self, cur: Any) -> None:
        """Check that all required tables have recent data for signal processing."""
        if not cur:
            return

        try:
            five_days_ago = self.run_date - timedelta(days=5)

            # Single query with one UNION ALL per table — avoids 10 round-trips
            batch_sql = """
                SELECT 'price_daily'          AS tbl, COUNT(*) FROM price_daily          WHERE date          >= %s
                UNION ALL
                SELECT 'buy_sell_daily',               COUNT(*) FROM buy_sell_daily               WHERE date          >= %s
                UNION ALL
                SELECT 'trend_template_data',          COUNT(*) FROM trend_template_data          WHERE date          >= %s
                UNION ALL
                SELECT 'technical_data_daily',         COUNT(*) FROM technical_data_daily         WHERE date          >= %s
                UNION ALL
                SELECT 'signal_quality_scores',        COUNT(*) FROM signal_quality_scores        WHERE date          >= %s
                UNION ALL
                SELECT 'swing_trader_scores',          COUNT(*) FROM swing_trader_scores          WHERE date          >= %s
                UNION ALL
                SELECT 'market_health_daily',          COUNT(*) FROM market_health_daily          WHERE date          >= %s
                UNION ALL
                SELECT 'sector_ranking',               COUNT(*) FROM sector_ranking               WHERE date_recorded >= %s
                UNION ALL
                SELECT 'industry_ranking',             COUNT(*) FROM industry_ranking             WHERE date_recorded >= %s
                UNION ALL
                SELECT 'stock_scores',                 COUNT(*) FROM stock_scores                 WHERE updated_at    >= %s
            """
            descriptions = {
                'price_daily':          'price_daily (OHLCV)',
                'buy_sell_daily':       'buy_sell_daily (entry signals)',
                'trend_template_data':  'trend_template_data (Minervini/Weinstein scores)',
                'technical_data_daily': 'technical_data_daily (MA/RSI/ATR)',
                'signal_quality_scores':'signal_quality_scores (SQS >= 40 gate)',
                'swing_trader_scores':  'swing_trader_scores (final ranking)',
                'market_health_daily':  'market_health_daily (Tier 2 gate)',
                'sector_ranking':       'sector_ranking (Tier 6 context)',
                'industry_ranking':     'industry_ranking (Tier 6 context)',
                'stock_scores':         'stock_scores (Tier 6 scoring)',
            }
            try:
                cur.execute(batch_sql, (five_days_ago,) * 10)
                status = {row[0]: row[1] for row in cur.fetchall()}
            except Exception as e:
                logger.warning(f"Pipeline health batch query failed: {e}")
                status = {t: 0 for t in descriptions}

            for table, description in descriptions.items():
                count = status.get(table, 0)
                flag = '[OK]' if count > 0 else '[EMPTY]'
                if self.verbose:
                    logger.info(f"    {flag} {description:50s}: {count:,} rows (5d)")

            # Alert if any critical table is empty
            empty_tables = [t for t in descriptions if status.get(t, 0) == 0]
            if empty_tables:
                empty_desc = ', '.join([descriptions[t] for t in empty_tables])
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
            conn = self._get_conn()
            cur = conn.cursor()

            # Count total BUY signals for today
            cur.execute(
                "SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s AND signal_type = 'BUY'",
                (self.run_date,)
            )
            result = cur.fetchone()
            total_signals = result[0] if result else 0

            # Count from trend_template_data where Stage 2 exists
            # (Stage 2 check is in filter_pipeline, using pre-filtered signals)
            cur.execute(
                """SELECT COUNT(DISTINCT symbol) FROM trend_template_data
                   WHERE date = %s AND weinstein_stage = 2""",
                (self.run_date,)
            )
            result = cur.fetchone()
            stage2_count = result[0] if result else 0

            # Count rejections per tier in a single query (uses composite index on eval_date, rejected_at_tier)
            tier_rejections = {f'Tier {i}': 0 for i in range(1, 7)}
            try:
                cur.execute(
                    """SELECT rejected_at_tier, COUNT(DISTINCT symbol)
                       FROM filter_rejection_log
                       WHERE eval_date = %s AND rejected_at_tier BETWEEN 1 AND 6
                       GROUP BY rejected_at_tier""",
                    (self.run_date,)
                )
                for tier_num, count in cur.fetchall():
                    tier_rejections[f'Tier {tier_num}'] = count or 0
            except Exception:
                # Table may not exist or columns different; skip
                pass

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

                interpretation = self._interpret_waterfall(total_signals, stage2_count, tier_rejections, final_count)
                logger.info(f"  Interpretation: {interpretation}")

                # FIXED Issue #24: Log waterfall to database for audit trail
                try:
                    waterfall_data = {
                        'total_signals': total_signals,
                        'stage2_count': stage2_count,
                        'tier_1_rejected': tier_rejections.get('Tier 1', 0),
                        'tier_2_rejected': tier_rejections.get('Tier 2', 0),
                        'tier_3_rejected': tier_rejections.get('Tier 3', 0),
                        'tier_4_rejected': tier_rejections.get('Tier 4', 0),
                        'tier_5_rejected': tier_rejections.get('Tier 5', 0),
                        'tier_6_rejected': tier_rejections.get('Tier 6', 0),
                        'final_qualified': final_count,
                        'interpretation': interpretation,
                    }
                    cur.execute(
                        """INSERT INTO algo_audit_log (run_id, phase, status, detail, created_at)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (self.run_id, 'signal_waterfall', 'info', json.dumps(waterfall_data), datetime.now(timezone.utc))
                    )
                    conn.commit()
                    logger.debug(f"[WATERFALL] Logged to algo_audit_log for persistence")
                except Exception as e:
                    logger.warning(f"[WATERFALL] Could not persist to database: {e}")

        except Exception as e:
            logger.warning(f"Signal waterfall report failed: {e}")
        finally:
            if cur:
                try:
                    cur.close()
                except Exception as e:
                    logger.error(f"Unhandled exception: {e}")
            self._put_conn(conn)

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
        """Thin delegation to phase1_data_freshness module."""
        self.log_phase_start(1, 'DATA FRESHNESS CHECK')
        from algo.orchestrator.phase1_data_freshness import run as run_phase1
        result = run_phase1(
            self.config, self._get_conn, self._put_conn,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result
        )
        return not result.halted

    def phase_2_circuit_breakers(self) -> bool:
        """Thin delegation to phase2_circuit_breakers module."""
        self.log_phase_start(2, 'CIRCUIT BREAKERS')
        from algo.orchestrator.phase2_circuit_breakers import run as run_phase2
        result = run_phase2(
            self.config, self._get_conn, self._put_conn,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result
        )
        return not result.halted

    def phase_3_position_monitor(self) -> List[Dict[str, Any]]:
        """Thin delegation to phase3_position_monitor module."""
        self.log_phase_start(3, 'POSITION MONITOR')
        from algo.orchestrator.phase3_position_monitor import run as run_phase3
        result = run_phase3(
            self.config, self._get_conn, self._put_conn,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result
        )
        self._position_recs = result.data.get('recommendations', [])
        return True  # fail-open

    def phase_3b_exposure_policy(self) -> Dict[str, Any]:
        """Thin delegation to phase3b_exposure_policy module."""
        self.log_phase_start('3b', 'EXPOSURE POLICY ACTIONS')
        from algo.orchestrator.phase3b_exposure_policy import run as run_phase3b
        result = run_phase3b(
            self.config, self._get_conn, self._put_conn,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result
        )
        self._exposure_constraints = result.data.get('constraints')
        self._exposure_actions = result.data.get('actions', [])
        return True  # fail-open

    def phase_4_exit_execution(self) -> List[Dict[str, Any]]:
        """Thin delegation to phase4_exit_execution module."""
        self.log_phase_start(4, 'EXIT EXECUTION')
        if self._check_halt_flag():
            return False
        from algo.orchestrator.phase4_exit_execution import run as run_phase4
        result = run_phase4(
            self.config, self._get_conn, self._put_conn,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result,
            getattr(self, '_position_recs', []),
            getattr(self, '_exposure_actions', []),
            self._check_halt_flag
        )
        return not result.halted


    def phase_4b_pyramid_adds(self) -> List[Dict[str, Any]]:
        """Thin delegation to phase4b_pyramid_adds module."""
        self.log_phase_start('4b', 'PYRAMID ADDS (winners)')
        from algo.orchestrator.phase4b_pyramid_adds import run as run_phase4b
        result = run_phase4b(
            self.config, self._get_conn, self._put_conn,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result
        )
        return True  # fail-open

    def phase_5_signal_generation(self) -> List[Dict[str, Any]]:
        """Thin delegation to phase5_signal_generation module."""
        self.log_phase_start(5, 'SIGNAL GENERATION & RANKING')
        if self._check_halt_flag():
            return False
        from algo.orchestrator.phase5_signal_generation import run as run_phase5
        result = run_phase5(
            self.config, self._get_conn, self._put_conn,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result,
            getattr(self, '_exposure_constraints', {}),
            self._check_halt_flag
        )
        self._qualified_trades = result.data.get('qualified_trades', [])
        self.phase_results.setdefault(5, {})['signals_evaluated'] = len(self._qualified_trades)
        return not result.halted

    def phase_6_entry_execution(self) -> List[Dict[str, Any]]:
        """Thin delegation to phase6_entry_execution module."""
        self.log_phase_start(6, 'ENTRY EXECUTION')
        if self._check_halt_flag():
            return False
        from algo.orchestrator.phase6_entry_execution import run as run_phase6
        result = run_phase6(
            self.config, self._get_conn, self._put_conn,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result,
            getattr(self, '_qualified_trades', []),
            getattr(self, '_exposure_constraints', None),
            self._check_halt_flag
        )
        self.phase_results.setdefault(6, {})['trades_executed'] = result.data.get('entered', 0)
        return not result.halted


    def phase_7_reconcile(self) -> Dict[str, Any]:
        """Thin delegation to phase7_reconciliation module."""
        self.log_phase_start(7, 'RECONCILIATION & SNAPSHOT')
        if self._check_halt_flag():
            return False
        from algo.orchestrator.phase7_reconciliation import run as run_phase7
        result = run_phase7(
            self.config, self._get_conn, self._put_conn,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result
        )
        self.phase_results.setdefault(7, {})['open_positions'] = result.data.get('positions', 0)
        return not result.halted


    # ---------- Main entrypoint ----------

    def run(self) -> Dict[str, Any]:
        import time
        run_start = time.time()
        logger.info(f"\n{'#'*70}")
        logger.info(f"#   ALGO ORCHESTRATOR — {self.run_date}  ({'DRY RUN' if self.dry_run else 'LIVE'})")
        logger.info(f"#   run_id: {self.run_id}")
        logger.info(f"#   START TIME: {datetime.now(timezone.utc).isoformat()}")
        logger.info(f"{'#'*70}")

        if not MarketCalendar.is_trading_day(self.run_date):
            status = MarketCalendar.market_status(datetime.combine(self.run_date, datetime.min.time()))
            logger.info(f"\n Market closed: {status['reason']}")
            logger.info("Skipping all trading phases.\n")
            return {'success': True, 'skipped': True, 'reason': f"Market closed: {status['reason']}"}

        # Concurrency lock — prevent two orchestrators running at once
        # which would risk duplicate trades or double-counting circuit breakers
        if not self._acquire_run_lock():
            logger.error(f"\nABORT: Could not acquire run lock. Another orchestrator instance is running.")
            return {'success': False, 'error': 'Lock acquisition failed'}

        try:
            logger.info("\n[CRITICAL] Running critical data checks...")
            conn = None
            cur = None
            try:
                conn = self._get_conn()
                cur = conn.cursor()

                # FIXED Issue #23: Validate required tables exist
                if not self._validate_required_tables(cur):
                    return self._final_report()

                # FIXED Issue #9: Check data freshness before patrol
                if not self._check_data_freshness(cur):
                    return self._final_report()

                # Check data patrol for quality issues
                if not self._check_data_patrol(cur):
                    return self._final_report()
            except Exception as e:
                logger.error(f"  [HALT] Data patrol check failed: {e}")
                return self._final_report()
            finally:
                if cur:
                    try:
                        cur.close()
                    except Exception as e:
                        logger.error(f"Unhandled exception: {e}")
                self._put_conn(conn)


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
                    if not self.dry_run:
                        self.phase_7_reconcile()
                    return self._final_report()
                else:
                    logger.error(f"\n[ERROR] Database connectivity failed ({failures}/3). Will halt if persists.")
                    if self.dry_run:
                        logger.info("[DRY-RUN] Skipping all phases due to missing database.")
                    return self._final_report()
            else:
                self._reset_db_failure_counter()

            if self.degraded_mode and self.dry_run:
                logger.info("[DRY-RUN] Running in planning mode — skipping all trading phases.")
                self.log_phase_result(1, 'planning_mode', 'success', 'Dry-run mode with unavailable database')
                return self._final_report()

            try:
                phase_1_start = time.time()
                logger.info(f"\n[PHASE 1] Starting at {datetime.now(timezone.utc).isoformat()}")
                with TimeBlock("phase_1_data_freshness"):
                    if not self.phase_1_data_freshness():
                        logger.error("\nFAIL-CLOSED: Data freshness check failed. Halting pipeline.")
                        self.log_phase_result(1, 'data_freshness', 'fail', 'Stale or missing critical data')
                        return self._final_report()
                phase_1_elapsed = time.time() - phase_1_start
                logger.info(f"[PHASE 1] Completed in {phase_1_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                logger.error(f"\nERROR in phase 1 (data freshness): {e}. Halting pipeline.")
                self.log_phase_result(1, 'data_freshness', 'error', str(e))
                return self._final_report()

            phase_2_start = time.time()
            logger.info(f"\n[PHASE 2] Starting at {datetime.now(timezone.utc).isoformat()}")
            with TimeBlock("phase_2_circuit_breakers"):
                phase_2_passed = self.phase_2_circuit_breakers()
            phase_2_elapsed = time.time() - phase_2_start
            logger.info(f"[PHASE 2] Completed in {phase_2_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")

            if not phase_2_passed:
                logger.info("\nHALT: Circuit breaker fired. Will still review positions but skip new entries.")
                self.phase_3_position_monitor()
                self.phase_3b_exposure_policy()
                self.phase_4_exit_execution()
                self.phase_7_reconcile()
                return self._final_report()

            # Phase 3: Position Monitor
            phase_3_start = time.time()
            logger.info(f"\n[PHASE 3] Starting at {datetime.now(timezone.utc).isoformat()}")
            try:
                with TimeBlock("phase_3_position_monitor"):
                    self.phase_3_position_monitor()
                phase_3_elapsed = time.time() - phase_3_start
                logger.info(f"[PHASE 3] Completed in {phase_3_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                logger.error(f"✗ Phase 3 (Position Monitor) failed: {e}", exc_info=True)
                self.log_phase_result(3, 'position_monitor', 'error', str(e))

            # Phase 3b: Exposure Policy
            phase_3b_start = time.time()
            logger.info(f"\n[PHASE 3b] Starting at {datetime.now(timezone.utc).isoformat()}")
            try:
                with TimeBlock("phase_3b_exposure_policy"):
                    self.phase_3b_exposure_policy()
                phase_3b_elapsed = time.time() - phase_3b_start
                logger.info(f"[PHASE 3b] Completed in {phase_3b_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                logger.error(f"✗ Phase 3b (Exposure Policy) failed: {e}", exc_info=True)
                self.log_phase_result('3b', 'exposure_policy', 'error', str(e))

            # Phase 4: Exit Execution
            phase_4_start = time.time()
            logger.info(f"\n[PHASE 4] Starting at {datetime.now(timezone.utc).isoformat()}")
            try:
                with TimeBlock("phase_4_exit_execution"):
                    result = self.phase_4_exit_execution()
                    if not result:
                        logger.critical("HALT: Phase 4 (Exit Execution) returned False — stopping pipeline")
                        return self._final_report()
                phase_4_elapsed = time.time() - phase_4_start
                logger.info(f"[PHASE 4] Completed in {phase_4_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
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
            phase_5_start = time.time()
            logger.info(f"\n[PHASE 5] Starting at {datetime.now(timezone.utc).isoformat()}")
            try:
                with TimeBlock("phase_5_signal_generation"):
                    result = self.phase_5_signal_generation()
                    if not result:
                        logger.critical("HALT: Phase 5 (Signal Generation) returned False — stopping pipeline")
                        return self._final_report()
                phase_5_elapsed = time.time() - phase_5_start
                logger.info(f"[PHASE 5] Completed in {phase_5_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                logger.error(f"✗ Phase 5 (Signal Generation) failed: {e}", exc_info=True)
                self.log_phase_result(5, 'signal_generation', 'error', str(e))

            # Phase 6: Entry Execution
            phase_6_start = time.time()
            logger.info(f"\n[PHASE 6] Starting at {datetime.now(timezone.utc).isoformat()}")
            try:
                with TimeBlock("phase_6_entry_execution"):
                    result = self.phase_6_entry_execution()
                    if not result:
                        logger.critical("HALT: Phase 6 (Entry Execution) returned False — stopping pipeline")
                        return self._final_report()
                phase_6_elapsed = time.time() - phase_6_start
                logger.info(f"[PHASE 6] Completed in {phase_6_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                logger.error(f"✗ Phase 6 (Entry Execution) failed: {e}", exc_info=True)
                self.log_phase_result(6, 'entry_execution', 'error', str(e))

            # Phase 7: Reconciliation (fail-open — doesn't execute trades, just records state)
            phase_7_start = time.time()
            logger.info(f"\n[PHASE 7] Starting at {datetime.now(timezone.utc).isoformat()}")
            try:
                with TimeBlock("phase_7_reconciliation"):
                    result = self.phase_7_reconcile()
                # Phase 7 is fail-open: if reconciliation fails, we still finalize the report
                # (positions may already be executed, so we must sync state)
                phase_7_elapsed = time.time() - phase_7_start
                logger.info(f"[PHASE 7] Completed in {phase_7_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                logger.error(f"✗ Phase 7 (Reconciliation) failed: {e}", exc_info=True)
                self.log_phase_result(7, 'reconciliation', 'error', str(e))

            # Log performance metrics and total time
            log_metrics_summary()
            total_elapsed = time.time() - run_start
            logger.info(f"\n[TOTAL] Orchestrator run completed in {total_elapsed:.2f}s")
            logger.info(f"[END TIME] {datetime.now(timezone.utc).isoformat()}")
            return self._final_report()
        finally:
            self._release_run_lock()

    def _pid_alive(self, pid):
        """Check if a PID is still running (cross-platform).

        Rejects system PIDs (< 100) which are kernel processes and not real orchestrator instances.
        """
        try:
            if pid < 100:
                # System/kernel PIDs (0-99) can never be orchestrator processes
                # PID 1 = init, PID 2 = kernel scheduler, etc.
                # Treat these as dead (stale lock)
                return False

            if os.name == 'nt':
                # Windows
                import subprocess
                result = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}'],
                    capture_output=True, text=True, timeout=get_subprocess_timeout(),
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

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    import argparse
    parser = argparse.ArgumentParser(description='Run daily algo workflow')
    parser.add_argument('--date', type=str, help='Run date (YYYY-MM-DD)', default=None)
    parser.add_argument('--dry-run', action='store_true', help='Plan only, no real trades')
    parser.add_argument('--init-only', action='store_true', help='Run loaders only, no trading')
    parser.add_argument('--quiet', action='store_true', help='Reduce output')
    args = parser.parse_args()

    run_date = _date.fromisoformat(args.date) if args.date else None

    # ORCHESTRATOR_DRY_RUN env var takes precedence over --dry-run flag.
    # Step Functions TriggerOrchestrator sets this to "true" for pipeline validation runs.
    env_dry_run = os.getenv('ORCHESTRATOR_DRY_RUN', 'false').lower() in ('true', '1', 'yes')
    dry_run = args.dry_run or env_dry_run

    from config.credential_validator import assert_credentials
    assert_credentials(on_failure="warn")

    if args.init_only:
        logger.info("Running in INIT-ONLY mode: loading data without trading")
        # For init-only, skip the orchestrator and just run loaders
        logger.info("To run loaders, execute: python3 run-all-loaders.py")
        sys.exit(0)

    orch = Orchestrator(run_date=run_date, dry_run=dry_run, verbose=not args.quiet)
    try:
        final = orch.run()
        sys.exit(0 if final['success'] else 1)
    finally:
        orch.cleanup()

