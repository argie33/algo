import os
import logging
from typing import Optional
from datetime import date, datetime

logger = logging.getLogger(__name__)


class DynamoDBWatermarkManager:
    """Persistent watermark storage using AWS DynamoDB."""

    def __init__(self, table_name: Optional[str] = None):
        """Initialize DynamoDB watermark manager.

        Args:
            table_name: DynamoDB table name. Defaults to WATERMARKS_TABLE env var.
        """
        self.table_name = table_name or os.getenv("WATERMARKS_TABLE")
        if not self.table_name:
            raise ValueError(
                "DynamoDB watermarks table name not specified. "
                "Set WATERMARKS_TABLE environment variable or pass table_name."
            )
        self._table = None
        self._try_connect()

    def _try_connect(self):
        """Lazy-load boto3 DynamoDB resource."""
        try:
            import boto3
            dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
            self._table = dynamodb.Table(self.table_name)
            # Test the connection with a head check
            self._table.table_status
            logger.info(f"Connected to DynamoDB watermarks table: {self.table_name}")
        except Exception as e:
            logger.warning(f"Failed to connect to DynamoDB: {e} — watermarks will be in-memory only")
            self._table = None

    def get(self, loader_id: str, symbol: Optional[str] = None) -> Optional[date]:
        """Retrieve the last watermark for a loader/symbol.

        Args:
            loader_id: Unique loader identifier (e.g., 'price_daily')
            symbol: Optional symbol. If provided, returns per-symbol watermark.

        Returns:
            The watermark date, or None if not found.
        """
        if not self._table:
            return None

        try:
            pk = f"{loader_id}#{symbol}" if symbol else loader_id
            response = self._table.get_item(Key={"loader_id": pk})
            item = response.get("Item")
            if item and item.get("watermark"):
                watermark_str = item["watermark"]
                # Parse ISO format date string
                if isinstance(watermark_str, str):
                    return datetime.fromisoformat(watermark_str).date()
                return watermark_str
            return None
        except Exception as e:
            logger.warning(f"Failed to get watermark for {loader_id}/{symbol}: {e}")
            return None

    def set(self, loader_id: str, watermark: date, symbol: Optional[str] = None, rows_loaded: int = 0) -> bool:
        """Update the watermark for a loader/symbol.

        Args:
            loader_id: Unique loader identifier
            watermark: The new watermark value
            symbol: Optional symbol for per-symbol tracking
            rows_loaded: Number of rows loaded (for metrics)

        Returns:
            True if successful, False otherwise
        """
        if not self._table:
            return False

        try:
            pk = f"{loader_id}#{symbol}" if symbol else loader_id
            self._table.put_item(
                Item={
                    "loader_id": pk,
                    "watermark": watermark.isoformat() if isinstance(watermark, date) else str(watermark),
                    "updated_at": datetime.utcnow().isoformat(),
                    "rows_loaded": rows_loaded,
                }
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to set watermark for {loader_id}/{symbol}: {e}")
            return False
