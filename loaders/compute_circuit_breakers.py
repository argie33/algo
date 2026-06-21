"""
Compute circuit breaker metrics and store in circuit_breaker_status table.
Runs daily at 4:30 PM ET (before Phase 7 reconciliation) via EventBridge scheduled task.

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

import logging
from datetime import date, timedelta
from datetime import datetime as dt
from typing import Any, Optional

import psycopg2
import psycopg2.extras

# Add parent directory to path for imports
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ


logger = logging.getLogger(__name__)


def compute_circuit_breaker_metrics(cur, today: date | None = None):
    """Compute all circuit breaker metrics for today and store in database."""
    if today is None:
        # Use ET date, not UTC (AWS containers run in UTC but trading is ET-based)
        today = dt.now(EASTERN_TZ).date()

    logger.info(f"Computing circuit breaker metrics for {today}")

    try:
        metrics: dict[str, Any] = {}

        # CB1: Portfolio drawdown from peak
        metrics["portfolio_drawdown_pct"] = _compute_drawdown(cur)

        # CB2: Daily loss %
        metrics["daily_loss_pct"] = _compute_daily_loss(cur, today)

        # CB3: Consecutive losses
        metrics["consecutive_losses"] = _compute_consecutive_losses(cur)

        # CB4: VIX level
        metrics["vix_level"] = _compute_vix_level(cur)

        # CB5: Weekly loss %
        metrics["weekly_loss_pct"] = _compute_weekly_loss(cur, today)

        # CB6: Market stage
        metrics["market_stage"] = _compute_market_stage(cur)

        # CB7: Total open risk %
        metrics["open_risk_pct"] = _compute_open_risk(cur)

        # CB8: SPY prior-day change %
        metrics["spy_prior_day_change_pct"] = _compute_spy_change(cur, today)

        # CB9: Win rate (last 30 trades)
        metrics["win_rate_last_30_pct"] = _compute_win_rate(cur)

        # Determine if any circuit breaker is triggered
        metrics["any_triggered"] = _check_any_triggered(metrics)
        metrics["triggered_count"] = _count_triggered(metrics)

        # Insert or update circuit_breaker_status
        _insert_circuit_breaker_status(cur, today, metrics)

        logger.info(
            f"Circuit breaker metrics computed for {today}: "
            f'{metrics["triggered_count"]} triggered, '
            f'any_triggered={metrics["any_triggered"]}'
        )

        return metrics

    except Exception as e:
        logger.error(f"Failed to compute circuit breaker metrics: {e}", exc_info=True)
        raise


def _compute_drawdown(cur) -> float:
    """Calculate portfolio drawdown from peak."""
    cur.execute("""
        SELECT MAX(total_portfolio_value) AS peak,
               (SELECT total_portfolio_value FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1) AS current
        FROM algo_portfolio_snapshots
    """)
    row = cur.fetchone()
    if not row or row[0] is None or row[1] is None:
        raise ValueError("Portfolio snapshot data unavailable for drawdown calculation")
    peak = float(float(row[0]))
    current = float(float(row[1]))
    if peak <= 0:
        raise ValueError(f"Invalid peak portfolio value: {peak}")
    dd = (peak - current) / peak * 100
    return round(dd, 2)


def _compute_daily_loss(cur, today: date) -> float:
    """Calculate today's loss %."""
    cur.execute(
        """
        SELECT daily_return_pct FROM algo_portfolio_snapshots
        WHERE snapshot_date = %s
    """,
        (today,),
    )
    row = cur.fetchone()
    if not row or row[0] is None:
        raise ValueError(f"Portfolio snapshot unavailable for {today}")
    daily = float(float(row[0]))
    loss = abs(min(0, daily))
    return round(loss, 2)


