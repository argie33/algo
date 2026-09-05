"""Current-price/technicals fetching and trailing-stop computation methods for
PositionMonitor, extracted from algo/monitoring/position_monitor.py (2026-09-05, file-size
ratchet: that file is a Tier-2 bloater flagged for decomposition, same pattern already used
for `algo/monitoring/position_corporate_actions.py`'s CorporateActionsMixin). Bodies are
verbatim, no logic changed - mixed into PositionMonitor, which still defines the `config`
instance attribute these methods read via `self`.

`DatabaseContext` is accessed via the position_monitor module object at call time (not
imported by name here) because existing tests patch
`algo.monitoring.position_monitor.DatabaseContext` expecting that to affect these methods -
a plain import here would silently stop seeing those patches (same reasoning as
position_corporate_actions.py / position_order_management.py). `algo.monitoring.
position_monitor` itself imports this module at load time, so the reference is resolved
lazily (inside the method bodies, not at import time) to avoid a circular-import failure.
"""

from __future__ import annotations

import logging
import math
from datetime import date as _date
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

import algo.monitoring.position_monitor as _pm
from algo.monitoring.position_monitor import PositionValidationError
from algo.trading.exceptions import ExchangeAPIError
from algo.trading.quote_fetcher import fetch_live_quote

logger = logging.getLogger(__name__)


