"""Infrastructure concerns for data loaders: signals, heartbeat, config, status."""

import logging
import os
import signal
import threading
import time
from typing import Any

import psycopg2

from utils.db.context import DatabaseContext
from utils.db.sql_safety import assert_safe_table

logger = logging.getLogger(__name__)


class LoaderInfrastructure:
    """Handles infrastructure for loaders: signals, heartbeat, status, config validation.

    Responsibilities:
    - Signal handlers for graceful shutdown
    - Heartbeat thread to detect hung tasks
    - Status updates in data_loader_status table
    - Runtime config validation (table_name safety, parallelism ranges)
    - RDS connection pool monitoring
    """

    def __init__(self, table_name: str):
        self.table_name = table_name
        self._shutdown_requested = False
        self._shutdown_lock = threading.Lock()
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_running = False
        self._heartbeat_exception: Exception | None = None
        self._heartbeat_lock = threading.Lock()
        self._heartbeat_interval = 60
        self._setup_signal_handlers()
        self._validate_runtime_config()

    def _setup_signal_handlers(self) -> None:
        """Register SIGTERM handler for graceful shutdown on ECS task termination."""
        if threading.current_thread() is not threading.main_thread():
            logger.debug(f"[{self.table_name}] Skipping signal handlers (not in main thread)")
            return

        def handle_shutdown(signum: int, frame: Any) -> None:
            with self._shutdown_lock:
                if not self._shutdown_requested:
                    self._shutdown_requested = True
                    logger.warning(f"[{self.table_name}] SIGTERM received - graceful shutdown requested")

        signal.signal(signal.SIGTERM, handle_shutdown)

    def _validate_runtime_config(self) -> None:
        """Validate runtime configuration for security and correctness."""
        try:
            assert_safe_table(self.table_name)
        except ValueError as e:
            logger.error(f"[SECURITY] {e}")
            raise

        try:
            loader_parallelism = os.getenv("LOADER_PARALLELISM", "")
            if loader_parallelism:
                try:
                    parallelism_value = int(loader_parallelism)
                    if parallelism_value < 1 or parallelism_value > 32:
                        logger.warning(
                            f"[CONFIG] LOADER_PARALLELISM={parallelism_value} outside normal range (1-32). "
                            "Check Terraform task definition."
                        )
                    logger.info(f"[CONFIG] LOADER_PARALLELISM={parallelism_value}")
                except ValueError:
                    logger.warning(f"[CONFIG] LOADER_PARALLELISM='{loader_parallelism}' is not a valid integer")
            else:
                logger.warning("[CONFIG] LOADER_PARALLELISM not set in environment. Using default.")

            aws_region = os.getenv("AWS_REGION", "not set")
            db_name = os.getenv("DB_NAME", "not set")
            logger.debug(f"[CONFIG] AWS_REGION={aws_region}, DB_NAME={db_name}")
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.debug(f"[CONFIG] Runtime validation check failed: {e}")

    def start_heartbeat(self) -> None:
        """Start background thread that updates loader status every 60 seconds."""
        with self._heartbeat_lock:
            if self._heartbeat_running:
                return
            self._heartbeat_running = True
            self._heartbeat_exception = None

        def heartbeat_worker() -> None:
            consecutive_failures = 0
            while self._heartbeat_running:
                try:
                    time.sleep(self._heartbeat_interval)
                    if self._heartbeat_running:
                        with DatabaseContext("write") as cur:
                            cur.execute(
                                "UPDATE data_loader_status SET last_updated = NOW() "
                                "WHERE table_name = %s AND status = %s",
                                (self.table_name, "RUNNING"),
                            )
                        consecutive_failures = 0
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    consecutive_failures += 1
                    error_msg = (
                        f"[{self.table_name}] Heartbeat update failed ({consecutive_failures}/3): {e}. "
                        "If failures persist, loader will be marked as failed."
                    )
                    logger.error(error_msg)
                    if consecutive_failures >= 3:
                        with self._heartbeat_lock:
                            self._heartbeat_exception = RuntimeError(
                                f"Heartbeat failed {consecutive_failures} times. Database connectivity lost."
                            )
                        self._heartbeat_running = False
                except Exception as e:
                    logger.error(f"[{self.table_name}] Unexpected heartbeat error: {e}", exc_info=True)
                    with self._heartbeat_lock:
                        self._heartbeat_exception = e
                    self._heartbeat_running = False

        self._heartbeat_thread = threading.Thread(
            target=heartbeat_worker, daemon=True, name=f"heartbeat-{self.table_name}"
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        """Stop the heartbeat background thread."""
        with self._heartbeat_lock:
            self._heartbeat_running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)

    def check_heartbeat_health(self) -> None:
        """Check if heartbeat has failed and raise if it has.

        Call periodically from loader main loop to detect database connectivity issues early.
        Prevents hung tasks that silently fail to update their status.
        """
        with self._heartbeat_lock:
            if self._heartbeat_exception:
                raise RuntimeError(
                    f"[{self.table_name}] Heartbeat health check failed. "
                    f"Loader cannot continue without database connectivity. "
                    f"Error: {self._heartbeat_exception}"
                ) from self._heartbeat_exception

    def update_loader_status(self, status: str) -> None:
        """Update loader status in data_loader_status table.

        Status values: 'RUNNING', 'COMPLETED', 'FAILED', 'INCOMPLETE'.
        """
        try:
            from utils.db.pooled_context_var import (
                get_pooled_connection,
                set_pooled_connection,
            )

            saved_conn = get_pooled_connection()
            set_pooled_connection(None)
            try:
                with DatabaseContext("write", enable_correlation_tracking=False) as cur:
                    cur.execute("SET statement_timeout = 0")
                    if status == "RUNNING":
                        cur.execute(
                            "UPDATE data_loader_status SET status = %s, last_updated = NOW(), execution_started = NOW() "
                            "WHERE table_name = %s",
                            (status, self.table_name),
                        )
                        if cur.rowcount == 0:
                            cur.execute(
                                "INSERT INTO data_loader_status (table_name, status, last_updated, execution_started) "
                                "VALUES (%s, %s, NOW(), NOW())",
                                (self.table_name, status),
                            )
                        logger.debug(f"[{self.table_name}] Status updated to RUNNING")
                    elif status in ("COMPLETED", "FAILED", "INCOMPLETE"):
                        cur.execute(
                            "UPDATE data_loader_status SET status = %s, last_updated = NOW(), execution_completed = NOW() "
                            "WHERE table_name = %s",
                            (status, self.table_name),
                        )
                        logger.debug(f"[{self.table_name}] Status updated to {status}")
            finally:
                set_pooled_connection(saved_conn)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"[{self.table_name}] CRITICAL: Failed to update loader status to {status}: {e}") from e

    def check_shutdown_requested(self) -> bool:
        """Check if graceful shutdown was requested."""
        with self._shutdown_lock:
            return self._shutdown_requested

    def get_rds_connection_count(self) -> int | None:
        """Get current RDS active connection count from CloudWatch metrics."""
        try:
            from datetime import datetime, timedelta

            import boto3

            cloudwatch = boto3.client("cloudwatch", region_name=os.getenv("AWS_REGION", "us-east-1"))

            response = cloudwatch.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName="DatabaseConnections",
                Dimensions=[{"Name": "DBInstanceIdentifier", "Value": "algo-db"}],
                StartTime=datetime.utcnow() - timedelta(minutes=5),
                EndTime=datetime.utcnow(),
                Period=60,
                Statistics=["Average"],
            )

            if response["Datapoints"]:
                latest = max(response["Datapoints"], key=lambda x: x["Timestamp"])
                return int(latest["Average"])
            return None
        except Exception as e:
            logger.warning(
                f"[{self.table_name}] CloudWatch unavailable for RDS connection check: {e}. "
                "Proceeding with reduced parallelism as conservative default."
            )
            return None

    def should_reduce_parallelism(self, parallelism: int) -> tuple[int, bool]:
        """Check if RDS pool is saturated and adjust parallelism if needed.

        Returns: (adjusted_parallelism, was_reduced)
        """
        if parallelism <= 1:
            return parallelism, False

        conn_count = self.get_rds_connection_count()

        if conn_count is None:
            adjusted = max(1, parallelism // 2)
            return adjusted, adjusted < parallelism

        max_db_connections = 500
        saturation_high = max_db_connections * 0.90
        saturation_medium = max_db_connections * 0.80

        if conn_count > saturation_high:
            logger.warning(
                f"[{self.table_name}] RDS saturation HIGH ({conn_count}/{max_db_connections}). "
                f"Reducing parallelism {parallelism}->1"
            )
            return 1, True
        elif conn_count > saturation_medium:
            adjusted = max(1, parallelism // 2)
            if adjusted < parallelism:
                logger.warning(
                    f"[{self.table_name}] RDS saturation MEDIUM ({conn_count}/{max_db_connections}). "
                    f"Reducing parallelism {parallelism}->{adjusted}"
                )
            return adjusted, adjusted < parallelism

        return parallelism, False
