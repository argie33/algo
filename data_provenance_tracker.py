#!/usr/bin/env python3
"""
Data Provenance Tracker - Complete audit trail for all loaded data.

Tracks:
  1. LOADER_RUN_ID - UUID for each loader execution (groups all rows from one run)
  2. SOURCE_TIMESTAMP - When the data was published (vs when loaded)
  3. LOAD_TIMESTAMP - When we actually inserted it
  4. DATA_CHECKSUM - Hash of the data (detect corruption, enable replay)
  5. SOURCE_API - Which API/file the data came from (yfinance, Alpaca, Polygon)
  6. ERROR_HANDLING - How errors were resolved (fallback, skip, or failed)
  7. REPLAY_CAPABILITY - Store enough info to replay any historical day

Enables:
  - Replay any date's trading with exact data used
  - Detect silent data corruption
  - Audit trail for regulatory compliance
  - Root-cause analysis (which API failed, when?)

DATABASE:
  All ticks stored with a data_provenance_id pointing to the loader run.
  Can query: "show me all data loaded by loadpricedaily on 2026-05-09"

USAGE:
  tracker = DataProvenanceTracker(loader_name='loadpricedaily')
  run_id = tracker.start_run()
  # ... load data ...
  tracker.record_tick(symbol='AAPL', tick_data, source='yfinance')
  tracker.end_run(success=True)
"""

import logging
import uuid
import hashlib
import json
from datetime import datetime, date as _date
from typing import Dict, List, Optional, Any
from decimal import Decimal
import psycopg2

logger = logging.getLogger(__name__)


