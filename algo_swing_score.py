#!/usr/bin/env python3
"""
Swing Trader Score - Research-weighted composite specifically for swing trading

Replaces generic IBD/value-oriented scoring with weights tuned for the 3-30 day
swing horizon. Synthesized from agent research summary (Minervini SEPA,
O'Neil CAN SLIM, Bulkowski pattern stats, Connors backtests, Bassal):

    SETUP QUALITY     25%   base type + breakout proximity + VCP + pivot
    TREND QUALITY     20%   Minervini 8-pt + Stage-2 phase + 30wk MA slope
    MOMENTUM / RS     20%   RS percentile + 1m/3m/6m return blend
    VOLUME            12%   breakout volume + accumulation days
    FUNDAMENTALS LITE 10%   EPS growth + revenue growth + ROE
    SECTOR + INDUSTRY  8%   industry rank > sector rank (industry weighted higher)
    MULTI-TIMEFRAME    5%   weekly + monthly buy_sell alignment

HARD-FAIL gates applied BEFORE scoring:
    - Trend Template score < 7
    - Stage != 2
    - Within 25% of 52-week high (not extended past) — already in Tier 3
    - Base count > 3
    - Industry rank > 100 of 197 (bottom half)
    - No earnings within 5 trading days
    - Wide-and-loose base
    - Base quality D

Result persisted to swing_trader_scores table for frontend display
and historical tracking.

The score becomes the PRIMARY ranking field in the filter pipeline,
replacing a blend of SQS + composite. Final position ranking by
swing_score directly.
"""

import os
import psycopg2
import json
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date as _date
from algo_signals import SignalComputer

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


