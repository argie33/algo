"""Production-grade data loader base class with separated infrastructure concerns."""

import logging
import os
import time
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any, cast

from utils.bulk_insert_manager import BulkInsertManager
from utils.data.watermark import WatermarkManager
from utils.db.context import DatabaseContext
from utils.loader_infrastructure import LoaderInfrastructure
from utils.loader_stats import LoaderStats
from utils.loaders.transient_errors import TransientAPIError

if not logging.root.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=None)

logger = logging.getLogger(__name__)


class OptimalLoader:
    """Base class for production-grade loaders with separated infrastructure.

    Delegates: LoaderInfrastructure (signals, heartbeat, status, RDS monitoring),
    LoaderStats (thread-safe stats), WatermarkManager (watermark persistence),
    BulkInsertManager (schema validation, bulk inserts).
    """

    table_name: str = ""
    primary_key: Sequence[str] = ()
    watermark_field: str = "date"
    chunk_size: int = 10_000
    max_age_for_full_refresh: timedelta = timedelta(days=365)
    is_symbol_based: bool = True

    def __init__(self, backfill_days: int | None = None):
        self._router: Any = None
        # ISSUE #14 FIX: Validate BACKFILL_DAYS configuration
        # Prevents accidental full historical reloads or invalid negative values
        if backfill_days is not None:
            self._backfill_days = backfill_days
        else:
            try:
                backfill_env = os.getenv("BACKFILL_DAYS", "0")
                self._backfill_days = int(backfill_env)
                # Validate BACKFILL_DAYS is reasonable (0-730 days = 2 years max)
                if self._backfill_days < 0:
                    raise ValueError(
                        f"[CONFIG] BACKFILL_DAYS cannot be negative (got {self._backfill_days}). "
                        "Use 0 for incremental load, or positive value for backfill."
                    )
                from loaders.config import get_loader_max_backfill_days
                max_backfill = get_loader_max_backfill_days()
                if self._backfill_days > max_backfill:
                    raise ValueError(
                        f"[CONFIG] BACKFILL_DAYS={self._backfill_days} exceeds configured maximum ({max_backfill} days). "
                        "Full backfills risk excessive load times and API rate limits. "
                        f"Use incremental load (BACKFILL_DAYS=0) or smaller backfill window (max {max_backfill} days). "
                        f"Override with LOADER_MAX_BACKFILL_DAYS environment variable."
                    )
            except ValueError as e:
                if "invalid literal" in str(e):
                    raise ValueError(
                        f"[CONFIG] BACKFILL_DAYS is not a valid integer: '{backfill_env}'. "
                        "Set to 0 (incremental) or positive number of days."
                    ) from e
                raise

        self._batch_context: dict[str, Any] | None = None
        self._execution_start_time: float | None = None

        self._infrastructure = LoaderInfrastructure(self.table_name)
        self._stats = LoaderStats()
        from utils.loaders.status_manager import LoaderStatusManager
        self._status_manager = LoaderStatusManager(self.table_name)
        # CRITICAL FIX: Derive loader_name from the class's source file, not self.__class__.__module__.
        # __module__ depends on *how* Python was invoked: every loader here is normally launched as
        # `python3 loaders/load_x.py` (see scripts/local_loader_scheduler.py, terraform loader tasks),
        # which makes CPython set that script's module name - and therefore every class defined in
        # it - to "__main__", not "loaders.load_x". A prior fix (this same line) switched from
        # self.table_name to self.__class__.__module__.split(".")[-1], which only resolves correctly
        # when the loader is imported as a module (e.g. `import loaders.load_x`); run the normal way,
        # every loader collides into a single loader="__main__" bucket in loader_watermarks, so any
        # two symbols/loaders sharing that bucket silently overwrite each other's incremental
        # watermark. inspect.getfile() returns the real source path regardless of invocation style.
        import inspect
        from pathlib import Path

        loader_module_name = Path(inspect.getfile(self.__class__)).stem
        self._watermark = WatermarkManager(loader_module_name, self.table_name)
        self._bulk_insert_mgr = BulkInsertManager(self.table_name, self.primary_key, self.chunk_size)
        self._last_health_check_update = 0.0  # Track health check updates

        self._configure_chunk_size()
        self._init_health_check()

    def _configure_chunk_size(self) -> None:
        env_chunk_size = os.getenv("LOADER_CHUNK_SIZE")
        if env_chunk_size:
            try:
                configured_size = int(env_chunk_size)
                if 100 <= configured_size <= 100_000:
                    self.chunk_size = configured_size
                    self._bulk_insert_mgr.chunk_size = configured_size
                    logger.info(f"[CONFIG] LOADER_CHUNK_SIZE={configured_size}")
                    return
            except ValueError:
                pass
        # chunk_size is the DATABASE INSERT chunk (rows per staging COPY+upsert), not an
        # API batch - the old 100-500 AWS cap was justified as "avoid yfinance rate
        # limiting", which this setting has nothing to do with. Small chunks just
        # multiply staging-table cycles and round trips. Bound by task memory instead.
        lambda_func_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME")
        exec_env = os.getenv("AWS_EXECUTION_ENV")
        is_aws = bool(lambda_func_name is not None or exec_env is not None)
        memory_limit_mb = int(os.getenv("ECS_TASK_MEMORY_LIMIT", "512"))
        safe_rows = int((memory_limit_mb * 0.40 * 1024) / 1.5)

        if is_aws:
            self.chunk_size = max(1_000, min(10_000, safe_rows))
        else:
            # Local: use larger batches
            self.chunk_size = max(2_000, min(50_000, safe_rows))
        self._bulk_insert_mgr.chunk_size = self.chunk_size
        logger.info(f"[CONFIG] Batch size set to {self.chunk_size} (AWS={is_aws})")

    def _init_health_check(self) -> None:
        """Initialize ECS health check file for liveness detection."""
        health_file = "/tmp/loader_health_check"
        try:
            with open(health_file, "w") as f:
                f.write(datetime.now(timezone.utc).isoformat())
            logger.debug(f"[HEALTHCHECK] Initialized: {health_file}")
        except OSError:
            logger.warning(f"[HEALTHCHECK] Failed to initialize (may be local dev mode): {health_file}")

    def _update_health_check(self) -> None:
        """Update ECS health check file to signal loader is responsive."""
        health_file = "/tmp/loader_health_check"
        now = time.time()

        # Update every 5 seconds to avoid excessive I/O
        if now - self._last_health_check_update < 5:
            return

        try:
            with open(health_file, "w") as f:
                f.write(datetime.now(timezone.utc).isoformat())
            self._last_health_check_update = now
        except OSError:
            # Silently fail - may be local dev mode without /tmp/
            pass

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]] | None:
        raise NotImplementedError("Implement fetch_incremental or fetch_global")

    def fetch_global(self, since: date | None) -> list[dict[str, Any]] | dict[str, Any]:
        """Fetch global data. Override in subclasses that implement global load patterns.

        Returns:
            list[dict]: Data rows if available.
            dict: Marker dict with data_unavailable=True if not implemented by subclass.

        Note: Return explicit data_unavailable marker instead of None for unimplemented loaders.
        """
        return {"data_unavailable": True, "reason": "fetch_global_not_implemented_by_subclass"}

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return rows

    def watermark_from_rows(self, rows: list[dict[str, Any]]) -> date:
        """Extract watermark (max date) from rows.

        Args:
            rows: List of data rows to extract watermark from.

        Returns:
            Maximum date value from watermark_field.

        Raises:
            ValueError: If rows are empty (should not call with empty rows) or
                       if rows present but critical watermark_field is missing.
        """
        if not rows:
            # Empty result set-should not call with empty rows
            raise ValueError(
                f"[{self.table_name}] watermark_from_rows called with empty rows (should never happen). "
                "This is a programming error-check caller before invoking."
            )

        # Extract all non-None values of watermark_field with fail-fast validation
        values: list[date] = []
        for r in rows:
            if self.watermark_field not in r:
                raise ValueError(
                    f"[{self.table_name}] Row missing critical watermark field '{self.watermark_field}': {r}"
                )
            field_value = r[self.watermark_field]
            if field_value is not None:
                # Convert string dates to date objects (field may come from transformers as strings)
                if isinstance(field_value, str):
                    try:
                        from datetime import datetime as dt

                        field_value = dt.fromisoformat(field_value).date()
                    except (ValueError, AttributeError) as e:
                        raise ValueError(
                            f"[{self.table_name}] Cannot parse {self.watermark_field} as date: '{field_value}'. "
                            f"Expected ISO format (YYYY-MM-DD). Error: {e}"
                        ) from e
                values.append(cast(date, field_value))

        if not values:
            raise ValueError(
                f"[{self.table_name}] watermark_from_rows: {len(rows)} rows present but all {self.watermark_field} values are NULL"
            )
        return max(values)

    @property
    def max_fail_rate(self) -> float:
        """Maximum percentage of symbols allowed to fail before marking load as failed.

        Default: 5% (conservative). Subclasses can override for different requirements.
        Price loader: 2% (critical data, high failure is a blocker).
        SEC/financial data: 5% (more lenient, API rate limiting is expected).
        """
        if hasattr(self, "_override_max_fail_rate"):
            return self._override_max_fail_rate
        from loaders.config import get_loader_max_fail_rate
        return get_loader_max_fail_rate("default")

    @max_fail_rate.setter
    def max_fail_rate(self, value: float) -> None:
        """Allow tests to override max_fail_rate."""
        self._override_max_fail_rate = value

    @property
    def router(self) -> Any:
        if self._router is None:
            from utils.data.source_router import DataSourceRouter

            self._router = DataSourceRouter()
        return self._router

    def load_symbol(self, symbol: str) -> int:
        previous_date = None
        if self._backfill_days > 0:
            previous_date = datetime.now(timezone.utc).date() - timedelta(days=self._backfill_days)
        else:
            watermark_value = self._watermark.get_current_watermark(symbol=symbol)
            previous_date = watermark_value

        # CRITICAL FIX (Session 263 EXTENDED): Watermark initialization for buy_sell_daily
        # Root cause: Loader running on weekends used calendar date (today) as watermark,
        # then queried for NEW signals AFTER market close = empty fetch = stale data
        # Solution: If watermark is None OR >= most_recent_trading_day, reset to enable full lookback
        if self.table_name == "buy_sell_daily" and self._backfill_days == 0:
            try:
                from algo.infrastructure import MarketCalendar
                from utils.infrastructure.timezone import EASTERN_TZ

                now_et = datetime.now(EASTERN_TZ)
                today_et = now_et.date()

                # Find most recent trading day (may be 1-3 days back on weekends/holidays)
                most_recent_trading_day = today_et
                for _ in range(10):
                    if MarketCalendar.is_trading_day(most_recent_trading_day):
                        break
                    most_recent_trading_day -= timedelta(days=1)

                # CASE 1: No watermark exists (first run or new symbol)
                # → Load full lookback window (fetch_incremental will use 120-day window)
                if previous_date is None:
                    logger.info(
                        f"[{self.table_name}] {symbol}: No watermark exists. "
                        f"Will load full lookback window (most recent trading day: {most_recent_trading_day})"
                    )

                # CASE 2: Watermark is on/after most_recent_trading_day (loaded today's/weekend's calendar date)
                # → Reset to None to force full lookback (prevents searching after market close)
                elif previous_date >= most_recent_trading_day:
                    days_ahead = (previous_date - most_recent_trading_day).days
                    logger.warning(
                        f"[{self.table_name}] {symbol}: Watermark {previous_date} is {days_ahead}+ days "
                        f"ahead of most recent trading day {most_recent_trading_day}. "
                        f"This indicates loader may have run on weekend/after-hours with calendar date. "
                        f"Resetting to None to force full lookback window."
                    )
                    previous_date = None

                # CASE 3: Watermark is stale (>7 trading days behind)
                # → Log warning, proceed with incremental load but orchestrator should retry
                else:
                    calendar_days_behind = (most_recent_trading_day - previous_date).days
                    if calendar_days_behind > 7:
                        logger.error(
                            f"[{self.table_name}] {symbol}: Watermark is {calendar_days_behind} calendar days old "
                            f"(watermark: {previous_date}, most recent trading day: {most_recent_trading_day}). "
                            f"Loader has not run in 5+ trading days. This indicates missed runs or persistent failure."
                        )

            except Exception as e:
                logger.warning(
                    f"[{self.table_name}] {symbol}: Trading day detection failed ({e}). "
                    f"Using watermark={previous_date} as-is (may be stale or invalid)."
                )

        logger.debug(f"[{self.table_name}] {symbol}: watermark={previous_date}, backfill_days={self._backfill_days}")

        # Retry transient API errors (timeouts, connection errors) with exponential backoff
        max_attempts = 3
        last_exception: Exception | None = None

        rows = None
        for attempt in range(1, max_attempts + 1):
            try:
                rows = self.fetch_incremental(symbol, previous_date)
                if rows is None:
                    raise RuntimeError(
                        f"[{self.table_name}] {symbol}: fetch_incremental returned None instead of list. "
                        "Subclass must return list[dict] or raise exception, never return None."
                    )
                if attempt > 1:
                    logger.info(f"[{self.table_name}] {symbol}: Success on attempt {attempt}/{max_attempts}")
                break
            except TransientAPIError as e:
                last_exception = e
                if attempt < max_attempts:
                    delay = min(2.0 * (2.0 ** (attempt - 1)), 30.0)
                    logger.warning(
                        f"[{self.table_name}] {symbol}: Transient API error on attempt {attempt}/{max_attempts}, "
                        f"retrying in {delay:.1f}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"[{self.table_name}] {symbol}: All {max_attempts} attempts failed due to transient errors: {e}"
                    )
            except Exception as e:
                logger.error(f"[{self.table_name}] {symbol}: Failed to fetch (non-transient error): {e}")
                raise RuntimeError(f"[{self.table_name}] {symbol}: Failed to fetch: {e}") from e

        if last_exception is not None:
            raise RuntimeError(
                f"[{self.table_name}] {symbol}: Failed to fetch after {max_attempts} attempts due to transient errors"
            ) from last_exception

        if rows is None or not rows:
            # No new data since watermark - EXPECTED for incremental loads (most symbols have
            # nothing new on most runs, e.g. no new SEC filing, no new signal, no price change
            # since the last successful watermark). Was logged at WARNING despite this comment
            # already documenting it as expected - on a full-universe run (~5000 symbols) this
            # fires for most/all of them, drowning genuinely rare WARNING-level signals in noise
            # (confirmed live: one run logged 4753 of these against price/signal data that
            # legitimately hadn't changed since Friday's close, vs. single digits of every other
            # WARNING/ERROR combined). The aggregate count is already surfaced properly via
            # self._stats -> MetricsPublisher.put_loader_result and the loader's own return
            # value, so nothing operationally useful is lost by not also logging each one at
            # WARNING. DEBUG keeps it available for local troubleshooting without alert fatigue.
            logger.debug(
                f"[{self.table_name}] {symbol}: Empty result from fetch_incremental (previous={previous_date}), rows={len(rows) if rows else 'None'}, skipping"
            )
            self._stats.increment("symbols_skipped_by_watermark")
            return 0

        logger.debug(f"[{self.table_name}] {symbol}: fetch_incremental returned {len(rows)} rows")
        self._stats.increment("rows_fetched", len(rows))
        if self.router and self.router.last_source:
            self._stats.add_source(self.router.last_source)

        rows = self.transform(rows)
        logger.debug(f"[{self.table_name}] {symbol}: After transform, {len(rows)} rows")
        validated_rows = []
        rows_rejected = 0
        for i, r in enumerate(rows):
            try:
                # CRITICAL FIX: the return value of _validate_row() was previously discarded -
                # only a raised ValueError (missing/None primary key) had any effect. Subclass
                # overrides that signal a bad row by returning False (e.g. PriceLoader's OHLC
                # sanity check: high>=low, close>0, open>0) were silently no-ops - the row was
                # appended and inserted regardless. Confirmed 2026-07-21: a row with negative
                # low, or close/open outside the [low, high] range, would pass straight through
                # to price_daily and corrupt every downstream technical indicator/position-sizing/
                # P&L calculation that reads it. A per-row False now skips just that row (not a
                # fail-fast crash of the whole symbol - a single bad tick is a routine data-quality
                # event, not evidence of systemic corruption the way a missing primary key is).
                if not self._validate_row(r):
                    rows_rejected += 1
                    logger.warning(f"[{self.table_name}] {symbol}: Row {i} rejected by validation, skipping: {r}")
                    continue
                validated_rows.append(r)
            except ValueError as e:
                logger.error(f"[{self.table_name}] {symbol}: Row {i} validation failed: {e}")
                raise ValueError(f"Row {i} failed validation: {e}") from e
        if rows_rejected:
            self._stats.increment("rows_rejected_by_validation", rows_rejected)

        logger.debug(f"[{self.table_name}] {symbol}: {len(validated_rows)} rows passed validation")
        if not validated_rows:
            logger.warning(f"[{self.table_name}] {symbol}: No rows passed validation, skipping")
            return 0

        rows = validated_rows
        new_wm = self.watermark_from_rows(rows)
        inserted = 0
        for chunk_start in range(0, len(rows), self.chunk_size):
            chunk = rows[chunk_start : chunk_start + self.chunk_size]
            is_final = chunk_start + self.chunk_size >= len(rows)
            inserted += self._bulk_insert_mgr.bulk_insert(
                chunk,
                symbol=symbol if is_final else None,
                new_watermark=new_wm if is_final else None,
                watermark_mgr=self._watermark if is_final else None,
            )

        # Watermark advance happens inside bulk_insert on the final chunk (with its own
        # fail-fast). A second advance_watermark call here was redundant - one extra
        # write round trip per symbol per run, ~10k/run across the universe.

        self._stats.increment("rows_inserted", inserted)
        return inserted

    def _validate_row(self, row: dict[str, Any]) -> bool:
        """Validate row has all required primary key fields non-None.

        Args:
            row: Data row to validate.

        Raises:
            ValueError: If any primary key field is missing or None.

        Returns:
            True if all primary_key fields are present and non-None.
        """
        for key in self.primary_key:
            if key not in row:
                raise ValueError(f"[{self.table_name}] Row missing required primary key field '{key}'")
            if row[key] is None:
                raise ValueError(f"[{self.table_name}] Row has NULL value for required primary key field '{key}'")
        return True

    def _prepare_batch_context(self) -> None:
        self._batch_context = {}

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
        # FIXED (Session 258): Auto-detect if AWS credentials are valid.
        # If invalid, use file-based locking instead of failing.
        # This allows loaders to run locally without DynamoDB access.
        is_local_mode = os.getenv("LOCAL_MODE", "").lower() in ("1", "true", "yes")
        from utils.db.dynamo_lock import DynamoDBLockManager
        from utils.db.local_file_lock import get_lock_manager
        from utils.db.rds_lock import RDSLockManager

        # Type annotation includes FileLockManager because get_lock_manager() returns it
        # in LOCAL_MODE, even though production code should not rely on it (Windows race condition).
        # get_lock_manager() returns: FileLockManager (LOCAL_MODE), DynamoDBLockManager, or RDS fallback.
        from utils.db.local_file_lock import FileLockManager
        lock_manager: FileLockManager | DynamoDBLockManager | RDSLockManager | None = None
        if is_local_mode:
            logger.info(f"[{self.table_name}] LOCAL_MODE enabled - using file-based locks")
            lock_manager = None

        from algo.exceptions import LockAcquisitionError

        try:
            lock_table = os.getenv(
                "LOADER_LOCKS_TABLE",
                f"{os.getenv('PROJECT_NAME', 'algo')}-loader-locks-{os.getenv('ENVIRONMENT', 'dev')}",
            )
            # Lock TTL must outlive the longest legitimate run. It used to be 1800s while
            # real loader runtimes are 60-90+ min (price loader) - the lock silently
            # expired mid-run and a concurrent trigger (SFN retry, manual run) could
            # acquire it and double-write. Tie it to the loader SLA: the run() SLA
            # enforcement self-kills at this same limit, and the finally-release below
            # frees the lock immediately on any normal exit; the TTL only backstops
            # hard-killed tasks (OOM, StopTask).
            # LOCAL MODE previously hardcoded 600s (10min) "for faster recovery from crashed
            # loaders during dev", unconditionally ignoring LOADER_SLA_TIMEOUT_SECONDS even
            # when explicitly set. Real local dev runs regularly exceed 600s - live-confirmed
            # 2026-07-28: institutional_holdings_13f held its lock for 926.6s on an ordinary
            # run (OpenFIGI crosswalk alone budgets 900s), and cash-flow statement backfills
            # observed at ~2385s. A first pass raised this to 1800s, but that still undercuts
            # the observed 2385s cash-flow run - the lock would still silently expire mid-run,
            # which is exactly the "concurrent trigger could acquire the lock and double-write"
            # race the comment above already describes being fixed for production - LOCAL_MODE
            # had quietly reintroduced it. cleanup_expired_locks() below already provides fast
            # crash recovery independently (deletes locks whose OWN expires_at is 1800s+ in the
            # past), so a short TTL was never actually required for that purpose - it only
            # needs to outlive legitimate runs, same as production. 3600s (1h) clears the
            # observed 2385s max with margin while still being friendlier than production's
            # full 2h for an accidental infinite loop.
            # PRODUCTION: Use 7200s (2h) for slow loaders like price_daily that legitimately run 60+ min
            # CRITICAL FIX: Use loader-specific SLA timeout (can be 90+ min for price_loader)
            from loaders.config import get_loader_sla_timeout
            sla_timeout = get_loader_sla_timeout(self.table_name)
            # Lock TTL should be at least as long as SLA timeout (add 10% margin for safety)
            lock_ttl = int(sla_timeout * 1.1)
            try:
                lock_manager = get_lock_manager(table_name=lock_table, lock_duration_seconds=lock_ttl)
                # CRITICAL FIX (Session 351): Auto-cleanup expired locks at startup
                # Previously, if a loader crashed without releasing its lock, subsequent
                # loaders would be blocked for 2 hours (lock TTL). Now cleanup expired
                # locks automatically so we can recover from stuck loader scenarios.
                if lock_manager and hasattr(lock_manager, 'cleanup_expired_locks'):
                    try:
                        cleaned = lock_manager.cleanup_expired_locks(lock_key=self.table_name, max_age_seconds=1800)
                        if cleaned > 0:
                            logger.warning(f"[{self.table_name}] Cleaned {cleaned} expired lock(s) from previous crashed loader")
                    except Exception as cleanup_err:
                        logger.warning(f"[{self.table_name}] Failed to cleanup expired locks: {cleanup_err}")
            except RuntimeError as ddb_err:
                # CRITICAL (Session 282, updated Session 290): get_lock_manager() itself already
                # falls back from DynamoDB to RDS - this RuntimeError only reaches here when BOTH
                # are unavailable. At that point, fail fast with no further fallback: FileLockManager
                # has a Windows race condition (non-atomic file creation) and must never be used.
                # Better to fail-fast and trigger infrastructure retry than silently degrade to unsafe locking.
                # Loaders are orchestrated by Step Functions/EventBridge which handles retries.
                logger.critical(
                    f"[{self.table_name}] DynamoDB lock unavailable: {ddb_err}. "
                    f"Cannot proceed without distributed locking. Fix DynamoDB access or AWS credentials."
                )
                raise LockAcquisitionError(
                    lock_key=lock_table,
                    reason=f"DynamoDB lock manager unavailable: {ddb_err}",
                    context={"table_name": self.table_name}
                ) from ddb_err

            # LOCAL_MODE: Use shorter lock timeout to fail fast on stale locks
            # Production (DynamoDB/RDS): Use 15s to allow some network variance
            is_file_lock = isinstance(lock_manager, FileLockManager) if lock_manager else False
            lock_timeout_seconds = 5 if is_file_lock else 15  # Fail faster on stale file locks in LOCAL_MODE

            if not lock_manager.acquire(lock_key=self.table_name, timeout_seconds=lock_timeout_seconds):
                # Lock acquisition failed. Check if it's a permission issue or actual contention.
                if hasattr(lock_manager, 'is_available') and not lock_manager.is_available:
                    # CRITICAL (Session 282): permission error on whichever backend get_lock_manager()
                    # returned - fail fast, never fall back to FileLockManager. Reason: FileLockManager
                    # has a Windows race condition (non-atomic file creation) - falling back to it
                    # makes the situation WORSE, not better. Fail-fast with clear error so ops can fix access.
                    logger.critical(
                        f"[{self.table_name}] DynamoDB lock unavailable (permission denied). "
                        f"Cannot proceed with idempotency guarantee. Fix AWS credentials or DynamoDB access."
                    )
                    raise LockAcquisitionError(
                        lock_key=self.table_name,
                        reason="DynamoDB lock manager unavailable (permission/access error)",
                        context={"table_name": self.table_name}
                    )
                else:
                    # Lock timeout - another instance running, RETRY with exponential backoff
                    # CRITICAL FIX (Session 351): Afternoon loaders blocked by stale morning locks
                    # now retry instead of skipping silently. This was the root cause of
                    # missing EOD signals when morning loader crashed without releasing lock.
                    # WIDENED (2026-07-27): 3 retries capped at 30s (~60s total budget) was too thin
                    # against signal_quality_scores specifically - phase7_signal_generation.py calls
                    # this same lock path and a lock-acquisition failure there halts the ENTIRE
                    # trading session (no entries, not just a skipped loader). The competing lock
                    # holder is often the scheduled signal_quality_scores ECS task, which the
                    # comment in phase7_signal_generation.py documents can take 5-35 minutes - far
                    # longer than the old ~60s budget could ever wait out.
                    # IMPROVED (2026-07-29): signal_quality_scores-specific timeout (20 min) to allow
                    # legitimate long-running loader to complete without halting orchestrator.
                    # Phase 7 orchestrator halt cascades to no entries - must tolerate scheduler overlap.
                    logger.warning(f"[{self.table_name}] Another instance already running, retrying with backoff...")
                    import random

                    # CRITICAL FIX 2026-07-31: signal_quality_scores can take 5-35 min, observed up to 45+ min
                    # Previous timeout (20 retries) was MATHEMATICALLY WRONG: actually only ~25 min, not claimed 40 min
                    # Calculation: 5+10+20+40+80+90*15 = 1505s ≈ 25 min (NOT 40 min)
                    # For TRUE 50+ minute coverage: 5+10+20+40+80+90*30 = 2885s ≈ 48 min
                    # Phase 7 halt cascades to entire orchestrator (no entries) - must not timeout on legitimate long loader
                    # LOCAL_MODE (Session 45): Use shorter retry budget to fail fast on stale locks
                    # File locks are from local dev (not production), so stale locks should be cleaned up manually
                    # rather than waited out for 5-50 minutes. Reduce to 2 min max to encourage cleanup.
                    if is_file_lock:
                        # LOCAL_MODE file locks: short budget to encourage cleanup of stale locks
                        max_retries = 4   # ~1 min total (exponential: 5+10+20+40 = 75s ≈ 1 min)
                        retry_timeout_label = "1 minute"
                    elif self.table_name == 'signal_quality_scores':
                        max_retries = 35  # ~50 min total (exponential backoff: 5+10+20+40+80+90*30 = 2885s ≈ 48 min, safely covers observed 5-45+ min range)
                        retry_timeout_label = "50 minutes"
                    else:
                        max_retries = 8   # ~5 min total
                        retry_timeout_label = "5 minutes"

                    for retry_attempt in range(1, max_retries + 1):
                        base_wait = min(90, 2 ** (retry_attempt - 1) * 5)
                        jitter = random.uniform(0.9, 1.1)
                        wait_time = base_wait * jitter
                        logger.info(f"[{self.table_name}] Retry {retry_attempt}/{max_retries}: waiting {wait_time:.1f}s before next lock attempt")
                        time.sleep(wait_time)
                        if lock_manager.acquire(lock_key=self.table_name, timeout_seconds=lock_timeout_seconds):
                            logger.info(f"[{self.table_name}] Lock acquired on retry {retry_attempt}")
                            break
                    else:
                        # Final failure after retries - fail fast instead of silently skipping
                        # Critical loaders must not silently degrade (violates governance)
                        msg = (
                            f"[{self.table_name}] Failed to acquire lock after {max_retries} retries (~{retry_timeout_label} total wait). "
                            f"Another process is holding the lock persistently. Check for: (1) Stale locks held by crashed processes, "
                            f"(2) Long-running loaders (signal_quality_scores can take 5-35+ min), "
                            f"(3) Database connection issues. Cannot proceed without lock - failing fast to surface infrastructure issue."
                        )
                        logger.error(msg)
                        raise LockAcquisitionError(
                            lock_key=self.table_name,
                            reason="Lock acquisition timeout after retries",
                            context={"table_name": self.table_name, "max_retries": max_retries, "total_wait_minutes": 50 if self.table_name == 'signal_quality_scores' else 5}
                        )
        except LockAcquisitionError:
            # Already a well-formed LockAcquisitionError (raised above) - propagate as-is.
            # Re-wrapping via the generic handler below would double the message
            # ("Failed to acquire lock for X: Failed to acquire lock for X: ...").
            raise
        except Exception as _lock_err:
            logger.critical(f"[{self.table_name}] Lock initialization failed: {_lock_err}")
            raise LockAcquisitionError(
                lock_key=self.table_name, reason=str(_lock_err), context={"table_name": self.table_name}
            ) from _lock_err

        sla_monitor = None
        try:
            from utils.loaders.sla_monitor import SLAMonitor

            sla_monitor = SLAMonitor(self.table_name)
            sla_monitor.start()
        except Exception as e:
            logger.warning(f"[{self.table_name}] SLA monitoring failed: {e}")

        try:
            from utils.db.pooled_connection_manager import PooledConnectionManager
            from utils.db.pooled_context_var import set_pooled_connection

            conn_manager = PooledConnectionManager(self.table_name)
            set_pooled_connection(conn_manager.acquire())

            if backfill_days is not None:
                self._backfill_days = backfill_days

            # Tracks whether a more specific status (TIMEOUT, "Upstream data incomplete")
            # has already been written via the status manager for this run, so the generic
            # except-block fallback below doesn't overwrite it with a less-specific FAILED.
            status_already_finalized = False

            self._status_manager.mark_running()
            self._infrastructure.start_heartbeat()

            start = time.time()
            self._execution_start_time = start
            symbols = list(symbols)
            self._stats["symbols_total"] = len(symbols)

            try:
                self._prepare_batch_context()
            except Exception as e:
                logger.critical(f"[{self.table_name}] Batch context preparation failed: {e}")
                raise RuntimeError(f"Batch context preparation failed: {e}") from e

            if not self._check_upstream_completeness(len(symbols)):
                self._status_manager.mark_failed("Upstream data incomplete")
                self._infrastructure.stop_heartbeat()
                self._log_execution_history("failed", "Upstream data incomplete")
                return self._stats.to_dict()

            parallelism, _ = self._infrastructure.should_reduce_parallelism(parallelism)
            logger.info(f"[{self.table_name}] Starting load: {len(symbols)} symbols (parallelism={parallelism})")

            # CRITICAL FIX: Use loader-specific SLA timeout instead of hardcoded 2h
            # price_daily needs 90+ min (5000+ symbols), signal_quality_scores needs 60+ min
            from loaders.config import get_loader_sla_timeout
            sla_timeout_seconds = get_loader_sla_timeout(self.table_name)

            try:
                if parallelism == 1:
                    self._run_serial(symbols)
                else:
                    self._run_parallel(symbols, parallelism)
            finally:
                elapsed = time.time() - start
                if elapsed > sla_timeout_seconds:
                    logger.critical(f"[{self.table_name}] TIMEOUT: Exceeded SLA {sla_timeout_seconds}s")
                    self._status_manager.mark_timeout(elapsed)
                    status_already_finalized = True
                    raise RuntimeError(f"Loader exceeded SLA timeout ({sla_timeout_seconds}s)")

            self._stats.set("duration_sec", round(time.time() - start, 2))

            # FIX: Compute symbols_loaded and add it to stats BEFORE converting to dict
            # _update_final_status needs expected_symbols to calculate completion_pct
            symbols_loaded = self._update_final_status(len(symbols), symbols)
            # _update_final_status writes data_loader_status directly via raw SQL (not
            # through self._status_manager), so it's already the authoritative terminal
            # status (COMPLETED or its own FAILED classification) by this point - a later
            # exception (e.g. metrics publishing below) must not let the except-block
            # fallback overwrite that with a less-informed FAILED.
            status_already_finalized = True
            self._stats.set("symbols_loaded", symbols_loaded)

            stats_dict = self._stats.to_dict()

            try:
                from algo.reporting.metrics import MetricsPublisher

                with MetricsPublisher() as m:
                    m.put_loader_result(self.table_name, stats_dict)
            except Exception as e:
                raise RuntimeError(f"Loader metrics publishing failed: {e}") from e
            if sla_monitor:
                sla_monitor.log_status("info")
                sla_monitor.publish_metric()

            self._log_execution_history("success")
            self._infrastructure.stop_heartbeat()
            self._invalidate_cache()

            return stats_dict

        except Exception as e:
            try:
                self._log_execution_history("failed", str(e)[:500])
            except Exception as log_err:
                logger.warning(f"[{self.table_name}] Failed to log execution history: {log_err}")
            # BUG FIX (2026-08-04): a fast-failing exception (DB error, network error, bug
            # in _run_serial/_run_parallel) that isn't an SLA timeout previously left the
            # live data_loader_status row stuck at RUNNING forever - only mark_timeout()
            # (SLA-exceeded path above) and the "Upstream data incomplete" early-return path
            # ever called mark_failed(). Live-confirmed on dividend_data: a run that started
            # 2026-08-02 crashed without ever writing a completion/failure record to either
            # data_loader_status or data_loader_status_history, leaving status=RUNNING with a
            # 2-day-stale execution_started and no trace of what happened. Guard on
            # status_already_finalized so this doesn't clobber the more specific TIMEOUT
            # status already written above.
            if "status_already_finalized" in locals() and not status_already_finalized:
                try:
                    self._status_manager.mark_failed(str(e)[:500])
                except Exception as mark_err:
                    logger.warning(f"[{self.table_name}] Failed to mark FAILED status: {mark_err}")
            raise
        finally:
            self._infrastructure.stop_heartbeat()
            try:
                from utils.db.pooled_context_var import set_pooled_connection

                set_pooled_connection(None)
                conn_manager.release()
            except Exception as cleanup_err:
                logger.warning(f"[{self.table_name}] Failed to clean up connection: {cleanup_err}")
            if lock_manager:
                try:
                    lock_manager.release(lock_key=self.table_name)
                except Exception as lock_err:
                    logger.warning(f"[{self.table_name}] Failed to release lock: {lock_err}")

    def load_global(self) -> int:
        from utils.db.dynamo_lock import DynamoDBLockManager
        from utils.db.local_file_lock import get_lock_manager
        from utils.db.rds_lock import RDSLockManager

        # Type annotation includes FileLockManager because get_lock_manager() returns it
        # in LOCAL_MODE, even though production code should not rely on it (Windows race condition).
        # get_lock_manager() returns: FileLockManager (LOCAL_MODE), DynamoDBLockManager, or RDS fallback.
        from utils.db.local_file_lock import FileLockManager
        lock_manager: FileLockManager | DynamoDBLockManager | RDSLockManager | None = None
        from algo.exceptions import LockAcquisitionError

        try:
            lock_table = os.getenv(
                "LOADER_LOCKS_TABLE",
                f"{os.getenv('PROJECT_NAME', 'algo')}-loader-locks-{os.getenv('ENVIRONMENT', 'dev')}",
            )
            # Lock TTL must outlive the longest legitimate run. It used to be 1800s while
            # real loader runtimes are 60-90+ min (price loader) - the lock silently
            # expired mid-run and a concurrent trigger (SFN retry, manual run) could
            # acquire it and double-write. Tie it to the loader SLA: the run() SLA
            # enforcement self-kills at this same limit, and the finally-release below
            # frees the lock immediately on any normal exit; the TTL only backstops
            # hard-killed tasks (OOM, StopTask).
            # LOCAL MODE previously hardcoded 600s (10min) "for faster recovery from crashed
            # loaders during dev", unconditionally ignoring LOADER_SLA_TIMEOUT_SECONDS even
            # when explicitly set. Real local dev runs regularly exceed 600s - live-confirmed
            # 2026-07-28: institutional_holdings_13f held its lock for 926.6s on an ordinary
            # run (OpenFIGI crosswalk alone budgets 900s), and cash-flow statement backfills
            # observed at ~2385s. A first pass raised this to 1800s, but that still undercuts
            # the observed 2385s cash-flow run - the lock would still silently expire mid-run,
            # which is exactly the "concurrent trigger could acquire the lock and double-write"
            # race the comment above already describes being fixed for production - LOCAL_MODE
            # had quietly reintroduced it. cleanup_expired_locks() below already provides fast
            # crash recovery independently (deletes locks whose OWN expires_at is 1800s+ in the
            # past), so a short TTL was never actually required for that purpose - it only
            # needs to outlive legitimate runs, same as production. 3600s (1h) clears the
            # observed 2385s max with margin while still being friendlier than production's
            # full 2h for an accidental infinite loop.
            # PRODUCTION: Use 7200s (2h) for slow loaders like price_daily that legitimately run 60+ min
            # CRITICAL FIX: Use loader-specific SLA timeout (can be 90+ min for price_loader)
            from loaders.config import get_loader_sla_timeout
            sla_timeout = get_loader_sla_timeout(self.table_name)
            # Lock TTL should be at least as long as SLA timeout (add 10% margin for safety)
            lock_ttl = int(sla_timeout * 1.1)
            try:
                lock_manager = get_lock_manager(table_name=lock_table, lock_duration_seconds=lock_ttl)
                # CRITICAL FIX (Session 351): Auto-cleanup expired locks at startup
                # Same as in run() method - prevents stale locks from blocking subsequent loaders
                if lock_manager and hasattr(lock_manager, 'cleanup_expired_locks'):
                    try:
                        cleaned = lock_manager.cleanup_expired_locks(lock_key=self.table_name, max_age_seconds=1800)
                        if cleaned > 0:
                            logger.warning(f"[{self.table_name}] Cleaned {cleaned} expired lock(s) from previous crashed loader")
                    except Exception as cleanup_err:
                        logger.warning(f"[{self.table_name}] Failed to cleanup expired locks: {cleanup_err}")
            except RuntimeError as ddb_err:
                # CRITICAL (Session 282, updated Session 290): get_lock_manager() itself already
                # falls back from DynamoDB to RDS - this RuntimeError only reaches here when BOTH
                # are unavailable. At that point, fail fast with no further fallback: FileLockManager
                # has a Windows race condition (non-atomic file creation) and must never be used.
                # Better to fail-fast and trigger infrastructure retry than silently degrade to unsafe locking.
                # Loaders are orchestrated by Step Functions/EventBridge which handles retries.
                logger.critical(
                    f"[{self.table_name}] DynamoDB lock unavailable: {ddb_err}. "
                    f"Cannot proceed without distributed locking. Fix DynamoDB access or AWS credentials."
                )
                raise LockAcquisitionError(
                    lock_key=lock_table,
                    reason=f"DynamoDB lock manager unavailable: {ddb_err}",
                    context={"table_name": self.table_name}
                ) from ddb_err

            if not lock_manager.acquire(lock_key=self.table_name, timeout_seconds=5):
                # Lock acquisition failed. Check if it's a permission issue or actual contention.
                if hasattr(lock_manager, 'is_available') and not lock_manager.is_available:
                    # CRITICAL (Session 282): permission error on whichever backend get_lock_manager()
                    # returned - fail fast, never fall back to FileLockManager. Reason: FileLockManager
                    # has a Windows race condition (non-atomic file creation) - falling back to it
                    # makes the situation WORSE, not better. Fail-fast with clear error so ops can fix access.
                    logger.critical(
                        f"[{self.table_name}] DynamoDB lock unavailable (permission denied). "
                        f"Cannot proceed with idempotency guarantee. Fix AWS credentials or DynamoDB access."
                    )
                    raise LockAcquisitionError(
                        lock_key=self.table_name,
                        reason="DynamoDB lock manager unavailable (permission/access error)",
                        context={"table_name": self.table_name}
                    )
                else:
                    # Lock timeout - another instance running, RETRY with exponential backoff
                    # CRITICAL FIX (Session 351): Same retry logic as run() method
                    # WIDENED (2026-07-27): same reasoning as run()'s retry block above - keep the
                    # two budgets in sync so global-load callers get the same ~3.5 min tolerance.
                    logger.warning(f"[{self.table_name}] Another instance already running (global load), retrying with backoff...")
                    import random
                    max_retries = 6
                    for retry_attempt in range(1, max_retries + 1):
                        base_wait = min(60, 2 ** (retry_attempt - 1) * 5)
                        jitter = random.uniform(0.9, 1.1)
                        wait_time = base_wait * jitter
                        logger.info(f"[{self.table_name}] Global load retry {retry_attempt}/{max_retries}: waiting {wait_time:.1f}s")
                        time.sleep(wait_time)
                        if lock_manager.acquire(lock_key=self.table_name, timeout_seconds=5):
                            logger.info(f"[{self.table_name}] Lock acquired on retry {retry_attempt}")
                            break
                    else:
                        # Final failure after retries
                        logger.error(f"[{self.table_name}] Failed to acquire lock (global load) after {max_retries} retries. Skipping.")
                        return 0
        except LockAcquisitionError:
            # Already a well-formed LockAcquisitionError (raised above) - propagate as-is.
            # Re-wrapping via the generic handler below would double the message
            # ("Failed to acquire lock for X: Failed to acquire lock for X: ...").
            raise
        except Exception as _lock_err:
            logger.critical(f"[{self.table_name}] Lock initialization failed: {_lock_err}")
            raise LockAcquisitionError(
                lock_key=self.table_name, reason=str(_lock_err), context={"table_name": self.table_name}
            ) from _lock_err

        try:
            from utils.db.pooled_connection_manager import PooledConnectionManager
            from utils.db.pooled_context_var import set_pooled_connection

            conn_manager = PooledConnectionManager(self.table_name)
            set_pooled_connection(conn_manager.acquire())

            self._status_manager.mark_running()
            start = time.time()
            self._execution_start_time = start

            with DatabaseContext("read") as cur:
                cur.execute(f"SELECT MAX({self.watermark_field}) FROM {self.table_name}")
                row = cur.fetchone()
                since = row[0] if row and row[0] is not None else None

            try:
                rows_result = self.fetch_global(since)
            except Exception as e:
                raise RuntimeError(f"[{self.table_name}] fetch_global failed: {e}") from e

            # fetch_global returns marker dict if not implemented by subclass
            if isinstance(rows_result, dict) and rows_result.get("data_unavailable"):
                logger.debug(
                    f"[{self.table_name}] fetch_global not implemented by subclass "
                    f"(data_unavailable: {rows_result.get('reason', 'unknown')}). Skipping global load step."
                )
                self._status_manager.mark_completed(execution_duration_sec=time.time() - start)
                return 0

            # Some subclasses (e.g. load_naaim.py) list-wrap the marker dict instead of
            # returning it bare - recognize that shape too, or it falls through to a real
            # insert attempt and silently drops the reason text on a phantom NULL-keyed row.
            if (
                isinstance(rows_result, list)
                and len(rows_result) == 1
                and isinstance(rows_result[0], dict)
                and rows_result[0].get("data_unavailable")
            ):
                logger.debug(
                    f"[{self.table_name}] fetch_global returned list-wrapped data_unavailable marker "
                    f"(reason: {rows_result[0].get('reason', 'unknown')}). Skipping global load step."
                )
                self._status_manager.mark_completed(execution_duration_sec=time.time() - start)
                return 0

            # rows_result is now guaranteed to be a list[dict] after marker dict check
            rows: list[dict[str, Any]] = cast(list[dict[str, Any]], rows_result)

            if not rows:
                logger.info(f"[{self.table_name}] fetch_global returned empty list (no data available)")
                self._status_manager.mark_completed(execution_duration_sec=time.time() - start)
                return 0

            rows = self.transform(rows)
            inserted = self._bulk_insert_mgr.bulk_insert(rows)

            self._stats.set("rows_inserted", inserted)
            self._log_execution_history("success")
            # CRITICAL FIX 2026-08-03: pass this run's own counts, same fix already applied
            # to load_prices.py's custom status path. Without them, mark_completed() re-reads
            # symbol_count/symbols_loaded straight from the DB row - but load_global() callers
            # never call mark_running(symbol_count=...)/update_progress() to keep that row in
            # sync during a run, so symbol_count sits at whatever a much earlier run (or the
            # initial _ensure_status_row() insert) left it at - live-confirmed 0 for
            # MarketConstituentsLoader (stock_symbols) despite a real, successful, 5555-row
            # global refresh completing in 3s: symbol_count=0/symbols_loaded=3183 produced a
            # nonsensical "0.00% complete" FAILED status for a load that fully succeeded.
            self._status_manager.mark_completed(
                execution_duration_sec=time.time() - start,
                current_run_symbols_loaded=inserted,
                current_run_symbol_count=len(rows),
            )

            return inserted
        finally:
            try:
                from utils.db.pooled_context_var import set_pooled_connection

                set_pooled_connection(None)
                conn_manager.release()
            except Exception as cleanup_err:
                logger.warning(f"[{self.table_name}] Failed to clean up connection in load_global: {cleanup_err}")
            if lock_manager:
                try:
                    lock_manager.release(lock_key=self.table_name)
                except Exception as lock_err:
                    logger.warning(f"[{self.table_name}] Failed to release lock in load_global: {lock_err}")

    def close(self) -> None:
        """No-op: loaders hold no persistent resources of their own - all DB access goes
        through the pooled connection context manager, which manages its own lifecycle.
        Exists as a lifecycle hook for runner.py's `finally: loader.close()`."""

    def _run_serial(self, symbols: list[str]) -> None:
        failed_symbols: list[str] = []
        per_symbol_timeout = int(os.getenv("LOADER_PER_SYMBOL_TIMEOUT_SECONDS", "600"))
        # CRITICAL FIX: Use loader-specific SLA timeout
        from loaders.config import get_loader_sla_timeout
        max_batch_time = get_loader_sla_timeout(self.table_name)
        batch_start = time.time()

        for i, symbol in enumerate(symbols, 1):
            self._update_health_check()  # Signal ECS health check that loader is responsive
            elapsed_batch = time.time() - batch_start
            if elapsed_batch > max_batch_time:
                logger.critical(
                    f"[{self.table_name}] HARD LIMIT: Batch exceeded {max_batch_time}s SLA after {i}/{len(symbols)} symbols. Halting."
                )
                raise RuntimeError(f"Loader exceeded hard SLA limit ({max_batch_time}s) after {i} symbols")
            if self._infrastructure.check_shutdown_requested():
                logger.warning(f"[{self.table_name}] Graceful shutdown - stopping after {i - 1} symbols")
                break
            if i % 50 == 0:
                try:
                    with DatabaseContext("read") as cur:
                        cur.execute("SELECT 1")
                except Exception as health_err:
                    logger.critical(
                        f"[{self.table_name}] Database health check failed at symbol {i}/{len(symbols)}: {health_err}"
                    )
                    raise RuntimeError(
                        f"[{self.table_name}] Database health check failed-connection unreliable. Halting loader."
                    ) from health_err
            try:
                symbol_start = time.time()
                self.load_symbol(symbol)
                symbol_elapsed = time.time() - symbol_start
                if symbol_elapsed > per_symbol_timeout:
                    logger.warning(
                        f"[{self.table_name}] {symbol}: Slow symbol took {symbol_elapsed:.1f}s (threshold {per_symbol_timeout}s)"
                    )
                self._stats.increment("symbols_processed")
            except Exception as e:
                self._stats.increment("symbols_failed")
                logger.error(f"[{self.table_name}] {symbol} failed: {e}")
                failed_symbols.append(symbol)
                status_code = getattr(e, "status_code", None)
                if isinstance(status_code, int):
                    self._stats.set("http_status_code", status_code)
            if i % 100 == 0:
                logger.info(f"  Progress: {i}/{len(symbols)}")

        if failed_symbols:
            fail_rate = (len(failed_symbols) / len(symbols)) * 100 if symbols else 0
            max_fail_rate = getattr(self, "max_fail_rate", 60.0)
            if fail_rate > max_fail_rate:
                raise RuntimeError(
                    f"[{self.table_name}] {len(failed_symbols)} symbols failed-incomplete dataset. Failed: {failed_symbols[:10]}{'...' if len(failed_symbols) > 10 else ''}"
                )
            logger.warning(
                f"[{self.table_name}] {len(failed_symbols)}/{len(symbols)} symbols skipped "
                f"({fail_rate:.1f}% failure rate, within {max_fail_rate}% tolerance)"
            )

    def _run_parallel(self, symbols: list[str], workers: int) -> None:
        import threading
        from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

        # CRITICAL FIX: Parallel per-symbol timeout was 120s, causing premature timeouts
        # for legitimate slow operations (e.g., SEC API queries can take 5+ min per symbol).
        # Increase to 600s (10 min) to match serial timeout. Environment can override.
        per_symbol_timeout = int(os.getenv("LOADER_PER_SYMBOL_TIMEOUT_SECONDS", "600"))
        # CRITICAL FIX: Use loader-specific SLA timeout instead of hardcoded value
        from loaders.config import get_loader_sla_timeout
        max_batch_time = get_loader_sla_timeout(self.table_name)
        batch_start = time.time()

        # Track when each symbol ACTUALLY STARTS executing (not when it's dispatched/queued).
        # With many symbols queued across N workers, symbols near the end of the queue can
        # wait for minutes before a worker picks them up. Measuring from dispatch time would
        # incorrectly timeout queued-but-not-running symbols. We only count the timeout from
        # when a worker thread actually begins executing the symbol.
        execution_starts: dict[str, float] = {}
        execution_starts_lock = threading.Lock()

        def _timed_safe_load(symbol: str) -> None:
            with execution_starts_lock:
                execution_starts[symbol] = time.time()
            self._safe_load_symbol(symbol)

        with ThreadPoolExecutor(max_workers=workers) as exe:
            futures = {exe.submit(_timed_safe_load, s): s for s in symbols}
            done = 0
            pending_futures = set(futures.keys())

            while pending_futures:
                self._update_health_check()  # Signal ECS health check that loader is responsive
                elapsed_batch = time.time() - batch_start
                if elapsed_batch > max_batch_time:
                    logger.critical(
                        f"[{self.table_name}] HARD LIMIT: Batch exceeded {max_batch_time}s SLA. Killing all workers."
                    )
                    for f in pending_futures:
                        f.cancel()
                    self._stats.increment("symbols_failed", len(pending_futures))
                    raise RuntimeError(f"Loader exceeded hard SLA limit ({max_batch_time}s)")

                if self._infrastructure.check_shutdown_requested():
                    logger.warning(f"[{self.table_name}] Graceful shutdown - cancelling remaining tasks")
                    for f in pending_futures:
                        f.cancel()
                    self._stats.increment("symbols_failed", len(pending_futures))
                    break

                # Wait for the next future to complete, with a short polling timeout
                # to detect stalled workers every 5 seconds
                try:
                    done_futures, pending_futures = wait(pending_futures, timeout=5.0, return_when=FIRST_COMPLETED)
                except Exception as e:
                    logger.error(f"[{self.table_name}] Wait failed: {e}")
                    break

                # Process completed futures
                for fut in done_futures:
                    try:
                        fut.result(timeout=1)
                        done += 1
                    except Exception as fut_err:
                        logger.error(f"[{self.table_name}] Future task failed: {fut_err}")
                        done += 1
                    if done % 100 == 0:
                        logger.info(f"  Progress: {done}/{len(symbols)}")

                # Check for stalled workers: only timeout symbols that have STARTED executing.
                # Symbols still queued (not yet picked up by a worker) have no entry in
                # execution_starts and are skipped - they are not hung, just waiting.
                now = time.time()
                stalled = []
                for fut in pending_futures:
                    symbol = futures.get(fut, "unknown")
                    start = execution_starts.get(symbol)
                    if start is None:
                        continue  # Not yet running - queued, not stalled
                    elapsed = now - start
                    if elapsed > per_symbol_timeout:
                        logger.warning(
                            f"[{self.table_name}] Symbol {symbol} exceeded timeout ({elapsed:.0f}s > {per_symbol_timeout}s). Cancelling."
                        )
                        fut.cancel()
                        stalled.append(fut)
                        self._stats.increment("symbols_failed")

                pending_futures -= set(stalled)

        if "symbols_failed" not in self._stats:
            stats_dict = self._stats.to_dict()
            logger.error(
                f"[{self.table_name}] Loader stats corrupted, symbols_failed counter missing. "
                f"Current stats: {stats_dict}"
            )
            raise RuntimeError(
                f"[{self.table_name}] Loader stats corrupted, symbols_failed counter missing. Full stats: {stats_dict}"
            )
        failed_count = self._stats.get("symbols_failed")
        fail_rate = (failed_count / len(symbols)) * 100 if symbols else 0

        # CRITICAL: Enforce strict completeness for financial data
        # Default max 5% failure (95% completeness required). Subclasses can set higher for optional data.
        # For CRITICAL data: MUST have >=95% symbol coverage (max 5% skips)
        # For REQUIRED data: MUST have >=85% symbol coverage (max 15% skips)
        # For OPTIONAL data: Can tolerate up to 50% (set max_fail_rate=50 in subclass)
        # Loaders that previously tolerated 55%+ missing (quality_metrics, growth_metrics) need fixing.
        max_fail_rate = getattr(self, "max_fail_rate", 5.0)

        if fail_rate > max_fail_rate:
            raise RuntimeError(
                f"[{self.table_name}] {failed_count}/{len(symbols)} symbols failed "
                f"({fail_rate:.1f}% > {max_fail_rate}% threshold)-incomplete dataset cannot be used"
            )

        if failed_count > 0:
            logger.warning(
                f"[{self.table_name}] {failed_count}/{len(symbols)} symbols skipped "
                f"({fail_rate:.1f}% failure rate, within {max_fail_rate}% tolerance)"
            )

    def _safe_load_symbol(self, symbol: str) -> None:
        try:
            self.load_symbol(symbol)
            self._stats.increment("symbols_processed")
        except Exception as e:
            self._stats.increment("symbols_failed")
            logger.error(f"[{self.table_name}] {symbol} failed: {e}")
            # Real HTTP status code, when the failing call captured one (e.g.
            # utils/external/sec_edgar_client.py attaches .status_code to its raised
            # exceptions) - last-seen-wins across a parallel run, threaded through to
            # LoaderStatusManager.mark_failed() by runner.py so the dashboard's API
            # Diagnostics section can read the real status instead of only guessing
            # from error-message text. No-op for loaders whose exceptions don't carry it.
            status_code = getattr(e, "status_code", None)
            if isinstance(status_code, int):
                self._stats.set("http_status_code", status_code)

    def _check_upstream_completeness(self, expected_symbols: int) -> bool:
        """Check that upstream dependencies are sufficiently complete.

        Loaders may have dependencies on other loaders completing first.
        This method validates that required upstream data is available.
        """
        upstream_deps = {
            "technical_data_daily": "price_daily",
            "buy_sell_daily": "technical_data_daily",
            "signal_quality_scores": "buy_sell_daily",
            # swing_trader_scores: signal_quality_scores removed (computed on-the-fly, not loaded)
        }
        upstream_table = upstream_deps.get(self.table_name, None)
        if not upstream_table:
            return True

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT completion_pct FROM data_loader_status WHERE table_name = %s",
                    (upstream_table,),
                )
                result = cur.fetchone()
                if not result:
                    logger.critical(f"[UPSTREAM] No status record for {upstream_table}")
                    return False
                completion_pct = result[0]
                if completion_pct is None:
                    logger.critical(f"[UPSTREAM] {upstream_table} completion percent is NULL")
                    return False
                if completion_pct < 95:
                    logger.critical(f"[UPSTREAM] {upstream_table} only {completion_pct:.1f}% complete (need >=95%)")
                    self._status_manager.mark_failed(f"Upstream {upstream_table} incomplete: {completion_pct:.1f}%")
                    return False
                return True
        except Exception as e:
            logger.critical(f"[UPSTREAM] Completeness check failed: {e}")
            raise RuntimeError(f"Upstream completeness check failed: {e}") from None

    def _log_execution_history(self, status: str, error_message: str | None = None) -> None:
        if not self._execution_start_time:
            return
        try:
            from utils.db.pooled_context_var import get_pooled_connection, set_pooled_connection

            _saved = get_pooled_connection()
            set_pooled_connection(None)
            try:
                with DatabaseContext("write", enable_correlation_tracking=False) as cur:
                    cur.execute("SET statement_timeout = 0")
                    cur.execute(
                        "INSERT INTO loader_execution_history "
                        "(loader_name, execution_start, execution_end, status, rows_processed, error_message) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (
                            self.table_name,
                            datetime.fromtimestamp(self._execution_start_time, tz=timezone.utc),
                            datetime.now(timezone.utc),
                            status,
                            self._stats.get("rows_inserted") if "rows_inserted" in self._stats else 0,
                            error_message,
                        ),
                    )
            finally:
                set_pooled_connection(_saved)
        except Exception as e:
            logger.error(f"[{self.table_name}] Failed to log execution: {e}")

    @staticmethod
    def _to_date(value: date | datetime | None) -> date | None:
        """Normalize a MAX(watermark) query result to a plain date.

        psycopg2 returns a datetime.date for DATE columns and a datetime.datetime
        for TIMESTAMP columns. datetime.date has no .date() method, so calling
        .date() unconditionally (or gating on hasattr(value, "date"), which is
        False for a bare date) silently produced None for every DATE-typed
        watermark column, freezing data_loader_status.latest_date at NULL.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, int):
            # FIX 2026-07-20: watermark_field can be an integer fiscal_year column
            # (e.g. SecEdgarStatementLoader), not just DATE/TIMESTAMP. Passing the raw
            # int into a DATE column raised psycopg2.errors.DatatypeMismatch, which
            # aborted the data_loader_status write (though not the actual data write -
            # this only breaks the status/completeness bookkeeping row). Map it onto
            # Dec 31 of that year, matching watermark_from_rows in loaders/helpers/sec_base.py.
            return date(value, 12, 31)
        return value

    def _update_final_status(self, expected_symbols: int, symbols: list[str] | None = None) -> int:
        # CRITICAL FIX: Never allow None for expected_symbols - this causes data integrity failures
        # When symbol_count is NULL, Phase 1 failsafe halts orchestrator
        if expected_symbols is None:
            logger.critical(
                f"[{self.table_name}] expected_symbols is None - this indicates a programming error. "
                f"Caller must provide valid expected_symbols count. Refusing to proceed with unknown data completeness."
            )
            raise RuntimeError(
                f"[{self.table_name}] expected_symbols is None at _update_final_status. "
                "Caller must ensure valid symbol count is passed. Cannot update status with unknown completeness."
            )
        symbols_loaded = 0  # Default if error occurs
        try:
            with DatabaseContext("read") as cur:
                # CRITICAL: Handle loaders with no watermark_field (e.g., stock_scores computed all-at-once)
                if self.watermark_field:
                    if self.is_symbol_based:
                        # FIXED 2026-08-03: the distinct-symbol count used to be unscoped
                        # (COUNT(DISTINCT symbol) FROM {table_name}) - the table's ENTIRE symbol
                        # population, not just the symbols this run actually requested. Harmless
                        # for a normal full-universe run (expected_symbols == real population
                        # size, so the ratio stays sane), but a live crash for a --symbols-scoped
                        # run (e.g. local dev/test) against a table an earlier full run already
                        # populated broadly: e.g. requesting 10 symbols against a table with
                        # 2,816 real distinct symbols computed completion_pct = 2816/10*100 =
                        # 28160%, overflowing the NUMERIC(5,2) completion_pct column in
                        # mark_completed()'s re-check and crashing the whole run (rolling back the
                        # real data this run had just written, since both live in the same
                        # externally-managed transaction). Scoping the count to the symbols
                        # actually requested this run (via a WHERE'd subquery, kept inside the
                        # same single query so the row shape callers/tests depend on is
                        # unchanged) fixes both the immediate completion_pct here and
                        # mark_completed()'s later re-derivation from the symbol_count/
                        # symbols_loaded columns this method writes.
                        if symbols:
                            cur.execute(
                                f"SELECT COUNT(*), MAX({self.watermark_field}), "
                                f"(SELECT COUNT(DISTINCT symbol) FROM {self.table_name} WHERE symbol = ANY(%s)) "
                                f"FROM {self.table_name}",
                                (list(symbols),),
                            )
                        else:
                            cur.execute(
                                f"SELECT COUNT(*), MAX({self.watermark_field}), COUNT(DISTINCT symbol) "
                                f"FROM {self.table_name}"
                            )
                        result = cur.fetchone()
                        if result is None:
                            raise RuntimeError(
                                f"Status query failed for table '{self.table_name}': query returned None"
                            )
                        if result[0] is None:
                            raise RuntimeError(f"COUNT query returned NULL for table '{self.table_name}'")
                        total_rows = result[0]
                        latest_date = self._to_date(result[1])
                        actual_symbols_loaded = result[2] if result[2] is not None else 0
                    else:
                        # Market-wide loader (not symbol-based): count rows only
                        cur.execute(f"SELECT COUNT(*), MAX({self.watermark_field}) FROM {self.table_name}")
                        result = cur.fetchone()
                        if result is None:
                            raise RuntimeError(
                                f"Status query failed for table '{self.table_name}': query returned None"
                            )
                        if result[0] is None:
                            raise RuntimeError(f"COUNT query returned NULL for table '{self.table_name}'")
                        total_rows = result[0]
                        latest_date = self._to_date(result[1])
                        # BUG FOUND 2026-08-10: actual_symbols_loaded used to be `total_rows` -
                        # the table's entire ALL-TIME row count (e.g. 1314 = one row/day across
                        # years of history for market_health_daily), compared below against
                        # expected_symbols=1 (the single "market" pseudo-symbol this run
                        # processes). Live-confirmed: produced completion_pct capped at 100%
                        # with symbols_loaded=1314 - logged as "100.0% complete (1314/1
                        # symbols)", which the orchestrator's proactive critical-loader wait
                        # reads as a stalled/hung loader (a nonsensical ratio, not an honest
                        # per-run signal) regardless of whether this run's fetch actually
                        # succeeded. Scope the count to rows matching the latest watermark
                        # value (this run's data), matching the is_symbol_based=True branch's
                        # pattern of scoping to what THIS run actually touched rather than the
                        # table's unscoped historical population. `total_rows` above is
                        # unaffected - it still feeds `row_count`, where the all-time table
                        # size is the correct, intended metric.
                        cur.execute(
                            f"SELECT COUNT(*) FROM {self.table_name} WHERE {self.watermark_field} = %s",
                            (latest_date,),
                        )
                        scoped_result = cur.fetchone()
                        actual_symbols_loaded = (
                            scoped_result[0] if scoped_result and scoped_result[0] is not None else 0
                        )
                else:
                    # No watermark_field: just count rows (can't count distinct symbols for non-symbol tables)
                    cur.execute(f"SELECT COUNT(*) FROM {self.table_name}")
                    result = cur.fetchone()
                    if result is None:
                        raise RuntimeError(f"Status query failed for table '{self.table_name}': query returned None")
                    if result[0] is None:
                        raise RuntimeError(f"COUNT query returned NULL for table '{self.table_name}'")
                    total_rows = result[0]
                    latest_date = None
                    actual_symbols_loaded = total_rows  # For non-symbol tables, use row count

            # FIX: Use actual symbol count from table, not from stats
            # This ensures accuracy even if symbols_processed tracking has issues
            symbols_loaded = actual_symbols_loaded
            completion_pct = (symbols_loaded / expected_symbols * 100) if expected_symbols > 0 else 100.0
            # CAP at 100 ONLY when symbols_loaded > expected_symbols (incremental loads)
            # to prevent numeric overflow (NUMERIC(5,2) max is 999.99).
            # When symbols_loaded <= expected_symbols, preserve the actual completion %
            # so Status thresholds (e.g., 98% min for price loader) work correctly.
            # Example: 5253/5486 symbols = 95.75%, must not be capped to 100%.
            if symbols_loaded > expected_symbols:
                completion_pct = min(completion_pct, 100.0)
            # Respect the subclass's own declared max_fail_rate (already used elsewhere in this
            # file, e.g. _run_sequential's fail-fast gate at "max_fail_rate = getattr(self,
            # 'max_fail_rate', 60.0)") instead of a hardcoded 90% for every OptimalLoader
            # subclass regardless of its own tolerance. ConsolidatedFinancialStatementsLoader
            # (quarterly_balance_sheet, quarterly_income_statement) declares max_fail_rate=15.0
            # specifically because "Some stocks (foreign, delisted, recently-IPO'd) lack annual
            # reports" - ADRs/foreign private issuers file 20-F/6-K, not 10-Q, so SEC XBRL
            # companyfacts has no quarterly data for them at all. Confirmed live 2026-07-27:
            # both loaders sit at completion_pct~85-86%, exactly at their declared 85% floor
            # (100 - 15) - a real, permanent ceiling, not a transient failure. Before this fix,
            # a hardcoded >=90 threshold combined with the FAILED-canonicalization above would
            # have made these two loaders permanently show FAILED with consecutive_failures
            # climbing forever, even though they're loading everything they structurally can.
            min_completion_pct = 100.0 - getattr(self, "max_fail_rate", 10.0)
            # Canonical LoaderStatus values only (utils/loaders/status_enum.py) - "INCOMPLETE"
            # is not a member of that enum and was invisible to two downstream consumers that
            # only recognize FAILED/TIMEOUT: dashboard/freshness_enhancements.py's failure-rate/
            # MTTR/recovery-trend stats, and algo/monitoring/pipeline_health.py's health-sweep
            # preserve-real-failure logic (commit 9f61e4833), which only protects a status from
            # being overwritten back to HEALTHY when consecutive_failures > 0. Confirmed live
            # 2026-07-27: quarterly_balance_sheet/quarterly_income_statement sat at
            # status='INCOMPLETE', consecutive_failures=0, completion_pct~85-86% - a real,
            # ongoing data gap the next orchestrator run's health sweep would have silently
            # relabeled HEALTHY, and that freshness_enhancements.py's failure_rate_30d/mttr_hours
            # already silently excluded from their stats.
            loader_status = "COMPLETED" if completion_pct >= min_completion_pct else "FAILED"
            status_error_message = (
                None
                if loader_status == "COMPLETED"
                else f"Only {completion_pct:.1f}% of symbols loaded ({symbols_loaded}/{expected_symbols}, "
                f"min {min_completion_pct:.1f}% required)"
            )

            from utils.db.pooled_context_var import get_pooled_connection, set_pooled_connection

            _saved = get_pooled_connection()
            set_pooled_connection(None)
            try:
                with DatabaseContext("write", enable_correlation_tracking=False) as cur:
                    cur.execute("SET statement_timeout = 0")
                    # Convert execution_start_time from Unix timestamp to datetime
                    execution_started = None
                    execution_duration_sec = None
                    if self._execution_start_time:
                        execution_started = datetime.fromtimestamp(self._execution_start_time, tz=timezone.utc)
                        execution_duration_sec = time.time() - self._execution_start_time
                    symbols_per_sec = (
                        symbols_loaded / execution_duration_sec
                        if execution_duration_sec and execution_duration_sec > 0
                        else None
                    )

                    # UPSERT, not DELETE+INSERT: table_name is the PK here, and
                    # data_loader_status_history.table_name FK-references it. Once the
                    # history INSERT below runs once for a table, the old DELETE started
                    # failing every run after with ForeignKeyViolation (can't delete a
                    # parent row referenced by a child row) - confirmed live 2026-07-27,
                    # only affected the one table that had actually reached the history
                    # insert so far, but would have frozen data_loader_status (and thus
                    # every dashboard/staleness check reading it) for every OptimalLoader
                    # table permanently after its second-ever run.
                    cur.execute(
                        "INSERT INTO data_loader_status "
                        "(table_name, row_count, latest_date, last_updated, status, error_message, "
                        "completion_pct, symbol_count, symbols_loaded, execution_started, execution_completed, "
                        "execution_duration_sec, symbols_per_second, "
                        "last_success_at, consecutive_failures) "
                        "VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s, NOW(), %s, %s, "
                        "CASE WHEN %s = 'COMPLETED' THEN NOW() ELSE NULL END, "
                        "CASE WHEN %s = 'COMPLETED' THEN 0 ELSE 1 END) "
                        "ON CONFLICT (table_name) DO UPDATE SET "
                        "row_count = EXCLUDED.row_count, "
                        "latest_date = EXCLUDED.latest_date, "
                        "last_updated = EXCLUDED.last_updated, "
                        "status = EXCLUDED.status, "
                        "error_message = EXCLUDED.error_message, "
                        "completion_pct = EXCLUDED.completion_pct, "
                        "symbol_count = EXCLUDED.symbol_count, "
                        "symbols_loaded = EXCLUDED.symbols_loaded, "
                        "execution_started = EXCLUDED.execution_started, "
                        "execution_completed = EXCLUDED.execution_completed, "
                        "execution_duration_sec = EXCLUDED.execution_duration_sec, "
                        "symbols_per_second = EXCLUDED.symbols_per_second, "
                        "last_success_at = CASE WHEN EXCLUDED.status = 'COMPLETED' THEN NOW() "
                        "ELSE data_loader_status.last_success_at END, "
                        "consecutive_failures = CASE WHEN EXCLUDED.status = 'COMPLETED' THEN 0 "
                        "ELSE data_loader_status.consecutive_failures + 1 END, "
                        # FIXED 2026-07-28: this UPSERT never touched `reason` at all, so any
                        # value ever written there (manually, or by a one-off diagnostic pass -
                        # this INSERT list doesn't include it, and neither does
                        # utils/loaders/status_manager.py's mark_completed/mark_failed) stays
                        # frozen forever, regardless of how many times the loader succeeds
                        # afterward. Live-confirmed: analyst_sentiment_analysis carried
                        # reason='analyst_ratings_no_free_source' - a claim this codebase's own
                        # history already disproved (see DATA_LOADERS.md) - through many
                        # subsequent successful runs. industry_ranking and
                        # sector_rotation_signal carried a similarly stale "no active loader,
                        # marked for removal" reason despite being actively written and HEALTHY.
                        # Clear it on a genuine COMPLETED run so it can't keep misleading anyone
                        # reading data_loader_status as if it were live-maintained.
                        "reason = CASE WHEN EXCLUDED.status = 'COMPLETED' THEN NULL "
                        "ELSE data_loader_status.reason END",
                        (
                            self.table_name,
                            total_rows,
                            latest_date,
                            loader_status,
                            status_error_message,
                            completion_pct,
                            expected_symbols,
                            symbols_loaded,
                            execution_started,
                            execution_duration_sec,
                            symbols_per_sec,
                            loader_status,
                            loader_status,
                        ),
                    )

                    # Archive to history for failure-pattern analysis (dashboard's
                    # DATA FRESHNESS panel - see dashboard/freshness_enhancements.py's
                    # enrich_health_item_with_failure_pattern). utils/loaders/status_manager.py's
                    # StatusManager class already does this on its own mark_completed/mark_failed/
                    # mark_timeout methods, but this loader base class writes data_loader_status
                    # directly via the raw SQL above instead of going through StatusManager, so
                    # every loader built on OptimalLoader (the large majority) never reached that
                    # archiving call - confirmed live: 0 rows in data_loader_status_history despite
                    # dozens of loader runs/day. Runs inside a SAVEPOINT, not just a bare
                    # try/except: an uncaught statement error aborts the whole transaction, and
                    # this runs after the real DELETE+INSERT above in the same transaction -
                    # without a SAVEPOINT to roll back to, a failure here would silently discard
                    # that write too when __exit__ commits (Postgres treats COMMIT on an aborted
                    # transaction as a ROLLBACK).
                    try:
                        cur.execute("SAVEPOINT archive_history")
                        cur.execute(
                            "INSERT INTO data_loader_status_history "
                            "(table_name, status, execution_started, execution_completed, "
                            "error_message, row_count, completion_pct, symbols_loaded, symbol_count) "
                            "VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, %s)",
                            (
                                self.table_name,
                                loader_status,
                                execution_started,
                                status_error_message,
                                total_rows,
                                completion_pct,
                                symbols_loaded,
                                expected_symbols,
                            ),
                        )
                        # Keep only the last 100 runs per table (matches StatusManager's own
                        # retention policy in utils/loaders/status_manager.py)
                        cur.execute(
                            "DELETE FROM data_loader_status_history "
                            "WHERE table_name = %s AND id NOT IN ("
                            "  SELECT id FROM data_loader_status_history WHERE table_name = %s "
                            "  ORDER BY execution_completed DESC NULLS LAST LIMIT 100"
                            ")",
                            (self.table_name, self.table_name),
                        )
                        cur.execute("RELEASE SAVEPOINT archive_history")
                    except Exception as archive_err:
                        logger.debug(f"[OPTIMAL_LOADER] Failed to archive history for {self.table_name}: {archive_err}")
                        try:
                            cur.execute("ROLLBACK TO SAVEPOINT archive_history")
                        except Exception as savepoint_err:
                            logger.debug(f"[OPTIMAL_LOADER] Failed to rollback to savepoint: {savepoint_err}")
            finally:
                set_pooled_connection(_saved)
        except Exception as e:
            logger.warning(f"Failed to update data_loader_status: {e}")

        return symbols_loaded

    # AWS error codes meaning "no usable DynamoDB access from this environment" - either
    # permission was denied (AccessDenied) or the credentials themselves aren't valid
    # (UnrecognizedClientException/InvalidClientTokenId/ExpiredTokenException, the family
    # local dev throws when no real AWS account is configured). Both cases degrade the
    # same way - loader continues, Phase 1 may use stale cache - so both log a single
    # WARNING and return instead of falling through to two scary ERROR-level "cache
    # poisoning failed" log lines on literally every loader run in local dev.
    _CACHE_NO_ACCESS_ERROR_CODES = frozenset(
        {
            "AccessDenied",
            "AccessDeniedException",
            "UnrecognizedClientException",
            "InvalidClientTokenId",
            "ExpiredTokenException",
            "InvalidSignatureException",
        }
    )

    def _invalidate_cache(self) -> None:
        try:
            import boto3
            from botocore.exceptions import ClientError

            dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
            cache_table = dynamodb.Table(os.getenv("CACHE_TABLE", "algo_phase1_cache"))
            cache_key = f"data_loader_status-{date.today().isoformat()}"

            try:
                cache_table.delete_item(Key={"cache_key": cache_key})
                logger.info(f"[{self.table_name}] Cache invalidation successful")
                return
            except ClientError as delete_err:
                # FAIL-FAST: Validate error response structure before checking code
                error_dict = delete_err.response.get("Error")
                if not error_dict:
                    logger.error(
                        f"[{self.table_name}] Cache invalidation failed: malformed AWS response (missing 'Error' key). "
                        f"Response: {delete_err.response}. Cannot determine if retriable error."
                    )
                    raise RuntimeError(
                        f"AWS DynamoDB error response structure invalid: {delete_err.response}"
                    ) from delete_err

                error_code = error_dict.get("Code")
                if error_code in self._CACHE_NO_ACCESS_ERROR_CODES:
                    logger.warning(
                        f"[{self.table_name}] Cache invalidation: No DynamoDB access ({error_code}). "
                        "Loader will continue, but Phase 1 may use stale data from previous run."
                    )
                    return
                logger.error(f"[{self.table_name}] Cache delete failed: {delete_err}. Attempting cache poisoning...")

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
                    f"[{self.table_name}] Cache poisoned (set invalidation_failed=true) - Phase 1 will skip stale data"
                )
                return
            except ClientError as poison_err:
                # FAIL-FAST: Validate error response structure before checking code
                error_dict = poison_err.response.get("Error")
                if not error_dict:
                    logger.error(
                        f"[{self.table_name}] Cache poisoning failed: malformed AWS response (missing 'Error' key). "
                        f"Response: {poison_err.response}. Cannot determine if retriable error."
                    )
                    raise RuntimeError(
                        f"AWS DynamoDB error response structure invalid: {poison_err.response}"
                    ) from poison_err

                error_code = error_dict.get("Code")
                if error_code in self._CACHE_NO_ACCESS_ERROR_CODES:
                    logger.warning(
                        f"[{self.table_name}] Cache poisoning: No DynamoDB access ({error_code}). "
                        "Loader will continue, but Phase 1 may use stale data from previous run."
                    )
                    return
                logger.error(f"[{self.table_name}] Cache poisoning failed: {poison_err}")
        except Exception as setup_err:
            logger.error(f"[{self.table_name}] Cache invalidation setup error: {setup_err}")
