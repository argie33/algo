#!/usr/bin/env python3
"""
Hedge-Fund-Style Multi-Factor Filter & Scoring (Tier 6+)

Layered ON TOP of the 5-tier filter pipeline. The 5 tiers ensure technical
qualification (Minervini-style); this layer applies institutional discipline:

    MOMENTUM (40 pts)  - is the stock + its sector + its tape moving right?
    QUALITY  (30 pts)  - is the business actually good?
    CATALYST (15 pts)  - is there a fundamental reason driving it?
    RISK     (15 pts)  - is the entry well-priced relative to risk?

Total = 100 pts. Used for final ranking among T5 passers, plus HARD-FAIL
gates that block obvious mistakes.

HARD-FAIL gates:
    H1. Earnings within block window           (default <= 5 days)
    H2. Over-extended above 50-DMA              (default >  15%)
    H3. High value-trap risk                    (default >= 75)
    H4. Insufficient liquidity                  (avg $vol < min, default $5M)
    H5. Strong sector requirement (configurable, default off)

Design notes:
    - Hard fails are independent — any one blocks the trade.
    - Soft scoring rewards quality across many dimensions.
    - Each factor reads from a real table (no synthetic data).
    - Failures gracefully default to neutral when data is missing.
"""

import os
import psycopg2
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