class SwingTraderScore:
    """Compute and persist swing-specific composite scores."""

    # Component weights (sum = 100)
    W_SETUP = 25
    W_TREND = 20
    W_MOMENTUM = 20
    W_VOLUME = 12
    W_FUNDAMENTALS = 10
    W_SECTOR = 8
    W_MULTI_TF = 5

    def __init__(self, cur=None):
        self.cur = cur
        self._owned = None
        self._signals = None

    def connect(self):
        if self.cur is None:
            self._owned = psycopg2.connect(**DB_CONFIG)
            self.cur = self._owned.cursor()
        if self._signals is None:
            self._signals = SignalComputer(cur=self.cur)

    def disconnect(self):
        if self._owned:
            self.cur.close()
            self._owned.close()
            self.cur = None
            self._owned = None

    def compute(self, symbol, eval_date, sector=None, industry=None):
        """Compute the full swing composite + hard fails. Returns dict."""
        self.connect()

        # Hard gates
        gates = self._check_hard_gates(symbol, eval_date, sector, industry)
        if not gates['pass']:
            return {
                'symbol': symbol,
                'eval_date': str(eval_date),
                'pass': False,
                'reason': gates['reason'],
                'hard_gates': gates,
                'swing_score': 0.0,
            }

        # Compute components
        setup_pts, setup_detail = self._setup_component(symbol, eval_date)
        trend_pts, trend_detail = self._trend_component(symbol, eval_date)
        mom_pts, mom_detail = self._momentum_component(symbol, eval_date)
        vol_pts, vol_detail = self._volume_component(symbol, eval_date)
        fund_pts, fund_detail = self._fundamentals_component(symbol)
        sec_pts, sec_detail = self._sector_component(symbol, eval_date, sector, industry)
        mtf_pts, mtf_detail = self._multi_timeframe_component(symbol, eval_date)

        total = setup_pts + trend_pts + mom_pts + vol_pts + fund_pts + sec_pts + mtf_pts

        # Letter grade
        if total >= 85:
            grade = 'A+'
        elif total >= 75:
            grade = 'A'
        elif total >= 65:
            grade = 'B'
        elif total >= 55:
            grade = 'C'
        elif total >= 45:
            grade = 'D'
        else:
            grade = 'F'

        result = {
            'symbol': symbol,
            'eval_date': str(eval_date),
            'pass': True,
            'swing_score': round(total, 1),
            'grade': grade,
            'components': {
                'setup_quality': {'pts': round(setup_pts, 1), 'max': self.W_SETUP, 'detail': setup_detail},
                'trend_quality': {'pts': round(trend_pts, 1), 'max': self.W_TREND, 'detail': trend_detail},
                'momentum_rs':   {'pts': round(mom_pts, 1),   'max': self.W_MOMENTUM, 'detail': mom_detail},
                'volume':        {'pts': round(vol_pts, 1),   'max': self.W_VOLUME, 'detail': vol_detail},
                'fundamentals':  {'pts': round(fund_pts, 1),  'max': self.W_FUNDAMENTALS, 'detail': fund_detail},
                'sector_industry': {'pts': round(sec_pts, 1), 'max': self.W_SECTOR, 'detail': sec_detail},
                'multi_timeframe': {'pts': round(mtf_pts, 1), 'max': self.W_MULTI_TF, 'detail': mtf_detail},
            },
            'hard_gates': gates,
        }
        self._persist(symbol, eval_date, result)
        return result

    # ============= HARD GATES =============

    def _check_hard_gates(self, symbol, eval_date, sector, industry):
        # 1. Trend template score >= 7
        self.cur.execute(
            """SELECT minervini_trend_score, weinstein_stage, percent_from_52w_high, consolidation_flag
               FROM trend_template_data WHERE symbol = %s AND date <= %s
               ORDER BY date DESC LIMIT 1""",
            (symbol, eval_date),
        )
        row = self.cur.fetchone()
        if not row:
            return {'pass': False, 'reason': 'No trend data'}
        trend_score = int(row[0] or 0)
        stage = int(row[1] or 0)
        pct_from_high = float(row[2] or 100)
        in_consolidation = bool(row[3])

        if trend_score < 7:
            return {'pass': False, 'reason': f'Minervini score {trend_score}/8 < 7', 'trend_score': trend_score}

        # 2. Must be Stage 2
        if stage != 2:
            return {'pass': False, 'reason': f'Weinstein stage {stage} != 2', 'stage': stage}

        # 3. Within 25% of 52w high (already enforced in T3, double-check)
        if pct_from_high > 25:
            return {'pass': False, 'reason': f'{pct_from_high:.0f}% from 52w high'}

        # 4. Base count check + base type (no wide-and-loose)
        phase = self._signals.stage2_phase(symbol, eval_date)
        if phase.get('estimated_base_count', 0) >= 4:
            return {'pass': False, 'reason': f'Base count {phase["estimated_base_count"]} >= 4'}

        base_type = self._signals.classify_base_type(symbol, eval_date)
        if base_type.get('type') == 'wide_and_loose' or base_type.get('quality') == 'D':
            return {
                'pass': False,
                'reason': f'Bad base: {base_type.get("type")} (quality {base_type.get("quality")})',
                'base': base_type,
            }

        # 5. Industry rank — get from industry_ranking
        industry_rank = None
        if industry:
            self.cur.execute(
                """SELECT current_rank FROM industry_ranking
                   WHERE industry = %s AND date_recorded <= %s
                   ORDER BY date_recorded DESC LIMIT 1""",
                (industry, eval_date),
            )
            r = self.cur.fetchone()
            if r and r[0]:
                industry_rank = int(r[0])

        # We don't hard-fail on missing industry data, but heavy penalty in scoring
        if industry_rank is not None and industry_rank > 100:
            return {
                'pass': False,
                'reason': f'Industry rank {industry_rank} > 100 (bottom half)',
                'industry_rank': industry_rank,
            }

        # 6. Earnings proximity
        days_to_earn = self._days_to_earnings(symbol, eval_date)
        if days_to_earn is not None and 0 <= days_to_earn <= 5:
            return {
                'pass': False,
                'reason': f'Earnings in ~{days_to_earn}d',
                'days_to_earnings': days_to_earn,
            }

        return {
            'pass': True,
            'trend_score': trend_score,
            'stage': stage,
            'base_count': phase.get('estimated_base_count'),
            'base_type': base_type.get('type'),
            'base_quality': base_type.get('quality'),
            'phase': phase.get('phase'),
            'industry_rank': industry_rank,
            'days_to_earnings': days_to_earn,
        }

    # ============= COMPONENTS =============

    def _setup_component(self, symbol, eval_date):
        """25 pts: base type + breakout proximity + VCP + pivot + power + 3WT + HTF."""
        base = self._signals.classify_base_type(symbol, eval_date)
        vcp = self._signals.vcp_detection(symbol, eval_date)
        pivot = self._signals.pivot_breakout(symbol, eval_date)
        power = self._signals.power_trend(symbol, eval_date)
        three_wt = self._signals.three_weeks_tight(symbol, eval_date)
        htf = self._signals.high_tight_flag(symbol, eval_date)

        pts = 0.0
        # Base type quality (max 10 pts)
        type_scores = {
            'vcp': 10, 'flat_base': 9, 'cup_with_handle': 8,
            'ascending_base': 7, 'double_bottom': 6, 'saucer': 5,
            'consolidation': 3, 'no_base': 0, 'wide_and_loose': 0,
        }
        type_pts = type_scores.get(base.get('type'), 0)
        quality_mult = {'A': 1.0, 'B': 0.85, 'C': 0.6, 'D': 0.0}
        type_pts *= quality_mult.get(base.get('quality', 'D'), 0)
        pts += type_pts

        # Breakout imminent bonus (max 5 pts)
        if base.get('breakout_imminent'):
            pts += 5
        elif base.get('in_base'):
            pts += 1.5

        # VCP bonus (max 3 pts)
        if vcp.get('is_vcp'):
            pts += 3 if vcp.get('tight_pattern') else 1.5

        # Pivot breakout (max 2 pts)
        if pivot.get('breakout'):
            pts += 2

        # Power trend (max 2 pts)
        if power.get('power_trend'):
            pts += 2

        # 3-Weeks-Tight bonus (max 2 pts) — IBD continuation pattern
        if three_wt.get('is_3wt'):
            pts += 2 if three_wt.get('breakout_imminent') else 1.0

        # High-Tight Flag bonus (max 4 pts) — rare but powerful
        if htf.get('is_htf'):
            pts += 4

        pts = min(self.W_SETUP, pts)
        return pts, {
            'base_type': base.get('type'),
            'base_quality': base.get('quality'),
            'depth_pct': base.get('depth_pct'),
            'duration_weeks': base.get('duration_weeks'),
            'breakout_imminent': base.get('breakout_imminent'),
            'is_vcp': vcp.get('is_vcp'),
            'pivot_breakout': pivot.get('breakout'),
            'power_trend': power.get('power_trend'),
            'is_3wt': three_wt.get('is_3wt'),
            'is_htf': htf.get('is_htf'),
        }

    def _trend_component(self, symbol, eval_date):
        """20 pts: Minervini score + stage phase multiplier + 30wk slope."""
        self.cur.execute(
            "SELECT minervini_trend_score FROM trend_template_data WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
            (symbol, eval_date),
        )
        row = self.cur.fetchone()
        mt_score = int(row[0]) if row and row[0] is not None else 0

        # Minervini 7/8 → 75% pts, 8/8 → 100%
        mt_pts = self.W_TREND * 0.6 * (mt_score / 8.0)  # 60% of 20 = 12 pts on Minervini

        # Phase: early=full, mid=full, late=half, climax=zero
        phase = self._signals.stage2_phase(symbol, eval_date)
        phase_mult = phase.get('size_multiplier', 0.5)

        # Stage phase contributes other 40% (8 pts) of trend bucket scaled by phase mult
        phase_pts = self.W_TREND * 0.4 * phase_mult

        pts = mt_pts + phase_pts
        return pts, {
            'minervini_score': mt_score,
            'phase': phase.get('phase'),
            'phase_multiplier': phase_mult,
            'weeks_in_uptrend': phase.get('weeks_since_30wk_uptrend'),
            'estimated_base_count': phase.get('estimated_base_count'),
        }

    def _momentum_component(self, symbol, eval_date):
        """20 pts: RS percentile + 1m/3m/6m return blend."""
        # RS percentile vs SPY (60-day)
        rs_60 = self._signals._rs_percentile_vs_spy(symbol, eval_date, lookback=60)
        rs_pts = 0.0
        if rs_60 is not None:
            # Minervini bar: 70 = pass, 90 = sweet spot
            if rs_60 >= 90:
                rs_pts = 12
            elif rs_60 >= 80:
                rs_pts = 10
            elif rs_60 >= 70:
                rs_pts = 7
            elif rs_60 >= 50:
                rs_pts = 3
            else:
                rs_pts = 0

        # Return blend: 21d (1m), 63d (3m), 126d (6m)
        r1 = self._signals._period_return(symbol, eval_date, 21) or 0
        r3 = self._signals._period_return(symbol, eval_date, 63) or 0
        r6 = self._signals._period_return(symbol, eval_date, 126) or 0
        # Each up to 8 pts max combined: weight 3/3/2
        blend_pts = 0.0
        for ret, weight in [(r1, 3), (r3, 3), (r6, 2)]:
            if ret > 0.30:
                blend_pts += weight
            elif ret > 0.15:
                blend_pts += weight * 0.7
            elif ret > 0.05:
                blend_pts += weight * 0.4
            elif ret > 0:
                blend_pts += weight * 0.2

        pts = min(self.W_MOMENTUM, rs_pts + blend_pts)
        return pts, {
            'rs_percentile_60d': round(rs_60, 1) if rs_60 is not None else None,
            'return_1m': round(r1 * 100, 1),
            'return_3m': round(r3 * 100, 1),
            'return_6m': round(r6 * 100, 1),
        }

    def _volume_component(self, symbol, eval_date):
        """12 pts: breakout volume vs avg + accumulation days."""
        # Latest day volume vs 50d avg
        self.cur.execute(
            """
            WITH d AS (
                SELECT date, volume,
                       AVG(volume) OVER (ORDER BY date ROWS BETWEEN 49 PRECEDING AND 1 PRECEDING) AS avg50
                FROM price_daily WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 1
            )
            SELECT volume, avg50 FROM d
            """,
            (symbol, eval_date),
        )
        row = self.cur.fetchone()
        ratio = None
        ratio_pts = 0.0
        if row and row[0] and row[1]:
            ratio = float(row[0]) / float(row[1])
            # 1.5x = full 6 pts (Bulkowski 65% breakout success threshold)
            if ratio >= 1.5:
                ratio_pts = 6
            elif ratio >= 1.2:
                ratio_pts = 5
            elif ratio >= 1.0:
                ratio_pts = 3
            elif ratio >= 0.7:
                ratio_pts = 1

        # Accumulation days (last 20 days where close up + volume above 50-day avg)
        self.cur.execute(
            """
            WITH d AS (
                SELECT date, close, volume,
                       LAG(close) OVER (ORDER BY date) AS prev_close,
                       AVG(volume) OVER (ORDER BY date ROWS BETWEEN 49 PRECEDING AND 1 PRECEDING) AS avg50
                FROM price_daily WHERE symbol = %s AND date <= %s
                  AND date >= %s::date - INTERVAL '40 days'
            )
            SELECT
                COUNT(*) FILTER (WHERE close > prev_close * 1.002 AND volume > avg50) AS accum,
                COUNT(*) FILTER (WHERE close < prev_close * 0.998 AND volume > avg50) AS dist
            FROM d
            """,
            (symbol, eval_date, eval_date),
        )
        row = self.cur.fetchone()
        accum = int(row[0]) if row else 0
        dist = int(row[1]) if row else 0
        net = accum - dist
        # +5 net = full 6 pts
        accum_pts = max(0.0, min(6.0, (net + 2) * 0.75))

        pts = ratio_pts + accum_pts
        return pts, {
            'today_volume_ratio': round(ratio, 2) if ratio else None,
            'accumulation_days': accum,
            'distribution_days': dist,
            'net_accumulation': net,
        }

    def _fundamentals_component(self, symbol):
        """10 pts: EPS growth + revenue growth + ROE / quality."""
        self.cur.execute(
            """
            SELECT eps_growth_3y_cagr, revenue_growth_3y_cagr,
                   net_income_growth_yoy, revenue_growth_yoy
            FROM growth_metrics WHERE symbol = %s
            ORDER BY date DESC LIMIT 1
            """,
            (symbol,),
        )
        gm = self.cur.fetchone()
        eps_3y = float(gm[0]) if gm and gm[0] is not None else 0
        rev_3y = float(gm[1]) if gm and gm[1] is not None else 0
        ni_yoy = float(gm[2]) if gm and gm[2] is not None else 0
        rev_yoy = float(gm[3]) if gm and gm[3] is not None else 0

        # EPS 3y >= 25% = 4 pts (CAN SLIM "C")
        eps_pts = 0.0
        if eps_3y >= 25:
            eps_pts = 4
        elif eps_3y >= 15:
            eps_pts = 3
        elif eps_3y >= 5:
            eps_pts = 1.5

        # Rev 3y >= 15% = 3 pts (CAN SLIM "S")
        rev_pts = 0.0
        if rev_3y >= 15:
            rev_pts = 3
        elif rev_3y >= 8:
            rev_pts = 2
        elif rev_3y > 0:
            rev_pts = 1

        # YoY positive = 1.5 pts each
        ni_pts = 1.5 if ni_yoy > 10 else (1 if ni_yoy > 0 else 0)
        ry_pts = 1.5 if rev_yoy > 10 else (1 if rev_yoy > 0 else 0)

        pts = eps_pts + rev_pts + ni_pts + ry_pts
        return min(self.W_FUNDAMENTALS, pts), {
            'eps_3y_cagr': eps_3y,
            'rev_3y_cagr': rev_3y,
            'ni_yoy': ni_yoy,
            'rev_yoy': rev_yoy,
        }

    def _sector_component(self, symbol, eval_date, sector, industry):
        """8 pts: industry rank top 40 (5 pts) + sector top half (3 pts)."""
        if sector is None or industry is None:
            self.cur.execute(
                "SELECT sector, industry FROM company_profile WHERE ticker = %s LIMIT 1",
                (symbol,),
            )
            r = self.cur.fetchone()
            if r:
                sector, industry = r[0], r[1]

        ind_pts = 0.0
        sec_pts = 0.0
        ind_rank = None
        sec_rank = None
        if industry:
            self.cur.execute(
                """SELECT current_rank FROM industry_ranking
                   WHERE industry = %s AND date_recorded <= %s
                   ORDER BY date_recorded DESC LIMIT 1""",
                (industry, eval_date),
            )
            r = self.cur.fetchone()
            if r and r[0]:
                ind_rank = int(r[0])
                # top 20 = 5pts, top 40 = 4, top 80 = 2.5
                if ind_rank <= 20:
                    ind_pts = 5.0
                elif ind_rank <= 40:
                    ind_pts = 4.0
                elif ind_rank <= 80:
                    ind_pts = 2.5
                elif ind_rank <= 100:
                    ind_pts = 1.0

        if sector:
            self.cur.execute(
                """SELECT current_rank FROM sector_ranking
                   WHERE sector_name = %s AND date_recorded <= %s
                   ORDER BY date_recorded DESC LIMIT 1""",
                (sector, eval_date),
            )
            r = self.cur.fetchone()
            if r and r[0]:
                sec_rank = int(r[0])
                # 11 sectors total. Top 5 = 3 pts, top 7 = 2, else 0
                if sec_rank <= 3:
                    sec_pts = 3.0
                elif sec_rank <= 5:
                    sec_pts = 2.5
                elif sec_rank <= 7:
                    sec_pts = 1.0

        return ind_pts + sec_pts, {
            'industry': industry,
            'industry_rank': ind_rank,
            'sector': sector,
            'sector_rank': sec_rank,
        }

    def _multi_timeframe_component(self, symbol, eval_date):
        """5 pts: weekly + monthly buy_sell alignment with daily."""
        weekly_buy = False
        monthly_up = False
        try:
            self.cur.execute(
                """SELECT 1 FROM buy_sell_weekly WHERE symbol = %s AND signal = 'BUY'
                   AND date >= %s::date - INTERVAL '30 days' AND date <= %s LIMIT 1""",
                (symbol, eval_date, eval_date),
            )
            weekly_buy = self.cur.fetchone() is not None

            # Monthly: any BUY in last 90 days OR price > monthly MA
            self.cur.execute(
                """SELECT 1 FROM buy_sell_monthly WHERE symbol = %s AND signal = 'BUY'
                   AND date >= %s::date - INTERVAL '90 days' AND date <= %s LIMIT 1""",
                (symbol, eval_date, eval_date),
            )
            monthly_up = self.cur.fetchone() is not None
        except Exception:
            pass

        # Documented edge: aligned timeframes 58% win rate vs 39% non-aligned
        pts = 0.0
        if weekly_buy and monthly_up:
            pts = 5.0
        elif weekly_buy:
            pts = 3.0
        elif monthly_up:
            pts = 1.5

        return pts, {'weekly_buy_recent': weekly_buy, 'monthly_buy_recent': monthly_up}

    # ============= helpers =============

    def _days_to_earnings(self, symbol, eval_date):
        self.cur.execute(
            "SELECT MAX(quarter) FROM earnings_history WHERE symbol = %s",
            (symbol,),
        )
        row = self.cur.fetchone()
        if not row or not row[0]:
            return None
        est = row[0] + timedelta(days=45)
        while est < eval_date:
            est += timedelta(days=90)
        return (est - eval_date).days

    def _persist(self, symbol, eval_date, result):
        try:
            self.cur.execute(
                """
                CREATE TABLE IF NOT EXISTS swing_trader_scores (
                    symbol VARCHAR(20),
                    eval_date DATE,
                    swing_score NUMERIC(5,2),
                    grade VARCHAR(3),
                    setup_pts NUMERIC(5,2),
                    trend_pts NUMERIC(5,2),
                    momentum_pts NUMERIC(5,2),
                    volume_pts NUMERIC(5,2),
                    fundamentals_pts NUMERIC(5,2),
                    sector_pts NUMERIC(5,2),
                    multi_tf_pts NUMERIC(5,2),
                    pass_gates BOOLEAN,
                    fail_reason TEXT,
                    components JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, eval_date)
                )
                """
            )
            comp = result.get('components', {})
            self.cur.execute(
                """
                INSERT INTO swing_trader_scores
                    (symbol, eval_date, swing_score, grade,
                     setup_pts, trend_pts, momentum_pts, volume_pts,
                     fundamentals_pts, sector_pts, multi_tf_pts,
                     pass_gates, fail_reason, components)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, eval_date) DO UPDATE SET
                    swing_score = EXCLUDED.swing_score,
                    grade = EXCLUDED.grade,
                    setup_pts = EXCLUDED.setup_pts,
                    trend_pts = EXCLUDED.trend_pts,
                    momentum_pts = EXCLUDED.momentum_pts,
                    volume_pts = EXCLUDED.volume_pts,
                    fundamentals_pts = EXCLUDED.fundamentals_pts,
                    sector_pts = EXCLUDED.sector_pts,
                    multi_tf_pts = EXCLUDED.multi_tf_pts,
                    pass_gates = EXCLUDED.pass_gates,
                    fail_reason = EXCLUDED.fail_reason,
                    components = EXCLUDED.components,
                    created_at = CURRENT_TIMESTAMP
                """,
                (
                    symbol, eval_date, result.get('swing_score', 0), result.get('grade', 'F'),
                    comp.get('setup_quality', {}).get('pts', 0),
                    comp.get('trend_quality', {}).get('pts', 0),
                    comp.get('momentum_rs', {}).get('pts', 0),
                    comp.get('volume', {}).get('pts', 0),
                    comp.get('fundamentals', {}).get('pts', 0),
                    comp.get('sector_industry', {}).get('pts', 0),
                    comp.get('multi_timeframe', {}).get('pts', 0),
                    result.get('pass', False), result.get('reason'),
                    json.dumps(comp),
                ),
            )
            if self._owned:
                self._owned.commit()
        except Exception as e:
            print(f"  (persist swing_score skipped for {symbol}: {e})")


