"""
Compute circuit breaker metrics and store in circuit_breaker_status table.
Runs nightly after Phase 7 reconciliation (around 5:00 PM ET).

Metrics computed:
- CB1: Portfolio drawdown from peak
- CB2: Daily loss %
- CB3: Consecutive losses
- CB4: VIX level
- CB5: Weekly loss %
- CB6: Market stage
- CB7: Total open risk %
- CB8: SPY prior-day change %
- CB9: Win rate (last 30 trades)
"""

import psycopg2
import psycopg2.extras
from datetime import date, timedelta
import logging
import sys
import os
import json
from decimal import Decimal

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_connection
from utils.safe_data_conversion import safe_float, safe_int

logger = logging.getLogger(__name__)


def compute_circuit_breaker_metrics(cur, today: date = None):
    """Compute all circuit breaker metrics for today and store in database."""
    if today is None:
        today = date.today()

    try:
        metrics = {}

        # CB1: Portfolio drawdown from peak
        metrics['portfolio_drawdown_pct'] = _compute_drawdown(cur)

        # CB2: Daily loss %
        metrics['daily_loss_pct'] = _compute_daily_loss(cur, today)

        # CB3: Consecutive losses
        metrics['consecutive_losses'] = _compute_consecutive_losses(cur)

        # CB4: VIX level
        metrics['vix_level'] = _compute_vix_level(cur)

        # CB5: Weekly loss %
        metrics['weekly_loss_pct'] = _compute_weekly_loss(cur, today)

        # CB6: Market stage
        metrics['market_stage'] = _compute_market_stage(cur)

        # CB7: Total open risk %
        metrics['open_risk_pct'] = _compute_open_risk(cur)

        # CB8: SPY prior-day change %
        metrics['spy_prior_day_change_pct'] = _compute_spy_change(cur, today)

        # CB9: Win rate (last 30 trades)
        metrics['win_rate_last_30_pct'] = _compute_win_rate(cur)

        # Determine if any circuit breaker is triggered
        metrics['any_triggered'] = _check_any_triggered(metrics)
        metrics['triggered_count'] = _count_triggered(metrics)

        # Insert or update circuit_breaker_status
        _insert_circuit_breaker_status(cur, today, metrics)

        logger.info(f'Circuit breaker metrics computed for {today}: '
                   f'{metrics["triggered_count"]} triggered, '
                   f'any_triggered={metrics["any_triggered"]}')

        return metrics

    except Exception as e:
        logger.error(f'Failed to compute circuit breaker metrics: {e}', exc_info=True)
        raise


def _compute_drawdown(cur) -> float:
    """Calculate portfolio drawdown from peak."""
    try:
        cur.execute("""
            SELECT MAX(total_portfolio_value) AS peak,
                   (SELECT total_portfolio_value FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date DESC LIMIT 1) AS current
            FROM algo_portfolio_snapshots
        """)
        row = cur.fetchone()
        if not row:
            return 0.0
        peak = safe_float(row[0])
        current = safe_float(row[1])
        if peak <= 0:
            return 0.0
        dd = ((peak - current) / peak * 100)
        return round(dd, 2)
    except Exception as e:
        logger.warning(f'Failed to compute drawdown: {e}')
        return 0.0


def _compute_daily_loss(cur, today: date) -> float:
    """Calculate today's loss %."""
    try:
        cur.execute("""
            SELECT daily_return_pct FROM algo_portfolio_snapshots
            WHERE snapshot_date = %s
        """, (today,))
        row = cur.fetchone()
        if not row:
            return 0.0
        daily = safe_float(row[0])
        # Return absolute value of loss (if negative) or 0
        loss = abs(min(0, daily))
        return round(loss, 2)
    except Exception as e:
        logger.warning(f'Failed to compute daily loss: {e}')
        return 0.0


def _compute_consecutive_losses(cur) -> int:
    """Calculate consecutive losing trades from last 10 closed trades."""
    try:
        cur.execute("""
            SELECT profit_loss_pct FROM algo_trades
            WHERE status = 'closed' AND exit_date IS NOT NULL
            ORDER BY exit_date DESC, trade_id DESC
            LIMIT 10
        """)
        rows = cur.fetchall()
        streak = 0
        for row in rows:
            pnl = safe_float(row[0])
            if pnl < 0:
                streak += 1
            else:
                break
        return streak
    except Exception as e:
        logger.warning(f'Failed to compute consecutive losses: {e}')
        return 0


def _compute_vix_level(cur) -> float:
    """Get latest VIX level from market_health_daily."""
    try:
        cur.execute("""
            SELECT vix_level FROM market_health_daily
            ORDER BY date DESC LIMIT 1
        """)
        row = cur.fetchone()
        if not row or row[0] is None:
            return None
        vix = safe_float(row[0])
        return round(vix, 1)
    except Exception as e:
        logger.warning(f'Failed to compute VIX level: {e}')
        return None


