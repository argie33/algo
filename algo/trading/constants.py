"""Trading constants — single source of truth for all status values, thresholds, and enums.

Principle: No hardcoded strings or magic numbers outside this module.
All status checks use these enums. All thresholds come from algo_config table.
"""

from enum import Enum


class PositionStatus(str, Enum):
    """Valid position statuses. Use these enums instead of string literals."""

    OPEN = "open"
    CLOSED = "closed"
    HALTED = "halted"
    CANCELLED = "cancelled"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a string is a valid position status."""
        return value.lower() in {s.value for s in cls}

    @classmethod
    def normalize(cls, value: str | None) -> str | None:
        """Normalize status to lowercase. Prevents 'OPEN' vs 'open' bugs."""
        if value is None:
            return None
        normalized = value.lower()
        if cls.is_valid(normalized):
            return normalized
        raise ValueError(f"Invalid status: {value}")


class TradeStatus(str, Enum):
    """Valid trade statuses."""

    OPEN = "open"
    CLOSED = "closed"
    FILLED = "filled"
    HALTED = "halted"
    CANCELLED = "cancelled"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value.lower() in {s.value for s in cls}

    @classmethod
    def normalize(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.lower()
        if cls.is_valid(normalized):
            return normalized
        raise ValueError(f"Invalid trade status: {value}")


class DataUnavailableReason(str, Enum):
    """Standardized reasons for data being unavailable."""

    LOADER_FAILURE = "loader_failure"
    UPSTREAM_ERROR = "upstream_error"
    INSUFFICIENT_HISTORY = "insufficient_history"
    DATA_QUALITY_GATE = "data_quality_gate"
    MISSING_FIELDS = "missing_fields"
    VALIDATION_ERROR = "validation_error"
    FEATURE_NOT_AVAILABLE = "feature_not_available"


class SignalGrade(str, Enum):
    """Signal quality grades based on score."""

    A = "A"  # score >= 80
    B = "B"  # 60 <= score < 80
    C = "C"  # 40 <= score < 60
    D = "D"  # score < 40

    @classmethod
    def from_score(cls, score: float) -> "SignalGrade":
        """Determine grade from numeric score. Single source of truth."""
        if score >= 80:
            return cls.A
        elif score >= 60:
            return cls.B
        elif score >= 40:
            return cls.C
        else:
            return cls.D


class WeinsteinStage(int, Enum):
    """Weinstein trend template stages."""

    STAGE_1 = 1  # Base/accumulation
    STAGE_2 = 2  # Trend/advance (early, mid, late)
    STAGE_3 = 3  # Top/distribution
    STAGE_4 = 4  # Decline/downtrend

    @classmethod
    def is_valid(cls, value: int) -> bool:
        return value in {s.value for s in cls}

    def description(self) -> str:
        """Human-readable stage description."""
        descriptions = {
            1: "Base (accumulation)",
            2: "Trend (advance)",
            3: "Top (distribution)",
            4: "Decline (downtrend)",
        }
        return descriptions.get(self.value, "Unknown")


# Configuration gate values (from algo_config table)
# These are the DEFAULTS; actual values should come from algo_config at runtime.
# Use AlgoConfig class to read these, not hardcode them.
DEFAULT_SIGNAL_SCORE_THRESHOLD = 60
DEFAULT_COMPOSITE_SCORE_THRESHOLD = 50
DEFAULT_DATA_COMPLETENESS_THRESHOLD = 0.70
DEFAULT_ENTRY_VOLUME_THRESHOLD = 300000
DEFAULT_ENTRY_DOLLAR_VOLUME = 500000

# Validation gates (fixed, not configurable)
MIN_PRICE_HISTORY_DAYS = 30
MIN_REQUIRED_METRICS_FOR_SCORE = 3
MIN_SIGNAL_SCORE_FLOOR = 40
MAX_SIGNAL_SCORE_CEIL = 100
