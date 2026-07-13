"""Error recovery and retry logic for dashboard rendering.

Implements transient vs permanent error classification, exponential backoff,
and automatic retry with state persistence.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from rich.layout import Layout
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

from algo.exceptions import ErrorCategory

logger = logging.getLogger(__name__)


def categorize_error(e: Exception) -> ErrorCategory:
    """Classify an exception as transient, permanent, or unknown.

    Maps exceptions to algo.exceptions.ErrorCategory for consistent retry logic.
    Falls back to PERMANENT for unknown errors (fail-safe behavior).
    """
    # Transient: network, timeout, rate-limit
    if isinstance(e, (TimeoutError, ConnectionError, BrokenPipeError)):
        return ErrorCategory.TRANSIENT
    if isinstance(e, OSError) and "429" in str(e):  # 429 Too Many Requests
        return ErrorCategory.TRANSIENT

    # Permanent: malformed data, missing keys, type mismatches
    if isinstance(e, (ValueError, KeyError, TypeError, AttributeError, IndexError)):
        return ErrorCategory.PERMANENT

    # Permanent: default to cautious fail-safe (don't retry unknown errors)
    return ErrorCategory.PERMANENT


@dataclass
class RenderState:
    """Track render attempts and recovery state."""

    last_good_layout: Layout | None = None
    last_good_time: datetime | None = None
    retry_count: int = 0
    error_category: ErrorCategory | None = None
    backoff_multiplier: float = 2.0  # Exponential: 0.5s → 1s → 2s → 4s...
    next_retry_time: datetime | None = None
    max_retries_transient: int = 10  # Retry transient errors up to 10 times
    max_retries_permanent: int = 3  # Give up on permanent errors sooner
    error_log: list[tuple[datetime, str, str]] = field(default_factory=list)  # Track all errors for diagnostics

    def get_recovery_status(self) -> str:
        if not self.error_category:
            # No error state: dashboard should render normally
            logger.debug("No active error category - rendering normally")
            return ""

        if self.error_category == ErrorCategory.TRANSIENT:
            if self.next_retry_time:
                secs = max(0, (self.next_retry_time - datetime.now()).total_seconds())
                return f"[yellow]Transient error, retrying in {secs:.1f}s... (attempt {self.retry_count})[/]"
            return f"[yellow]Transient error, retrying... (attempt {self.retry_count})[/]"
        elif self.error_category == ErrorCategory.PERMANENT:
            if self.retry_count >= self.max_retries_permanent:
                return "[red]Permanent error - no more retries. Reload dashboard to continue.[/]"
            return f"[red]Permanent error (malformed data), attempting repair (attempt {self.retry_count})...[/]"
        return "[red]Error with unknown category - no more retries. Reload dashboard to continue.[/]"

    def should_retry(self) -> bool:
        """Determine if we should retry based on error category and attempt count."""
        if not self.error_category:
            return False

        if self.error_category == ErrorCategory.TRANSIENT:
            return self.retry_count < self.max_retries_transient
        else:  # PERMANENT (fail-safe default for unknown/unclassified errors)
            return self.retry_count < self.max_retries_permanent

    def next_backoff_delay(self) -> float:
        if self.error_category == ErrorCategory.PERMANENT:
            return 2.0  # Permanent errors: steady 2s (unlikely to help anyway)

        # Exponential backoff: 0.5s * 2^(retry_count-1), max 30s
        base_delay = 0.5
        multiplier = self.backoff_multiplier if self.error_category == ErrorCategory.TRANSIENT else 1.5
        delay = base_delay * (multiplier ** (self.retry_count - 1))
        return min(delay, 30.0)


class RenderRecovery:
    """Manage render error recovery with exponential backoff and state persistence."""

    _lock = threading.Lock()

    def __init__(self) -> None:
        self.state = RenderState()

    def render_with_recovery(
        self, data: dict[str, Any], render_fn: Callable[[dict[str, Any]], Layout]
    ) -> tuple[Layout, str]:
        """Attempt to render with automatic retry on transient errors.

        Args:
            data: Dashboard data dict to pass to render_fn
            render_fn: Callable that takes data dict and returns Layout

        Returns:
            (layout, status_message) tuple:
            - layout: successful render or last good render (if available)
            - status_message: recovery status for display in error panel
        """
        # Check if we're in backoff period (hold lock for brief state read)
        with self._lock:
            if self.state.next_retry_time and datetime.now() < self.state.next_retry_time:
                # Still in backoff period, use cached render with status
                status = self.state.get_recovery_status()
                cached_layout = self.state.last_good_layout

            else:
                cached_layout = None
                status = None

        # If in backoff period, return cached result
        if status is not None:
            if cached_layout:
                return cached_layout, status
            return self._create_loading_panel(status), status

        # Attempt render (don't hold lock during potentially long operation)
        try:
            layout = render_fn(data)
            # Success: reset error state and cache this layout
            with self._lock:
                was_recovering = self.state.retry_count > 0
                self.state.last_good_layout = layout
                self.state.last_good_time = datetime.now()
                self.state.retry_count = 0
                self.state.error_category = None
                self.state.next_retry_time = None

            # Log recovery if we were previously in error state
            if was_recovering:
                logger.info("Render recovered successfully after transient error")
            else:
                logger.debug("Render successful with no active errors")

            return layout, ""  # Empty status = no error to display
        except Exception as e:
            # Error: categorize and decide retry (hold lock while updating state)
            with self._lock:
                self.state.error_category = categorize_error(e)
                self.state.error_log.append((datetime.now(), type(e).__name__, str(e)))
                self.state.retry_count += 1

                # Log error with appropriate level based on category
                error_msg = f"Render error ({self.state.error_category.value}): {type(e).__name__}: {e!s}"
                if self.state.error_category == ErrorCategory.PERMANENT:
                    logger.error(error_msg)
                elif self.state.error_category == ErrorCategory.TRANSIENT:
                    logger.warning(error_msg)
                else:
                    logger.warning(f"Unclassified error: {error_msg}")

                if self.state.should_retry():
                    # Schedule next retry
                    delay = self.state.next_backoff_delay()
                    self.state.next_retry_time = datetime.now() + timedelta(seconds=delay)
                    status = self.state.get_recovery_status()
                    logger.debug(f"Scheduled retry in {delay:.1f}s (attempt {self.state.retry_count})")
                else:
                    # Give up after max retries
                    status = self.state.get_recovery_status()
                    logger.error(f"Giving up on render after {self.state.retry_count} attempts")

                # CRITICAL: For finance apps, NEVER return stale cached renders.
                # Stale position/price/metric data is worse than no data.
                # Always display error panel to prevent silent use of outdated information.
                logger.error(
                    f"Render failed permanently - showing error instead of stale cached render "
                    f"(cache age: {self.state.last_good_time})"
                )
                return self._create_error_panel(e, status), status

    def should_retry_data_load(self) -> bool:
        """Check if data reload should be triggered (e.g., in watch mode).

        For transient errors, reloading data may help recover from API issues.

        Returns:
            True if data should be reloaded, False otherwise.
        """
        with self._lock:
            should_reload = (
                self.state.error_category == ErrorCategory.TRANSIENT
                and self.state.retry_count > 0
                and self.state.should_retry()
            )
            if should_reload:
                logger.debug("Data reload triggered to recover from transient error")
            return should_reload

    def get_recovery_status(self) -> str:
        with self._lock:
            status = self.state.get_recovery_status()
            if not status:
                logger.debug("No active recovery status - dashboard rendering normally")
            return status

    def _create_loading_panel(self, status: str) -> Layout:
        layout = Layout()
        content = Text.from_markup(f"[dim]Recovering from transient error... waiting for next retry[/]\n\n{status}")
        layout.update(Panel(content, title="[yellow]RECOVERING[/]", border_style="yellow"))
        return layout

    def _create_error_panel(self, e: Exception, status: str) -> Layout:
        layout = Layout()
        error_line = escape(f"{type(e).__name__}: {str(e)[:80]}")
        if status:
            content = f"[bold red]⚠ Render Error[/]\n[dim]{error_line}[/]\n\n{status}"
        else:
            content = f"[bold red]⚠ Render Error[/]\n[dim]{error_line}[/]"
        layout.update(
            Panel(
                Text.from_markup(content),
                title="[bold red]ERROR[/]",
                border_style="red",
            )
        )
        return layout
