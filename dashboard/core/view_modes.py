"""Dashboard view modes and state management."""

from enum import Enum


class ViewMode(str, Enum):
    """Enumeration of dashboard view modes."""

    NORMAL = "normal"
    CIRCUIT = "circuit"
    EXPOSURE = "exposure"
    MARKET = "market"
    POSITIONS = "positions"
    SIGNALS = "signals"
    HEALTH = "health"
    SECTORS = "sectors"
    TRADES = "trades"
    ECONOMIC = "economic"
    PORTFOLIO = "portfolio"
    ERRORS = "errors"

    @classmethod
    def is_valid(cls, mode: str) -> bool:
        try:
            cls(mode)
            return True
        except ValueError:
            return False

    @classmethod
    def toggle(cls, current: str, target: str) -> str:
        """Toggle between current and target modes."""
        if current == target:
            return cls.NORMAL.value
        return target


class ViewModeState:
    """Thread-safe view mode state."""

    def __init__(self) -> None:
        self.current = ViewMode.NORMAL.value

    def set(self, mode: str) -> None:
        if ViewMode.is_valid(mode):
            self.current = mode

    def get(self) -> str:
        return self.current

    def toggle_to(self, target: str) -> str:
        """Toggle to target mode, returning new mode."""
        new_mode = ViewMode.toggle(self.current, target)
        self.current = new_mode
        return new_mode
