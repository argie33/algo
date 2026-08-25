"""Formatter strategy classes for dashboard display.

Replaces if-elif chains with pluggable formatter strategies.
Each formatter handles a specific formatting task independently.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


class FormatterStrategy(ABC):
    """Base class for all formatter strategies."""

    @abstractmethod
    def format(self, value: Any) -> str:
        """Format a value according to strategy-specific rules."""


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
    """Converts percentage to market tier classification.

    BUG FOUND 2026-08-25 (goal session, exposure dashboard audit): TIER_MAP used to be its
    own hardcoded copy of the tier boundaries (80/60/40/0) that had drifted from the real
    EXPOSURE_TIERS in algo/risk/exposure_policy.py (70/45/25/0) - same "duplicate copy of a
    tuned constant drifts out of sync" bug class already fixed once for
    lambda/api/routes/algo_handlers/signals.py's _TIER_CONFIG (see that file's own
    2026-08-24 fix comment). The drift meant every panel using this formatter - the compact
    and expanded exposure score panels' header tier badge, plus the market panel's
    exposure-% bar color in 3 places (dashboard/panels/market.py's exp_bar callers) - showed
    the WRONG tier/color for exposure_pct in [70,80), [45,60), and [25,40), directly
    contradicting the correct tier name shown by the same panel's "Policy Tier:" row (which
    reads the real active_tier from the API). Now derives thresholds from EXPOSURE_TIERS
    directly so it can't drift again - single source of truth.
    """

    def format(self, percentage: Any) -> str:
        """Convert percentage to tier name."""
        if percentage is None:
            return "unknown"

        try:
            p = float(percentage)
        except (ValueError, TypeError):
            return "unknown"

        from algo.risk.exposure_policy import EXPOSURE_TIERS

        for tier in EXPOSURE_TIERS:
            if p >= tier["min_pct"]:
                return str(tier["name"])
        return "unknown"


class SignFormatter(FormatterStrategy):
    """Formats numeric value with sign prefix."""

    def format(self, value: Any) -> str:
        """Return '+' for non-negative, '' for negative."""
        try:
            v = float(value)
            return "+" if v >= 0 else "-"  # Always return explicit +/- sign, not empty
        except (ValueError, TypeError):
            return "--"  # Error case - explicit marker, not empty


class MarketHoursFormatter(FormatterStrategy):
    """Formats time remaining until market status change as countdown string."""

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
    """Formats timestamp as age string."""

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
            # BUG FIX 2026-08-17: naive timestamps here come from DB columns
            # (`timestamp without time zone`), and this DB's session timezone is UTC
            # (confirmed via SHOW timezone) - not Eastern. Assuming ET silently shifted
            # every age by the ET/UTC offset (4-5h) and could go negative when a
            # recent UTC timestamp got read as if it were that many hours in the
            # future ET (live-observed: a run 39min old rendered as "-202m ago").
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        else:
            return "--"

        try:
            m = int((datetime.now(timezone.utc) - ts).total_seconds() / 60)
        except (TypeError, ValueError):
            return "--"

        # Defensive floor: a still-negative value here means the source timestamp is
        # ahead of "now" (clock skew or bad upstream data), not that this formatter
        # should ever display a negative age.
        m = max(m, 0)

        if m < 60:
            return f"{m}m ago"
        if m < 1440:
            return f"{m // 60}h{m % 60:02d}m ago"
        return f"{m // 1440}d ago"


class MoneyFormatter(FormatterStrategy):
    """Formats decimal value as currency string."""

    def __init__(self, short: bool = False) -> None:
        """Initialize formatter.

        Args:
            short: If True, use compact format (e.g., $45K). If False, full format.
        """
        self.short = short

    def format(self, value: Any) -> str:
        """Format value as currency: $1.23, $12.34K, $1.23M."""
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
            if av >= 999_500:
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
        """Format Decimal type value."""
        is_neg = value < 0
        av = abs(value)
        s = "-" if is_neg else ""

        if self.short:
            if av >= Decimal("999500"):
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
