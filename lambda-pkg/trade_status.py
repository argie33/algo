#!/usr/bin/env python3
"""
Trade Status Enumeration

Single source of truth for all trade and position status values.
Prevents silent failures from hard-coded status string typos.
"""

from enum import Enum


class TradeStatus(Enum):
    """All possible trade execution statuses."""

    PENDING = 'pending'  # Trade created, not yet sent to Alpaca
    OPEN = 'open'        # Submitted to Alpaca, waiting for fill
    FILLED = 'filled'    # Order filled, position active
    PARTIAL = 'partially_filled'  # Some shares filled, rest pending
    ACTIVE = 'active'    # Alternate term for open position
    CANCELLED = 'cancelled'  # Order cancelled
    CLOSED = 'closed'    # Position fully exited
    ORPHANED = 'orphaned'  # Position exists in DB but not in Alpaca (error state)

    @classmethod
    def all_open(cls):
        """Returns tuple of statuses where position is still active."""
        return (cls.OPEN.value, cls.FILLED.value, cls.ACTIVE.value, cls.PARTIAL.value)

    @classmethod
    def all_closed(cls):
        """Returns tuple of statuses where position is done."""
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
            'pending': ['open', 'cancelled', 'orphaned'],
            'open': ['filled', 'partially_filled', 'cancelled', 'orphaned'],
            'partially_filled': ['filled', 'orphaned'],
            'filled': ['closed', 'orphaned'],
            'active': ['closed', 'orphaned'],
            'cancelled': ['orphaned'],
            'closed': [],  # Terminal
            'orphaned': [],  # Terminal
        }

        if from_status not in transitions:
            raise ValueError(f"Unknown from_status: {from_status}")

        legal = transitions[from_status]
        if to_status not in legal:
            return False
        return True


class PositionStatus(Enum):
    """All possible position statuses in algo_positions table."""

    OPEN = 'open'        # Position still active
    CLOSED = 'closed'    # Position fully exited
    PARTIAL = 'partial'  # Some shares exited, some still open
    PENDING_CLOSE = 'pending_close'  # Exit order submitted, awaiting fill
    ORPHANED = 'orphaned'  # Position in DB but not in Alpaca (error state)

    @classmethod
    def all_active(cls):
        """Returns tuple of statuses where position is still exposed."""
        return (cls.OPEN.value, cls.PARTIAL.value, cls.PENDING_CLOSE.value)

    @classmethod
    def is_active(cls, status: str) -> bool:
        """Check if position is still exposed to market movement."""
        return status in cls.all_active()


# Export for convenience
__all__ = ['TradeStatus', 'PositionStatus']
