#!/usr/bin/env python3
"""
Quantitative Market Exposure Engine - Research-backed 9-factor composite

Replaces simple "Stage 2 yes/no" gating with a 0-100 portfolio risk allocation
score driven by these inputs (weights from synthesis of IBD, O'Neil, Weinstein,
Zweig, AAII contrarian, Schwab/Fidelity breadth research):

    20pt  IBD MARKET STATE      Confirmed Uptrend / Pressure / Correction
    15pt  TREND 30-WK MA        SPY price vs rising/flat/falling 30-week MA
    15pt  BREADTH % > 50-DMA    short-term participation (linear 20-80%)
    10pt  BREADTH % > 200-DMA   longer-term health (linear 30-80%)
    10pt  VIX REGIME            <15 / 15-25 / 25-35 / 35+
    10pt  MCCLELLAN OSCILLATOR  short-term momentum (-100 to +100 zone)
     8pt  NEW HIGHS - LOWS      regime health indicator
     7pt  ADVANCE-DECLINE LINE  confirmation / divergence vs index
     5pt  AAII SENTIMENT        contrarian: extreme bullish = caution

PLUS HARD VETOES (cap at ≤25%):
  - SPY < rising 30-wk MA AND breadth_50 < 30%
  - VIX > 40 with rising trend
  - 6+ distribution days in last 25 sessions
  - No follow-through day after correction

Output:
    market_exposure_pct (0-100): drives dynamic risk allocation
    state: 'confirmed_uptrend' | 'uptrend_under_pressure' | 'correction'
    factors: dict of each input + sub-score
    halt_reasons: list of any active hard vetoes

Persists daily to market_exposure_daily table for dashboard / audit.
"""

import os
import psycopg2
import json
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


