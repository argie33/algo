#!/usr/bin/env python3
"""Halt Flag Manager - Centralized halt flag state management."""

import logging
import os
from datetime import datetime, timezone


logger = logging.getLogger(__name__)


class HaltFlagManager:
    """Manages halt flag lifecycle in DynamoDB."""

    HALT_FLAG_DYNAMODB_KEY = "orchestrator_halt"

    def __init__(self) -> None:
        """Initialize with DynamoDB access."""
        self.table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")

    def check_halt_flag(self) -> bool:
        """Check if halt flag is active."""
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
            table = dynamodb.Table(self.table_name)
            response = table.get_item(Key={"key": self.HALT_FLAG_DYNAMODB_KEY})
            return response.get("Item", {}).get("halt_flag", False) is True
        except Exception as e:
            logger.critical(f"[HALT_FLAG] Check failed: {e}")
            return True

    def set_halt_flag(self, reason: str = "") -> bool:
        """Set halt flag in DynamoDB."""
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
            table = dynamodb.Table(self.table_name)
            now_utc = datetime.now(timezone.utc)
            table.put_item(
                Item={
                    "key": self.HALT_FLAG_DYNAMODB_KEY,
                    "halt_flag": True,
                    "triggered_at": now_utc.isoformat(),
                    "reason": reason or "Halt triggered",
                }
            )
            logger.critical(f"[HALT_FLAG_SET] {reason}")
            return True
        except Exception as e:
            logger.critical(f"[HALT_FLAG] Set failed: {e}")
            raise RuntimeError(f"Failed to set halt flag: {e}") from e

    def clear_halt_flag(self, reason: str = "") -> bool:
        """Clear halt flag in DynamoDB."""
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
            table = dynamodb.Table(self.table_name)
            now_utc = datetime.now(timezone.utc)
            table.put_item(
                Item={
                    "key": self.HALT_FLAG_DYNAMODB_KEY,
                    "halt_flag": False,
                    "reset_at": now_utc.isoformat(),
                    "reason": reason or "Halt cleared",
                }
            )
            logger.info(f"[HALT_FLAG_CLEAR] {reason}")
            return True
        except Exception as e:
            logger.critical(f"[HALT_FLAG] Clear failed: {e}")
            raise RuntimeError(f"Failed to clear halt flag: {e}") from e
