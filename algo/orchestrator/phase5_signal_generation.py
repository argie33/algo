#!/usr/bin/env python3

import logging
import traceback
from datetime import date as _date
from typing import Any, Callable, Dict

from algo.algo_metrics import MetricsPublisher
from algo.orchestrator.phase_result import PhaseResult
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)


def _get_config_value(cur: Any, key: str, default: Any) -> Any:
    """Read configuration value from algo_config table, fall back to default."""
    try:
        cur.execute("SELECT value FROM algo_config WHERE key = %s", (key,))
        result = cur.fetchone()
        if result and result[0]:
            try:
                if '.' in str(result[0]):
                    return float(result[0])
                else:
                    return int(result[0])
            except (ValueError, TypeError):
                return result[0]
        return default
    except Exception:
        return default


def _report_signal_waterfall(cur: Any, run_date: _date, final_count: int = 0) -> None:
    """Log signal count at each filter tier + detailed per-filter rejection breakdown."""
    try:
        # Count total BUY signals for today
        cur.execute(
            "SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s AND signal_type = 'BUY'",
            (run_date,),
        )
        result = cur.fetchone()
        total_signals = result[0] if result else 0

        # Count from trend_template_data where Stage 2 exists
        # (Stage 2 check is in filter_pipeline, using pre-filtered signals)
        cur.execute(
            """SELECT COUNT(DISTINCT symbol) FROM trend_template_data
               WHERE date = %s AND weinstein_stage = 2""",
            (run_date,),
        )
        result = cur.fetchone()
        stage2_count = result[0] if result else 0

        # Count rejections at each tier + get per-filter breakdown
        tier_rejections = {}
        filter_rejections = {}  # Track rejections by filter name
        try:
            # Collect all rejection reasons to understand filter impacts
            cur.execute(
                "SELECT rejection_reason, COUNT(DISTINCT symbol) as count "
                "FROM filter_rejection_log WHERE eval_date = %s AND rejection_reason IS NOT NULL "
                "GROUP BY rejection_reason ORDER BY count DESC",
                (run_date,),
            )
            for row in cur.fetchall():
                reason, count = row[0], row[1]
                if reason:
                    filter_rejections[reason] = count

            # Get tier-level rejection counts for summary
            for tier_num, tier_name in enumerate(
                ["Tier 1", "Tier 2", "Tier 3", "Tier 4", "Tier 5"], 1
            ):
                cur.execute(
                    "SELECT COUNT(DISTINCT symbol) FROM filter_rejection_log WHERE eval_date = %s AND rejected_at_tier = %s",
                    (run_date, tier_num),
                )
                result = cur.fetchone()
                rejected = result[0] if result else 0
                tier_rejections[tier_name] = rejected
        except Exception as e:
            logger.warning(f"Exception reading filter rejection log: {e}")
            # Table may not exist or columns different; skip
            for tier_name in ["Tier 1", "Tier 2", "Tier 3", "Tier 4", "Tier 5"]:
                tier_rejections[tier_name] = 0

        # Always log waterfall to diagnose 'no trades' situations
        logger.info(f"\n  [FILTER REJECTION ANALYSIS] Signal filtering on {run_date}:")

        # Include source data ages in waterfall report
        signal_data_ages = {}
        try:
            with DatabaseContext("read") as db_cur:
                db_cur.execute("""
                    SELECT
                        MAX(COALESCE(buy_sell_daily_age_days, 0)) as buy_sell_age,
                        MAX(COALESCE(technical_data_age_days, 0)) as technical_age,
                        MAX(COALESCE(trend_template_age_days, 0)) as trend_age
                    FROM signal_quality_scores WHERE date = %s
                """, (run_date,))
                result = db_cur.fetchone()
                if result:
                    signal_data_ages['buy_sell_daily'] = result[0] or 0
                    signal_data_ages['technical_data'] = result[1] or 0
                    signal_data_ages['trend_template'] = result[2] or 0
        except Exception as e:
            logger.debug(f"Could not read signal data ages: {e}")

        if signal_data_ages:
            max_age = max(signal_data_ages.values()) if signal_data_ages.values() else 0
            logger.info(f"    Source data ages (max):   {max_age:4d}d (buy_sell={signal_data_ages.get('buy_sell_daily', '?')}d, "
                       f"technical={signal_data_ages.get('technical_data', '?')}d, trend={signal_data_ages.get('trend_template', '?')}d)")

        logger.info(f"    Total BUY signals:        {total_signals:4d}")
        logger.info(f"    Stage 2 (pre-pipeline):   {stage2_count:4d}")

        # Tier-level summary
        for tier_name in ["Tier 1", "Tier 2", "Tier 3", "Tier 4", "Tier 5"]:
            count = tier_rejections.get(tier_name, 0)
            if count > 0:
                logger.info(f"    {tier_name} rejected:          {count:4d}")
            else:
                logger.info(f"    {tier_name} rejected:          {count:4d}")

        # Age-based rejections (count from filter_rejection_log where is_age_driven_rejection = true)
        # Show breakdown by data source (technical, buy_sell, trend)
        try:
            # Total age-driven rejections
            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM filter_rejection_log WHERE eval_date = %s AND is_age_driven_rejection = TRUE",
                (run_date,),
            )
            result = cur.fetchone()
            age_rejected_count = result[0] if result else 0

            if age_rejected_count > 0:
                logger.info(f"    Data age rejected:         {age_rejected_count:4d}")

                # Show average ages of rejected signals
                try:
                    cur.execute("""
                        SELECT
                            AVG(COALESCE(technical_data_age_days, 0))::int as avg_tech_age,
                            AVG(COALESCE(buy_sell_daily_age_days, 0))::int as avg_bs_age,
                            AVG(COALESCE(trend_template_age_days, 0))::int as avg_trend_age,
                            MAX(COALESCE(max_data_age_days, 0))::int as max_age
                        FROM filter_rejection_log
                        WHERE eval_date = %s AND is_age_driven_rejection = TRUE
                    """, (run_date,))
                    age_stats = cur.fetchone()
                    if age_stats:
                        avg_tech, avg_bs, avg_trend, max_age = age_stats
                        logger.info(f"      Age breakdown (rejected): tech={avg_tech}d, bs={avg_bs}d, trend={avg_trend}d (max={max_age}d)")
                except Exception as age_stats_err:
                    logger.debug(f"Could not fetch age statistics: {age_stats_err}")
        except Exception:
            pass  # Age-driven rejection columns may not exist; skip gracefully

        # Per-filter rejection breakdown (most important filters first)
        if filter_rejections:
            logger.info(f"    [Per-Filter Breakdown] (top rejection reasons):")
            sorted_filters = sorted(filter_rejections.items(), key=lambda x: x[1], reverse=True)
            for reason, count in sorted_filters[:10]:  # Top 10 rejection reasons
                logger.info(f"      - {reason:40s} {count:4d} signals")

        logger.info(f"    Final qualified:          {final_count:4d}")
        interpretation = _interpret_waterfall(
            total_signals, stage2_count, tier_rejections, final_count
        )
        logger.info(f"  Interpretation: {interpretation}")

        # Publish per-filter rejection metrics to CloudWatch
        try:
            with MetricsPublisher() as m:
                # Overall counts
                m.add_metric("TotalSignalsGenerated", total_signals, unit="Count")
                m.add_metric("Stage2CandidatesAvailable", stage2_count, unit="Count")
                m.add_metric("QualifiedTradesAfterFilters", final_count, unit="Count")

                # Per-filter rejections (top 5 to avoid CloudWatch metric spam)
                for i, (reason, count) in enumerate(sorted(filter_rejections.items(), key=lambda x: x[1], reverse=True)[:5]):
                    sanitized_reason = reason.replace(" ", "_").replace("/", "_")[:50]  # Safe metric name
                    m.add_metric(
                        f"FilterRejection_{sanitized_reason}",
                        count,
                        unit="Count",
                        dimensions={"RejectionType": reason[:100]}
                    )

                m.flush()
        except Exception as metric_err:
            logger.debug(f"Could not publish per-filter metrics: {metric_err}")

    except Exception as e:
        logger.warning(f"Signal waterfall report failed: {e}")


