"""Algo dashboard handler: /api/algo/circuit-breakers.

Split 2026-09-05 out of the original 2160-line algo_handlers/dashboard.py (see
positions.py's module docstring for the full split rationale). This module holds only
`_get_circuit_breakers`. Pure move, no logic changed.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.sql
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    error_response,
    handle_db_error,
    json_response,
    safe_dict_convert,
    validate_api_response,
)

from utils.data_queries import (
    get_trade_win_loss_stats,
)
from utils.validation import format_decimal_string

logger = logging.getLogger(__name__)


@db_route_handler("fetch circuit breakers")
@validate_api_response("cb")
def _get_circuit_breakers(cur: cursor) -> Any:  # noqa: C901
    try:
        today = date.today()
        breakers = []

        # CRITICAL: Validate required circuit breaker configuration tables exist
        required_tables = [
            "algo_portfolio_snapshots",
            "algo_trades",
            "market_health_daily",
            "algo_positions",
        ]
        missing_tables = []
        for table in required_tables:
            try:
                from utils.validation import assert_safe_table

                table_safe = assert_safe_table(table)
                cur.execute(psycopg2.sql.SQL("SELECT 1 FROM {} LIMIT 1").format(psycopg2.sql.Identifier(table_safe)))
            except psycopg2.errors.UndefinedTable:
                missing_tables.append(table)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"Unexpected error checking table {table}: {type(e).__name__}: {e}")
                missing_tables.append(table)

        if missing_tables:
            logger.error(f"ALERT: Circuit breaker CRITICAL config tables missing: {missing_tables}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Data unavailable",
                    },
                    "errorType": "missing_critical_tables",
                    "message": (
                        f"Circuit breaker configuration incomplete: missing tables {missing_tables}. "
                        "Trading is disabled until data is available."
                    ),
                    "_error": (
                        f"Circuit breaker configuration incomplete: missing tables {missing_tables}. "
                        "Trading is disabled until data is available."
                    ),
                },
            )

        # Fetch pre-computed circuit breaker metrics from database
        # CRITICAL: Fail-fast if metrics are unavailable (don't default to 0 for trading safety)
        cbm_data = {}
        computed_at: datetime | None = None
        data_age_seconds: int | None = None
        data_stale: bool = False
        try:
            cur.execute(
                "SELECT portfolio_drawdown_pct, daily_loss_pct, weekly_loss_pct, open_risk_pct, "
                "consecutive_losses, vix_level, market_stage, check_date FROM circuit_breaker_status "
                "ORDER BY check_date DESC LIMIT 1"
            )
            cbm_row = cur.fetchone()
            if not cbm_row:
                logger.warning("Circuit breaker metrics unavailable (circuit_breaker_status table empty)")
                return json_response(
                    503,
                    {
                        "breakers": [],
                        "any_triggered": False,
                        "triggered_count": 0,
                        "data_freshness": {
                            "data_age_days": None,
                            "is_stale": True,
                            "warning": "Circuit breaker data unavailable",
                        },
                        "errorType": "missing_circuit_breaker_data",
                        "message": "Circuit breaker metrics unavailable. Trading disabled until data is available.",
                        "_error": "Circuit breaker metrics unavailable. Trading disabled until data is available.",
                    },
                )
            cbm_row = safe_dict_convert(cbm_row)

            # Extract check_date timestamp and calculate data age
            check_date = cbm_row["check_date"]
            if check_date is not None:
                from datetime import datetime as dt
                from datetime import timedelta
                from zoneinfo import ZoneInfo

                et = ZoneInfo("America/New_York")
                computed_at = dt.combine(check_date, dt.min.time()).replace(tzinfo=et)
                now_et = datetime.now(et)
                data_age_seconds = int((now_et - computed_at).total_seconds())

                # circuit_breaker_status rows are written by each orchestrator run with
                # check_date = the run's trading date (first run of the day is 9:30 AM ET).
                # The previous trading day's row therefore remains the freshest possible
                # data until today's first run completes. Staleness is "check_date is older
                # than the most recent trading day whose row should exist by now" - NOT
                # wall-clock age anchored at midnight of check_date, which falsely flagged
                # Trading day-aware freshness check (uses MarketCalendar to skip holidays correctly).
                # On trading days: expect today's data
                # On non-trading days (weekends/holidays): expect previous trading day's data
                from algo.infrastructure import MarketCalendar

                expected_date = now_et.date()
                if MarketCalendar.is_trading_day(expected_date):
                    # Today is a trading day: require today's data (or previous trading day if pre-market)
                    if now_et.hour < 10:  # Pre-market: previous trading day's data is acceptable
                        expected_date -= timedelta(days=1)
                        for _ in range(10):
                            if MarketCalendar.is_trading_day(expected_date):
                                break
                            expected_date -= timedelta(days=1)
                else:
                    # Today is not a trading day (weekend/holiday): use most recent trading day's data
                    expected_date -= timedelta(days=1)
                    for _ in range(10):
                        if MarketCalendar.is_trading_day(expected_date):
                            break
                        expected_date -= timedelta(days=1)

                data_stale = check_date < expected_date

                if data_stale:
                    logger.critical(
                        f"[CIRCUIT_BREAKER_STALE] check_date {check_date} older than expected "
                        f"trading day {expected_date}. Trading halted. Evaluated at {now_et.isoformat()} "
                        f"(latest circuit_breaker_status row is dated {check_date}, not stale wall-clock)"
                    )
                    return json_response(
                        503,
                        {
                            "breakers": [],
                            "any_triggered": True,  # Fail-closed: treat stale data as triggered
                            "triggered_count": 0,
                            "data_freshness": {
                                "data_age_seconds": data_age_seconds,
                                "is_stale": True,
                                "warning": (
                                    f"Circuit breaker data stale ({data_age_seconds}s old). "
                                    "Cannot proceed with risk assessment. Trading disabled."
                                ),
                            },
                            "errorType": "stale_circuit_breaker_data",
                            "message": (
                                f"Circuit breaker data is for {check_date} but expected {expected_date}. "
                                "All trading halted until fresh metrics available."
                            ),
                            "_error": "Circuit breaker data stale. Trading disabled.",
                        },
                    )

            # Validate critical fields exist and are non-null (fail-closed)
            critical_fields = [
                "portfolio_drawdown_pct",
                "daily_loss_pct",
                "weekly_loss_pct",
                "open_risk_pct",
                "consecutive_losses",
                "market_stage",
                "vix_level",
            ]
            missing = [f for f in critical_fields if cbm_row[f] is None]
            if missing:
                logger.error(f"Circuit breaker critical fields missing: {missing}")
                return json_response(
                    503,
                    {
                        "breakers": [],
                        "any_triggered": False,
                        "triggered_count": 0,
                        "data_freshness": {
                            "data_age_days": None,
                            "is_stale": True,
                            "warning": "Circuit breaker data incomplete",
                        },
                        "errorType": "incomplete_circuit_breaker_data",
                        "message": f"Circuit breaker data incomplete (missing {', '.join(missing)}). Trading disabled.",
                        "_error": "Circuit breaker data incomplete. Trading disabled.",
                    },
                )

            cbm_data = {
                "drawdown": float(cbm_row["portfolio_drawdown_pct"]),
                "daily_loss": float(cbm_row["daily_loss_pct"]),
                "weekly_loss": float(cbm_row["weekly_loss_pct"]),
                "total_risk": float(cbm_row["open_risk_pct"]),
                "consecutive_losses": int(cbm_row["consecutive_losses"]),
                "vix_level": float(cbm_row["vix_level"]),  # VIX is optional
                "market_stage": int(cbm_row["market_stage"]),
            }
        except (
            psycopg2.errors.UndefinedTable,
            psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError,
            psycopg2.DatabaseError,
            Exception,
        ) as e:
            code, error_type, message = handle_db_error(e, "fetch circuit breaker metrics")
            return error_response(code, error_type, message)

        # CRITICAL: All thresholds below must come from algo_config (the same source
        # algo/risk/circuit_breaker.py's _get_required_config reads at halt time), not
        # hardcoded literals. FIXED (commit 7505f72b1): this panel used to hardcode
        # threshold_dd=20.0 while the real configured halt_drawdown_pct was -10 (halt at
        # 10% down) - a live 12-19% drawdown would already have halted real trading while
        # this panel kept showing "not triggered" - and CB2/CB3/CB4/CB5/CB7's thresholds
        # (threshold_dl, threshold_cl, threshold_vix, threshold_wl, threshold_risk) were
        # the same bug, hardcoded independent of algo_config. All six are now fetched live
        # from algo_config below, so any operator tuning max_daily_loss_pct etc. (their
        # whole purpose) stays in sync with this panel and the real halt gate. Same bug
        # class as market.py's _get_data_status (commit 2a5a41c78) and
        # loaders/compute_circuit_breakers.py (commit bca23264d) - if a similar panel is
        # found hardcoding a risk/halt threshold instead of reading algo_config, it's the
        # same class of bug and should be fixed the same way.
        try:
            cur.execute(
                """
                SELECT key, value FROM algo_config
                WHERE key IN ('halt_drawdown_pct', 'max_daily_loss_pct', 'max_consecutive_losses',
                              'vix_max_threshold', 'max_weekly_loss_pct', 'max_total_risk_pct')
                """
            )
            cb_cfg = {row[0]: row[1] for row in cur.fetchall()}
            required_cb_cfg_keys = (
                "halt_drawdown_pct",
                "max_daily_loss_pct",
                "max_consecutive_losses",
                "vix_max_threshold",
                "max_weekly_loss_pct",
                "max_total_risk_pct",
            )
            missing_cb_cfg_keys = [k for k in required_cb_cfg_keys if k not in cb_cfg or cb_cfg[k] is None]
            if missing_cb_cfg_keys:
                raise ValueError(f"algo_config missing required circuit breaker keys: {missing_cb_cfg_keys}")
            threshold_dd = abs(float(cb_cfg["halt_drawdown_pct"]))
            threshold_dl = float(cb_cfg["max_daily_loss_pct"])
            threshold_cl = int(cb_cfg["max_consecutive_losses"])
            threshold_vix = float(cb_cfg["vix_max_threshold"])
            threshold_wl = float(cb_cfg["max_weekly_loss_pct"])
            threshold_risk = float(cb_cfg["max_total_risk_pct"])
        except (psycopg2.errors.UndefinedTable, psycopg2.OperationalError, psycopg2.DatabaseError, ValueError) as e:
            code, error_type, message = handle_db_error(e, "fetch circuit breaker thresholds")
            return error_response(code, error_type, message)

        # CB1: Portfolio drawdown (from pre-computed metrics)
        try:
            dd = cbm_data["drawdown"]
            breakers.append(
                {
                    "id": "drawdown",
                    "label": "Portfolio Drawdown",
                    "triggered": dd >= threshold_dd,
                    "current": dd,
                    "threshold": threshold_dd,
                    "unit": "%",
                    "description": f"Halt when drawdown from peak ≥ {threshold_dd:.0f}%",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB1 (drawdown) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (drawdown): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB2: Daily loss (from pre-computed metrics)
        try:
            daily_loss = cbm_data["daily_loss"]
            breakers.append(
                {
                    "id": "daily_loss",
                    "label": "Daily Loss",
                    "triggered": daily_loss >= threshold_dl,
                    "current": daily_loss,
                    "threshold": threshold_dl,
                    "unit": "%",
                    "description": f"Halt when today's loss ≥ {threshold_dl:.0f}%",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB2 (daily_loss) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (daily_loss): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB3: Consecutive losses (from pre-computed metrics)
        try:
            streak = cbm_data["consecutive_losses"]
            breakers.append(
                {
                    "id": "consecutive_losses",
                    "label": "Consecutive Losses",
                    "triggered": streak >= threshold_cl,
                    "current": streak,
                    "threshold": threshold_cl,
                    "unit": "",
                    "description": f"Halt after {threshold_cl} consecutive losing trades",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB3 (consecutive_losses) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (consecutive_losses): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB4: VIX spike (from pre-computed metrics)
        # CRITICAL: Fail-fast if VIX unavailable (market volatility essential for trading risk assessment)
        try:
            if not cbm_data:
                raise ValueError("Circuit breaker metrics data missing")
            vix = cbm_data["vix_level"]
            if vix is None:
                logger.error(
                    "[CB4 CRITICAL] VIX level is NULL. Cannot assess market volatility/fear. Trading disabled."
                )
                return json_response(
                    503,
                    {
                        "breakers": [],
                        "any_triggered": False,
                        "triggered_count": 0,
                        "data_freshness": {
                            "data_age_days": None,
                            "is_stale": True,
                            "warning": "Circuit breaker data incomplete",
                        },
                        "errorType": "missing_vix_data",
                        "message": "VIX data unavailable. Market volatility metrics required for risk assessment. "
                        "Trading disabled.",
                        "_error": "VIX data unavailable. Trading disabled.",
                    },
                )
            breakers.append(
                {
                    "id": "vix_spike",
                    "label": "VIX Spike",
                    "triggered": vix >= threshold_vix,
                    "current": vix,
                    "threshold": threshold_vix,
                    "unit": "",
                    "description": f"Halt when VIX ≥ {threshold_vix:.0f} (extreme fear)",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB4 (vix_spike) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "vix_computation_error",
                    "message": f"VIX computation error: {e!s}. Market volatility data unavailable.",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB5: Weekly portfolio loss (from pre-computed metrics)
        try:
            weekly_loss = cbm_data["weekly_loss"]
            breakers.append(
                {
                    "id": "weekly_loss",
                    "label": "Weekly Loss",
                    "triggered": weekly_loss >= threshold_wl,
                    "current": weekly_loss,
                    "threshold": threshold_wl,
                    "unit": "%",
                    "description": f"Halt when 7-day loss ≥ {threshold_wl:.0f}%",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB5 (weekly_loss) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (weekly_loss): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB6: Market stage break (Stage 4 = downtrend) (from pre-computed metrics)
        try:
            stage = cbm_data["market_stage"]
            breakers.append(
                {
                    "id": "market_stage",
                    "label": "Market Stage",
                    "triggered": stage == 4,
                    "current": stage,
                    "threshold": 4,
                    "unit": "",
                    "description": "Halt when market enters Stage 4 (confirmed downtrend)",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB6 (market_stage) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (market_stage): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB7: Total open risk (from pre-computed metrics)
        try:
            risk_pct = cbm_data["total_risk"]
            breakers.append(
                {
                    "id": "total_risk",
                    "label": "Total Open Risk",
                    "triggered": risk_pct >= threshold_risk,
                    "current": risk_pct,
                    "threshold": threshold_risk,
                    "unit": "%",
                    "description": f"Halt when total open risk ≥ {threshold_risk:.0f}% of portfolio",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB7 (total_risk) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (total_risk): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB8: Intraday market health (SPY down >2% yesterday)
        # CRITICAL: Fail-fast if SPY price data missing (market health essential for trading)
        try:
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
                logger.error(
                    "[CB8 CRITICAL] SPY price history insufficient (%d prices, need 2). "
                    "Cannot assess market health for trading decisions. Trading disabled.",
                    len(prices),
                )
                return json_response(
                    503,
                    {
                        "breakers": [],
                        "any_triggered": False,
                        "triggered_count": 0,
                        "data_freshness": {
                            "data_age_days": None,
                            "is_stale": True,
                            "warning": "Circuit breaker data incomplete",
                        },
                        "errorType": "missing_spy_price_data",
                        "message": "SPY price data insufficient. Market health assessment required for trading. "
                        "Trading disabled.",
                        "_error": "SPY price data unavailable. Trading disabled.",
                    },
                )
            latest = float(prices[0][0])
            prior = float(prices[1][0])
            if not (latest > 0 and prior > 0):
                raise ValueError(f"Invalid SPY prices: latest={latest}, prior={prior}")
            market_change = (latest - prior) / prior * 100
            threshold_mc = -2.0
            breakers.append(
                {
                    "id": "intraday_health",
                    "label": "Prior-Day Market Health",
                    "triggered": market_change <= threshold_mc,
                    "current": round(market_change, 2),
                    "threshold": threshold_mc,
                    "unit": "%",
                    "description": f"Halt if SPY dropped >{abs(threshold_mc):.0f}% yesterday (await stability)",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"CB8 (intraday_health) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "market_health_computation_error",
                    "message": f"SPY price computation error: {e!s}. Market health unavailable.",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB9: Win rate floor
        try:
            # Get win/loss stats from centralized data query (single source of truth)
            wr_stats = get_trade_win_loss_stats(cur, limit=30)
            # Fail-fast: Check for missing data explicitly. None means no trades (insufficient data),
            # not "zero wins". Do not convert to 0 (silent fallback).
            wins = wr_stats["wins"]
            losses = wr_stats["losses"]
            total = wr_stats["total"]
            win_rate = None
            threshold_wr = 40.0

            # Only compute win_rate if we have actual data (all values non-None)
            decisive = None
            if total is not None and total > 0 and wins is not None and losses is not None:
                decisive = wins + losses
                if decisive > 0:
                    win_rate = wins / decisive * 100

            if win_rate is not None and total is not None and total > 0 and decisive is not None and decisive >= 10:
                breakers.append(
                    {
                        "id": "win_rate",
                        "label": "Win Rate Floor",
                        "triggered": win_rate < threshold_wr,
                        "current": round(win_rate, 1),
                        "threshold": threshold_wr,
                        "unit": "%",
                        "description": f"Halt if win rate drops below {threshold_wr:.0f}% (last 30 closed)",
                    }
                )
            else:
                breakers.append(
                    {
                        "id": "win_rate",
                        "label": "Win Rate Floor",
                        "triggered": False,
                        "current": None,
                        "threshold": threshold_wr,
                        "unit": "%",
                        "description": "Insufficient trades to calculate win rate",
                    }
                )
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"CB9 (win_rate) computation failed: {type(e).__name__}: {e}")
            breakers.append(
                {
                    "id": "win_rate",
                    "label": "Win Rate Floor",
                    "triggered": False,
                    "current": None,
                    "threshold": 40,
                    "unit": "%",
                    "description": "Insufficient closed trades (need 10+)",
                }
            )

        any_halted = any(b["triggered"] for b in breakers)
        triggered_count = sum(1 for b in breakers if b["triggered"])
        freshness = check_data_freshness(cur, "algo_portfolio_snapshots", "snapshot_date", warning_days=1)

        # Enrich all breakers with data staleness information
        # CRITICAL: Include computed_at age and staleness flag for frontend to detect stale VIX/market_stage
        # FIX: Add data_unavailable flag when data_age_seconds is null (computation failed)
        for breaker in breakers:
            # Add staleness metadata to each breaker
            breaker["data_age_seconds"] = data_age_seconds
            breaker["data_stale"] = data_stale

            # Add explicit data_unavailable flag when age couldn't be computed
            if data_age_seconds is None:
                breaker["data_unavailable"] = True
                breaker["staleness_warning"] = "Circuit breaker computation date unavailable - cannot assess data age"
            elif data_stale:
                breaker["data_unavailable"] = False
                breaker["staleness_warning"] = (
                    f"Data is {data_age_seconds}s old (>{3600}s threshold). "
                    "Consider this breaker unreliable for trading decisions."
                )
            else:
                breaker["data_unavailable"] = False
                breaker["staleness_warning"] = None

            # Format decimal values for consistent API response
            if breaker["unit"] == "%":
                breaker["current"] = format_decimal_string(breaker["current"], precision=2, allow_none=True)
                breaker["threshold"] = format_decimal_string(breaker["threshold"], precision=2, allow_none=False)
            elif breaker["unit"] == "" and breaker["id"] == "vix_spike":
                breaker["current"] = format_decimal_string(breaker["current"], precision=2, allow_none=True)
                breaker["threshold"] = format_decimal_string(breaker["threshold"], precision=2, allow_none=False)

        # Enhance freshness metadata with circuit breaker-specific staleness data
        cb_freshness = freshness.copy() if freshness else {}
        cb_freshness["circuit_breaker_data_age_seconds"] = data_age_seconds
        cb_freshness["circuit_breaker_computed_at"] = computed_at.isoformat() if computed_at else None

        cb_response = {
            "breakers": breakers,
            "any_triggered": any_halted,
            "triggered_count": triggered_count,
            "data_freshness": cb_freshness,
        }

        return json_response(200, cb_response)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch circuit breakers")
        return error_response(code, error_type, message)
