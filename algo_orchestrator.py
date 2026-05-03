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

    def __init__(self, run_date=None, dry_run=False, verbose=True):
        from algo_config import get_config
        self.config = get_config()
        self.run_date = run_date or _date.today()
        self.dry_run = dry_run
        self.verbose = verbose
        self.phase_results = {}
        self.run_id = f"RUN-{self.run_date.isoformat()}-{datetime.now().strftime('%H%M%S')}"

    # ---------- Logging helpers ----------

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
        except Exception:
            pass

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
            cur.close()
            conn.close()

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
                self.log_phase_result(1, 'data_freshness', 'fail',
                                      f'Stale: {"; ".join(stale_items)}')
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
                        result = executor.exit_trade(
                            trade_id=action['trade_id'],
                            exit_price=0,  # filled at market — we'll compute current price below
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
                        try:
                            conn = psycopg2.connect(**DB_CONFIG)
                            cur = conn.cursor()
                            cur.execute(
                                "SELECT current_price FROM algo_positions WHERE position_id = %s",
                                (action['position_id'],),
                            )
                            row = cur.fetchone()
                            cur.close(); conn.close()
                            cur_price = float(row[0]) if row and row[0] else 0
                        except Exception:
                            cur_price = 0
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
                            cur = conn.cursor()
                            cur.execute(
                                "UPDATE algo_positions SET current_stop_price = %s WHERE position_id = %s",
                                (action['new_stop'], action['position_id']),
                            )
                            conn.commit()
                            cur.close(); conn.close()
                            stop_raises += 1
                            if self.verbose:
                                print(f"  EXPOSURE TIGHTEN {action['symbol']}: stop -> ${action['new_stop']:.2f}")
                        except Exception as e:
                            errors += 1
                            print(f"  Tighten failed for {action['symbol']}: {e}")
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
            pipeline = FilterPipeline()
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
            if not self.phase_1_data_freshness():
                print("\nFAIL-CLOSED: Data freshness check failed. Halting pipeline.")
                return self._final_report()

            if not self.phase_2_circuit_breakers():
                print("\nHALT: Circuit breaker fired. Will still review positions but skip new entries.")
                self.phase_3_position_monitor()
                self.phase_3b_exposure_policy()
                self.phase_4_exit_execution()
                self.phase_7_reconcile()
                return self._final_report()

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
    args = parser.parse_args()

    run_date = _date.fromisoformat(args.date) if args.date else None
    orch = Orchestrator(run_date=run_date, dry_run=args.dry_run, verbose=not args.quiet)
    final = orch.run()
    sys.exit(0 if final['success'] else 1)
