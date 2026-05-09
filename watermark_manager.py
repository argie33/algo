#!/usr/bin/env python3
"""
Persistent Watermark Manager for Incremental Data Loading

Tracks the last successfully loaded data for each source:
- Last load timestamp (for time-based incremental loads)
- Last ID/cursor (for ID-based incremental loads)
- Load status and error tracking

Supports two backends:
1. DynamoDB (production): Distributed, serverless, multi-region ready
2. Local JSON file (development): Fast, requires no AWS setup

Usage:
    # Initialize manager
    watermark = WatermarkManager(source='daily_prices')

    # Get last successful load time
    last_timestamp = watermark.get_last_timestamp()
    if last_timestamp:
        # Load only data since last_timestamp
        data = fetch_data(since=last_timestamp)

    # Update after successful load
    watermark.set_last_timestamp(new_timestamp)
    watermark.mark_success(records_loaded=1000)

    # Handle failures
    watermark.mark_failure(error="API rate limited")
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

log = logging.getLogger(__name__)


class WatermarkManager:
    """Manages persistent watermarks for incremental data loading."""

    def __init__(self, source: str, backend: str = None):
        """
        Initialize watermark manager.

        Args:
            source: Name of data source (e.g., 'daily_prices', 'earnings', 'sentiment')
            backend: 'dynamodb' (prod) or 'local' (dev). Auto-detected if not provided.
        """
        self.source = source
        self.backend = backend or self._detect_backend()
        self._table = None
        self._local_file = None

        if self.backend == "dynamodb":
            self._init_dynamodb()
        elif self.backend == "local":
            self._init_local()
        else:
            raise ValueError(f"Unknown backend: {self.backend}")

        log.debug(f"Watermark manager initialized for {source} (backend: {self.backend})")

    def _detect_backend(self) -> str:
        """Auto-detect backend based on environment."""
        if os.getenv("AWS_EXECUTION_ENV") or os.getenv("AWS_REGION"):
            return "dynamodb"
        return "local"

    def _init_dynamodb(self):
        """Initialize DynamoDB backend."""
        try:
            import boto3
            region = os.getenv("AWS_REGION", "us-east-1")
            table_name = os.getenv("WATERMARK_TABLE", "algo-watermarks")

            dynamodb = boto3.resource("dynamodb", region_name=region)
            self._table = dynamodb.Table(table_name)

            # Test connection
            self._table.table_status  # Will fail if table doesn't exist
            log.info(f"Connected to DynamoDB table: {table_name}")

        except Exception as e:
            log.error(f"Failed to initialize DynamoDB: {e}")
            log.warning("Falling back to local file backend")
            self.backend = "local"
            self._init_local()

    def _init_local(self):
        """Initialize local file backend."""
        base_dir = Path(os.getenv("WATERMARK_DIR", "./.watermarks"))
        base_dir.mkdir(exist_ok=True)

        self._local_file = base_dir / f"{self.source}.json"
        log.info(f"Using local watermark file: {self._local_file}")

    def get_last_timestamp(self) -> Optional[datetime]:
        """Get timestamp of last successful load."""
        record = self._get_record()
        if record and "last_timestamp" in record:
            try:
                return datetime.fromisoformat(record["last_timestamp"])
            except (ValueError, TypeError):
                return None
        return None

    def set_last_timestamp(self, timestamp: datetime) -> None:
        """Set timestamp of last successful load."""
        if not isinstance(timestamp, datetime):
            raise TypeError("timestamp must be datetime object")

        record = self._get_record()
        record["last_timestamp"] = timestamp.isoformat()
        self._save_record(record)

        log.debug(f"Set watermark timestamp to {timestamp}")

    def get_last_id(self) -> Optional[str]:
        """Get last record ID (for ID-based incremental loading)."""
        record = self._get_record()
        return record.get("last_id") if record else None

    def set_last_id(self, last_id: str) -> None:
        """Set last record ID."""
        record = self._get_record()
        record["last_id"] = str(last_id)
        self._save_record(record)

        log.debug(f"Set watermark ID to {last_id}")

    def mark_success(self, records_loaded: int = 0, metadata: Dict = None) -> None:
        """Mark a successful load."""
        record = self._get_record()
        record["status"] = "success"
        record["last_load_at"] = datetime.utcnow().isoformat()
        record["records_loaded"] = records_loaded
        record["error"] = None

        if metadata:
            record["metadata"] = metadata

        self._save_record(record)
        log.info(f"Marked {self.source} as success ({records_loaded} records)")

    def mark_failure(self, error: str) -> None:
        """Mark a failed load."""
        record = self._get_record()
        record["status"] = "failed"
        record["last_error_at"] = datetime.utcnow().isoformat()
        record["error"] = error
        record["error_count"] = record.get("error_count", 0) + 1

        self._save_record(record)
        log.warning(f"Marked {self.source} as failed: {error}")

    def get_status(self) -> Dict[str, Any]:
        """Get current watermark status."""
        record = self._get_record()
        if not record:
            return {
                "source": self.source,
                "status": "never_loaded",
                "last_timestamp": None,
                "last_id": None
            }

        return {
            "source": self.source,
            "status": record.get("status"),
            "last_timestamp": record.get("last_timestamp"),
            "last_id": record.get("last_id"),
            "last_load_at": record.get("last_load_at"),
            "last_error_at": record.get("last_error_at"),
            "error": record.get("error"),
            "error_count": record.get("error_count", 0),
            "records_loaded": record.get("records_loaded", 0)
        }

    def clear(self) -> None:
        """Clear watermark (useful for testing or full reload)."""
        if self.backend == "dynamodb":
            try:
                self._table.delete_item(Key={"source": self.source})
                log.info(f"Cleared watermark for {self.source}")
            except Exception as e:
                log.error(f"Failed to clear watermark: {e}")
        elif self.backend == "local":
            if self._local_file.exists():
                self._local_file.unlink()
                log.info(f"Cleared watermark file: {self._local_file}")

    # ============================================================================
    # Private Methods
    # ============================================================================

    def _get_record(self) -> Dict[str, Any]:
        """Get record from backend (returns empty dict if not found)."""
        if self.backend == "dynamodb":
            return self._get_dynamodb_record()
        else:
            return self._get_local_record()

    def _get_dynamodb_record(self) -> Dict[str, Any]:
        """Fetch record from DynamoDB."""
        try:
            response = self._table.get_item(Key={"source": self.source})
            return response.get("Item", {})
        except Exception as e:
            log.warning(f"Failed to fetch DynamoDB record: {e}")
            return {}

    def _get_local_record(self) -> Dict[str, Any]:
        """Fetch record from local file."""
        if not self._local_file.exists():
            return {}

        try:
            with open(self._local_file, "r") as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"Failed to read local watermark: {e}")
            return {}

    def _save_record(self, record: Dict) -> None:
        """Save record to backend."""
        record["source"] = self.source  # Always include source
        record["updated_at"] = datetime.utcnow().isoformat()

        if self.backend == "dynamodb":
            self._save_dynamodb_record(record)
        else:
            self._save_local_record(record)

    def _save_dynamodb_record(self, record: Dict) -> None:
        """Save record to DynamoDB."""
        try:
            # Convert datetime strings to ensure they're JSON-serializable
            self._table.put_item(Item=record)
            log.debug(f"Saved watermark to DynamoDB: {self.source}")
        except Exception as e:
            log.error(f"Failed to save DynamoDB record: {e}")
            raise

    def _save_local_record(self, record: Dict) -> None:
        """Save record to local file."""
        try:
            with open(self._local_file, "w") as f:
                json.dump(record, f, indent=2, default=str)
            log.debug(f"Saved watermark to file: {self._local_file}")
        except Exception as e:
            log.error(f"Failed to save local watermark: {e}")
            raise


class WatermarkBatch:
    """Context manager for batching multiple watermark updates."""

    def __init__(self, *managers: WatermarkManager):
        """
        Initialize batch update context.

        Usage:
            with WatermarkBatch(wm1, wm2) as batch:
                # ... do work ...
                batch.mark_success()  # Marks all as success
        """
        self.managers = managers
        self.success = True
        self.error = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.success = False
            self.error = str(exc_val)
            self.mark_failure(self.error)
        elif self.success:
            self.mark_success()

        return False  # Re-raise exceptions

    def mark_success(self, records_loaded: int = 0) -> None:
        """Mark all watermarks as successful."""
        for manager in self.managers:
            manager.mark_success(records_loaded)

    def mark_failure(self, error: str) -> None:
        """Mark all watermarks as failed."""
        for manager in self.managers:
            manager.mark_failure(error)


# Module-level cache for watermark managers (singleton-like)
_watermark_cache = {}


def get_watermark(source: str) -> WatermarkManager:
    """Get or create watermark manager for a source."""
    if source not in _watermark_cache:
        _watermark_cache[source] = WatermarkManager(source)
    return _watermark_cache[source]


def clear_watermark_cache() -> None:
    """Clear cached watermark managers (useful for testing)."""
    _watermark_cache.clear()
