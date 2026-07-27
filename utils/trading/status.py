#!/usr/bin/env python3
"""
Trade Status Enumeration

Single source of truth for all trade and position status values.
Prevents silent failures from hard-coded status string typos.
"""

from enum import Enum


class TradeStatus(Enum):
    """All possible trade execution statuses."""

    PENDING = "pending"  # Trade created, not yet sent to Alpaca
    OPEN = "open"  # Submitted to Alpaca, waiting for fill
    FILLED = "filled"  # Order filled, position active
    PARTIAL = "partially_filled"  # Some shares filled, rest pending
    ACTIVE = "active"  # Alternate term for open position
    PAPER_PENDING = "paper_pending"  # Paper mode trade recorded while Alpaca was unreachable
    CANCELLED = "cancelled"  # Order cancelled
    CLOSED = "closed"  # Position fully exited
    ORPHANED = "orphaned"  # Position exists in DB but not in Alpaca (error state)

    @classmethod
    def all_open(cls) -> tuple[str, ...]:
        # CRITICAL: must cover every status a real order can be inserted with (see
        # algo/trading/executor_entry_handler.py's _record_entry_phase). This classmethod
        # already covered FILLED/PARTIAL/ACTIVE correctly - the real bug was that its
        # highest-stakes caller, exit_engine.py's core exit-candidate query, never called
        # this method at all and instead hand-rolled `TradeStatus.OPEN.value,
        # TradeStatus.PENDING.value` inline (missing FILLED/PARTIAL entirely). Added
        # PENDING/PAPER_PENDING here too so this tuple is the actual complete set once
        # callers are switched to use it instead of re-deriving their own subset.
        return (
            cls.OPEN.value,
            cls.FILLED.value,
            cls.PARTIAL.value,
            cls.ACTIVE.value,
            cls.PENDING.value,
            cls.PAPER_PENDING.value,
        )

    @classmethod
    def all_closed(cls) -> tuple[str, ...]:
        return (cls.CLOSED.value, cls.CANCELLED.value, cls.ORPHANED.value)

    @classmethod
    def validate_transition(cls, from_status: str, to_status: str) -> bool:
        """Validate that status transition is legal.

        Legal transitions:
        pending → open → filled/partial → closed
        open → cancelled (manual cancel)
        pending → cancelled (manual cancel before submission)
        partial → filled (remaining shares filled)
        * → orphaned (emergency state when DB/Alpaca diverge)
        """
        transitions = {
            "pending": ["open", "cancelled", "orphaned"],
            "open": ["filled", "partially_filled", "cancelled", "orphaned"],
            "partially_filled": ["filled", "orphaned"],
            "filled": ["closed", "orphaned"],
            "active": ["closed", "orphaned"],
            "cancelled": ["orphaned"],
            "closed": [],  # Terminal
            "orphaned": [],  # Terminal
        }

        if from_status not in transitions:
            raise ValueError(f"Unknown from_status: {from_status}")

        legal = transitions[from_status]
        if to_status not in legal:
            return False
        return True


class PositionStatus(Enum):
    """All possible position statuses in algo_positions table."""

    OPEN = "open"  # Position still active
    CLOSED = "closed"  # Position fully exited
    PARTIAL = "partial"  # Some shares exited, some still open
    PENDING_CLOSE = "pending_close"  # Exit order submitted, awaiting fill
    ORPHANED = "orphaned"  # Position in DB but not in Alpaca (error state)

    @classmethod
    def all_active(cls) -> tuple[str, ...]:
        return (cls.OPEN.value, cls.PARTIAL.value, cls.PENDING_CLOSE.value)

    @classmethod
    def is_active(cls, status: str) -> bool:
        return status in cls.all_active()


# Export for convenience
__all__ = ["PositionStatus", "TradeStatus"]
