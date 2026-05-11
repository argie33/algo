#!/usr/bin/env python3
"""
Circuit Breakers - Kill-switch risk halts (institutional safety layer)

Halts trading when any of these fire:
  CB1. PORTFOLIO DRAWDOWN  >= halt_drawdown_pct (default 20%)
  CB2. DAILY LOSS          >= max_daily_loss_pct (default 2%)
  CB3. CONSECUTIVE LOSSES  >= max_consecutive_losses (default 3)
  CB4. TOTAL OPEN RISK     >= max_total_risk_pct (default 4%)
  CB5. VIX SPIKE           > vix_max_threshold (default 35)
  CB6. MARKET STAGE BREAK  market_stage = 4 (downtrend)
  CB7. WEEKLY LOSS         >= max_weekly_loss_pct (default 5%)
  CB8. DATA STALENESS      latest data > N days old

Each check returns (halted, reason). The orchestrator runs all checks before
new entries — any halt blocks new positions but does NOT auto-exit existing
ones (those are managed by exit_engine + position_monitor).

When a circuit breaker fires:
  - logged in algo_audit_log with action_type='circuit_breaker'
  - returned to caller for display / notification
  - persists state until cleared (e.g., recovery threshold met)
"""

from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import os
import json
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date as _date
from typing import Dict, List, Any, Tuple
from trade_status import TradeStatus, PositionStatus
import logging

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
    }


