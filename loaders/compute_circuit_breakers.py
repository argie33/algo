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
from collections.abc import Callable
from datetime import date, timedelta
from datetime import datetime as dt
from typing import Any

import psycopg2
import psycopg2.extras

# Add parent directory to path for imports
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)


class CircuitBreakerDef:
    """Defines a circuit breaker check: metric name, threshold, operator, and logging context."""

    def __init__(
        self,
        name: str,
        metric_key: str,
        threshold: Any,
        operator: Callable[[Any, Any], bool],
        fail_closed: bool = True,
    ):
        self.name = name
        self.metric_key = metric_key
        self.threshold = threshold
        self.operator = operator
        self.fail_closed = fail_closed

    def is_triggered(self, metrics: dict[str, Any]) -> bool:
        """Check if this circuit breaker is triggered.

        CRITICAL: Fails immediately if metric is missing or None.
        No fallback — incomplete risk assessment must fail closed.
        """
        if self.metric_key not in metrics:
            msg = (
                f"[CIRCUIT_BREAKER_CRITICAL] {self.metric_key} missing from metrics dict for {self.name}. "
                f"Cannot evaluate circuit breaker without required metric. "
                f"Failing closed to prevent trading without complete risk assessment."
            )
            logger.critical(msg)
            raise ValueError(msg)

        value = metrics[self.metric_key]
        if value is None:
            msg = (
                f"[CIRCUIT_BREAKER_CRITICAL] {self.metric_key} is None for {self.name}. "
                f"Cannot evaluate circuit breaker with null value. "
                f"Failing closed to prevent trading without complete risk assessment."
            )
            logger.critical(msg)
            raise ValueError(msg)
        return self.operator(value, self.threshold)


CIRCUIT_BREAKERS = [
    CircuitBreakerDef("CB1", "portfolio_drawdown_pct", 20.0, lambda v, t: v >= t),
    CircuitBreakerDef("CB2", "daily_loss_pct", 2.0, lambda v, t: v >= t),
    CircuitBreakerDef("CB3", "consecutive_losses", 3, lambda v, t: v >= t),
    CircuitBreakerDef("CB4", "vix_level", 35.0, lambda v, t: v >= t),
    CircuitBreakerDef("CB5", "weekly_loss_pct", 5.0, lambda v, t: v >= t),
    CircuitBreakerDef("CB6", "market_stage", 4, lambda v, t: v == t),
    CircuitBreakerDef("CB7", "open_risk_pct", 4.0, lambda v, t: v >= t),
    CircuitBreakerDef("CB8", "spy_prior_day_change_pct", -2.0, lambda v, t: v <= t),
    CircuitBreakerDef("CB9", "win_rate_last_30_pct", 40.0, lambda v, t: v < t and v > 0),
]


def compute_circuit_breaker_metrics(cur: Any, today: date | None = None) -> dict[str, Any]:
    """Compute all circuit breaker metrics for today and store in database.

    Args:
        cur: Database cursor
        today: Specific date to compute metrics for (defaults to current ET date if None)
    """
    if today is None:
        # Use ET date, not UTC (AWS containers run in UTC but trading is ET-based)
        today = dt.now(EASTERN_TZ).date()
    elif not isinstance(today, date):
        raise TypeError(f"today must be a date or None, got {type(today).__name__}: {today!r}")

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

        # Validate all required metrics are present and not None before DB insert
        required_keys = [
            "portfolio_drawdown_pct",
            "daily_loss_pct",
            "weekly_loss_pct",
            "consecutive_losses",
            "open_risk_pct",
            "vix_level",
            "market_stage",
            "spy_prior_day_change_pct",
            "win_rate_last_30_pct",
            "triggered_count",
            "any_triggered",
        ]
        missing_or_none = [k for k in required_keys if k not in metrics or metrics[k] is None]
        if missing_or_none:
            raise ValueError(
                f"Circuit breaker metrics incomplete before DB insert: {missing_or_none}. "
                f"This prevents silent data corruption (NULL insertion). Metrics available: {list(metrics.keys())}"
            )

        # Insert or update circuit_breaker_status
        _insert_circuit_breaker_status(cur, today, metrics)

        logger.info(
            f"Circuit breaker metrics computed for {today}: "
            f"{metrics['triggered_count']} triggered, "
            f"any_triggered={metrics['any_triggered']}"
        )

        return metrics

    except Exception as e:
        logger.error(f"Failed to compute circuit breaker metrics: {e}", exc_info=True)
        raise