class AdvancedFilters:
    """Quality boosters that turn 'qualifying' signals into 'best' signals."""

    # ---- Score weights (sum = 100) ----
    W_MOMENTUM_RS = 15           # Mansfield RS vs SPY
    W_MOMENTUM_SECTOR = 10
    W_MOMENTUM_INDUSTRY = 5
    W_MOMENTUM_VOLUME = 5
    W_MOMENTUM_PRICE_TREND = 5

    W_QUALITY_IBD = 15
    W_QUALITY_FIN = 8
    W_QUALITY_EARNINGS = 7

    W_CATALYST_GROWTH = 7
    W_CATALYST_ANALYST = 5
    W_CATALYST_INSIDER = 3

    W_RISK_EXTENSION = 8
    W_RISK_TRAP = 5
    W_RISK_EARNINGS_PROX = 2

    def __init__(self, config, cur=None):
        self.config = config
        self.cur = cur
        self._owned_conn = None
        self._strong_sectors = None
        self._strong_industries = None
        self._market_breadth = None
        self._sector_full_ranking = None
        self._signals = None  # SignalComputer, lazy-init

    def connect(self):
        if self.cur is None:
            self._owned_conn = psycopg2.connect(**DB_CONFIG)
            self.cur = self._owned_conn.cursor()

    def disconnect(self):
        if self._owned_conn:
            self.cur.close()
            self._owned_conn.close()
            self.cur = None
            self._owned_conn = None

    # ---------- Pre-load: market context ----------

    def load_market_context(self, eval_date):
        self.connect()

        self.cur.execute(
            """
            SELECT sector_name, current_rank, momentum_score
            FROM sector_ranking
            WHERE date_recorded = (
                SELECT MAX(date_recorded) FROM sector_ranking
                WHERE date_recorded <= %s
            )
            AND sector_name <> '' AND sector_name IS NOT NULL
            AND sector_name <> 'Benchmark'
            ORDER BY current_rank ASC
            """,
            (eval_date,),
        )
        sectors = self.cur.fetchall()
        top_n = int(self.config.get('strong_sector_top_n', 5))
        self._sector_full_ranking = {row[0]: int(row[1]) for row in sectors}
        self._strong_sectors = {row[0]: float(row[2] or 0) for row in sectors[:top_n]}

        self.cur.execute(
            """
            SELECT industry, daily_strength_score
            FROM industry_ranking
            WHERE date_recorded = (
                SELECT MAX(date_recorded) FROM industry_ranking
                WHERE date_recorded <= %s
            )
            AND industry <> '' AND industry IS NOT NULL
            AND daily_strength_score IS NOT NULL
            ORDER BY daily_strength_score DESC
            """,
            (eval_date,),
        )
        industries = self.cur.fetchall()
        if industries:
            cutoff_idx = max(1, len(industries) // 4)
            self._strong_industries = {row[0]: float(row[1]) for row in industries[:cutoff_idx]}
        else:
            self._strong_industries = {}

        self.cur.execute(
            "SELECT bullish, bearish, neutral FROM aaii_sentiment WHERE date <= %s ORDER BY date DESC LIMIT 1",
            (eval_date,),
        )
        sent = self.cur.fetchone()
        if sent:
            self._market_breadth = {
                'bullish': float(sent[0] or 0),
                'bearish': float(sent[1] or 0),
                'bull_bear_spread': float(sent[0] or 0) - float(sent[1] or 0),
            }

        return {
            'strong_sectors': list(self._strong_sectors.keys()),
            'strong_industries_count': len(self._strong_industries),
            'market_breadth': self._market_breadth,
        }

    # ---------- Per-candidate evaluation ----------

    def evaluate_candidate(self, symbol, signal_date, entry_price, sector, industry):
        """Run all advanced filters for one candidate.

        Returns dict with:
          'pass': bool (hard fails)
          'reason': string for failure
          'composite_score': 0-100
          'subscores': {momentum, quality, catalyst, risk}
          'components': dict
        """
        self.connect()
        components = {}
        subscores = {'momentum': 0.0, 'quality': 0.0, 'catalyst': 0.0, 'risk': 0.0}
        max_subscores = {'momentum': 40.0, 'quality': 30.0, 'catalyst': 15.0, 'risk': 15.0}
        hard_fail = None

        # ===== HARD-FAIL gates (independent) =====

        # H1. Earnings proximity
        days_to_earnings = self._estimate_days_to_earnings(symbol, signal_date)
        components['days_to_earnings'] = days_to_earnings
        block_window = int(self.config.get('block_days_before_earnings', 5))
        if days_to_earnings is not None and 0 <= days_to_earnings <= block_window:
            hard_fail = f'Earnings in ~{days_to_earnings}d (block window {block_window}d)'

        # H2. Over-extended
        ext_pct = self._extension_pct(symbol, signal_date, entry_price)
        components['extension_pct'] = ext_pct
        max_extension = float(self.config.get('max_extension_above_50ma_pct', 15.0))
        if ext_pct is not None and ext_pct > max_extension:
            hard_fail = hard_fail or f'{ext_pct:.1f}% above 50-DMA (max {max_extension:.0f})'

        # H3. Value trap
        trap_risk, trap_components = self._trap_metrics(symbol)
        components['trap_metrics'] = trap_components
        max_trap = float(self.config.get('max_value_trap_risk', 75.0))
        if trap_risk is not None and trap_risk >= max_trap:
            hard_fail = hard_fail or f'Value-trap risk {trap_risk:.0f} >= {max_trap:.0f}'

        # H4. Liquidity (institutional must)
        avg_dollar_vol = self._avg_dollar_volume(symbol, signal_date)
        components['avg_dollar_volume'] = avg_dollar_vol
        min_liq = float(self.config.get('min_avg_daily_dollar_volume', 5_000_000))
        if avg_dollar_vol is not None and avg_dollar_vol < min_liq:
            hard_fail = hard_fail or f'Liquidity ${avg_dollar_vol/1e6:.1f}M < ${min_liq/1e6:.1f}M'

        # H5. Strong-sector requirement (off by default)
        if self.config.get('require_strong_sector', False):
            if sector and sector not in (self._strong_sectors or {}):
                hard_fail = hard_fail or f'Sector "{sector}" not in top {len(self._strong_sectors or {})}'

        # ===== SOFT scoring (always computed, even when hard-failed) =====

        # MOMENTUM (40)
        rs_pts, rs_value = self._mansfield_rs_score(symbol, signal_date)
        components['relative_strength'] = {'pts': round(rs_pts, 1), 'excess_vs_spy': rs_value}
        subscores['momentum'] += rs_pts

        sec_pts = self._sector_momentum_score(sector)
        components['sector_strength'] = round(sec_pts, 1)
        subscores['momentum'] += sec_pts

        ind_pts = self._industry_momentum_score(industry)
        components['industry_strength'] = round(ind_pts, 1)
        subscores['momentum'] += ind_pts

        vol_pts, vol_ratio = self._volume_confirmation_score(symbol, signal_date)
        components['volume_ratio'] = vol_ratio
        subscores['momentum'] += vol_pts

        trend_pts = self._price_trend_score(symbol, signal_date)
        components['price_trend_pts'] = round(trend_pts, 1)
        subscores['momentum'] += trend_pts

        # SETUP QUALITY (5 pts within momentum bucket): base breakout / VCP
        # Bassal, Darvas, Minervini all emphasize entering on breakout from
        # tight consolidation (vs chasing extended trends).
        setup_pts, setup_breakdown = self._setup_quality_score(symbol, signal_date)
        components['setup_quality'] = setup_breakdown
        subscores['momentum'] += setup_pts

        # QUALITY (30)
        ibd_pts, ibd_breakdown = self._ibd_composite_score(symbol)
        components['ibd_composite'] = ibd_breakdown
        subscores['quality'] += ibd_pts

        fin_pts, fin_val = self._financial_quality_score(symbol)
        components['financial_quality'] = fin_val
        subscores['quality'] += fin_pts

        eq_pts, eq_val = self._earnings_quality_score(symbol)
        components['earnings_quality_score'] = eq_val
        subscores['quality'] += eq_pts

        # CATALYST (15)
        grw_pts, grw_breakdown = self._growth_score(symbol)
        components['growth'] = grw_breakdown
        subscores['catalyst'] += grw_pts

        an_pts, an_net = self._analyst_score(symbol, signal_date)
        components['analyst_net_actions'] = an_net
        subscores['catalyst'] += an_pts

        in_pts, in_net = self._insider_score(symbol, signal_date)
        components['insider_net_value'] = in_net
        subscores['catalyst'] += in_pts

        # RISK (15) — these are GOOD when low risk
        ext_pts = self._extension_risk_score(ext_pct)
        components['extension_pts'] = round(ext_pts, 1)
        subscores['risk'] += ext_pts

        trap_pts = self._trap_risk_score(trap_risk)
        components['trap_pts'] = round(trap_pts, 1)
        subscores['risk'] += trap_pts

        ep_pts = self._earnings_proximity_score(days_to_earnings, block_window)
        components['earnings_proximity_pts'] = round(ep_pts, 1)
        subscores['risk'] += ep_pts

        composite_score = sum(subscores.values())
        return {
            'pass': hard_fail is None,
            'reason': hard_fail or 'all advanced gates passed',
            'composite_score': round(composite_score, 1),
            'subscores': {k: round(v, 1) for k, v in subscores.items()},
            'subscore_max': max_subscores,
            'components': components,
        }

    # ============= MOMENTUM =============

    def _mansfield_rs_score(self, symbol, signal_date):
        stock = self._period_return(symbol, signal_date, 60)
        spy = self._period_return('SPY', signal_date, 60)
        if stock is None or spy is None:
            return 0.0, None
        excess = stock - spy
        # +30% excess → max; -10% excess → 0
        pts = max(0.0, min(self.W_MOMENTUM_RS, (excess + 0.10) * (self.W_MOMENTUM_RS / 0.40)))
        return pts, round(excess, 4)

    def _sector_momentum_score(self, sector):
        if not sector or not self._strong_sectors:
            return 0.0
        rank = self._sector_full_ranking.get(sector, 99) if self._sector_full_ranking else 99
        # Top sector = 10pts, rank 5 = 5pts, rank 11 = 0pts
        return max(0.0, self.W_MOMENTUM_SECTOR * (1.0 - (rank - 1) / 10.0))

    def _industry_momentum_score(self, industry):
        if not industry or not self._strong_industries:
            return 0.0
        return self.W_MOMENTUM_INDUSTRY if industry in self._strong_industries else 0.0

    def _volume_confirmation_score(self, symbol, signal_date):
        self.cur.execute(
            """
            WITH d AS (
                SELECT date, volume,
                       AVG(volume) OVER (ORDER BY date ROWS BETWEEN 49 PRECEDING AND 1 PRECEDING) AS avg_vol
                FROM price_daily
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 1
            )
            SELECT volume, avg_vol FROM d
            """,
            (symbol, signal_date),
        )
        row = self.cur.fetchone()
        if not row or not row[0] or not row[1]:
            return 0.0, None
        vol = float(row[0])
        avg = float(row[1])
        if avg <= 0:
            return 0.0, None
        ratio = vol / avg
        # 1.5x = full points
        pts = max(0.0, min(self.W_MOMENTUM_VOLUME, (ratio - 0.8) * self.W_MOMENTUM_VOLUME / 0.7))
        return pts, round(ratio, 2)

    def _price_trend_score(self, symbol, signal_date):
        """Multi-timeframe alignment (Elder Triple Screen):
            +2 pts each if 5d return positive, 20d return positive,
            +1 pt if also a BUY signal on weekly timeframe (very strong combo).
        """
        r5 = self._period_return(symbol, signal_date, 5)
        r20 = self._period_return(symbol, signal_date, 20)
        if r5 is None or r20 is None:
            return 0.0
        score = 0.0
        if r5 > 0:
            score += 2.0
        if r20 > 0:
            score += 2.0

        # Weekly alignment: if buy_sell_weekly also says BUY in last 30 days, bonus
        try:
            self.cur.execute(
                """SELECT 1 FROM buy_sell_weekly
                   WHERE symbol = %s AND signal = 'BUY'
                     AND date >= %s::date - INTERVAL '30 days'
                     AND date <= %s
                   LIMIT 1""",
                (symbol, signal_date, signal_date),
            )
            if self.cur.fetchone():
                score += 1.0
        except Exception:
            pass

        return min(score, self.W_MOMENTUM_PRICE_TREND)

    def _setup_quality_score(self, symbol, signal_date):
        """Bonus pts for entering on a real base breakout / VCP (canonical swing setup).

        +3 pts: in identified base AND breakout imminent (within 2% of pivot)
        +2 pts: VCP confirmed (sequential range narrowing)
        +1 pt:  pivot breakout fired today on volume
        +1 pt:  Minervini power trend (20%+ in 21 days)
        Capped at 5.
        """
        try:
            if self._signals is None:
                self._signals = SignalComputer(cur=self.cur)
            base = self._signals.base_detection(symbol, signal_date)
            vcp = self._signals.vcp_detection(symbol, signal_date)
            pivot = self._signals.pivot_breakout(symbol, signal_date)
            power = self._signals.power_trend(symbol, signal_date)
        except Exception as e:
            return 0.0, {'error': str(e)[:60]}

        pts = 0.0
        if base.get('in_base') and base.get('breakout_imminent'):
            pts += 3.0
        elif base.get('in_base'):
            pts += 1.5
        if vcp.get('is_vcp'):
            pts += 2.0
        if pivot.get('breakout'):
            pts += 1.0
        if power.get('power_trend'):
            pts += 1.0
        pts = min(5.0, pts)

        return pts, {
            'in_base': base.get('in_base'),
            'breakout_imminent': base.get('breakout_imminent'),
            'base_depth_pct': base.get('base_depth_pct'),
            'is_vcp': vcp.get('is_vcp'),
            'vcp_contractions': vcp.get('contractions'),
            'pivot_breakout': pivot.get('breakout'),
            'power_trend': power.get('power_trend'),
            'return_21d': power.get('return_21d'),
        }

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
        return (recent - oldest) / oldest if oldest > 0 else None

    # ============= QUALITY =============

    def _ibd_composite_score(self, symbol):
        self.cur.execute(
            """
            SELECT composite_score, quality_score, growth_score, momentum_score
            FROM stock_scores WHERE symbol = %s LIMIT 1
            """,
            (symbol,),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None:
            return 0.0, {'composite': None, 'grade': 'NA'}
        composite = float(row[0])
        # 40 = 0pts, 90+ = full pts
        pts = max(0.0, min(self.W_QUALITY_IBD, (composite - 40.0) * self.W_QUALITY_IBD / 50.0))
        grade = ('A+' if composite >= 90 else 'A' if composite >= 80 else 'B' if composite >= 70
                 else 'C' if composite >= 60 else 'D' if composite >= 50 else 'F')
        return pts, {
            'composite': round(composite, 1),
            'grade': grade,
            'quality': round(float(row[1] or 0), 1),
            'growth': round(float(row[2] or 0), 1),
            'momentum': round(float(row[3] or 0), 1),
        }

    def _financial_quality_score(self, symbol):
        """Combine stock_scores.quality_score + balance_sheet_score."""
        self.cur.execute(
            """
            SELECT s.quality_score, v.balance_sheet_score, v.cash_quality_score
            FROM stock_scores s
            LEFT JOIN value_trap_scores v ON v.symbol = s.symbol
            WHERE s.symbol = %s LIMIT 1
            """,
            (symbol,),
        )
        row = self.cur.fetchone()
        if not row:
            return 0.0, None
        q = float(row[0]) if row[0] is not None else 50.0
        bs = float(row[1]) if row[1] is not None else 50.0
        cash = float(row[2]) if row[2] is not None else 50.0
        # Weighted average; 50 = neutral, 100 = full points
        avg = (q * 0.5) + (bs * 0.3) + (cash * 0.2)
        pts = max(0.0, min(self.W_QUALITY_FIN, (avg - 50.0) * self.W_QUALITY_FIN / 30.0))
        return pts, round(avg, 1)

    def _earnings_quality_score(self, symbol):
        self.cur.execute(
            """
            SELECT earnings_quality_score FROM earnings_metrics
            WHERE symbol = %s AND earnings_quality_score IS NOT NULL
            ORDER BY report_date DESC LIMIT 1
            """,
            (symbol,),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None:
            return 0.0, None
        score = float(row[0])
        pts = (score / 100.0) * self.W_QUALITY_EARNINGS
        return pts, round(score, 1)

    # ============= CATALYST =============

    def _growth_score(self, symbol):
        self.cur.execute(
            """
            SELECT revenue_growth_3y_cagr, eps_growth_3y_cagr,
                   quarterly_growth_momentum, revenue_growth_yoy, eps_growth_3y_cagr
            FROM growth_metrics
            WHERE symbol = %s
            ORDER BY date DESC LIMIT 1
            """,
            (symbol,),
        )
        row = self.cur.fetchone()
        if not row:
            return 0.0, {}
        rev_3y = float(row[0]) if row[0] is not None else 0.0
        eps_3y = float(row[1]) if row[1] is not None else 0.0
        mom = float(row[2]) if row[2] is not None else 0.0
        rev_yoy = float(row[3]) if row[3] is not None else 0.0
        # 3 pts each for EPS 3y >20%, rev 3y >15%, positive momentum (within W_CATALYST_GROWTH=7)
        eps_p = max(0.0, min(2.5, eps_3y / 20.0 * 2.5)) if eps_3y > 0 else 0.0
        rev_p = max(0.0, min(2.5, rev_3y / 15.0 * 2.5)) if rev_3y > 0 else 0.0
        mom_p = 2.0 if mom > 0 else 0.0
        return eps_p + rev_p + mom_p, {
            'eps_3y_cagr': round(eps_3y, 1),
            'rev_3y_cagr': round(rev_3y, 1),
            'rev_yoy': round(rev_yoy, 1),
            'momentum': round(mom, 1),
        }

    def _analyst_score(self, symbol, signal_date):
        self.cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE LOWER(action) IN ('up','upgrade')),
                COUNT(*) FILTER (WHERE LOWER(action) IN ('down','downgrade'))
            FROM analyst_upgrade_downgrade
            WHERE symbol = %s
              AND action_date >= %s::date - INTERVAL '90 days'
              AND action_date <= %s
            """,
            (symbol, signal_date, signal_date),
        )
        row = self.cur.fetchone()
        if not row:
            return 0.0, 0
        ups, downs = int(row[0] or 0), int(row[1] or 0)
        net = ups - downs
        # +5 net = full; -3 net = 0
        pts = max(0.0, min(self.W_CATALYST_ANALYST, (net + 3) * self.W_CATALYST_ANALYST / 8.0))
        return pts, net

    def _insider_score(self, symbol, signal_date):
        self.cur.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN LOWER(transaction_type) LIKE '%%buy%%' THEN value END), 0),
                COALESCE(SUM(CASE WHEN LOWER(transaction_type) LIKE '%%sale%%' OR LOWER(transaction_type) LIKE '%%sell%%' THEN value END), 0)
            FROM insider_transactions
            WHERE symbol = %s
              AND transaction_date >= %s::date - INTERVAL '60 days'
              AND transaction_date <= %s
              AND value IS NOT NULL
            """,
            (symbol, signal_date, signal_date),
        )
        row = self.cur.fetchone()
        if not row:
            return 0.0, 0
        buys = float(row[0] or 0)
        sells = float(row[1] or 0)
        net = buys - sells
        if net <= 0:
            return 0.0, net
        pts = min(self.W_CATALYST_INSIDER, net / 500_000.0 * self.W_CATALYST_INSIDER)
        return pts, net

    # ============= RISK =============

    def _extension_pct(self, symbol, signal_date, entry_price):
        self.cur.execute(
            "SELECT sma_50 FROM technical_data_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
            (symbol, signal_date),
        )
        row = self.cur.fetchone()
        if not row or not row[0] or float(row[0]) <= 0:
            return None
        sma_50 = float(row[0])
        return ((entry_price - sma_50) / sma_50) * 100.0

    def _extension_risk_score(self, ext_pct):
        if ext_pct is None:
            return 0.0
        if ext_pct < 0:
            return self.W_RISK_EXTENSION * 0.6   # below 50 = OK but not ideal
        if ext_pct <= 5:
            return self.W_RISK_EXTENSION         # sweet spot
        if ext_pct <= 10:
            return self.W_RISK_EXTENSION * (1.0 - (ext_pct - 5) / 5.0 * 0.5)
        if ext_pct <= 15:
            return self.W_RISK_EXTENSION * 0.25
        return 0.0

    def _trap_metrics(self, symbol):
        self.cur.execute(
            """SELECT trap_risk_score, balance_sheet_score, cash_quality_score
               FROM value_trap_scores WHERE symbol = %s LIMIT 1""",
            (symbol,),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None:
            return None, None
        return float(row[0]), {
            'trap_risk': float(row[0]),
            'balance_sheet': float(row[1]) if row[1] is not None else None,
            'cash_quality': float(row[2]) if row[2] is not None else None,
        }

    def _trap_risk_score(self, trap_risk):
        if trap_risk is None:
            return self.W_RISK_TRAP * 0.6   # neutral when missing
        if trap_risk < 30:
            return self.W_RISK_TRAP
        if trap_risk < 50:
            return self.W_RISK_TRAP * 0.7
        if trap_risk < 70:
            return self.W_RISK_TRAP * 0.4
        return 0.0

    def _earnings_proximity_score(self, days_to_earnings, block_window):
        if days_to_earnings is None:
            return self.W_RISK_EARNINGS_PROX * 0.5
        if days_to_earnings <= block_window:
            return 0.0
        if days_to_earnings >= 30:
            return self.W_RISK_EARNINGS_PROX
        return self.W_RISK_EARNINGS_PROX * (days_to_earnings - block_window) / (30 - block_window)

    def _avg_dollar_volume(self, symbol, signal_date):
        self.cur.execute(
            """
            SELECT AVG(close * volume) FROM price_daily
            WHERE symbol = %s AND date <= %s
              AND date >= %s::date - INTERVAL '50 days'
              AND volume > 0
            """,
            (symbol, signal_date, signal_date),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None:
            return None
        return float(row[0])

    def _estimate_days_to_earnings(self, symbol, signal_date):
        self.cur.execute(
            "SELECT MAX(quarter) FROM earnings_history WHERE symbol = %s",
            (symbol,),
        )
        row = self.cur.fetchone()
        if not row or not row[0]:
            return None
        last_q = row[0]
        est = last_q + timedelta(days=45)
        signal_d = signal_date if isinstance(signal_date, _date) else signal_date
        while est < signal_d:
            est += timedelta(days=90)
        return (est - signal_d).days


if __name__ == "__main__":
    from algo_config import get_config
    f = AdvancedFilters(get_config())
    ctx = f.load_market_context(_date(2026, 4, 24))
    print("Strong sectors:", ctx['strong_sectors'])
    print()
    for sym, sec, ind in [
        ('LRCX', 'Technology', 'Semiconductor Equipment & Materials'),
        ('AROC', 'Energy', 'Oil & Gas Equipment & Services'),
        ('NATR', 'Consumer Defensive', 'Packaged Foods'),
        ('NBHC', 'Financial Services', 'Banks - Regional'),
    ]:
        # Get entry price
        f.cur.execute(
            "SELECT entry_price FROM buy_sell_daily WHERE symbol=%s AND date='2026-04-24' AND signal='BUY'",
            (sym,),
        )
        row = f.cur.fetchone()
        if not row:
            continue
        entry_price = float(row[0])
        result = f.evaluate_candidate(sym, _date(2026, 4, 24), entry_price, sec, ind)
        print(f"\n{sym} ({sec}/{ind}):")
        print(f"  pass: {result['pass']} — {result['reason']}")
        print(f"  composite: {result['composite_score']:.1f}")
        print(f"  subscores: {result['subscores']}")
        print(f"  components: {result['components']}")
    f.disconnect()
