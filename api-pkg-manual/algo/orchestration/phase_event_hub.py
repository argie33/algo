#!/usr/bin/env python3
"""Phase EventHub - Pub/sub event system for phase execution.

Decouples phase execution from dashboard/API consumers by implementing event-driven
architecture. Phases publish events; consumers subscribe independently.

PROBLEM SOLVED:
- Phase schema changes (15+ file ripple) -> single publish point
- Tight coupling (dashboard reads phase internals) -> event subscriptions
- Shotgun surgery (same change scattered everywhere) -> centralized event stream

EVENT TYPES:
- phase_started(phase_num, name, timestamp)
- phase_completed(phase_num, name, status, summary, metrics)
- phase_error(phase_num, name, error, timestamp)
- metrics_published(phase_num, metrics_dict, timestamp)
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PhaseStatus(Enum):
    """Phase execution status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    DEGRADED = "degraded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PhaseEvent:
    """Base event for phase lifecycle."""

    event_type: str
    phase_num: int | str
    phase_name: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "event_type": self.event_type,
            "phase_num": self.phase_num,
            "phase_name": self.phase_name,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }


@dataclass
class PhaseStartedEvent(PhaseEvent):
    """Fired when phase execution starts."""

    def __init__(self, phase_num: int | str, phase_name: str):
        super().__init__(
            event_type="phase_started",
            phase_num=phase_num,
            phase_name=phase_name,
        )


@dataclass
class PhaseCompletedEvent(PhaseEvent):
    """Fired when phase execution completes."""

    def __init__(
        self,
        phase_num: int | str,
        phase_name: str,
        status: PhaseStatus,
        summary: str = "",
        metrics: dict[str, Any] | None = None,
    ):
        if metrics is None:
            raise ValueError(
                f"[PHASE_EVENT] Phase completion event for '{phase_name}' missing metrics. "
                f"Cannot publish phase completion without metrics data—events with missing metrics hide phase progress. "
                f"Ensure phase executor populates metrics before firing PhaseCompletedEvent."
            )
        super().__init__(
            event_type="phase_completed",
            phase_num=phase_num,
            phase_name=phase_name,
            details={
                "status": status.value,
                "summary": summary,
                "metrics": metrics,
            },
        )


@dataclass
class PhaseErrorEvent(PhaseEvent):
    """Fired when phase execution fails."""

    def __init__(
        self,
        phase_num: int | str,
        phase_name: str,
        error: str,
    ):
        super().__init__(
            event_type="phase_error",
            phase_num=phase_num,
            phase_name=phase_name,
            details={"error": error},
        )


class PhaseEventHub:
    """Centralized pub/sub hub for phase execution events.

    USAGE:
        hub = PhaseEventHub()

        # Publisher (orchestrator)
        hub.publish(PhaseStartedEvent(1, "Data Freshness"))
        hub.publish(PhaseCompletedEvent(1, "Data Freshness", PhaseStatus.SUCCESS))

        # Subscribers (dashboard, API, monitoring)
        hub.subscribe("phase_completed", dashboard_handler)
        hub.subscribe("phase_error", alert_handler)
    """

    def __init__(self) -> None:
        """Initialize event hub."""
        self.subscribers: dict[str, list[Callable[..., Any]]] = {}
        self.event_history: list[PhaseEvent] = []
        self.max_history = 1000  # Keep last 1000 events in memory

    def subscribe(self, event_type: str, callback: Callable[..., Any]) -> None:
        """Subscribe to phase events.

        Args:
            event_type: Event type to subscribe to (e.g., "phase_completed")
            callback: Callable to invoke when event fires. Signature: callback(event: PhaseEvent) -> None
        """
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)
        logger.debug(f"[EVENT_HUB] Subscriber registered for {event_type}")

    def publish(self, event: PhaseEvent) -> None:
        """Publish phase event to all subscribers.

        Args:
            event: PhaseEvent instance to publish
        """
        logger.info(f"[EVENT_HUB] Publishing {event.event_type} for phase {event.phase_num}")

        # Store in history
        self.event_history.append(event)
        if len(self.event_history) > self.max_history:
            self.event_history.pop(0)

        # Invoke all subscribers for this event type
        # CRITICAL FIX: Explicit checks for subscriber lists instead of empty defaults
        type_subscribers = self.subscribers.get(event.event_type)
        if type_subscribers is None:
            logger.debug(f"[EVENT_HUB] No subscribers registered for {event.event_type}")
        elif isinstance(type_subscribers, list):
            for callback in type_subscribers:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"[EVENT_HUB] Subscriber failed for {event.event_type}: {e}")
        else:
            logger.warning(
                f"[EVENT_HUB] Subscriber list for {event.event_type} is not a list: {type(type_subscribers)}"
            )

        # Also invoke any "wildcard" subscribers listening to all events
        wildcard_subscribers = self.subscribers.get("*")
        if wildcard_subscribers is None:
            logger.debug("[EVENT_HUB] No wildcard subscribers registered")
        elif isinstance(wildcard_subscribers, list):
            for callback in wildcard_subscribers:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"[EVENT_HUB] Wildcard subscriber failed: {e}")
        else:
            logger.warning(f"[EVENT_HUB] Wildcard subscriber list is not a list: {type(wildcard_subscribers)}")

    def get_history(self, event_type: str | None = None, phase_num: int | str | None = None) -> list[PhaseEvent]:
        """Get event history, optionally filtered by type or phase.

        Args:
            event_type: Filter by event type (e.g., "phase_completed")
            phase_num: Filter by phase number

        Returns:
            List of matching events from history
        """
        results = self.event_history
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if phase_num is not None:
            results = [e for e in results if e.phase_num == phase_num]
        return results

    def get_phase_status(self, phase_num: int | str) -> PhaseStatus | None:
        """Get the current status of a phase.

        Args:
            phase_num: Phase number

        Returns:
            Current PhaseStatus if phase has completed with valid status
            None: if no completion event found in history (phase not yet completed)

        Raises ValueError if phase exists with invalid status string.
        """
        # Look backwards through history for most recent completion event
        for event in reversed(self.event_history):
            if event.phase_num == phase_num and event.event_type == "phase_completed":
                status_str = event.details.get("status")
                if status_str:
                    try:
                        return PhaseStatus(status_str)
                    except ValueError as e:
                        raise ValueError(
                            f"Phase {phase_num} has invalid status '{status_str}' in event history. "
                            f"Valid statuses: {', '.join(s.value for s in PhaseStatus)}"
                        ) from e
        logger.debug(f"[PHASE_EVENT_HUB] No completion event found for phase {phase_num} (not yet completed)")
        return None

    def clear_history(self) -> None:
        """Clear event history (for testing)."""
        self.event_history.clear()


# Global singleton instance
_event_hub: PhaseEventHub | None = None


def get_event_hub() -> PhaseEventHub:
    """Get or create the global event hub singleton."""
    global _event_hub
    if _event_hub is None:
        _event_hub = PhaseEventHub()
    return _event_hub


def reset_event_hub() -> None:
    """Reset event hub (for testing)."""
    global _event_hub
    _event_hub = None
