"""Phase-1-cache invalidation, weekly/monthly bar derivation, and loader-execution logging
for load_prices.py, extracted from that file (2026-09-05, file-size ratchet: it's the largest
Tier-1 bloater flagged for decomposition). Bodies are verbatim, no logic changed - only moved
file.

`DatabaseContext`/`LoaderStatusManager` are accessed via the load_prices module object at call
time (not imported by name here) because several existing tests patch
`loaders.load_prices.DatabaseContext` expecting that to affect these functions - a plain import
here would silently stop seeing those patches.
"""

import logging
import os
import time
from datetime import date, timedelta
from typing import Any

import psycopg2

import loaders.load_prices as _lp
from utils.db.sql_safety import assert_safe_table
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)


def _invalidate_phase1_cache() -> None:
    """Invalidate Phase 1 cache to force fresh status check on next run.

    Called on loader failure to ensure Phase 1 doesn't use stale cached data.
    CRITICAL: If invalidation fails, marks cache with 'invalidation_failed' flag
    so Phase 1 knows not to use it. If that also fails, raises RuntimeError to
    halt the loader and prevent silent stale-data use.

    In LOCAL_MODE, skips DynamoDB operations since credentials unavailable.

    ISSUE #2 FIX: Three-tier approach:
    1. Try to delete cache (best case)
    2. If delete fails, mark as poisoned so Phase 1 skips it
    3. If both fail and not a permission error, halt loader immediately
    4. If permission error or LOCAL_MODE, log warning and allow loader to continue
    """
    from datetime import datetime

    import boto3
    from botocore.exceptions import ClientError

    local_mode = os.getenv("LOCAL_MODE", "").lower() in ("1", "true", "yes")
    if local_mode:
        logger.info("[CACHE INVALIDATION] LOCAL_MODE enabled - skipping DynamoDB cache invalidation")
        return

    # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
    try:
        aws_region = os.getenv("AWS_REGION")
        if not aws_region:
            logger.error("[CACHE INVALIDATION] AWS_REGION not set. Cannot invalidate cache.")
            return

        cache_date = datetime.now(EASTERN_TZ).date()
        cache_key = f"data_loader_status-{cache_date.isoformat()}"
        cache_table_name = os.getenv("CACHE_TABLE", "algo_phase1_cache")
        dynamodb = boto3.resource("dynamodb", region_name=aws_region)
        cache_table = dynamodb.Table(cache_table_name)

        try:
            # Step 1: Try direct deletion
            cache_table.delete_item(Key={"cache_key": cache_key})
            logger.info(
                "[CACHE INVALIDATION]  Successfully deleted Phase 1 cache: %s",
                cache_key,
            )
            return
        except ClientError as delete_err:
            error_dict = delete_err.response.get("Error")
            # Same treatment as AccessDenied: any of these codes mean the credentials in
            # use fundamentally cannot talk to DynamoDB right now (invalid/expired/unknown
            # token) - functionally identical to a permission denial from the loader's
            # perspective. Without this, local dev runs (no working AWS credentials, the
            # normal state per CLAUDE.md's local mode) hit the generic branch below,
            # "successfully" fail to poison too for the same credential reason, and hit
            # the Step 3 hard RuntimeError - discarding an otherwise-successful price load
            # and orphaning loader_execution_locks (confirmed live 2026-07-20: a full
            # 10K-symbol fetch completed, then got thrown away here).
            if error_dict and error_dict.get("Code") in (
                "AccessDenied",
                "AccessDeniedException",
                "UnrecognizedClientException",
                "InvalidClientTokenId",
                "ExpiredTokenException",
                "InvalidSignatureException",
            ):
                logger.warning(
                    "[CACHE INVALIDATION] DynamoDB unusable (%s): No DynamoDB write access. "
                    "Loader will proceed without cache invalidation (risk: may use stale data from previous run).",
                    error_dict.get("Code"),
                )
                return
            logger.error(
                f"[CACHE INVALIDATION] DELETE FAILED: {type(delete_err).__name__}: {delete_err}. Attempting cache poisoning..."
            )
        except Exception as delete_err:
            logger.error(
                f"[CACHE INVALIDATION] DELETE FAILED: {type(delete_err).__name__}: {delete_err}. Attempting cache poisoning..."
            )

        # Step 2: If delete failed, try to poison the cache so Phase 1 knows not to use it
        try:
            from decimal import Decimal

            cache_table.update_item(
                Key={"cache_key": cache_key},
                UpdateExpression="SET invalidation_failed = :true, poisoned_at = :now",
                ExpressionAttributeValues={
                    ":true": True,
                    ":now": Decimal(str(time.time())),
                },
            )
            logger.warning(
                "[CACHE INVALIDATION] POISONED cache (set invalidation_failed=true) - Phase 1 will skip stale data"
            )
            return
        except ClientError as poison_err:
            error_dict = poison_err.response.get("Error")
            # See matching comment on the delete-path ClientError handler above.
            if error_dict and error_dict.get("Code") in (
                "AccessDenied",
                "AccessDeniedException",
                "UnrecognizedClientException",
                "InvalidClientTokenId",
                "ExpiredTokenException",
                "InvalidSignatureException",
            ):
                logger.warning(
                    "[CACHE INVALIDATION] DynamoDB unusable (%s): No DynamoDB write access. "
                    "Loader will proceed without cache invalidation (risk: may use stale data from previous run).",
                    error_dict.get("Code"),
                )
                return
            logger.error(
                "[CACHE INVALIDATION] POISONING ALSO FAILED: %s: %s",
                type(poison_err).__name__,
                poison_err,
            )
        except (ValueError, ZeroDivisionError, TypeError) as poison_err:
            logger.error(
                "[CACHE INVALIDATION] POISONING ALSO FAILED: %s: %s",
                type(poison_err).__name__,
                poison_err,
            )

    except (ValueError, ZeroDivisionError, TypeError) as setup_err:
        logger.error("[CACHE INVALIDATION] Setup error: %s", setup_err)

    # Step 3: Both deletion AND poisoning failed - CRITICAL: MUST HALT
    logger.critical(
        "[CACHE INVALIDATION] CRITICAL FAILURE: Could not delete OR poison cache. "
        "Phase 1 will potentially use stale data. HALTING LOADER IMMEDIATELY."
    )
    raise RuntimeError(
        "CRITICAL: Cache invalidation completely failed (cannot delete or poison). "
        "Halting loader to prevent silent stale-data corruption."
    )


