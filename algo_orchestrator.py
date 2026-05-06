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

import os
import sys
import psycopg2
import json
import traceback
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date as _date
from algo_alerts import AlertManager
from algo_market_calendar import MarketCalendar

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


class Orchestrator:
    """Daily workflow runner with explicit phases."""

    def __init__(self, config=None, run_date=None, dry_run=False, verbose=True):
        from algo_config import get_config
        self.config = config or get_config()
        self.run_date = run_date or _date.today()
        self.dry_run = dry_run
        self.verbose = verbose
        self.phase_results = {}
        self.run_id = f"RUN-{self.run_date.isoformat()}-{datetime.now().strftime('%H%M%S')}"
        self.lock_file = Path('/tmp/algo_orchestrator.lock')
        self._lock_acquired = False
        self.db_failure_counter_file = Path('/tmp/algo_db_failures.txt')
        self.degraded_mode = False  # B4: Circuit breaker for DB failures
        self.alerts = AlertManager()

    # ---------- Database health monitoring (B4) ----------

    def _check_db_connectivity(self):
        """Test if database is reachable. Returns True if OK, False if failed."""
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            conn.close()
            return True
        except Exception as e:
            print(f"  [ERROR] Database connectivity check failed: {e}")
            return False

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
                    print("  [WARN] No patrol data available")
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
                    print("  [PATROL] No findings in latest patrol")
                return True

            worst_severity, total_findings, critical_count, error_count, warn_count, info_count = row

            if self.verbose:
                print(f"  [PATROL] {latest_run_id}: {total_findings} findings "
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
                    print(f"  [HALT] Data patrol found {critical_count} CRITICAL issues")
                self.log_phase_result(1, 'data_patrol', 'halt',
                                      f'Critical data quality issues: {critical_count} critical findings')
                return False

            # FAIL-CLOSED: too many errors block in auto mode
            if error_count and error_count > 2:
                if self.verbose:
                    print(f"  [HALT] Data patrol found {error_count} ERROR issues")
                self.log_phase_result(1, 'data_patrol', 'halt',
                                      f'Data quality errors: {error_count} findings')
                return False

            # Warnings are just logged, not blocking
            if error_count == 1 or error_count == 2:
                if self.verbose:
                    print(f"  [WARN] Data patrol found {error_count} error(s)")

            return True

        except Exception as e:
            # If patrol check fails, don't block (assume manual run/oversight)
            if self.verbose:
                print(f"  [WARN] Could not check data patrol: {e}")
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
                        print(f"ERROR: Orchestrator already running (PID {old_pid})")
                        return False
                    else:
                        print(f"Stale lock from PID {old_pid} — acquiring")
            except Exception as e:
                print(f"Warning: Could not read lock file: {e}")

        # Acquire lock
        try:
            self.lock_file.write_text(str(os.getpid()))
            self._lock_acquired = True
            if self.verbose:
                print(f"Lock acquired (PID {os.getpid()})")
            return True
        except Exception as e:
            print(f"ERROR: Could not create lock file: {e}")
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
            print(f"\n{'='*70}")
            print(f"PHASE {phase_num}: {name}")
            print(f"{'='*70}")

    def log_phase_result(self, phase_num, name, status, summary):
        self.phase_results[phase_num] = {
            'name': name,
            'status': status,
            'summary': summary,
        }
        if self.verbose:
            print(f"\n-> Phase {phase_num} {status}: {summary}")
        try:
            conn = psycopg2.connect(**DB_CONFIG)
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
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Warning: Could not persist audit log entry: {e}")

    # ---------- Phase implementations ----------

    def phase_1_data_freshness(self):
        self.log_phase_start(1, 'DATA FRESHNESS CHECK')
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()
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

            spy_date, mh_date, tt_date, sqs_date, buys_date = row
            checks = {
                'SPY price data': spy_date,
                'Market health': mh_date,
                'Trend template': tt_date,
                'Signal quality scores': sqs_date,
                'Buy/sell signals': buys_date,
            }
            max_stale = int(self.config.get('max_data_staleness_days', 7))
            stale_items = []
            for name, d in checks.items():
                if d is None:
                    stale_items.append(f"{name}: missing")
                else:
                    age = (self.run_date - d).days
                    if age > max_stale:
                        stale_items.append(f"{name}: {age}d old")
                    if self.verbose:
                        flag = '[OK]' if age <= max_stale else '[STALE]'
                        print(f"  {flag} {name:25s}: latest {d} ({age}d ago)")

            if stale_items:
                cur.close()
                conn.close()
                self.log_phase_result(1, 'data_freshness', 'fail',
                                      f'Stale: {"; ".join(stale_items)}')
                return False

            # NEW: Check data patrol results (quality gate) - cursor still open
            patrol_ok = self._check_data_patrol(cur)

            cur.close()
            conn.close()

            if not patrol_ok:
                return False

            self.log_phase_result(1, 'data_freshness', 'success',
                                  'All data fresh within window')
            return True
        except Exception as e:
            self.log_phase_result(1, 'data_freshness', 'error', str(e))
            return False

    def phase_2_circuit_breakers(self):
        self.log_phase_start(2, 'CIRCUIT BREAKERS')
        try:
            from algo_circuit_breaker import CircuitBreaker
            cb = CircuitBreaker(self.config)
            result = cb.check_all(self.run_date)

            if self.verbose:
                for name, state in result['checks'].items():
                    flag = '[HALT]' if state.get('halted') else '[OK]  '
                    print(f"  {flag} {name:22s}: {state.get('reason', '')}")

            # Check market circuit breakers (market-wide halts, L1/L2/L3)
            try:
                from algo_market_events import MarketEventHandler
                meh = MarketEventHandler(self.config)
                cb_result = meh.check_market_circuit_breaker()
                if cb_result and cb_result.get('triggered'):
                    halt_level = cb_result.get('level', '?')
                    halt_reason = cb_result.get('reason', 'circuit breaker triggered')
                    if self.verbose:
                        print(f"  [HALT] circuit_breaker_L{halt_level:>1s}: {halt_reason}")
                    self.log_phase_result(2, 'market_circuit_breaker', 'halt',
                                        f'L{halt_level} breaker active: {halt_reason}')
                    return False
            except Exception as e:
                self.log_phase_result(2, 'market_circuit_breaker', 'warn', f'check failed: {e}')

            if result['halted']:
                self.log_phase_result(2, 'circuit_breakers', 'halt',
                                      f'Halted: {"; ".join(result["halt_reasons"])}')
                return False
            self.log_phase_result(2, 'circuit_breakers', 'success', 'all clear')
            return True
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result(2, 'circuit_breakers', 'error', str(e))
            return False

    def phase_3_position_monitor(self):
        self.log_phase_start(3, 'POSITION MONITOR')
        try:
            from algo_position_monitor import PositionMonitor
            monitor = PositionMonitor(self.config)

            # Check for single-stock halts on open positions
            try:
                from algo_market_events import MarketEventHandler
                from algo_position_monitor import PositionMonitor
                pm = PositionMonitor(self.config)
                meh = MarketEventHandler(self.config)
                # Get open positions from position monitor
                open_positions = pm.get_open_positions() or []
                halts_found = []
                for pos in open_positions:
                    halt_check = meh.check_single_stock_halt(pos.get('symbol') or pos.get('name', ''))
                    if halt_check and halt_check.get('halted'):
                        symbol = pos.get('symbol') or pos.get('name', '')
                        halts_found.append(symbol)
                        if self.verbose:
                            print(f"  [WARN] {symbol} halted — pending orders cancelled")
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

    def phase_3a_reconciliation(self):
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

    def phase_3b_exposure_policy(self):
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
            print(f"  Exposure: {exposure['exposure_pct']}% ({exposure['regime']})")
            if exposure.get('halt_reasons'):
                print(f"  Halt reasons: {'; '.join(exposure['halt_reasons'])}")

            policy = ExposurePolicy(self.config)
            constraints = policy.get_entry_constraints(self.run_date)
            self._exposure_constraints = constraints
            if constraints:
                print(f"  Tier: {constraints['tier_name']} — {constraints['description']}")
                print(f"    risk_mult={constraints['risk_multiplier']}, "
                      f"max_new/day={constraints['max_new_positions_today']}, "
                      f"min_grade={constraints['min_swing_grade']}, "
                      f"halt_entries={constraints['halt_new_entries']}")

            actions = policy.review_existing_positions(self.run_date)
            self._exposure_actions = actions

            if not actions:
                print(f"  No exposure-policy actions for {len(getattr(self, '_position_recs', []))} open positions")
                self.log_phase_result('3b', 'exposure_policy', 'success',
                                      f'tier={constraints["tier_name"] if constraints else "n/a"}, no actions')
                return True

            counts = {'tighten_stop': 0, 'partial_exit': 0, 'force_exit': 0}
            for action in actions:
                counts[action['action']] = counts.get(action['action'], 0) + 1

            print(f"\n  {len(actions)} exposure-policy actions:")
            for a in actions:
                print(f"    {a['symbol']:6s} -> {a['action'].upper():15s} "
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

    def phase_4_exit_execution(self):
        self.log_phase_start(4, 'EXIT EXECUTION')
        try:
            from algo_trade_executor import TradeExecutor
            from algo_exit_engine import ExitEngine

            executor = TradeExecutor(self.config)
            exit_count = 0
            stop_raises = 0
            errors = 0

            # 4a-prime. Apply exposure-policy actions FIRST (highest priority)
            for action in getattr(self, '_exposure_actions', []):
                try:
                    if self.dry_run:
                        if self.verbose:
                            print(f"  [DRY-RUN] {action['symbol']}: {action['action'].upper()} "
                                  f"({action['reason']})")
                        continue

                    if action['action'] == 'force_exit':
                        # Fetch current price for accurate P&L
                        cur_price = 0
                        try:
                            conn_tmp = psycopg2.connect(**DB_CONFIG)
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
                            print(f"  Warning: Could not fetch price for force_exit: {e}")
                        finally:
                            try:
                                conn_tmp.close()
                            except Exception:
                                pass

                        if cur_price <= 0:
                            print(f"  ERROR: force_exit cannot proceed — no valid current price")
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
                            print(f"  EXPOSURE FORCE-EXIT: {result.get('message', action['symbol'])}")
                        else:
                            errors += 1

                    elif action['action'] == 'partial_exit':
                        # Need current price — fetch
                        cur_price = 0
                        try:
                            conn = psycopg2.connect(**DB_CONFIG)
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
                            print(f"  Warning: Could not fetch current price for {action['position_id']}: {e}")
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
                                print(f"  EXPOSURE PARTIAL: {result['message']}")

                    elif action['action'] == 'tighten_stop':
                        try:
                            conn = psycopg2.connect(**DB_CONFIG)
                            try:
                                cur = conn.cursor()
                                cur.execute(
                                    "UPDATE algo_positions SET current_stop_price = %s WHERE position_id = %s",
                                    (action['new_stop'], action['position_id']),
                                )
                                conn.commit()
                                stop_raises += 1
                                if self.verbose:
                                    print(f"  EXPOSURE TIGHTEN {action['symbol']}: stop -> ${action['new_stop']:.2f}")
                            finally:
                                cur.close()
                        except Exception as e:
                            errors += 1
                            print(f"  Tighten failed for {action['symbol']}: {e}")
                        finally:
                            try:
                                conn.close()
                            except Exception:
                                pass
                except Exception as e:
                    errors += 1
                    print(f"  Error on exposure action {action.get('symbol')}: {e}")

            # 4a. Apply position monitor recommendations (early exits + stop raises)
            for rec in getattr(self, '_position_recs', []):
                try:
                    if self.dry_run:
                        if self.verbose:
                            print(f"  [DRY-RUN] {rec['symbol']}: {rec['action']} ({rec['action_reason']})")
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
                                print(f"  EARLY EXIT: {result['message']}")
                        else:
                            errors += 1
                    elif rec['action'] == 'RAISE_STOP' and rec.get('new_stop_recommended'):
                        # Raise stop without exiting via direct UPDATE
                        try:
                            conn = psycopg2.connect(**DB_CONFIG)
                            cur = conn.cursor()
                            cur.execute(
                                "UPDATE algo_positions SET current_stop_price = %s "
                                "WHERE position_id = %s AND status = 'open'",
                                (rec['new_stop_recommended'], rec['position_id']),
                            )
                            conn.commit()
                            cur.close()
                            conn.close()
                            stop_raises += 1
                            if self.verbose:
                                print(f"  RAISED STOP {rec['symbol']}: ${rec['active_stop']:.2f} -> ${rec['new_stop_recommended']:.2f}")
                        except Exception as e:
                            errors += 1
                            print(f"  Stop-raise failed for {rec['symbol']}: {e}")
                except Exception as e:
                    errors += 1
                    print(f"  Error on {rec.get('symbol')}: {e}")

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

    def phase_4b_pyramid_adds(self):
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
                    print(f"  [DRY-RUN] PYRAMID {r['symbol']} #{r['add_number']}: "
                          f"+{r['add_size_shares']} sh @ ${r['add_price']:.2f}")
                    continue
                result = engine.execute_add(r)
                if result.get('success'):
                    executed += 1
                    print(f"  PYRAMID: {result['message']}")

            self.log_phase_result('4b', 'pyramid_adds', 'success',
                                  f'{len(recs)} recommended, {executed} executed')
            return True
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result('4b', 'pyramid_adds', 'error', str(e))
            return True

    def phase_5_signal_generation(self):
        self.log_phase_start(5, 'SIGNAL GENERATION & RANKING')
        try:
            from algo_filter_pipeline import FilterPipeline
            exposure_mult = 1.0
            if hasattr(self, '_exposure_constraints') and self._exposure_constraints:
                exposure_mult = self._exposure_constraints.get('risk_multiplier', 1.0)
            pipeline = FilterPipeline(exposure_risk_multiplier=exposure_mult)
            qualified = pipeline.evaluate_signals(self.run_date)

            self._qualified_trades = qualified
            self.log_phase_result(
                5, 'signal_generation', 'success',
                f'{len(qualified)} qualified trades after all 6 tiers',
            )
            return True
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result(5, 'signal_generation', 'error', str(e))
            self._qualified_trades = []
            return True

    def phase_6_entry_execution(self):
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
                    print(f"  Tier filter: {before} -> {len(qualified)} "
                          f"(min_score={min_score}, min_grade={min_grade})")

            # Determine open slots
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
                open_count = cur.fetchone()[0] or 0
                cur.close()
                conn.close()
            except Exception:
                open_count = 0
            max_positions = int(self.config.get('max_positions', 6))
            open_slots = max(0, max_positions - open_count)

            # Apply daily entry cap from exposure tier
            if constraints:
                daily_cap = constraints.get('max_new_positions_today', 5)
                open_slots = min(open_slots, daily_cap)

            print(f"  Open positions: {open_count}/{max_positions}, slots available: {open_slots}")
            if constraints:
                print(f"  Tier '{constraints['tier_name']}' caps daily entries at {constraints['max_new_positions_today']}")

            if open_slots == 0:
                self.log_phase_result(6, 'entry_execution', 'success',
                                      f'No room (already {open_count}/{max_positions} or daily cap)')
                return True
            if not qualified:
                self.log_phase_result(6, 'entry_execution', 'success',
                                      'No qualified trades meet tier requirements')
                return True

            entered = 0
            blocked = 0
            errors = 0
            for trade in qualified[:open_slots]:
                if self.dry_run:
                    if self.verbose:
                        print(f"  [DRY-RUN] WOULD ENTER {trade['symbol']}: "
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
                            print(f"  ENTERED: {result['message']}")
                    elif result.get('duplicate'):
                        blocked += 1
                    else:
                        errors += 1
                        print(f"  Failed {trade['symbol']}: {result.get('message')}")
                except Exception as e:
                    errors += 1
                    print(f"  Exception on {trade['symbol']}: {e}")

            self.log_phase_result(
                6, 'entry_execution', 'success',
                f'{entered} entered, {blocked} blocked (duplicates), {errors} errors',
            )
            return True
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result(6, 'entry_execution', 'error', str(e))
            return True

    def phase_7_reconcile(self):
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

            return True
        except Exception as e:
            traceback.print_exc()
            self.log_phase_result(7, 'reconciliation', 'error', str(e))
            return True

    # ---------- Main entrypoint ----------

    def run(self):
        print(f"\n{'#'*70}")
        print(f"#   ALGO ORCHESTRATOR — {self.run_date}  ({'DRY RUN' if self.dry_run else 'LIVE'})")
        print(f"#   run_id: {self.run_id}")
        print(f"{'#'*70}")

        # Check market calendar
        if not MarketCalendar.is_trading_day(self.run_date):
            status = MarketCalendar.market_status(datetime.combine(self.run_date, datetime.min.time()))
            print(f"\n⏸️  Market closed: {status['reason']}")
            print("Skipping all trading phases.\n")
            return {'success': False, 'error': f"Market closed: {status['reason']}"}

        # Concurrency lock — prevent two orchestrators running at once
        # which would risk duplicate trades or double-counting circuit breakers
        lock_path = Path(__file__).parent / '.algo_orchestrator.lock'
        existing_pid = None
        if lock_path.exists():
            try:
                existing_pid = int(lock_path.read_text().strip())
                # Check if PID is alive
                if self._pid_alive(existing_pid):
                    print(f"\nABORT: Orchestrator already running (PID {existing_pid}). "
                          "Wait for it to finish or kill it.")
                    return {'success': False, 'error': f'lock held by PID {existing_pid}'}
                else:
                    print(f"  (Stale lock from PID {existing_pid} — clearing)")
            except Exception:
                pass

        # Acquire lock
        try:
            lock_path.write_text(str(os.getpid()))
        except Exception as e:
            print(f"  (warning: couldn't write lock file: {e})")

        try:
            # Run data patrol first (before DB check, but will silently fail if DB down)
            # Note: Use quick=True for the 5 critical checks only (staleness, universe, zeros, corp actions, DB constraints)
            # Full patrol (16 checks) is run separately on a slower schedule
            print("\nRunning critical data patrol checks...")
            try:
                from algo_data_patrol import DataPatrol
                patrol = DataPatrol()
                patrol.run(quick=True)  # Only run the 5 critical checks, not the full 16-check suite
            except Exception as e:
                print(f"  [WARN] Data patrol failed: {e}")

            # B4: Check database connectivity — fail-closed on multiple consecutive failures
            if not self._check_db_connectivity():
                failures = self._increment_db_failure_counter()
                if failures >= 3:
                    self.degraded_mode = True
                    print(f"\n[CRITICAL] Database down for {failures} consecutive runs — ENTERING DEGRADED MODE")
                    print("Skipping all trading phases. Continuing with monitoring only.")
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
                    print(f"\n[ERROR] Database connectivity failed ({failures}/3). Will halt if persists.")
                    return self._final_report()
            else:
                self._reset_db_failure_counter()

            if getattr(self, 'skip_freshness', False):
                print("\nNOTE: Phase 1 freshness gate skipped (--skip-freshness flag set).")
                self.log_phase_result(1, 'freshness_bypassed', 'override',
                                     '--skip-freshness flag used — data freshness check skipped')
            elif not self.phase_1_data_freshness():
                print("\nFAIL-CLOSED: Data freshness check failed. Halting pipeline.")
                return self._final_report()

            if not self.phase_2_circuit_breakers():
                print("\nHALT: Circuit breaker fired. Will still review positions but skip new entries.")
                self.phase_3a_reconciliation()
                self.phase_3_position_monitor()
                self.phase_3b_exposure_policy()
                self.phase_4_exit_execution()
                self.phase_7_reconcile()
                return self._final_report()

            self.phase_3a_reconciliation()
            self.phase_3_position_monitor()
            self.phase_3b_exposure_policy()
            self.phase_4_exit_execution()
            self.phase_4b_pyramid_adds()
            self.phase_5_signal_generation()
            self.phase_6_entry_execution()
            self.phase_7_reconcile()

            return self._final_report()
        finally:
            # Always release the lock, even on exception
            try:
                if lock_path.exists():
                    held_pid = int(lock_path.read_text().strip())
                    if held_pid == os.getpid():
                        lock_path.unlink()
            except Exception:
                pass

    def _is_market_open_or_imminent(self, window_min: int = 30) -> bool:
        """Return True if US equity market is open right now OR opens within
        `window_min` minutes. Queries Alpaca's /v2/clock — authoritative for
        holidays, half-days, etc. In auto mode, fails closed (returns False) on
        API failure so we don't trade when market status is unknown."""
        try:
            import requests
            key = os.getenv('APCA_API_KEY_ID')
            secret = os.getenv('APCA_API_SECRET_KEY')
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
                print(f"  [ERROR] market-hours check failed: {e} — failing closed (no entries in auto mode)")
                return False
            print(f"  [warn] market-hours check failed: {e} — proceeding in {mode} mode")
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
        print(f"\n{'#'*70}")
        print(f"#   FINAL REPORT — {self.run_id}")
        print(f"{'#'*70}")
        for n, info in sorted(self.phase_results.items(), key=lambda x: str(x[0])):
            status_flag = {
                'success': '[OK] ',
                'halt':    '[HALT]',
                'fail':    '[FAIL]',
                'error':   '[ERR] ',
            }.get(info['status'], '[?]   ')
            print(f"  {status_flag} Phase {n}: {info['name']:22s} — {info['summary']}")
        print(f"{'#'*70}\n")

        return {
            'run_id': self.run_id,
            'run_date': self.run_date.isoformat(),
            'phases': self.phase_results,
            'success': all(p['status'] in ('success', 'halt') for p in self.phase_results.values()),
        }


if __name__ == "__main__":
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
        print("WARNING: --skip-freshness is set. Data may be stale. Do NOT use for live trading.")
    final = orch.run()
    sys.exit(0 if final['success'] else 1)
