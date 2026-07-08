"""Check handler strategies for trade validation.

Eliminates if-elif chains by using strategy pattern for different check result types.
Each check type has a dedicated handler that knows how to unpack and process its result tuple.
"""

from abc import ABC, abstractmethod
from typing import Any


class CheckResultHandler(ABC):
    """Base class for check result handlers."""

    @abstractmethod
    def process(self, result: tuple[Any, ...]) -> tuple[bool, str, dict[str, Any] | None]:
        """Process check result.

        Args:
            result: Tuple result from the check (structure varies by check type)

        Returns:
            (should_return_early, error_msg, status_dict_or_none)
        """


class IdempotentCheckHandler(CheckResultHandler):
    """Handles idempotent check results."""

    def process(self, result: tuple[Any, ...]) -> tuple[bool, str, dict[str, Any] | None]:
        is_dup, error_msg, existing_trade_id = result
        if is_dup:
            # CRITICAL: If duplicate detected, existing_trade_id must be present
            if not existing_trade_id:
                raise ValueError(
                    f"Duplicate trade detected but existing_trade_id missing. "
                    f"Cannot validate without prior trade reference. error_msg={error_msg}"
                )
            if not error_msg:
                raise ValueError(
                    "Duplicate trade detected but error_msg missing. Cannot proceed without validation context."
                )
            return (
                True,
                error_msg,
                {
                    "status": "duplicate",
                    "trade_id": existing_trade_id,
                    "duplicate": True,
                },
            )
        return False, "", None


class OpenPositionCheckHandler(CheckResultHandler):
    """Handles open position check results."""

    def process(self, result: tuple[Any, ...]) -> tuple[bool, str, dict[str, Any] | None]:
        is_dup, error_msg = result
        if is_dup:
            return (
                True,
                error_msg,
                {"status": "duplicate", "duplicate": True},
            )
        return False, "", None


class FingerprintCheckHandler(CheckResultHandler):
    """Handles fingerprint check results."""

    def process(self, result: tuple[Any, ...]) -> tuple[bool, str, dict[str, Any] | None]:
        is_dup, error_msg, existing_trade_id = result
        if is_dup:
            # CRITICAL: If duplicate detected, existing_trade_id must be present
            if not existing_trade_id:
                raise ValueError(
                    f"Fingerprint duplicate detected but existing_trade_id missing. "
                    f"Cannot validate without prior trade reference. error_msg={error_msg}"
                )
            if not error_msg:
                raise ValueError(
                    "Fingerprint duplicate detected but error_msg missing. Cannot proceed without validation context."
                )
            return (
                True,
                error_msg,
                {
                    "status": "duplicate",
                    "trade_id": existing_trade_id,
                    "duplicate": True,
                },
            )
        return False, "", None


class PendingCheckHandler(CheckResultHandler):
    """Handles pending trade check results."""

    def process(self, result: tuple[Any, ...]) -> tuple[bool, str, dict[str, Any] | None]:
        has_pending, error_msg, _ = result
        if has_pending:
            return (
                True,
                error_msg,
                {"status": "pending_trade_exists"},
            )
        return False, "", None


class ReentryCheckHandler(CheckResultHandler):
    """Handles reentry check results."""

    def process(self, result: tuple[Any, ...]) -> tuple[bool, str, dict[str, Any] | None]:
        valid, error_msg, _ = result
        if not valid:
            # CRITICAL: If reentry validation fails, error_msg must be present for diagnosis
            if not error_msg:
                raise ValueError(
                    "Reentry check failed but error_msg missing. "
                    "Cannot determine failure reason without validation context."
                )
            status = "reentry_blocked" if "prior re-entries" in error_msg else "reentry_cooldown"
            return (
                True,
                error_msg,
                {
                    "status": status,
                    "reentry_blocked": "prior" in error_msg.lower(),
                },
            )
        return False, "", None


class CheckHandlerRegistry:
    """Registry for check result handlers."""

    _handlers: dict[str, CheckResultHandler] = {
        "idempotent": IdempotentCheckHandler(),
        "open_position": OpenPositionCheckHandler(),
        "fingerprint": FingerprintCheckHandler(),
        "pending": PendingCheckHandler(),
        "reentry": ReentryCheckHandler(),
    }

    @classmethod
    def get_handler(cls, check_name: str) -> CheckResultHandler:
        """Get handler for check type.

        Args:
            check_name: Name of the check

        Returns:
            Handler for the check type

        Raises:
            ValueError: If check type is not registered
        """
        if check_name not in cls._handlers:
            raise ValueError(f"Unknown check type: {check_name}. Available: {list(cls._handlers.keys())}")
        return cls._handlers[check_name]

    @classmethod
    def register(cls, check_name: str, handler: CheckResultHandler) -> None:
        """Register a new check handler.

        Args:
            check_name: Name of the check
            handler: Handler instance for the check
        """
        cls._handlers[check_name] = handler