def derive_aggregate_prices(asset_class: str) -> None:
    """Derive weekly/monthly bars from the daily table in SQL (no API fetches).

    Replaces fetching 1wk/1mo bars from yfinance for the whole universe (~10,700
    requests/day when it ran; production disabled those fetches on 2026-07-10 which
    left price_weekly/price_monthly with live readers - signal_patterns,
    market_factor_calculator, dashboard price routes - and a critical 7-day Phase 1
    freshness gate, but NO writer). Bar labeling matches the yfinance rows already in
    the tables: weekly bars keyed by week start (Monday), monthly by the 1st.

    The derivation window starts one full period before the target table's own
    MAX(date), so the in-progress and prior period always heal, and any gap since the
    last successful derivation auto-backfills. An empty target table backfills from
    the entire daily history. Daily marker rows (NULL close) are excluded.
    """
    if asset_class == "etf":
        daily_table = "etf_price_daily"
        targets = (("etf_price_weekly", "week", 28), ("etf_price_monthly", "month", 92))
        # ETF tables predate migration 114 and may lack data_unavailable columns.
        reset_unavailable_flag = ""
    else:
        daily_table = "price_daily"
        targets = (("price_weekly", "week", 28), ("price_monthly", "month", 92))
        # A derived bar is real data: clear any marker state left by old loader runs
        # (CHECK constraint requires reason NULL when flag is false).
        reset_unavailable_flag = ", data_unavailable = FALSE, data_unavailable_reason = NULL"

    assert_safe_table(daily_table)
    for target_table, period, heal_days in targets:
        assert_safe_table(target_table)
        with _lp.DatabaseContext("write") as cur:  # type: ignore[attr-defined]
            cur.execute(f"SELECT MAX(date) FROM {target_table}")
            row = cur.fetchone()
            last_derived: date | None = row[0] if row and row[0] is not None else None

            date_filter = ""
            params: tuple[Any, ...] = ()
            if last_derived is not None:
                date_filter = "AND date >= %s"
                params = (last_derived - timedelta(days=heal_days),)

            cur.execute(
                f"""
                INSERT INTO {target_table} (symbol, date, open, high, low, close, volume)
                SELECT symbol,
                       date_trunc('{period}', date)::date AS period_start,
                       (array_agg(open ORDER BY date ASC) FILTER (WHERE open IS NOT NULL))[1],
                       MAX(high),
                       MIN(low),
                       (array_agg(close ORDER BY date DESC) FILTER (WHERE close IS NOT NULL))[1],
                       SUM(volume)
                FROM {daily_table}
                WHERE close IS NOT NULL {date_filter}
                GROUP BY symbol, date_trunc('{period}', date)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume{reset_unavailable_flag}
                """,
                params,
            )
            derived_rows = cur.rowcount
            logger.info(
                f"[DERIVE] {target_table}: upserted {derived_rows} {period}ly bars from {daily_table} "
                f"(window start: {params[0] if params else 'full history'})"
            )

            # Keep freshness gates green: derived tables report loader status like any
            # other loader (Phase 1 checks data_loader_status for these table names).
            cur.execute(f"SELECT MAX(date) FROM {target_table}")
            latest_row = cur.fetchone()
            latest_date = latest_row[0] if latest_row else None

        # Use LoaderStatusManager for centralized status update (RACE CONDITION FIX)
        #
        # BUG FOUND 2026-08-10: this never called mark_running()/update_progress() before
        # mark_completed(), so its own safety check fell back to reading symbol_count/
        # symbols_loaded from the DB row - which this derivation never populates at all
        # (it's a bulk SQL upsert, not a per-symbol loop). Live-confirmed: symbols_loaded
        # stuck at 0 while symbol_count held a stale value from an unrelated prior run
        # (10594/19), so every single derivation - success or not - computed 0% completion
        # and got marked FAILED, even though the upsert genuinely succeeded. This silently
        # broke health monitoring for price_weekly/price_monthly/etf_price_weekly/
        # etf_price_monthly on every price_daily load. Pass this run's own real row count
        # (derived_rows) as both loaded/total - 100% by construction, since the INSERT
        # either upserts all `derived_rows` rows or the whole DatabaseContext block raises
        # (no partial-failure concept for a single atomic SQL statement). min_completion_pct
        # =0.0 additionally covers the legitimate 0-row case (nothing new to derive since
        # the last successful run - not a failure).
        status_mgr = _lp.LoaderStatusManager(target_table)  # type: ignore[attr-defined]
        status_mgr.mark_completed(
            latest_date=latest_date,
            current_run_symbols_loaded=derived_rows,
            current_run_symbol_count=derived_rows,
            min_completion_pct=0.0,
        )


