"""
Compute circuit breaker metrics and store in circuit_breaker_status table.
Runs daily at 4:30 PM ET (before Phase 7 reconciliation) via EventBridge scheduled task.

NOTE: the CB1-CB9 numbering below is LOCAL to this reporting/dashboard loader and
is NOT the same scheme as algo/risk/circuit_breaker.py's live pretrade halt gate -
the two only agree on CB1/CB2/CB3/CB6 (drawdown/daily loss/consecutive losses/market
stage). CB4/CB5/CB7/CB8/CB9 name different checks in each file (e.g. this loader's
CB9 is win rate; the live gate's CB9 is sector drawdown). Do not assume a "CBn
triggered" reference means the same thing in both files - check which module it
came from.

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
        No fallback - incomplete risk assessment must fail closed.
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


def _build_circuit_breakers(cur: Any) -> list[CircuitBreakerDef]:
    """Build circuit breaker definitions with thresholds read live from algo_config.

    CRITICAL: This used to hardcode thresholds (e.g. portfolio_drawdown_pct >= 20.0)
    completely independent of the actual configured values algo/risk/circuit_breaker.py
    reads at halt time (halt_drawdown_pct = -10, i.e. halt at 10% down). A live 12-19%
    drawdown would already have halted real trading while this loader - which writes
    the any_triggered/triggered_count this session's dashboard and Phase 9 alerting both
    read - kept reporting "all clear" for the same condition. Thresholds must come from
    the same source of truth so this reporting layer and the real halt gate never diverge.
    """
    cur.execute(
        """
        SELECT key, value FROM algo_config
        WHERE key IN ('halt_drawdown_pct', 'max_daily_loss_pct', 'max_weekly_loss_pct',
                      'max_total_risk_pct', 'vix_max_threshold', 'max_consecutive_losses',
                      'min_win_rate_pct')
        """
    )
    cfg = {row["key"]: row["value"] for row in cur.fetchall()}
    required = (
        "halt_drawdown_pct",
        "max_daily_loss_pct",
        "max_weekly_loss_pct",
        "max_total_risk_pct",
        "vix_max_threshold",
        "max_consecutive_losses",
        "min_win_rate_pct",
    )
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ValueError(f"algo_config missing required circuit breaker keys: {missing}")

    return [
        CircuitBreakerDef("CB1", "portfolio_drawdown_pct", abs(float(cfg["halt_drawdown_pct"])), lambda v, t: v >= t),
        CircuitBreakerDef("CB2", "daily_loss_pct", float(cfg["max_daily_loss_pct"]), lambda v, t: v >= t),
        CircuitBreakerDef("CB3", "consecutive_losses", int(cfg["max_consecutive_losses"]), lambda v, t: v >= t),
        CircuitBreakerDef("CB4", "vix_level", float(cfg["vix_max_threshold"]), lambda v, t: v >= t),
        CircuitBreakerDef("CB5", "weekly_loss_pct", float(cfg["max_weekly_loss_pct"]), lambda v, t: v >= t),
        CircuitBreakerDef("CB6", "market_stage", 4, lambda v, t: v == t),
        CircuitBreakerDef("CB7", "open_risk_pct", float(cfg["max_total_risk_pct"]), lambda v, t: v >= t),
        CircuitBreakerDef("CB8", "spy_prior_day_change_pct", -2.0, lambda v, t: v <= t),
        CircuitBreakerDef("CB9", "win_rate_last_30_pct", float(cfg["min_win_rate_pct"]), lambda v, t: v < t and v > 0),
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
        breakers = _build_circuit_breakers(cur)
        metrics["any_triggered"] = _check_any_triggered(metrics, breakers)
        metrics["triggered_count"] = _count_triggered(metrics, breakers)

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
    """Cash-flow-adjusted drawdown (migration 1134): raw total_portfolio_value conflates
    trading performance with external deposits/withdrawals (see algo_capital_flows and
    algo/risk/circuit_breaker.py::_check_drawdown for the full incident). This value feeds
    circuit_breaker_status, which the dashboard health panel reads directly - computing it
    from raw total_portfolio_value here would show a false "triggered" drawdown on the
    dashboard even after the actual trading circuit breaker (which already uses
    adjusted_equity) correctly clears, exactly the halted-vs-completed inconsistency this
    must not reintroduce.
    """
    cur.execute("""
        SELECT MAX(adjusted_equity) AS peak,
               (SELECT adjusted_equity FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1) AS current
        FROM algo_portfolio_snapshots
    """)
    row = cur.fetchone()
    if not row:
        error_msg = (
            "[CIRCUIT_BREAKER CRITICAL] Portfolio snapshot query returned no rows. "
            "Cannot compute drawdown (CB1) - database may be empty or query failed."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
    if row["peak"] is None:
        error_msg = (
            "[CIRCUIT_BREAKER CRITICAL] Maximum (peak) portfolio value is NULL. "
            "Cannot compute drawdown (CB1). Check adjusted_equity calculation."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
    if row["current"] is None:
        error_msg = (
            "[CIRCUIT_BREAKER CRITICAL] Current portfolio value is NULL. "
            "Cannot compute drawdown (CB1). Check most recent portfolio snapshot."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
    peak = float(row["peak"])
    current = float(row["current"])
    if peak <= 0:
        error_msg = (
            f"[CIRCUIT_BREAKER CRITICAL] Invalid peak portfolio value: {peak}. "
            f"Peak equity must be positive."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
    dd = (peak - current) / peak * 100
    return dd


def _compute_daily_loss(cur: Any, today: date) -> float:
    """Cash-flow-adjusted daily loss (migration 1134): mirrors _compute_drawdown above and
    algo/risk/circuit_breaker.py::_check_daily_loss - the precomputed daily_return_pct
    column is derived from raw total_portfolio_value deltas, so a same-day capital
    withdrawal reads as an equivalent trading loss here just like the pre-1134 drawdown
    bug this loader already fixed once for CB1. Confirmed live 2026-07-27: this still used
    the raw column and disagreed with the live gate's adjusted_equity-based value.
    """
    cur.execute("SELECT adjusted_equity FROM algo_portfolio_snapshots WHERE snapshot_date = %s", (today,))
    today_row = cur.fetchone()
    if not today_row:
        error_msg = (
            f"[CIRCUIT_BREAKER CRITICAL] No portfolio snapshot for {today}. "
            f"Cannot compute daily loss (CB2). Check: (1) snapshot table has entry for today, "
            f"(2) date values are in ET timezone"
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
    if today_row["adjusted_equity"] is None:
        error_msg = (
            f"[CIRCUIT_BREAKER CRITICAL] Adjusted equity is NULL for {today}. "
            f"Cannot compute daily loss (CB2). Check adjusted_equity calculation."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
    cur.execute(
        """
        SELECT adjusted_equity FROM algo_portfolio_snapshots
        WHERE snapshot_date < %s AND adjusted_equity IS NOT NULL
        ORDER BY snapshot_date DESC LIMIT 1
        """,
        (today,),
    )
    prev_row = cur.fetchone()
    if not prev_row:
        error_msg = (
            f"[CIRCUIT_BREAKER CRITICAL] No prior portfolio snapshot before {today}. "
            f"Cannot compute daily loss (CB2) - need at least 2 days of history. "
            f"Check: (1) snapshots for previous trading day exist, (2) ET date values"
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
    if prev_row["adjusted_equity"] is None:
        error_msg = (
            f"[CIRCUIT_BREAKER CRITICAL] Prior adjusted equity is NULL. "
            f"Cannot compute daily loss (CB2). Check adjusted_equity calculation for prior date."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)
    cur_val = float(today_row["adjusted_equity"])
    prev_val = float(prev_row["adjusted_equity"])
    if prev_val <= 0:
        raise ValueError(f"Invalid prior adjusted_equity for daily loss calculation: {prev_val}")
    daily = (cur_val - prev_val) / prev_val * 100
    loss = abs(min(0, daily))
    return loss


def _compute_consecutive_losses(cur: Any) -> int:
    # Mirrors algo/risk/circuit_breaker.py's _check_consecutive_losses (the live trading
    # gate) - same exclusions (reconciliation/force-close/delisted/DATA-QC/CONCENTRATION
    # closes aren't real strategy losses) and same exit_time-based tiebreak (exit_date DESC
    # alone is not deterministic when 2+ trades close same day). Without this, this
    # reporting table disagreed with the live gate it's supposed to be reflecting on the
    # dashboard - confirmed live 2026-07-27: this query kept reporting the live gate's
    # already-fixed, already-excluded bug-induced closes as real losses for the rest of the
    # day. CONCENTRATION added 2026-08-03 alongside the same fix in the live gate: it was
    # missing there too, so POSITION_SIZE_CONCENTRATION/SECTOR_CONCENTRATION force-exits
    # (portfolio rebalancing, not a strategy call) counted as real losses on both sides.
    cur.execute(
        """
        SELECT profit_loss_pct FROM algo_trades
        WHERE status = 'closed' AND exit_date IS NOT NULL
          AND trade_id NOT LIKE 'EXT-%%'
          AND exit_reason NOT LIKE %s
          AND exit_reason NOT LIKE %s
          AND exit_reason NOT LIKE %s
          AND exit_reason NOT LIKE %s
          AND exit_reason NOT LIKE %s
        ORDER BY exit_date DESC, exit_time DESC NULLS LAST, id DESC
        LIMIT 10
        """,
        ("%reconciliation%", "%force%close%", "%delisted%", "%DATA-QC%", "%CONCENTRATION%"),
    )
    rows = cur.fetchall()
    if not rows:
        logger.info(
            "[CIRCUIT_BREAKER] No closed trades available for consecutive loss calculation (CB3) - new account, returning 0"
        )
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
    return float(row["vix_level"])


def _compute_weekly_loss(cur: Any, today: date) -> float:
    """Cash-flow-adjusted 7-day return, mirroring algo/risk/circuit_breaker.py::_check_weekly_loss
    (see _compute_daily_loss above for why raw total_portfolio_value must not be used).
    Reference points are the most recent snapshot on/before `today` and on/before
    `today - 7d` (not the earliest snapshot AT OR AFTER 7 days ago) - the prior version's
    ORDER BY ASC picked a different, later snapshot than the live gate whenever a snapshot
    was missing exactly 7 days back (weekend/holiday gap), silently comparing a different
    time window than the check it's supposed to mirror.
    """
    week_ago = today - timedelta(days=7)
    cur.execute(
        """
        SELECT
            (SELECT adjusted_equity FROM algo_portfolio_snapshots
             WHERE snapshot_date <= %s AND adjusted_equity IS NOT NULL
             ORDER BY snapshot_date DESC LIMIT 1) AS cur_val,
            (SELECT adjusted_equity FROM algo_portfolio_snapshots
             WHERE snapshot_date <= %s AND adjusted_equity IS NOT NULL
             ORDER BY snapshot_date DESC LIMIT 1) AS week_ago_val
        """,
        (today, week_ago),
    )
    row = cur.fetchone()
    if not row or row["cur_val"] is None or row["week_ago_val"] is None:
        raise ValueError("Insufficient adjusted_equity snapshot data for 7-day loss calculation")

    cur_val = float(row["cur_val"])
    week_ago_val = float(row["week_ago_val"])
    if week_ago_val <= 0:
        raise ValueError(f"Invalid week-ago adjusted_equity for 7-day calculation: {week_ago_val}")

    weekly_ret = (cur_val - week_ago_val) / week_ago_val * 100
    loss = abs(min(0, weekly_ret))
    return loss


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
            "Market stage not available in market_health_daily - "
            "Phase X market exposure detection must populate market_health_daily before circuit breaker metrics. "
            "CB6 (market stage break) cannot be computed without this critical market regime data."
        )
    stage = int(row["market_stage"])
    return stage


def _compute_open_risk(cur: Any) -> float:
    """Calculate total open risk % of portfolio.

    CRITICAL: Requires all open positions to have valid stop_loss_price set.
    No fallback to entry_price (that would show 0% risk when stops are missing).
    Fails fast if any position lacks a stop - this is a data integrity error.
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
            "NO FALLBACK to historical entry stop - current risk requires current stops."
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
    return risk_pct


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
    return change