def _compute_weekly_loss(cur, today: date) -> float:
    """Calculate 7-day portfolio loss %."""
    try:
        # Get portfolio value from 7 days ago
        cur.execute("""
            SELECT total_portfolio_value FROM algo_portfolio_snapshots
            WHERE snapshot_date >= %s
            ORDER BY snapshot_date ASC
            LIMIT 1
        """, (today - timedelta(days=7),))
        week_start = cur.fetchone()

        # Get latest portfolio value
        cur.execute("""
            SELECT total_portfolio_value FROM algo_portfolio_snapshots
            ORDER BY snapshot_date DESC LIMIT 1
        """)
        week_end = cur.fetchone()

        if not week_start or not week_end:
            return 0.0

        sv = safe_float(week_start[0])
        ev = safe_float(week_end[0])
        if sv <= 0:
            return 0.0

        weekly_ret = ((ev - sv) / sv * 100)
        # Return absolute value of loss (if negative) or 0
        loss = abs(min(0, weekly_ret))
        return round(loss, 2)
    except Exception as e:
        logger.warning(f'Failed to compute weekly loss: {e}')
        return 0.0


def _compute_market_stage(cur) -> int:
    """Get latest market stage from market_health_daily."""
    try:
        cur.execute("""
            SELECT market_stage FROM market_health_daily
            ORDER BY date DESC LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return 0
        stage = safe_int(row[0])
        return stage
    except Exception as e:
        logger.warning(f'Failed to compute market stage: {e}')
        return 0


def _compute_open_risk(cur) -> float:
    """Calculate total open risk % of portfolio."""
    try:
        # Calculate risk from open positions
        cur.execute("""
            SELECT COALESCE(SUM(GREATEST(0, (t.entry_price - COALESCE(p.current_stop_price, t.stop_loss_price)) * p.quantity)), 0)
            FROM algo_positions p
            JOIN algo_trades t ON t.trade_id = ANY(p.trade_ids_arr)
            WHERE LOWER(p.status) = 'open'
        """)
        risk_row = cur.fetchone()
        total_risk = safe_float(risk_row[0]) if risk_row else 0.0

        # Get portfolio value
        cur.execute("""
            SELECT total_portfolio_value FROM algo_portfolio_snapshots
            ORDER BY snapshot_date DESC LIMIT 1
        """)
        port_row = cur.fetchone()
        port_val = safe_float(port_row[0]) if port_row else 1.0

        if port_val <= 0:
            return 0.0

        risk_pct = (total_risk / port_val * 100)
        return round(risk_pct, 2)
    except Exception as e:
        logger.warning(f'Failed to compute open risk: {e}')
        return 0.0


def _compute_spy_change(cur, today: date) -> float:
    """Calculate SPY prior-day change %."""
    try:
        cur.execute("""
            SELECT close FROM price_daily
            WHERE symbol = 'SPY' AND date <= %s
            ORDER BY date DESC LIMIT 2
        """, (today,))
        prices = cur.fetchall()

        if len(prices) < 2:
            return 0.0

        latest = safe_float(prices[0][0])
        prior = safe_float(prices[1][0])

        if latest <= 0 or prior <= 0:
            return 0.0

        change = ((latest - prior) / prior * 100)
        return round(change, 2)
    except Exception as e:
        logger.warning(f'Failed to compute SPY change: {e}')
        return 0.0


def _compute_win_rate(cur) -> float:
    """Calculate win rate from last 30 closed trades."""
    try:
        cur.execute("""
            SELECT COUNT(*) FILTER (WHERE profit_loss_pct > 0) as wins,
                   COUNT(*) FILTER (WHERE profit_loss_pct < 0) as losses
            FROM (
                SELECT profit_loss_pct
                FROM algo_trades
                WHERE status = 'closed' AND exit_date IS NOT NULL
                ORDER BY exit_date DESC LIMIT 30
            ) recent_trades
        """)
        row = cur.fetchone()
        if not row:
            return 0.0

        wins = safe_int(row[0])
        losses = safe_int(row[1])
        decisive = wins + losses

        if decisive == 0:
            return 0.0

        win_rate = (wins / decisive * 100)
        return round(win_rate, 1)
    except Exception as e:
        logger.warning(f'Failed to compute win rate: {e}')
        return 0.0


def _check_any_triggered(metrics: dict) -> bool:
    """Check if any circuit breaker is triggered based on thresholds."""
    thresholds = {
        'portfolio_drawdown_pct': 20.0,
        'daily_loss_pct': 2.0,
        'consecutive_losses': 3,
        'vix_level': 35.0,
        'weekly_loss_pct': 5.0,
        'market_stage': 4,
        'open_risk_pct': 4.0,
        'spy_prior_day_change_pct': -2.0,
        'win_rate_last_30_pct': 40.0,  # Below 40% triggers
    }

    # Portfolio drawdown
    if metrics.get('portfolio_drawdown_pct', 0) >= thresholds['portfolio_drawdown_pct']:
        return True

    # Daily loss
    if metrics.get('daily_loss_pct', 0) >= thresholds['daily_loss_pct']:
        return True

    # Consecutive losses
    if metrics.get('consecutive_losses', 0) >= thresholds['consecutive_losses']:
        return True

    # VIX
    vix = metrics.get('vix_level')
    if vix is not None and vix >= thresholds['vix_level']:
        return True

    # Weekly loss
    if metrics.get('weekly_loss_pct', 0) >= thresholds['weekly_loss_pct']:
        return True

    # Market stage
    if metrics.get('market_stage', 0) == thresholds['market_stage']:
        return True

    # Open risk
    if metrics.get('open_risk_pct', 0) >= thresholds['open_risk_pct']:
        return True

    # SPY change
    spy_change = metrics.get('spy_prior_day_change_pct', 0)
    if spy_change <= thresholds['spy_prior_day_change_pct']:
        return True

    # Win rate (below 40%)
    wr = metrics.get('win_rate_last_30_pct', 0)
    if wr < thresholds['win_rate_last_30_pct'] and wr > 0:
        return True

    return False


def _count_triggered(metrics: dict) -> int:
    """Count how many circuit breakers are triggered."""
    count = 0
    thresholds = {
        'portfolio_drawdown_pct': 20.0,
        'daily_loss_pct': 2.0,
        'consecutive_losses': 3,
        'vix_level': 35.0,
        'weekly_loss_pct': 5.0,
        'market_stage': 4,
        'open_risk_pct': 4.0,
        'spy_prior_day_change_pct': -2.0,
        'win_rate_last_30_pct': 40.0,
    }

    if metrics.get('portfolio_drawdown_pct', 0) >= thresholds['portfolio_drawdown_pct']:
        count += 1
    if metrics.get('daily_loss_pct', 0) >= thresholds['daily_loss_pct']:
        count += 1
    if metrics.get('consecutive_losses', 0) >= thresholds['consecutive_losses']:
        count += 1
    vix = metrics.get('vix_level')
    if vix is not None and vix >= thresholds['vix_level']:
        count += 1
    if metrics.get('weekly_loss_pct', 0) >= thresholds['weekly_loss_pct']:
        count += 1
    if metrics.get('market_stage', 0) == thresholds['market_stage']:
        count += 1
    if metrics.get('open_risk_pct', 0) >= thresholds['open_risk_pct']:
        count += 1
    spy_change = metrics.get('spy_prior_day_change_pct', 0)
    if spy_change <= thresholds['spy_prior_day_change_pct']:
        count += 1
    wr = metrics.get('win_rate_last_30_pct', 0)
    if wr < thresholds['win_rate_last_30_pct'] and wr > 0:
        count += 1

    return count


def _insert_circuit_breaker_status(cur, today: date, metrics: dict):
    """Insert or update circuit breaker status in database."""
    try:
        cur.execute("""
            INSERT INTO circuit_breaker_status (
                check_date, portfolio_drawdown_pct, daily_loss_pct, weekly_loss_pct,
                consecutive_losses, open_risk_pct, vix_level, market_stage,
                spy_prior_day_change_pct, win_rate_last_30_pct,
                triggered_count, any_triggered, computed_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (check_date) DO UPDATE SET
                portfolio_drawdown_pct = EXCLUDED.portfolio_drawdown_pct,
                daily_loss_pct = EXCLUDED.daily_loss_pct,
                weekly_loss_pct = EXCLUDED.weekly_loss_pct,
                consecutive_losses = EXCLUDED.consecutive_losses,
                open_risk_pct = EXCLUDED.open_risk_pct,
                vix_level = EXCLUDED.vix_level,
                market_stage = EXCLUDED.market_stage,
                spy_prior_day_change_pct = EXCLUDED.spy_prior_day_change_pct,
                win_rate_last_30_pct = EXCLUDED.win_rate_last_30_pct,
                triggered_count = EXCLUDED.triggered_count,
                any_triggered = EXCLUDED.any_triggered,
                updated_at = NOW()
        """, (
            today,
            metrics.get('portfolio_drawdown_pct'),
            metrics.get('daily_loss_pct'),
            metrics.get('weekly_loss_pct'),
            metrics.get('consecutive_losses'),
            metrics.get('open_risk_pct'),
            metrics.get('vix_level'),
            metrics.get('market_stage'),
            metrics.get('spy_prior_day_change_pct'),
            metrics.get('win_rate_last_30_pct'),
            metrics.get('triggered_count'),
            metrics.get('any_triggered'),
        ))
    except Exception as e:
        logger.error(f'Failed to insert circuit breaker status: {e}', exc_info=True)
        raise


def main():
    """Main entry point for the loader."""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        compute_circuit_breaker_metrics(cur)

        conn.commit()
        logger.info('Circuit breaker metrics loader completed successfully')
    except Exception as e:
        logger.error(f'Circuit breaker metrics loader failed: {e}', exc_info=True)
        if conn:
            conn.rollback()
        raise
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    main()
