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

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None
credential_manager = get_credential_manager()

import os
import sys
import tempfile
import psycopg2
import traceback
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date as _date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from algo_alerts import AlertManager
from algo_market_calendar import MarketCalendar
from trade_status import PositionStatus
import logging
from monitoring_context import TimeBlock, log_metrics_summary, clear_metrics_buffer

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Get DB config (lazy-loaded to support testing without credentials)."""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": credential_manager.get_db_credentials()["password"],
        "database": os.getenv("DB_NAME", "stocks"),
    }


class Orchestrator:
    """Daily workflow runner with explicit phases."""

    def __init__(self, config=None, run_date=None, dry_run=False, verbose=True, init_db=True):
        from algo_config import get_config
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

        if init_db:
            self._ensure_schema_initialized()

    # ---------- Database health monitoring (B4) ----------

    def _check_db_connectivity(self):
        """Test if database is reachable. Returns True if OK, False if failed."""
        conn = None
        cur = None
        try:
            conn = psycopg2.connect(**_get_db_config())
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
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _increment_db_failure_counter(self):
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

    def _reset_db_failure_counter(self):
        """Reset counter on successful DB connection."""
        try:
            if self.db_failure_counter_file.exists():
                self.db_failure_counter_file.unlink()
        except Exception:
            pass

    def _ensure_schema_initialized(self):
        """Initialize database schema if not already present. Idempotent."""
        conn = None
        cur = None
        try:
            conn = psycopg2.connect(**_get_db_config())
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
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _check_data_patrol(self, cur):
        """Check data patrol results. Fail-closed if critical/error findings.

        Only checks the LATEST patrol run (not accumulated from all runs in 24h).
        Returns: True if patrol OK, False if critical/error issues found.
        """
        try:
            # Get LATEST patrol run ID first
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
            # If patrol check fails, don't block (assume manual run/oversight)
            if self.verbose:
                logger.warning(f"  [WARN] Could not check data patrol: {e}")
            return True

    # ---------- Logging helpers ----------

    def _acquire_run_lock(self):
        """Acquire exclusive lock to prevent concurrent orchestrator runs.

        Uses file-based locking with PID checking. If another instance holds the lock
        but its PID is dead, steal the lock and continue.

        Returns: True if lock acquired, False if another active instance holds it.
        """
        if self.lock_file.exists():
            try:
                lock_content = self.lock_file.read_text().strip()
                if lock_content:
                    old_pid = int(lock_content)
                    if self._pid_alive(old_pid):
                        logger.error(f"ERROR: Orchestrator already running (PID {old_pid})")
                        return False
                    else:
                        logger.info(f"Stale lock from PID {old_pid} — acquiring")
            except Exception as e:
                logger.warning(f"Warning: Could not read lock file: {e}")

        # Acquire lock
        try:
            self.lock_file.write_text(str(os.getpid()))
            self._lock_acquired = True
            if self.verbose:
                logger.info(f"Lock acquired (PID {os.getpid()})")
            return True
        except Exception as e:
            logger.error(f"ERROR: Could not create lock file: {e}")
            return False

    def _release_run_lock(self):
        """Release the run lock."""
        if self._lock_acquired and self.lock_file.exists():
            try:
                self.lock_file.unlink()
                self._lock_acquired = False
            except Exception:
                pass

    def log_phase_start(self, phase_num, name):
        if self.verbose:
            logger.info(f"\n{'='*70}")
            logger.info(f"PHASE {phase_num}: {name}")
            logger.info(f"{'='*70}")

    def log_phase_result(self, phase_num, name, status, summary):
        import json
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
            conn = psycopg2.connect(**_get_db_config())
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
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # ---------- Pipeline Health & Visibility ----------

    def _check_pipeline_health(self, cur):
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
                'signal_quality_scores': 'signal_quality_scores (SQS >= 60 gate)',
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
                        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE date >= %s", (five_days_ago,))
                    elif table in ('buy_sell_daily', 'trend_template_data', 'technical_data_daily',
                                  'signal_quality_scores', 'swing_trader_scores', 'market_health_daily',
                                  'sector_ranking', 'industry_ranking', 'stock_scores'):
                        # Different tables use different date column names
                        if table == 'stock_scores':
                            col = 'score_date'
                        elif table in ('sector_ranking', 'industry_ranking'):
                            col = 'date_recorded'
                        else:
                            col = 'date'
                        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} >= %s", (five_days_ago,))
                    else:
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

    def _report_signal_waterfall(self):
        """Log signal count at each filter tier for visibility on rejections."""
        conn = None
        cur = None
        try:
            conn = psycopg2.connect(**_get_db_config())
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
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _interpret_waterfall(self, total, stage2, tier_rejections, final):
        """Interpret the signal waterfall to help diagnose 'no trades' situations."""
        if total == 0:
            return "No BUY signals generated today. Check buy_sell_daily loader or market conditions."
        if stage2 == 0:
            return f"{total} signals exist but NONE are Stage 2. RSI<30 in Stage 2 stocks is rare. Check market stage."
        if final > 0:
            return f"✓ {final} candidates qualified. Ready to execute."

        # Find the biggest rejection point
        max_reject_tier = max(tier_rejections, key=tier_rejections.get) if tier_rejections else "Unknown"
        max_reject_count = tier_rejections.get(max_reject_tier, 0)
        return f"Stage 2 signals exist but {max_reject_count} rejected at {max_reject_tier}. Review config thresholds."

    # ---------- Phase implementations ----------

    def phase_1_data_freshness(self) -> bool:
        self.log_phase_start(1, 'DATA FRESHNESS CHECK')
        conn = None
        cur = None
        try:
            conn = psycopg2.connect(**_get_db_config())
            cur = conn.cursor()

            # Check critical loader SLA status first — fail-closed if data didn't load
            try:
                from loader_sla_tracker import get_tracker
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

            # Check loader health via monitor — fail-closed if critical data missing
            try:
                from algo_loader_monitor import LoaderMonitor
                monitor = LoaderMonitor()
                monitor.connect()
                try:
                    critical_symbols = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'SPY']
                    findings = monitor.audit_all(critical_symbols=critical_symbols)

                    # Check for CRITICAL findings (missing symbols, low volume)
                    critical_findings = [f for f in findings if f[0] == 'CRITICAL']
                    error_findings = [f for f in findings if f[0] == 'ERROR']

                    if critical_findings or error_findings:
                        self.alerts.send_loader_alert(findings)

                    if critical_findings:
                        messages = [f[2] for f in critical_findings]
                        self.log_phase_result(1, 'loader_health', 'halt',
                                              f'Loader critical: {"; ".join(messages)}')
                        return False

                    # Fail-closed on ERROR if it's a data volume issue (0 symbols loaded today)
                    volume_error = [e for e in error_findings if 'low_daily_load_volume' in e[1]]
                    if volume_error:
                        for _, _, msg in volume_error:
                            if '0 symbols' in msg:  # Zero data loaded today
                                self.log_phase_result(1, 'loader_health', 'halt',
                                                      f'No data loaded today: {msg}')
                                return False

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
            max_stale = int(self.config.get('max_data_staleness_days', 7))
            stale_items = []

            try:
                from algo_metrics import MetricsPublisher
                _metrics = MetricsPublisher(dry_run=self.dry_run)
            except Exception:
                _metrics = None

            for name, d in checks.items():
                if d is None:
                    stale_items.append(f"{name}: missing")
                    if _metrics:
                        _metrics.put_data_freshness(table_keys[name], 999)
                else:
                    age = (self.run_date - d).days
                    if _metrics:
                        _metrics.put_data_freshness(table_keys[name], age)
                    if age > max_stale:
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
                from algo_margin_monitor import MarginMonitor
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
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def phase_2_circuit_breakers(self) -> bool:
        self.log_phase_start(2, 'CIRCUIT BREAKERS')
        try:
            from algo_circuit_breaker import CircuitBreaker
            cb = CircuitBreaker(self.config)
            result = cb.check_all(self.run_date)

            if self.verbose:
                for name, state in result['checks'].items():
                    flag = '[HALT]' if state.get('halted') else '[OK]  '
                    logger.info(f"  {flag} {name:22s}: {state.get('reason', '')}")

            # Publish per-breaker CloudWatch metrics (non-blocking)
            try:
                from algo_metrics import MetricsPublisher
                with MetricsPublisher(dry_run=self.dry_run) as _m:
                    for name, state in result.get('checks', {}).items():
                        _m.put_circuit_breaker(name, bool(state.get('halted')))
            except Exception:
                pass

            # Check market circuit breakers (market-wide halts, L1/L2/L3)
            try:
                from algo_market_events import MarketEventHandler
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
            from algo_position_monitor import PositionMonitor
            monitor = PositionMonitor(self.config)

            # Check for single-stock halts on open positions
            try:
                from algo_market_events import MarketEventHandler
                meh = MarketEventHandler(self.config)
                # Get open positions from position monitor
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
                # Halt check is non-critical; fail gracefully
                pass

            # Check for stale orders first
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
            from algo_reconciliation import PositionReconciler
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
            from algo_market_exposure import MarketExposure
            from algo_market_exposure_policy import ExposurePolicy
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
        try:
            from algo_trade_executor import TradeExecutor
            from algo_exit_engine import ExitEngine

            # Detect Phase 3 crash: if position monitor errored, _position_recs is []
            # but we may have real open positions. Log a critical alert so we know.
            position_recs = getattr(self, '_position_recs', None)
            if position_recs is None:
                logger.critical("Phase 4: _position_recs not set — Phase 3 may not have run")
            elif len(position_recs) == 0:
                # Check whether there are actually open positions to distinguish
                # "no positions" from "Phase 3 crashed with fail-open"
                try:
                    import psycopg2
                    conn_chk = psycopg2.connect(**_get_db_config())
                    with conn_chk:
                        with conn_chk.cursor() as cur_chk:
                            cur_chk.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
                            open_count = cur_chk.fetchone()[0]
                    if open_count > 0:
                        logger.error(
                            f"Phase 4: _position_recs is empty but {open_count} open positions exist "
                            "— Phase 3 likely crashed (fail-open). Early-exit logic will be skipped."
                        )
                except Exception:
                    pass

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
                            conn_tmp = psycopg2.connect(**_get_db_config())
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
                            except Exception:
                                pass

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
                            conn = psycopg2.connect(**_get_db_config())
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
                            except Exception:
                                pass
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
                            conn = psycopg2.connect(**_get_db_config())
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
                            except Exception:
                                pass
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
                            conn = psycopg2.connect(**_get_db_config())
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
                                except Exception:
                                    pass
                            if conn:
                                try:
                                    conn.close()
                                except Exception:
                                    pass
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
            return True

    def phase_4b_pyramid_adds(self) -> List[Dict[str, Any]]:
        """Add to winners (Livermore) — runs after exits, before new entries."""
        self.log_phase_start('4b', 'PYRAMID ADDS (winners)')
        try:
            from algo_pyramid import PyramidEngine
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
        try:
            from algo_filter_pipeline import FilterPipeline
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
                from algo_metrics import MetricsPublisher
                with MetricsPublisher(dry_run=self.dry_run) as _m:
                    _m.put_circuit_breaker('PortfolioValueUnavailable', fired=True)
            except Exception:
                pass
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
        try:
            from algo_trade_executor import TradeExecutor
            executor = TradeExecutor(self.config)
            qualified = getattr(self, '_qualified_trades', [])
            constraints = getattr(self, '_exposure_constraints', None)

            # Market-hours gate: refuse entries unless market is open OR within
            # 30 min of open (queued for opening cross). Skip the gate in
            # paper/dry/review mode so testing works after hours, but enforce
            # strictly on auto/live.
            mode = (self.config.get('execution_mode', 'paper') if isinstance(self.config, dict) else 'paper').lower()
            if mode == 'auto':
                if not self._is_market_open_or_imminent():
                    self.log_phase_result(
                        6, 'entry_execution', 'success',
                        'Market closed and not within 30min of open — skipping entries'
                    )
                    return True

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
                qualified = [
                    t for t in qualified
                    if (t.get('swing_score', 0) >= min_score and
                        grade_order.index(t.get('swing_grade', 'F')) >= min_grade_idx)
                ]
                if len(qualified) < before:
                    logger.info(f"  Tier filter: {before} -> {len(qualified)} "
                                f"(min_score={min_score}, min_grade={min_grade})")

            # Determine open slots
            conn = None
            cur = None
            try:
                conn = psycopg2.connect(**_get_db_config())
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = %s", (PositionStatus.OPEN.value,))
                open_count = cur.fetchone()[0] or 0
            except Exception:
                open_count = 0
            finally:
                if cur:
                    try:
                        cur.close()
                    except Exception:
                        pass
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
            max_positions = int(self.config.get('max_positions', 6))
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
                from algo_margin_monitor import MarginMonitor
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

                    # Get stop method from pipeline if available
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
                    logger.info(f"  Exception on {trade['symbol']}: {e}")

            self.log_phase_result(
                6, 'entry_execution', 'success',
                f'{entered} entered, {blocked} blocked (duplicates), {errors} errors',
            )
            self.phase_results[6]['trades_executed'] = entered
            return True
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result(6, 'entry_execution', 'error', str(e))
            return True

    def phase_7_reconcile(self) -> Dict[str, Any]:
        self.log_phase_start(7, 'RECONCILIATION & SNAPSHOT')
        try:
            from algo_daily_reconciliation import DailyReconciliation
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
                from algo_performance import LivePerformance
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

            # Compute and log portfolio risk metrics (Phase 8)
            # IMPORTANT: Each module handles its own DB connection/transaction
            # Do NOT assume previous module's transaction is clean
            risk_status = 'warn'
            risk_summary = 'N/A'
            try:
                from algo_var import PortfolioRisk
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

        # Check market calendar
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
            # Run data patrol first (before DB check, but will silently fail if DB down)
            # Note: Use quick=True for the 5 critical checks only (staleness, universe, zeros, corp actions, DB constraints)
            # Full patrol (16 checks) is run separately on a slower schedule
            logger.info("\nRunning critical data patrol checks...")
            try:
                from algo_data_patrol import DataPatrol
                patrol = DataPatrol()
                patrol.run(quick=True)  # Only run the 5 critical checks, not the full 16-check suite
            except Exception as e:
                logger.error(f"  [WARN] Data patrol failed: {e}")

            # Load stock quality scores (daily quality/growth/momentum/value ratings)
            # This populates the stock_scores table used by advanced filters
            logger.info("\nLoading stock quality scores...")
            try:
                from loadstockscores import StockScoresLoader, get_active_symbols
                symbols = get_active_symbols()
                if not symbols:
                    logger.warning("  [WARN] No active symbols available for stock scores loader")
                else:
                    loader = StockScoresLoader()
                    stats = loader.run(symbols=symbols, parallelism=4)  # Moderate parallelism, doesn't block trading
                    if self.verbose:
                        logger.info(f"  Stock scores loaded: {stats.get('symbols_loaded', 0)} symbols, "
                                   f"{stats.get('symbols_failed', 0)} failures")
                    loader.close()
            except Exception as e:
                logger.warning(f"  [WARN] Stock scores load failed (won't block trading): {e}")

            # B4: Check database connectivity — fail-closed on multiple consecutive failures
            if not self._check_db_connectivity():
                failures = self._increment_db_failure_counter()
                if failures >= 3:
                    self.degraded_mode = True
                    logger.error(f"\n[CRITICAL] Database down for {failures} consecutive runs — ENTERING DEGRADED MODE")
                    logger.info("Skipping all trading phases. Continuing with monitoring only.")
                    try:
                        from algo_notifications import notify
                        notify(
                            'critical',
                            title='Database Circuit Breaker Activated',
                            message=f'DB unreachable for {failures} runs. System in degraded mode. No trading.'
                        )
                    except Exception:
                        pass
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
                    if not self.phase_1_data_freshness():
                        logger.error("\nFAIL-CLOSED: Data freshness check failed. Halting pipeline.")
                        return self._final_report()
                except Exception as e:
                    logger.error(f"\nERROR in phase 1 (data freshness): {e}. Halting pipeline.")
                    self.log_phase_result(1, 'data_freshness', 'error', str(e))
                    return self._final_report()

            if not self.phase_2_circuit_breakers():
                logger.info("\nHALT: Circuit breaker fired. Will still review positions but skip new entries.")
                self.phase_3a_reconciliation()
                self.phase_3_position_monitor()
                self.phase_3b_exposure_policy()
                self.phase_4_exit_execution()
                self.phase_7_reconcile()
                return self._final_report()

            self.phase_3a_reconciliation()
            with TimeBlock("phase_3_position_monitor"):
                self.phase_3_position_monitor()
            self.phase_3b_exposure_policy()
            self.phase_4_exit_execution()
            self.phase_4b_pyramid_adds()
            with TimeBlock("phase_5_signal_generation"):
                self.phase_5_signal_generation()
            with TimeBlock("phase_6_entry_execution"):
                self.phase_6_entry_execution()
            self.phase_7_reconcile()

            # Log performance metrics at end
            log_metrics_summary()
            return self._final_report()
        finally:
            self._release_run_lock()

    def _is_market_open_or_imminent(self, window_min: int = 30) -> bool:
        """Return True if US equity market is open right now OR opens within
        `window_min` minutes. Queries Alpaca's /v2/clock — authoritative for
        holidays, half-days, etc. In auto mode, fails closed (returns False) on
        API failure so we don't trade when market status is unknown."""
        try:
            import requests
            key = credential_manager.get_alpaca_credentials()["key"]
            secret = credential_manager.get_alpaca_credentials()["secret"]
            base = os.getenv('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets')
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
            from algo_metrics import MetricsPublisher
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
    from algo_logging import configure_root_logger
    configure_root_logger(level=os.getenv("LOG_LEVEL", "INFO"))

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
    if args.skip_freshness:
        orch.skip_freshness = True
        logger.warning("WARNING: --skip-freshness is set. Data may be stale. Do NOT use for live trading.")
    final = orch.run()
    sys.exit(0 if final['success'] else 1)
