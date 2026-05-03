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

import os
import psycopg2
import json
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date as _date

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


class CircuitBreaker:
    """Pre-trade kill-switch checks."""

    def __init__(self, config):
        self.config = config
        self.conn = None
        self.cur = None

    def connect(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def check_all(self, current_date=None):
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
                ('daily_loss', self._check_daily_loss),
                ('consecutive_losses', self._check_consecutive_losses),
                ('total_risk', self._check_total_risk),
                ('vix_spike', self._check_vix_spike),
                ('market_stage', self._check_market_stage),
                ('weekly_loss', self._check_weekly_loss),
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
        finally:
            self.disconnect()

    # ---------- Individual checks ----------

    def _check_drawdown(self, current_date):
        self.cur.execute(
            """
            SELECT MAX(total_portfolio_value),
                   (SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1)
            FROM algo_portfolio_snapshots
            """
        )
        row = self.cur.fetchone()
        if not row or not row[0] or not row[1]:
            return {'halted': False, 'reason': 'No portfolio history'}
        peak = float(row[0])
        cur_val = float(row[1])
        dd = ((peak - cur_val) / peak * 100.0) if peak > 0 else 0.0
        threshold = float(self.config.get('halt_drawdown_pct', 20.0))
        return {
            'halted': dd >= threshold,
            'reason': f'Drawdown {dd:.2f}% >= {threshold:.0f}%' if dd >= threshold else f'Drawdown {dd:.2f}%',
            'value': round(dd, 2),
            'threshold': threshold,
        }

    def _check_daily_loss(self, current_date):
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

    def _check_consecutive_losses(self, current_date):
        self.cur.execute(
            """
            SELECT profit_loss_pct, exit_date FROM algo_trades
            WHERE status = 'closed' AND exit_date IS NOT NULL
            ORDER BY exit_date DESC, id DESC
            LIMIT 10
            """
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

    def _check_total_risk(self, current_date):
        """Sum of (entry - stop) * qty across open positions vs portfolio value."""
        self.cur.execute(
            """
            SELECT COALESCE(SUM(GREATEST(0, (t.entry_price - COALESCE(p.current_stop_price, t.stop_loss_price)) * p.quantity)), 0)
            FROM algo_positions p
            JOIN algo_trades t ON p.trade_ids LIKE '%%' || t.trade_id || '%%'
            WHERE p.status = 'open'
            """
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

    def _check_vix_spike(self, current_date):
        self.cur.execute(
            "SELECT vix_level FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
            (current_date,),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None:
            return {'halted': False, 'reason': 'No VIX'}
        vix = float(row[0])
        threshold = float(self.config.get('vix_max_threshold', 35.0))
        return {
            'halted': vix > threshold,
            'reason': f'VIX {vix:.1f} > {threshold:.0f}' if vix > threshold else f'VIX {vix:.1f}',
            'value': vix,
            'threshold': threshold,
        }

    def _check_market_stage(self, current_date):
        self.cur.execute(
            "SELECT market_stage, market_trend FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
            (current_date,),
        )
        row = self.cur.fetchone()
        if not row:
            return {'halted': False, 'reason': 'No market health'}
        stage = int(row[0]) if row[0] is not None else 0
        trend = row[1] or 'unknown'
        # Stage 4 = halt new entries (full downtrend). Stage 3 = caution but allow.
        halted = stage == 4
        return {
            'halted': halted,
            'reason': f'Stage 4 downtrend (trend={trend})' if halted else f'Stage {stage} ({trend})',
            'value': stage,
        }

    def _check_weekly_loss(self, current_date):
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

    def _check_data_freshness(self, current_date):
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
        except Exception:
            pass
        # Surface to notifications for UI
        try:
            from algo_notifications import notify
            notify(
                kind='circuit_breaker',
                severity='critical',
                title='Trading Halted by Circuit Breaker',
                message='; '.join(results.get('halt_reasons', [])),
                details=results.get('checks'),
            )
        except Exception:
            pass


if __name__ == "__main__":
    from algo_config import get_config
    cb = CircuitBreaker(get_config())
    result = cb.check_all()
    print(f"\n{'HALTED' if result['halted'] else 'CLEAR'}\n")
    for name, state in result['checks'].items():
        flag = '[HALT]' if state.get('halted') else '[OK]  '
        print(f"  {flag} {name:22s} : {state.get('reason', 'no detail')}")
    if result['halted']:
        print(f"\nHALT REASONS:")
        for r in result['halt_reasons']:
            print(f"  - {r}")