def _compute_drawdown(cur: Any) -> float:
    cur.execute("""
        SELECT MAX(total_portfolio_value) AS peak,
               (SELECT total_portfolio_value FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1) AS current
        FROM algo_portfolio_snapshots
    """)
    row = cur.fetchone()
    if not row or row["peak"] is None or row["current"] is None:
        logger.warning("[CIRCUIT_BREAKER] Portfolio snapshot data unavailable for drawdown calculation (CB1)")
        raise ValueError("Portfolio snapshot data unavailable for drawdown calculation")
    peak = float(row["peak"])
    current = float(row["current"])
    if peak <= 0:
        raise ValueError(f"Invalid peak portfolio value: {peak}")
    dd = (peak - current) / peak * 100
    return round(dd, 2)


def _compute_daily_loss(cur: Any, today: date) -> float:
    cur.execute(
        """
        SELECT daily_return_pct FROM algo_portfolio_snapshots
        WHERE snapshot_date <= %s
        ORDER BY snapshot_date DESC
        LIMIT 1
    """,
        (today,),
    )
    row = cur.fetchone()
    if not row or row["daily_return_pct"] is None:
        logger.warning(f"[CIRCUIT_BREAKER] Portfolio snapshot unavailable on or before {today} (CB2)")
        raise ValueError(f"Portfolio snapshot unavailable on or before {today}")
    daily = float(row["daily_return_pct"])
    loss = abs(min(0, daily))
    return round(loss, 2)