def _compute_win_rate(cur: Any) -> float:
    # Mirrors algo/risk/circuit_breaker.py's _check_win_rate_floor (the live trading gate):
    # same exclusions (reconciliation/force-close/delisted/DATA-QC/CONCENTRATION closes and
    # EXT- trades aren't real strategy outcomes), same exit_r_multiple IS NOT NULL guard,
    # same exit_time-based tiebreak, and same inclusion of open positions' unrealized P&L so
    # a good closed-trade history can't mask live bleeding. Without this, this reporting
    # table disagreed with the live gate - confirmed live 2026-07-27: this query reported
    # 40.0% (dragged down by the live gate's already-excluded bug-induced DATA-QC closes)
    # while the live gate's own win_rate_floor check reported the real 61.1%. CONCENTRATION
    # added 2026-08-03 alongside the same fix in the live gate - see
    # _compute_consecutive_losses above for the live-reproduced incident.
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
               COUNT(*) FILTER (WHERE pnl_pct < 0) as losses
        FROM (
            SELECT profit_loss_pct as pnl_pct
            FROM (
                SELECT profit_loss_pct, id
                FROM algo_trades
                WHERE status = 'closed' AND exit_date IS NOT NULL
                  AND exit_r_multiple IS NOT NULL
                  AND trade_id NOT LIKE 'EXT-%%'
                  AND exit_reason NOT LIKE %s
                  AND exit_reason NOT LIKE %s
                  AND exit_reason NOT LIKE %s
                  AND exit_reason NOT LIKE %s
                  AND exit_reason NOT LIKE %s
                ORDER BY exit_date DESC, exit_time DESC NULLS LAST, id DESC
                LIMIT 30
            ) recent_closed
            UNION ALL
            SELECT unrealized_pnl_pct as pnl_pct
            FROM algo_positions
            WHERE status = 'open'
              AND quantity > 0
        ) recent_trades
    """, ("%reconciliation%", "%force%close%", "%delisted%", "%DATA-QC%", "%CONCENTRATION%"))
    row = cur.fetchone()
    if not row:
        raise ValueError("Win rate query failed")

    wins = int(row["wins"])
    losses = int(row["losses"])
    decisive = wins + losses

    if decisive == 0:
        # No closed trades yet (e.g. fresh paper account) - CB9's trigger condition
        # (v < threshold and v > 0) treats 0 as "not applicable", not "triggered".
        # Raising here would block persistence of all 8 other circuit breaker
        # metrics, which don't depend on trade history and can be computed fine.
        logger.info("[CB9] No closed trades yet - win rate not applicable, defaulting to 0")
        return 0.0

    win_rate = wins / decisive * 100
    return win_rate


def _validate_all_metrics_present(metrics: dict[str, Any], breakers: list[CircuitBreakerDef]) -> None:
    """CRITICAL: Atomically validate ALL required circuit breaker metrics are present.

    Fails immediately if ANY metric is missing or None. This prevents partial risk
    assessment where some checks pass but complete safety evaluation is impossible.

    Raises:
        RuntimeError: If ANY required metric missing or None
    """
    missing_metrics = []
    for cb in breakers:
        if cb.metric_key not in metrics or metrics[cb.metric_key] is None:
            missing_metrics.append(cb.metric_key)

    if missing_metrics:
        raise RuntimeError(
            f"CRITICAL RISK ASSESSMENT FAILURE: Cannot evaluate circuit breakers - "
            f"missing metrics: {missing_metrics}. "
            f"Must have ALL 9 metrics to perform complete risk assessment. "
            f"Halting trading to prevent execution without complete safety checks."
        )


def _check_any_triggered(metrics: dict[str, Any], breakers: list[CircuitBreakerDef]) -> bool:
    """Check if any circuit breaker is triggered based on registry.

    If a required metric is missing or None, fail closed (return True).
    This ensures data quality issues don't silently pass safety checks.
    """
    # CRITICAL: Validate ALL metrics present before checking any breaker
    _validate_all_metrics_present(metrics, breakers)
    return any(cb.is_triggered(metrics) for cb in breakers)


def _count_triggered(metrics: dict[str, Any], breakers: list[CircuitBreakerDef]) -> int:
    """Count how many circuit breakers are triggered.

    If a required metric is missing or None, fail closed (count as triggered).
    This ensures data quality issues don't silently reduce triggered count.
    """
    # CRITICAL: Validate ALL metrics present before counting
    _validate_all_metrics_present(metrics, breakers)
    return sum(1 for cb in breakers if cb.is_triggered(metrics))


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
                any_triggered = EXCLUDED.any_triggered,
                updated_at = CURRENT_TIMESTAMP
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
