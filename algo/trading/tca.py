"""
Transaction Cost Analysis (TCA) - Execution quality measurement.

Measures every fill against its signal price (arrival price) to quantify:
- Slippage per trade (signal_price vs executed_price)
- Fill rate (shares requested vs filled)
- Execution latency (order send to fill confirmation)
- Cumulative cost of execution friction

Alerts if slippage exceeds thresholds:
- 100 bps (1% adverse): WARN
- 300 bps (3% adverse): ERROR

This is what institutional traders use to validate their edge isn't eroded by fees/slippage.
"""

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from algo.infrastructure.config import AlgoConfig
from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class TCAEngine:
    """Transaction Cost Analysis for every trade execution."""

    def __init__(self, config: AlgoConfig | dict[str, Any]) -> None:
        self.config = config

    def record_fill(
        self,
        trade_id: int,
        symbol: str,
        signal_price: float,
        fill_price: float,
        shares_requested: int,
        shares_filled: int,
        side: str = "BUY",
        execution_latency_ms: int | None = None,
    ) -> dict[str, Any]:
        """Record a fill and compute slippage metrics.

        Args:
            trade_id: Foreign key to algo_trades
            symbol: Stock symbol
            signal_price: Entry price from signal (arrival price)
            fill_price: Actual executed price from Alpaca
            shares_requested: Target quantity
            shares_filled: Actual filled quantity
            side: BUY or SELL
            execution_latency_ms: Order send to fill confirmation time in ms

        Returns:
            dict with tca_id, slippage_bps, fill_rate, etc.
        """
        try:
            with DatabaseContext("write") as cur:
                # Compute slippage in basis points
                signal_price_dec = Decimal(str(signal_price))
                fill_price_dec = Decimal(str(fill_price))
                if side == "BUY":
                    # For buy, adverse if fill_price > signal_price
                    slippage_bps = (fill_price_dec - signal_price_dec) / signal_price_dec * Decimal(10000)
                else:
                    # For sell, adverse if fill_price < signal_price
                    slippage_bps = (signal_price_dec - fill_price_dec) / signal_price_dec * Decimal(10000)

                # Compute fill rate
                fill_rate_pct = (
                    (Decimal(shares_filled) / Decimal(shares_requested) * Decimal(100))
                    if shares_requested > 0
                    else Decimal(0)
                )

                # Insert into algo_tca table
                cur.execute(
                    """
                    INSERT INTO algo_tca (
                        trade_id, symbol, signal_date, signal_price, fill_price,
                        shares_requested, shares_filled, fill_rate_pct,
                        slippage_bps, side, execution_latency_ms
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING tca_id
                    """,
                    (
                        trade_id,
                        symbol,
                        date.today(),
                        signal_price,
                        fill_price,
                        shares_requested,
                        shares_filled,
                        fill_rate_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                        slippage_bps.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                        side,
                        execution_latency_ms,
                    ),
                )
                row = cur.fetchone()
                if row is None or row[0] is None:
                    raise RuntimeError("TCA insert failed: RETURNING tca_id returned no row")
                tca_id = row[0]

                result = {
                    "tca_id": tca_id,
                    "symbol": symbol,
                    "signal_price": signal_price,
                    "fill_price": fill_price,
                    "slippage_bps": float(slippage_bps.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                    "fill_rate_pct": float(fill_rate_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                    "execution_latency_ms": execution_latency_ms,
                }

                alert = self._check_slippage_alert(symbol, slippage_bps, side)
                if alert:
                    result["alert"] = alert

                return result
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"TCA: record_fill failed: {e}")
            raise

    def _check_slippage_alert(self, symbol: str, slippage_bps: Decimal | float, side: str) -> dict[str, Any] | None:
        # Only alert on adverse slippage (positive for buy)
        if side == "BUY" and slippage_bps <= 0:
            logger.debug(f"[TCA] {symbol} favorable slippage on BUY: {slippage_bps:.1f} bps")
            return None  # Favorable, no alert
        if side == "SELL" and slippage_bps <= 0:
            logger.debug(f"[TCA] {symbol} favorable slippage on SELL: {slippage_bps:.1f} bps")
            return None  # Favorable, no alert

        abs_slippage = abs(float(slippage_bps))

        if abs_slippage >= 300:  # 3% adverse
            return {
                "severity": "ERROR",
                "message": f"{symbol} excessive slippage: {abs_slippage:.0f} bps (3%+ adverse)",
                "slippage_bps": slippage_bps,
            }
        elif abs_slippage >= 100:  # 1% adverse
            return {
                "severity": "WARN",
                "message": f"{symbol} high slippage: {abs_slippage:.0f} bps (1%+ adverse)",
                "slippage_bps": slippage_bps,
            }

        logger.debug(f"[TCA] {symbol} slippage {abs_slippage:.1f} bps below threshold (no alert)")
        return None

    def daily_report(self, report_date: date | None = None) -> dict[str, Any]:
        """Generate daily TCA report.

        Args:
            report_date: Date to report on (default today)

        Returns:
            dict with daily metrics: avg slippage, worst fills, alert count, etc.
        """
        try:
            if not report_date:
                report_date = date.today()

            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as fill_count,
                        AVG(ABS(slippage_bps)) as avg_abs_slippage_bps,
                        MIN(slippage_bps) as best_slippage_bps,
                        MAX(slippage_bps) as worst_slippage_bps,
                        AVG(fill_rate_pct) as avg_fill_rate_pct,
                        AVG(execution_latency_ms) as avg_latency_ms
                    FROM algo_tca
                    WHERE signal_date = %s
                    """,
                    (report_date,),
                )
                row = cur.fetchone()

                if row is None or len(row) < 1:
                    return {
                        "report_date": report_date,
                        "fill_count": 0,
                        "status": "no_data",
                    }

                (
                    fill_count,
                    avg_abs_slippage,
                    best_slippage,
                    worst_slippage,
                    avg_fill_rate,
                    avg_latency,
                ) = row

                # Count adverse fills > 100 bps
                cur.execute(
                    """
                    SELECT COUNT(*) FROM algo_tca
                    WHERE signal_date = %s AND ABS(slippage_bps) > 100
                    """,
                    (report_date,),
                )
                row = cur.fetchone()
                if row is None or row[0] is None:
                    raise RuntimeError("High slippage count query failed: returned no row")
                high_slippage_count = row[0]

                cur.execute(
                    """
                    SELECT symbol, ABS(slippage_bps) FROM algo_tca
                    WHERE signal_date = %s
                    ORDER BY ABS(slippage_bps) DESC
                    LIMIT 1
                    """,
                    (report_date,),
                )
                worst_row = cur.fetchone()
                worst_symbol = worst_row[0] if worst_row else None

                if avg_abs_slippage is None:
                    raise RuntimeError(
                        f"[TCA CRITICAL] Average absolute slippage is NULL for {report_date}. "
                        f"Cannot compute TCA metrics without valid execution data."
                    )
                if best_slippage is None:
                    raise RuntimeError(
                        f"[TCA CRITICAL] Best slippage is NULL for {report_date}. "
                        f"Cannot compute TCA metrics without valid execution data."
                    )
                if worst_slippage is None:
                    raise RuntimeError(
                        f"[TCA CRITICAL] Worst slippage is NULL for {report_date}. "
                        f"Cannot compute TCA metrics without valid execution data."
                    )
                if avg_fill_rate is None:
                    raise RuntimeError(
                        f"[TCA CRITICAL] Average fill rate is NULL for {report_date}. "
                        f"Cannot compute TCA metrics without valid execution data."
                    )
                if avg_latency is None:
                    raise RuntimeError(
                        f"[TCA CRITICAL] Average latency is NULL for {report_date}. "
                        f"Cannot compute TCA metrics without valid execution data."
                    )
                avg_abs_slippage_dec = Decimal(str(avg_abs_slippage))
                best_slippage_dec = Decimal(str(best_slippage))
                worst_slippage_dec = Decimal(str(worst_slippage))
                avg_fill_rate_dec = Decimal(str(avg_fill_rate))
                avg_latency_dec = Decimal(str(avg_latency))

                return {
                    "report_date": report_date,
                    "fill_count": fill_count,
                    "avg_abs_slippage_bps": float(
                        avg_abs_slippage_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    ),
                    "best_slippage_bps": float(best_slippage_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                    "worst_slippage_bps": float(worst_slippage_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                    "worst_symbol": worst_symbol,
                    "high_slippage_fills": high_slippage_count,
                    "high_slippage_pct": float(
                        (Decimal(high_slippage_count) / Decimal(fill_count) * Decimal(100)).quantize(
                            Decimal("0.1"), rounding=ROUND_HALF_UP
                        )
                    ),
                    "avg_fill_rate_pct": float(avg_fill_rate_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                    "avg_execution_latency_ms": int(avg_latency_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
                    "status": "ok" if high_slippage_count == 0 else "warning",
                }
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.critical(f"[TCA_AUDIT] daily_report FAILED: {e}")
            raise RuntimeError(
                f"TCA daily report generation failed (audit trail interrupted): {e}. "
                "This is critical — all fills must be audited. Check database connectivity and data integrity."
            ) from e

    def monthly_summary(self, year: int, month: int) -> dict[str, Any]:
        """Generate monthly TCA summary.

        Args:
            year: Year (e.g., 2026)
            month: Month (1-12)

        Returns:
            Monthly aggregated metrics
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as fill_count,
                        AVG(ABS(slippage_bps)) as avg_abs_slippage_bps,
                        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ABS(slippage_bps))
                            as p95_abs_slippage_bps,
                        MAX(ABS(slippage_bps)) as worst_slippage_bps,
                        AVG(fill_rate_pct) as avg_fill_rate_pct,
                        SUM(CASE WHEN ABS(slippage_bps) > 100 THEN 1 ELSE 0 END)
                            as high_slippage_count
                    FROM algo_tca
                    WHERE EXTRACT(YEAR FROM signal_date) = %s
                      AND EXTRACT(MONTH FROM signal_date) = %s
                    """,
                    (year, month),
                )
                row = cur.fetchone()

                if row is None or len(row) < 1:
                    return {
                        "period": f"{year}-{month:02d}",
                        "status": "no_data",
                    }

                (
                    fill_count,
                    avg_abs_slippage,
                    p95_slippage,
                    worst_slippage,
                    avg_fill_rate,
                    high_slippage_count,
                ) = row

                avg_abs_slippage_dec = Decimal(str(avg_abs_slippage)) if avg_abs_slippage else Decimal(0)
                p95_slippage_dec = Decimal(str(p95_slippage)) if p95_slippage else Decimal(0)
                worst_slippage_dec = Decimal(str(worst_slippage)) if worst_slippage else Decimal(0)
                avg_fill_rate_dec = Decimal(str(avg_fill_rate)) if avg_fill_rate else Decimal(0)

                return {
                    "period": f"{year}-{month:02d}",
                    "fill_count": fill_count,
                    "avg_abs_slippage_bps": float(
                        avg_abs_slippage_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    ),
                    "p95_abs_slippage_bps": float(p95_slippage_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                    "worst_slippage_bps": float(worst_slippage_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                    "avg_fill_rate_pct": float(avg_fill_rate_dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                    "high_slippage_fills": high_slippage_count,
                    "high_slippage_pct": float(
                        (Decimal(high_slippage_count) / Decimal(fill_count) * Decimal(100)).quantize(
                            Decimal("0.1"), rounding=ROUND_HALF_UP
                        )
                    ),
                    "status": "ok" if high_slippage_count == 0 else "warning",
                }
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.critical(f"[TCA_AUDIT] monthly_summary FAILED: {e}")
            raise RuntimeError(
                f"TCA monthly summary generation failed (audit trail interrupted): {e}. "
                "This is critical — all fills must be audited. Check database connectivity and data integrity."
            ) from e
