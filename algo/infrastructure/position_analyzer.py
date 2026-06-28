"""Position Analysis - compute P&L, breakdowns, and position metrics.

Extracted from reconciliation to separate concerns: data fetching vs. analysis.
"""

import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


class PositionAnalyzer:
    """Analyze open positions and compute P&L metrics."""

    @staticmethod
    def analyze_positions(
        positions: list[tuple[Any, ...]],
    ) -> dict[str, Any]:
        """Analyze open positions and compute P&L breakdown.

        Args:
            positions: list of (symbol, qty, entry_price, current_price, position_value)

        Returns: {
            'total_position_value': Decimal,
            'unrealized_pnl': Decimal,
            'unrealized_pnl_pct': float,
            'positions_with_prices': int,
            'winning_count': int,
            'losing_count': int,
            'breakeven_count': int,
            'position_details': list of analyzed positions
        }
        """
        total_position_value = Decimal(0)
        unrealized_pnl = Decimal(0)
        positions_with_prices = 0
        winning_count = 0
        losing_count = 0
        breakeven_count = 0
        position_details = []

        for symbol, qty, entry, current, pos_value in positions:
            # Validate critical fields - fail fast on missing data
            if entry is None:
                raise ValueError(f"[POSITION ANALYSIS] {symbol}: ENTRY PRICE MISSING - cannot compute P&L")
            if current is None:
                entry_dec = Decimal(str(entry))
                qty_dec = Decimal(str(qty)) if qty is not None else Decimal(0)
                raise ValueError(
                    f"[POSITION ANALYSIS] {symbol}: {qty_dec:.0f} @ ${entry_dec:.2f} -> CURRENT PRICE MISSING"
                )
            if qty is None or pos_value is None:
                raise ValueError(f"[POSITION ANALYSIS] {symbol}: QUANTITY OR VALUE MISSING")

            # Keep all calculations in Decimal for precision
            entry_dec = Decimal(str(entry))
            current_dec = Decimal(str(current))
            qty_dec = Decimal(str(qty))
            pos_value_dec = Decimal(str(pos_value))

            pnl_dec = (current_dec - entry_dec) * qty_dec
            pnl_pct_dec = ((current_dec - entry_dec) / entry_dec * Decimal(100)) if entry_dec > 0 else Decimal(0)

            total_position_value += pos_value_dec
            unrealized_pnl += pnl_dec
            positions_with_prices += 1

            # Track winning/losing/breakeven status
            if pnl_dec > 0:
                winning_count += 1
            elif pnl_dec < 0:
                losing_count += 1
            else:
                breakeven_count += 1

            position_details.append(
                {
                    "symbol": symbol,
                    "quantity": float(qty_dec),
                    "entry_price": float(entry_dec),
                    "current_price": float(current_dec),
                    "position_value": float(pos_value_dec),
                    "unrealized_pnl": float(pnl_dec),
                    "unrealized_pnl_pct": float(pnl_pct_dec),
                }
            )

        # Compute total unrealized P&L percentage
        if total_position_value <= 0:
            unrealized_pnl_pct = None
        else:
            unrealized_pnl_pct = float(unrealized_pnl / total_position_value * Decimal(100))

        return {
            "total_position_value": total_position_value,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "positions_with_prices": positions_with_prices,
            "winning_count": winning_count,
            "losing_count": losing_count,
            "breakeven_count": breakeven_count,
            "position_details": position_details,
        }

    @staticmethod
    def log_position_analysis(analysis: dict[str, Any], logger_obj: Any = None) -> None:
        """Log position analysis results in standardized format."""
        if logger_obj is None:
            logger_obj = logger

        if "position_details" not in analysis:
            raise ValueError(
                "Position analysis missing required 'position_details' key. "
                "Verify PositionAnalyzer.analyze_positions() returned valid analysis result."
            )
        details = analysis["position_details"]
        logger_obj.info(f"\n2. Database Positions: {len(details)} open")

        for pos in details:
            logger_obj.info(
                f"   {pos['symbol']}: {pos['quantity']:.0f} @ ${pos['entry_price']:.2f} "
                f"-> ${pos['current_price']:.2f} | "
                f"{pos['unrealized_pnl']:+,.2f} ({pos['unrealized_pnl_pct']:+.2f}%)"
            )

        logger_obj.info(f"\n   Total Position Value: ${float(analysis['total_position_value']):,.2f}")
        logger_obj.info(
            f"   Unrealized P&L: {float(analysis['unrealized_pnl']):+,.2f} ({analysis['unrealized_pnl_pct']:+.2f}%)"
        )
        logger_obj.info(
            f"   Position Breakdown: {analysis['winning_count']} winning, "
            f"{analysis['losing_count']} losing, {analysis['breakeven_count']} breakeven"
        )