if __name__ == "__main__":
    s = SwingTraderScore()
    s.connect()
    eval_date = _date(2026, 4, 24)
    print(f"\n{'='*80}")
    print(f"SWING TRADER SCORES — {eval_date}")
    print(f"{'='*80}\n")

    # Get sector/industry from company_profile
    candidates = ('AROC', 'CASS', 'CVV', 'EW', 'FSTR', 'LRCX', 'NATR', 'NBHC', 'NGS', 'SMTC', 'SRCE', 'CTS')
    for sym in candidates:
        s.cur.execute("SELECT sector, industry FROM company_profile WHERE ticker = %s", (sym,))
        r = s.cur.fetchone()
        sector = r[0] if r else None
        industry = r[1] if r else None
        result = s.compute(sym, eval_date, sector=sector, industry=industry)
        if result['pass']:
            comp = result['components']
            print(f"{sym:6s} {result['grade']:>3s} {result['swing_score']:5.1f}/100 | "
                  f"setup {comp['setup_quality']['pts']:4.1f} | "
                  f"trend {comp['trend_quality']['pts']:4.1f} | "
                  f"mom {comp['momentum_rs']['pts']:4.1f} | "
                  f"vol {comp['volume']['pts']:4.1f} | "
                  f"fund {comp['fundamentals']['pts']:4.1f} | "
                  f"sec {comp['sector_industry']['pts']:4.1f} | "
                  f"mtf {comp['multi_timeframe']['pts']:4.1f}")
        else:
            print(f"{sym:6s} BLOCKED: {result['reason']}")
    s.disconnect()
