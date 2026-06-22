#!/usr/bin/env python3

"""Momentum and breakout signal methods — TD Sequential, power trend, pocket pivot, distribution."""

import logging
from typing import Any

import psycopg2

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class SignalMomentumMixin:
    """Momentum and breakout signals."""

    def _with_cursor(self, operation):
        """Execute an operation with a cursor via DatabaseContext."""
        try:
            with DatabaseContext("read") as cur:
                return operation(cur)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def td_sequential(self, symbol: str, eval_date) -> dict[str, Any]:
        def _fetch_data(cur):
            # M6: Compute count fresh from price data each time
            # Count inherently resets daily as it's based on bar-by-bar closes
            cur.execute(
                """
                SELECT date, high, low, close FROM price_daily
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 30
                """,
                (symbol, eval_date),
            )
            rows = cur.fetchall()
            if len(rows) < 14:
                return {
                    "setup_count": 0,
                    "setup_type": None,
                    "completed_9": False,
                    "perfected": False,
                }

            # Reverse to chronological order
            rows = list(reversed(rows))
            closes = []
            highs = []
            lows = []
            for r in rows:
                c = float(r[3])
                h = float(r[1])
                lo = float(r[2])
                if c is None or h is None or lo is None:
                    raise ValueError(f"Price data missing for {symbol}: close={c}, high={h}, low={lo}")
                closes.append(c)
                highs.append(h)
                lows.append(lo)
            dates = [r[0] for r in rows]

            # Walk forward, tracking sell-setup and buy-setup independently
            sell_count = 0
            buy_count = 0
            sell_count_history = []
            buy_count_history = []

            for i in range(4, len(closes)):
                # SELL setup: close > close 4 bars earlier
                if closes[i] > closes[i - 4]:
                    sell_count = sell_count + 1 if sell_count >= 1 else 1
                    buy_count = 0  # opposing setup resets
                elif closes[i] < closes[i - 4]:
                    buy_count = buy_count + 1 if buy_count >= 1 else 1
                    sell_count = 0
                else:
                    # Equal — both reset
                    sell_count = 0
                    buy_count = 0
                sell_count_history.append(sell_count)
                buy_count_history.append(buy_count)

            latest_sell = sell_count_history[-1] if sell_count_history else 0
            latest_buy = buy_count_history[-1] if buy_count_history else 0

            # Most recent count and type
            if latest_sell >= latest_buy:
                setup_count = latest_sell
                setup_type = "sell" if setup_count > 0 else None
            else:
                setup_count = latest_buy
                setup_type = "buy" if setup_count > 0 else None

            completed_9_today = setup_count == 9
            last_9_date = None
            for offset in range(min(5, len(sell_count_history))):
                idx = -1 - offset
                if sell_count_history[idx] == 9 or buy_count_history[idx] == 9:
                    last_9_date = dates[4 + len(sell_count_history) + idx]  # crude index calc
                    break

            # Perfected sell setup: bar 8 OR 9 high > bar 6 AND 7 high
            perfected = False
            if completed_9_today and len(highs) >= 9:
                if setup_type == "sell":
                    bar_8_high = highs[-2]
                    bar_9_high = highs[-1]
                    bar_6_high = highs[-4]
                    bar_7_high = highs[-3]
                    perfected = (bar_8_high > bar_6_high and bar_8_high > bar_7_high) or (
                        bar_9_high > bar_6_high and bar_9_high > bar_7_high
                    )
                else:  # buy
                    bar_8_low = lows[-2]
                    bar_9_low = lows[-1]
                    bar_6_low = lows[-4]
                    bar_7_low = lows[-3]
                    perfected = (bar_8_low < bar_6_low and bar_8_low < bar_7_low) or (
                        bar_9_low < bar_6_low and bar_9_low < bar_7_low
                    )

            combo_13_complete = False
            combo_count = 0
            if completed_9_today or last_9_date:
                # Find when the 9 fired
                ref_idx = None
                if completed_9_today:
                    ref_idx = len(closes) - 1
                else:
                    # find idx of most recent 9 within last 5 bars
                    for i in range(len(sell_count_history) - 1, -1, -1):
                        if sell_count_history[i] == 9 or buy_count_history[i] == 9:
                            ref_idx = 4 + i
                            break
                if ref_idx is not None and ref_idx + 2 < len(closes):
                    # Count bars since 9 that meet TD Combo countdown criteria
                    target_type = "sell" if (ref_idx < len(sell_count_history) + 4 and setup_type == "sell") else "buy"
                    for i in range(ref_idx, len(closes)):
                        if i < 2:
                            continue
                        if target_type == "sell":
                            if closes[i] > highs[i - 2]:
                                combo_count += 1
                        else:
                            if closes[i] < lows[i - 2]:
                                combo_count += 1
                        if combo_count >= 13:
                            combo_13_complete = True
                            break

            return {
                "setup_count": setup_count,
                "setup_type": setup_type,
                "completed_9": completed_9_today,
                "perfected": perfected,
                "last_9_date": str(last_9_date) if last_9_date else None,
                "combo_count": combo_count,
                "combo_13_complete": combo_13_complete,
            }

        return self._with_cursor(_fetch_data)  # type: ignore[no-any-return]

    def power_trend(self, symbol: str, eval_date) -> dict[str, Any]:
        """
        Minervini "Power Trend" indicator: 20%+ gain in 21 trading days.
        These are the strongest setups for stocks already in motion.
        """

        def _compute(cur):
            ret_21 = self._period_return(cur, symbol, eval_date, 21)  # type: ignore[attr-defined]
            return {
                "power_trend": ret_21 is not None and ret_21 >= 0.20,
                "return_21d": round(ret_21 * 100, 2) if ret_21 is not None else None,
            }

        return self._with_cursor(_compute)  # type: ignore[no-any-return]

    def pivot_breakout(self, symbol: str, eval_date) -> dict[str, Any]:
        """
        Livermore-style pivot point: price closing decisively above the highest
        high of the prior 20 trading days, on volume > 50d avg.
        """

        def _check_pivot(cur):
            cur.execute(
                """
                WITH d AS (
                    SELECT date, close, volume,
                           MAX(high) OVER (ORDER BY date ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING) AS pivot,
                           AVG(volume) OVER (ORDER BY date ROWS BETWEEN 50 PRECEDING AND 1 PRECEDING) AS avg_vol_50
                    FROM price_daily
                    WHERE symbol = %s AND date <= %s
                    ORDER BY date DESC LIMIT 1
                )
                SELECT close, pivot, volume, avg_vol_50 FROM d
                """,
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if not row or row[1] is None:
                return {"breakout": False}
            close = float(row[0])
            pivot = float(row[1])
            volume = float(row[2]) if row[2] else 0
            avg_vol = float(row[3]) if row[3] else 0
            breakout = close > pivot * 1.005
            on_volume = avg_vol > 0 and volume > avg_vol
            return {
                "breakout": breakout and on_volume,
                "close": close,
                "pivot": round(pivot, 2),
                "pct_above_pivot": (round((close - pivot) / pivot * 100, 2) if pivot > 0 else 0),
                "volume_ratio": round(volume / avg_vol, 2) if avg_vol > 0 else None,
            }

        try:
            return self._with_cursor(_check_pivot)  # type: ignore[no-any-return]
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.debug(f"Pivot breakout check failed: {e}")
            return {"breakout": False}

    def pocket_pivot(self, symbol: str, eval_date, lookback_days: int = 10) -> dict[str, Any]:
        """
        Pocket Pivot (re-accumulation signal): an up day where volume >= highest
        down-day volume in the prior lookback_days.

        Indicates institutional absorption of selling pressure and setup for breakout.
        """

        def _check_pocket(cur):
            cur.execute(
                """
                WITH daily AS (
                    SELECT date, close, volume,
                           LAG(close) OVER (ORDER BY date) AS prev_close,
                           ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                    FROM price_daily
                    WHERE symbol = %s AND date <= %s
                    ORDER BY date DESC LIMIT %s
                )
                SELECT
                    date, close, prev_close, volume, rn
                FROM daily
                ORDER BY date DESC
                """,
                (symbol, eval_date, lookback_days + 5),
            )
            rows = cur.fetchall()
            if not rows:
                return {"pocket_pivot": False}

            # Find max down-day volume in lookback window
            max_down_vol: float = 0
            for row in rows[1:]:  # Skip today initially
                _date, close, prev_close, vol, rn = row
                if prev_close is not None and close < prev_close:
                    max_down_vol = max(max_down_vol, float(vol) if vol else 0)

            if rows:
                _today_date, today_close, today_prev, today_vol, _today_rn = rows[0]
                today_vol = float(today_vol) if today_vol else 0
                today_prev = float(today_prev) if today_prev is not None else None
                today_close = float(today_close) if today_close else 0

                is_up_day = today_prev is not None and today_close > today_prev
                fires = is_up_day and today_vol >= max_down_vol and max_down_vol > 0

                if fires:
                    return {
                        "pocket_pivot": True,
                        "days_since_fired": 0,
                        "current_vol": round(today_vol, 0),
                        "max_down_vol": round(max_down_vol, 0),
                        "vol_ratio": (round(today_vol / max_down_vol, 2) if max_down_vol > 0 else 0),
                    }

            # Also check if pocket pivot fired 1-2 days ago (yesterday and day-2 only)
            up_day_dates = []
            for row in rows[1:3]:  # Skip today, check yesterday and day-2
                _date, close, prev_close, vol, rn = row
                vol = float(vol) if vol else 0
                prev_close = float(prev_close) if prev_close is not None else None
                close = float(close) if close else 0
                if prev_close is not None and close > prev_close and vol >= max_down_vol and max_down_vol > 0:
                    days_since = rn - 1  # rn=1 is most recent
                    up_day_dates.append((days_since, vol))

            if up_day_dates:
                days_since, vol = up_day_dates[0]
                return {
                    "pocket_pivot": True,
                    "days_since_fired": days_since,
                    "current_vol": round(vol, 0),
                    "max_down_vol": round(max_down_vol, 0),
                    "vol_ratio": (round(vol / max_down_vol, 2) if max_down_vol > 0 else 0),
                }

            return {"pocket_pivot": False}

        return self._with_cursor(_check_pocket)  # type: ignore[no-any-return]

    def distribution_days(self, symbol: str, eval_date, lookback: int = 25) -> int:
        """
        IBD-style distribution day count. A distribution day is when:
          - Close is down >= 0.2% from prior close
          - Volume is higher than the prior day's volume

        Returns count over lookback window (IBD standard: 25 trading days).
        Fails fast on database errors—distribution data is required for signal filtering.
        """

        def _count_dist(cur):
            cur.execute(
                """
                WITH d AS (
                    SELECT date, close, volume,
                           LAG(close) OVER (ORDER BY date) AS prev_close,
                           LAG(volume) OVER (ORDER BY date) AS prev_vol
                    FROM price_daily
                    WHERE symbol = %s AND date <= %s
                    ORDER BY date DESC LIMIT %s
                )
                SELECT COUNT(*) FROM d
                WHERE prev_close IS NOT NULL
                  AND close < prev_close * 0.998
                  AND volume > prev_vol
                """,
                (symbol, eval_date, lookback),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                raise ValueError(
                    f"CRITICAL: Cannot calculate distribution days for {symbol} — price data unavailable"
                )
            return int(row[0])

        return self._with_cursor(_count_dist)
