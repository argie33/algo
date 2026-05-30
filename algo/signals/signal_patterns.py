#!/usr/bin/env python3

"""Pattern-based signal methods — base detection, VCP, 3WT, HTF."""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class SignalPatternsMixin:
    """Chart pattern detection signals."""

    def base_detection(self, symbol: str, eval_date) -> Dict[str, Any]:
        """
        Detects bases (consolidation patterns) — the institutional setup.

        A **base** is a tight consolidation period (4-12 weeks, 20-60 trading days)
        where price trades within a narrow range while accumulation occurs.
        This is the classic Minervini, Bassal, Darvas, and O'Neil entry setup.

        **Base Characteristics:**
          - **Depth**: 8-35% from peak to trough (tighter = stronger)
          - **Duration**: 4-12 weeks in base for setup to mature
          - **Price action**: Oscillating sideways, not making new lows
          - **Volume**: Drying up during consolidation (accumulation)
          - **Breakout**: Imminent when price within 2% of pivot high

        **Technical Logic:**
          1. Find the peak high in last 60 days (base peak)
          2. Measure from peak to present (base range)
          3. Calculate base depth: (peak - low) / peak
          4. Base is valid if: 8% <= depth <= 35% AND duration >= 20 bars
          5. Breakout imminent if: price within 2% of pivot
          6. Volume dryup if: recent 10-bar avg < prior 30-bar avg

        **Return Dict:**
          {
              'in_base': bool (depth 8-35% AND duration >= 4 weeks),
              'base_depth_pct': float (peak-to-trough as % of peak),
              'weeks_in_base': int (days_in_base // 5),
              'pivot_high': float (resistance level to break),
              'pct_to_pivot': float (% below pivot; <2% = breakout imminent),
              'breakout_imminent': bool (in_base AND pct_to_pivot <= 2%),
              'volume_dryup': bool (recent vol < prior vol * 0.8),
              'reason': str (if in_base=False, why),
          }

        **Use Cases:**
          - Entry: Buy breakout above pivot_high on volume if breakout_imminent
          - Rejection: Skip if in_base=False (no setup yet)
          - Stop: Base low is support; below that = setup failed

        **Performance:** ~50ms per symbol

        Args:
            symbol: Stock ticker
            eval_date: Date to evaluate as of

        Returns:
            Dict with base detection results and characteristics
        """
        try:
            # Use existing cursor from parent class, don't reconnect
            if not hasattr(self, 'cur') or self.cur is None:
                self.connect()
            # Look at the last 60 trading days
            self.cur.execute(
                """
                SELECT date, high, low, close, volume FROM price_daily
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 60
                """,
                (symbol, eval_date),
            )
            rows = self.cur.fetchall()
            if len(rows) < 20:
                return {'in_base': False, 'reason': 'Insufficient history'}

            highs = [float(r[1]) for r in rows]
            lows = [float(r[2]) for r in rows]
            closes = [float(r[3]) for r in rows]
            volumes = [float(r[4]) for r in rows]

            # Find the MOST RECENT occurrence of the max high (lowest index in DESC-ordered data).
            # This is the current resistance level. Earlier peaks are old setup failures.
            peak_val = max(highs)
            peak_idx = min(i for i, h in enumerate(highs) if h == peak_val)
            peak = peak_val
            # Slice from start of base (peak) through present
            base_highs = highs[:peak_idx + 1]
            base_lows = lows[:peak_idx + 1]
            base_closes = closes[:peak_idx + 1]
            base_vols = volumes[:peak_idx + 1]

            if len(base_highs) < 10:
                return {'in_base': False, 'reason': f'Base too short ({len(base_highs)} bars)'}

            base_high = max(base_highs)
            base_low = min(base_lows)
            base_depth = ((base_high - base_low) / base_high * 100.0) if base_high > 0 else 0
            weeks_in_base = len(base_highs) // 5  # 5 trading days per week

            cur_price = closes[0]
            # In-base = depth in the 8%-35% range, length >= 4 weeks (20 bars)
            in_base = (8.0 <= base_depth <= 35.0) and len(base_highs) >= 20

            # Breakout imminent: current price within 2% of pivot (base_high)
            pct_to_pivot = ((base_high - cur_price) / base_high * 100.0) if base_high > 0 else 100
            breakout_imminent = in_base and pct_to_pivot <= 2.0

            # Volume drying up: recent 10-bar avg vol < base 30-bar avg vol
            recent_vol = sum(base_vols[:10]) / 10 if len(base_vols) >= 10 else 0
            prior_vol = sum(volumes[20:50]) / 30 if len(volumes) >= 50 else recent_vol
            volume_dryup = prior_vol > 0 and recent_vol < prior_vol * 0.8

            return {
                'in_base': in_base,
                'base_depth_pct': round(base_depth, 1),
                'weeks_in_base': weeks_in_base,
                'pivot_high': round(base_high, 2),
                'pct_to_pivot': round(pct_to_pivot, 2),
                'breakout_imminent': breakout_imminent,
                'volume_dryup': volume_dryup,
            }
        except (ValueError, TypeError, IndexError) as e:
            logger.debug(f"Base detection error for {symbol}: {e}")
            return {'in_base': False, 'reason': f'Calculation error: {str(e)[:50]}'}
        except Exception as e:
            if self._owned:
                try:
                    self._owned.rollback()
                except Exception as rb_e:
                    logger.debug(f"Failed to rollback: {rb_e}")
            logger.error(f"Unexpected error in base_detection({symbol}): {e}")
            return {'in_base': False, 'reason': 'Unexpected error'}

    def vcp_detection(self, symbol: str, eval_date) -> Dict[str, Any]:
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
        try:
            # Use existing cursor from parent class, don't reconnect
            if not hasattr(self, 'cur') or self.cur is None:
                self.connect()
            # Last 60 bars
            self.cur.execute(
                """
                SELECT date, high, low, close FROM price_daily
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 60
                """,
                (symbol, eval_date),
            )
            rows = self.cur.fetchall()
            if len(rows) < 30:
                return {'is_vcp': False, 'reason': 'Insufficient bars'}

            rows = list(reversed(rows))  # chronological
            highs = [float(r[1]) for r in rows]
            lows = [float(r[2]) for r in rows]

            # Find local peaks (high higher than 5 bars on either side) and identify
            # base depths between consecutive peaks.
            peaks = []
            for i in range(5, len(highs) - 5):
                if highs[i] == max(highs[i - 5:i + 6]):
                    peaks.append(i)
            if len(peaks) < 2:
                return {'is_vcp': False, 'contractions': 0}

            # Compute depths between consecutive peaks
            depths = []
            for j in range(len(peaks) - 1):
                p1, p2 = peaks[j], peaks[j + 1]
                window_low = min(lows[p1:p2 + 1])
                depth = ((highs[p1] - window_low) / highs[p1] * 100.0) if highs[p1] > 0 else 0
                depths.append(round(depth, 1))

            # VCP = each subsequent depth <= prior * 0.7
            contractions = 0
            for i in range(1, len(depths)):
                if depths[i] <= depths[i - 1] * 0.7:
                    contractions += 1
            is_vcp = contractions >= 2 and len(depths) >= 3
            tight_pattern = depths[-1] <= 5.0 if depths else False

            return {
                'is_vcp': is_vcp,
                'contractions': contractions,
                'depth_progression': depths,
                'tight_pattern': tight_pattern,
            }


        finally:
            try:
                self.disconnect()
            except Exception as e:
                logger.debug(f"Exception (expected): {e}")
                pass

    def classify_base_type(self, symbol: str, eval_date) -> Dict[str, Any]:
        """
        Classify the current base into canonical chart pattern types:

          - cup_with_handle   (O'Neil): U-shape body + small handle pullback
          - flat_base         (Minervini): tight rectangle, depth <= 15%
          - vcp               (Minervini): 2-4 progressively tighter contractions
          - double_bottom     (W-shape): two lows within 3-5% of each other
          - ascending_base    (Minervini): three higher lows + higher highs
          - saucer            (rounded U with no handle, longer duration)
          - wide_and_loose    (AVOID): large erratic swings, > 35% depth

        Returns: {
          'type': str,
          'quality': 'A' | 'B' | 'C' | 'D' (D = avoid),
          'depth_pct': float,
          'duration_weeks': int,
          'pivot_high': float,
          'breakout_imminent': bool,
          'characteristics': dict
        }
        """
        try:
            self.connect()
            # Use the existing base_detection as starting point
            base_info = self.base_detection(symbol, eval_date)
            if not base_info.get('in_base'):
                return {
                    'type': 'no_base',
                    'quality': 'D',
                    'characteristics': base_info,
                }

            # Pull last 60 bars
            self.cur.execute(
                """
                SELECT date, high, low, close, volume FROM price_daily
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 60
                """,
                (symbol, eval_date),
            )
            rows = list(reversed(self.cur.fetchall()))
            if len(rows) < 20:
                return {'type': 'no_base', 'quality': 'D'}

            highs = [float(r[1]) for r in rows]
            lows = [float(r[2]) for r in rows]
            closes = [float(r[3]) for r in rows]
            volumes = [float(r[4]) for r in rows]

            depth = base_info['base_depth_pct']
            duration = base_info['weeks_in_base']

            characteristics = {
                'depth_pct': depth,
                'duration_weeks': duration,
                'pivot_high': base_info['pivot_high'],
                'breakout_imminent': base_info['breakout_imminent'],
                'volume_dryup': base_info['volume_dryup'],
            }

            # Wide-and-loose: large erratic swings >35% — AVOID
            if depth > 35:
                return {
                    'type': 'wide_and_loose',
                    'quality': 'D',
                    'characteristics': characteristics,
                    **characteristics,
                }

            # Try VCP first (multiple tightening contractions)
            vcp = self.vcp_detection(symbol, eval_date)
            if vcp.get('is_vcp'):
                return {
                    'type': 'vcp',
                    'quality': 'A' if vcp.get('tight_pattern') else 'B',
                    'characteristics': {**characteristics, **vcp},
                    **characteristics,
                    'vcp': vcp,
                }

            # Flat base: depth <= 15%, duration >= 5 weeks, low spread
            spread = (max(highs) - min(lows)) / max(highs) * 100.0 if max(highs) > 0 else 0
            # Tight = closes within narrow range
            recent_closes = closes[-25:] if len(closes) >= 25 else closes
            recent_high = max(recent_closes)
            recent_low = min(recent_closes)
            recent_spread = (recent_high - recent_low) / recent_high * 100.0 if recent_high > 0 else 0
            if depth <= 15 and duration >= 5 and recent_spread <= 12:
                return {
                    'type': 'flat_base',
                    'quality': 'A' if duration >= 7 and depth <= 10 else 'B',
                    'characteristics': characteristics,
                    **characteristics,
                }

            # Cup-with-handle detection: U-shape (low in middle) + smaller pullback at end
            if duration >= 7 and 12 <= depth <= 35:
                mid_idx = len(lows) // 2
                mid_third_low = min(lows[len(lows)//3 : 2*len(lows)//3])
                full_low = min(lows)
                # Low must be roughly in middle third
                mid_low_match = abs(mid_third_low - full_low) / full_low < 0.02
                handle_high = max(highs[-15:-5]) if len(highs) >= 15 else max(highs[-5:])
                recent_dip = (handle_high - min(lows[-7:])) / handle_high * 100.0 if handle_high > 0 else 0
                handle_present = 5 < recent_dip < 12
                if mid_low_match and handle_present:
                    return {
                        'type': 'cup_with_handle',
                        'quality': 'A' if depth <= 30 and recent_dip <= 10 else 'B',
                        'characteristics': {**characteristics, 'handle_dip_pct': round(recent_dip, 1)},
                        'handle_dip_pct': round(recent_dip, 1),
                        **characteristics,
                    }
                # Saucer (cup without handle)
                if mid_low_match:
                    return {
                        'type': 'saucer',
                        'quality': 'B' if duration >= 12 else 'C',
                        'characteristics': characteristics,
                        **characteristics,
                    }

            # Double bottom: two distinct lows within 3-5% of each other
            # Find two local minima
            min_indices = []
            for i in range(3, len(lows) - 3):
                if lows[i] == min(lows[max(0, i-3):min(len(lows), i+4)]):
                    min_indices.append(i)
            if len(min_indices) >= 2:
                low1 = lows[min_indices[0]]
                low2 = lows[min_indices[-1]]
                diff_pct = abs(low2 - low1) / low1 * 100.0 if low1 > 0 else 100
                if diff_pct <= 5 and (min_indices[-1] - min_indices[0]) >= 10:
                    return {
                        'type': 'double_bottom',
                        'quality': 'B' if diff_pct <= 3 else 'C',
                        'characteristics': {**characteristics, 'low_diff_pct': round(diff_pct, 2)},
                        'low_diff_pct': round(diff_pct, 2),
                        **characteristics,
                    }

            # Ascending base: three higher lows
            if len(lows) >= 30:
                third_thirds = [
                    min(lows[:len(lows)//3]),
                    min(lows[len(lows)//3:2*len(lows)//3]),
                    min(lows[2*len(lows)//3:]),
                ]
                if third_thirds[0] < third_thirds[1] < third_thirds[2]:
                    rise_pct = (third_thirds[2] - third_thirds[0]) / third_thirds[0] * 100.0
                    if 6 <= rise_pct <= 25:
                        return {
                            'type': 'ascending_base',
                            'quality': 'B',
                            'characteristics': {**characteristics, 'rise_pct': round(rise_pct, 1)},
                            'rise_pct': round(rise_pct, 1),
                            **characteristics,
                        }

            # Generic consolidation
            return {
                'type': 'consolidation',
                'quality': 'C' if depth <= 25 else 'D',
                'characteristics': characteristics,
                **characteristics,
            }


        finally:
            try:
                self.disconnect()
            except Exception as e:
                logger.debug(f"Exception (expected): {e}")
                pass

    def base_type_stop(self, symbol: str, eval_date, entry_price: float, atr: Optional[float] = None) -> Dict[str, Any]:
        """Compute optimal stop loss based on the SPECIFIC base type detected.

        Different chart bases have proven-optimal stop placements per the canon:
          - cup_with_handle: stop below handle low (last 5-10 bars low) - O'Neil
          - flat_base:        stop below base low - Minervini
          - vcp:              stop below last contraction low (tightest) - Minervini
          - double_bottom:    stop below 2nd low - 0.5×ATR (allow shake-out room)
          - ascending_base:   stop below last higher-low (most recent pullback)
          - saucer:           stop below saucer low (longer cushion)
          - 3wt:              stop below 3-week range low
          - htf:              stop below consolidation low

        Falls back to 8% hard cap if specific stop is unreasonable.

        Returns: { 'stop_price': float, 'method': str, 'reasoning': str }
        """
        try:
            # Use existing cursor from parent class, don't reconnect
            if not hasattr(self, 'cur') or self.cur is None:
                self.connect()

            base = self.classify_base_type(symbol, eval_date)
            base_type = base.get('type', 'no_base')

            # classify_base_type disconnects internally; reconnect for ATR and stop queries
            if not hasattr(self, 'cur') or self.cur is None:
                self.connect()

            if atr is None:
                self.cur.execute(
                    "SELECT atr FROM technical_data_daily WHERE symbol = %s AND date <= %s "
                    "ORDER BY date DESC LIMIT 1",
                    (symbol, eval_date),
                )
                r = self.cur.fetchone()
                atr = float(r[0]) if r and r[0] else entry_price * 0.02

            # 8% hard floor — nothing wider than this
            max_stop_pct = 0.08
            floor_stop = entry_price * (1.0 - max_stop_pct)

            method = 'fallback_8pct'
            candidate = floor_stop
            reasoning = '8% hard floor (no specific base detected)'

            if base_type == 'cup_with_handle':
                # Stop below handle low (last 7 bars)
                self.cur.execute(
                    "SELECT MIN(low) FROM price_daily WHERE symbol = %s AND date <= %s "
                    "AND date >= %s::date - INTERVAL '7 days'",
                    (symbol, eval_date, eval_date),
                )
                r = self.cur.fetchone()
                if r and r[0]:
                    handle_low = float(r[0])
                    candidate = handle_low * 0.99  # 1% buffer below handle low
                    method = 'handle_low'
                    reasoning = f'Cup-handle: 1% below handle low ${handle_low:.2f}'

            elif base_type == 'flat_base':
                # Stop below base low (full base lookback ~30 days)
                self.cur.execute(
                    "SELECT MIN(low) FROM price_daily WHERE symbol = %s AND date <= %s "
                    "AND date >= %s::date - INTERVAL '35 days'",
                    (symbol, eval_date, eval_date),
                )
                r = self.cur.fetchone()
                if r and r[0]:
                    base_low = float(r[0])
                    candidate = base_low * 0.995  # 0.5% buffer
                    method = 'flat_base_low'
                    reasoning = f'Flat base: 0.5% below base low ${base_low:.2f}'

            elif base_type == 'vcp':
                # Stop below last contraction low (tightest — last 10 bars)
                self.cur.execute(
                    "SELECT MIN(low) FROM price_daily WHERE symbol = %s AND date <= %s "
                    "AND date >= %s::date - INTERVAL '10 days'",
                    (symbol, eval_date, eval_date),
                )
                r = self.cur.fetchone()
                if r and r[0]:
                    vcp_low = float(r[0])
                    candidate = vcp_low * 0.99
                    method = 'vcp_last_contraction'
                    reasoning = f'VCP: 1% below last contraction low ${vcp_low:.2f}'

            elif base_type == 'double_bottom':
                # Stop below 2nd low - 0.5×ATR (room for shake-out)
                self.cur.execute(
                    "SELECT MIN(low) FROM price_daily WHERE symbol = %s AND date <= %s "
                    "AND date >= %s::date - INTERVAL '20 days'",
                    (symbol, eval_date, eval_date),
                )
                r = self.cur.fetchone()
                if r and r[0]:
                    second_low = float(r[0])
                    candidate = second_low - (0.5 * atr)
                    method = 'double_bottom_low_minus_half_atr'
                    reasoning = f'Double-bottom: 2nd low ${second_low:.2f} - 0.5×ATR (${atr:.2f})'

            elif base_type == 'ascending_base':
                # Stop below most recent higher-low (last 1/3 of base)
                self.cur.execute(
                    "SELECT MIN(low) FROM price_daily WHERE symbol = %s AND date <= %s "
                    "AND date >= %s::date - INTERVAL '14 days'",
                    (symbol, eval_date, eval_date),
                )
                r = self.cur.fetchone()
                if r and r[0]:
                    last_hl = float(r[0])
                    candidate = last_hl * 0.985  # 1.5% buffer
                    method = 'ascending_base_last_higher_low'
                    reasoning = f'Ascending base: 1.5% below last higher low ${last_hl:.2f}'

            elif base_type == 'saucer':
                # Wider stop, saucer base low
                self.cur.execute(
                    "SELECT MIN(low) FROM price_daily WHERE symbol = %s AND date <= %s "
                    "AND date >= %s::date - INTERVAL '60 days'",
                    (symbol, eval_date, eval_date),
                )
                r = self.cur.fetchone()
                if r and r[0]:
                    saucer_low = float(r[0])
                    candidate = saucer_low * 0.99
                    method = 'saucer_base_low'
                    reasoning = f'Saucer: 1% below saucer low ${saucer_low:.2f}'

            twt = self.three_weeks_tight(symbol, eval_date)
            if twt.get('is_3wt') and method == 'fallback_8pct':
                # 3WT: stop below the 3-week range low (subquery limits rows BEFORE aggregating)
                self.cur.execute(
                    "SELECT MIN(low) FROM ("
                    "  SELECT low FROM price_weekly WHERE symbol = %s AND date <= %s"
                    "  ORDER BY date DESC LIMIT 3"
                    ") AS recent_3w",
                    (symbol, eval_date),
                )
                row = self.cur.fetchone()
                if row and row[0] is not None:
                    three_wk_low = float(row[0])
                    candidate = three_wk_low * 0.985
                    method = '3wt_low'
                    reasoning = f'3-Weeks-Tight: 1.5% below 3wk low ${three_wk_low:.2f}'

            htf = self.high_tight_flag(symbol, eval_date)
            if htf.get('is_htf') and htf.get('pivot_high'):
                # HTF: typically wider stop given volatility
                cons_low = htf.get('pivot_high', 0) * (1 - htf.get('consolidation_pct', 25) / 100)
                candidate = max(candidate, cons_low * 0.95)  # 5% buffer for HTF volatility
                method = 'htf_consolidation_low'
                reasoning = f'HTF: 5% below consolidation low ${cons_low:.2f}'

            # Enforce 8% floor (never wider than 8%)
            if candidate < floor_stop:
                candidate = floor_stop
                reasoning = f'{reasoning} -> capped at 8% floor (${floor_stop:.2f})'
                method = method + '_capped'

            # Enforce sanity: stop must be below entry
            if candidate >= entry_price:
                candidate = entry_price * 0.93  # 7% fallback
                method = 'sanity_fallback_7pct'
                reasoning = '7% sanity fallback (computed stop was >= entry)'

            return {
                'stop_price': round(candidate, 2),
                'method': method,
                'reasoning': reasoning,
                'base_type': base_type,
                'risk_per_share': round(entry_price - candidate, 2),
                'risk_pct': round((entry_price - candidate) / entry_price * 100, 2),
            }


        finally:
            try:
                self.disconnect()
            except Exception as e:
                logger.debug(f"Exception (expected): {e}")
                pass

    def three_weeks_tight(self, symbol: str, eval_date) -> Dict[str, Any]:
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
        try:
            # Use existing cursor from parent class, don't reconnect
            if not hasattr(self, 'cur') or self.cur is None:
                self.connect()
            # Need 4+ weeks of weekly data
            self.cur.execute(
                """
                SELECT date, high, low, close FROM price_weekly
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 5
                """,
                (symbol, eval_date),
            )
            rows = self.cur.fetchall()
            if len(rows) < 4:
                return {'is_3wt': False, 'reason': 'insufficient weekly history'}
            # rows[0]=most recent, rows[1..3] = 3 weeks back
            # Take last 3 weekly closes
            last3 = rows[:3]
            closes = [float(r[3]) for r in last3]
            highs = [float(r[1]) for r in last3]
            lows = [float(r[2]) for r in last3]

            # All 3 closes within 1.5% of each other (spread of max-min)
            cmax = max(closes)
            cmin = min(closes)
            spread_pct = (cmax - cmin) / cmin * 100.0 if cmin > 0 else 100
            is_tight = spread_pct <= 1.5

            # Each weekly range is small (< 5% of price)
            ranges_pct = [(h - l) / l * 100.0 for h, l in zip(highs, lows) if l > 0]
            avg_range = sum(ranges_pct) / len(ranges_pct) if ranges_pct else 100
            is_quiet = avg_range <= 6.0

            # Must be in a rising trend (close above 3 weeks ago)
            if len(rows) >= 4:
                week_ago_close = float(rows[3][3])
                in_uptrend = closes[0] > week_ago_close * 1.02
            else:
                in_uptrend = False

            is_3wt = is_tight and is_quiet and in_uptrend
            pivot_high = max(highs)

            # Latest daily close
            self.cur.execute(
                "SELECT close FROM price_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
                (symbol, eval_date),
            )
            r = self.cur.fetchone()
            cur_close = float(r[0]) if r else 0
            breakout_imminent = is_3wt and cur_close >= pivot_high * 0.98

            return {
                'is_3wt': is_3wt,
                'weekly_close_spread_pct': round(spread_pct, 2),
                'weekly_range_avg_pct': round(avg_range, 2),
                'in_uptrend': in_uptrend,
                'pivot_high': round(pivot_high, 2),
                'breakout_imminent': breakout_imminent,
            }

        finally:
            try:
                self.disconnect()
            except Exception as e:
                logger.debug(f"Exception (expected): {e}")
                pass

    def high_tight_flag(self, symbol: str, eval_date) -> Dict[str, Any]:
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
        try:
            # Use existing cursor from parent class, don't reconnect
            if not hasattr(self, 'cur') or self.cur is None:
                self.connect()
            # Need ~12 weeks of weekly data
            self.cur.execute(
                """
                SELECT date, high, low, close FROM price_weekly
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 12
                """,
                (symbol, eval_date),
            )
            rows = self.cur.fetchall()
            if len(rows) < 8:
                return {'is_htf': False, 'reason': 'insufficient weekly history'}

            rows = list(reversed(rows))  # chronological
            highs = [float(r[1]) for r in rows]
            lows = [float(r[2]) for r in rows]
            closes = [float(r[3]) for r in rows]

            # Look for last 1-3 weeks (consolidation) and prior 4-8 weeks (advance)
            # Try different consolidation lengths
            best_htf = None
            for cons_weeks in (1, 2, 3):
                if len(rows) < 4 + cons_weeks:
                    continue
                cons_section = closes[-cons_weeks:]
                cons_highs = highs[-cons_weeks:]
                cons_lows = lows[-cons_weeks:]
                cons_high = max(cons_highs)
                cons_low = min(cons_lows)
                cons_pct = (cons_high - cons_low) / cons_high * 100.0 if cons_high > 0 else 100

                # Tight consolidation: <= 25% range (HTF is allowed wider than other bases)
                if cons_pct > 25:
                    continue

                # Prior advance: 4-8 weeks before consolidation
                for adv_weeks in (4, 5, 6, 7, 8):
                    if len(rows) < adv_weeks + cons_weeks:
                        continue
                    advance_section = closes[-(adv_weeks + cons_weeks):-cons_weeks]
                    if not advance_section:
                        continue
                    start_close = advance_section[0]
                    end_close = advance_section[-1]
                    if start_close <= 0:
                        continue
                    advance_pct = (end_close - start_close) / start_close * 100.0
                    # 100%+ advance qualifies
                    if advance_pct >= 100:
                        if best_htf is None or advance_pct > best_htf['advance']:
                            best_htf = {
                                'advance': advance_pct,
                                'cons_pct': cons_pct,
                                'cons_weeks': cons_weeks,
                                'pivot_high': cons_high,
                            }

            if best_htf:
                return {
                    'is_htf': True,
                    'prior_advance_pct': round(best_htf['advance'], 1),
                    'consolidation_pct': round(best_htf['cons_pct'], 1),
                    'consolidation_weeks': best_htf['cons_weeks'],
                    'pivot_high': round(best_htf['pivot_high'], 2),
                }
            return {'is_htf': False}


        finally:
            try:
                self.disconnect()
            except Exception as e:
                logger.debug(f"Exception (expected): {e}")
                pass
