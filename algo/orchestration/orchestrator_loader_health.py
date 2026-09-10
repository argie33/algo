"""Orchestrator mixin (OrchestratorLoaderHealthMixin), extracted from orchestrator.py
(file-size ratchet split, 2026-09-10). Methods moved verbatim - no behavior change -
except call sites for names some test files patch at module level on
algo.orchestration.orchestrator (DatabaseContext/datetime/get_event_hub/run_phaseN)
now go through `_owner()` so that patching keeps working regardless of which mixin
file actually calls them; see `_owner()`'s own docstring. Mixed into Orchestrator via
multiple inheritance in orchestrator.py - every other `self.` call here resolves
normally through the instance regardless of which mixin file defines it.
"""

import logging
import os
import time
from datetime import time as dt_time
from datetime import timedelta, timezone
from typing import TYPE_CHECKING, Any

import psycopg2

from algo.infrastructure import MarketCalendar
from utils.infrastructure import EASTERN_TZ
from utils.infrastructure.market_timing import (
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    ORCHESTRATOR_KILL_BUFFER_MINUTES,
    ORCHESTRATOR_RUN_TIMES_TUPLE,
)

if TYPE_CHECKING:
    from algo.orchestration._orchestrator_protocol import OrchestratorProtocol

    _Base = OrchestratorProtocol
else:
    _Base = object

logger = logging.getLogger(__name__)


def _owner() -> Any:
    """Lazy reference to the owner module (algo.orchestration.orchestrator), resolved at
    call time not import time. Several tests patch `algo.orchestration.orchestrator.
    DatabaseContext` / `.datetime` / `.get_event_hub` / `.run_phase1` / `.run_phase2` /
    `.run_phase9` directly (module-level monkeypatching) - a plain top-level import of
    those names in THIS file would bind this module's own separate copy, which those
    patches can never reach. Going through `_owner().X` always reads whatever the owner
    module's current attribute is, mocked or real - same pattern as loaders/helpers/
    vqg_quality.py's `_owner()` for the identical reason. Importing lazily (inside this
    function body, not at module level) also avoids a circular import, since the owner
    module is what imports THIS module.
    """
    from algo.orchestration import orchestrator as _owner_mod

    return _owner_mod