def log_loader_execution(
    loader_name: str,
    table_name: str,
    status: str,
    records_loaded: int = 0,
    records_updated: int = 0,
    error_msg: str | None = None,
    duration_seconds: float = 0,
) -> None:
    """Log loader execution to data_loader_runs table for monitoring."""
    from datetime import datetime

    try:
        with _lp.DatabaseContext("write") as cur:  # type: ignore[attr-defined]
            # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
            run_date = datetime.now(EASTERN_TZ).date()
            # FIX: started_at must be recomputed (NOW() - this run's own duration) on every
            # write, not just the initial INSERT. Previously ON CONFLICT DO UPDATE omitted
            # started_at, so a retried loader on the same run_date kept whatever started_at
            # the FIRST attempt that day had - completed_at kept advancing to NOW() on each
            # retry while started_at stayed frozen, making completed_at - started_at balloon
            # to hours even when the loader's own measured duration_seconds was seconds.
            # Live-confirmed on price_daily (2026-08-19 loader-health review): duration_seconds
            # showed 39.59s for the actual run but completed_at - started_at showed 1h36m
            # because an earlier same-day attempt's started_at was never refreshed.
            cur.execute(
                """
                INSERT INTO data_loader_runs (
                    loader_name, table_name, run_date, status, records_loaded, records_updated,
                    error_message, duration_seconds, started_at, completed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, NOW() - (%s * interval '1 second'), NOW()
                )
                ON CONFLICT (loader_name, run_date) DO UPDATE SET
                    status = EXCLUDED.status,
                    records_loaded = EXCLUDED.records_loaded,
                    records_updated = EXCLUDED.records_updated,
                    error_message = EXCLUDED.error_message,
                    duration_seconds = EXCLUDED.duration_seconds,
                    started_at = EXCLUDED.started_at,
                    completed_at = NOW()
            """,
                (
                    loader_name,
                    table_name,
                    run_date,
                    status,
                    records_loaded,
                    records_updated,
                    error_msg,
                    duration_seconds,
                    duration_seconds,
                ),
            )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.critical("[LOADER_EXECUTION_LOG] Failed to log execution to data_loader_runs: %s", e)
        raise
