"""Production-grade data loader base class with separated infrastructure concerns."""

import logging
import os
import time
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any

from utils.bulk_insert_manager import BulkInsertManager
from utils.db.context import DatabaseContext
from utils.loader_infrastructure import LoaderInfrastructure
from utils.loader_stats import LoaderStats
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
        memory_limit_mb = int(os.getenv("ECS_TASK_MEMORY_LIMIT", "512"))
        safe_rows = int((memory_limit_mb * 0.40 * 1024) / 1.5)
        self.chunk_size = max(2_000, min(50_000, safe_rows))
        self._bulk_insert_mgr.chunk_size = self.chunk_size

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]] | None:
        raise NotImplementedError("Implement fetch_incremental or fetch_global")

    def fetch_global(self, since: date | None) -> list[dict[str, Any]] | None:
        return None

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return rows

    def watermark_from_rows(self, rows: list[dict[str, Any]]) -> date | None:
        if not rows:
            return None
        values: list[Any] = [r.get(self.watermark_field) for r in rows if r.get(self.watermark_field)]
        return max(values) if values else None

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

        try:
            rows = self.fetch_incremental(symbol, previous_date)
        except Exception as e:
            raise RuntimeError(f"[{self.table_name}] {symbol}: Failed to fetch: {e}") from e

        if not rows:
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
                chunk, symbol=symbol if is_final else None, new_watermark=new_wm if is_final else None
            )

        if new_wm:
            self._watermark.set(symbol, new_wm, inserted)

        self._stats.increment("rows_inserted", inserted)
        return inserted

    def _validate_row(self, row: dict[str, Any]) -> bool:
        return all(row.get(c) is not None for c in self.primary_key)

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
                since = self._watermark._parse_watermark_date(row[0]) if row and row[0] else None

            try:
                rows = self.fetch_global(since)
            except Exception as e:
                raise RuntimeError(f"[{self.table_name}] fetch_global failed: {e}") from e

            if not rows:
                logger.info(f"[{self.table_name}] fetch_global returned no rows")
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
        for i, symbol in enumerate(symbols, 1):
            if self._infrastructure.check_shutdown_requested():
                logger.warning(f"[{self.table_name}] Graceful shutdown - stopping after {i - 1} symbols")
                break
            if i % 50 == 0:
                try:
                    with DatabaseContext("read") as cur:
                        cur.execute("SELECT 1")
                except Exception:
                    pass
            try:
                self.load_symbol(symbol)
                self._stats.increment("symbols_processed")
            except Exception as e:
                self._stats.increment("symbols_failed")
                logger.error(f"[{self.table_name}] {symbol} failed: {e}")
            if i % 100 == 0:
                logger.info(f"  Progress: {i}/{len(symbols)}")

    def _run_parallel(self, symbols: list[str], workers: int) -> None:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from concurrent.futures import TimeoutError as FutureTimeoutError

        with ThreadPoolExecutor(max_workers=workers) as exe:
            futures = {exe.submit(self._safe_load_symbol, s): s for s in symbols}
            done = 0
            try:
                for fut in as_completed(futures, timeout=3600):
                    if self._infrastructure.check_shutdown_requested():
                        logger.warning(f"[{self.table_name}] Graceful shutdown - cancelling remaining tasks")
                        for f in futures:
                            f.cancel()
                        break
                    try:
                        fut.result(timeout=5)
                        done += 1
                    except Exception as fut_err:
                        logger.error(f"[{self.table_name}] Future task failed: {fut_err}")
                        done += 1
                    if done % 100 == 0:
                        logger.info(f"  Progress: {done}/{len(symbols)}")
            except FutureTimeoutError:
                pending = [s for f, s in futures.items() if not f.done()]
                logger.error(f"[{self.table_name}] Global timeout reached. {len(pending)} symbols hung.")
                self._stats.increment("symbols_failed", len(pending))
                for f in futures.keys():
                    f.cancel()

    def _safe_load_symbol(self, symbol: str) -> None:
        try:
            self.load_symbol(symbol)
            self._stats.increment("symbols_processed")
        except Exception as e:
            self._stats.increment("symbols_failed")
            logger.error(f"[{self.table_name}] {symbol} failed: {e}")

    def _check_upstream_completeness(self, expected_symbols: int) -> bool:
        upstream_deps = {
            "technical_data_daily": "price_daily",
            "buy_sell_daily": "technical_data_daily",
            "signal_quality_scores": "buy_sell_daily",
            "swing_trader_scores": "signal_quality_scores",
        }
        upstream_table = upstream_deps.get(self.table_name)
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
                completion_pct = result[0] or 100.0
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
                            self._stats.get("rows_inserted"),
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
                cur.execute(f"SELECT COUNT(*), MAX({self.watermark_field}) FROM {self.table_name}")
                result = cur.fetchone()
                if result is None:
                    raise RuntimeError(f"Status query failed for table '{self.table_name}': query returned None")
                if result[0] is None:
                    raise RuntimeError(f"COUNT query returned NULL for table '{self.table_name}'")
                total_rows = result[0]
                latest_date = result[1].date() if result[1] is not None and hasattr(result[1], "date") else None

            symbols_processed = self._stats.get("symbols_processed")
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

            dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
            cache_table = dynamodb.Table(os.getenv("CACHE_TABLE", "algo_phase1_cache"))
            cache_table.delete_item(Key={"cache_key": f"data_loader_status-{date.today().isoformat()}"})
        except Exception:
            pass