class DataProvenanceTracker:
    """Tracks provenance of all loaded data for audit and replay."""

    def __init__(
        self,
        loader_name: str,
        table_name: str,
        db_conn: Optional[psycopg2.extensions.connection] = None,
        in_memory: bool = False,
    ):
        """
        Args:
            loader_name: Name of the loader (e.g., 'loadpricedaily')
            table_name: Table being loaded (e.g., 'price_daily')
            db_conn: Database connection (required if in_memory=False)
            in_memory: If True, store locally (for testing)
        """
        self.loader_name = loader_name
        self.table_name = table_name
        self.db_conn = db_conn
        self.in_memory = in_memory

        self.run_id: Optional[str] = None
        self.start_time: Optional[datetime] = None
        self.ticks_recorded: List[Dict] = [] if in_memory else []
        self.error_log: List[Dict] = []

    def start_run(
        self,
        source_api: str = "unknown",
        parameters: Optional[Dict] = None,
    ) -> str:
        """
        Start a new loader run. Returns run_id (UUID).

        Args:
            source_api: Which API this run is using (yfinance, alpaca, polygon)
            parameters: Any parameters passed to the loader

        Returns:
            run_id: UUID for this loader execution
        """
        self.run_id = str(uuid.uuid4())
        self.start_time = datetime.utcnow()

        if not self.in_memory:
            self._insert_loader_run(source_api, parameters)
        else:
            self.ticks_recorded = []
            self.error_log = []

        logger.info(
            f"[{self.loader_name}] Starting run {self.run_id} via {source_api}"
        )
        return self.run_id

    def record_tick(
        self,
        symbol: str,
        tick_date: _date,
        data: Dict[str, Any],
        source_timestamp: Optional[datetime] = None,
        source_api: str = "unknown",
    ) -> str:
        """
        Record that we loaded a tick of data.

        Args:
            symbol: Stock symbol
            tick_date: Date of the data point
            data: The actual OHLCV data (open, high, low, close, volume, etc)
            source_timestamp: When this data was published (vs when we loaded it)
            source_api: Which API provided it

        Returns:
            provenance_id: UUID for this tick's metadata
        """
        if not self.run_id:
            raise RuntimeError("Must call start_run() before recording ticks")

        provenance_id = str(uuid.uuid4())
        load_timestamp = datetime.utcnow()

        # Compute checksum for integrity verification
        checksum = self._compute_checksum(data)

        # Prepare data for JSON serialization (convert dates to strings)
        data_for_json = {k: v.isoformat() if isinstance(v, _date) else v for k, v in data.items()}

        record = {
            "provenance_id": provenance_id,
            "run_id": self.run_id,
            "loader_name": self.loader_name,
            "table_name": self.table_name,
            "symbol": symbol,
            "tick_date": tick_date,
            "source_timestamp": source_timestamp or load_timestamp,
            "load_timestamp": load_timestamp,
            "source_api": source_api,
            "data_checksum": checksum,
            "data_hash": hashlib.sha256(
                json.dumps(data_for_json, default=str, sort_keys=True).encode()
            ).hexdigest(),
            "data_size_bytes": len(json.dumps(data_for_json, default=str).encode()),
        }

        if not self.in_memory:
            self._insert_provenance_record(record)
        else:
            self.ticks_recorded.append(record)

        return provenance_id

    def record_error(
        self,
        symbol: str,
        error_type: str,
        error_message: str,
        resolution: str,  # 'skipped', 'fallback', 'retried', 'failed'
    ):
        """
        Record that we encountered an error and how we resolved it.

        Args:
            symbol: Stock symbol that had the error
            error_type: Type of error (API_LIMIT, DATA_INVALID, DB_ERROR, etc)
            error_message: Human-readable error
            resolution: How we handled it
        """
        error_record = {
            "run_id": self.run_id or "unknown",
            "loader_name": self.loader_name,
            "symbol": symbol,
            "error_type": error_type,
            "error_message": error_message,
            "resolution": resolution,
            "recorded_at": datetime.utcnow(),
        }

        if not self.in_memory:
            self._insert_error_record(error_record)
        else:
            self.error_log.append(error_record)

        logger.warning(
            f"[{self.loader_name}] {symbol}: {error_type} → {resolution}"
        )

    def end_run(
        self,
        success: bool,
        summary: Optional[Dict] = None,
    ):
        """
        Mark the run as complete.

        Args:
            success: Whether the run succeeded overall
            summary: Optional summary stats (rows_loaded, rows_failed, etc)
        """
        if not self.run_id or not self.start_time:
            return

        duration_seconds = (datetime.utcnow() - self.start_time).total_seconds()

        if not self.in_memory:
            self._finalize_loader_run(success, duration_seconds, summary)

        status = "SUCCESS" if success else "FAILED"
        logger.info(
            f"[{self.loader_name}] Run {self.run_id} completed: {status} "
            f"({duration_seconds:.1f}s, {len(self.ticks_recorded)} ticks)"
        )

    def get_run_replay_data(self, run_id: str) -> Dict[str, Any]:
        """
        Get all data and metadata for a specific loader run.
        Use this to replay a date's trades with exact data that was used.

        Args:
            run_id: The loader run ID

        Returns:
            Dict with all ticks and metadata for that run
        """
        if self.in_memory:
            return {
                "run_id": run_id,
                "ticks": [t for t in self.ticks_recorded if t["run_id"] == run_id],
                "errors": [e for e in self.error_log if e["run_id"] == run_id],
            }

        if not self.db_conn:
            return None

        with self.db_conn.cursor() as cur:
            # Get the loader run metadata
            cur.execute(
                """
                SELECT * FROM data_loader_runs
                WHERE run_id = %s
                """,
                (run_id,),
            )
            run = cur.fetchone()

            # Get all ticks from this run
            cur.execute(
                """
                SELECT * FROM data_provenance_log
                WHERE run_id = %s
                ORDER BY symbol, tick_date
                """,
                (run_id,),
            )
            ticks = cur.fetchall()

            # Get all errors from this run
            cur.execute(
                """
                SELECT * FROM data_provenance_errors
                WHERE run_id = %s
                ORDER BY recorded_at
                """,
                (run_id,),
            )
            errors = cur.fetchall()

            return {
                "run_id": run_id,
                "metadata": run,
                "ticks": ticks,
                "errors": errors,
            }

    # ========================================================================
    # PRIVATE: Database Operations
    # ========================================================================

    def _insert_loader_run(
        self,
        source_api: str,
        parameters: Optional[Dict],
    ):
        """Insert the loader run record."""
        if not self.db_conn:
            return

        try:
            with self.db_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO data_loader_runs
                    (run_id, loader_name, table_name, source_api, parameters, start_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        self.run_id,
                        self.loader_name,
                        self.table_name,
                        source_api,
                        json.dumps(parameters) if parameters else None,
                        self.start_time,
                    ),
                )
            self.db_conn.commit()
        except Exception as e:
            logger.error(f"Failed to insert loader run: {e}", exc_info=True)
            # Allow system to continue - provenance is non-critical

    def _insert_provenance_record(self, record: Dict):
        """Insert a provenance record for a tick."""
        if not self.db_conn:
            return

        try:
            with self.db_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO data_provenance_log
                    (provenance_id, run_id, loader_name, table_name, symbol, tick_date,
                     source_timestamp, load_timestamp, source_api, data_checksum, data_hash, data_size_bytes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record["provenance_id"],
                        record["run_id"],
                        record["loader_name"],
                        record["table_name"],
                        record["symbol"],
                        record["tick_date"],
                        record["source_timestamp"],
                        record["load_timestamp"],
                        record["source_api"],
                        record["data_checksum"],
                        record["data_hash"],
                        record["data_size_bytes"],
                    ),
                )
            self.db_conn.commit()
        except Exception as e:
            logger.error(f"Failed to insert provenance record for {record.get('symbol')}: {e}")
            # Allow system to continue - provenance is non-critical

    def _insert_error_record(self, error_record: Dict):
        """Insert an error record."""
        if not self.db_conn:
            return

        with self.db_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO data_provenance_errors
                (run_id, loader_name, symbol, error_type, error_message, resolution, recorded_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    error_record["run_id"],
                    error_record["loader_name"],
                    error_record["symbol"],
                    error_record["error_type"],
                    error_record["error_message"],
                    error_record["resolution"],
                    error_record["recorded_at"],
                ),
            )
        self.db_conn.commit()

    def _finalize_loader_run(
        self,
        success: bool,
        duration_seconds: float,
        summary: Optional[Dict],
    ):
        """Mark the loader run as complete."""
        if not self.db_conn or not self.run_id:
            return

        with self.db_conn.cursor() as cur:
            cur.execute(
                """
                UPDATE data_loader_runs
                SET success = %s,
                    end_at = NOW(),
                    duration_seconds = %s,
                    ticks_loaded = %s,
                    summary = %s
                WHERE run_id = %s
                """,
                (
                    success,
                    duration_seconds,
                    len(self.ticks_recorded),
                    json.dumps(summary) if summary else None,
                    self.run_id,
                ),
            )
        self.db_conn.commit()

    @staticmethod
    def _compute_checksum(data: Dict[str, Any]) -> str:
        """Compute a checksum of the data for integrity verification."""
        data_str = json.dumps(data, default=str, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()