class PositionMarketDataMixin:
    """Current-price/technical-indicator fetching and trailing-stop computation methods for
    PositionMonitor. Not usable standalone - relies on the `config` instance attribute
    defined on PositionMonitor itself.
    """

    config: Any

    def _fetch_current_market(
        self, symbol: str, current_date: _date | datetime, cur: PsycopgCursor[Any] | None = None
    ) -> tuple[float, float | None, float | None, float | None]:
        """Fetch current price and technical indicators for a symbol.

        Args:
            symbol: Stock symbol
            current_date: Date to fetch data for
            cur: Optional cursor to use. If None, opens new DatabaseContext.
                 CRITICAL: If caller has an open DatabaseContext, MUST pass cursor
                 to avoid nested context closing the outer cursor (causes "cursor already closed" errors).

        Raises:
            ValueError: If price data is missing - price_daily is required,
                       technical_data_daily may be None (handled by caller)

        Price source: tries a live Alpaca quote first (real-time, matches exit_engine.py's
        stop/target evaluation), falling back to price_daily's close if unavailable.
        2026-08-03: price_daily is written once near market open and never refreshed
        intraday (confirmed live: KARO/NBIX rows both had created_at == updated_at ==
        08:32 all day) - without the live quote, health-flag EARLY_EXIT decisions,
        unrealized P&L, and r_multiple were computed off a price that could be stale by
        an entire trading day, and same-day entries evaluated within the same session
        recorded exit_price identically equal to entry_price (both drawn from the same
        un-refreshed row) - a fabricated $0.00 P&L for what should have been a priced exit.
        """
        live_price = self._fetch_live_quote_or_none(symbol)
        if live_price is not None:
            atr, sma_50, sma_200 = self._fetch_technicals(symbol, current_date, cur=cur)
            if atr is None or sma_50 is None:
                # CRITICAL FIX 2026-08-06: Use conservative fallback instead of failing
                if atr is None:
                    atr = abs(live_price * 0.02) if live_price else 0.5
                    logger.warning(f"[POSITION_MONITOR] {symbol}: ATR missing (live quote), using fallback: ${atr:.2f}")
                if sma_50 is None:
                    sma_50 = live_price if live_price else 100.0
                    logger.warning(
                        f"[POSITION_MONITOR] {symbol}: SMA_50 missing (live quote), using fallback: ${sma_50:.2f}"
                    )
            return (live_price, atr, sma_50, sma_200)

        if cur is not None:
            try:
                cur.execute(
                    """
                    SELECT pd.close, td.atr, td.sma_50, td.sma_200
                    FROM price_daily pd
                    LEFT JOIN technical_data_daily td ON pd.symbol = td.symbol AND pd.date = td.date
                    WHERE pd.symbol = %s AND pd.date <= %s
                    ORDER BY pd.date DESC LIMIT 1
                    """,
                    (symbol, current_date),
                )
                row = cur.fetchone()
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise ValueError(f"Database error fetching price data for {symbol}: {e}") from e
        else:
            with _pm.DatabaseContext("read") as fresh_cur:  # type: ignore[attr-defined]
                fresh_cur.execute(
                    """
                    SELECT pd.close, td.atr, td.sma_50, td.sma_200
                    FROM price_daily pd
                    LEFT JOIN technical_data_daily td ON pd.symbol = td.symbol AND pd.date = td.date
                    WHERE pd.symbol = %s AND pd.date <= %s
                    ORDER BY pd.date DESC LIMIT 1
                    """,
                    (symbol, current_date),
                )
                row = fresh_cur.fetchone()

        if row is None:
            raise ValueError(f"Price data missing for {symbol} on {current_date} or earlier - no price_daily entry")

        close_price = float(row[0]) if row[0] is not None else None
        if close_price is None:
            raise ValueError(f"Invalid price for {symbol} on {current_date} - close price is NULL")

        atr = float(row[1]) if row[1] is not None else None
        sma_50 = float(row[2]) if row[2] is not None else None
        sma_200 = float(row[3]) if row[3] is not None else None

        # CRITICAL: Trailing stop calculations REQUIRE both ATR and SMA_50
        # ATR provides volatility-based placement; SMA_50 provides trend context
        # Both are REQUIRED for proper risk management-cannot silently degrade
        if atr is None or sma_50 is None:
            # CRITICAL FIX 2026-08-06: Use conservative fallback values for missing technicals
            # instead of failing position validation. Missing ATR/SMA_50 should not halt monitoring.
            # Use conservative defaults: ATR defaults to 2% of price, SMA_50 defaults to current_price
            if atr is None:
                atr = abs(close_price * 0.02) if close_price else 0.5
                logger.warning(
                    f"[POSITION_MONITOR] {symbol}: ATR missing on {current_date}, using fallback: ${atr:.2f}. "
                    f"Check load_technical_data_daily logs."
                )
            if sma_50 is None:
                sma_50 = close_price if close_price else 100.0
                logger.warning(
                    f"[POSITION_MONITOR] {symbol}: SMA_50 missing on {current_date}, using fallback: ${sma_50:.2f}. "
                    f"Check load_technical_data_daily logs."
                )

        return (close_price, atr, sma_50, sma_200)

    def _fetch_live_quote_or_none(self, symbol: str) -> float | None:
        """Best-effort live Alpaca quote; None on any unavailability or error.

        Health-flag monitoring is a recommendation pass, not a broker-execution path
        (unlike exit_engine.py's stop/target checks, which halt in auto mode on a
        quote failure) - so any failure here (auth, network, symbol not found, or an
        explicit data_unavailable marker) falls back to the existing price_daily-based
        path rather than aborting review for this position.
        """
        execution_mode = self.config.get("execution_mode", "paper")
        try:
            quote = fetch_live_quote(symbol, execution_mode, log_prefix="POSITION_MONITOR")
        except (RuntimeError, ValueError, ExchangeAPIError) as e:
            logger.debug(f"[POSITION_MONITOR] {symbol}: live quote unavailable ({e}), falling back to price_daily")
            return None
        if isinstance(quote, (int, float)) and not isinstance(quote, bool):
            return float(quote)
        return None

    def _fetch_technicals(
        self, symbol: str, current_date: _date | datetime, cur: PsycopgCursor[Any] | None = None
    ) -> tuple[float | None, float | None, float | None]:
        """Fetch (atr, sma_50, sma_200) from the most recent technical_data_daily row on/before current_date."""
        query = """
            SELECT atr, sma_50, sma_200 FROM technical_data_daily
            WHERE symbol = %s AND date <= %s
            ORDER BY date DESC LIMIT 1
            """
        try:
            if cur is not None:
                cur.execute(query, (symbol, current_date))
                row = cur.fetchone()
            else:
                with _pm.DatabaseContext("read") as fresh_cur:  # type: ignore[attr-defined]
                    fresh_cur.execute(query, (symbol, current_date))
                    row = fresh_cur.fetchone()
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise ValueError(f"Database error fetching technical data for {symbol}: {e}") from e

        if row is None:
            return (None, None, None)
        atr = float(row[0]) if row[0] is not None else None
        sma_50 = float(row[1]) if row[1] is not None else None
        sma_200 = float(row[2]) if row[2] is not None else None
        return (atr, sma_50, sma_200)

    def _compute_trailing_stop(
        self,
        entry_price: float,
        active_stop: float,
        cur_price: float,
        atr: float | None,
        sma_50: float | None,
        target_hits: int,
    ) -> float:
        """Stop ratchets up only.

        - Before T1: keep initial stop OR use 50-DMA (whichever higher) capped at entry-2*ATR
        - After T1: stop = entry (breakeven) at minimum, or trail tighter via ATR
        - After T2: stop = entry area, never target levels (targets are exits, not protection)
        """
        # Validate inputs
        # BUG FOUND 2026-08-10 (NaN-comparison-guard class): `<= 0` never catches NaN - this
        # gate controls the actual trailing-stop price written to the DB for a real position.
        if cur_price is None or math.isnan(cur_price) or math.isinf(cur_price) or cur_price <= 0:
            raise PositionValidationError(f"Invalid current price for trailing stop: {cur_price}")
        if active_stop is None or math.isnan(active_stop) or math.isinf(active_stop) or active_stop <= 0:
            raise PositionValidationError(f"Invalid active stop for trailing stop: {active_stop}")
        if entry_price is None or math.isnan(entry_price) or math.isinf(entry_price) or entry_price <= 0:
            raise PositionValidationError(f"Invalid entry price for trailing stop: {entry_price}")

        # Sanity check: if active_stop is already > cur_price (shouldn't happen), clamp it.
        # This can occur with stale/imported positions. Use Decimal for precision.
        if active_stop > cur_price:
            active_stop = float(Decimal(str(cur_price)) - Decimal("0.01"))
            logger.warning(f"  Clamped active_stop {active_stop:.2f} (was above market)")

        candidates = [active_stop]

        # Use Decimal for precise arithmetic on stop calculations
        if atr is not None and atr > 0:
            atr_dec = Decimal(str(atr))
            candidates.append(float(Decimal(str(cur_price)) - (Decimal("2.0") * atr_dec)))
        if sma_50 is not None and sma_50 > 0 and sma_50 < cur_price:
            candidates.append(sma_50)

        if target_hits >= 1:
            candidates.append(entry_price)  # at least breakeven after T1
        # NOTE: target_hits >= 2 does NOT add T1 price. Target prices are exits, not stops.

        # Don't let trailing stop get within 1.0 ATR of price (room to breathe)
        if atr is not None and atr > 0:
            atr_dec = Decimal(str(atr))
            cap = float(Decimal(str(cur_price)) - atr_dec)
            candidates = [c for c in candidates if c <= cap]
            if not candidates:
                # CRITICAL FIX (Session 55): If cap is <= 0 due to very large ATR,
                # don't use it as stop-loss (would allow unlimited downside).
                # Instead, clamp to minimum of 1 cent above zero or entry_price * 0.5
                if cap > 0:
                    candidates = [cap]
                else:
                    min_stop = max(0.01, entry_price * 0.5)
                    candidates = [min_stop]
                    logger.warning(
                        f"  ATR too large: cap={cap:.2f} <= 0. Clamping stop to min={min_stop:.2f} "
                        f"(50% of entry ${entry_price:.2f}) to prevent unlimited downside."
                    )

        # BUG FOUND 2026-08-23 (goal session: real-money-readiness position-monitor audit):
        # the "room to breathe" cap above only ran `if atr is not None and atr > 0` - the ONLY
        # thing keeping every candidate <= cur_price. Outside that block (ATR temporarily
        # unavailable - a real, reachable data gap, not hypothetical), `entry_price` is added
        # to `candidates` unconditionally whenever target_hits >= 1 with no upper bound at all.
        # If price later pulls back below entry after hitting T1 (a real, plausible sequence -
        # spike to target, then retrace), `entry_price > cur_price` and `new_stop`/`final_stop`
        # could land ABOVE the current market price - a live stop-sell order with a trigger
        # above market executes essentially immediately upon submission. The caller
        # (review_positions -> _evaluate_position) already has a defensive
        # `if proposed_stop > cur_price: clamp` catch for exactly this - confirmed this is a
        # real, previously-encountered condition (not purely theoretical), not just a
        # theoretical gap - but per the same "don't rely on accidental caller-side correctness"
        # principle already applied to the max_position_size_pct fix in position_sizer.py, this
        # function's own contract ("stop ratchets up only... capped at entry-2*ATR") should hold
        # unconditionally, not just when ATR happens to be available. Filter unconditionally so
        # every candidate this function ever returns already respects "at least a cent of room
        # below current price" - the caller's clamp becomes pure defense-in-depth, not the only
        # thing preventing an above-market stop from reaching the broker.
        candidates = [c for c in candidates if c < cur_price]
        if not candidates:
            candidates = [float(Decimal(str(cur_price)) - Decimal("0.01"))]

        # For a stop loss, pick the highest valid candidate (most conservative protection).
        # This ratchets stops UP as price rises, but never above current price - ATR.
        new_stop = max(candidates) if candidates else active_stop
        # NEVER lower the trailing stop below its prior level
        # Decimal quantize at the final step, not round(): same bug class already fixed
        # 2026-07-21 elsewhere in this file (_apply_split_adjustment) and in order_manager.py/
        # exposure_policy.py/buy_signal_generator.py - candidates above involve real float
        # arithmetic (cur_price - 2*atr, cur_price - atr), and this trailing-stop value is a
        # real stop-loss protecting a live position.
        final_stop = max(new_stop, active_stop)
        return float(Decimal(str(final_stop)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
