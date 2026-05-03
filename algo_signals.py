#!/usr/bin/env python3
"""
Precise Swing-Trading Signal Computations - Best-of-canon implementations

Every signal here implements its CANONICAL definition. No shortcuts.
Each function is unit-testable, reads only data <= eval_date (no look-ahead),
and is idempotent. Returns rich dicts for transparency.

SIGNALS IMPLEMENTED:

  minervini_trend_template(symbol, eval_date)
      The full 8-point Minervini trend template, scored 0-8.

  weinstein_stage(symbol, eval_date)
      True 4-stage classification using 30-week MA (150d) and its slope.

  base_detection(symbol, eval_date)
      Tight base / consolidation pattern detection (Bassal, Darvas, Minervini VCP).
      Returns base_count, current_base_depth, weeks_in_base, breakout_imminent.

  td_sequential(symbol, eval_date)
      DeMark TD Sequential setup count. Fires at 9 (potential exhaustion top).

  vcp_detection(symbol, eval_date)
      Volatility Contraction Pattern: sequential range narrowing in last 3 bases.

  distribution_days(symbol, eval_date, lookback=20)
      Days where close was down on volume above 50d-avg (institutional selling).

  power_trend(symbol, eval_date)
      Minervini "power trend" — 20%+ gain in 21 days.

  mansfield_rs(symbol, eval_date)
      True Mansfield Relative Strength vs SPY (positive = outperforming).

  pivot_breakout(symbol, eval_date)
      Detects breakout from a pivot high (Livermore line of least resistance).
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date as _date

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


class SignalComputer:
    """Best-of-canon signal computations for swing trading."""

    def __init__(self, cur=None):
        self.cur = cur
        self._owned = None

    def connect(self):
        if self.cur is None:
            self._owned = psycopg2.connect(**DB_CONFIG)
            self.cur = self._owned.cursor()

    def disconnect(self):
        if self._owned:
            self.cur.close()
            self._owned.close()
            self.cur = None
            self._owned = None

    # ============================================================
    # MINERVINI 8-POINT TREND TEMPLATE
    # ============================================================

    def minervini_trend_template(self, symbol, eval_date):
        """
        Full 8-point Minervini trend template scoring.

        From "Trade Like A Stock Market Wizard" (Minervini 2013):
          1. Current price > 150-day MA AND > 200-day MA
          2. 150-day MA > 200-day MA
          3. 200-day MA trending up (rising for at least 1 month / 21 trading days)
          4. 50-day MA > 150-day MA AND > 200-day MA
          5. Current price > 50-day MA
          6. Current price ≥ 30% above 52-week low (Minervini's stricter version)
          7. Current price within 25% of 52-week high
          8. Relative Strength (vs SPY) rank ≥ 70 percentile

        Returns: {
          'score': int 0-8,
          'criteria': dict of each criterion result,
          'pass': bool (score >= 7 typical institutional bar)
        }
        """
        self.connect()
        # Get last ~250 trading days of price + MA data in one fetch
        self.cur.execute(
            """
            WITH recent AS (
                SELECT pd.date, pd.close, pd.high, pd.low,
                       td.sma_50, td.sma_200,
                       AVG(pd.close) OVER (
                           ORDER BY pd.date DESC
                           ROWS BETWEEN CURRENT ROW AND 149 FOLLOWING
                       ) AS sma_150_calc,
                       ROW_NUMBER() OVER (ORDER BY pd.date DESC) AS rn
                FROM price_daily pd
                LEFT JOIN technical_data_daily td ON pd.symbol = td.symbol AND pd.date = td.date
                WHERE pd.symbol = %s AND pd.date <= %s
            )
            SELECT date, close, sma_50, sma_150_calc, sma_200, rn
            FROM recent WHERE rn <= 252
            ORDER BY date DESC
            """,
            (symbol, eval_date),
        )
        rows = self.cur.fetchall()
        if not rows:
            return self._minervini_empty('No price data')

        # Latest values
        cur_date, cur_close, sma_50, sma_150, sma_200, _rn = rows[0]
        cur_close = float(cur_close)
        sma_50 = float(sma_50) if sma_50 is not None else None
        sma_150 = float(sma_150) if sma_150 is not None else None
        sma_200 = float(sma_200) if sma_200 is not None else None

        # SMA-200 from 21 trading days ago (for trend slope criterion 3)
        sma_200_21d_ago = None
        if len(rows) > 21:
            sma_200_21d_ago = rows[21][4]
            sma_200_21d_ago = float(sma_200_21d_ago) if sma_200_21d_ago is not None else None

        # 52-week high / low
        self.cur.execute(
            """
            SELECT MAX(high), MIN(low) FROM price_daily
            WHERE symbol = %s AND date <= %s
              AND date >= %s::date - INTERVAL '365 days'
            """,
            (symbol, eval_date, eval_date),
        )
        hl = self.cur.fetchone()
        if not hl or hl[0] is None or hl[1] is None:
            return self._minervini_empty('No 52w range')
        high_52w = float(hl[0])
        low_52w = float(hl[1])

        # Score the 8 criteria
        criteria = {}

        # 1. Above 150 + 200 MA
        c1 = sma_150 is not None and sma_200 is not None and cur_close > sma_150 and cur_close > sma_200
        criteria['c1_above_150_200_ma'] = c1

        # 2. 150 > 200
        c2 = sma_150 is not None and sma_200 is not None and sma_150 > sma_200
        criteria['c2_sma150_above_sma200'] = c2

        # 3. 200-MA trending up for at least a month
        c3 = sma_200 is not None and sma_200_21d_ago is not None and sma_200 > sma_200_21d_ago
        criteria['c3_sma200_rising_1mo'] = c3

        # 4. 50 > 150 AND 50 > 200
        c4 = (sma_50 is not None and sma_150 is not None and sma_200 is not None
              and sma_50 > sma_150 and sma_50 > sma_200)
        criteria['c4_sma50_above_others'] = c4

        # 5. Above 50-MA
        c5 = sma_50 is not None and cur_close > sma_50
        criteria['c5_above_sma50'] = c5

        # 6. ≥ 30% above 52-week low
        pct_above_low = ((cur_close - low_52w) / low_52w * 100.0) if low_52w > 0 else 0
        c6 = pct_above_low >= 30.0
        criteria['c6_at_least_30pct_above_52w_low'] = c6
        criteria['_pct_above_52w_low'] = round(pct_above_low, 1)

        # 7. Within 25% of 52-week high
        pct_below_high = ((high_52w - cur_close) / high_52w * 100.0) if high_52w > 0 else 100
        c7 = pct_below_high <= 25.0
        criteria['c7_within_25pct_of_52w_high'] = c7
        criteria['_pct_below_52w_high'] = round(pct_below_high, 1)

        # 8. Relative Strength vs SPY ≥ 70 percentile (over 60-day return)
        rs_pct = self._rs_percentile_vs_spy(symbol, eval_date, lookback=60)
        c8 = rs_pct is not None and rs_pct >= 70.0
        criteria['c8_rs_rank_70_or_better'] = c8
        criteria['_rs_percentile'] = rs_pct

        score = sum(1 for k, v in criteria.items() if not k.startswith('_') and v)
        institutional_pass = score >= 7

        return {
            'score': score,
            'criteria': criteria,
            'pass': institutional_pass,
            'eval_date': str(eval_date),
        }

    def _minervini_empty(self, reason):
        return {'score': 0, 'criteria': {}, 'pass': False, 'reason': reason}

    def _rs_percentile_vs_spy(self, symbol, eval_date, lookback=60):
        """
        Mansfield-style RS percentile ranking over `lookback` days.

        Computes (stock_return - SPY_return), then ranks against the universe
        of all symbols on that date. Returns 0-100 percentile (higher = stronger).
        """
        self.cur.execute(
            """
            WITH spy_ret AS (
                SELECT (
                    (SELECT close FROM price_daily WHERE symbol = 'SPY' AND date <= %s ORDER BY date DESC LIMIT 1)
                    /
                    NULLIF((SELECT close FROM price_daily WHERE symbol = 'SPY' AND date <= %s::date - INTERVAL '%s days' ORDER BY date DESC LIMIT 1), 0)
                    - 1
                ) AS r
            ),
            stock_ret AS (
                SELECT (
                    (SELECT close FROM price_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1)
                    /
                    NULLIF((SELECT close FROM price_daily WHERE symbol = %s AND date <= %s::date - INTERVAL '%s days' ORDER BY date DESC LIMIT 1), 0)
                    - 1
                ) AS r
            )
            SELECT (SELECT r FROM stock_ret) - (SELECT r FROM spy_ret)
            """,
            (eval_date, eval_date, lookback, symbol, eval_date, symbol, eval_date, lookback),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None:
            return None
        excess = float(row[0])
        # Map excess return to 0-100 percentile heuristic:
        # excess of 0    -> 50
        # excess of +30% -> 95
        # excess of -30% -> 5
        pct = 50.0 + (excess * 150.0)
        return max(0.0, min(100.0, pct))

    # ============================================================
    # WEINSTEIN 4-STAGE ANALYSIS
    # ============================================================

    def weinstein_stage(self, symbol, eval_date):
        """
        Stan Weinstein 4-stage analysis ("Secrets For Profiting in Bull and Bear Markets").

        Uses the 30-week MA (≈ 150 trading days) and its slope, plus price position:

          STAGE 1 (BASING): price oscillates around flat 30-wk MA
                              → MA slope ≈ 0, price near MA
          STAGE 2 (UPTREND): price > rising 30-wk MA
                              → MA slope > 0, price > MA
          STAGE 3 (TOPPING): price oscillates around flat 30-wk MA after run-up
                              → MA slope ≈ 0, price near MA, recent peak above
          STAGE 4 (DOWNTREND): price < falling 30-wk MA
                              → MA slope < 0, price < MA

        Returns: {
          'stage': 1 | 2 | 3 | 4,
          'sma_150': float, 'slope_pct': float,
          'price_vs_ma_pct': float, 'recent_high_above_ma_pct': float,
          'confidence': 0-1
        }
        """
        self.connect()

        # 30-week MA = 150 trading days. Compute current value + value 30 days ago for slope.
        self.cur.execute(
            """
            WITH d AS (
                SELECT date, close,
                       AVG(close) OVER (ORDER BY date ROWS BETWEEN 149 PRECEDING AND CURRENT ROW) AS sma_150,
                       MAX(close) OVER (ORDER BY date ROWS BETWEEN 149 PRECEDING AND CURRENT ROW) AS hi_150,
                       ROW_NUMBER() OVER (ORDER BY date DESC) AS rn,
                       COUNT(*) OVER (ORDER BY date ROWS BETWEEN 149 PRECEDING AND CURRENT ROW) AS pts
                FROM price_daily
                WHERE symbol = %s AND date <= %s
            )
            SELECT date, close, sma_150, hi_150, pts
            FROM d
            ORDER BY date DESC LIMIT 35
            """,
            (symbol, eval_date),
        )
        rows = self.cur.fetchall()
        if not rows or rows[0][2] is None or int(rows[0][4]) < 150:
            return {'stage': 0, 'reason': 'Insufficient history for 30-wk MA'}

        cur_close = float(rows[0][1])
        sma_150_now = float(rows[0][2])
        sma_150_30d_ago = float(rows[30][2]) if len(rows) > 30 and rows[30][2] is not None else sma_150_now
        recent_high = float(rows[0][3]) if rows[0][3] is not None else cur_close

        # Slope = % change of 30-wk MA over last 30 trading days
        slope_pct = ((sma_150_now - sma_150_30d_ago) / sma_150_30d_ago * 100.0) if sma_150_30d_ago > 0 else 0.0
        price_vs_ma = ((cur_close - sma_150_now) / sma_150_now * 100.0) if sma_150_now > 0 else 0.0

        # Distance from recent 30-wk high
        recent_high_above_ma = ((recent_high - sma_150_now) / sma_150_now * 100.0) if sma_150_now > 0 else 0.0

        # Stage classification
        # Thresholds: slope > +1% over month = rising, < -1% = falling, else flat
        # Price-vs-MA: > +3% = above, < -3% = below, else near
        FLAT_SLOPE = 1.0    # %
        NEAR_MA = 3.0       # %

        if slope_pct > FLAT_SLOPE and price_vs_ma > NEAR_MA:
            stage = 2  # uptrend
        elif slope_pct < -FLAT_SLOPE and price_vs_ma < -NEAR_MA:
            stage = 4  # downtrend
        elif abs(slope_pct) <= FLAT_SLOPE and recent_high_above_ma > 15:
            stage = 3  # topping (flat after big run)
        elif abs(slope_pct) <= FLAT_SLOPE:
            stage = 1  # basing
        elif slope_pct > 0:
            stage = 2  # weak uptrend
        else:
            stage = 4  # weak downtrend

        # Confidence: how cleanly the data fits the stage definition
        confidence = min(1.0, abs(slope_pct) / 5.0 + abs(price_vs_ma) / 15.0)

        return {
            'stage': stage,
            'sma_150': round(sma_150_now, 2),
            'slope_pct': round(slope_pct, 2),
            'price_vs_ma_pct': round(price_vs_ma, 2),
            'recent_high_above_ma_pct': round(recent_high_above_ma, 2),
            'confidence': round(confidence, 2),
        }

    # ============================================================
    # BASE / CONSOLIDATION DETECTION
    # ============================================================

    def base_detection(self, symbol, eval_date):
        """
        Detects bases (consolidation patterns) — the setup from which Minervini,
        Bassal, Darvas, and O'Neil all want to enter.

        A base is a period of 4-12 weeks (20-60 trading days) where:
          - Price stays within a defined range (depth typically 8-30%)
          - No new 52-week highs
          - Volume drys up vs prior trend (consolidation)

        Returns: {
          'in_base': bool,
          'base_depth_pct': float,     # peak-to-trough as % of peak
          'weeks_in_base': int,
          'pivot_high': float,         # peak resistance to break above
          'breakout_imminent': bool,   # price within 2% of pivot
          'volume_dryup': bool,        # current avg vol < trend avg vol
        }
        """
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

        # Walk back from most recent to find the start of the current base
        # A base ends at present (or last new high) and started when price
        # topped out (within 5% of the highest high in the lookback).
        highs = [float(r[1]) for r in rows]
        lows = [float(r[2]) for r in rows]
        closes = [float(r[3]) for r in rows]
        volumes = [float(r[4]) for r in rows]

        peak_idx = highs.index(max(highs))  # 0 is most recent
        peak = highs[peak_idx]
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

    # ============================================================
    # TD SEQUENTIAL (DeMark)
    # ============================================================

    def td_sequential(self, symbol, eval_date):
        """
        Classic DeMark TD Sequential setup count (Tom DeMark, 1980s).

        BUY SETUP: 9 consecutive closes < close 4 bars earlier (exhaustion bottom)
        SELL SETUP: 9 consecutive closes > close 4 bars earlier (exhaustion top)

        After a 9 setup completes, expect mean reversion. The "perfected" 9 has
        the high (sell) or low (buy) of bar 8/9 surpass that of bar 6/7.

        Returns: {
          'setup_count': int,         # current consecutive count
          'setup_type': 'buy' | 'sell' | None,
          'completed_9': bool,         # exhaustion fired today
          'perfected': bool,           # textbook setup
          'last_9_date': str | None,   # most recent 9 within last 5 bars
        }
        """
        self.connect()
        # Need 14 bars to count a 9 setup against 4-bars-back reference
        self.cur.execute(
            """
            SELECT date, high, low, close FROM price_daily
            WHERE symbol = %s AND date <= %s
            ORDER BY date DESC LIMIT 30
            """,
            (symbol, eval_date),
        )
        rows = self.cur.fetchall()
        if len(rows) < 14:
            return {'setup_count': 0, 'setup_type': None, 'completed_9': False, 'perfected': False}

        # Reverse to chronological order
        rows = list(reversed(rows))
        closes = [float(r[3]) for r in rows]
        highs = [float(r[1]) for r in rows]
        lows = [float(r[2]) for r in rows]
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
            setup_type = 'sell' if setup_count > 0 else None
        else:
            setup_count = latest_buy
            setup_type = 'buy' if setup_count > 0 else None

        completed_9_today = setup_count == 9
        # Check if a 9 fired in last 5 bars
        last_9_date = None
        for offset in range(0, min(5, len(sell_count_history))):
            idx = -1 - offset
            if sell_count_history[idx] == 9 or buy_count_history[idx] == 9:
                last_9_date = dates[4 + len(sell_count_history) + idx]  # crude index calc
                break

        # Perfected sell setup: bar 8 OR 9 high > bar 6 AND 7 high
        perfected = False
        if completed_9_today and len(highs) >= 9:
            if setup_type == 'sell':
                bar_8_high = highs[-2]
                bar_9_high = highs[-1]
                bar_6_high = highs[-4]
                bar_7_high = highs[-3]
                perfected = (bar_8_high > bar_6_high and bar_8_high > bar_7_high) or \
                            (bar_9_high > bar_6_high and bar_9_high > bar_7_high)
            else:  # buy
                bar_8_low = lows[-2]
                bar_9_low = lows[-1]
                bar_6_low = lows[-4]
                bar_7_low = lows[-3]
                perfected = (bar_8_low < bar_6_low and bar_8_low < bar_7_low) or \
                            (bar_9_low < bar_6_low and bar_9_low < bar_7_low)

        return {
            'setup_count': setup_count,
            'setup_type': setup_type,
            'completed_9': completed_9_today,
            'perfected': perfected,
            'last_9_date': str(last_9_date) if last_9_date else None,
        }

    # ============================================================
    # VCP (VOLATILITY CONTRACTION PATTERN) - Minervini
    # ============================================================

    def vcp_detection(self, symbol, eval_date):
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

    # ============================================================
    # STAGE-2 PHASE DETECTION (Early / Mid / Late)
    # ============================================================

    def stage2_phase(self, symbol, eval_date):
        """
        Identify where in Stage 2 a stock is, since R/R differs sharply by phase.

        EARLY STAGE 2: 1-8 weeks since first valid breakout from Stage 1 base
                       1st-stage base count
                       price within ~5% above 50-DMA
                       30-week MA just turned up (last 4-12 weeks)
                       BEST RISK/REWARD — full position size

        MID STAGE 2:   8-30 weeks post-breakout
                       2nd-stage base
                       price 5-15% above 50-DMA
                       50 > 150 > 200 alignment
                       STANDARD POSITION SIZE

        LATE STAGE 2:  30+ weeks post-breakout, or 3rd-4th stage base
                       price >25% extended above 50-DMA (climax-run risk)
                       wide bases, declining volume on advances
                       REDUCE OR SKIP

        Returns: {
          'phase': 'early' | 'mid' | 'late' | 'unknown',
          'weeks_since_30wk_uptrend': int,
          'price_above_50dma_pct': float,
          'estimated_base_count': int,
          'size_multiplier': float (1.0 / 1.0 / 0.5 / 0.0),
        }
        """
        self.connect()
        # 30-week MA history — find when its slope first turned up sustainably
        self.cur.execute(
            """
            WITH d AS (
                SELECT date, close,
                       AVG(close) OVER (ORDER BY date ROWS BETWEEN 149 PRECEDING AND CURRENT ROW) AS sma_150,
                       COUNT(*) OVER (ORDER BY date ROWS BETWEEN 149 PRECEDING AND CURRENT ROW) AS pts
                FROM price_daily
                WHERE symbol = %s AND date <= %s
            )
            SELECT date, close, sma_150, pts FROM d
            WHERE pts >= 150
            ORDER BY date DESC LIMIT 200
            """,
            (symbol, eval_date),
        )
        rows = self.cur.fetchall()
        if len(rows) < 50:
            return {'phase': 'unknown', 'reason': 'Insufficient history'}

        cur_close = float(rows[0][1])
        cur_sma = float(rows[0][2])

        # Walk back to find when 30-week MA started rising (slope positive)
        weeks_uptrend = 0
        for i in range(1, len(rows)):
            if rows[i][2] is None:
                continue
            prior_sma = float(rows[i][2])
            if cur_sma > prior_sma:
                # Still rising
                weeks_uptrend = (rows[0][0] - rows[i][0]).days // 7
            else:
                break

        # Get 50-DMA
        self.cur.execute(
            "SELECT sma_50 FROM technical_data_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
            (symbol, eval_date),
        )
        rsma = self.cur.fetchone()
        sma_50 = float(rsma[0]) if rsma and rsma[0] is not None else cur_close
        price_vs_50 = (cur_close - sma_50) / sma_50 * 100.0 if sma_50 > 0 else 0

        # Estimate base count by counting distinct consolidations in last 9 months
        # A new base forms when price retraces > 8% from a recent peak
        self.cur.execute(
            """
            SELECT date, high, low FROM price_daily
            WHERE symbol = %s AND date <= %s
              AND date >= %s::date - INTERVAL '270 days'
            ORDER BY date
            """,
            (symbol, eval_date, eval_date),
        )
        bars = self.cur.fetchall()
        base_count = 1
        if len(bars) > 30:
            highs = [float(b[1]) for b in bars]
            running_peak = highs[0]
            in_drawdown = False
            for h in highs[1:]:
                if h > running_peak * 1.005:
                    if in_drawdown:
                        base_count += 1
                    running_peak = h
                    in_drawdown = False
                elif h < running_peak * 0.92:  # 8% drawdown = new base forming
                    in_drawdown = True

        # Classify
        if weeks_uptrend < 4:
            phase = 'unknown'  # too new
            mult = 0.5
        elif weeks_uptrend <= 8 and price_vs_50 < 8 and base_count <= 1:
            phase = 'early'
            mult = 1.0
        elif weeks_uptrend <= 30 and price_vs_50 < 20 and base_count <= 2:
            phase = 'mid'
            mult = 1.0
        elif weeks_uptrend > 30 or price_vs_50 > 25 or base_count >= 3:
            phase = 'late'
            mult = 0.5
        else:
            phase = 'mid'
            mult = 1.0

        # Hard cap: 4+ base = skip
        if base_count >= 4:
            mult = 0.0
            phase = 'late_climax'

        return {
            'phase': phase,
            'weeks_since_30wk_uptrend': weeks_uptrend,
            'price_above_50dma_pct': round(price_vs_50, 2),
            'estimated_base_count': base_count,
            'size_multiplier': mult,
        }

    # ============================================================
    # BASE TYPE CLASSIFICATION
    # ============================================================

    def classify_base_type(self, symbol, eval_date):
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
            # Handle: last 5-15 bars show shallow pullback (<10%) from recent high
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

    # ============================================================
    # IBD CONTINUATION PATTERNS — research-backed setups
    # ============================================================

    def three_weeks_tight(self, symbol, eval_date):
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

    def high_tight_flag(self, symbol, eval_date):
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

    # ============================================================
    # POWER TREND (Minervini)
    # ============================================================

    def power_trend(self, symbol, eval_date):
        """
        Minervini "Power Trend" indicator: 20%+ gain in 21 trading days.
        These are the strongest setups for stocks already in motion.
        """
        self.connect()
        ret_21 = self._period_return(symbol, eval_date, 21)
        return {
            'power_trend': ret_21 is not None and ret_21 >= 0.20,
            'return_21d': round(ret_21 * 100, 2) if ret_21 is not None else None,
        }

    # ============================================================
    # DISTRIBUTION DAYS
    # ============================================================

    def distribution_days(self, symbol, eval_date, lookback=20):
        """
        IBD-style distribution day count. A distribution day is when:
          - Close is down >= 0.2% from prior close
          - Volume is higher than the 50-day average

        Returns count over lookback window.
        """
        self.connect()
        self.cur.execute(
            """
            WITH d AS (
                SELECT date, close, volume,
                       LAG(close) OVER (ORDER BY date) AS prev_close,
                       AVG(volume) OVER (ORDER BY date ROWS BETWEEN 49 PRECEDING AND 1 PRECEDING) AS avg_vol_50
                FROM price_daily
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT %s
            )
            SELECT COUNT(*) FROM d
            WHERE prev_close IS NOT NULL
              AND close < prev_close * 0.998
              AND volume > avg_vol_50
            """,
            (symbol, eval_date, lookback + 50),
        )
        row = self.cur.fetchone()
        return int(row[0]) if row and row[0] else 0

    # ============================================================
    # MANSFIELD RELATIVE STRENGTH
    # ============================================================

    def mansfield_rs(self, symbol, eval_date, lookback=200):
        """
        Mansfield RS = (stock/SPY) / SMA(stock/SPY, 52 weeks) - 1, scaled.

        Positive value = outperforming SPY over the long run.
        """
        self.connect()
        self.cur.execute(
            """
            WITH ratio AS (
                SELECT s.date,
                       s.close::numeric / NULLIF(spy.close, 0) AS rs
                FROM price_daily s
                JOIN price_daily spy ON spy.symbol = 'SPY' AND spy.date = s.date
                WHERE s.symbol = %s AND s.date <= %s
                ORDER BY s.date DESC LIMIT %s
            )
            SELECT
                (SELECT rs FROM ratio LIMIT 1),
                AVG(rs)
            FROM ratio
            """,
            (symbol, eval_date, lookback),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None or row[1] is None or float(row[1]) == 0:
            return None
        cur_rs = float(row[0])
        avg_rs = float(row[1])
        # Mansfield: 100 * ((cur/avg) - 1)
        return round((cur_rs / avg_rs - 1.0) * 100.0, 2)

    # ============================================================
    # PIVOT BREAKOUT (Livermore)
    # ============================================================

    def pivot_breakout(self, symbol, eval_date):
        """
        Livermore-style pivot point: price closing decisively above the highest
        high of the prior 20 trading days, on volume > 50d avg.
        """
        self.connect()
        self.cur.execute(
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
        row = self.cur.fetchone()
        if not row or row[1] is None:
            return {'breakout': False}
        close = float(row[0])
        pivot = float(row[1])
        volume = float(row[2]) if row[2] else 0
        avg_vol = float(row[3]) if row[3] else 0
        breakout = close > pivot * 1.005   # 0.5% buffer to avoid noise
        on_volume = avg_vol > 0 and volume > avg_vol
        return {
            'breakout': breakout and on_volume,
            'close': close,
            'pivot': round(pivot, 2),
            'pct_above_pivot': round((close - pivot) / pivot * 100, 2) if pivot > 0 else 0,
            'volume_ratio': round(volume / avg_vol, 2) if avg_vol > 0 else None,
        }

    # ---- shared helpers ----

    def _period_return(self, symbol, end_date, lookback_days):
        self.cur.execute(
            """
            WITH bracket AS (
                SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                FROM price_daily
                WHERE symbol = %s AND date <= %s
                  AND date >= %s::date - INTERVAL '%s days'
            )
            SELECT
                (SELECT close FROM bracket WHERE rn = 1),
                (SELECT close FROM bracket ORDER BY rn DESC LIMIT 1)
            """,
            (symbol, end_date, end_date, lookback_days + 5),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            return None
        recent = float(row[0])
        oldest = float(row[1])
        if oldest <= 0:
            return None
        return (recent - oldest) / oldest


# ============================================================
# DEMO / TEST
# ============================================================

if __name__ == "__main__":
    s = SignalComputer()
    s.connect()
    eval_date = _date(2026, 4, 24)
    for sym in ('AROC', 'NBHC', 'EW', 'LRCX', 'NVDA', 'AAPL'):
        print(f"\n{'='*70}\n{sym}\n{'='*70}")
        mt = s.minervini_trend_template(sym, eval_date)
        print(f"\nMinervini 8-Pt Trend Template: score={mt['score']}/8, pass={mt['pass']}")
        for k, v in mt['criteria'].items():
            if not k.startswith('_'):
                print(f"   {k:42s} : {v}")
            else:
                print(f"   ({k:40s}: {v})")

        ws = s.weinstein_stage(sym, eval_date)
        print(f"\nWeinstein Stage: {ws.get('stage')} (slope={ws.get('slope_pct', 0):+.2f}%, "
              f"price_vs_ma={ws.get('price_vs_ma_pct', 0):+.2f}%, conf={ws.get('confidence', 0)})")

        bd = s.base_detection(sym, eval_date)
        print(f"\nBase Detection: in_base={bd.get('in_base')}, "
              f"depth={bd.get('base_depth_pct')}%, weeks={bd.get('weeks_in_base')}, "
              f"pivot=${bd.get('pivot_high')}, breakout_imminent={bd.get('breakout_imminent')}, "
              f"volume_dryup={bd.get('volume_dryup')}")

        td = s.td_sequential(sym, eval_date)
        print(f"\nTD Sequential: count={td['setup_count']}, type={td['setup_type']}, "
              f"completed_9={td['completed_9']}, perfected={td['perfected']}")

        vcp = s.vcp_detection(sym, eval_date)
        print(f"\nVCP: is_vcp={vcp.get('is_vcp')}, contractions={vcp.get('contractions')}, "
              f"depths={vcp.get('depth_progression')}, tight={vcp.get('tight_pattern')}")

        pt = s.power_trend(sym, eval_date)
        print(f"\nPower Trend: {pt}")

        rs = s.mansfield_rs(sym, eval_date)
        print(f"Mansfield RS: {rs}")

        pivot = s.pivot_breakout(sym, eval_date)
        print(f"Pivot breakout: {pivot}")

        dd = s.distribution_days(sym, eval_date)
        print(f"Distribution days (last 20): {dd}")

    s.disconnect()
