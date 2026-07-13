"""Formatter strategy classes for dashboard display.

Replaces if-elif chains with pluggable formatter strategies.
Each formatter handles a specific formatting task independently.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .utilities import ET


class FormatterStrategy(ABC):
    """Base class for all formatter strategies."""

    @abstractmethod
    def format(self, value: Any) -> str: ...


class GradeFormatter(FormatterStrategy):
    """Converts numeric score (0-100) to letter grade."""

    def format(self, score: Any) -> str:
        """Convert score to letter grade: A+, A, B, C, D."""
        try:
            s = float(score)
        except (ValueError, TypeError):
            return "D"

        if s >= 90:
            return "A+"
        if s >= 80:
            return "A"
        if s >= 70:
            return "B"
        if s >= 60:
            return "C"
        return "D"


class TierFormatter(FormatterStrategy):
    """Converts percentage to market tier classification."""

    TIER_MAP = {
        80: "confirmed_uptrend",
        60: "uptrend_under_pressure",
        40: "caution",
        0: "correction",
    }

    def format(self, percentage: Any) -> str:
        """Convert percentage to tier name."""
        if percentage is None:
            return "unknown"

        try:
            p = float(percentage)
        except (ValueError, TypeError):
            return "unknown"

        for threshold in sorted(self.TIER_MAP.keys(), reverse=True):
            if p >= threshold:
                return self.TIER_MAP[threshold]
        return "unknown"


class SignFormatter(FormatterStrategy):

    def format(self, value: Any) -> str:
        try:
            v = float(value)
            return "+" if v >= 0 else "-"  # Always return explicit +/- sign, not empty
        except (ValueError, TypeError):
            return "--"  # Error case - explicit marker, not empty


class MarketHoursFormatter(FormatterStrategy):

    def format(self, minutes: int) -> str:
        """Convert minutes to human-readable countdown: '5h30m', '45m', etc."""
        if minutes < 0:
            minutes = 0

        if minutes < 60:
            return f"{minutes}m"
        if minutes < 1440:
            h, m = divmod(minutes, 60)
            return f"{h}h{m:02d}m"
        return f"{minutes // 1440}d"


class DataAgeFormatter(FormatterStrategy):

    def format(self, ts: Any) -> str:
        """Convert timestamp to age: '5m ago', '2h10m ago', '3d ago'."""
        if ts is None:
            return "--"

        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except ValueError:
                return "--"

        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=ET)
        else:
            return "--"

        try:
            m = int((datetime.now(ET) - ts).total_seconds() / 60)
        except (TypeError, ValueError):
            return "--"

        if m < 60:
            return f"{m}m ago"
        if m < 1440:
            return f"{m // 60}h{m % 60:02d}m ago"
        return f"{m // 1440}d ago"


class MoneyFormatter(FormatterStrategy):

    def __init__(self, short: bool = False) -> None:
        """Initialize formatter.

        Args:
            short: If True, use compact format (e.g., $45K). If False, full format.
        """
        self.short = short

    def format(self, value: Any) -> str:
        if value is None:
            return "--"

        if isinstance(value, Decimal):
            return self._format_decimal(value)
        try:
            v = float(value)
        except (ValueError, TypeError):
            return "--"

        is_neg = v < 0
        av = abs(v)
        s = "-" if is_neg else ""

        if self.short:
            if av >= 1e6:
                return f"{s}${av / 1e6:.1f}M"
            if av >= 1e3:
                return f"{s}${av / 1e3:.0f}K"
            return f"{s}${av:.0f}"

        if av >= 1e6:
            return f"{s}${av / 1e6:.2f}M"
        if av >= 1e3:
            return f"{s}${av:,.0f}"
        return f"{s}${av:.2f}"

    def _format_decimal(self, value: Decimal) -> str:
        is_neg = value < 0
        av = abs(value)
        s = "-" if is_neg else ""

        if self.short:
            if av >= Decimal("1e6"):
                result = (av / Decimal("1e6")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                return f"{s}${result}M"
            if av >= Decimal("1e3"):
                result = (av / Decimal("1e3")).quantize(Decimal("0"), rounding=ROUND_HALF_UP)
                return f"{s}${result}K"
            result = av.quantize(Decimal("0"), rounding=ROUND_HALF_UP)
            return f"{s}${result}"

        if av >= Decimal("1e6"):
            result = (av / Decimal("1e6")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return f"{s}${result}M"
        if av >= Decimal("1e3"):
            result = av.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            return f"{s}${result:,}"
        result = av.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"{s}${result}"
