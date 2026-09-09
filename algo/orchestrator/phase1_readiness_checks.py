#!/usr/bin/env python3
"""
PHASE 1 HELPERS: DOWNSTREAM READINESS CHECKS

Pure extract-method split of phase1_data_freshness.py's run() (see that module's docstring
for the overall Phase 1 contract). This file holds the two checks that run only after the
core price/table freshness gates have already passed:

- validate_stock_scores_readiness(): validates upstream metric loaders (quality, growth,
  value, positioning, stability, momentum) are ready for Phase 7 signal generation, and
  checks stock_scores completeness/staleness.
- validate_portfolio_symbol_prices(): validates every open-position symbol has a usable
  price so Phase 6 exit execution won't halt mid-run.

NO BEHAVIOR CHANGE: every function here is a verbatim relocation of code that used to live
inline in run() - control flow, thresholds, log messages, and return values are unchanged.
"""

import logging
from collections.abc import Callable
from datetime import date as _date
from typing import Any

import psycopg2

from algo.infrastructure.constants import PHASE1_METRIC_COVERAGE_MIN_PCT
from algo.orchestrator.phase_result import PhaseResult

logger = logging.getLogger(__name__)


def validate_stock_scores_readiness(
    cur: Any, halt_tables: dict[str, str], log_phase_result_fn: Callable[..., Any]
) -> tuple[str | None, PhaseResult | None]:
    """Validate that metric loaders are ready for Phase 7 signal generation via stock_scores.

    CRITICAL FIX 2026-07-05: Validate that metric loaders are ready before Phase 7 signal generation
    These loaders (quality, growth, value, positioning, stability, momentum) feed into stock_scores
    which feed into signal generation. If metrics are all-unavailable, stock_scores will fail.

    Returns (degraded_reason, halt_result). If halt_result is not None, Phase 1 must return it
    immediately. Otherwise degraded_reason (possibly None) should be carried forward by the
    caller to the later GOVERNANCE degraded-data check.
    """
    logger.info("[PHASE 1] Validating upstream metric loaders ready for stock_scores...")
    degraded_reason = None
    try:
        from loaders.load_stock_scores import StockScoresLoader

        metric_validator = StockScoresLoader()
        metric_validator.validate_upstream_metrics_ready()
        logger.info("[PHASE 1] Metric loaders validation: PASS - All metric loaders ready")

        # FIXED 2026-07-15: Add stock_scores data completeness check (Issue #6 from Session 166 audit)
        # Validate that scores have sufficient completeness (60%+ avg for available scores)
        # FIXED 2026-07-18: Only average AVAILABLE scores (data_unavailable=FALSE)
        # Stocks with 0% completeness are legitimately unavailable due to missing metrics,
        # and should not drag down the average or halt trading for all other stocks.
        try:
            # CRITICAL: stock_scores.updated_at is `timestamp without time zone`, written via
            # datetime.now(timezone.utc) in load_stock_scores.py (i.e. the stored digits ARE
            # UTC wall-clock). TRADING-DAY FIX: Don't check "last 24 hours" (fails on Monday
            # morning when Friday's EOD scores are 48h old). Instead check if max score date
            # matches the most recent trading day in the DB (which stock_scores depends on for
            # underlying metric data). Stock scores have no date column, so check updated_at
            # against price_daily's max date (latest trading day with prices).
            cur.execute(f"""
                SELECT AVG(data_completeness) as avg_completeness,
                       COUNT(*) as total_available_scores,
                       COUNT(CASE WHEN data_completeness >= {PHASE1_METRIC_COVERAGE_MIN_PCT} THEN 1 END) as complete_scores,
                       COUNT(*) FILTER (WHERE data_unavailable = FALSE) as available_count,
                       MAX(updated_at) as max_updated
                FROM stock_scores
                WHERE data_unavailable = FALSE
            """)
            completeness_row = cur.fetchone()

            # Verify stock_scores were computed for the latest trading day available in price data
            cur.execute("SELECT MAX(date) FROM price_daily")
            price_row = cur.fetchone()
            if not price_row or price_row[0] is None:
                raise RuntimeError("[PHASE 1] price_daily table is empty - cannot verify stock_scores freshness")
            latest_price_date = price_row[0]

            # Stock scores should have been updated AFTER the latest price date (they're computed
            # end-of-day). Allow up to 48 hours for EOD pipelines to run (covering overnight + weekend scenarios).
            scores_age_hours = None
            if completeness_row and completeness_row[4] and latest_price_date:
                from datetime import datetime, timezone

                now_utc = datetime.now(timezone.utc)
                max_updated = completeness_row[4]
                if max_updated.tzinfo is None:
                    max_updated = max_updated.replace(tzinfo=timezone.utc)
                scores_age_hours = (now_utc - max_updated).total_seconds() / 3600

            if (
                completeness_row
                and completeness_row[0] is not None
                and scores_age_hours is not None
                and scores_age_hours < 48
            ):
                avg_completeness = float(completeness_row[0])
                total_available = completeness_row[1]
                complete_scores = completeness_row[2]

                logger.info(
                    f"[PHASE 1] Stock scores completeness: {avg_completeness:.1f}% avg "
                    f"({complete_scores}/{total_available} available symbols >= {PHASE1_METRIC_COVERAGE_MIN_PCT}%)"
                )

                # GOVERNANCE: Allow proceeding if 60%+ of available scores are complete
                # Stocks with insufficient metrics are properly marked data_unavailable
                # and excluded from signal generation, so degradation is contained
                if avg_completeness < 60:
                    logger.warning(
                        f"[PHASE 1] DEGRADED: Stock scores avg completeness only {avg_completeness:.1f}%. "
                        f"Position sizing may use incomplete metric data. "
                        f"If this persists, check: {[t for t in halt_tables if 'metric' in t]}"
                    )
                    degraded_reason = (
                        f"Stock scores only {avg_completeness:.1f}% complete "
                        f"(missing positioning/stability/growth metrics)"
                    )
            else:
                # Stale, missing, or incompute able scores
                if (
                    completeness_row
                    and completeness_row[4] is not None
                    and scores_age_hours is not None
                    and scores_age_hours >= 48
                ):
                    logger.warning(
                        f"[PHASE 1] stock_scores stale: computed {scores_age_hours:.1f}h ago "
                        f"(max_updated={completeness_row[4]}). "
                        f"Latest price data is from {latest_price_date}. "
                        f"Scores are older than 48h threshold. "
                        f"Check if end-of-day pipeline has run."
                    )
                else:
                    logger.warning(
                        "[PHASE 1] stock_scores data unavailable or no available symbols. "
                        "Proceeding but scores will be unavailable for signal generation."
                    )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as completeness_err:
            logger.warning(
                f"[PHASE 1] Could not check stock_scores completeness (DB error): {completeness_err}. "
                "Will proceed with signal generation using available scores."
            )
        except (KeyError, ValueError, AttributeError) as completeness_err:
            logger.warning(
                f"[PHASE 1] Could not check stock_scores completeness (data error): {completeness_err}. "
                "Will proceed with signal generation using available scores."
            )
    except RuntimeError as e:
        metric_error = str(e)
        logger.warning(f"[PHASE 1] Metric loaders validation failed: {metric_error}")
        try:
            cur.execute("""
                SELECT COUNT(*) FROM quality_metrics WHERE updated_at > NOW() - INTERVAL '7 days'
                UNION ALL SELECT COUNT(*) FROM growth_metrics WHERE updated_at > NOW() - INTERVAL '7 days'
                UNION ALL SELECT COUNT(*) FROM stability_metrics WHERE updated_at > NOW() - INTERVAL '7 days'
            """)
            metric_counts = cur.fetchall()
            has_recent_metrics = any(row[0] > 0 for row in metric_counts)

            if has_recent_metrics:
                logger.critical(
                    f"[PHASE 1] CRITICAL: Metrics exist but validation failed. {metric_error}. "
                    f"GOVERNANCE requires fail-fast on metric validation failure. "
                    f"Root cause must be resolved before trading resumes."
                )
                halt_reason = f"Metric loader validation failed: {metric_error[:500]}"
                log_phase_result_fn(1, "metric_validation_failed", "halt", halt_reason)
                return degraded_reason, PhaseResult(
                    1,
                    "metric_validation_failed",
                    "halted",
                    {},
                    True,
                    halt_reason,
                )
            else:
                logger.critical(f"[PHASE 1] CRITICAL: Metric loaders validation failed: {metric_error}")
                halt_reason = f"Required metric loaders not ready: {metric_error[:500]}"
                log_phase_result_fn(1, "metric_loaders_not_ready", "halt", halt_reason)
                return degraded_reason, PhaseResult(
                    1,
                    "metric_loaders_not_ready",
                    "halted",
                    {},
                    True,
                    halt_reason,
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as check_err:
            # CRITICAL FIX: this branch only logged halt_reason with no `return` (and no
            # log_phase_result_fn call) - unlike its sibling except clause immediately
            # below, which correctly halts. We only reach this try block after
            # validate_upstream_metrics_ready() has ALREADY raised a genuine critical
            # metric-validation failure (metric_error); this except exists purely to
            # assess its severity via a diagnostic query. If that diagnostic query itself
            # hits a transient DB error, execution fell through to this function's normal
            # "all_tables_fresh"/"success" logging further down, masking the original
            # critical metric-validation failure as a clean pass - the DB error ate the
            # halt, rather than the halt surviving the DB error.
            halt_reason = f"Could not verify metric availability (DB error): {str(check_err)[:500]}"
            logger.critical(f"[PHASE 1] {halt_reason}. Original metric validation failure: {metric_error}")
            log_phase_result_fn(1, "metric_verification_error", "halt", halt_reason)
            return degraded_reason, PhaseResult(
                1,
                "metric_verification_error",
                "halted",
                {},
                True,
                halt_reason,
            )
        except (RuntimeError, ValueError, KeyError) as check_err:
            halt_reason = f"Could not verify metric availability (validation error): {str(check_err)[:500]}"
            logger.error(f"[PHASE 1] {halt_reason}")
            logger.critical(f"[PHASE 1] CRITICAL: Metric loaders validation failed: {metric_error}")
            log_phase_result_fn(1, "metric_verification_error", "halt", halt_reason)
            return degraded_reason, PhaseResult(
                1,
                "metric_verification_error",
                "halted",
                {},
                True,
                halt_reason,
            )

    return degraded_reason, None


def validate_portfolio_symbol_prices(
    cur: Any,
    phase_data: dict[str, Any],
    log_phase_result_fn: Callable[..., Any],
    acceptable_min_date: _date | None = None,
) -> PhaseResult | None:
    """Validate all open-position portfolio symbols have a usable, sufficiently recent price.

    CRITICAL NEW CHECK (2026-08-02): Validate portfolio symbols have prices
    Phase 1 verified price_daily overall freshness, but doesn't check if ALL
    portfolio symbols have data for the trading date. This causes Phase 6 to halt
    when evaluating exits for a symbol with no price_daily data (verified root
    cause of "5 errors" pattern on 2026-07-29). Catch this early.

    FIX (2026-09-09, real-money-readiness data-loader-integrity audit): this used to only
    check that a portfolio symbol had ANY row in price_daily, with no recency bound - a
    symbol stuck on a multi-day-old row (a partial same-day loader failure affecting only
    that symbol, invisible to the aggregate-table freshness check and to DataPatrol's
    per-symbol staleness check, which only fires WARN past a 7-day lag) passed this check
    as "has prices" indefinitely. Phase 3/6 would then evaluate stops/exits for a real open
    position against a stale price with nothing here to catch it. `acceptable_min_date` is
    the SAME per-run threshold phase1_data_freshness.py's aggregate check already computes
    (compute_last_trading_day + compute_acceptable_min_date_with_grace +
    apply_eod_yesterday_price_grace - the "today's data once market close has passed,
    yesterday's otherwise" rule, with its existing EOD-load-delay grace period) - reusing it
    here means a portfolio symbol is held to exactly the same bar as the rest of the
    universe, not a new, separately-tuned threshold. Optional and defaults to None (skips
    the recency check, preserving prior behavior) only so existing callers/tests that don't
    thread it through are unaffected - the real Phase 1 caller always passes it.

    Mutates `phase_data` in place with portfolio_symbols/portfolio_price_coverage or
    missing_prices, matching the original inline behavior. Returns a halting PhaseResult
    if any portfolio symbol is missing a price or (when acceptable_min_date is given) stuck
    on a price older than that threshold, else None.
    """
    try:
        # Get all open positions in portfolio
        cur.execute("""
            SELECT DISTINCT symbol FROM algo_positions
            WHERE status IN ('open', 'partially_filled')
        """)
        portfolio_symbols = [row[0] for row in cur.fetchall()]

        if portfolio_symbols:
            logger.info(
                f"[PHASE 1] Validating prices for {len(portfolio_symbols)} portfolio symbols (using latest available)"
            )
            # CRITICAL FIX: Use latest available price for each symbol, consistent with Phase 3
            # Phase 3 position_monitor.py uses ROW_NUMBER() OVER ORDER BY date DESC to get
            # the most recent price regardless of exact date. Phase 1 must validate the same way
            # to avoid false halts on mid-trading-day runs before EOD prices load.
            cur.execute(
                """
                WITH latest_prices AS (
                    SELECT symbol, close, date,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
                    FROM price_daily
                    WHERE symbol = ANY(%s) AND close IS NOT NULL
                )
                SELECT symbol, close, date FROM latest_prices WHERE rn = 1
            """,
                (portfolio_symbols,),
            )
            price_rows = cur.fetchall()
            price_symbols = {row[0]: row[1] for row in price_rows}
            price_dates = {row[0]: row[2] for row in price_rows}
            missing_symbols = [s for s in portfolio_symbols if s not in price_symbols]
            stale_symbols = (
                [
                    s
                    for s in portfolio_symbols
                    if s in price_dates and price_dates[s] is not None and price_dates[s] < acceptable_min_date
                ]
                if acceptable_min_date is not None
                else []
            )

            if stale_symbols:
                error_msg = (
                    f"[PHASE 1 CRITICAL] Portfolio symbols have price data older than the "
                    f"acceptable threshold ({acceptable_min_date}): "
                    f"{[(s, str(price_dates[s])) for s in stale_symbols]}. "
                    f"Phase 3/6 would evaluate stops/exits for these open positions against a "
                    f"stale price. Check price_daily loader logs for a symbol-specific data gap."
                )
                logger.critical(error_msg)
                log_phase_result_fn(1, "portfolio_price_coverage", "halt", error_msg)
                phase_data["portfolio_symbols"] = len(portfolio_symbols)
                phase_data["stale_prices"] = stale_symbols
                return PhaseResult(
                    1,
                    "portfolio_price_coverage",
                    "halted",
                    phase_data,
                    True,
                    f"Portfolio symbols have stale prices: {stale_symbols}",
                )

            if missing_symbols:
                # CRITICAL: Missing prices for portfolio symbols - cannot execute exits
                error_msg = (
                    f"[PHASE 1 CRITICAL] Portfolio symbols missing any price data: {missing_symbols}. "
                    f"Phase 6 exit execution will fail for these positions. "
                    f"Check price_daily loader logs for data gaps or symbol-specific issues."
                )
                logger.critical(error_msg)
                log_phase_result_fn(1, "portfolio_price_coverage", "halt", error_msg)

                # Return halted status to prevent Phase 6 attempting exits without price data
                phase_data["portfolio_symbols"] = len(portfolio_symbols)
                phase_data["missing_prices"] = missing_symbols
                return PhaseResult(
                    1,
                    "portfolio_price_coverage",
                    "halted",
                    phase_data,
                    True,
                    f"Portfolio symbols missing prices: {missing_symbols}",
                )
            else:
                logger.info(f"[PHASE 1] All {len(portfolio_symbols)} portfolio symbols have prices (latest available)")
                phase_data["portfolio_symbols"] = len(portfolio_symbols)
                phase_data["portfolio_price_coverage"] = "complete"
    except (psycopg2.DatabaseError, psycopg2.OperationalError, KeyError, ValueError, TypeError) as portfolio_check_err:
        # FAIL-CLOSED (2026-09-06, real-money-readiness audit): this used to log a warning and
        # return None ("no problem found, continue") on ANY error here - the exact failure mode
        # this check exists to prevent. If we can't verify portfolio symbols have usable prices
        # (a transient DB error is exactly when that's least certain), silently proceeding is
        # indistinguishable from the missing_prices branch above except that nobody notices until
        # Phase 6 halts mid-run trying to exit a position with no price data - the original
        # "5 errors" pattern this check was built to catch early. Halt instead; a genuinely
        # transient DB blip surfaces as a halt Phase 1 will clear itself once the DB recovers.
        error_msg = (
            f"[PHASE 1 CRITICAL] Could not validate portfolio symbol price coverage "
            f"({type(portfolio_check_err).__name__}: {portfolio_check_err}). Cannot verify Phase 6 "
            "exit execution has usable prices for every open position - halting rather than "
            "proceeding on an unverified assumption."
        )
        logger.critical(error_msg)
        log_phase_result_fn(1, "portfolio_price_coverage", "halt", error_msg)
        return PhaseResult(1, "portfolio_price_coverage", "halted", phase_data, True, error_msg)

    return None
