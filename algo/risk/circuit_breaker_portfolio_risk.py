from __future__ import annotations

import math
from datetime import date as _date
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from psycopg2.extensions import cursor as PsycopgCursor

# Qualified-attribute reference (not a plain `from ... import _float, logger`) so this mixin
# reads the exact same `_float` helper and `logger` instance physically defined in
# circuit_breaker.py - matching this repo's established mixin-split convention (see
# algo/monitoring/position_order_management.py's `import ... as _pm` / `_pm.time`/`_pm.requests`
# style). This keeps any existing test that does `patch.object(circuit_breaker_module, ...)`
# on those base-module globals working unchanged, since a function's globals are bound to
# whatever module it is physically defined in, not the class it ends up mixed into.
import algo.risk.circuit_breaker as _cb
from utils.trading import PositionStatus


class CircuitBreakerPortfolioRiskMixin:
    """Portfolio-level P&L threshold circuit breakers (drawdown, daily/weekly loss, total
    open risk, daily profit cap) and their shared minimum-elapsed-trading-days
    re-engagement lockout - split out of circuit_breaker.py's CircuitBreaker God-class
    (bloater decomposition, mechanical/no-behavior-change split, see git log 2026-09-05).

    Not usable standalone - relies on `_get_required_config` (defined on CircuitBreaker
    itself) and `_resolve_current_market_stage` (defined on CircuitBreakerMarketConditionsMixin,
    a sibling mixin). Declared here under TYPE_CHECKING only (not a real method - a real
    stub here would shadow the sibling mixin's actual implementation via MRO) purely so mypy
    can see these cross-mixin calls; same `config: Any`-style convention as
    algo/monitoring/position_order_management.py's PositionOrderManagementMixin.
    """

    if TYPE_CHECKING:

        def _get_required_config(self, key: str, context: str = ...) -> Any: ...

        def _resolve_current_market_stage(
            self, current_date: _date, cur: PsycopgCursor[Any]
        ) -> tuple[int | None, str, str | None]: ...

    def _check_drawdown(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        # Uses adjusted_equity/adjusted_running_peak (cash-flow-adjusted), NOT raw
        # total_portfolio_value/running_peak. Raw equity moves for two different reasons:
        # trading performance AND external capital flows (deposits/withdrawals). A withdrawal
        # looks identical to a trading loss in the raw series, which is exactly the bug fixed
        # by migration 1134 (see algo_capital_flows) - this circuit breaker must measure
        # trading performance, not account size. Every capital flow must be recorded in
        # algo_capital_flows (see scripts/record_capital_flow.py) or it will misreport here.
        # CRITICAL FIX: bound the "current" subquery by current_date - an unbounded
        # "ORDER BY snapshot_date DESC LIMIT 1" picks up any stray future-dated row (e.g. a
        # leftover local --date simulation snapshot in the shared dev DB) ahead of the real
        # current one, corrupting the drawdown halt check with the wrong equity value.
        # Live-reproduced 2026-08-09: a leftover 2026-08-11 test snapshot outranked the real
        # current run's own snapshot. _check_daily_loss below already bounds by current_date
        # correctly - this sibling check (and _check_drawdown_re_engagement) had been missed.
        # MAX(adjusted_equity) for the peak is intentionally unbounded (all-time high).
        cur.execute(
            """
            SELECT MAX(adjusted_equity),
                   (SELECT adjusted_equity FROM algo_portfolio_snapshots
                    WHERE snapshot_date <= %s ORDER BY snapshot_date DESC LIMIT 1)
            FROM algo_portfolio_snapshots
            """,
            (current_date,),
        )
        row = cur.fetchone()
        # Bootstrap path: if table is empty (first ever run), allow through with explicit logging
        if row is None or row[0] is None or row[1] is None:
            _cb.logger.warning(
                "[CIRCUIT_BREAKER] Bootstrap path: no portfolio history available yet. "
                "Allowing initial trading while history accumulates. "
                "Subsequent runs will require valid portfolio peak/current values."
            )
            return {"halted": False, "reason": "Bootstrap: no portfolio history yet"}
        peak = _cb._float(row[0], None, context="drawdown peak")
        cur_val = _cb._float(row[1], None, context="drawdown current")
        if peak is None or cur_val is None or peak <= 0 or cur_val <= 0:
            return {"halted": True, "reason": "Invalid portfolio values - fail-closed"}
        dd = (peak - cur_val) / peak * 100.0
        halt_dd_val = self._get_required_config("halt_drawdown_pct", "in drawdown check")
        # _cb._float(val, default=None, ...) raises ValueError on invalid/NaN/Inf input rather than
        # returning None (see its docstring/impl) - an `if threshold is None` guard here would be
        # dead code. An invalid config value propagates as an exception instead, caught by
        # phase2_circuit_breakers.py's outer handler, which still halts (fail-closed either way).
        threshold = _cb._float(
            halt_dd_val,
            None,
            context="halt_drawdown_pct",
        )
        # halt_drawdown_pct is stored as negative (e.g. -20.0 = halt at 20% down).
        # dd is computed as a positive percentage drop from peak.
        halt_threshold = abs(threshold)
        return {
            "halted": dd >= halt_threshold,
            "reason": (
                f"Drawdown {dd:.2f}% >= {halt_threshold:.0f}%" if dd >= halt_threshold else f"Drawdown {dd:.2f}%"
            ),
            "value": round(dd, 2),
            "threshold": threshold,
        }

    def _check_drawdown_re_engagement(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """C2: Drawdown Re-engagement Protocol.

        After a drawdown halt, require conditions to resume:
        1. Portfolio recovered to within N% of peak (not at peak)
        2. Market shows Follow-Through Day signal (optional)
        3. At least N days have passed since halt
        """
        # Cash-flow-adjusted, same reasoning as _check_drawdown above. Also bound by
        # current_date for the same reason (see CRITICAL FIX comment in _check_drawdown).
        cur.execute(
            """
            SELECT MAX(adjusted_equity),
                   (SELECT adjusted_equity FROM algo_portfolio_snapshots
                    WHERE snapshot_date <= %s ORDER BY snapshot_date DESC LIMIT 1)
            FROM algo_portfolio_snapshots
            """,
            (current_date,),
        )
        row = cur.fetchone()
        if row is None or row[0] is None or row[1] is None:
            return {"halted": False, "reason": "No halt history"}

        # BUG FOUND 2026-08-10: bare float() here missed the NaN/Inf guard that this file's
        # own _cb._float() helper exists for (and that the sibling _check_drawdown, same
        # adjusted_equity source, already uses at line ~316) - `peak <= 0`/`cur_val <= 0`
        # never catch NaN (always False in Python), so a NaN would sail through and NaN would
        # then be silently written into `dd`. _cb._float(default=0.0) coerces NaN/Inf to 0.0,
        # which correctly falls into the existing "Invalid values" branch below.
        peak = _cb._float(row[0], default=0.0, context="drawdown re-engagement peak")
        cur_val = _cb._float(row[1], default=0.0, context="drawdown re-engagement current")
        if peak <= 0 or cur_val <= 0:
            return {"halted": False, "reason": "Invalid values"}

        dd = (peak - cur_val) / peak * 100.0

        # Gate on whether a drawdown halt has ever actually fired, not on whether the
        # CURRENT drawdown is still above halt_threshold_abs. The old gate made this
        # check redundant with _check_drawdown: the instant dd ticked back under the
        # halt line (e.g. 20.1% -> 19.9%), this returned "not halted" before ever
        # evaluating the tighter recovery/day/FTD protocol below - defeating the point
        # of a separate re-engagement guard.
        # Match on the actual drawdown check's own halted flag, not a substring search over
        # the whole details blob - every halt log's JSON always contains the literal key
        # "drawdown" (and "drawdown_re_engagement") in its `checks` dict regardless of which
        # check actually fired, so `details::text ILIKE '%drawdown%'` matched EVERY halt log
        # entry ever written, not just genuine drawdown-triggered ones. That meant an
        # unrelated halt (e.g. a VIX spike) reset "halt occurred Nd ago" back to 0 on every
        # occurrence, capable of extending this 5-day recovery lockout indefinitely as long
        # as anything else kept halting periodically - confirmed live 2026-07-20 (a real
        # drawdown halt fired at 11:59, recovered by 13:54, but 3 subsequent VIX-only halts
        # with drawdown.halted=false each re-matched the old query and kept resetting the
        # clock to "0d ago").
        # Excludes entries explicitly marked details->>'corrected'=true: a documented,
        # auditable correction (see algo_audit_log action_type
        # 'circuit_breaker_halt_correction' for the reasoning/evidence/commit reference)
        # applied when a halt's own recorded value is later proven to not reflect real
        # trading risk - e.g. computed by a since-fixed bug. The correction never rewrites
        # the original checks/value/reason fields, only adds a 'corrected' annotation, so
        # the halt remains fully visible in history; it's just excluded from gating
        # re-engagement, since that cooldown exists to protect against a genuine drawdown
        # recurring, not to penalize a measurement bug that has already been fixed.
        cur.execute("""
            SELECT created_at FROM algo_audit_log
            WHERE action_type = 'circuit_breaker_halt'
              AND (details->'checks'->'drawdown'->>'halted')::boolean IS TRUE
              AND NOT COALESCE((details->>'corrected')::boolean, false)
            ORDER BY created_at DESC LIMIT 1
            """)
        halt_row = cur.fetchone()
        if halt_row is None:
            return {"halted": False, "reason": "Not in drawdown halt"}

        halt_date = halt_row[0]
        halt_date_only = halt_date.date() if isinstance(halt_date, datetime) else halt_date
        # BUG FOUND 2026-09-01 (/goal session, risk-mgmt fringe-case sweep): raw calendar-day
        # subtraction, not trading-day-aware, unlike every other date-sensitive check in this
        # same file (see the MarketCalendar.is_trading_day calls elsewhere here) and the
        # repo-wide load-bearing rule ("Date math via MarketCalendar only"). For a SAFETY
        # recovery window this matters in the dangerous direction: calendar days pass FASTER
        # than trading days across a weekend/holiday, so a halt on a Thursday would count 5
        # calendar days elapsed by the following Tuesday (a real trading day span of only 3
        # sessions) - re-engaging the circuit breaker up to 2 sessions earlier than the
        # `re_engage_min_days` config value was actually meant to require. Switched to
        # MarketCalendar.trading_days_elapsed, matching this file's own convention elsewhere
        # and exit_engine.py's identical days_held calculation.
        from algo.infrastructure import MarketCalendar

        days_elapsed = MarketCalendar.trading_days_elapsed(halt_date_only, current_date)

        recovery_val = self._get_required_config("re_engage_recovery_pct", "in re-engagement recovery check")
        min_days_val = self._get_required_config("re_engage_min_days", "in re-engagement timing check")
        require_ftd_val = self._get_required_config("require_ftd_to_re_engage", "in re-engagement FTD check")
        recovery_threshold = float(recovery_val)
        min_days_elapsed = int(min_days_val)
        require_ftd = bool(require_ftd_val)

        recovery_pct = (peak - cur_val) / peak * 100.0  # Current distance from peak
        if recovery_pct > recovery_threshold:
            return {
                "halted": True,
                "reason": f"Drawdown {dd:.1f}%, need recovery to {recovery_threshold:.1f}% to resume (currently {recovery_pct:.1f}%)",
            }

        if days_elapsed < min_days_elapsed:
            return {
                "halted": True,
                "reason": f"Halt occurred {days_elapsed}d ago, need {min_days_elapsed}d to elapse before resume",
            }

        if require_ftd:
            # A Follow-Through Day is when SPY up 1.25%+ on higher volume after a pullback/correction;
            # simplified here to "market is in Stage 2". Uses the same NULL-skipping +
            # staleness-bounded lookup as CB6 (_resolve_current_market_stage) instead of a bare
            # "latest row" query - a bare query here previously misread a not-yet-computed
            # same-day NULL placeholder (e.g. before the day's market-exposure loader ran) as a
            # confirmed "market not in Stage 2", permanently blocking re-engagement that day even
            # though yesterday's stage (still valid) may have qualified.
            stage, _trend, halt_reason = self._resolve_current_market_stage(current_date, cur)
            if halt_reason is not None:
                return {"halted": True, "reason": halt_reason}
            if stage != 2:
                return {
                    "halted": True,
                    "reason": "Recovery conditions met, but market not in Stage 2 uptrend (waiting for Follow-Through Day)",
                }

        # All conditions met - re-engagement approved
        return {
            "halted": False,
            "reason": f"Re-engagement approved: recovered to {recovery_pct:.1f}%, {days_elapsed}d elapsed, market Stage 2",
        }

    def _check_min_reengagement_days(
        self,
        current_date: _date,
        cur: PsycopgCursor[Any],
        source_check_name: str,
        min_days_config_key: str,
    ) -> dict[str, Any]:
        """Shared minimum-elapsed-trading-days lockout, generalized from
        _check_drawdown_re_engagement's day-gate for breakers where a full
        recovery-pct/Follow-Through-Day protocol doesn't apply (VIX, daily/weekly loss,
        total open risk aren't "distance from peak" concepts). Without this, those
        breakers could trip and clear on consecutive check_all() calls the moment the
        underlying metric ticks back under threshold, even though the condition that
        caused the halt (e.g. an elevated-vol regime) hasn't actually resolved - a real
        flap risk drawdown was deliberately protected against but these four were not
        (audit finding, 2026-09-04 real-money-readiness push).

        Same audit-log matching convention as _check_drawdown_re_engagement: gate on the
        SOURCE check's own halted flag via its JSON key (not a substring/text search,
        which would match every halt log entry regardless of which check fired), and
        exclude details->>'corrected'=true entries for the same reason documented there.
        """
        cur.execute(
            """
            SELECT created_at FROM algo_audit_log
            WHERE action_type = 'circuit_breaker_halt'
              AND (details->'checks'->%s->>'halted')::boolean IS TRUE
              AND NOT COALESCE((details->>'corrected')::boolean, false)
            ORDER BY created_at DESC LIMIT 1
            """,
            (source_check_name,),
        )
        halt_row = cur.fetchone()
        if halt_row is None:
            return {"halted": False, "reason": f"Not in {source_check_name} halt"}

        halt_date = halt_row[0]
        halt_date_only = halt_date.date() if isinstance(halt_date, datetime) else halt_date

        from algo.infrastructure import MarketCalendar

        days_elapsed = MarketCalendar.trading_days_elapsed(halt_date_only, current_date)
        min_days_val = self._get_required_config(min_days_config_key, f"in {source_check_name} re-engagement check")
        min_days_elapsed = int(min_days_val)

        if days_elapsed < min_days_elapsed:
            return {
                "halted": True,
                "reason": f"{source_check_name} halt occurred {days_elapsed}d ago, need {min_days_elapsed}d to elapse before resume",
            }

        return {
            "halted": False,
            "reason": f"Re-engagement approved: {days_elapsed}d elapsed since last {source_check_name} halt",
        }

    def _check_vix_spike_re_engagement(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        return self._check_min_reengagement_days(current_date, cur, "vix_spike", "vix_spike_min_reengagement_days")

    def _check_daily_loss_re_engagement(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        return self._check_min_reengagement_days(current_date, cur, "daily_loss", "daily_loss_min_reengagement_days")

    def _check_weekly_loss_re_engagement(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        return self._check_min_reengagement_days(current_date, cur, "weekly_loss", "weekly_loss_min_reengagement_days")

    def _check_total_risk_re_engagement(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        return self._check_min_reengagement_days(current_date, cur, "total_risk", "total_risk_min_reengagement_days")

    def _check_daily_loss(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        # Cash-flow-adjusted, same reasoning as _check_drawdown above (migration 1134):
        # the precomputed daily_return_pct column is derived from raw total_portfolio_value
        # deltas, so a same-day capital withdrawal reads as an equivalent trading loss and
        # can false-trip this breaker exactly like the pre-1134 drawdown bug. Compute the
        # daily return from adjusted_equity deltas instead, mirroring _check_drawdown.
        cur.execute(
            "SELECT adjusted_equity FROM algo_portfolio_snapshots WHERE snapshot_date = %s",
            (current_date,),
        )
        today_row = cur.fetchone()
        if today_row is None or today_row[0] is None:
            return {"halted": False, "reason": "No today snapshot yet"}
        cur.execute(
            """
            SELECT adjusted_equity FROM algo_portfolio_snapshots
            WHERE snapshot_date < %s AND adjusted_equity IS NOT NULL
            ORDER BY snapshot_date DESC LIMIT 1
            """,
            (current_date,),
        )
        prev_row = cur.fetchone()
        if prev_row is None or prev_row[0] is None:
            return {"halted": False, "reason": "Insufficient history"}
        cur_val = _cb._float(today_row[0], None, context="daily_loss current")
        prev_val = _cb._float(prev_row[0], None, context="daily_loss previous")
        if cur_val is None or prev_val is None or prev_val <= 0:
            return {"halted": True, "reason": "Adjusted equity data invalid - fail-closed"}
        daily = (cur_val - prev_val) / prev_val * 100.0
        max_daily_val = self._get_required_config("max_daily_loss_pct", "in daily loss check")
        # _cb._float(val, default=None, ...) raises rather than returning None on invalid/NaN/Inf
        # input, so `threshold is None` below is unreachable (see matching note in
        # _check_drawdown above) - kept only because `threshold == 0.0` is a real, reachable
        # guard against a misconfigured zero threshold (max_daily_loss_pct=0 is a valid float
        # that would otherwise halt on any loss, however small).
        threshold = -_cb._float(
            max_daily_val,
            None,
            context="max_daily_loss_pct",
        )
        if threshold is None or threshold == 0.0:
            _cb.logger.error("CRITICAL: max_daily_loss_pct is invalid. Cannot enforce daily loss circuit breaker.")
            return {"halted": True, "reason": "CRITICAL: max_daily_loss_pct invalid"}
        return {
            "halted": daily <= threshold,
            "reason": (
                f"Daily loss {daily:.2f}% <= {threshold:.1f}%" if daily <= threshold else f"Daily {daily:+.2f}%"
            ),
            "value": round(daily, 2),
            "threshold": threshold,
        }

    def _check_weekly_loss(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """7-day return on portfolio (cash-flow-adjusted, see _check_daily_loss/_check_drawdown - migration 1134)."""
        week_ago = current_date - timedelta(days=7)
        cur.execute(
            """
            SELECT
                (SELECT adjusted_equity FROM algo_portfolio_snapshots WHERE snapshot_date <= %s AND adjusted_equity IS NOT NULL ORDER BY snapshot_date DESC LIMIT 1),
                (SELECT adjusted_equity FROM algo_portfolio_snapshots WHERE snapshot_date <= %s AND adjusted_equity IS NOT NULL ORDER BY snapshot_date DESC LIMIT 1)
            """,
            (current_date, week_ago),
        )
        row = cur.fetchone()
        if row is None or len(row) < 2 or row[0] is None or row[1] is None:
            return {"halted": False, "reason": "Insufficient history"}
        cur_val, week_ago_val = float(row[0]), float(row[1])
        # BUG FOUND 2026-08-10: `week_ago_val <= 0` never catches NaN/Inf (always False in
        # Python) - this function's own `threshold` check a few lines below already knows to
        # guard NaN explicitly (`threshold != threshold`), but that treatment was never applied
        # to cur_val/week_ago_val here. A NaN cur_val previously wasn't checked at all, and
        # would have produced a NaN `weekly` whose final `weekly <= threshold` comparison
        # silently evaluates to False - fail-open (not halted) for a genuinely invalid,
        # non-comparable portfolio value. Both must be finite for this check to be meaningful.
        if math.isnan(cur_val) or math.isinf(cur_val) or math.isnan(week_ago_val) or math.isinf(week_ago_val):
            _cb.logger.critical(
                f"CRITICAL: Portfolio value not finite (cur={cur_val}, week_ago={week_ago_val}) - "
                "cannot calculate weekly return"
            )
            return {"halted": True, "reason": "CRITICAL: Portfolio history data invalid"}
        if week_ago_val <= 0:
            _cb.logger.critical(
                f"CRITICAL: Week-ago portfolio value invalid ({week_ago_val}) - cannot calculate weekly return"
            )
            return {"halted": True, "reason": "CRITICAL: Portfolio history data invalid"}
        weekly = (cur_val - week_ago_val) / week_ago_val * 100.0
        max_weekly_val = self._get_required_config("max_weekly_loss_pct", "in weekly loss check")
        try:
            threshold = -float(max_weekly_val)
            if (
                threshold == 0 or (threshold != threshold) or threshold == float("inf") or threshold == float("-inf")
            ):  # NaN/Inf check
                raise ValueError(f"max_weekly_loss_pct invalid ({max_weekly_val})")
        except (ValueError, TypeError) as e:
            _cb.logger.critical(
                f"CRITICAL: max_weekly_loss_pct configuration invalid - cannot enforce weekly loss limit: {e}"
            )
            return {"halted": True, "reason": "CRITICAL: max_weekly_loss_pct configuration invalid"}
        return {
            "halted": weekly <= threshold,
            "reason": (
                f"Weekly {weekly:.2f}% <= {threshold:.1f}%" if weekly <= threshold else f"Weekly {weekly:+.2f}%"
            ),
            "value": round(weekly, 2),
            "threshold": threshold,
        }

    def _check_total_risk(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Sum of (entry - stop) * qty across open positions vs portfolio value."""
        cur.execute(
            "SELECT COUNT(*) FROM algo_positions WHERE status = %s AND current_stop_price IS NULL",
            (PositionStatus.OPEN.value,),
        )
        result = cur.fetchone()
        if not result:
            raise RuntimeError("Circuit breaker total_risk check: algo_positions query returned no rows")
        missing_stops_count = result[0]
        if missing_stops_count > 0:
            _cb.logger.critical(
                f"[TOTAL_RISK_CHECK] {missing_stops_count} open positions have NULL current_stop_price. "
                "Cannot calculate risk with missing current stops. Halting to prevent blind risk-taking."
            )
            return {
                "halted": True,
                "reason": f"{missing_stops_count} positions missing current stops - fail-closed halt",
            }

        cur.execute(
            """
            SELECT SUM(GREATEST(0, (t.entry_price - p.current_stop_price) * p.quantity)),
                   COUNT(*) as position_count
            FROM algo_positions p
            JOIN algo_trades t ON t.trade_id::text = ANY(p.trade_ids_arr::text[])
            WHERE p.status = %s
            """,
            (PositionStatus.OPEN.value,),
        )
        result = cur.fetchone()
        if result is None:
            _cb.logger.error(
                "Position count query failed (no result). Cannot determine position count. "
                "Position monitoring unsafe - halting to prevent blind trading."
            )
            raise RuntimeError(
                "Cannot determine position count: query failed. Position monitoring unsafe. "
                "Zero positions must be explicitly confirmed, not defaulted."
            )
        total_open_risk_raw = result[0]
        position_count = result[1]

        # CRITICAL: the SUM/COUNT above is an INNER JOIN against algo_trades via
        # trade_ids_arr - any open position whose trade_ids_arr doesn't resolve to a real
        # algo_trades row (empty array, stale/orphaned ids) silently drops out of BOTH the
        # SUM and this COUNT, understating total open risk with no error raised. Verify
        # against a direct count of open positions and fail-closed on any mismatch, since a
        # position risk calculation silently ignores is exactly the "blind risk-taking" this
        # check exists to prevent.
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = %s", (PositionStatus.OPEN.value,))
        actual_open_row = cur.fetchone()
        actual_open_count = actual_open_row[0] if actual_open_row else None
        if actual_open_count is None:
            raise RuntimeError("Cannot verify open position count - query failed. Position monitoring unsafe.")
        if actual_open_count != position_count:
            _cb.logger.critical(
                f"[TOTAL_RISK_CHECK] {actual_open_count} open positions exist but risk calculation only "
                f"matched {position_count} via trade_ids_arr join - {actual_open_count - position_count} "
                "position(s) have no resolvable algo_trades row and were silently excluded from total risk. "
                "Halting to prevent blind risk-taking."
            )
            return {
                "halted": True,
                "reason": (
                    f"{actual_open_count - position_count} open position(s) missing from risk calculation "
                    "(orphaned trade_ids_arr) - fail-closed halt"
                ),
            }

        # If there are open positions but SUM returns NULL, that's data corruption
        if position_count > 0 and total_open_risk_raw is None:
            _cb.logger.critical(
                f"[TOTAL_RISK_CHECK] {position_count} open positions exist but risk calculation returned NULL. "
                "Missing or corrupted entry_price or stop_price data detected. Halting to prevent blind trading."
            )
            return {
                "halted": True,
                "reason": f"Risk calculation failed on {position_count} positions - data corruption",
            }

        # If no positions, risk is legitimately 0; if positions exist and calculation succeeded, use result
        total_open_risk = _cb._float(total_open_risk_raw, 0.0, context="total_open_risk")
        if total_open_risk is None:
            _cb.logger.critical("Cannot calculate total open risk - risk calculation failed")
            return {"halted": True, "reason": "Risk calculation failed - fail-closed"}

        # CRITICAL FIX: bound by current_date - see _check_drawdown for why an unbounded
        # "latest snapshot" query is unsafe (stray future-dated rows outrank the real one).
        cur.execute(
            "SELECT total_portfolio_value FROM algo_portfolio_snapshots "
            "WHERE snapshot_date <= %s ORDER BY snapshot_date DESC LIMIT 1",
            (current_date,),
        )
        row = cur.fetchone()
        if row is None or row[0] is None:
            # First run (no portfolio snapshots yet) - skip risk check but log
            _cb.logger.info("[TOTAL_RISK_CHECK] Skipping (no portfolio snapshot yet; expected on first run)")
            return {"halted": False, "reason": "No portfolio snapshot (first run?)"}

        portfolio = _cb._float(row[0], None, context="portfolio_value")
        # CRITICAL: Portfolio value missing/invalid -> risk calculation impossible.
        # Fail-closed: cannot assess total risk without portfolio value.
        if portfolio is None or portfolio <= 0:
            _cb.logger.critical(
                f"[TOTAL_RISK_CHECK] Portfolio value invalid ({portfolio}) - cannot calculate risk. "
                "Halting trading to prevent blind risk-taking."
            )
            return {
                "halted": True,
                "reason": f"Portfolio value invalid ({portfolio}) - risk calculation impossible. Fail-closed halt.",
            }

        # CRITICAL FIX: Ensure both operands are float before arithmetic. Database SUM may return
        # psycopg2 Decimal type; explicitly convert to avoid "Decimal * float" TypeError.
        # NOTE: total_open_risk and portfolio are guaranteed non-None at this point:
        # - total_open_risk: checked at line 700, returns if None
        # - portfolio: checked at line 714, returns if None or <= 0
        # No fallback defaults allowed (fail-fast accuracy principle)
        if total_open_risk is None:
            raise RuntimeError(
                "[CIRCUIT_BREAKER CRITICAL] total_open_risk is None after earlier validation check. "
                "This indicates a logic error in _check_total_risk. Cannot proceed with risk calculation."
            )
        if portfolio is None:
            raise RuntimeError(
                "[CIRCUIT_BREAKER CRITICAL] portfolio is None after earlier validation check. "
                "This indicates a logic error in _check_total_risk. Cannot proceed with risk calculation."
            )
        total_open_risk_f = float(total_open_risk)
        portfolio_f = float(portfolio)
        risk_pct = total_open_risk_f / portfolio_f * 100.0
        max_risk_val = self._get_required_config("max_total_risk_pct", "in total risk check")
        threshold = _cb._float(
            max_risk_val,
            None,
            context="max_total_risk_pct",
        )
        return {
            "halted": risk_pct >= threshold,
            "reason": (
                f"Total open risk {risk_pct:.2f}% >= {threshold:.0f}%"
                if risk_pct >= threshold
                else f"Risk {risk_pct:.2f}%"
            ),
            "value": round(risk_pct, 2),
            "threshold": threshold,
        }

    def _check_daily_profit_cap(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Warn (don't halt) if daily P&L exceeds profit target; can skip new entries.

        Cash-flow-adjusted (migration 1134): raw daily_return_pct would read a same-day
        deposit as a false "profit cap exceeded" (spuriously skipping new entries) or a
        withdrawal as masking a real profit cap breach.
        """
        cur.execute(
            "SELECT adjusted_equity FROM algo_portfolio_snapshots WHERE snapshot_date = %s",
            (current_date,),
        )
        today_row = cur.fetchone()
        if not today_row or today_row[0] is None:
            return {"halted": False, "reason": "No today snapshot yet"}
        cur.execute(
            """
            SELECT adjusted_equity FROM algo_portfolio_snapshots
            WHERE snapshot_date < %s AND adjusted_equity IS NOT NULL
            ORDER BY snapshot_date DESC LIMIT 1
            """,
            (current_date,),
        )
        prev_row = cur.fetchone()
        if not prev_row or prev_row[0] is None:
            return {"halted": False, "reason": "Insufficient history"}
        prev_val = float(prev_row[0])
        today_val = float(today_row[0])
        # BUG FOUND 2026-08-10: `prev_val <= 0` never catches NaN/Inf (always False in
        # Python), and today_val had no finiteness check at all - either would silently
        # produce a NaN `daily`, whose `daily >= threshold` comparison below always
        # evaluates False, masking a real profit-cap breach (this check's whole purpose).
        if (
            math.isnan(prev_val)
            or math.isinf(prev_val)
            or math.isnan(today_val)
            or math.isinf(today_val)
            or prev_val <= 0
        ):
            return {"halted": False, "reason": "Insufficient history"}
        daily = (today_val - prev_val) / prev_val * 100.0
        daily_profit_val = self._get_required_config("daily_profit_cap_pct", "in daily profit cap check")
        threshold = float(daily_profit_val)
        # This check is a SOFT warning, not a halt - it's logged but doesn't block trading
        # Orchestrator uses this to skip NEW entries only, not to exit existing positions
        return {
            "halted": False,
            "reason": f"Daily profit {daily:+.2f}% vs cap {threshold:.1f}%",
            "value": round(daily, 2),
            "threshold": threshold,
            "exceed_profit_cap": daily >= threshold,
        }
