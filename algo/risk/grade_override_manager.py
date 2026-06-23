"""Grade Override Safety Manager

Manages the grade override feature with safeguards:
- Explicit enable/disable flag
- Time-bound duration (auto-reset at market close)
- Logging of every trade with override applied
- Alerting if override active for >N hours
"""

import logging
import threading
from datetime import datetime, timezone

from algo.infrastructure.config import get_config

logger = logging.getLogger(__name__)

_override_state_lock = threading.Lock()
_override_enabled_at: datetime | None = None


def is_grade_override_enabled() -> bool:
    """Check if grade override is currently enabled.

    Returns: bool (True if override is active and enabled)
    """
    config = get_config()
    grade_override_val = config.get("grade_override_enabled")
    if grade_override_val is None:
        logger.warning("grade_override_enabled config missing, assuming disabled")
        return False
    return bool(grade_override_val)


def get_override_duration_minutes() -> int:
    """Get configured max duration for override in minutes.

    CRITICAL: If grade override is enabled, duration config MUST be present.
    Fail fast to prevent grade override running indefinitely.
    """
    config = get_config()
    is_enabled = config.get("grade_override_enabled")

    if not is_enabled:
        return 60  # Default when override not enabled

    val = config.get("grade_override_max_duration_minutes")
    if val is None:
        raise ValueError(
            "CRITICAL: grade_override_enabled is True but grade_override_max_duration_minutes config missing. "
            "Cannot use grade override without explicit time limit. Set max duration in minutes."
        )
    return int(val)


def get_override_state() -> tuple[bool, datetime | None, int | None]:
    """Get current override state.

    Returns: (is_enabled, enabled_at_time, minutes_active)
    """
    global _override_enabled_at

    with _override_state_lock:
        is_enabled = is_grade_override_enabled()

        if not is_enabled:
            return (False, None, None)

        if _override_enabled_at is None:
            _override_enabled_at = datetime.now(timezone.utc)

        now = datetime.now(timezone.utc)
        minutes_active = int((now - _override_enabled_at).total_seconds() / 60)

        return (True, _override_enabled_at, minutes_active)


def log_override_activation(reason: str = "config_change") -> None:
    """Log that grade override was activated."""
    global _override_enabled_at

    with _override_state_lock:
        if _override_enabled_at is None:
            _override_enabled_at = datetime.now(timezone.utc)

        logger.warning(
            "[GRADE_OVERRIDE] ACTIVATED: min_swing_grade override enabled. "
            f"Reason: {reason}. "
            f"Auto-resets at market close. "
            f"Enabled at: {_override_enabled_at.isoformat()}"
        )


def reset_override() -> None:
    """Reset override state (called at market close)."""
    global _override_enabled_at

    with _override_state_lock:
        if _override_enabled_at is not None:
            was_enabled_at = _override_enabled_at
            duration_minutes = int((datetime.now(timezone.utc) - was_enabled_at).total_seconds() / 60)
            _override_enabled_at = None

            logger.warning(
                "[GRADE_OVERRIDE] AUTO-RESET at market close. "
                f"Was active for {duration_minutes} minutes. "
                f"Enabled at: {was_enabled_at.isoformat()}"
            )
        else:
            logger.info("[GRADE_OVERRIDE] Reset called (was not active)")


def check_and_alert_on_long_duration() -> bool:
    """Check if override has been active too long and log alert.

    Returns: bool (True if alert was triggered)
    """
    is_enabled, enabled_at, minutes_active = get_override_state()

    if not is_enabled or minutes_active is None:
        return False

    max_duration = get_override_duration_minutes()

    if minutes_active > max_duration:
        logger.error(
            "[GRADE_OVERRIDE] ALERT: Override active for %d minutes (max: %d). "
            "Enabled at: %s. Action required: Disable override or extend deadline.",
            minutes_active,
            max_duration,
            enabled_at.isoformat() if enabled_at else "unknown",
        )
        return True

    return False


def log_trade_with_override(symbol: str, entry_price: float, direction: str = "long") -> None:
    """Log that a trade was entered with grade override active.

    Args:
        symbol: Stock ticker
        entry_price: Entry price
        direction: Trade direction (long/short)
    """
    is_enabled, _, minutes_active = get_override_state()

    if is_enabled:
        logger.warning(
            "[GRADE_OVERRIDE] TRADE ENTERED WITH OVERRIDE: %s %s @ $%.2f. Override enabled for %d minutes (max: %d).",
            direction.upper(),
            symbol,
            entry_price,
            minutes_active or 0,
            get_override_duration_minutes(),
        )


def validate_override_state_against_config() -> bool:
    """Validate that override state is consistent with config.

    This is called periodically to detect config changes that enable/disable override.

    Returns: bool (True if consistency check passed)
    """
    is_enabled = is_grade_override_enabled()
    _, enabled_at, _ = get_override_state()

    if is_enabled and enabled_at is None:
        log_override_activation("config_detected")
    elif not is_enabled and enabled_at is not None:
        logger.info(f"[GRADE_OVERRIDE] Override was disabled via config. Was active since: {enabled_at.isoformat()}")
        reset_override()

    return True
