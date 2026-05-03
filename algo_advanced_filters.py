#!/usr/bin/env python3
"""
Advanced Pre-Trade Filters & Composite Signal Scoring

Layered ON TOP of the 5-tier filter pipeline. Pull every quality signal we have
and convert each candidate into a composite score that drives final selection.

Filters added (each can FAIL or PENALIZE):
  F1.  EARNINGS PROXIMITY  — block if earnings expected within window (default 5 days)
  F2.  SECTOR STRENGTH     — sector must rank in top N by momentum_score
  F3.  INDUSTRY STRENGTH   — industry must rank in top quartile
  F4.  RELATIVE STRENGTH   — vs SP500 (Mansfield-style); reward outperformers
  F5.  VOLUME CONFIRMATION — entry-day volume vs 50d avg
  F6.  EXTENSION CHECK     — % above 50-DMA, avoid chasing
  F7.  ANALYST TREND       — recent upgrades minus downgrades
  F8.  INSIDER ACTIVITY    — insider buying recently is a tailwind
  F9.  EARNINGS QUALITY    — earnings_metrics.earnings_quality_score
  F10. IBD COMPOSITE       — stock_scores.composite_score (IBD-style A-F rating)
  F11. QUALITY SCORE       — stock_scores.quality_score (financial health)
  F12. VALUE TRAP CHECK    — value_trap_scores.trap_risk_score (block high traps)
  F13. GROWTH METRICS      — revenue / EPS 3-year CAGR (real growth confirmation)

Signals are combined into composite_score (0-100). Final ranking uses that.

Score weight breakdown (max 130 pts → normalized to 100):
  IBD Composite        20 pts  (most important — captures everything fundamentally)
  Earnings Quality     15 pts
  Growth (3yr CAGR)    15 pts
  Relative Strength    15 pts
  Quality Score        10 pts
  Sector Strength      10 pts
  Industry Strength    10 pts
  Volume Confirmation  10 pts
  Extension (penalty) 10 pts
  Analyst Trend        10 pts
  Insider Activity     10 pts
  Value Trap (penalty)  5 pts
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


class AdvancedFilters:
    """Quality boosters that turn 'qualifying' signals into 'best' signals."""

    def __init__(self, config, cur=None):
        self.config = config
        self.cur = cur  # may be passed from caller, else opens own connection
        self._owned_conn = None
        self._strong_sectors = None
        self._strong_industries = None
        self._market_breadth = None

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

    # ---------- Pre-load: market context computed once per run ----------

    def load_market_context(self, eval_date):
        """Pre-load the things every candidate needs to compare against."""
        self.connect()

        # Top sectors by momentum (skip the empty 'Benchmark' row)
        self.cur.execute(
            """
            SELECT sector_name, momentum_score
            FROM sector_ranking
            WHERE date_recorded = (
                SELECT MAX(date_recorded) FROM sector_ranking
                WHERE date_recorded <= %s
            )
            AND sector_name <> '' AND sector_name IS NOT NULL
            AND sector_name <> 'Benchmark'
            ORDER BY momentum_score DESC NULLS LAST
            """,
            (eval_date,),
        )
        sectors = self.cur.fetchall()
        top_n = int(self.config.get('strong_sector_top_n', 5))
        self._strong_sectors = {row[0]: float(row[1] or 0) for row in sectors[:top_n]}

        # Top industries by daily_strength_score (top quartile)
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
            self._strong_industries = {
                row[0]: float(row[1]) for row in industries[:cutoff_idx]
            }
        else:
            self._strong_industries = {}

        # Market breadth from AAII sentiment (latest)
        self.cur.execute(
            """
            SELECT bullish, bearish, neutral
            FROM aaii_sentiment
            WHERE date <= %s ORDER BY date DESC LIMIT 1
            """,
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

    # ---------- Per-candidate quality assessment ----------

    def evaluate_candidate(self, symbol, signal_date, entry_price, sector, industry):
        """Run all advanced filters for one candidate.

        Returns dict with:
          'pass': bool — hard-fail gates
          'reason': string for failure
          'composite_score': 0-100 weighted quality
          'components': dict of individual filter results
        """
        self.connect()
        components = {}
        score = 0.0
        max_score = 0.0
        hard_fail = None

        # F1. EARNINGS PROXIMITY (HARD FAIL)
        days_to_earnings = self._estimate_days_to_earnings(symbol, signal_date)
        components['days_to_earnings'] = days_to_earnings
        block_window = int(self.config.get('block_days_before_earnings', 5))
        if days_to_earnings is not None and 0 <= days_to_earnings <= block_window:
            hard_fail = f'Earnings in ~{days_to_earnings}d (block window {block_window}d)'

        # F2. SECTOR STRENGTH (SOFT — penalize but don't block by default)
        sector_pts, sector_max = self._score_sector_strength(sector)
        components['sector_strength'] = sector_pts
        score += sector_pts
        max_score += sector_max
        if self.config.get('require_strong_sector', False) and sector not in (self._strong_sectors or {}):
            hard_fail = hard_fail or f'Sector "{sector}" not in top {len(self._strong_sectors or {})}'

        # F3. INDUSTRY STRENGTH (SOFT)
        ind_pts, ind_max = self._score_industry_strength(industry)
        components['industry_strength'] = ind_pts
        score += ind_pts
        max_score += ind_max

        # F4. RELATIVE STRENGTH vs SPY
        rs_pts, rs_max, rs_value = self._score_relative_strength(symbol, signal_date)
        components['relative_strength'] = {'points': rs_pts, 'value': rs_value}
        score += rs_pts
        max_score += rs_max

        # F5. VOLUME CONFIRMATION
        vol_pts, vol_max, vol_ratio = self._score_volume_confirmation(symbol, signal_date)
        components['volume_confirmation'] = {'points': vol_pts, 'ratio': vol_ratio}
        score += vol_pts
        max_score += vol_max

        # F6. EXTENSION CHECK (% above 50-DMA) — high extension penalized
        ext_pts, ext_max, ext_pct = self._score_extension(symbol, signal_date, entry_price)
        components['extension'] = {'points': ext_pts, 'pct': ext_pct}
        score += ext_pts
        max_score += ext_max
        max_extension = float(self.config.get('max_extension_above_50ma_pct', 15.0))
        if ext_pct is not None and ext_pct > max_extension:
            hard_fail = hard_fail or f'{ext_pct:.1f}% above 50-DMA > {max_extension:.0f}% (over-extended)'

        # F7. ANALYST TREND
        an_pts, an_max, an_net = self._score_analyst_trend(symbol, signal_date)
        components['analyst_trend'] = {'points': an_pts, 'net_actions': an_net}
        score += an_pts
        max_score += an_max

        # F8. INSIDER ACTIVITY
        in_pts, in_max, in_net = self._score_insider_activity(symbol, signal_date)
        components['insider_activity'] = {'points': in_pts, 'net_value': in_net}
        score += in_pts
        max_score += in_max

        # F9. EARNINGS QUALITY
        eq_pts, eq_max = self._score_earnings_quality(symbol)
        components['earnings_quality'] = eq_pts
        score += eq_pts
        max_score += eq_max

        # F10. IBD-STYLE COMPOSITE (most important fundamental signal)
        ibd_pts, ibd_max, ibd_breakdown = self._score_ibd_composite(symbol)
        components['ibd_composite'] = {'points': ibd_pts, **ibd_breakdown}
        score += ibd_pts
        max_score += ibd_max

        # F11. QUALITY SCORE (financial health)
        qual_pts, qual_max, qual_val = self._score_quality(symbol)
        components['quality_score'] = {'points': qual_pts, 'value': qual_val}
        score += qual_pts
        max_score += qual_max

        # F12. VALUE TRAP CHECK (HARD FAIL on high trap risk)
        trap_pts, trap_max, trap_risk = self._score_value_trap(symbol)
        components['value_trap'] = {'points': trap_pts, 'trap_risk': trap_risk}
        score += trap_pts
        max_score += trap_max
        max_trap_risk = float(self.config.get('max_value_trap_risk', 75.0))
        if trap_risk is not None and trap_risk >= max_trap_risk:
            hard_fail = hard_fail or f'High value-trap risk: {trap_risk:.0f} >= {max_trap_risk:.0f}'

        # F13. GROWTH METRICS (real revenue & earnings growth)
        grw_pts, grw_max, grw_breakdown = self._score_growth(symbol)
        components['growth_metrics'] = {'points': grw_pts, **grw_breakdown}
        score += grw_pts
        max_score += grw_max

        composite_score = (score / max_score * 100.0) if max_score > 0 else 0.0
        return {
            'pass': hard_fail is None,
            'reason': hard_fail or 'all advanced gates passed',
            'composite_score': round(composite_score, 1),
            'components': components,
        }

    # ---------- Individual filter implementations ----------

    def _estimate_days_to_earnings(self, symbol, signal_date):
        """Earnings dates are sparse. Best estimate: latest quarter end + 45 days.

        If that estimated date is in the past, project forward by 90 days at a time
        until we get a future date (covers companies skipping a quarter).
        """
        self.cur.execute(
            "SELECT MAX(quarter) FROM earnings_history WHERE symbol = %s",
            (symbol,),
        )
        row = self.cur.fetchone()
        if not row or not row[0]:
            return None
        last_quarter_end = row[0]

        # Estimate next earnings ~45 days after quarter end (typical)
        est = last_quarter_end + timedelta(days=45)
        signal_d = signal_date if isinstance(signal_date, _date) else signal_date
        while est < signal_d:
            est += timedelta(days=90)
        return (est - signal_d).days

    def _score_sector_strength(self, sector):
        """Top sector → 10 pts, otherwise → 0 (max 10)."""
        if not sector or not self._strong_sectors:
            return 0.0, 10.0
        if sector in self._strong_sectors:
            momentum = self._strong_sectors[sector]
            sector_list = list(self._strong_sectors.keys())
            rank_idx = sector_list.index(sector)
            return 10.0 * (1.0 - (rank_idx / max(1, len(sector_list)))), 10.0
        return 0.0, 10.0

    def _score_industry_strength(self, industry):
        """Top-quartile industry → 10 pts (max 10)."""
        if not industry or not self._strong_industries:
            return 0.0, 10.0
        if industry in self._strong_industries:
            return 10.0, 10.0
        return 0.0, 10.0

    def _score_relative_strength(self, symbol, signal_date):
        """Mansfield RS via stock vs SPY 12-week return. Max 15 pts."""
        # Fetch stock 12-week return
        stock_ret = self._period_return(symbol, signal_date, 60)
        spy_ret = self._period_return('SPY', signal_date, 60)
        if stock_ret is None or spy_ret is None:
            return 0.0, 15.0, None
        rs_excess = stock_ret - spy_ret
        # Map: outperform by 30% = 15 pts, underperform = 0 pts
        pts = max(0.0, min(15.0, rs_excess * 50.0))  # 0.30 -> 15
        return pts, 15.0, round(rs_excess, 4)

    def _period_return(self, symbol, end_date, lookback_days):
        self.cur.execute(
            """
            WITH bracket AS (
                SELECT close,
                       ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                FROM price_daily
                WHERE symbol = %s AND date <= %s
                  AND date >= %s::date - INTERVAL '%s days'
            )
            SELECT
                (SELECT close FROM bracket WHERE rn = 1) AS recent,
                (SELECT close FROM bracket ORDER BY rn DESC LIMIT 1) AS oldest
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

    def _score_volume_confirmation(self, symbol, signal_date):
        """Today's volume vs 50d avg. Ratio >= 1.5 → max points (max 10)."""
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
            return 0.0, 10.0, None
        vol = float(row[0])
        avg = float(row[1])
        if avg <= 0:
            return 0.0, 10.0, None
        ratio = vol / avg
        # Linear up to 1.5x = full points
        pts = max(0.0, min(10.0, (ratio - 0.8) * 14.3))  # ratio 0.8 -> 0pts, 1.5 -> 10pts
        return pts, 10.0, round(ratio, 2)

    def _score_extension(self, symbol, signal_date, entry_price):
        """% above 50-DMA. 0-5% = full points, 5-10% = partial, >10% = 0. Max 10."""
        self.cur.execute(
            "SELECT sma_50 FROM technical_data_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
            (symbol, signal_date),
        )
        row = self.cur.fetchone()
        if not row or not row[0] or float(row[0]) <= 0:
            return 0.0, 10.0, None
        sma_50 = float(row[0])
        ext_pct = ((entry_price - sma_50) / sma_50) * 100.0
        if ext_pct <= 0:
            return 5.0, 10.0, round(ext_pct, 2)  # below 50ma = mediocre but not bad for swing
        if ext_pct <= 5:
            return 10.0, 10.0, round(ext_pct, 2)
        if ext_pct <= 10:
            return max(0.0, 10.0 - ((ext_pct - 5) * 2)), 10.0, round(ext_pct, 2)
        return 0.0, 10.0, round(ext_pct, 2)

    def _score_analyst_trend(self, symbol, signal_date):
        """Net upgrades-downgrades over last 90 days. Max 10."""
        self.cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE LOWER(action) IN ('up','upgrade')) AS ups,
                COUNT(*) FILTER (WHERE LOWER(action) IN ('down','downgrade')) AS downs
            FROM analyst_upgrade_downgrade
            WHERE symbol = %s
              AND action_date >= %s::date - INTERVAL '90 days'
              AND action_date <= %s
            """,
            (symbol, signal_date, signal_date),
        )
        row = self.cur.fetchone()
        if not row:
            return 0.0, 10.0, 0
        ups, downs = int(row[0] or 0), int(row[1] or 0)
        net = ups - downs
        # +5 net = max points; -3 = 0 points
        pts = max(0.0, min(10.0, (net + 3) * 1.25))
        return pts, 10.0, net

    def _score_insider_activity(self, symbol, signal_date):
        """Net insider buying $ over last 60 days. Max 10."""
        self.cur.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN LOWER(transaction_type) LIKE '%%buy%%' THEN value ELSE 0 END), 0) AS buys,
                COALESCE(SUM(CASE WHEN LOWER(transaction_type) LIKE '%%sale%%' OR LOWER(transaction_type) LIKE '%%sell%%' THEN value ELSE 0 END), 0) AS sells
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
            return 0.0, 10.0, 0
        buys = float(row[0] or 0)
        sells = float(row[1] or 0)
        net = buys - sells
        # >$500K net buying = max; net selling = 0
        if net <= 0:
            return 0.0, 10.0, net
        pts = min(10.0, (net / 500000.0) * 10.0)
        return pts, 10.0, net

    def _score_earnings_quality(self, symbol):
        """Use earnings_quality_score from earnings_metrics. Max 15."""
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
            return 0.0, 15.0
        score = float(row[0])
        return (score / 100.0) * 15.0, 15.0

    def _score_ibd_composite(self, symbol):
        """IBD-style composite from stock_scores. Max 20."""
        self.cur.execute(
            """
            SELECT composite_score, quality_score, growth_score, momentum_score
            FROM stock_scores WHERE symbol = %s LIMIT 1
            """,
            (symbol,),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None:
            return 0.0, 20.0, {'composite': None, 'grade': None}
        composite = float(row[0])
        pts = max(0.0, min(20.0, (composite - 40.0) * (20.0 / 50.0)))
        if composite >= 90:
            grade = 'A+'
        elif composite >= 80:
            grade = 'A'
        elif composite >= 70:
            grade = 'B'
        elif composite >= 60:
            grade = 'C'
        elif composite >= 50:
            grade = 'D'
        else:
            grade = 'F'
        return pts, 20.0, {
            'composite': round(composite, 1),
            'grade': grade,
            'quality': round(float(row[1] or 0), 1),
            'growth': round(float(row[2] or 0), 1),
            'momentum': round(float(row[3] or 0), 1),
        }

    def _score_quality(self, symbol):
        """Financial quality from stock_scores.quality_score. Max 10."""
        self.cur.execute(
            "SELECT quality_score FROM stock_scores WHERE symbol = %s LIMIT 1",
            (symbol,),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None:
            return 0.0, 10.0, None
        q = float(row[0])
        pts = max(0.0, min(10.0, (q - 50.0) * (10.0 / 30.0)))
        return pts, 10.0, round(q, 1)

    def _score_value_trap(self, symbol):
        """Value trap risk. trap_risk_score: 0-100, HIGHER = WORSE. Max 5 pts."""
        self.cur.execute(
            """SELECT trap_risk_score, balance_sheet_score FROM value_trap_scores
               WHERE symbol = %s LIMIT 1""",
            (symbol,),
        )
        row = self.cur.fetchone()
        if not row or row[0] is None:
            return 5.0, 5.0, None  # neutral if no data
        trap_risk = float(row[0])
        bs_score = float(row[1]) if row[1] is not None else 50.0
        risk_pts = max(0.0, min(5.0, (80.0 - trap_risk) / 60.0 * 5.0))
        if bs_score < 40:
            risk_pts *= 0.5
        return risk_pts, 5.0, round(trap_risk, 1)

    def _score_growth(self, symbol):
        """Real growth from growth_metrics. Max 15 pts.
        6 pts for EPS 3y CAGR > 20%, 6 pts for revenue 3y CAGR > 15%, 3 pts for positive momentum."""
        self.cur.execute(
            """
            SELECT revenue_growth_3y_cagr, eps_growth_3y_cagr,
                   quarterly_growth_momentum, revenue_growth_yoy
            FROM growth_metrics
            WHERE symbol = %s
            ORDER BY date DESC LIMIT 1
            """,
            (symbol,),
        )
        row = self.cur.fetchone()
        if not row:
            return 0.0, 15.0, {}
        rev_3y = float(row[0]) if row[0] is not None else 0.0
        eps_3y = float(row[1]) if row[1] is not None else 0.0
        mom = float(row[2]) if row[2] is not None else 0.0
        rev_yoy = float(row[3]) if row[3] is not None else 0.0

        eps_pts = max(0.0, min(6.0, (eps_3y / 20.0) * 6.0)) if eps_3y > 0 else 0.0
        rev_pts = max(0.0, min(6.0, (rev_3y / 15.0) * 6.0)) if rev_3y > 0 else 0.0
        mom_pts = 3.0 if mom > 0 else 0.0
        total = eps_pts + rev_pts + mom_pts

        return total, 15.0, {
            'eps_3y_cagr': round(eps_3y, 1),
            'revenue_3y_cagr': round(rev_3y, 1),
            'revenue_yoy': round(rev_yoy, 1),
            'momentum': round(mom, 1),
        }


if __name__ == "__main__":
    from algo_config import get_config
    f = AdvancedFilters(get_config())
    ctx = f.load_market_context(_date(2026, 4, 24))
    print("Strong sectors:", ctx['strong_sectors'])
    print("Strong industries:", ctx['strong_industries_count'])
    print("Market breadth:", ctx['market_breadth'])

    # Test on a known qualified symbol
    result = f.evaluate_candidate('LRCX', _date(2026, 4, 24), 273.50,
                                   'Technology', 'Semiconductor Equipment & Materials')
    print("\nLRCX evaluation:")
    print(f"  pass: {result['pass']}, reason: {result['reason']}")
    print(f"  composite_score: {result['composite_score']}/100")
    for k, v in result['components'].items():
        print(f"  {k}: {v}")

    f.disconnect()
