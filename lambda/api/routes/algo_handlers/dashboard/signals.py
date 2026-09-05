"""Algo dashboard handler: /api/algo/signals.

Split 2026-09-05 out of the original 2160-line algo_handlers/dashboard.py (see
positions.py's module docstring for the full split rationale). This module holds only
`_get_dashboard_signals`. Pure move, no logic changed.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    error_response,
    handle_db_error,
    json_response,
    safe_dict_convert,
    safe_json_serialize,
    validate_api_response,
)

logger = logging.getLogger(__name__)


@db_route_handler("fetch dashboard signals")
@validate_api_response("sig")
def _get_dashboard_signals(cur: cursor) -> Any:
    """Get dashboard signal data - the Pine-matched technical scan, with the algo's decision
    on each signal overlaid.

    REWRITTEN 2026-08-20 (goal: dashboard signal-source confusion): previously sourced its
    entire roster from algo_signals (the orchestrator Phase 8 curated subset the algo actually
    considered for capital allocation - ~15-75/day), while lambda/api/routes/signals.py's
    /api/signals/stocks (backing the web Trading Signals page) sourced from buy_sell_daily
    (the full Pine-matched buy_signal_generator.py scan - ~130+/day, live-confirmed 134 BUY
    signals on 2026-08-19). Both are legitimate concepts, but nothing distinguished them for a
    viewer - the CLI dashboard's "ALGO SIGNALS" panel and the web page's "Trading Signals" page
    showed different-sized, mostly non-overlapping rosters with no indication one was a subset
    of the other, which reads as the data being wrong/inconsistent rather than "the algo only
    acts on a fraction of what Pine flags". Now sources the base roster from buy_sell_daily
    directly (same universe, same numbers as the web page - the actual Pine output) and LEFT
    JOINs algo_signals only to *annotate* which of those Pine signals the algo picked up as a
    candidate and what happened to it (executed/rejected/not selected at all, via
    execution_status - NULL means Pine flagged it but the algo never considered it). One
    canonical signal list instead of two.

    Queries buy_sell_daily (populated daily by Phase 7 / algo/signals/buy_signal_generator.py,
    the clean-room Pine-matched implementation - see tests/unit/pine_reference_impl.py's
    cross-check test) for the day's BUY roster, grade distribution, near-miss signals, and
    7-day trend, enriched with market stage from trend_template_data and RS percentile from
    stock_scores.
    """
    try:
        cur.execute("SET LOCAL statement_timeout = '20000ms'")

        from utils.market_symbols_config import MarketSymbolsConfig

        buy_sell_filter = MarketSymbolsConfig.buy_sell_only_where_clause("b")

        cur.execute("SELECT MAX(date) FROM buy_sell_daily")
        latest_row = cur.fetchone()
        latest_date = latest_row[0] if latest_row else None

        if latest_date is None:
            # No signals available - return empty response instead of error
            logger.info("[DASHBOARD SIGNALS] buy_sell_daily is empty")
            sig_response: dict[str, Any] = {
                "n": 0,
                "total": 0,
                "date": None,
                "buy_sigs": [],
                "near": [],
                "top_a": [],
                "grades": {"a": 0, "b": 0, "c": 0, "d": 0, "total": 0},
                "trend": [],
                "data_freshness": {"data_age_days": None, "is_stale": False, "max_date": None, "warning": None},
            }
            # Ensure empty response is also JSON-serializable
            sig_response = safe_json_serialize(sig_response)
        else:
            cur.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM buy_sell_daily b
                WHERE b.signal = 'BUY' AND b.date = %s
                {buy_sell_filter}
                """,
                (latest_date,),
            )
            total_row = cur.fetchone()
            total_n = int(total_row[0]) if total_row and total_row[0] is not None else 0

            # Full BUY roster for the latest date, straight from buy_sell_daily (the Pine-
            # matched source) - LEFT JOINed to algo_signals so each row can be annotated with
            # what the algo decided to do about it (execution_status/rejection_reason both NULL
            # if the algo never picked this signal up as a candidate at all, distinct from
            # 'rejected' - the algo considered it and passed).
            #
            # RS% FIX (2026-08-03, preserved from the prior algo_signals-based query): join
            # stock_scores.rs_percentile directly rather than relying on buy_sell_daily's own
            # rs_rating copy, which is timing-fragile (backfilled by a separate sync step that
            # can run before or after the day's buy_sell_daily insert).
            #
            # ALGO OVERLAY JOIN: symbol-only (+ recent window), NOT symbol+date. Live-checked
            # 2026-08-20: algo_signals.signal_date is stamped with the orchestrator's run_date
            # (see phase8_entry_execution.py::_persist_signals), which is NOT the same date as
            # the buy_sell_daily row that qualified the symbol as a candidate - e.g. JLL and
            # HALO were both execution_status='executed' on signal_date=2026-08-19, but their
            # only buy_sell_daily BUY row on file is from 2026-06-26 and 2026-06-25
            # respectively (54-55 days earlier). Joining on an exact date match (as first
            # written) found zero matches for any of that day's 23 algo_signals rows - the
            # overlay was silently empty. A separate concern (worth its own investigation: why
            # Phase 7's candidate query, which filters buy_sell_daily to a ~1-2 trading day
            # lookback, is producing candidates for symbols whose only on-file BUY row is
            # months old) - not fixed here, this join just needs to surface whatever the algo
            # actually did with this symbol recently regardless of which exact date lines up.
            #
            # Capped at 40 for terminal readability - the web Trading Signals page has no cap
            # and is the place to browse the full roster - highest-quality first.
            cur.execute(
                f"""
                SELECT
                    b.symbol, b.signal_quality_score,
                    cp.sector, cp.industry, b.entry_price,
                    b.date::text as signal_date,
                    b.close, b.buylevel, b.stoplevel,
                    b.buy_zone_start, b.buy_zone_end, b.pivot_price,
                    b.initial_stop, b.trailing_stop,
                    b.profit_target_8pct, b.profit_target_20pct, b.profit_target_25pct,
                    b.exit_trigger_1_price, b.exit_trigger_2_price,
                    b.rsi, b.adx, b.atr, b.volume_surge_pct, b.risk_reward_ratio,
                    b.base_type, b.base_length_days,
                    CASE t.weinstein_stage
                        WHEN 1 THEN 'Stage 1'
                        WHEN 2 THEN 'Stage 2 - Markup'
                        WHEN 3 THEN 'Stage 3 - Topping'
                        WHEN 4 THEN 'Stage 4'
                    END AS market_stage,
                    t.weinstein_stage AS stage_number,
                    ss.rs_percentile,
                    s.execution_status, s.rejection_reason
                FROM buy_sell_daily b
                LEFT JOIN company_profile cp ON cp.symbol = b.symbol
                LEFT JOIN trend_template_data t ON t.symbol = b.symbol AND t.date = b.date
                LEFT JOIN stock_scores ss ON ss.symbol = b.symbol
                LEFT JOIN LATERAL (
                    SELECT execution_status, rejection_reason
                    FROM algo_signals
                    WHERE symbol = b.symbol AND signal_date >= %s - 7
                    ORDER BY signal_date DESC
                    LIMIT 1
                ) s ON TRUE
                WHERE b.signal = 'BUY' AND b.date = %s
                {buy_sell_filter}
                ORDER BY b.signal_quality_score DESC NULLS LAST, b.symbol ASC
                LIMIT 40
                """,
                (latest_date, latest_date),
            )
            buy_sigs_rows = cur.fetchall()
            buy_sigs = [safe_json_serialize(safe_dict_convert(row)) for row in buy_sigs_rows]

            # CRITICAL AUDIT: Track NULL signal_quality_score (COALESCE default usage)
            null_quality_count = sum(1 for row in buy_sigs if row.get("signal_quality_score") is None)
            if null_quality_count > 0:
                logger.warning(
                    f"[DASHBOARD AUDIT] {null_quality_count}/{len(buy_sigs)} signals have NULL quality_score. "
                    f"These are defaulting to 0 in ranking (COALESCE fallback). If > 10%, check signal quality scorer."
                )

            # Grade distribution (A/B/C/D by signal_quality_score, full buy_sell_daily roster
            # for the latest date - not the capped 40-row display list above)
            cur.execute(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE b.signal_quality_score >= 80) AS a,
                    COUNT(*) FILTER (WHERE b.signal_quality_score >= 60 AND b.signal_quality_score < 80) AS b,
                    COUNT(*) FILTER (WHERE b.signal_quality_score >= 40 AND b.signal_quality_score < 60) AS c,
                    COUNT(*) FILTER (WHERE b.signal_quality_score < 40 OR b.signal_quality_score IS NULL) AS d,
                    COUNT(*) AS total
                FROM buy_sell_daily b
                WHERE b.signal = 'BUY' AND b.date = %s
                {buy_sell_filter}
                """,
                (latest_date,),
            )
            grades_r = cur.fetchone()
            if grades_r is None:
                raise RuntimeError(
                    "[DASHBOARD] Grade distribution query returned no result. Database connection lost or buy_sell_daily table missing. "
                    "Cannot fetch grade distribution."
                )
            grades = safe_json_serialize(safe_dict_convert(grades_r))

            # Near-misses: signals with decent scores (55-69 range)
            cur.execute(
                f"""
                SELECT b.symbol, b.signal_quality_score AS score, cp.sector
                FROM buy_sell_daily b
                LEFT JOIN company_profile cp ON cp.symbol = b.symbol
                WHERE b.signal = 'BUY' AND b.date = %s
                {buy_sell_filter}
                  AND b.signal_quality_score BETWEEN 55 AND 69
                ORDER BY b.signal_quality_score DESC NULLS LAST, b.symbol ASC
                LIMIT 15
                """,
                (latest_date,),
            )
            near = [safe_json_serialize(safe_dict_convert(row)) for row in cur.fetchall()]

            # Top A-grade signals (score >= 80)
            cur.execute(
                f"""
                SELECT b.symbol, b.signal_quality_score AS score
                FROM buy_sell_daily b
                WHERE b.signal = 'BUY' AND b.date = %s
                {buy_sell_filter}
                  AND b.signal_quality_score >= 80
                ORDER BY b.signal_quality_score DESC NULLS LAST, b.symbol ASC
                LIMIT 20
                """,
                (latest_date,),
            )
            top_a = [safe_json_serialize(safe_dict_convert(row)) for row in cur.fetchall()]

            # Signal count trend: last 7 days - cast date to text at source
            cur.execute(
                f"""
                SELECT b.date::text as date,
                       COUNT(*) FILTER (WHERE b.signal_quality_score >= 60) AS buy_n,
                       COUNT(*) AS total_n
                FROM buy_sell_daily b
                WHERE b.signal = 'BUY' AND b.date >= %s - 7
                {buy_sell_filter}
                GROUP BY b.date
                ORDER BY b.date DESC
                LIMIT 7
                """,
                (latest_date,),
            )
            trend = [safe_json_serialize(safe_dict_convert(row)) for row in cur.fetchall()]

            # Count qualifying high-quality signals (score >= 70)
            cur.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM buy_sell_daily b
                WHERE b.signal = 'BUY' AND b.date = %s
                {buy_sell_filter}
                  AND b.signal_quality_score >= 70
                """,
                (latest_date,),
            )
            count_row = cur.fetchone()
            if count_row is None:
                raise RuntimeError(
                    "[DASHBOARD] COUNT query returned no result. Database connection lost or buy_sell_daily table missing. "
                    "Cannot fetch qualifying signal count."
                )
            n_value = count_row[0]
            if n_value is None:
                raise RuntimeError(
                    "[DASHBOARD] COUNT(*) returned None/NULL. This is impossible - COUNT() always returns 0+. "
                    "Database schema or query result parsing corrupted."
                )
            qualifying_buy_count = int(n_value)

            freshness = check_data_freshness(cur, "buy_sell_daily", "date", warning_days=1)
            # Ensure freshness dict has dates as strings (check_data_freshness converts them, but be explicit)
            if freshness and "max_date" in freshness and freshness["max_date"] is not None:
                freshness["max_date"] = str(freshness["max_date"])
            freshness = safe_json_serialize(freshness)

            sig_response = {
                "n": qualifying_buy_count,
                "total": total_n,
                "date": str(latest_date),
                "buy_sigs": buy_sigs,
                "near": near[:8] if near else [],
                "top_a": top_a[:20] if top_a else [],
                "grades": grades,
                "trend": trend,
                "data_freshness": freshness,
            }
            sig_response = safe_json_serialize(sig_response)

        return json_response(200, sig_response)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch dashboard signals")
        return error_response(code, error_type, message)