def _compute_consecutive_losses(cur: Any) -> int:
    cur.execute("""
        SELECT profit_loss_pct FROM algo_trades
        WHERE status = 'closed' AND exit_date IS NOT NULL
        ORDER BY exit_date DESC, trade_id DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    if not rows:
        logger.info("[CIRCUIT_BREAKER] No closed trades available for consecutive loss calculation (CB3) - new account, returning 0")
        return 0
    streak = 0
    for row in rows:
        pnl_value = row["profit_loss_pct"]
        if pnl_value is None:
            # Skip rows with NULL profit_loss_pct (trades not yet fully reconciled)
            continue
        pnl = float(pnl_value)
        if pnl < 0:
            streak += 1
        else:
            break
    return streak


def _compute_vix_level(cur: Any) -> float | None:
    cur.execute("""
        SELECT vix_level FROM market_health_daily
        WHERE vix_level IS NOT NULL
        ORDER BY date DESC LIMIT 1
    """)
    row = cur.fetchone()
    if not row or row["vix_level"] is None:
        logger.warning("[CIRCUIT_BREAKER] VIX level not available in market_health_daily (CB4)")
        raise ValueError(
            "VIX level not available in market_health_daily - circuit breaker CB4 metric cannot be computed"
        )
    vix = float(row["vix_level"])
    return round(vix, 1)


def _compute_weekly_loss(cur: Any, today: date) -> float:
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

    if (
        not week_start
        or not week_end
        or week_start["total_portfolio_value"] is None
        or week_end["total_portfolio_value"] is None
    ):
        raise ValueError("Insufficient portfolio snapshot data for 7-day loss calculation")

    sv = float(week_start["total_portfolio_value"])
    ev = float(week_end["total_portfolio_value"])
    if sv <= 0:
        raise ValueError(f"Invalid portfolio value for 7-day calculation: {sv}")

    weekly_ret = (ev - sv) / sv * 100
    loss = abs(min(0, weekly_ret))
    return round(loss, 2)


def _compute_market_stage(cur: Any) -> int:
    cur.execute("""
        SELECT market_stage FROM market_health_daily
        WHERE market_stage IS NOT NULL
        ORDER BY date DESC LIMIT 1
    """)
    row = cur.fetchone()
    if not row or row["market_stage"] is None:
        logger.warning("[CIRCUIT_BREAKER] Market stage not available in market_health_daily (CB6)")
        raise ValueError(
            "Market stage not available in market_health_daily — "
            "Phase X market exposure detection must populate market_health_daily before circuit breaker metrics. "
            "CB6 (market stage break) cannot be computed without this critical market regime data."
        )
    stage = int(row["market_stage"])
    return stage


def _compute_open_risk(cur: Any) -> float:
    """Calculate total open risk % of portfolio.

    CRITICAL: Requires all open positions to have valid stop_loss_price set.
    No fallback to entry_price (that would show 0% risk when stops are missing).
    Fails fast if any position lacks a stop — this is a data integrity error.
    """
    # First, validate that all open positions have stop prices set (NO FALLBACK)
    # CRITICAL: Each position MUST have p.current_stop_price set. No fallback to trade stop_loss_price.
    # This ensures risk calculations use the ACTUAL current stop, not historical entry stop.
    cur.execute("""
        SELECT COUNT(*) as missing_current_stops
        FROM algo_positions
        WHERE LOWER(status) = 'open'
        AND current_stop_price IS NULL
    """)
    check_row = cur.fetchone()
    if check_row and check_row["missing_current_stops"] and check_row["missing_current_stops"] > 0:
        raise ValueError(
            f"CRITICAL: {check_row['missing_current_stops']} open position(s) have NULL current_stop_price. "
            "Cannot calculate portfolio risk without valid CURRENT stops. "
            "All open positions MUST have current_stop_price updated before risk assessment. "
            "NO FALLBACK to historical entry stop — current risk requires current stops."
        )

    cur.execute("""
        SELECT SUM(GREATEST(0, (p.entry_price - p.current_stop_price) * p.quantity))
               AS total_risk
        FROM algo_positions p
        WHERE LOWER(p.status) = 'open'
    """)
    risk_row = cur.fetchone()
    if not risk_row:
        raise ValueError("Cannot calculate open risk: positions/trades query failed")
    total_risk_val = risk_row["total_risk"]

    # Explicit check: NULL total_risk could mean:
    # 1. No open positions (valid: 0% risk)
    # 2. Query failed (invalid: must not silently assume 0%)
    # Distinguish by checking for open positions explicitly
    cur.execute("SELECT COUNT(*) as cnt FROM algo_positions WHERE LOWER(status) = 'open'")
    result = cur.fetchone()
    if result is None:
        raise ValueError("[RISK_CALCULATION_CRITICAL] Query to count open positions returned no result")
    pos_count = result["cnt"]

    if total_risk_val is None:
        if pos_count == 0:
            total_risk = 0.0
        else:
            raise ValueError(
                f"[RISK_CALCULATION_CRITICAL] Open risk calculation returned NULL "
                f"but {pos_count} open position(s) exist. Risk calculation failed. "
                f"Cannot proceed without accurate risk assessment."
            )
    else:
        total_risk = float(total_risk_val)

    cur.execute("""
        SELECT total_portfolio_value FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC LIMIT 1
    """)
    port_row = cur.fetchone()
    if not port_row or port_row["total_portfolio_value"] is None:
        logger.warning("[CIRCUIT_BREAKER] Portfolio value unavailable for risk calculation (CB7)")
        raise ValueError("Portfolio value unavailable for risk calculation")
    port_val = float(port_row["total_portfolio_value"])

    if port_val <= 0:
        raise ValueError(f"Invalid portfolio value for risk calculation: {port_val}")

    risk_pct = total_risk / port_val * 100
    return round(risk_pct, 2)


def _compute_spy_change(cur: Any, today: date) -> float:
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

    latest = float(prices[0]["close"])
    prior = float(prices[1]["close"])

    if latest <= 0 or prior <= 0:
        raise ValueError(f"Invalid SPY prices for {today}: latest={latest}, prior={prior}")

    change = (latest - prior) / prior * 100
    return round(change, 2)


def _compute_win_rate(cur: Any) -> float:
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

    wins = int(row["wins"])
    losses = int(row["losses"])
    decisive = wins + losses

    if decisive == 0:
        # No closed trades yet (e.g. fresh paper account) — CB9's trigger condition
        # (v < threshold and v > 0) treats 0 as "not applicable", not "triggered".
        # Raising here would block persistence of all 8 other circuit breaker
        # metrics, which don't depend on trade history and can be computed fine.
        logger.info("[CB9] No closed trades yet — win rate not applicable, defaulting to 0")
        return 0.0

    win_rate = wins / decisive * 100
    return round(win_rate, 1)


def _validate_all_metrics_present(metrics: dict[str, Any]) -> None:
    """CRITICAL: Atomically validate ALL required circuit breaker metrics are present.

    Fails immediately if ANY metric is missing or None. This prevents partial risk
    assessment where some checks pass but complete safety evaluation is impossible.

    Raises:
        RuntimeError: If ANY required metric missing or None
    """
    missing_metrics = []
    for cb in CIRCUIT_BREAKERS:
        if cb.metric_key not in metrics or metrics[cb.metric_key] is None:
            missing_metrics.append(cb.metric_key)

    if missing_metrics:
        raise RuntimeError(
            f"CRITICAL RISK ASSESSMENT FAILURE: Cannot evaluate circuit breakers — "
            f"missing metrics: {missing_metrics}. "
            f"Must have ALL 9 metrics to perform complete risk assessment. "
            f"Halting trading to prevent execution without complete safety checks."
        )


def _check_any_triggered(metrics: dict[str, Any]) -> bool:
    """Check if any circuit breaker is triggered based on registry.

    If a required metric is missing or None, fail closed (return True).
    This ensures data quality issues don't silently pass safety checks.
    """
    # CRITICAL: Validate ALL metrics present before checking any breaker
    _validate_all_metrics_present(metrics)
    return any(cb.is_triggered(metrics) for cb in CIRCUIT_BREAKERS)


def _count_triggered(metrics: dict[str, Any]) -> int:
    """Count how many circuit breakers are triggered.

    If a required metric is missing or None, fail closed (count as triggered).
    This ensures data quality issues don't silently reduce triggered count.
    """
    # CRITICAL: Validate ALL metrics present before counting
    _validate_all_metrics_present(metrics)
    return sum(1 for cb in CIRCUIT_BREAKERS if cb.is_triggered(metrics))


def _insert_circuit_breaker_status(cur: Any, today: date, metrics: dict[str, Any]) -> None:
    """Insert or update circuit breaker status in database."""
    try:
        cur.execute(
            """
            INSERT INTO circuit_breaker_status (
                check_date, portfolio_drawdown_pct, daily_loss_pct, weekly_loss_pct,
                consecutive_losses, open_risk_pct, vix_level, market_stage,
                spy_prior_day_change_pct, win_rate_last_30_pct,
                triggered_count, any_triggered
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                any_triggered = EXCLUDED.any_triggered
        """,
            (
                today,
                metrics["portfolio_drawdown_pct"],
                metrics["daily_loss_pct"],
                metrics["weekly_loss_pct"],
                metrics["consecutive_losses"],
                metrics["open_risk_pct"],
                metrics["vix_level"],
                metrics["market_stage"],
                metrics["spy_prior_day_change_pct"],
                metrics["win_rate_last_30_pct"],
                metrics["triggered_count"],
                metrics["any_triggered"],
            ),
        )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Failed to insert circuit breaker status: {e}", exc_info=True)
        raise


def main() -> None:
    """Main entry point for the loader."""
    try:
        # Use ET date, not UTC (AWS containers run in UTC but trading is ET-based)
        run_date = dt.now(EASTERN_TZ).date()
        with DatabaseContext("write", cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            compute_circuit_breaker_metrics(cur, today=run_date)
            logger.info(f"Circuit breaker metrics loader completed successfully for {run_date}")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Circuit breaker metrics loader failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    main()