def _interpret_waterfall(
    total: int, stage2: int, tier_rejections: Dict[str, int], final: int
) -> str:
    """Interpret the signal waterfall to help diagnose 'no trades' situations."""
    if total == 0:
        return "No BUY signals generated today. Check buy_sell_daily loader or market conditions."
    if stage2 == 0:
        return f"{total} signals exist but NONE are Stage 2. RSI<30 in Stage 2 stocks is rare. Check market stage."
    if final > 0:
        return f"[OK] {final} candidates qualified. Ready to execute."

    # Find the biggest rejection point
    max_reject_tier = (
        max(tier_rejections, key=tier_rejections.get) if tier_rejections else "Unknown"
    )
    max_reject_count = tier_rejections.get(max_reject_tier, 0)
    return f"Stage 2 signals exist but {max_reject_count} rejected at {max_reject_tier}. Review config thresholds."


def run(
    run_date: _date,
    dry_run: bool,
    verbose: bool,
    log_phase_result_fn: Callable,
    exposure_constraints: Dict[str, Any],
    check_halt_flag: Callable,
) -> PhaseResult:
    """Execute Phase 5: Signal Generation & Ranking.

    Args:
        run_date: Date for this run
        dry_run: Whether running in dry-run mode
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results
        exposure_constraints: Exposure constraints from Phase 3b
        check_halt_flag: Function to check halt flag

    Returns:
        PhaseResult with status 'ok', data containing qualified trades
    """
    if check_halt_flag():
        return PhaseResult(
            5, "signal_generation", "halted", {}, True, "Halt flag detected"
        )

    logger.info(f"\n{'='*70}")
    logger.info("PHASE 5: SIGNAL GENERATION & RANKING")
    logger.info(f"{'='*70}")
    if exposure_constraints:
        logger.info(
            f"Exposure constraints: risk_mult={exposure_constraints.get('risk_multiplier', 1.0):.2f}x, tier='{exposure_constraints.get('tier_name', 'N/A')}'"
        )
    else:
        logger.info("Exposure constraints: None (no tier active, using defaults)")

    try:
        import time as _timing

        from algo.algo_filter_pipeline import FilterPipeline

        exposure_mult = 1.0
        if exposure_constraints:
            exposure_mult = exposure_constraints.get("risk_multiplier", 1.0)

        pipeline = FilterPipeline(exposure_risk_multiplier=exposure_mult)

        # Timing instrumentation for Phase 5 performance diagnostics
        _start = _timing.time()
        qualified = pipeline.evaluate_signals(
            None, max_date=run_date
        )  # Auto-detect latest date <= run_date
        _elapsed = _timing.time() - _start
        eval_date = pipeline._snapshot_eval_date or run_date

        # Age-based signal filtering: reject signals with stale source data
        age_rejected = {}  # Track rejections by symbol and reason
        try:
            with DatabaseContext("read") as _age_cur:
                # Read max_data_age_days threshold from algo_config (default 2 days)
                max_data_age_threshold = _get_config_value(
                    _age_cur, "signal_max_data_age_days", 2
                )

                # Only process if we have qualified symbols
                if qualified:
                    # ISSUE #8 FIX: Check if signal_quality_scores exists for eval_date
                    # Morning prep pipeline should populate today's scores, but if it hasn't,
                    # we'll proceed without age filtering (fail-open) but with warning
                    _age_cur.execute(
                        f"""SELECT COUNT(*) FROM signal_quality_scores WHERE date = %s""",
                        (eval_date,),
                    )
                    scores_count = _age_cur.fetchone()[0] if _age_cur.fetchone() else 0
                    if scores_count == 0:
                        logger.warning(
                            f"[ISSUE #8] signal_quality_scores MISSING for {eval_date}. "
                            f"Morning prep pipeline may not have completed. "
                            f"Proceeding without age-based filtering (fail-open). "
                            f"Check that load_signal_quality_scores completed in morning pipeline."
                        )
                        # Emit metric to track missing scores
                        try:
                            from algo.algo_metrics import MetricsPublisher
                            m = MetricsPublisher()
                            m.put_metric('SignalQualityScoresMissing', 1, unit='Count', dimensions={
                                'date': str(eval_date),
                                'phase': 'Phase5'
                            })
                            m.flush()
                        except Exception:
                            pass

                    # Query signal_quality_scores for all qualified symbols
                    placeholders = ",".join(["%s"] * len(qualified))
                    _age_cur.execute(
                        f"""SELECT symbol,
                                   COALESCE(buy_sell_daily_age_days, 0) as buy_sell_age,
                                   COALESCE(technical_data_age_days, 0) as technical_age,
                                   COALESCE(trend_template_age_days, 0) as trend_age
                            FROM signal_quality_scores
                            WHERE date = %s AND symbol IN ({placeholders})""",
                        [eval_date] + qualified,
                    )

                    age_checked = set()
                    for row in _age_cur.fetchall():
                        symbol, buy_sell_age, technical_age, trend_age = row
                        age_checked.add(symbol)
                        max_age = max(buy_sell_age, technical_age, trend_age)

                        # Reject if max age exceeds threshold
                        if max_age > max_data_age_threshold:
                            # Determine which source caused rejection
                            if buy_sell_age == max_age:
                                rejection_source = "buy_sell_daily"
                            elif technical_age == max_age:
                                rejection_source = "technical_data"
                            else:
                                rejection_source = "trend_template"

                            age_rejected[symbol] = {
                                "max_age": max_age,
                                "source": rejection_source,
                                "buy_sell_age": buy_sell_age,
                                "technical_age": technical_age,
                                "trend_age": trend_age,
                            }

                    # Filter out aged symbols
                    qualified = [s for s in qualified if s not in age_rejected]

                    # Log rejections to filter_rejection_log table with age tracking
                    if age_rejected:
                        try:
                            with DatabaseContext("write") as _log_cur:
                                # Query source data ages for rejected symbols
                                for symbol, details in age_rejected.items():
                                    rejection_reason = (
                                        f"Data age threshold exceeded: {details['source']} "
                                        f"({details['max_age']}d > {max_data_age_threshold}d)"
                                    )

                                    # Get the actual ages from signal_quality_scores
                                    bs_age = 0
                                    tech_age = 0
                                    trend_age = 0
                                    try:
                                        _log_cur.execute("""
                                            SELECT buy_sell_daily_age_days, technical_data_age_days, trend_template_age_days
                                            FROM signal_quality_scores
                                            WHERE symbol = %s AND date = %s
                                            ORDER BY date DESC LIMIT 1
                                        """, (symbol, eval_date))
                                        age_row = _log_cur.fetchone()
                                        if age_row:
                                            bs_age = age_row[0] or 0
                                            tech_age = age_row[1] or 0
                                            trend_age = age_row[2] or 0
                                    except Exception as age_fetch_err:
                                        logger.debug(f"Could not fetch ages for {symbol}: {age_fetch_err}")

                                    max_age = max(bs_age, tech_age, trend_age)

                                    _log_cur.execute(
                                        """INSERT INTO filter_rejection_log
                                           (eval_date, symbol, rejection_reason, rejected_at_tier,
                                            buy_sell_daily_age_days, technical_data_age_days, trend_template_age_days,
                                            max_data_age_days, is_age_driven_rejection)
                                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                                        (
                                            eval_date,
                                            symbol,
                                            rejection_reason,
                                            6,  # Tier 6: age filtering
                                            bs_age,
                                            tech_age,
                                            trend_age,
                                            max_age,
                                            True,  # This is an age-driven rejection
                                        ),
                                    )
                                _log_cur.connection.commit()
                        except Exception as _log_err:
                            logger.debug(f"Could not log age-based rejections: {_log_err}")

                    # Publish metrics for age-based rejections
                    if age_rejected:
                        try:
                            with MetricsPublisher(dry_run=dry_run) as _m:
                                _m.put_metric(
                                    "SignalsRejectedByDataAge",
                                    len(age_rejected),
                                    unit="Count",
                                )

                                # Track by rejection source
                                source_counts = {}
                                for details in age_rejected.values():
                                    source = details["source"]
                                    source_counts[source] = source_counts.get(source, 0) + 1

                                for source, count in source_counts.items():
                                    _m.put_metric(
                                        f"SignalsRejectedByDataAge_{source}",
                                        count,
                                        unit="Count",
                                        dimensions={"data_source": source},
                                    )
                        except Exception as _metric_err:
                            logger.debug(f"Could not publish age rejection metrics: {_metric_err}")

                    if age_rejected:
                        logger.info(
                            f"[DATA AGE FILTERING] Rejected {len(age_rejected)} signal(s) for stale source data "
                            f"(threshold: {max_data_age_threshold}d)"
                        )
        except Exception as _age_err:
            logger.debug(f"Age-based filtering failed (non-blocking): {_age_err}")

        # Track signal freshness: check age of source data components
        signal_data_ages = {}
        try:
            with DatabaseContext("read") as _cur:
                # Check swing_trader_scores freshness (critical for signal quality)
                _cur.execute("SELECT MAX(date) FROM swing_trader_scores")
                result = _cur.fetchone()
                latest_scores_date = result[0] if result and result[0] else None

                if latest_scores_date:
                    score_age = (run_date - latest_scores_date).days
                    signal_data_ages['swing_trader_scores'] = score_age
                    if score_age <= 0:
                        logger.info(
                            f"[SIGNAL FRESHNESS] swing_trader_scores: fresh ({latest_scores_date}, same day)"
                        )
                    elif score_age == 1:
                        logger.info(
                            f"[SIGNAL FRESHNESS] swing_trader_scores: 1 day stale ({latest_scores_date})"
                        )
                    else:
                        logger.warning(
                            f"[SIGNAL FRESHNESS] swing_trader_scores: {score_age} days stale ({latest_scores_date}) — signals may lack freshness"
                        )
                else:
                    logger.warning(
                        "[SIGNAL FRESHNESS] swing_trader_scores: NO DATA FOUND — signals will have zero scores"
                    )

                # Check source data staleness columns (buy_sell_daily_age_days, etc.)
                _cur.execute("""
                    SELECT
                        MAX(COALESCE(buy_sell_daily_age_days, 0)) as buy_sell_age,
                        MAX(COALESCE(technical_data_age_days, 0)) as technical_age,
                        MAX(COALESCE(trend_template_age_days, 0)) as trend_age,
                        COUNT(*) as signal_count
                    FROM signal_quality_scores
                    WHERE date = %s
                """, (eval_date,))

                result = _cur.fetchone()
                if result:
                    buy_sell_age, technical_age, trend_age, signal_count = result
                    signal_data_ages['buy_sell_daily'] = buy_sell_age or 0
                    signal_data_ages['technical_data'] = technical_age or 0
                    signal_data_ages['trend_template'] = trend_age or 0

                    max_source_age = max(buy_sell_age or 0, technical_age or 0, trend_age or 0)
                    logger.info(
                        f"[SIGNAL DATA AGE] Source data freshness: buy_sell={buy_sell_age}d, "
                        f"technical={technical_age}d, trend={trend_age}d (max={max_source_age}d, {signal_count} signals)"
                    )

                    # CRITICAL: Reject signals if source data is 5+ days old (stale)
                    # Phase 1 should have caught this, but double-check here
                    if max_source_age >= 5:
                        logger.critical(
                            f"[SIGNAL DATA AGE] CRITICAL: Source data {max_source_age} days old — far too stale! "
                            f"Phase 1 should have halted. Rejecting all signals for safety. "
                            f"Check Phase 1 data freshness checks and failsafe logic."
                        )
                        qualified = []  # Empty qualified trades if source data too stale
                    # Warn if source data is 2-4 days old (reduced freshness)
                    elif max_source_age >= 2:
                        logger.warning(
                            f"[SIGNAL DATA AGE] Source data {max_source_age} days old — signal quality may be reduced"
                        )

                    # Emit metrics for data age tracking
                    try:
                        with MetricsPublisher(dry_run=dry_run) as _m:
                            _m.put_metric(
                                "SignalFreshnessAge",
                                max(score_age or 0, max_source_age or 0),
                                unit="Days",
                                dimensions={"component": "max_age"},
                            )
                            _m.put_metric(
                                "SignalSourceDataAge",
                                max_source_age or 0,
                                unit="Days",
                                dimensions={"component": "source_data"},
                            )
                    except Exception as _metric_err:
                        logger.debug(
                            f"Could not emit signal freshness metrics: {_metric_err}"
                        )
        except Exception as _freshness_err:
            logger.debug(
                f"Signal freshness check failed (non-blocking): {_freshness_err}"
            )

        logger.info(
            f"[TIMING] Phase 5 filter pipeline completed in {_elapsed:.1f}s for {len(qualified)} qualified trades"
        )

        # Signal count waterfall report (for visibility on where signals die)
        try:
            with DatabaseContext("read") as cur:
                _report_signal_waterfall(cur, eval_date, len(qualified))
                # When nothing qualifies, emit a clear diagnostic so we know exactly why
                if len(qualified) == 0:
                    cur.execute(
                        "SELECT date, market_stage, market_trend, distribution_days_4w, vix_level "
                        "FROM market_health_daily ORDER BY date DESC LIMIT 1"
                    )
                    mh = cur.fetchone()
                    cur.execute(
                        "SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s AND signal_type = 'BUY'",
                        (eval_date,),
                    )
                    bsd_count = (cur.fetchone() or [0])[0]
                    cur.execute(
                        "SELECT COUNT(*) FROM trend_template_data WHERE date = %s AND weinstein_stage = 2",
                        (eval_date,),
                    )
                    stage2_stocks = (cur.fetchone() or [0])[0]

                    diag = {
                        "eval_date": str(eval_date),
                        "buy_signals": bsd_count,
                        "stage2_stocks": stage2_stocks,
                        "market_stage": mh[1] if mh else None,
                        "market_trend": mh[2] if mh else None,
                        "dist_days": mh[3] if mh else None,
                        "vix": str(mh[4]) if mh else None,
                    }

                    if mh:
                        logger.warning(
                            f"[ZERO TRADES DIAGNOSIS] eval_date={eval_date} | "
                            f"market_health latest={mh[0]} stage={mh[1]} trend={mh[2]} "
                            f"dist_days={mh[3]} vix={mh[4]} | "
                            f"buy_signals={bsd_count} stage2_stocks={stage2_stocks}"
                        )
                        if mh[1] != 2:
                            logger.warning(
                                f"[ZERO TRADES] Primary blocker: market_stage={mh[1]} (need 2 for Tier 2). "
                                f"Set require_stage_2_market=false in algo_config table to trade in other market stages."
                            )
                    else:
                        logger.warning(
                            f"[ZERO TRADES DIAGNOSIS] eval_date={eval_date} | market_health_daily: NO ROWS FOUND"
                        )

                    # Alert: 0 qualified trades is never silent
                    # Suppress alert during dry_run to avoid noise from pipeline validation runs
                    if not dry_run:
                        try:
                            from algo.algo_alerts import AlertManager

                            AlertManager().send_position_alert(
                                "SIGNAL",
                                "ZERO_QUALIFIED_TRADES",
                                f"Phase 5 found 0 qualified trades on {eval_date}. "
                                f"buy_signals={bsd_count}, stage2_stocks={stage2_stocks}, "
                                f'market_stage={diag["market_stage"]}, vix={diag["vix"]}. '
                                f"Check CloudWatch logs for filter rejection details.",
                                diag,
                            )
                        except Exception as _alert_err:
                            logger.warning(
                                f"Zero-trades alert failed (non-blocking): {_alert_err}"
                            )
        except Exception as e:
            logger.warning(f"Signal waterfall report failed (non-blocking): {e}")

        log_phase_result_fn(
            5,
            "signal_generation",
            "success",
            f"{len(qualified)} qualified trades after 5-tier filter + advanced scoring",
        )

        return PhaseResult(
            5,
            "signal_generation",
            "ok",
            {"qualified_trades": qualified, "count": len(qualified)},
            False,
            None,
        )

    except RuntimeError as e:
        logger.critical(
            f"PHASE 5 HALT — portfolio value unavailable, no new entries: {e}"
        )
        try:
            with MetricsPublisher(dry_run=dry_run) as _m:
                _m.put_circuit_breaker("PortfolioValueUnavailable", fired=True)
        except Exception as e:
            logger.error(f"Unhandled exception: {e}")

        log_phase_result_fn(5, "signal_generation", "halt", str(e))
        return PhaseResult(5, "signal_generation", "halted", {}, True, str(e))

    except Exception as e:
        traceback.print_exc()
        log_phase_result_fn(5, "signal_generation", "error", str(e))
        # Fail-open: log error but don't halt — Phase 6 gets empty qualified_trades
        # and will log "no qualified trades" rather than blocking exits/reconciliation.
        return PhaseResult(
            5, "signal_generation", "error", {"qualified_trades": []}, False, str(e)
        )
