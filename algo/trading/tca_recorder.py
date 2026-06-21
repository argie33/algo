#!/usr/bin/env python3
"""TCA Recorder - Trade Cost Analysis recording and metrics."""

import logging
from decimal import Decimal
from typing import Any


logger = logging.getLogger(__name__)


class TCARecorder:
    """Records trade cost analysis metrics for execution quality tracking."""

    def __init__(self, config: Any) -> None:
        """Initialize TCA recorder."""
        self.config = config
        self.tca_records: list[dict[str, Any]] = []

    def record_entry_execution(
        self,
        symbol: str,
        entry_price: Decimal,
        reference_price: Decimal,
        slippage: Decimal,
        shares: int,
    ) -> None:
        """Record entry execution TCA metrics."""
        try:
            slippage_pct = float((slippage / reference_price * 100)) if reference_price else 0
            record = {
                "event": "entry",
                "symbol": symbol,
                "entry_price": float(entry_price),
                "reference_price": float(reference_price),
                "slippage": float(slippage),
                "slippage_pct": slippage_pct,
                "shares": shares,
            }
            self.tca_records.append(record)
            logger.info(f"[TCA_ENTRY] {symbol}: entry=${entry_price:.2f}, slippage={slippage_pct:+.2f}%, {shares}sh")
        except Exception as e:
            logger.warning(f"Failed to record entry TCA: {e}")

    def record_exit_execution(
        self,
        symbol: str,
        exit_price: Decimal,
        reference_price: Decimal,
        slippage: Decimal,
        shares: int,
        pnl: Decimal,
    ) -> None:
        """Record exit execution TCA metrics."""
        try:
            slippage_pct = float((slippage / reference_price * 100)) if reference_price else 0
            record = {
                "event": "exit",
                "symbol": symbol,
                "exit_price": float(exit_price),
                "reference_price": float(reference_price),
                "slippage": float(slippage),
                "slippage_pct": slippage_pct,
                "shares": shares,
                "pnl": float(pnl),
            }
            self.tca_records.append(record)
            logger.info(f"[TCA_EXIT] {symbol}: exit=${exit_price:.2f}, slippage={slippage_pct:+.2f}%, PnL=${pnl:.2f}")
        except Exception as e:
            logger.warning(f"Failed to record exit TCA: {e}")

    def get_tca_summary(self) -> dict[str, Any]:
        """Get TCA summary metrics."""
        if not self.tca_records:
            return {"total_records": 0, "avg_entry_slippage": 0, "avg_exit_slippage": 0}

        entries = [r for r in self.tca_records if r["event"] == "entry"]
        exits = [r for r in self.tca_records if r["event"] == "exit"]

        avg_entry_slippage = sum(r.get("slippage_pct", 0) for r in entries) / len(entries) if entries else 0
        avg_exit_slippage = sum(r.get("slippage_pct", 0) for r in exits) / len(exits) if exits else 0

        return {
            "total_records": len(self.tca_records),
            "total_entries": len(entries),
            "total_exits": len(exits),
            "avg_entry_slippage": avg_entry_slippage,
            "avg_exit_slippage": avg_exit_slippage,
        }

    def clear_records(self) -> None:
        """Clear TCA records (for testing)."""
        self.tca_records.clear()