class CircuitBreaker:
    """Pre-trade kill-switch checks."""

    def __init__(self, config):
        self.config = config
        self.conn = None
        self.cur = None

    def connect(self):
        self.conn = psycopg2.connect(**_get_db_config())
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def check_all(self, current_date: Any = None) -> Dict[str, Any]:
        """Run all circuit breakers. Returns dict with per-check status."""
        if not current_date:
            current_date = _date.today()

        self.connect()
        try:
            results = {
                'halted': False,
                'halt_reasons': [],
                'checks': {},
            }

            for name, fn in [
                ('drawdown', self._check_drawdown),
                ('drawdown_re_engagement', self._check_drawdown_re_engagement),  # C2: Re-engagement protocol
                ('daily_loss', self._check_daily_loss),
                ('consecutive_losses', self._check_consecutive_losses),
                ('win_rate_floor', self._check_win_rate_floor),
                ('total_risk', self._check_total_risk),
                ('vix_spike', self._check_vix_spike),
                ('market_stage', self._check_market_stage),
                ('intraday_market_health', self._check_intraday_market_health),
                ('weekly_loss', self._check_weekly_loss),
                ('sector_concentration', self._check_sector_concentration),
                ('daily_profit_cap', self._check_daily_profit_cap),
                ('data_freshness', self._check_data_freshness),
            ]:
                try:
                    state = fn(current_date)
                except Exception as e:
                    state = {'halted': False, 'reason': f'check error: {e}'}
                results['checks'][name] = state
                if state.get('halted'):
                    results['halted'] = True
                    results['halt_reasons'].append(f"{name}: {state['reason']}")

            # Persist if halted
            if results['halted']:
                self._log_halt(results)

            return results
        except Exception as e:
            logger.error(f"CRITICAL ERROR in circuit breaker check: {e}")
            import traceback
            traceback.print_exc()
            # B12: Fail-closed — if circuit breaker logic itself fails, halt trading
            # Do NOT allow trading when we can't verify safety checks
            try:
                from algo_notifications import notify
                notify(
                    'critical',
                    title='CIRCUIT BREAKER CHECK FAILED',
                    message=f'Circuit breaker logic crashed: {e}. Trading halted until resolved.'
                )
            except Exception:
                pass
            return {
                'halted': True,
                'halt_reasons': [f'Circuit breaker check failed: {e}'],
                'checks': {}
            }
        finally:
            self.disconnect()

    # ---------- Individual checks ----------

    def _check_drawdown(self, current_date: Any) -> Dict[str, Any]:
        self.cur.execute(
            """
            SELECT MAX(total_portfolio_value),
                   (SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1)
            FROM algo_portfolio_snapshots
            """
        )
        row = self.cur.fetchone()
        if not row or not row[0] or not row[1]:
            return {'halted': True, 'reason': 'Portfolio history missing — fail-closed'}
        peak = float(row[0])
        cur_val = float(row[1])
        if peak <= 0 or cur_val <= 0:
            return {'halted': True, 'reason': 'Invalid portfolio values — fail-closed'}
        dd = ((peak - cur_val) / peak * 100.0)
        threshold = float(self.config.get('halt_drawdown_pct', 20.0))
        return {
            'halted': dd >= threshold,
            'reason': f'Drawdown {dd:.2f}% >= {threshold:.0f}%' if dd >= threshold else f'Drawdown {dd:.2f}%',
            'value': round(dd, 2),
            'threshold': threshold,
        }

    def _check_drawdown_re_engagement(self, current_date: Any) -> Dict[str, Any]:
        """C2: Drawdown Re-engagement Protocol.

        After a drawdown halt, require conditions to resume:
        1. Portfolio recovered to within N% of peak (not at peak)
        2. Market shows Follow-Through Day signal (optional)
        3. At least N days have passed since halt
        """
        threshold = float(self.config.get('halt_drawdown_pct', 20.0))

        # First check: is current drawdown >= threshold? If not, no re-engagement needed
        self.cur.execute(
            """
            SELECT MAX(total_portfolio_value),
                   (SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1)
            FROM algo_portfolio_snapshots
            """
        )
        row = self.cur.fetchone()
        if not row or not row[0] or not row[1]:
            return {'halted': False, 'reason': 'No halt history'}

        peak = float(row[0])
        cur_val = float(row[1])
        if peak <= 0 or cur_val <= 0:
            return {'halted': False, 'reason': 'Invalid values'}

        dd = ((peak - cur_val) / peak * 100.0)

        # If NOT currently halted due to drawdown, no re-engagement check needed
        if dd < threshold:
            return {'halted': False, 'reason': 'Not in drawdown halt'}

        # We ARE in drawdown halt. Check if we can resume.
        recovery_threshold = float(self.config.get('re_engage_recovery_pct', 8.0))
        min_days_elapsed = int(self.config.get('re_engage_min_days', 5))
        require_ftd = bool(self.config.get('require_ftd_to_re_engage', True))

        # Check 1: Has portfolio recovered to within recovery_threshold of peak?
        recovery_pct = (peak - cur_val) / peak * 100.0  # Current distance from peak
        if recovery_pct > recovery_threshold:
            return {
                'halted': True,
                'reason': f'Drawdown {dd:.1f}%, need recovery to {recovery_threshold:.1f}% to resume (currently {recovery_pct:.1f}%)',
            }

        # Check 2: Has enough time elapsed since halt?
        # Find the date of the latest drawdown halt event
        days_elapsed = 0
        self.cur.execute(
            """
            SELECT created_at FROM algo_audit_log
            WHERE action_type = 'circuit_breaker' AND details ILIKE '%drawdown%'
            ORDER BY created_at DESC LIMIT 1
            """
        )
        halt_row = self.cur.fetchone()
        if halt_row:
            halt_date = halt_row[0]
            days_elapsed = (current_date - halt_date.date()).days if isinstance(halt_date, datetime) else (current_date - halt_date).days
            if days_elapsed < min_days_elapsed:
                return {
                    'halted': True,
                    'reason': f'Halt occurred {days_elapsed}d ago, need {min_days_elapsed}d to elapse before resume',
                }

        # Check 3: Require Follow-Through Day signal (optional)
        if require_ftd:
            # A Follow-Through Day is when SPY up 1.25%+ on higher volume after a pullback/correction
            # For now, simplified check: market is in Stage 2
            self.cur.execute(
                "SELECT market_stage FROM market_health_daily ORDER BY date DESC LIMIT 1"
            )
            market_row = self.cur.fetchone()
            if not market_row or market_row[0] != 2:
                return {
                    'halted': True,
                    'reason': 'Recovery conditions met, but market not in Stage 2 uptrend (waiting for Follow-Through Day)',
                }

        # All conditions met — re-engagement approved
        return {
            'halted': False,
            'reason': f'Re-engagement approved: recovered to {recovery_pct:.1f}%, {days_elapsed}d elapsed, market Stage 2',
        }

    def _check_daily_loss(self, current_date: Any) -> Dict[str, Any]:
        self.cur.execute(
            "SELECT daily_return_pct FROM algo_portfolio_snapshots WHERE snapshot_date = %s",
            (current_date,),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None:
            return {'halted': False, 'reason': 'No today snapshot yet'}
        daily = float(row[0])
        threshold = -float(self.config.get('max_daily_loss_pct', 2.0))
        return {
            'halted': daily <= threshold,
            'reason': f'Daily loss {daily:.2f}% <= {threshold:.1f}%' if daily <= threshold else f'Daily {daily:+.2f}%',
            'value': round(daily, 2),
            'threshold': threshold,
        }

    def _check_consecutive_losses(self, current_date: Any) -> Dict[str, Any]:
        self.cur.execute(
            """
            SELECT profit_loss_pct, exit_date FROM algo_trades
            WHERE status = %s AND exit_date IS NOT NULL
            ORDER BY exit_date DESC, id DESC
            LIMIT 10
            """,
            (TradeStatus.CLOSED.value,)
        )
        rows = self.cur.fetchall()
        if not rows:
            return {'halted': False, 'reason': 'No closed trades'}
        # Count consecutive losses from most recent
        streak = 0
        for r in rows:
            pnl = float(r[0]) if r[0] is not None else 0
            if pnl < 0:
                streak += 1
            else:
                break
        threshold = int(self.config.get('max_consecutive_losses', 3))
        return {
            'halted': streak >= threshold,
            'reason': f'{streak} consecutive losses >= {threshold}' if streak >= threshold else f'{streak} losses',
            'value': streak,
            'threshold': threshold,
        }

    def _check_win_rate_floor(self, current_date: Any) -> Dict[str, Any]:
        """Halt if recent win rate drops below floor (e.g., 40% of last 30 closed trades)."""
        self.cur.execute(
            """
            SELECT COUNT(*) FILTER (WHERE profit_loss_pct > 0) as wins,
                   COUNT(*) FILTER (WHERE profit_loss_pct < 0) as losses,
                   COUNT(*) as total
            FROM (
                SELECT profit_loss_pct
                FROM algo_trades
                WHERE status = %s AND exit_date IS NOT NULL
                ORDER BY exit_date DESC LIMIT 30
            ) recent_trades
            """,
            (TradeStatus.CLOSED.value,)
        )
        row = self.cur.fetchone()
        if not row or row[2] is None or int(row[2]) < 10:
            return {'halted': False, 'reason': 'Insufficient closed trades (< 10)'}

        wins = int(row[0] or 0)
        total = int(row[2])
        win_rate = (wins / total * 100.0) if total > 0 else 0
        threshold = float(self.config.get('min_win_rate_pct', 40.0))
        return {
            'halted': win_rate < threshold,
            'reason': f'Win rate {win_rate:.1f}% < {threshold:.0f}%' if win_rate < threshold else f'Win rate {win_rate:.1f}%',
            'value': round(win_rate, 1),
            'threshold': threshold,
            'trades_sampled': total,
        }

    def _check_total_risk(self, current_date: Any) -> Dict[str, Any]:
        """Sum of (entry - stop) * qty across open positions vs portfolio value."""
        self.cur.execute(
            """
            SELECT COALESCE(SUM(GREATEST(0, (t.entry_price - COALESCE(p.current_stop_price, t.stop_loss_price)) * p.quantity)), 0)
            FROM algo_positions p
            JOIN algo_trades t ON t.trade_id = ANY(p.trade_ids_arr)
            WHERE p.status = %s
            """,
            (PositionStatus.OPEN.value,)
        )
        total_open_risk = float(self.cur.fetchone()[0] or 0)

        self.cur.execute(
            "SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1"
        )
        row = self.cur.fetchone()
        if not row or not row[0]:
            return {'halted': False, 'reason': 'No portfolio value'}
        portfolio = float(row[0])
        if portfolio <= 0:
            return {'halted': False, 'reason': 'Portfolio value <= 0'}

        risk_pct = total_open_risk / portfolio * 100.0
        threshold = float(self.config.get('max_total_risk_pct', 4.0))
        return {
            'halted': risk_pct >= threshold,
            'reason': f'Total open risk {risk_pct:.2f}% >= {threshold:.0f}%' if risk_pct >= threshold else f'Risk {risk_pct:.2f}%',
            'value': round(risk_pct, 2),
            'threshold': threshold,
        }

    def _check_vix_spike(self, current_date: Any) -> Dict[str, Any]:
        self.cur.execute(
            "SELECT vix_level FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
            (current_date,),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None:
            return {'halted': True, 'reason': 'VIX data missing — fail-closed to prevent trading during unknown volatility'}
        vix = float(row[0])
        threshold = float(self.config.get('vix_max_threshold', 35.0))
        return {
            'halted': vix > threshold,
            'reason': f'VIX {vix:.1f} > {threshold:.0f}' if vix > threshold else f'VIX {vix:.1f}',
            'value': vix,
            'threshold': threshold,
        }

    def _check_market_stage(self, current_date: Any) -> Dict[str, Any]:
        self.cur.execute(
            "SELECT market_stage, market_trend FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
            (current_date,),
        )
        row = self.cur.fetchone()
        if not row:
            return {'halted': True, 'reason': 'Market health data missing — fail-closed'}
        if row[0] is None:
            return {'halted': True, 'reason': 'Market stage NULL — fail-closed to prevent trading in unknown stage'}
        stage = int(row[0])
        trend = row[1] or 'unknown'
        # Stage 4 = halt new entries (full downtrend). Stage 3 = caution but allow.
        halted = stage == 4
        return {
            'halted': halted,
            'reason': f'Stage 4 downtrend (trend={trend})' if halted else f'Stage {stage} ({trend})',
            'value': stage,
        }

    def _check_weekly_loss(self, current_date: Any) -> Dict[str, Any]:
        """7-day return on portfolio."""
        week_ago = current_date - timedelta(days=7)
        self.cur.execute(
            """
            SELECT
                (SELECT total_portfolio_value FROM algo_portfolio_snapshots WHERE snapshot_date <= %s ORDER BY snapshot_date DESC LIMIT 1),
                (SELECT total_portfolio_value FROM algo_portfolio_snapshots WHERE snapshot_date <= %s ORDER BY snapshot_date DESC LIMIT 1)
            """,
            (current_date, week_ago),
        )
        row = self.cur.fetchone()
        if not row or not row[0] or not row[1]:
            return {'halted': False, 'reason': 'Insufficient history'}
        cur_val, week_ago_val = float(row[0]), float(row[1])
        weekly = ((cur_val - week_ago_val) / week_ago_val * 100.0) if week_ago_val > 0 else 0
        threshold = -float(self.config.get('max_weekly_loss_pct', 5.0))
        return {
            'halted': weekly <= threshold,
            'reason': f'Weekly {weekly:.2f}% <= {threshold:.1f}%' if weekly <= threshold else f'Weekly {weekly:+.2f}%',
            'value': round(weekly, 2),
            'threshold': threshold,
        }

    def _check_data_freshness(self, current_date: Any) -> Dict[str, Any]:
        """Block if our market data is too stale."""
        self.cur.execute(
            "SELECT MAX(date) FROM price_daily WHERE symbol = 'SPY'"
        )
        row = self.cur.fetchone()
        if not row or not row[0]:
            return {'halted': True, 'reason': 'No SPY data at all'}
        latest = row[0]
        days_stale = (current_date - latest).days
        threshold = int(self.config.get('max_data_staleness_days', 5))
        return {
            'halted': days_stale > threshold,
            'reason': f'Data {days_stale}d stale > {threshold}d max' if days_stale > threshold else f'{days_stale}d old',
            'value': days_stale,
            'threshold': threshold,
        }

    def _check_intraday_market_health(self, current_date: Any) -> Dict[str, Any]:
        """Intraday check: has SPY dropped >2% from yesterday's close (market crash)?

        Unlike EOD circuit breakers, this catches intraday crashes early.
        """
        try:
            self.cur.execute(
                """
                SELECT close FROM price_daily
                WHERE symbol = 'SPY'
                  AND date <= %s
                ORDER BY date DESC LIMIT 2
                """,
                (current_date,),
            )
            rows = self.cur.fetchall()
            if len(rows) < 2:
                return {'halted': False, 'reason': 'Insufficient price history'}

            latest = float(rows[0][0]) if rows[0][0] else None
            prior = float(rows[1][0]) if rows[1][0] else None

            if not latest or not prior or prior <= 0:
                return {'halted': False, 'reason': 'Invalid price data'}

            intraday_change = ((latest - prior) / prior * 100.0)

            # Halt if down >2% from yesterday's close (market crash level)
            if intraday_change <= -2.0:
                return {
                    'halted': True,
                    'reason': f'Market down {intraday_change:.2f}% (intraday crash)',
                    'market_change_pct': round(intraday_change, 2),
                }

            return {
                'halted': False,
                'reason': f'SPY {intraday_change:+.2f}%',
                'market_change_pct': round(intraday_change, 2),
            }
        except Exception as e:
            logger.debug(f'Intraday check failed: {e}')
            return {'halted': False, 'reason': 'Intraday check error'}

    def _check_sector_concentration(self, current_date: Any) -> Dict[str, Any]:
        """Halt if any sector has 2+ open positions and is down 12%+ in last 5 days."""
        try:
            # Get open positions with their sectors via company_profile
            self.cur.execute(
                """
                SELECT ap.symbol, COALESCE(cp.sector, 'Unknown') AS sector
                FROM algo_positions ap
                LEFT JOIN company_profile cp ON cp.ticker = ap.symbol
                WHERE ap.status = 'open'
                """
            )
            rows = self.cur.fetchall()
            if not rows:
                return {'halted': False, 'reason': 'No open positions'}

            # Count positions per sector
            sector_counts: Dict[str, int] = {}
            for _, sector in rows:
                sector_counts[sector] = sector_counts.get(sector, 0) + 1

            concentrated = {s: n for s, n in sector_counts.items() if n >= 2 and s != 'Unknown'}
            if not concentrated:
                return {'halted': False, 'reason': 'No concentrated sectors'}

            # For each concentrated sector, check 5-day cumulative return
            from datetime import timedelta
            five_days_ago = current_date - timedelta(days=7)  # 7 calendar days ≈ 5 trading days
            threshold = float(self.config.get('sector_drawdown_halt_pct', -12.0))

            for sector, count in concentrated.items():
                self.cur.execute(
                    """
                    SELECT return_pct, date FROM sector_performance
                    WHERE sector = %s AND date >= %s
                    ORDER BY date
                    """,
                    (sector, five_days_ago),
                )
                perf_rows = self.cur.fetchall()
                if not perf_rows:
                    continue

                # Compound returns: (1+r1) * (1+r2) * ... - 1
                cumulative = 1.0
                for r_pct, _ in perf_rows:
                    if r_pct is not None:
                        cumulative *= (1.0 + float(r_pct) / 100.0)
                cumulative_pct = (cumulative - 1.0) * 100.0

                if cumulative_pct <= threshold:
                    return {
                        'halted': True,
                        'reason': (f'Sector "{sector}" down {cumulative_pct:.1f}% in 5d '
                                   f'with {count} open positions (threshold: {threshold:.0f}%)'),
                        'sector': sector,
                        'positions_in_sector': count,
                        'sector_return_5d': round(cumulative_pct, 2),
                    }

            return {
                'halted': False,
                'reason': f'Concentrated sectors OK: {", ".join(f"{s}({n})" for s, n in concentrated.items())}',
            }
        except Exception as e:
            logger.warning(f'Sector concentration check failed: {e}')
            return {'halted': False, 'reason': f'Check error: {e}'}

    def _check_daily_profit_cap(self, current_date: Any) -> Dict[str, Any]:
        """Warn (don't halt) if daily P&L exceeds profit target; can skip new entries."""
        self.cur.execute(
            "SELECT daily_return_pct FROM algo_portfolio_snapshots WHERE snapshot_date = %s",
            (current_date,),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None:
            return {'halted': False, 'reason': 'No today snapshot yet'}
        daily = float(row[0])
        threshold = float(self.config.get('daily_profit_cap_pct', 2.0))
        # This check is a SOFT warning, not a halt — it's logged but doesn't block trading
        # Orchestrator uses this to skip NEW entries only, not to exit existing positions
        return {
            'halted': False,
            'reason': f'Daily profit {daily:+.2f}% vs cap {threshold:.1f}%',
            'value': round(daily, 2),
            'threshold': threshold,
            'exceed_profit_cap': daily >= threshold,
        }

    def _log_halt(self, results):
        try:
            self.cur.execute(
                """
                INSERT INTO algo_audit_log (action_type, action_date, details, actor, status, created_at)
                VALUES ('circuit_breaker_halt', CURRENT_TIMESTAMP, %s, 'circuit_breaker', 'halt', CURRENT_TIMESTAMP)
                """,
                (json.dumps(results),),
            )
            self.conn.commit()
        except Exception as e:
            logger.warning(f"Warning: Could not log circuit breaker halt to audit log: {e}")
        # Surface to notifications for UI
        try:
            from algo_notifications import notify
            notify(
                severity='critical',
                title='Trading Halted by Circuit Breaker',
                message='; '.join(results.get('halt_reasons', [])),
                details=results.get('checks'),
            )
        except Exception as e:
            logger.warning(f"Warning: Could not send circuit breaker notification: {e}")


if __name__ == "__main__":
    from algo_config import get_config
    cb = CircuitBreaker(get_config())
    result = cb.check_all()
    logger.info(f"\n{'HALTED' if result['halted'] else 'CLEAR'}\n")
    for name, state in result['checks'].items():
        flag = '[HALT]' if state.get('halted') else '[OK]  '
        logger.info(f"  {flag} {name:22s} : {state.get('reason', 'no detail')}")
    if result['halted']:
        logger.info(f"\nHALT REASONS:")
        for r in result['halt_reasons']:
            logger.info(f"  - {r}")