class OrchestratorLoaderHealthMixin(_Base):
    def _kill_long_running_loaders(self) -> None:
        """CRITICAL: Kill hung loaders (analytics + critical-path) if approaching next orchestrator run.

        Analytics loaders (company_profile, analyst_sentiment, stability_metrics, value_metrics)
        iterate 5000+ symbols with yfinance rate limits and can run 6+ hours.

        Critical-path loaders (trend_template_data, sector_ranking,
        market_health_daily, market_exposure_daily, algo_metrics_daily) should complete within
        30-90 minutes. If still running 15 min before next orchestrator run, they're hung and
        consuming RDS connections.

        If any is still running when orchestrator fires, RDS connection pool exhaustion occurs.
        This check prevents that.

        Dynamic timeout: calculate time until next orchestrator run, subtract 15 min buffer.
        Orchestrator runs at: 9:30 AM, 1 PM, 3 PM, 5:30 PM ET (Mon-Fri only)

        ISSUE #5 FIX: Verifies task termination to prevent hung tasks consuming RDS connections.
        ISSUE #1 FIX: Added critical-path loaders to kill check.
        """
        try:
            import boto3

            ecs = boto3.client("ecs", region_name=os.getenv("AWS_REGION", "us-east-1"))
            cluster = os.getenv("ECS_CLUSTER_ARN", "algo-cluster")

            # Both analytics (6+ hour) and critical-path (30-90 min) loaders
            analytics_loaders = {
                "company_profile",
                "analyst_sentiment",
                "stability_metrics",
                "value_metrics",
            }
            critical_path_loaders = {
                "trend_template_data",
                "sector_ranking",
                "market_health_daily",
                "market_exposure_daily",
                "algo_metrics_daily",
            }
            monitored_loaders = analytics_loaders | critical_path_loaders

            # Calculate time until next orchestrator run (in ET)
            now_utc = _owner().datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)

            # Find next orchestrator run
            next_orch_et = None
            for orch_hour, orch_minute in ORCHESTRATOR_RUN_TIMES_TUPLE:
                orch_time = now_et.replace(hour=orch_hour, minute=orch_minute, second=0, microsecond=0)
                if orch_time > now_et:
                    next_orch_et = orch_time
                    break

            # If no more runs today, next is tomorrow morning
            if next_orch_et is None:
                next_orch_et = (now_et + timedelta(days=1)).replace(
                    hour=MARKET_OPEN_HOUR,
                    minute=MARKET_OPEN_MINUTE,
                    second=0,
                    microsecond=0,
                )
                # Skip non-trading days
                while not MarketCalendar.is_trading_day(next_orch_et.date()):
                    next_orch_et += timedelta(days=1)

            # Calculate kill threshold: next_orch - buffer minutes
            kill_threshold_et = next_orch_et - timedelta(minutes=ORCHESTRATOR_KILL_BUFFER_MINUTES)
            max_runtime = kill_threshold_et - now_et

            if max_runtime.total_seconds() <= 0:
                logger.debug("[OOM_PREVENTION] Next orchestrator run is imminent, using 5 min max runtime")
                max_runtime = timedelta(minutes=5)

            logger.debug(
                f"[OOM_PREVENTION] Next orchestrator run at {next_orch_et.strftime('%H:%M')} ET. "
                f"Kill timeout: {max_runtime.total_seconds() / 60:.0f} minutes"
            )

            # List running tasks
            response = ecs.list_tasks(cluster=cluster, desiredStatus="RUNNING")
            task_arns = response.get("taskArns")
            if not task_arns:
                return
            if not isinstance(task_arns, list):
                logger.error(f"[OOM_PREVENTION] Unexpected taskArns type: {type(task_arns)}, expected list")
                return

            # Get task details (includes startedAt timestamp)
            task_details = ecs.describe_tasks(cluster=cluster, tasks=task_arns)
            now = _owner().datetime.now(timezone.utc)

            # Validate DynamoDB response schema
            if not isinstance(task_details, dict):
                logger.error(f"[OOM_PREVENTION] Unexpected task_details type: {type(task_details)}, expected dict")
                return

            tasks = task_details.get("tasks")
            if not isinstance(tasks, list):
                logger.error(f"[OOM_PREVENTION] Unexpected tasks type: {type(tasks)}, expected list")
                return

            failed_terminations = []
            for task in tasks:
                # Extract loader name from task definition (format: algo-LOADER_NAME-loader:1)
                task_def = task.get("taskDefinitionArn", "")
                loader_name = None
                for loader in monitored_loaders:
                    if loader in task_def:
                        loader_name = loader
                        break

                if not loader_name:
                    continue  # Skip non-monitored loaders

                started_at = task.get("startedAt")
                if not started_at:
                    # CRITICAL: Validate taskArn field exists for error context (fail-fast if missing)
                    task_arn = task.get("taskArn")
                    if task_arn is None:
                        raise ValueError(
                            f"[CRITICAL] Task missing BOTH startedAt AND taskArn fields. "
                            f"Cannot assess hung loader or identify which task failed. "
                            f"This indicates ECS metadata corruption or schema change. Task: {task}"
                        )
                    raise ValueError(
                        f"[CRITICAL] Task missing startedAt field - cannot assess if hung. "
                        f"This indicates ECS metadata corruption or schema change. "
                        f"Cannot proceed with hung loader detection. Task: {task_arn}"
                    )

                # Convert startedAt to UTC-aware datetime if needed
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)

                age = now - started_at
                if age > max_runtime:
                    task_arn = task.get("taskArn")
                    logger.warning(
                        f"[OOM_PREVENTION] Killing {loader_name} task (running {age.total_seconds() / 3600:.1f}h, "
                        f"max {max_runtime.total_seconds() / 3600:.1f}h before next orch run): {task_arn}"
                    )

                    # ISSUE #5: Issue stop request
                    try:
                        ecs.stop_task(
                            cluster=cluster,
                            task=task_arn,
                            reason="Loader hung beyond timeout before next orchestrator run",
                        )
                    except Exception as stop_err:
                        logger.critical(
                            f"[TASK_TERMINATION] CRITICAL: Failed to kill hung loader {loader_name}: {stop_err}. "
                            f"Task will continue consuming resources. Manual intervention required: {task_arn}"
                        )
                        self.degraded_mode = True
                        failed_terminations.append((loader_name, task_arn, str(stop_err)))
                        # Don't silently continue - mark as degraded so operator is aware task termination failed

                    # ISSUE #5: Verify task actually stopped (with retries)
                    if self.db_monitor.verify_task_stopped(ecs, cluster, task_arn, loader_name):
                        self.log_phase_result(
                            0,
                            "oom_prevention",
                            "success",
                            f"Killed {loader_name} task running {age.total_seconds() / 3600:.1f}h",
                        )
                    else:
                        failed_terminations.append((loader_name, task_arn, "verification timeout"))

            # ISSUE #5: Alert if any terminations failed
            if failed_terminations:
                error_details = "; ".join([f"{name}: {err}" for name, arn, err in failed_terminations])
                logger.critical(
                    f"[TASK_TERMINATION] ESCALATION: {len(failed_terminations)} task termination(s) failed. "
                    f"{error_details}"
                )
                try:
                    self.alerts.send_position_alert(
                        "TASK_TERMINATION",
                        "HUNG_LOADER_TERMINATION_FAILED",
                        f"Failed to terminate {len(failed_terminations)} hung loaders. RDS connections may not be released. "
                        f"Check CloudWatch logs and manually stop: {', '.join([arn.split('/')[-1] for _, arn, _ in failed_terminations])}",
                        {
                            "failed_tasks": [
                                {"loader": name, "task_arn": arn, "error": err}
                                for name, arn, err in failed_terminations
                            ]
                        },
                    )
                except (ValueError, ZeroDivisionError, TypeError) as alert_err:
                    logger.error(f"[TASK_TERMINATION] Could not send escalation alert: {alert_err}")

        except Exception as e:
            logger.warning(f"[OOM_PREVENTION] Could not check/kill long-running loaders: {e}")
            # Don't halt trading for this check - it's advisory

    def _cleanup_expired_locks(self) -> None:
        """Clean up expired loader locks from database.

        Prevents stale locks from hung loaders from blocking future orchestrator runs.
        Automatically called during preflight checks to maintain lock table health.
        Session 391: Fixed stale signal_quality_scores lock that held 2-hour TTL.
        Session 398: Be more aggressive - delete locks held > 1 hour even if not expired.
        Session 428: Further improvement - lower threshold to 10 min and alert on stuck locks.

        FIX (2026-07-27): The flat 10-minute threshold from Session 428 predates, and was
        never reconciled with, utils/optimal_loader.py's later per-loader lock_ttl fix
        (lock_ttl=7200s in production specifically because real loader runtimes are
        60-90+ min for price_daily, ~15 min for insider_transaction_velocity - see that
        file's own comment on why TTL "must outlive the longest legitimate run"). This
        routine ran unconditionally on every orchestrator preflight and force-DELETEd
        (not just alerted on) any lock older than 600s regardless of environment or the
        lock's own expires_at, which in production would strip a still-legitimately-running
        loader's lock and let a concurrent trigger acquire it and double-write - exactly the
        race the lock exists to prevent. Live-reproduced 2026-07-27: a real dry-run flagged
        insider_transaction_velocity's lock as "crash suspected" at 702s into its known-normal
        ~900s run. Now mirrors optimal_loader.py's own LOCAL_MODE-aware threshold instead of
        a threshold disconnected from the TTL loaders actually request.
        """
        try:
            # UPDATED (2026-07-28): optimal_loader.py's LOCAL_MODE lock_ttl changed from a flat
            # 600s to 3600s (real local dev runs regularly exceed 600s - e.g.
            # institutional_holdings_13f held its lock 926.6s on an ordinary run, and cash-flow
            # statement backfills observed at ~2385s, which an interim 1800s value still
            # undercut). This threshold must track that value or this routine reintroduces the
            # exact bug its own 2026-07-27 fix removed, just in LOCAL_MODE: force-deleting a
            # still-legitimately-running local loader's lock out from under it.
            #
            # SESSION 98 FIX: Use maximum configured loader timeout instead of hardcoded defaults.
            # Prices timeout is 900 minutes (54000s), so detecting stuck loaders at 1-2 hours
            # would force-delete legitimate long-running loader locks mid-execution.
            from loaders.loader_timeout_config import get_loader_timeouts

            all_timeouts = get_loader_timeouts().values()
            max_loader_timeout = max(all_timeouts) if all_timeouts else 54000  # prices default fallback
            stuck_threshold_seconds = max_loader_timeout + 300  # Add 5 min grace period for cleanup

            with _owner().DatabaseContext("write") as cur:
                # First: Alert on stuck locks BEFORE deleting them (for debugging)
                # Stuck locks indicate loader crash/hang - need visibility
                cur.execute(
                    """
                    SELECT loader_name, locked_at,
                           EXTRACT(EPOCH FROM (NOW() - locked_at)) as duration_sec
                    FROM loader_execution_locks
                    WHERE EXTRACT(EPOCH FROM (NOW() - locked_at)) > %s
                    ORDER BY locked_at ASC
                    """,
                    (stuck_threshold_seconds,),
                )
                stuck_locks = cur.fetchall()
                if stuck_locks:
                    logger.critical(
                        f"[LOCK_CLEANUP ALERT] {len(stuck_locks)} loader lock(s) held > {stuck_threshold_seconds}s "
                        f"(loader crash/hang suspected): "
                        + ", ".join([f"{name}({dur:.0f}s)" for name, _, dur in stuck_locks])
                    )

                # Second: Delete expired locks OR locks held past the same SLA threshold
                # loaders themselves use to set expires_at (matches optimal_loader.py's
                # lock_ttl, so this never deletes out from under a still-legitimate run).
                cur.execute(
                    """
                    DELETE FROM loader_execution_locks
                    WHERE expires_at <= CURRENT_TIMESTAMP
                       OR EXTRACT(EPOCH FROM (NOW() - locked_at)) > %s
                    """,
                    (stuck_threshold_seconds,),
                )
                deleted_count = cur.rowcount

                if deleted_count > 0:
                    logger.info(
                        f"[LOCK_CLEANUP] Force-deleted {deleted_count} stuck loader lock(s) "
                        f"(held > {stuck_threshold_seconds}s)"
                    )
        except Exception as e:
            logger.critical(
                f"[LOCK_CLEANUP FAILED] Could not clean expired locks: {e}. Loader pipeline may be blocked!"
            )
            # Don't halt trading, but make this CRITICAL so ops team sees it

    def _wait_for_critical_loaders_proactive(self, max_wait_seconds: int = 300) -> bool:
        """Actively wait for critical loaders to complete before Phase 1.

        Polls data_loader_status for PHASE_1_CRITICAL loaders and waits until they reach
        90%+ completion or timeout. This prevents Phase 1 from running with stale data.

        Strategy:
        1. Query which critical loaders are actively running (status = 'RUNNING', completion_pct < 95)
        2. Poll every 5 seconds, checking for completion
        3. If all critical loaders complete, Phase 1 proceeds immediately
        4. If timeout expires, Phase 1 proceeds anyway but may detect degraded mode

        This is the "proactive" fix vs. the reactive Phase 1 Failsafe which retries AFTER detecting
        staleness. By waiting here, we prevent staleness from being a problem in the first place.

        Args:
            max_wait_seconds: Maximum time to wait for loaders (default 300s = 5 min)

        Returns:
            True if all critical loaders completed within timeout, False if timeout
        """
        from utils.loader_priority import get_critical_loaders

        poll_interval_seconds = 5
        start_time = time.time()
        critical_loaders = get_critical_loaders()

        logger.info(f"\n[PROACTIVE WAIT] Checking for running critical loaders (max wait: {max_wait_seconds}s)...")

        try:
            while time.time() - start_time < max_wait_seconds:
                try:
                    with _owner().DatabaseContext("read", timeout=5) as cur:
                        cur.execute("SET LOCAL statement_timeout = '5000ms'")

                        # Find critical loaders that are still running (incomplete)
                        # CRITICAL FIX 2026-07-31: Use 90% threshold to allow natural data gaps
                        # price_daily loader caps at ~94.6% (5189/5486 symbols) due to delisted/halted stocks.
                        # This is acceptable data quality for trading. Previous 95% threshold would timeout
                        # every day at ~94.6%, causing unnecessary halts. Phase 1 validates actual data quality,
                        # so orchestrator can proceed with 90%+ loaders and let Phase 1 catch data issues.
                        # BUG FOUND 2026-08-10 (live evidence): every status value this table
                        # actually stores is uppercase (LoaderStatus.RUNNING.value == "RUNNING" -
                        # confirmed via `SELECT DISTINCT status FROM data_loader_status`: RUNNING,
                        # COMPLETED, TIMEOUT, etc., never lowercase). Postgres string equality is
                        # case-sensitive by default, so `status = 'running'` never matched a single
                        # row - this half of the OR was silently dead. Live-reproduced: a crashed
                        # mid-run left quality_metrics/growth_metrics (both critical loaders)
                        # status='RUNNING' with completion_pct 95.57%/94.00% (both >=90), so neither
                        # half of the original condition caught them - the proactive wait treated a
                        # genuinely stuck-mid-run critical loader as fine.
                        cur.execute(
                            """
                            SELECT table_name, status, completion_pct, symbols_loaded, symbol_count
                            FROM data_loader_status
                            WHERE table_name = ANY(%s)
                            AND (status = 'RUNNING' OR completion_pct < 90.0)
                            ORDER BY completion_pct ASC
                            """,
                            (list(critical_loaders),),
                        )

                        incomplete_loaders = cur.fetchall()
                        if not incomplete_loaders:
                            logger.info(
                                "[PROACTIVE WAIT] All critical loaders are at 90%+ completion (target threshold)"
                            )
                            return True

                        # Still running - log progress and wait
                        elapsed = time.time() - start_time
                        slowest = incomplete_loaders[0]
                        slowest_name, _, slowest_pct, slowest_loaded, slowest_count = slowest

                        logger.info(
                            f"[PROACTIVE WAIT] {len(incomplete_loaders)} loader(s) still running. "
                            f"Slowest: {slowest_name} ({slowest_pct:.1f}%, {slowest_loaded}/{slowest_count} symbols). "
                            f"Elapsed: {elapsed:.0f}s/{max_wait_seconds}s"
                        )

                        time.sleep(poll_interval_seconds)

                except (psycopg2.DatabaseError, psycopg2.OperationalError) as db_err:
                    logger.warning(f"[PROACTIVE WAIT] Database error during poll: {db_err}. Retrying...")
                    time.sleep(poll_interval_seconds)

            # Timeout expired. Even at 90%+ completion, data is usable. If timeout occurs, it
            # indicates the loader is stalled, not just slow.
            # CRITICAL FIX: this used to say "BLOCKER"/"HALTING orchestration"/"For safety,
            # halt on stalled loaders" - but _wait_for_loaders_before_execution() (the only
            # caller) unconditionally catches this exact RuntimeError and proceeds to Phase 1
            # regardless ("Proceeding to Phase 1 anyway" - by design, since Phase 1 is the
            # real, authoritative data-quality gate that validates and halts if needed; this
            # proactive wait is only a best-effort head start, not a safety gate itself). The
            # halt/blocker language was actively misleading - an operator watching logs would
            # see "CRITICAL: HALTING" and reasonably conclude the orchestrator stopped, when
            # it never does. Describe what this function actually does: escalate to a warning
            # and hand off to Phase 1, not halt anything.
            logger.warning(
                f"[PROACTIVE WAIT] Timeout after {max_wait_seconds}s waiting for loaders to reach 90%+ completion. "
                f"Critical loader {slowest_name} stalled at {slowest_pct:.1f}% ({slowest_loaded}/{slowest_count} symbols). "
                f"Proceeding to Phase 1, which will validate actual data quality and halt there if needed. "
                f"Investigation needed if this recurs: (1) Why is {slowest_name} stalled below 90%? "
                f"(2) yfinance availability issues, (3) EventBridge loader schedules, "
                f"(4) ECS cluster health for stuck loaders"
            )
            raise RuntimeError(
                f"[PROACTIVE WAIT] Critical loader '{slowest_name}' stalled at {slowest_pct:.1f}% complete "
                f"({slowest_loaded}/{slowest_count} symbols) after {max_wait_seconds}s wait. "
                f"Loader appears hung or experiencing systematic failures. "
                f"Halting to investigate and prevent partial data load."
            )

        except RuntimeError:
            # Our own intentionally-raised "loader stalled" signal from the timeout
            # branch above (line ~960) - let it propagate as-is. It must NOT fall into
            # the generic Exception handler below, which would relabel a legitimate
            # stalled-loader condition as a "programming error", misleading anyone
            # reading the logs about what actually happened.
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError, TimeoutError) as e:
            msg = f"[PROACTIVE WAIT] Infrastructure error during loader status check: {e}. Cannot proceed with uncertain loader state."
            logger.error(msg)
            raise RuntimeError(msg) from e
        except Exception as e:
            msg = f"[PROACTIVE WAIT] Unexpected error during proactive wait: {e}. This indicates a programming error or unhandled exception type."
            logger.error(msg)
            raise RuntimeError(msg) from e

    def _check_loader_health(self) -> None:
        """Check if critical loaders have run recently and provide diagnostics.

        Queries data_loader_status to verify critical loaders (prices, technical, scores)
        have been executed and are up-to-date. Non-blocking advisory check that helps
        diagnose data staleness issues before Phase 1 runs.

        Logs warnings if critical loaders are missing or stale (>4 hours old) - this often
        indicates EventBridge is not firing the loader schedule, or loaders are hung.

        CRITICAL: If ALL critical loaders are missing/stale simultaneously, this indicates
        a systemic issue (EventBridge failure, loader infrastructure down). Logs alert.
        """
        from utils.loader_priority import get_critical_loaders

        # Loaders that are critical for trading (MUST run before orchestrator)
        critical_loaders = get_critical_loaders()

        try:
            with _owner().DatabaseContext("read", timeout=5) as cur:
                cur.execute("SET LOCAL statement_timeout = '5000ms'")

                # Check when each critical loader last ran
                cur.execute(
                    """
                    SELECT table_name, status, last_updated, completion_pct, symbols_loaded, symbol_count
                    FROM data_loader_status
                    WHERE table_name = ANY(%s)
                    ORDER BY last_updated DESC
                    """,
                    (list(critical_loaders),),
                )

                loaders_checked = set()
                loader_status = {}
                now_utc = _owner().datetime.now(timezone.utc)
                now_et = now_utc.astimezone(EASTERN_TZ)

                # CRITICAL FIX: Staleness threshold anchors to the most recently completed
                # trading day's close (midnight ET), not a flat hours-ago window - both during
                # market hours (today hasn't closed yet) and before market open want
                # *yesterday's* close as the fresh reference; only after today's own close
                # (16:00 ET) does *today* become the reference.
                #
                # FIX (2026-07-27): this used to be two different computations - a flat 13-hour
                # window during market hours (9 AM-4 PM), and a flat 36-hour window otherwise
                # (that 36h version was already fixed to be trading-day-anchored earlier the same
                # day for the weekend-gap case). Both flat versions shared the same broken
                # assumption: that `last_updated` is a precise per-run completion timestamp. It
                # isn't - pipeline_health.py's log_health_check() deliberately writes
                # last_updated = latest_date (the loaded row's own business date, at midnight ET,
                # not "when this health check ran" - see that function's docstring) for nearly
                # every tracked table. Measured from a midnight-anchored last_updated, a flat 13h
                # window breaches on literally EVERY trading morning (yesterday's close is always
                # >13h before "now" during market hours), not just after a weekend/holiday gap.
                # Live-reproduced 2026-07-27: a Monday 09:07 AM ET dry run (inside the old 9
                # AM-4 PM branch) flagged price_daily/etf_price_daily/technical_data_daily/etc.
                # all STALE despite Friday's close being the correct, most-recent-available data.
                # Reusing the trading-day-anchored logic for both branches removes the flat-hours
                # assumption entirely instead of just widening it further.
                #
                # get_previous_trading_day() returns from_date itself when from_date is already a
                # trading day (it walks backward only while from_date is NOT a trading day) - so
                # both "during market hours" and "before market open" must ask about "yesterday"
                # to correctly land on the last completed trading day (e.g. Friday from a Monday
                # run), while "after close" correctly wants *today* (the orchestrator only runs
                # on trading days, confirmed by the preflight market-calendar check).
                from algo.infrastructure import MarketCalendar

                # BUG FIX 2026-08-24 (goal session: real-money accuracy audit): `hour >= 16` is
                # the same early-close-blind pattern already found and fixed in
                # phase1_data_freshness.py/phase8_entry_execution.py this session - on a NYSE/
                # NASDAQ early close (real close 1:00 PM ET), reference_day stayed "yesterday"
                # until 4 PM instead of flipping to "today" at the real close, making
                # stale_threshold one full trading day too lenient for the 1-4 PM window on
                # those days.
                market_close_today = dt_time(13, 0) if MarketCalendar.is_early_close(now_et.date()) else dt_time(16, 0)
                reference_day = (
                    now_et.date() if now_et.time() >= market_close_today else now_et.date() - timedelta(days=1)
                )
                prev_trading_day = MarketCalendar.get_previous_trading_day(reference_day)
                if prev_trading_day is not None:
                    # Floor at the START of the reference trading day (midnight ET), not its
                    # EOD completion deadline - is_stale is "last_updated < stale_threshold",
                    # so the threshold must be a lower bound a real completed run's timestamp
                    # will land AFTER, not a deadline a real timestamp could still land before.
                    reference_day_start_et = (
                        _owner().datetime.combine(prev_trading_day, dt_time(0, 0)).replace(tzinfo=EASTERN_TZ)
                    )
                    stale_threshold = reference_day_start_et.astimezone(timezone.utc)
                else:
                    stale_threshold = now_utc - timedelta(hours=36)

                for table_name, status, last_updated, completion_pct, symbols_loaded, symbol_count in cur.fetchall():
                    loaders_checked.add(table_name)
                    # CRITICAL FIX: Database stores timestamps as NAIVE in Eastern Time (-05:00).
                    # Convert to UTC for staleness comparison, not assume they're already UTC.
                    if last_updated:
                        last_updated_utc = last_updated.replace(tzinfo=EASTERN_TZ).astimezone(timezone.utc)
                    else:
                        last_updated_utc = None

                    # CRITICAL: Must explicitly determine staleness - no silent assumptions about loader health
                    if last_updated_utc is None:
                        logger.error(
                            f"[LOADER HEALTH] {table_name} cannot determine staleness: last_updated_utc is None. "
                            "Loader status unknown - cannot proceed without explicit timestamp."
                        )
                        raise RuntimeError(
                            f"Cannot determine loader staleness for {table_name}: no last_updated_utc timestamp. "
                            "Loader status unknown, must fail-fast instead of assuming fresh."
                        )

                    # FIX (2026-07-27): price_weekly/price_monthly (and their ETF counterparts)
                    # are, by their own name/cadence, only expected to update roughly once a
                    # week or once a month - the daily-trading-day-anchored stale_threshold
                    # above would flag them "STALE" in literally every health check, forever,
                    # on their best day right after a successful run. A warning that always
                    # fires trains operators to ignore it (alert fatigue), which defeats the
                    # point of the check. Give these two known non-daily-cadence tables their
                    # own wider floor instead of the daily one.
                    # FIX (2026-07-27): earnings_calendar is forward-looking calendar data (next
                    # scheduled earnings dates), not a daily price/technical series - new rows
                    # only land when a company announces or updates a date, so multi-day gaps
                    # between refreshes are normal, not a sign of a broken loader.
                    # algo/monitoring/pipeline_health.py already treats it this way explicitly
                    # (CRITICAL_TABLES["earnings_calendar"]["sla_days"] = 30, vs. 1 day for
                    # price_daily) - this check had no matching override, so it kept flagging
                    # earnings_calendar STALE using the same daily-trading-day threshold as
                    # price_daily. Live-reproduced 2026-07-27: flagged STALE at 105.2h old (~4.4
                    # days) even after the market-hours fix above, well inside its real 30-day SLA.
                    if table_name in ("price_weekly", "etf_price_weekly"):
                        table_stale_threshold = now_utc - timedelta(days=10)
                    elif table_name in ("price_monthly", "etf_price_monthly"):
                        table_stale_threshold = now_utc - timedelta(days=40)
                    elif table_name == "earnings_calendar":
                        table_stale_threshold = now_utc - timedelta(days=30)
                    else:
                        table_stale_threshold = stale_threshold
                    is_stale = last_updated_utc < table_stale_threshold

                    # CRITICAL: completion_pct is None only if database query failed or loader hasn't reported yet
                    # Treat None as incomplete (fail-safe) - don't silently use 0 (which looks like successful 0% load)
                    if completion_pct is None:
                        is_complete = False
                        logger.error(
                            f"[LOADER HEALTH] {table_name} completion_pct is NULL (database error or loader never reported). "
                            "Treating as incomplete until next status update."
                        )
                    else:
                        is_complete = completion_pct >= 90.0

                    loader_status[table_name] = {
                        "status": status,
                        "last_updated": last_updated_utc,
                        "is_stale": is_stale,
                        "is_complete": is_complete,
                        "completion_pct": completion_pct,
                    }

                    if is_stale:
                        # NOTE: last_updated cannot be None here (would have raised error on line 826)
                        # This null check was defensive but dead code - last_updated_utc is guaranteed valid
                        age_hours = (now_utc - last_updated_utc).total_seconds() / 3600
                        logger.warning(f"[LOADER HEALTH] {table_name} is STALE (last run {age_hours:.1f}h ago)")
                    elif not is_complete:
                        if completion_pct is None:
                            logger.warning(
                                f"[LOADER HEALTH] {table_name} is INCOMPLETE (completion_pct=NULL, status={status})"
                            )
                        else:
                            logger.warning(
                                f"[LOADER HEALTH] {table_name} is INCOMPLETE ({completion_pct:.1f}%, "
                                f"{symbols_loaded}/{symbol_count} symbols)"
                            )
                    else:
                        logger.info(f"[LOADER HEALTH] {table_name} OK ({completion_pct:.1f}%)")

                # Check for missing critical loaders
                missing_loaders = critical_loaders - loaders_checked
                stale_loaders = [name for name, status in loader_status.items() if status["is_stale"]]

                if missing_loaders:
                    logger.warning(
                        f"[LOADER HEALTH] MISSING in data_loader_status: {missing_loaders} "
                        "(loaders have never run or been registered)"
                    )

                # ESCALATION: If all critical loaders are stale/missing, this is a systemic issue
                # (likely EventBridge failure or loader infrastructure down)
                # FIXED: Detect hung loaders (partial completion 1-94%), not just 0% or missing
                all_loaders_checked = dict(loader_status)
                all_stale_or_missing = len(all_loaders_checked) > 0 and all(
                    status["is_stale"] or status["completion_pct"] is None or not status.get("is_complete")
                    for status in all_loaders_checked.values()
                )

                if all_stale_or_missing and (stale_loaders or missing_loaders):
                    # LOCAL_MODE failsafe will refresh stale loaders, so don't fail pre-flight
                    local_mode = os.getenv("LOCAL_MODE", "").lower() in ("1", "true", "yes")

                    if not local_mode:
                        logger.critical(
                            f"[LOADER HEALTH] SYSTEMIC ALERT: ALL critical loaders are stale or missing. "
                            f"This indicates EventBridge may not be firing loader schedules, or loader "
                            f"infrastructure is down. Stale: {stale_loaders}. Missing: {missing_loaders}. "
                            f"Check: EventBridge rules, ECS cluster health, CloudWatch logs for loaders."
                        )
                        try:
                            self.alerts.send_position_alert(
                                "LOADER_INFRASTRUCTURE",
                                "ALL_CRITICAL_LOADERS_STALE",
                                f"All critical loaders are stale/missing (stale: {len(stale_loaders)}, "
                                f"missing: {len(missing_loaders)}). EventBridge or loader infrastructure issue.",
                                {"stale_loaders": stale_loaders, "missing_loaders": list(missing_loaders)},
                            )
                        except Exception as alert_err:
                            logger.debug(f"[LOADER HEALTH] Could not send alert: {alert_err}")

                        # FIXED: Remove paper mode bypass - data integrity is non-negotiable
                        # Paper trading still requires fresh data to be trustworthy for testing
                        # If loaders aren't running, fix the loader infrastructure, don't bypass validation
                        raise RuntimeError(
                            f"[ORCHESTRATOR] CRITICAL HALT: All critical loaders are stale/missing. "
                            f"Cannot proceed with trading (live or paper) using stale data. "
                            f"Paper mode does NOT bypass data validation - test data must be fresh too. "
                            f"Stale loaders: {stale_loaders}. Missing loaders: {missing_loaders}. "
                            f"Fix: (1) Verify EventBridge scheduler firing loader pipelines, "
                            f"(2) Check ECS cluster has capacity to run loader tasks, "
                            f"(3) Review CloudWatch logs for loader failures, "
                            f"(4) Verify database connection pool has available connections, "
                            f"(5) Check if loader infrastructure (S3, Alpaca, yfinance) is accessible."
                        )
                    else:
                        # LOCAL_MODE: log as warning, Phase 1 failsafe will handle refresh
                        logger.warning(
                            f"[LOADER HEALTH] All loaders stale/missing - LOCAL_MODE will refresh. "
                            f"Stale: {stale_loaders}. Missing: {missing_loaders}."
                        )

        except (psycopg2.DatabaseError, psycopg2.OperationalError, TimeoutError) as e:
            logger.warning(f"[LOADER HEALTH] Could not check loader status: {e}")
            # If we can't check loader health, HALT (don't assume data is fresh)
            raise RuntimeError(
                f"[ORCHESTRATOR] CRITICAL: Cannot verify loader health: {e}. "
                f"Halting trading - unable to confirm data freshness."
            ) from e
        except RuntimeError:
            # The deliberate "CRITICAL HALT: All critical loaders are stale/missing" raise
            # above is expected control flow for a known condition (caller catches RuntimeError
            # and defers to Phase 1's own re-check), not a bug in this health-check logic.
            # Letting it fall into the generic `except Exception` below double-wrapped it as
            # "[LOADER HEALTH] UNEXPECTED ERROR ... unexpected runtime error in the health
            # check logic" - misleading an operator into debugging this function instead of
            # the actual loader/EventBridge infrastructure the message already pointed at.
            raise
        except Exception as e:
            logger.error(
                f"[LOADER HEALTH] UNEXPECTED ERROR checking loader health: {e}. "
                f"This indicates an unexpected runtime error in the health check logic. "
                f"Halting trading to prevent operating with unverified loader state."
            )
            raise RuntimeError(
                f"[ORCHESTRATOR] Unexpected error during loader health check: {e}. "
                f"Cannot proceed with trading until loader health verification succeeds."
            ) from e