def _compute_consecutive_losses(cur) -> int:
    """Calculate consecutive losing trades from last 10 closed trades."""
    cur.execute("""
        SELECT profit_loss_pct FROM algo_trades
        WHERE status = 'closed' AND exit_date IS NOT NULL
        ORDER BY exit_date DESC, trade_id DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    if not rows:
        raise ValueError("No closed trades available for consecutive loss calculation")
    streak = 0
    for row in rows:
        pnl = float(float(row[0]))
        if pnl < 0:
            streak += 1
        else:
            break
    return streak


def _compute_vix_level(cur) -> float | None:
    """Get latest VIX level from market_health_daily. Raises if not available."""
    cur.execute("""
        SELECT vix_level FROM market_health_daily
        WHERE vix_level IS NOT NULL
        ORDER BY date DESC LIMIT 1
    """)
    row = cur.fetchone()
    if not row or row[0] is None:
        raise ValueError("VIX level not available in market_health_daily - circuit breaker CB4 metric cannot be computed")
    vix = float(float(row[0]))
    return round(vix, 1)


def _compute_weekly_loss(cur, today: date) -> float:
    """Calculate 7-day portfolio loss %."""
    cur.execute(
        """
        SELECT total_portfolio_value FROM algo_portfolio_snapshots
        WHERE snapshot_date >= %s
        ORDER BY snapshot_date ASC
        LIMIT 1
    """,
        (today - timedelta(days=7),),
    )
    week_start = cur.fetchone()

    cur.execute("""
        SELECT total_portfolio_value FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC LIMIT 1
    """)
    week_end = cur.fetchone()

    if not week_start or not week_end or week_start[0] is None or week_end[0] is None:
        raise ValueError("Insufficient portfolio snapshot data for 7-day loss calculation")

    sv = float(float(week_start[0]))
    ev = float(float(week_end[0]))
    if sv <= 0:
        raise ValueError(f"Invalid portfolio value for 7-day calculation: {sv}")

    weekly_ret = (ev - sv) / sv * 100
    loss = abs(min(0, weekly_ret))
    return round(loss, 2)


def _compute_market_stage(cur) -> int | None:
    """Get latest market stage from market_health_daily. Returns None if not available (fail-closed)."""
    cur.execute("""
        SELECT market_stage FROM market_health_daily
        WHERE market_stage IS NOT NULL
        ORDER BY date DESC LIMIT 1
    """)
    row = cur.fetchone()
    if not row or row[0] is None:
        logger.warning("Market stage not available in market_health_daily — circuit breaker CB6 will fail-closed")
        return None
    stage = int(int(row[0]))
    return stage


def _compute_open_risk(cur) -> float:
    """Calculate total open risk % of portfolio."""
    cur.execute("""
        SELECT COALESCE(SUM(GREATEST(0, (t.entry_price - COALESCE(p.current_stop_price, t.stop_loss_price)) * p.quantity)), 0)
        FROM algo_positions p
        JOIN algo_trades t ON t.trade_id = ANY(p.trade_ids_arr)
        WHERE LOWER(p.status) = 'open'
    """)
    risk_row = cur.fetchone()
    if not risk_row:
        raise ValueError("Cannot calculate open risk: positions/trades query failed")
    total_risk = float(float(risk_row[0]))

    cur.execute("""
        SELECT total_portfolio_value FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC LIMIT 1
    """)
    port_row = cur.fetchone()
    if not port_row or port_row[0] is None:
        raise ValueError("Portfolio value unavailable for risk calculation")
    port_val = float(float(port_row[0]))

    if port_val <= 0:
        raise ValueError(f"Invalid portfolio value for risk calculation: {port_val}")

    risk_pct = total_risk / port_val * 100
    return round(risk_pct, 2)


def _compute_spy_change(cur, today: date) -> float:
    """Calculate SPY prior-day change %."""
    cur.execute(
        """
        SELECT close FROM price_daily
        WHERE symbol = 'SPY' AND date <= %s
        ORDER BY date DESC LIMIT 2
    """,
        (today,),
    )
    prices = cur.fetchall()

    if len(prices) < 2:
        raise ValueError(f"Insufficient SPY price data for {today}: got {len(prices)} prices, need 2")

    latest = float(float(prices[0][0]))
    prior = float(float(prices[1][0]))

    if latest <= 0 or prior <= 0:
        raise ValueError(f"Invalid SPY prices for {today}: latest={latest}, prior={prior}")

    change = (latest - prior) / prior * 100
    return round(change, 2)


def _compute_win_rate(cur) -> float:
    """Calculate win rate from last 30 closed trades."""
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
        raise ValueError("Win rate query failed")

    wins = int(int(row[0]))
    losses = int(int(row[1]))
    decisive = wins + losses

    if decisive == 0:
        raise ValueError("No closed trades available for win rate calculation")

    win_rate = wins / decisive * 100
    return round(win_rate, 1)


def _check_any_triggered(metrics: dict) -> bool:
    """Check if any circuit breaker is triggered based on thresholds.

    If a required metric is missing or None, fail closed (return True).
    This ensures data quality issues don't silently pass safety checks.
    """
    thresholds = {
        "portfolio_drawdown_pct": 20.0,
        "daily_loss_pct": 2.0,
        "consecutive_losses": 3,
        "vix_level": 35.0,
        "weekly_loss_pct": 5.0,
        "market_stage": 4,
        "open_risk_pct": 4.0,
        "spy_prior_day_change_pct": -2.0,
        "win_rate_last_30_pct": 40.0,  # Below 40% triggers
    }

    # Portfolio drawdown - fail closed if unavailable
    dd = metrics.get("portfolio_drawdown_pct")
    if dd is None:
        logger.error("portfolio_drawdown_pct missing: failing closed (CB1 triggered)")
        return True
    if dd >= thresholds["portfolio_drawdown_pct"]:
        return True

    # Daily loss - fail closed if unavailable
    dl = metrics.get("daily_loss_pct")
    if dl is None:
        logger.error("daily_loss_pct missing: failing closed (CB2 triggered)")
        return True
    if dl >= thresholds["daily_loss_pct"]:
        return True

    # Consecutive losses - fail closed if unavailable
    cl = metrics.get("consecutive_losses")
    if cl is None:
        logger.error("consecutive_losses missing: failing closed (CB3 triggered)")
        return True
    if cl >= thresholds["consecutive_losses"]:
        return True

    # VIX - fail closed if unavailable
    vix = metrics.get("vix_level")
    if vix is None:
        logger.error("vix_level missing: failing closed (CB4 triggered)")
        return True
    if vix >= thresholds["vix_level"]:
        return True

    # Weekly loss - fail closed if unavailable
    wl = metrics.get("weekly_loss_pct")
    if wl is None:
        logger.error("weekly_loss_pct missing: failing closed (CB5 triggered)")
        return True
    if wl >= thresholds["weekly_loss_pct"]:
        return True

    # Market stage - fail closed if unavailable
    ms = metrics.get("market_stage")
    if ms is None:
        logger.error("market_stage missing: failing closed (CB6 triggered)")
        return True
    if ms == thresholds["market_stage"]:
        return True

    # Open risk - fail closed if unavailable
    or_ = metrics.get("open_risk_pct")
    if or_ is None:
        logger.error("open_risk_pct missing: failing closed (CB7 triggered)")
        return True
    if or_ >= thresholds["open_risk_pct"]:
        return True

    # SPY change - fail closed if unavailable
    spy_change = metrics.get("spy_prior_day_change_pct")
    if spy_change is None:
        logger.error("spy_prior_day_change_pct missing: failing closed (CB8 triggered)")
        return True
    if spy_change <= thresholds["spy_prior_day_change_pct"]:
        return True

    # Win rate - fail closed if unavailable
    wr = metrics.get("win_rate_last_30_pct")
    if wr is None:
        logger.error("win_rate_last_30_pct missing: failing closed (CB9 triggered)")
        return True
    if wr < thresholds["win_rate_last_30_pct"] and wr > 0:
        return True

    return False


def _count_triggered(metrics: dict) -> int:
    """Count how many circuit breakers are triggered.

    If a required metric is missing or None, fail closed (count as triggered).
    This ensures data quality issues don't silently reduce triggered count.
    """
    count = 0
    thresholds = {
        "portfolio_drawdown_pct": 20.0,
        "daily_loss_pct": 2.0,
        "consecutive_losses": 3,
        "vix_level": 35.0,
        "weekly_loss_pct": 5.0,
        "market_stage": 4,
        "open_risk_pct": 4.0,
        "spy_prior_day_change_pct": -2.0,
        "win_rate_last_30_pct": 40.0,
    }

    dd = metrics.get("portfolio_drawdown_pct")
    if dd is None:
        count += 1
    elif dd >= thresholds["portfolio_drawdown_pct"]:
        count += 1

    dl = metrics.get("daily_loss_pct")
    if dl is None:
        count += 1
    elif dl >= thresholds["daily_loss_pct"]:
        count += 1

    cl = metrics.get("consecutive_losses")
    if cl is None:
        count += 1
    elif cl >= thresholds["consecutive_losses"]:
        count += 1

    vix = metrics.get("vix_level")
    if vix is None:
        count += 1
    elif vix >= thresholds["vix_level"]:
        count += 1

    wl = metrics.get("weekly_loss_pct")
    if wl is None:
        count += 1
    elif wl >= thresholds["weekly_loss_pct"]:
        count += 1

    ms = metrics.get("market_stage")
    if ms is None:
        count += 1
    elif ms == thresholds["market_stage"]:
        count += 1

    or_ = metrics.get("open_risk_pct")
    if or_ is None:
        count += 1
    elif or_ >= thresholds["open_risk_pct"]:
        count += 1

    spy_change = metrics.get("spy_prior_day_change_pct")
    if spy_change is None:
        count += 1
    elif spy_change <= thresholds["spy_prior_day_change_pct"]:
        count += 1

    wr = metrics.get("win_rate_last_30_pct")
    if wr is None:
        count += 1
    elif wr < thresholds["win_rate_last_30_pct"] and wr > 0:
        count += 1

    return count


def _insert_circuit_breaker_status(cur, today: date, metrics: dict):
    """Insert or update circuit breaker status in database."""
    try:
        cur.execute(
            """
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
        """,
            (
                today,
                metrics.get("portfolio_drawdown_pct"),
                metrics.get("daily_loss_pct"),
                metrics.get("weekly_loss_pct"),
                metrics.get("consecutive_losses"),
                metrics.get("open_risk_pct"),
                metrics.get("vix_level"),
                metrics.get("market_stage"),
                metrics.get("spy_prior_day_change_pct"),
                metrics.get("win_rate_last_30_pct"),
                metrics.get("triggered_count"),
                metrics.get("any_triggered"),
            ),
        )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Failed to insert circuit breaker status: {e}", exc_info=True)
        raise


def main():
    """Main entry point for the loader."""
    try:
        # Use ET date, not UTC (AWS containers run in UTC but trading is ET-based)
        run_date = dt.now(EASTERN_TZ).date()
        with DatabaseContext(
            "write", cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            compute_circuit_breaker_metrics(cur, today=run_date)
            logger.info(
                f"Circuit breaker metrics loader completed successfully for {run_date}"
            )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Circuit breaker metrics loader failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    main()
