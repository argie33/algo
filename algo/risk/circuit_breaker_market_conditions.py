from __future__ import annotations

import math
from datetime import date as _date
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

# See circuit_breaker_portfolio_risk.py's top-of-file comment for why this qualified
# `import ... as _cb` (not `from ... import _float, logger`) is used instead of a plain
# module-level import.
import algo.risk.circuit_breaker as _cb


class CircuitBreakerMarketConditionsMixin:
    """Market-condition circuit breakers: VIX spike, market-stage (Stage 4 downtrend),
    data staleness, and prior-day market-health checks, plus the market-stage resolver
    shared with the drawdown re-engagement Follow-Through-Day check - split out of
    circuit_breaker.py's CircuitBreaker God-class (bloater decomposition, mechanical/
    no-behavior-change split, see git log 2026-09-05).

    Not usable standalone - relies on `_get_required_config` (defined on CircuitBreaker
    itself). Declared here under TYPE_CHECKING only so mypy can see the cross-class call,
    same convention as circuit_breaker_portfolio_risk.py.
    """

    if TYPE_CHECKING:

        def _get_required_config(self, key: str, context: str = ...) -> Any: ...

    def _check_vix_spike(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        from algo.infrastructure import MarketCalendar

        # On non-trading days (weekends/holidays), VIX data from last trading day is valid
        # (market regime unchanged while market is closed)
        is_trading_day = MarketCalendar.is_trading_day(current_date)

        cur.execute(
            "SELECT vix_level, date, data_unavailable, reason FROM market_health_daily WHERE date <= %s AND vix_level IS NOT NULL ORDER BY date DESC LIMIT 1",
            (current_date,),
        )
        row = cur.fetchone()
        # First check if row/data exists; if not, return None for later detection
        if row is None or row[0] is None:
            vix = None
            data_date = None
        else:
            vix = row[0]
            data_date = row[1]
            data_unavailable_flag = row[2]
            reason_msg = row[3]

            # CRITICAL FIX: market_health_daily.date can come back as datetime (not date) -
            # _resolve_current_market_stage needed the identical normalization for the same
            # column/table. Without it, data_date >= min_acceptable_date below (both `date`
            # objects) raises TypeError comparing datetime to date - caught by check_all's
            # generic exception handler and fails closed (halts), but as a confusing crash
            # rather than a clean stale-data message, and only when the driver happens to
            # return datetime for this particular row.
            if isinstance(data_date, datetime):
                data_date = data_date.date()

            # GOVERNANCE COMPLIANCE: Check data_unavailable flag before using VIX data
            if data_unavailable_flag:
                return {
                    "halted": True,
                    "reason": f"VIX data marked unavailable: {reason_msg or 'no reason provided'}. Cannot assess market volatility without valid VIX data. Fail-closed halt.",
                }

            vix = _cb._float(vix, None, context="vix_level check")
            # CRITICAL: VIX is a volatility index and is physically never <= 0 (historical
            # floor is ~9, set by index construction itself) - a non-positive value can only
            # come from upstream data corruption (bad parse, sign error, wrong field mapped).
            # Silently treating it as "not halted" (it easily clears the >threshold check)
            # would be a fail-open on data corruption, the exact failure mode this circuit
            # breaker exists to prevent. Stress-tested 2026-07-28: confirmed real historical
            # data has never had vix_level <= 0 (min ever recorded: 15.03), so this only fires
            # on genuine corruption, never a real market condition.
            if vix <= 0:
                _cb.logger.critical(
                    f"VIX data corrupted: {vix} is not a physically possible VIX value - halting trading"
                )
                corrupted_vix_max_val = self._get_required_config("vix_max_threshold", "in VIX circuit breaker check")
                return {
                    "halted": True,
                    "reason": f"VIX data corrupted: value {vix} is not physically possible (VIX must be positive). Fail-closed halt.",
                    "value": vix,
                    "threshold": _cb._float(corrupted_vix_max_val, None),
                }
            # CRITICAL FIX: Use trading-day logic, not calendar days
            # On trading days: accept data from today OR the most recent trading day (pre-market runs get yesterday's EOD)
            # On non-trading days: data from most recent trading day is valid (market regime unchanged while closed)
            # DO NOT compare calendar days (Friday vs Monday = 3-5 days apart)

            is_acceptable_age = False
            min_acceptable_date = None

            if is_trading_day:
                # Today is a trading day (Mon-Fri)
                # Find the most recent trading day (to handle cases where today is trading day)
                most_recent_trading_day = current_date
                for _ in range(10):
                    if MarketCalendar.is_trading_day(most_recent_trading_day):
                        break
                    most_recent_trading_day -= timedelta(days=1)

                # Also find the previous trading day (pre-market runs use yesterday's EOD)
                prev_trading_day = current_date - timedelta(days=1)
                for _ in range(10):
                    if MarketCalendar.is_trading_day(prev_trading_day):
                        break
                    prev_trading_day -= timedelta(days=1)

                # Accept data from current trading day OR previous trading day
                min_acceptable_date = prev_trading_day
                is_acceptable_age = data_date >= min_acceptable_date
            else:
                # Today is weekend/holiday: find most recent trading day and require that date
                most_recent_trading_day = current_date - timedelta(days=1)
                for _ in range(10):
                    if MarketCalendar.is_trading_day(most_recent_trading_day):
                        break
                    most_recent_trading_day -= timedelta(days=1)

                min_acceptable_date = most_recent_trading_day
                is_acceptable_age = data_date >= min_acceptable_date

            if not is_acceptable_age:
                calendar_age = (current_date - data_date).days
                _cb.logger.critical(
                    f"VIX data stale: latest from {data_date}, expected from {min_acceptable_date} or later. "
                    f"Calendar age: {calendar_age} days. Trading halted."
                )
                vix_max_val = self._get_required_config("vix_max_threshold", "in VIX circuit breaker check")
                return {
                    "halted": True,
                    "reason": f"VIX data stale ({data_date}): expected {min_acceptable_date} or later. Trading halted.",
                    "value": None,
                    "threshold": _cb._float(vix_max_val, None),
                }

        # CRITICAL: VIX data unavailable - cannot safely assess volatility risk.
        # Fail-closed: cannot use fallback estimates. Even computed estimates from SPY
        # volatility mask the real issue (missing live data) and may be inaccurate during
        # extreme market dislocations when we most need reliable circuit breaker protection.
        vix_max_val = self._get_required_config("vix_max_threshold", "in VIX circuit breaker check")

        if vix is None:
            _cb.logger.critical("VIX unavailable from live data sources - halting trading")
            return {
                "halted": True,
                "reason": "VIX data unavailable - cannot assess volatility risk. Trading halted.",
                "value": None,
                "threshold": _cb._float(vix_max_val, None),
            }

        threshold = _cb._float(
            vix_max_val,
            None,
            context="vix_max_threshold",
        )
        if threshold is None:
            _cb.logger.error("CRITICAL: vix_max_threshold is invalid (NaN/Inf). Cannot enforce VIX circuit breaker.")
            return {"halted": True, "reason": "CRITICAL: vix_max_threshold invalid"}
        return {
            "halted": vix > threshold,
            "reason": (f"VIX {vix:.1f} > {threshold:.0f}" if vix > threshold else f"VIX {vix:.1f}"),
            "value": vix,
            "threshold": threshold,
        }

    def _resolve_current_market_stage(
        self, current_date: _date, cur: PsycopgCursor[Any]
    ) -> tuple[int | None, str, str | None]:
        """Shared market_stage lookup with data-freshness handling, used by both the
        Stage-4 circuit breaker (CB6, _check_market_stage) and the drawdown re-engagement
        Follow-Through-Day check (_check_drawdown_re_engagement) - both need "what is the
        market stage right now", and duplicating this logic let the FTD check drift out of
        sync with CB6's NULL/staleness handling (see history for the bug that caused).

        On trading days: prefer today's market_stage once computed; the morning loader inserts
        a same-day row before market_stage is available, so we fall back to the most recent
        NON-NULL stage (bounded to 10 days) rather than fail-closed halting on that placeholder.
        On non-trading days (weekends/holidays): use most recent trading day's market_stage
        (market regime doesn't change when market is closed).
        CRITICAL: MarketCalendar must succeed to ensure holiday accuracy.

        Returns (stage, trend, halt_reason). halt_reason is None on success; when set, the
        caller must fail-closed halt with it instead of trusting stage/trend (both None/"unknown").
        """
        from algo.infrastructure import MarketCalendar

        # Determine expected data date based on trading days
        is_trading_day = MarketCalendar.is_trading_day(current_date)
        if is_trading_day:
            # Trading day: require today's market_stage (market closed at 4 PM today)
            expected_data_date = current_date
        else:
            # Weekend/holiday: use most recent trading day's market_stage
            # (market regime valid from most recent close, unchanged until next open)
            expected_data_date = current_date - timedelta(days=1)
            for _ in range(10):
                if MarketCalendar.is_trading_day(expected_data_date):
                    break
                expected_data_date -= timedelta(days=1)

        # market_health_daily gets a same-day row from the morning loader (VIX, breadth) before
        # market_stage is computed later in the day - a bare "latest row <= expected_data_date"
        # picks up that not-yet-computed NULL and fail-closed halts even though yesterday's stage
        # is still valid. compute_circuit_breakers.py's own _compute_market_stage() already skips
        # NULL rows for this exact reason (WHERE market_stage IS NOT NULL); mirror that here so a
        # same-day placeholder row doesn't halt trading before the day's stage is even available.
        cur.execute(
            """SELECT date, market_stage, market_trend, data_unavailable, reason FROM market_health_daily
               WHERE date <= %s AND market_stage IS NOT NULL ORDER BY date DESC LIMIT 1""",
            (expected_data_date,),
        )
        row = cur.fetchone()
        if row is None:
            return None, "unknown", "Market health data missing - fail-closed"

        data_date, market_stage_val, market_trend_val, data_unavailable_flag, reason_msg = (
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
        )

        # GOVERNANCE COMPLIANCE: Check data_unavailable flag before using any data from this row
        if data_unavailable_flag:
            return (
                None,
                "unknown",
                f"Market health data marked unavailable: {reason_msg or 'no reason provided'}. Cannot determine market stage without valid data. Fail-closed halt.",
            )

        if isinstance(data_date, datetime):
            data_date = data_date.date()

        # Bound how far back the NULL-skipping fallback above may reach: a legitimately
        # not-yet-computed same-day value is expected (small gap), but if the most recent
        # non-NULL stage is more than 10 calendar days old, market_stage computation itself
        # is broken and trusting it further would be exactly the silent stale-data bypass
        # this check exists to prevent - fail closed instead.
        staleness_days = (expected_data_date - data_date).days
        if staleness_days > 10:
            return (
                None,
                "unknown",
                (
                    f"Market stage last computed {data_date} ({staleness_days}d before expected "
                    f"{expected_data_date}) - too stale to trust. Fail-closed halt."
                ),
            )

        stage = int(market_stage_val)
        trend = market_trend_val if market_trend_val is not None else "unknown"
        return stage, trend, None

    def _check_market_stage(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """H7 FIX: Market stage validation with data freshness check (CB6)."""
        stage, trend, halt_reason = self._resolve_current_market_stage(current_date, cur)
        if halt_reason is not None:
            return {"halted": True, "reason": halt_reason}
        # Stage 4 = halt new entries (full downtrend). Stage 3 = caution but allow.
        halted = stage == 4
        return {
            "halted": halted,
            "reason": (f"Stage 4 downtrend (trend={trend})" if halted else f"Stage {stage} ({trend})"),
            "value": stage,
        }

    def _check_data_freshness(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Block if our market data is too stale.

        Compares against the previous trading day (not a fixed calendar threshold)
        so 3-day holiday weekends don't cause false halts.
        Allows up to 2 trading days of staleness to handle RDS Proxy replication lag.

        NOTE: Uses trading-day logic (more sophisticated) vs centralized config's calendar-day logic.
        Coordinated via get_freshness_rule("price_daily") for consistency with other components.
        CRITICAL: MarketCalendar must succeed; cannot fall back to weekday logic (misses holidays).
        """
        cur.execute(
            "SELECT date, data_unavailable, data_unavailable_reason FROM price_daily WHERE symbol = 'SPY' ORDER BY date DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row is None or len(row) != 3 or row[0] is None:
            return {
                "halted": True,
                "reason": f"SPY data query malformed (expected 3 columns, got {len(row) if row else 0})",
            }

        latest = row[0]
        data_unavailable_flag_raw = row[1]
        if data_unavailable_flag_raw is None:
            _cb.logger.critical(
                "[CIRCUIT_BREAKER] SPY data_unavailable flag missing from database query. "
                "Fail-closed: cannot determine if SPY data is safe for trading."
            )
            return {
                "halted": True,
                "reason": "SPY data_unavailable flag is NULL - cannot determine data integrity. Fail-closed halt.",
            }
        data_unavailable_flag = bool(data_unavailable_flag_raw)
        reason_msg = row[2] if row[2] is not None else None

        # GOVERNANCE COMPLIANCE: Check data_unavailable flag before using price data
        if data_unavailable_flag:
            return {
                "halted": True,
                "reason": f"SPY price data marked unavailable: {reason_msg or 'no reason provided'}. Cannot assess data freshness without valid prices. Fail-closed halt.",
            }
        days_stale = (current_date - latest).days

        # Compute the previous trading day as the freshness reference point.
        # Using trading-day comparison prevents false halts after 3-day weekends
        # where the calendar gap (e.g. Friday -> Tuesday = 4 days) would exceed a
        # fixed threshold even though the data is from the last trading day.
        from datetime import timedelta

        expected = current_date - timedelta(days=1)
        min_acceptable = current_date - timedelta(days=2)  # 1 trading day back
        try:
            from algo.infrastructure import MarketCalendar

            for _ in range(10):
                if MarketCalendar.is_trading_day(expected):
                    break
                expected -= timedelta(days=1)
            for _ in range(10):
                if MarketCalendar.is_trading_day(min_acceptable):
                    break
                min_acceptable -= timedelta(days=1)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as cal_e:
            _cb.logger.critical(
                f"MarketCalendar check failed: {cal_e}. "
                "Cannot fall back to weekday logic - holidays would be misclassified. "
                "Failing closed to prevent false staleness determination."
            )
            return {
                "halted": True,
                "reason": f"Market calendar unavailable ({type(cal_e).__name__}). Cannot determine trading days accurately. Fail-closed halt.",
                "value": days_stale,
            }
        is_stale = latest < min_acceptable

        return {
            "halted": is_stale,
            "reason": (
                f"Data {days_stale}d stale (latest {latest}, expected {expected})" if is_stale else f"{days_stale}d old"
            ),
            "value": days_stale,
        }

    def _check_intraday_market_health(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Prior-day market drop check: did SPY fall >2% yesterday?

        The orchestrator runs pre-market (9:30 AM ET). price_daily contains yesterday's
        EOD prices, so the two most recent rows are yesterday vs the day before. This
        checks the prior day's return, not a live intraday reading. Blocking on a >2%
        decline yesterday is intentional: entering new swing positions the morning after
        a significant sell-off is poor risk management (Minervini: wait for market to
        stabilize before adding exposure).
        CRITICAL: Missing or invalid SPY prices must halt trading (fail-closed).
        """
        try:
            cur.execute(
                """
                SELECT close, data_unavailable, data_unavailable_reason FROM price_daily
                WHERE symbol = 'SPY'
                  AND date <= %s
                ORDER BY date DESC LIMIT 2
                """,
                (current_date,),
            )
            rows = cur.fetchall()
            if len(rows) < 2:
                _cb.logger.critical(
                    f"CIRCUIT BREAKER: Insufficient SPY price history (got {len(rows)}, need 2). "
                    "Cannot determine prior-day market movement. Halting to prevent trading in unknown market conditions."
                )
                return {"halted": True, "reason": "Insufficient SPY price history - cannot assess market stability"}

            # GOVERNANCE COMPLIANCE: Check data_unavailable flags before using prices
            for idx, row in enumerate(rows):
                data_unavailable_flag = row[1] if len(row) > 1 else False
                reason_msg = row[2] if len(row) > 2 else None
                if data_unavailable_flag:
                    return {
                        "halted": True,
                        "reason": f"SPY price data marked unavailable (row {idx}): {reason_msg or 'no reason provided'}. Cannot assess market movement with invalid prices. Fail-closed halt.",
                    }

            latest = float(rows[0][0]) if rows[0][0] is not None else None
            prior = float(rows[1][0]) if rows[1][0] is not None else None

            # BUG FOUND 2026-08-10: `prior <= 0` never catches NaN/Inf (always False in
            # Python), and `latest` had no finiteness check at all. A NaN/Inf `latest` or
            # `prior` would have produced a NaN `prior_day_change` below, whose
            # `prior_day_change <= -2.0` comparison silently evaluates to False - fail-open
            # (not halted) for a genuinely unusable SPY price, contradicting this function's
            # own documented "CRITICAL: Missing or invalid SPY prices must halt trading
            # (fail-closed)" contract.
            if (latest is not None and (math.isnan(latest) or math.isinf(latest))) or (
                prior is not None and (math.isnan(prior) or math.isinf(prior))
            ):
                _cb.logger.critical(
                    f"CIRCUIT BREAKER: Non-finite SPY price data (latest={latest}, prior={prior}). "
                    "Cannot calculate prior-day market change. Halting to prevent trading with invalid market data."
                )
                return {
                    "halted": True,
                    "reason": "Non-finite SPY price data - cannot assess market stability. Fail-closed halt.",
                }

            if latest is None or prior is None or prior <= 0:
                _cb.logger.critical(
                    f"CIRCUIT BREAKER: Invalid SPY price data (latest={latest}, prior={prior}). "
                    "Cannot calculate prior-day market change. Halting to prevent trading with missing market data."
                )
                return {
                    "halted": True,
                    "reason": "Invalid SPY price data - cannot assess market stability. Fail-closed halt.",
                }

            prior_day_change = (latest - prior) / prior * 100.0

            # REAL-MONEY-READINESS FIX (2026-09-06 audit): this threshold was a bare literal,
            # unlike every sibling check in this file (vix_max_threshold, max_daily_loss_pct,
            # sector_drawdown_halt_pct, etc.) which all pull from _get_required_config - changing
            # it required a code deploy instead of an algo_config row update. Now config-driven,
            # consistent with the rest of this file's checks.
            drop_halt_pct_raw = self._get_required_config(
                "intraday_prior_day_drop_halt_pct", "in intraday market health check"
            )
            drop_halt_pct = _cb._float(drop_halt_pct_raw, None, context="intraday_prior_day_drop_halt_pct")
            if drop_halt_pct is None:
                _cb.logger.error(
                    "CRITICAL: intraday_prior_day_drop_halt_pct is invalid (NaN/Inf). "
                    "Cannot enforce intraday market health circuit breaker."
                )
                return {"halted": True, "reason": "CRITICAL: intraday_prior_day_drop_halt_pct invalid"}

            # Halt if SPY dropped more than the configured threshold yesterday - significant
            # sell-off, wait for stability.
            if prior_day_change <= drop_halt_pct:
                return {
                    "halted": True,
                    "reason": f"Market down {prior_day_change:.2f}% yesterday (await stability)",
                    "market_change_pct": round(prior_day_change, 2),
                }

            return {
                "halted": False,
                "reason": f"SPY prior day {prior_day_change:+.2f}%",
                "market_change_pct": round(prior_day_change, 2),
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            _cb.logger.critical(f"CIRCUIT BREAKER: Prior-day market health check failed: {e}")
            return {
                "halted": True,
                "reason": f"Market health check unavailable (data error): {type(e).__name__}. Cannot proceed without market data.",
            }
