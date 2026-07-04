"""Production-grade data loader base class with separated infrastructure concerns."""

import logging
import os
import time
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any, cast

from utils.bulk_insert_manager import BulkInsertManager
from utils.db.context import DatabaseContext
from utils.loader_infrastructure import LoaderInfrastructure
from utils.loader_stats import LoaderStats
from utils.loaders.transient_errors import TransientAPIError
from utils.watermark_manager import WatermarkManager

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

    def __init__(self, backfill_days: int | None = None):
        self._router: Any = None
        self._backfill_days = backfill_days or int(os.getenv("BACKFILL_DAYS", "0"))
        self._batch_context: dict[str, Any] | None = None
        self._execution_start_time: float | None = None

        self._infrastructure = LoaderInfrastructure(self.table_name)
        self._stats = LoaderStats()
        self._watermark = WatermarkManager(self.table_name, self.watermark_field)
        self._bulk_insert_mgr = BulkInsertManager(self.table_name, self.primary_key, self.chunk_size)

        self._configure_chunk_size()

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
        # AWS environment: use smaller batch size to avoid yfinance rate limiting
        # Local development: use larger batch size (no rate limits)
        is_aws = bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.getenv("AWS_EXECUTION_ENV"))
        memory_limit_mb = int(os.getenv("ECS_TASK_MEMORY_LIMIT", "512"))
        safe_rows = int((memory_limit_mb * 0.40 * 1024) / 1.5)

        if is_aws:
            # AWS: reduce batch size to 100 to avoid yfinance rate limiting
            self.chunk_size = max(100, min(500, safe_rows))
        else:
            # Local: use larger batches (no rate limit concerns)
            self.chunk_size = max(2_000, min(50_000, safe_rows))
        self._bulk_insert_mgr.chunk_size = self.chunk_size
        logger.info(f"[CONFIG] Batch size set to {self.chunk_size} (AWS={is_aws})")

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
            # Empty result set—should not call with empty rows
            raise ValueError(
                f"[{self.table_name}] watermark_from_rows called with empty rows (should never happen). "
                "This is a programming error—check caller before invoking."
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
                values.append(cast(date, field_value))

        if not values:
            raise ValueError(
                f"[{self.table_name}] watermark_from_rows: {len(rows)} rows present but all {self.watermark_field} values are NULL"
            )
        return max(values)

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
            previous_date = self._watermark.get(symbol)
            if previous_date is None:
                previous_date = self._watermark.read_from_db(symbol)

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
            # No new data since watermark—expected for incremental loads
            logger.debug(
                f"[{self.table_name}] {symbol}: No new data since watermark (previous={previous_date}), skipping"
            )
            self._stats.increment("symbols_skipped_by_watermark")
            return 0

        self._stats.increment("rows_fetched", len(rows))
        if self.router and self.router.last_source:
            self._stats.add_source(self.router.last_source)

        rows = self.transform(rows)
        validated_rows = []
        for i, r in enumerate(rows):
            try:
                self._validate_row(r)
                validated_rows.append(r)
            except ValueError as e:
                raise ValueError(f"Row {i} failed validation: {e}") from e

        if not validated_rows:
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

        if new_wm:
            self._watermark.set(symbol, new_wm, inserted)

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
        lock_manager = None
        try:
            from utils.db.dynamo_lock import DynamoDBLockManager

            lock_table = os.getenv(
                "LOADER_LOCKS_TABLE",
                f"{os.getenv('PROJECT_NAME', 'algo')}-loader-locks-{os.getenv('ENVIRONMENT', 'dev')}",
            )
            lock_manager = DynamoDBLockManager(table_name=lock_table, lock_duration_seconds=1800)
            if not lock_manager.acquire(lock_key=self.table_name, timeout_seconds=5):
                logger.warning(f"[{self.table_name}] Skipping: another instance already running")
                return self._stats.to_dict()
        except Exception as _lock_err:
            logger.critical(f"[{self.table_name}] DynamoDB lock failed: {_lock_err}")
            from algo.exceptions import LockAcquisitionError

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

            self._infrastructure.update_loader_status("RUNNING")
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
                self._infrastructure.update_loader_status("FAILED")
                self._infrastructure.stop_heartbeat()
                self._log_execution_history("failed", "Upstream data incomplete")
                return self._stats.to_dict()

            parallelism, _ = self._infrastructure.should_reduce_parallelism(parallelism)
            logger.info(f"[{self.table_name}] Starting load: {len(symbols)} symbols (parallelism={parallelism})")

            sla_timeout_seconds = int(os.getenv("LOADER_SLA_TIMEOUT_SECONDS", "10800"))

            try:
                if parallelism == 1:
                    self._run_serial(symbols)
                else:
                    self._run_parallel(symbols, parallelism)
            finally:
                elapsed = time.time() - start
                if elapsed > sla_timeout_seconds:
                    logger.critical(f"[{self.table_name}] TIMEOUT: Exceeded SLA {sla_timeout_seconds}s")
                    self._infrastructure.update_loader_status("FAILED")
                    raise RuntimeError(f"Loader exceeded SLA timeout ({sla_timeout_seconds}s)")

            self._stats.set("duration_sec", round(time.time() - start, 2))
            stats_dict = self._stats.to_dict()

            try:
                from algo.reporting.metrics import MetricsPublisher

                with MetricsPublisher() as m:
                    m.put_loader_result(self.table_name, stats_dict)
            except Exception as e:
                raise RuntimeError(f"Loader metrics publishing failed: {e}") from e

            self._update_final_status(len(symbols))
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
        lock_manager = None
        try:
            from utils.db.dynamo_lock import DynamoDBLockManager

            lock_table = os.getenv(
                "LOADER_LOCKS_TABLE",
                f"{os.getenv('PROJECT_NAME', 'algo')}-loader-locks-{os.getenv('ENVIRONMENT', 'dev')}",
            )
            lock_manager = DynamoDBLockManager(table_name=lock_table, lock_duration_seconds=1800)
            if not lock_manager.acquire(lock_key=self.table_name, timeout_seconds=5):
                logger.warning(f"[{self.table_name}] Skipping global load: another instance running")
                return 0
        except Exception as _lock_err:
            logger.critical(f"[{self.table_name}] DynamoDB lock failed: {_lock_err}")
            from algo.exceptions import LockAcquisitionError

            raise LockAcquisitionError(
                lock_key=self.table_name, reason=str(_lock_err), context={"table_name": self.table_name}
            ) from _lock_err

        try:
            from utils.db.pooled_connection_manager import PooledConnectionManager
            from utils.db.pooled_context_var import set_pooled_connection

            conn_manager = PooledConnectionManager(self.table_name)
            set_pooled_connection(conn_manager.acquire())

            self._infrastructure.update_loader_status("RUNNING")
            start = time.time()
            self._execution_start_time = start

            with DatabaseContext("read") as cur:
                cur.execute(f"SELECT MAX({self.watermark_field}) FROM {self.table_name}")
                row = cur.fetchone()
                since = self._watermark._parse_watermark_date(row[0]) if row and row[0] is not None else None

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
                return 0

            # rows_result is now guaranteed to be a list[dict] after marker dict check
            rows: list[dict[str, Any]] = cast(list[dict[str, Any]], rows_result)

            if not rows:
                logger.info(f"[{self.table_name}] fetch_global returned empty list (no data available)")
                return 0

            rows = self.transform(rows)
            inserted = self._bulk_insert_mgr.bulk_insert(rows)

            self._stats.set("rows_inserted", inserted)
            self._log_execution_history("success")

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
        pass

    def _run_serial(self, symbols: list[str]) -> None:
        failed_symbols: list[str] = []
        per_symbol_timeout = int(os.getenv("LOADER_PER_SYMBOL_TIMEOUT_SECONDS", "600"))
        max_batch_time = int(os.getenv("LOADER_SLA_TIMEOUT_SECONDS", "10800"))
        batch_start = time.time()

        for i, symbol in enumerate(symbols, 1):
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
                        f"[{self.table_name}] Database health check failed—connection unreliable. Halting loader."
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
            if i % 100 == 0:
                logger.info(f"  Progress: {i}/{len(symbols)}")

        if failed_symbols:
            fail_rate = (len(failed_symbols) / len(symbols)) * 100 if symbols else 0
            max_fail_rate = getattr(self, "max_fail_rate", 60.0)
            if fail_rate > max_fail_rate:
                raise RuntimeError(
                    f"[{self.table_name}] {len(failed_symbols)} symbols failed—incomplete dataset. Failed: {failed_symbols[:10]}{'...' if len(failed_symbols) > 10 else ''}"
                )
            logger.warning(
                f"[{self.table_name}] {len(failed_symbols)}/{len(symbols)} symbols skipped "
                f"({fail_rate:.1f}% failure rate, within {max_fail_rate}% tolerance)"
            )

    def _run_parallel(self, symbols: list[str], workers: int) -> None:
        import threading
        from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

        per_symbol_timeout = int(os.getenv("LOADER_PER_SYMBOL_TIMEOUT_SECONDS", "120"))
        max_batch_time = int(os.getenv("LOADER_SLA_TIMEOUT_SECONDS", "10800"))
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
                # execution_starts and are skipped — they are not hung, just waiting.
                now = time.time()
                stalled = []
                for fut in pending_futures:
                    symbol = futures.get(fut, "unknown")
                    start = execution_starts.get(symbol)
                    if start is None:
                        continue  # Not yet running — queued, not stalled
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
                f"({fail_rate:.1f}% > {max_fail_rate}% threshold)—incomplete dataset cannot be used"
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
                    logger.critical(f"[UPSTREAM] {upstream_table} only {completion_pct:.1f}% complete")
                    self._infrastructure.update_loader_status("FAILED")
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

    def _update_final_status(self, expected_symbols: int) -> None:
        try:
            with DatabaseContext("read") as cur:
                # CRITICAL: Handle loaders with no watermark_field (e.g., stock_scores computed all-at-once)
                if self.watermark_field:
                    cur.execute(f"SELECT COUNT(*), MAX({self.watermark_field}) FROM {self.table_name}")
                    result = cur.fetchone()
                    if result is None:
                        raise RuntimeError(f"Status query failed for table '{self.table_name}': query returned None")
                    if result[0] is None:
                        raise RuntimeError(f"COUNT query returned NULL for table '{self.table_name}'")
                    total_rows = result[0]
                    latest_date = result[1].date() if result[1] is not None and hasattr(result[1], "date") else None
                else:
                    # No watermark_field: just count rows
                    cur.execute(f"SELECT COUNT(*) FROM {self.table_name}")
                    result = cur.fetchone()
                    if result is None:
                        raise RuntimeError(f"Status query failed for table '{self.table_name}': query returned None")
                    if result[0] is None:
                        raise RuntimeError(f"COUNT query returned NULL for table '{self.table_name}'")
                    total_rows = result[0]
                    latest_date = None

            # CRITICAL FIX: Validate symbols_processed exists — don't mask incomplete tracking with 0
            symbols_processed = self._stats.get("symbols_processed")
            if symbols_processed is None:
                logger.warning(
                    f"[{self.table_name}] symbols_processed not tracked in stats — possible loader instrumentation issue. "
                    "Defaulting to 0 but check loader logging for completion issues."
                )
                symbols_processed = 0
            completion_pct = (symbols_processed / expected_symbols * 100) if expected_symbols > 0 else 100.0
            loader_status = "COMPLETED" if completion_pct >= 95 else "INCOMPLETE"

            from utils.db.pooled_context_var import get_pooled_connection, set_pooled_connection

            _saved = get_pooled_connection()
            set_pooled_connection(None)
            try:
                with DatabaseContext("write", enable_correlation_tracking=False) as cur:
                    cur.execute("SET statement_timeout = 0")
                    cur.execute("DELETE FROM data_loader_status WHERE table_name = %s", (self.table_name,))
                    cur.execute(
                        "INSERT INTO data_loader_status "
                        "(table_name, row_count, latest_date, last_updated, status, "
                        "completion_pct, symbol_count, symbols_loaded, execution_started, execution_completed) "
                        "VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, NOW(), NOW())",
                        (
                            self.table_name,
                            total_rows,
                            latest_date,
                            loader_status,
                            completion_pct,
                            expected_symbols,
                            symbols_processed,
                        ),
                    )
            finally:
                set_pooled_connection(_saved)
        except Exception as e:
            logger.warning(f"Failed to update data_loader_status: {e}")

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
                if error_code in ("AccessDenied", "AccessDeniedException"):
                    logger.warning(
                        f"[{self.table_name}] Cache invalidation: No DynamoDB write access (permission denied). "
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
                if error_code in ("AccessDenied", "AccessDeniedException"):
                    logger.warning(
                        f"[{self.table_name}] Cache poisoning: No DynamoDB write access (permission denied). "
                        "Loader will continue, but Phase 1 may use stale data from previous run."
                    )
                    return
                logger.error(f"[{self.table_name}] Cache poisoning failed: {poison_err}")
        except Exception as setup_err:
            logger.error(f"[{self.table_name}] Cache invalidation setup error: {setup_err}")