class MarketExposure:
    """Quantitative market regime + exposure % computation."""

    # Factor weights (sum = 100)
    W_IBD_STATE = 20
    W_TREND_30WK = 15
    W_BREADTH_50 = 15
    W_BREADTH_200 = 10
    W_VIX = 10
    W_MCCLELLAN = 10
    W_NEW_HIGHS_LOWS = 8
    W_AD_LINE = 7
    W_AAII = 5

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

    def compute(self, eval_date=None):
        """Compute full market exposure score. Returns dict."""
        if not eval_date:
            eval_date = _date.today()

        self.connect()
        try:
            factors = {}
            score = 0.0

            # --- 1. IBD market state ---
            ibd = self._ibd_state(eval_date)
            ibd_pts = self.W_IBD_STATE * ibd['score_factor']
            factors['ibd_state'] = {
                **ibd,
                'pts': round(ibd_pts, 1),
                'max': self.W_IBD_STATE,
            }
            score += ibd_pts

            # --- 2. Trend 30-week MA (SPY vs SMA_150 + slope) ---
            t30 = self._trend_30wk(eval_date)
            t30_pts = self.W_TREND_30WK * t30['score_factor']
            factors['trend_30wk'] = {**t30, 'pts': round(t30_pts, 1), 'max': self.W_TREND_30WK}
            score += t30_pts

            # --- 3. Breadth: % stocks above 50-DMA ---
            b50 = self._pct_above_ma(eval_date, ma_days=50)
            b50_pts = self.W_BREADTH_50 * b50['score_factor']
            factors['breadth_50dma'] = {**b50, 'pts': round(b50_pts, 1), 'max': self.W_BREADTH_50}
            score += b50_pts

            # --- 4. Breadth: % stocks above 200-DMA ---
            b200 = self._pct_above_ma(eval_date, ma_days=200)
            b200_pts = self.W_BREADTH_200 * b200['score_factor']
            factors['breadth_200dma'] = {**b200, 'pts': round(b200_pts, 1), 'max': self.W_BREADTH_200}
            score += b200_pts

            # --- 5. VIX regime ---
            vix = self._vix_regime(eval_date)
            vix_pts = self.W_VIX * vix['score_factor']
            factors['vix_regime'] = {**vix, 'pts': round(vix_pts, 1), 'max': self.W_VIX}
            score += vix_pts

            # --- 6. McClellan oscillator ---
            mc = self._mcclellan(eval_date)
            mc_pts = self.W_MCCLELLAN * mc['score_factor']
            factors['mcclellan'] = {**mc, 'pts': round(mc_pts, 1), 'max': self.W_MCCLELLAN}
            score += mc_pts

            # --- 7. New highs vs new lows ---
            nhnl = self._new_highs_lows(eval_date)
            nhnl_pts = self.W_NEW_HIGHS_LOWS * nhnl['score_factor']
            factors['new_highs_lows'] = {**nhnl, 'pts': round(nhnl_pts, 1), 'max': self.W_NEW_HIGHS_LOWS}
            score += nhnl_pts

            # --- 8. A/D line confirmation ---
            ad = self._ad_line(eval_date)
            ad_pts = self.W_AD_LINE * ad['score_factor']
            factors['ad_line'] = {**ad, 'pts': round(ad_pts, 1), 'max': self.W_AD_LINE}
            score += ad_pts

            # --- 9. AAII sentiment (contrarian) ---
            aaii = self._aaii_sentiment(eval_date)
            aaii_pts = self.W_AAII * aaii['score_factor']
            factors['aaii_sentiment'] = {**aaii, 'pts': round(aaii_pts, 1), 'max': self.W_AAII}
            score += aaii_pts

            score = max(0.0, min(100.0, score))

            # --- SECTOR ROTATION OVERLAY ---
            # If defensive sectors are leading cyclicals, reduce score
            # (Mansfield rotation research: this precedes broad-market tops)
            try:
                from algo_sector_rotation import SectorRotationDetector
                detector = SectorRotationDetector()
                detector.cur = self.cur  # share connection
                detector._owned = None
                rotation = detector.compute(eval_date)
                if rotation:
                    rot_penalty = rotation.get('reduce_exposure_pts', 0)
                    if rot_penalty > 0:
                        score = max(0.0, score - rot_penalty)
                        factors['sector_rotation'] = {
                            'signal': rotation['signal'],
                            'defensive_lead_score': rotation['defensive_lead_score'],
                            'penalty_applied': rot_penalty,
                            'pts': -rot_penalty,
                            'max': 0,
                        }
                    else:
                        factors['sector_rotation'] = {
                            'signal': rotation['signal'],
                            'defensive_lead_score': rotation['defensive_lead_score'],
                            'penalty_applied': 0,
                            'pts': 0,
                            'max': 0,
                        }
            except Exception as e:
                factors['sector_rotation'] = {'error': str(e)[:60]}

            # --- HARD VETOES ---
            halt_reasons = []
            cap = 100.0

            # Veto 1: SPY < rising 30wk MA AND breadth weak
            if (t30.get('price_below_ma') and b50.get('value', 100) < 30):
                halt_reasons.append('SPY < 30wk MA AND <30% above 50-DMA')
                cap = min(cap, 25.0)
            # Veto 2: VIX > 40 rising
            if vix.get('value', 0) > 40 and vix.get('rising'):
                halt_reasons.append(f'VIX {vix["value"]:.1f} rising > 40')
                cap = min(cap, 30.0)
            # Veto 3: 6+ distribution days
            dd = self._distribution_days(eval_date)
            if dd >= 6:
                halt_reasons.append(f'{dd} distribution days >= 6')
                cap = min(cap, 35.0)
            # Veto 4: in correction without FTD
            if ibd['state'] == 'correction' and not ibd.get('follow_through_day'):
                halt_reasons.append('In correction without follow-through day')
                cap = min(cap, 40.0)

            final = min(score, cap)

            # Determine recommended state
            if final >= 70:
                regime = 'confirmed_uptrend'
            elif final >= 45:
                regime = 'uptrend_under_pressure'
            elif final >= 25:
                regime = 'caution'
            else:
                regime = 'correction'

            result = {
                'eval_date': str(eval_date),
                'raw_score': round(score, 1),
                'capped_score': round(final, 1),
                'exposure_pct': round(final, 1),
                'regime': regime,
                'halt_reasons': halt_reasons,
                'distribution_days': dd,
                'factors': factors,
            }
            self._persist(eval_date, result)
            return result
        finally:
            self.disconnect()

    # ====== Factor implementations ======

    def _ibd_state(self, eval_date):
        """Classify market state using DD count + FTD presence."""
        dd_count = self._distribution_days(eval_date)
        ftd = self._has_follow_through_day(eval_date)
        if dd_count <= 3 and ftd:
            state = 'confirmed_uptrend'
            sf = 1.0
        elif dd_count <= 4:
            state = 'uptrend_under_pressure'
            sf = 0.5
        else:
            state = 'correction'
            sf = 0.0
        return {
            'state': state,
            'score_factor': sf,
            'distribution_days_25d': dd_count,
            'follow_through_day': ftd,
        }

    def _distribution_days(self, eval_date):
        """IBD distribution day count over last 25 trading sessions on SPY.

        Canonical IBD definition: a session where close declines >= 0.2%
        AND volume is heavier than the prior day. Counted in a rolling
        25-session window. (We previously also used > prev_vol; the IBD
        canon specifically uses prior-day comparison, not 50d avg, so this
        is correct as-is. Window size now strictly 25, not 30.)
        """
        self.cur.execute(
            """
            WITH d AS (
                SELECT date, close, volume,
                       LAG(close) OVER (ORDER BY date) AS prev_close,
                       LAG(volume) OVER (ORDER BY date) AS prev_vol
                FROM price_daily
                WHERE symbol = 'SPY' AND date <= %s
                ORDER BY date DESC LIMIT 25
            )
            SELECT COUNT(*) FROM d
            WHERE prev_close IS NOT NULL
              AND close < prev_close * 0.998
              AND volume > prev_vol
            """,
            (eval_date,),
        )
        row = self.cur.fetchone()
        return int(row[0]) if row and row[0] else 0

    def _has_follow_through_day(self, eval_date):
        """Detect FTD: index closes >= 1.25% on volume above prior in last 30 days."""
        self.cur.execute(
            """
            WITH d AS (
                SELECT date, close, volume,
                       LAG(close) OVER (ORDER BY date) AS prev_close,
                       LAG(volume) OVER (ORDER BY date) AS prev_vol
                FROM price_daily
                WHERE symbol = 'SPY' AND date <= %s
                  AND date >= %s::date - INTERVAL '30 days'
            )
            SELECT 1 FROM d
            WHERE prev_close IS NOT NULL
              AND close >= prev_close * 1.0125
              AND volume > prev_vol
            LIMIT 1
            """,
            (eval_date, eval_date),
        )
        return self.cur.fetchone() is not None

    def _trend_30wk(self, eval_date):
        """SPY vs 30-week (150d) MA + slope over 30 trading days."""
        self.cur.execute(
            """
            WITH d AS (
                SELECT date, close,
                       AVG(close) OVER (ORDER BY date ROWS BETWEEN 149 PRECEDING AND CURRENT ROW) AS sma_150,
                       COUNT(*) OVER (ORDER BY date ROWS BETWEEN 149 PRECEDING AND CURRENT ROW) AS pts
                FROM price_daily
                WHERE symbol = 'SPY' AND date <= %s
                ORDER BY date DESC LIMIT 35
            )
            SELECT date, close, sma_150, pts FROM d ORDER BY date DESC
            """,
            (eval_date,),
        )
        rows = self.cur.fetchall()
        if not rows or rows[0][2] is None or int(rows[0][3]) < 150:
            return {'score_factor': 0.5, 'value': None, 'reason': 'Insufficient history'}

        cur_close = float(rows[0][1])
        sma_now = float(rows[0][2])
        sma_30d_ago = float(rows[30][2]) if len(rows) > 30 and rows[30][2] is not None else sma_now

        slope = (sma_now - sma_30d_ago) / sma_30d_ago * 100.0 if sma_30d_ago > 0 else 0
        price_pct = (cur_close - sma_now) / sma_now * 100.0 if sma_now > 0 else 0

        # Score: above and rising = 1.0, above and flat = 0.7, near = 0.5, below = 0.0
        if price_pct > 2 and slope > 1:
            sf = 1.0
        elif price_pct > 0 and slope > 0:
            sf = 0.75
        elif price_pct > -2 and abs(slope) < 1:
            sf = 0.5
        elif price_pct < 0:
            sf = 0.1
        else:
            sf = 0.3

        return {
            'score_factor': sf,
            'price': round(cur_close, 2),
            'sma_150': round(sma_now, 2),
            'slope_pct': round(slope, 2),
            'price_vs_ma_pct': round(price_pct, 2),
            'price_below_ma': cur_close < sma_now,
        }

    def _pct_above_ma(self, eval_date, ma_days):
        """% of all stocks (>$5, with sufficient history) above their N-day MA."""
        self.cur.execute(
            f"""
            WITH stocks AS (
                SELECT symbol,
                       (SELECT close FROM price_daily WHERE symbol = pd.symbol AND date <= %s ORDER BY date DESC LIMIT 1) AS price,
                       (SELECT AVG(close) FROM price_daily WHERE symbol = pd.symbol AND date <= %s
                          AND date >= %s::date - INTERVAL '{ma_days * 2} days') AS ma_n
                FROM (SELECT DISTINCT symbol FROM price_daily WHERE date >= %s::date - INTERVAL '5 days') pd
            )
            SELECT
                COUNT(*) FILTER (WHERE price > ma_n) AS above,
                COUNT(*) FILTER (WHERE price IS NOT NULL AND ma_n IS NOT NULL AND price > 5) AS total
            FROM stocks
            WHERE price IS NOT NULL AND ma_n IS NOT NULL AND price > 5
            """,
            (eval_date, eval_date, eval_date, eval_date),
        )
        row = self.cur.fetchone()
        if not row or not row[1]:
            return {'score_factor': 0.5, 'value': None}
        above, total = int(row[0]), int(row[1])
        pct = above / total * 100.0 if total > 0 else 0
        # Linear: 20% -> 0pts, 80% -> 1.0
        if ma_days == 50:
            sf = max(0.0, min(1.0, (pct - 20) / 60))
        else:  # 200
            sf = max(0.0, min(1.0, (pct - 30) / 50))
        return {'score_factor': sf, 'value': round(pct, 1), 'above': above, 'total': total}

    def _vix_regime(self, eval_date):
        """VIX value -> regime score factor."""
        self.cur.execute(
            """
            SELECT close, LAG(close, 5) OVER (ORDER BY date) AS prior
            FROM price_daily WHERE symbol = '^VIX' AND date <= %s
            ORDER BY date DESC LIMIT 1
            """,
            (eval_date,),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None:
            # Fallback to market_health_daily if ^VIX missing
            self.cur.execute(
                "SELECT vix_level FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
                (eval_date,),
            )
            r2 = self.cur.fetchone()
            if not r2 or r2[0] is None:
                return {'score_factor': 0.7, 'value': None}
            vix = float(r2[0])
            return self._vix_score(vix, rising=False)
        vix = float(row[0])
        prior = float(row[1]) if row[1] is not None else vix
        rising = vix > prior * 1.05
        return self._vix_score(vix, rising=rising)

    def _vix_score(self, vix, rising):
        if vix < 15:
            sf = 1.0
        elif vix < 20:
            sf = 0.85
        elif vix < 25:
            sf = 0.65
        elif vix < 30:
            sf = 0.45
        elif vix < 35:
            sf = 0.30
        else:
            sf = 0.10
        if rising and vix > 20:
            sf *= 0.7
        return {'score_factor': sf, 'value': round(vix, 2), 'rising': rising}

    def _mcclellan(self, eval_date):
        """McClellan Oscillator: 19-EMA(adv-dec) - 39-EMA(adv-dec).

        Approximate using SPY component proxy: count daily advancers/decliners
        in the broad universe.
        """
        # Count advancers/decliners over last 60 days
        self.cur.execute(
            """
            WITH days AS (
                SELECT DISTINCT date FROM price_daily WHERE date <= %s
                  AND date >= %s::date - INTERVAL '90 days' ORDER BY date DESC LIMIT 60
            ),
            ad AS (
                SELECT pd.date,
                       COUNT(*) FILTER (WHERE pd.close > prev.close) AS adv,
                       COUNT(*) FILTER (WHERE pd.close < prev.close) AS dec
                FROM price_daily pd
                JOIN price_daily prev ON prev.symbol = pd.symbol
                                     AND prev.date = (SELECT MAX(date) FROM price_daily
                                                       WHERE symbol = pd.symbol AND date < pd.date)
                WHERE pd.date IN (SELECT date FROM days)
                  AND pd.close > 5
                GROUP BY pd.date
            )
            SELECT date, adv, dec FROM ad ORDER BY date
            """,
            (eval_date, eval_date),
        )
        rows = self.cur.fetchall()
        if len(rows) < 39:
            return {'score_factor': 0.5, 'value': None}
        # Compute ratio (adv-dec)/(adv+dec) per day
        ratios = []
        for date, adv, dec in rows:
            adv = int(adv or 0)
            dec = int(dec or 0)
            tot = adv + dec
            if tot > 0:
                ratios.append((adv - dec) / tot * 1000)  # Scale for McClellan
            else:
                ratios.append(0)

        # Simple EMAs
        def ema(values, span):
            k = 2.0 / (span + 1)
            e = values[0]
            for v in values[1:]:
                e = v * k + e * (1 - k)
            return e

        ema_19 = ema(ratios, 19)
        ema_39 = ema(ratios, 39)
        oscillator = ema_19 - ema_39
        # Score factor: 0 to +100 = 1.0, 0 to -50 = 0.7, < -50 = 0.4, > +100 = 0.5 (overbought)
        if 0 <= oscillator <= 100:
            sf = 1.0
        elif -50 <= oscillator < 0:
            sf = 0.7
        elif oscillator < -50:
            sf = max(0.2, 0.4 + oscillator / 200)  # approaches 0.2 by -100
        else:  # > 100
            sf = 0.5
        return {'score_factor': sf, 'value': round(oscillator, 1)}

    def _new_highs_lows(self, eval_date):
        """52-week new highs vs new lows ratio."""
        self.cur.execute(
            """
            WITH stocks AS (
                SELECT pd.symbol, pd.close,
                       (SELECT MAX(high) FROM price_daily p2 WHERE p2.symbol = pd.symbol
                          AND p2.date >= pd.date - INTERVAL '252 days' AND p2.date < pd.date) AS hi_52w,
                       (SELECT MIN(low) FROM price_daily p2 WHERE p2.symbol = pd.symbol
                          AND p2.date >= pd.date - INTERVAL '252 days' AND p2.date < pd.date) AS lo_52w
                FROM price_daily pd
                WHERE pd.date = %s AND pd.close > 5
            )
            SELECT
                COUNT(*) FILTER (WHERE close > hi_52w) AS new_hi,
                COUNT(*) FILTER (WHERE close < lo_52w) AS new_lo
            FROM stocks
            WHERE hi_52w IS NOT NULL AND lo_52w IS NOT NULL
            """,
            (eval_date,),
        )
        row = self.cur.fetchone()
        if not row:
            return {'score_factor': 0.5, 'value': None}
        new_hi, new_lo = int(row[0] or 0), int(row[1] or 0)
        net = new_hi - new_lo
        # Net +50 -> 1.0, 0 -> 0.5, -50 -> 0
        sf = max(0.0, min(1.0, 0.5 + net / 100.0))
        return {
            'score_factor': sf,
            'new_highs': new_hi,
            'new_lows': new_lo,
            'net': net,
        }

    def _ad_line(self, eval_date):
        """A/D line: cumulative advancers - decliners. Confirms or diverges from index."""
        # Get last 20 days of A/D and SPY
        self.cur.execute(
            """
            WITH ad AS (
                SELECT pd.date,
                       COUNT(*) FILTER (WHERE pd.close > prev.close) AS adv,
                       COUNT(*) FILTER (WHERE pd.close < prev.close) AS dec
                FROM price_daily pd
                JOIN price_daily prev ON prev.symbol = pd.symbol
                  AND prev.date = (SELECT MAX(date) FROM price_daily WHERE symbol = pd.symbol AND date < pd.date)
                WHERE pd.date <= %s AND pd.date >= %s::date - INTERVAL '30 days'
                  AND pd.close > 5
                GROUP BY pd.date
            ),
            spy_dates AS (
                SELECT date, close FROM price_daily WHERE symbol = 'SPY'
                  AND date <= %s AND date >= %s::date - INTERVAL '30 days'
            )
            SELECT
                ad.date,
                SUM(adv - dec) OVER (ORDER BY ad.date) AS ad_cum,
                spy_dates.close
            FROM ad JOIN spy_dates ON ad.date = spy_dates.date
            ORDER BY ad.date
            """,
            (eval_date, eval_date, eval_date, eval_date),
        )
        rows = self.cur.fetchall()
        if len(rows) < 10:
            return {'score_factor': 0.5, 'value': None}
        first_ad = float(rows[0][1])
        last_ad = float(rows[-1][1])
        first_spy = float(rows[0][2])
        last_spy = float(rows[-1][2])
        ad_change = last_ad - first_ad
        spy_change_pct = (last_spy - first_spy) / first_spy * 100.0 if first_spy > 0 else 0
        # Confirmation: both same direction. Divergence: opposite.
        if (ad_change > 0 and spy_change_pct > 0) or (ad_change < 0 and spy_change_pct < 0):
            sf = 1.0
            relation = 'confirming'
        elif ad_change > 0 and spy_change_pct < 0:
            sf = 0.6  # hidden bullish
            relation = 'bullish_divergence'
        else:
            sf = 0.3  # bearish divergence
            relation = 'bearish_divergence'
        return {
            'score_factor': sf,
            'ad_change_20d': int(ad_change),
            'spy_change_pct_20d': round(spy_change_pct, 2),
            'relation': relation,
        }

    def _aaii_sentiment(self, eval_date):
        """AAII sentiment as contrarian indicator."""
        self.cur.execute(
            """
            SELECT bullish, bearish, neutral, date
            FROM aaii_sentiment WHERE date <= %s ORDER BY date DESC LIMIT 8
            """,
            (eval_date,),
        )
        rows = self.cur.fetchall()
        if not rows:
            return {'score_factor': 0.5, 'value': None}
        bull = float(rows[0][0] or 0)
        bear = float(rows[0][1] or 0)
        spread = bull - bear
        # 8-week MA
        spread_ma = sum((float(r[0] or 0) - float(r[1] or 0)) for r in rows) / len(rows)
        # Contrarian: extreme bull (+20) = caution; extreme bear (-15) = bullish opportunity
        if spread > 25:
            sf = 0.3   # extreme bullish = topping risk
        elif spread > 10:
            sf = 0.6
        elif spread > -10:
            sf = 0.9
        elif spread > -20:
            sf = 1.0   # bearish extreme = bullish forward
        else:
            sf = 1.0
        return {
            'score_factor': sf,
            'bull_bear_spread': round(spread, 1),
            'spread_8wk_ma': round(spread_ma, 1),
        }

    def _persist(self, eval_date, result):
        try:
            self.cur.execute(
                """
                CREATE TABLE IF NOT EXISTS market_exposure_daily (
                    date DATE PRIMARY KEY,
                    exposure_pct NUMERIC(5,2),
                    raw_score NUMERIC(5,2),
                    regime VARCHAR(40),
                    distribution_days INTEGER,
                    factors JSONB,
                    halt_reasons TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self.cur.execute(
                """
                INSERT INTO market_exposure_daily
                    (date, exposure_pct, raw_score, regime, distribution_days, factors, halt_reasons)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    exposure_pct = EXCLUDED.exposure_pct,
                    raw_score = EXCLUDED.raw_score,
                    regime = EXCLUDED.regime,
                    distribution_days = EXCLUDED.distribution_days,
                    factors = EXCLUDED.factors,
                    halt_reasons = EXCLUDED.halt_reasons,
                    created_at = CURRENT_TIMESTAMP
                """,
                (
                    eval_date,
                    result['exposure_pct'],
                    result['raw_score'],
                    result['regime'],
                    result['distribution_days'],
                    json.dumps(result['factors']),
                    '; '.join(result['halt_reasons']) or None,
                ),
            )
            if self._owned:
                self._owned.commit()
        except Exception as e:
            print(f"  (persist skipped: {e})")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Compute market exposure for a date")
    parser.add_argument("--date", type=str, default=None,
                        help="Eval date YYYY-MM-DD. Default = latest trading date in price_daily.")
    args = parser.parse_args()
    me = MarketExposure()
    if args.date:
        eval_d = _date.fromisoformat(args.date)
    else:
        # Use latest trading date in price_daily
        me.connect()
        me.cur.execute("SELECT MAX(date) FROM price_daily WHERE symbol='SPY'")
        eval_d = me.cur.fetchone()[0]
    result = me.compute(eval_d)
    print(f"\n{'='*70}")
    print(f"MARKET EXPOSURE — {result['eval_date']}")
    print(f"{'='*70}\n")
    print(f"Regime: {result['regime']}")
    print(f"Exposure %: {result['exposure_pct']}%")
    print(f"Raw score: {result['raw_score']}")
    print(f"Distribution days: {result['distribution_days']}")
    if result['halt_reasons']:
        print(f"\nHALT REASONS:")
        for r in result['halt_reasons']:
            print(f"  - {r}")
    print("\nFactor breakdown:")
    for name, info in result['factors'].items():
        pts = info.get('pts', 0)
        max_pts = info.get('max', '?')
        print(f"  {name:22s}: {pts:5.1f} / {max_pts:>3} pts  ({info})")
