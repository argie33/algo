#!/usr/bin/env python3

"""Pattern-based signal methods — base detection, VCP, 3WT, HTF."""

import logging
from typing import Any

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class SignalPatternsMixin:
    """Chart pattern detection signals."""

    # Pattern detection thresholds (extracted from hardcoded values)
    BASE_MIN_DEPTH_PCT = 8.0
    BASE_MAX_DEPTH_PCT = 35.0
    BASE_MIN_BARS = 10
    BASE_MIN_HISTORY = 20
    VCP_MIN_BARS = 30
    VCP_MIN_CONTRACTIONS = 2
    VCP_MIN_DEPTHS = 3
    VCP_TIGHT_PATTERN_PCT = 5.0
    VCP_CONTRACTION_FACTOR = 0.7  # Depth must be <= 70% of previous
    LOOKBACK_DAYS_DEFAULT = 60
    LOOKBACK_BARS_SHORT = 25

    def _with_cursor(self, operation: Any) -> Any:
        """Execute an operation with a cursor via DatabaseContext."""
        try:
            with DatabaseContext("read") as cur:
                return operation(cur)
        except (ValueError, TypeError, IndexError, RuntimeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _get_signal_pattern_thresholds(self) -> dict[str, int]:
        """Load signal pattern date thresholds from config."""
        thresholds = {
            "signal_patterns_signal_age_days": 7,
            "signal_patterns_intermediate_lookback_days": 10,
            "signal_patterns_extended_lookback_days": 14,
            "signal_patterns_medium_lookback_days": 20,
            "signal_patterns_longer_lookback_days": 35,
            "signal_patterns_60d_lookback_days": 60,
        }
        try:
            with DatabaseContext("read") as cur:
                # SEC-001 FIX: Use parameterized query to prevent SQL injection
                keys_list = list(thresholds.keys())
                placeholders = ", ".join(["%s"] * len(keys_list))
                query = f"SELECT key, value FROM algo_config WHERE key IN ({placeholders})"
                cur.execute(query, keys_list)
                for k, v in cur.fetchall():
                    thresholds[k] = int(v)
        except (ValueError, TypeError, KeyError, RuntimeError) as e:
            logger.debug(f"Could not load signal pattern thresholds: {e} — using defaults")
        return thresholds

    def base_detection(self, symbol: str, eval_date: Any) -> dict[str, Any]:
        def _fetch_and_analyze(cur):
            cur.execute(
                """
                SELECT date, high, low, close, volume FROM price_daily
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 60
                """,
                (symbol, eval_date),
            )
            rows = cur.fetchall()
            if len(rows) < self.BASE_MIN_HISTORY:
                return {"in_base": False, "reason": "Insufficient history"}

            highs = [float(r[1]) for r in rows]
            lows = [float(r[2]) for r in rows]
            closes = [float(r[3]) for r in rows]
            volumes = [float(r[4]) for r in rows]

            peak_val = max(highs)
            peak_idx = min(i for i, h in enumerate(highs) if h == peak_val)
            base_highs = highs[: peak_idx + 1]
            base_lows = lows[: peak_idx + 1]
            base_vols = volumes[: peak_idx + 1]

            if len(base_highs) < self.BASE_MIN_BARS:
                return {
                    "in_base": False,
                    "reason": f"Base too short ({len(base_highs)} bars)",
                }

            base_high = max(base_highs)
            base_low = min(base_lows)
            base_depth = ((base_high - base_low) / base_high * 100.0) if base_high > 0 else 0
            weeks_in_base = len(base_highs) // 5

            cur_price = closes[0]
            in_base = (self.BASE_MIN_DEPTH_PCT <= base_depth <= self.BASE_MAX_DEPTH_PCT) and len(
                base_highs
            ) >= self.BASE_MIN_HISTORY

            pct_to_pivot = ((base_high - cur_price) / base_high * 100.0) if base_high > 0 else 100
            breakout_imminent = in_base and pct_to_pivot <= 2.0

            recent_vol = (
                sum(base_vols[: self.LOOKBACK_BARS_SHORT]) / self.LOOKBACK_BARS_SHORT
                if len(base_vols) >= self.LOOKBACK_BARS_SHORT
                else 0
            )
            prior_vol = sum(volumes[20:50]) / 30 if len(volumes) >= 50 else recent_vol
            volume_dryup = prior_vol > 0 and recent_vol < prior_vol * 0.8

            return {
                "in_base": in_base,
                "base_depth_pct": round(base_depth, 1),
                "weeks_in_base": weeks_in_base,
                "pivot_high": round(base_high, 2),
                "pct_to_pivot": round(pct_to_pivot, 2),
                "breakout_imminent": breakout_imminent,
                "volume_dryup": volume_dryup,
            }

        try:
            return self._with_cursor(_fetch_and_analyze)  # type: ignore[no-any-return]
        except (ValueError, TypeError, IndexError) as e:
            logger.debug(f"Base detection error for {symbol}: {e}")
            return {"in_base": False, "reason": f"Calculation error: {str(e)[:50]}"}
        except (RuntimeError, AttributeError, KeyError) as e:
            logger.error(f"Unexpected error in base_detection({symbol}): {e}")
            return {"in_base": False, "reason": "Unexpected error"}

    def vcp_detection(self, symbol: str, eval_date) -> dict[str, Any]:
        """
        Volatility Contraction Pattern (Minervini's signature setup).

        Look for 2-4 successive consolidations within the last 30-60 bars where
        each subsequent base has SMALLER depth (volatility contracting) and
        LOWER volume.

        Returns: {
          'is_vcp': bool,
          'contractions': int,
          'depth_progression': [pct, pct, ...],
          'tight_pattern': bool   # last contraction <= 5% deep
        }
        """

        def _analyze_vcp(cur):
            cur.execute(
                """
                SELECT date, high, low, close FROM price_daily
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 60
                """,
                (symbol, eval_date),
            )
            rows = cur.fetchall()
            if len(rows) < self.VCP_MIN_BARS:
                return {"is_vcp": False, "reason": "Insufficient bars"}

            rows = list(reversed(rows))
            highs = [float(r[1]) for r in rows]
            lows = [float(r[2]) for r in rows]

            peaks = []
            for i in range(5, len(highs) - 5):
                if highs[i] == max(highs[i - 5 : i + 6]):
                    peaks.append(i)
            if len(peaks) < 2:
                return {"is_vcp": False, "contractions": 0}

            depths = []
            for j in range(len(peaks) - 1):
                p1, p2 = peaks[j], peaks[j + 1]
                window_low = min(lows[p1 : p2 + 1])
                depth = ((highs[p1] - window_low) / highs[p1] * 100.0) if highs[p1] > 0 else 0
                depths.append(round(depth, 1))

            contractions = 0
            for i in range(1, len(depths)):
                if depths[i] <= depths[i - 1] * self.VCP_CONTRACTION_FACTOR:
                    contractions += 1
            is_vcp = contractions >= self.VCP_MIN_CONTRACTIONS and len(depths) >= self.VCP_MIN_DEPTHS
            tight_pattern = depths[-1] <= self.VCP_TIGHT_PATTERN_PCT if depths else False

            return {
                "is_vcp": is_vcp,
                "contractions": contractions,
                "depth_progression": depths,
                "tight_pattern": tight_pattern,
            }

        return self._with_cursor(_analyze_vcp)  # type: ignore[no-any-return]

    def classify_base_type(self, symbol: str, eval_date) -> dict[str, Any]:
        """
        Classify the current base into canonical chart pattern types.
        """
        base_info = self.base_detection(symbol, eval_date)
        if not base_info.get("in_base"):
            return {
                "type": "no_base",
                "quality": "D",
                "characteristics": base_info,
            }

        def _classify_with_cursor(cur):
            cur.execute(
                """
                SELECT date, high, low, close, volume FROM price_daily
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 60
                """,
                (symbol, eval_date),
            )
            rows = list(reversed(cur.fetchall()))
            if len(rows) < 20:
                return {"type": "no_base", "quality": "D"}

            highs = [float(r[1]) for r in rows]
            lows = [float(r[2]) for r in rows]
            closes = [float(r[3]) for r in rows]

            depth = base_info["base_depth_pct"]
            duration = base_info["weeks_in_base"]

            characteristics = {
                "depth_pct": depth,
                "duration_weeks": duration,
                "pivot_high": base_info["pivot_high"],
                "breakout_imminent": base_info["breakout_imminent"],
                "volume_dryup": base_info["volume_dryup"],
            }

            if depth > 35:
                return {
                    "type": "wide_and_loose",
                    "quality": "D",
                    **characteristics,
                }

            vcp = self.vcp_detection(symbol, eval_date)
            if vcp.get("is_vcp"):
                return {
                    "type": "vcp",
                    "quality": "A" if vcp.get("tight_pattern") else "B",
                    **characteristics,
                    **vcp,
                }

            recent_closes = closes[-25:] if len(closes) >= 25 else closes
            recent_high = max(recent_closes)
            recent_low = min(recent_closes)
            recent_spread = (recent_high - recent_low) / recent_high * 100.0 if recent_high > 0 else 0
            if depth <= 15 and duration >= 5 and recent_spread <= 12:
                return {
                    "type": "flat_base",
                    "quality": "A" if duration >= 7 and depth <= 10 else "B",
                    **characteristics,
                }

            if duration >= 7 and 12 <= depth <= 35:
                mid_third_low = min(lows[len(lows) // 3 : 2 * len(lows) // 3])
                full_low = min(lows)
                mid_low_match = abs(mid_third_low - full_low) / full_low < 0.02
                handle_high = max(highs[-15:-5]) if len(highs) >= 15 else max(highs[-5:])
                recent_dip = (handle_high - min(lows[-7:])) / handle_high * 100.0 if handle_high > 0 else 0
                handle_present = 5 < recent_dip < 12
                if mid_low_match and handle_present:
                    return {
                        "type": "cup_with_handle",
                        "quality": "A" if depth <= 30 and recent_dip <= 10 else "B",
                        "characteristics": {
                            **characteristics,
                            "handle_dip_pct": round(recent_dip, 1),
                        },
                        "handle_dip_pct": round(recent_dip, 1),
                        **characteristics,
                    }
                if mid_low_match:
                    return {
                        "type": "saucer",
                        "quality": "B" if duration >= 12 else "C",
                        "characteristics": characteristics,
                        **characteristics,
                    }

            min_indices = []
            for i in range(3, len(lows) - 3):
                if lows[i] == min(lows[max(0, i - 3) : min(len(lows), i + 4)]):
                    min_indices.append(i)
            if len(min_indices) >= 2:
                low1 = lows[min_indices[0]]
                low2 = lows[min_indices[-1]]
                diff_pct = abs(low2 - low1) / low1 * 100.0 if low1 > 0 else 100
                if diff_pct <= 5 and (min_indices[-1] - min_indices[0]) >= 10:
                    return {
                        "type": "double_bottom",
                        "quality": "B" if diff_pct <= 3 else "C",
                        "characteristics": {
                            **characteristics,
                            "low_diff_pct": round(diff_pct, 2),
                        },
                        "low_diff_pct": round(diff_pct, 2),
                        **characteristics,
                    }

            if len(lows) >= 30:
                third_thirds = [
                    min(lows[: len(lows) // 3]),
                    min(lows[len(lows) // 3 : 2 * len(lows) // 3]),
                    min(lows[2 * len(lows) // 3 :]),
                ]
                if third_thirds[0] < third_thirds[1] < third_thirds[2]:
                    rise_pct = (third_thirds[2] - third_thirds[0]) / third_thirds[0] * 100.0
                    if 6 <= rise_pct <= 25:
                        return {
                            "type": "ascending_base",
                            "quality": "B",
                            "characteristics": {
                                **characteristics,
                                "rise_pct": round(rise_pct, 1),
                            },
                            "rise_pct": round(rise_pct, 1),
                            **characteristics,
                        }

            return {
                "type": "consolidation",
                "quality": "C" if depth <= 25 else "D",
                "characteristics": characteristics,
                **characteristics,
            }

        return self._with_cursor(_classify_with_cursor)  # type: ignore[no-any-return]

    def base_type_stop(self, symbol: str, eval_date, entry_price: float, atr: float | None = None) -> dict[str, Any]:
        """Compute optimal stop loss based on the SPECIFIC base type detected.

        Different chart bases have proven-optimal stop placements per the canon:
          - cup_with_handle: stop below handle low (last 5-10 bars low) - O'Neil
          - flat_base:        stop below base low - Minervini
          - vcp:              stop below last contraction low (tightest) - Minervini
          - double_bottom:    stop below 2nd low - 0.5x ATR (allow shake-out room)
          - ascending_base:   stop below last higher-low (most recent pullback)
          - saucer:           stop below saucer low (longer cushion)
          - 3wt:              stop below 3-week range low
          - htf:              stop below consolidation low

        Falls back to 8% hard cap if specific stop is unreasonable.

        Returns: { 'stop_price': float, 'method': str, 'reasoning': str }
        """
        base = self.classify_base_type(symbol, eval_date)
        base_type = base.get("type", "no_base")
        twt = self.three_weeks_tight(symbol, eval_date)
        htf = self.high_tight_flag(symbol, eval_date)

        def _compute_stop(cur):
            nonlocal atr
            if atr is None:
                cur.execute(
                    "SELECT atr FROM technical_data_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
                    (symbol, eval_date),
                )
                r = cur.fetchone()
                atr = float(r[0]) if r and r[0] else entry_price * 0.02

            max_stop_pct = 0.08
            floor_stop = entry_price * (1.0 - max_stop_pct)

            method = "fallback_8pct"
            candidate = floor_stop
            reasoning = "8% hard floor (no specific base detected)"

            # Use strategy pattern for base type stop calculations
            from algo.signals.base_type_strategy import get_strategy

            strategy = get_strategy(base_type)
            if strategy:
                cur.execute(
                    "SELECT MIN(low) FROM price_daily WHERE symbol = %s AND date <= %s "
                    "AND date >= %s::date - INTERVAL %s",
                    (symbol, eval_date, eval_date, f"{strategy.lookback_days} days"),
                )
                r = cur.fetchone()
                if r and r[0]:
                    low_price = float(r[0])
                    calc_stop, calc_reasoning = strategy.calculate(low_price, atr, entry_price)
                    candidate = calc_stop
                    method = strategy.name
                    reasoning = calc_reasoning

            if twt.get("is_3wt") and method == "fallback_8pct":
                cur.execute(
                    "SELECT MIN(low) FROM ("
                    "  SELECT low FROM price_weekly WHERE symbol = %s AND date <= %s"
                    "  ORDER BY date DESC LIMIT 3"
                    ") AS recent_3w",
                    (symbol, eval_date),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    three_wk_low = float(row[0])
                    candidate = three_wk_low * 0.985
                    method = "3wt_low"
                    reasoning = f"3-Weeks-Tight: 1.5% below 3wk low ${three_wk_low:.2f}"

            if htf.get("is_ht") and htf.get("pivot_high"):
                pivot_high = htf.get("pivot_high")
                consolidation_pct = htf.get("consolidation_pct")
                if pivot_high is not None and consolidation_pct is not None:
                    if isinstance(pivot_high, (int, float)) and isinstance(consolidation_pct, (int, float)):
                        cons_low = pivot_high * (1 - consolidation_pct / 100)
                        candidate = max(candidate, cons_low * 0.95)
                        method = "htf_consolidation_low"
                        reasoning = f"HTF: 5% below consolidation low ${cons_low:.2f}"
                    else:
                        logger.warning(
                            f"HTF data invalid types for {symbol}: pivot_high={type(pivot_high).__name__}, consolidation_pct={type(consolidation_pct).__name__}"
                        )

            if candidate < floor_stop:
                candidate = floor_stop
                reasoning = f"{reasoning} -> capped at 8% floor (${floor_stop:.2f})"
                method = method + "_capped"

            if candidate >= entry_price:
                candidate = entry_price * 0.93
                method = "sanity_fallback_7pct"
                reasoning = "7% sanity fallback (computed stop was >= entry)"

            return {
                "stop_price": round(candidate, 2),
                "method": method,
                "reasoning": reasoning,
                "base_type": base_type,
                "risk_per_share": round(entry_price - candidate, 2),
                "risk_pct": round((entry_price - candidate) / entry_price * 100, 2),
            }

        return self._with_cursor(_compute_stop)  # type: ignore[no-any-return]

    def three_weeks_tight(self, symbol: str, eval_date) -> dict[str, Any]:
        """
        IBD's "3-Weeks-Tight" (3WT) — high-probability continuation pattern.

        After a stock has rallied from a base, it consolidates for 3 weeks where
        each weekly close is within ~1.5% of the prior weekly close. The weekly
        ranges are also tight. Breakout above the 3-week high signals continuation.

        Per O'Neil's leading-stock studies: 3WT patterns formed by the strongest
        stocks during their advance phases — high reliability for adding to
        existing winners or initiating new positions.

        Returns: {
          'is_3wt': bool,
          'weekly_close_spread_pct': float,   # spread of 3 closes
          'weekly_range_avg_pct': float,      # avg range as % of price
          'pivot_high': float,                # breakout level
          'breakout_imminent': bool,
        }
        """

        def _analyze_3wt(cur):
            cur.execute(
                """
                SELECT date, high, low, close FROM price_weekly
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 5
                """,
                (symbol, eval_date),
            )
            rows = cur.fetchall()
            if len(rows) < 4:
                return {"is_3wt": False, "reason": "insufficient weekly history"}

            last3 = rows[:3]
            closes = [float(r[3]) for r in last3]
            highs = [float(r[1]) for r in last3]
            lows = [float(r[2]) for r in last3]

            cmax = max(closes)
            cmin = min(closes)
            spread_pct = (cmax - cmin) / cmin * 100.0 if cmin > 0 else 100
            is_tight = spread_pct <= 1.5

            ranges_pct = [(h - low) / low * 100.0 for h, low in zip(highs, lows, strict=False) if low > 0]
            avg_range = sum(ranges_pct) / len(ranges_pct) if ranges_pct else 100
            is_quiet = avg_range <= 6.0

            if len(rows) >= 4:
                week_ago_close = float(rows[3][3])
                in_uptrend = closes[0] > week_ago_close * 1.02
            else:
                in_uptrend = False

            is_3wt = is_tight and is_quiet and in_uptrend
            pivot_high = max(highs)

            cur.execute(
                "SELECT close FROM price_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
                (symbol, eval_date),
            )
            r = cur.fetchone()
            cur_close = float(r[0]) if r else 0
            breakout_imminent = is_3wt and cur_close >= pivot_high * 0.98

            return {
                "is_3wt": is_3wt,
                "weekly_close_spread_pct": round(spread_pct, 2),
                "weekly_range_avg_pct": round(avg_range, 2),
                "in_uptrend": in_uptrend,
                "pivot_high": round(pivot_high, 2),
                "breakout_imminent": breakout_imminent,
            }

        return self._with_cursor(_analyze_3wt)  # type: ignore[no-any-return]

    def high_tight_flag(self, symbol: str, eval_date) -> dict[str, Any]:
        """
        IBD's "High Tight Flag" (HTF) — rare but highly explosive continuation.

        Definition (O'Neil's leading-stock study):
          1. Stock advances 100%+ in 4-8 weeks (parabolic move)
          2. Then consolidates in a tight 1-3 week range (max ~25% pullback)
          3. Volume dries up during consolidation
          4. Breakout above the consolidation high signals continuation

        Per O'Neil's CAN SLIM research, HTF stocks have produced some of the
        biggest gains in market history (think early-stage biotech, tech IPOs).
        Rare pattern — most stocks won't show it. When it appears, it's a tier-1
        setup for swing traders willing to take the heat.

        Returns: {
          'is_htf': bool,
          'prior_advance_pct': float,
          'consolidation_pct': float,
          'consolidation_weeks': int,
          'pivot_high': float,
        }
        """

        def _analyze_htf(cur):
            cur.execute(
                """
                SELECT date, high, low, close FROM price_weekly
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 12
                """,
                (symbol, eval_date),
            )
            rows = cur.fetchall()
            if len(rows) < 8:
                return {"is_ht": False, "reason": "insufficient weekly history"}

            rows = list(reversed(rows))
            highs = [float(r[1]) for r in rows]
            lows = [float(r[2]) for r in rows]
            closes = [float(r[3]) for r in rows]

            best_htf = None
            for cons_weeks in (1, 2, 3):
                if len(rows) < 4 + cons_weeks:
                    continue
                cons_highs = highs[-cons_weeks:]
                cons_lows = lows[-cons_weeks:]
                cons_high = max(cons_highs)
                cons_low = min(cons_lows)
                cons_pct = (cons_high - cons_low) / cons_high * 100.0 if cons_high > 0 else 100

                if cons_pct > 25:
                    continue

                for adv_weeks in (4, 5, 6, 7, 8):
                    if len(rows) < adv_weeks + cons_weeks:
                        continue
                    advance_section = closes[-(adv_weeks + cons_weeks) : -cons_weeks]
                    if not advance_section:
                        continue
                    start_close = advance_section[0]
                    end_close = advance_section[-1]
                    if start_close <= 0:
                        continue
                    advance_pct = (end_close - start_close) / start_close * 100.0
                    if advance_pct >= 100:
                        if best_htf is None or advance_pct > best_htf["advance"]:
                            best_htf = {
                                "advance": advance_pct,
                                "cons_pct": cons_pct,
                                "cons_weeks": cons_weeks,
                                "pivot_high": cons_high,
                            }

            if best_htf:
                return {
                    "is_htf": True,
                    "prior_advance_pct": round(best_htf["advance"], 1),
                    "consolidation_pct": round(best_htf["cons_pct"], 1),
                    "consolidation_weeks": best_htf["cons_weeks"],
                    "pivot_high": round(best_htf["pivot_high"], 2),
                }
            return {"is_htf": False}

        return self._with_cursor(_analyze_htf)  # type: ignore[no-any-return]
