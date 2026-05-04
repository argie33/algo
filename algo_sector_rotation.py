#!/usr/bin/env python3
"""
Sector Rotation Detector — defensive leadership early warning

Mansfield RS rotation research and IBD's leadership-rotation studies show
that defensive sectors (Utilities, Consumer Staples, Healthcare) typically
begin outperforming SPY 1-3 months BEFORE major market tops, while the
cyclical "risk-on" sectors (Technology, Consumer Discretionary,
Communication, Industrials) start lagging.

This module:
  1. Computes sector RS vs SPY over 4w/12w windows
  2. Identifies if defensive leadership is taking hold
  3. Returns severity score (0-100) for orchestrator/exposure to consume
  4. Persists to sector_rotation_signal table

When defensive_lead_score >= 60, the market exposure model reduces the
composite score by 5-10 points (handled in algo_market_exposure.py).
"""

import os
import psycopg2
import json
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date as _date

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

# Sector classifications (Mansfield/IBD)
DEFENSIVE_SECTORS = ['Utilities', 'Consumer Defensive', 'Healthcare']
CYCLICAL_SECTORS  = ['Technology', 'Consumer Cyclical', 'Communication Services',
                     'Industrials', 'Financial Services']

# Sector ETF proxies (for Mansfield-style RS computation)
SECTOR_ETF = {
    'Utilities': 'XLU', 'Consumer Defensive': 'XLP', 'Healthcare': 'XLV',
    'Technology': 'XLK', 'Consumer Cyclical': 'XLY',
    'Communication Services': 'XLC', 'Industrials': 'XLI',
    'Financial Services': 'XLF', 'Energy': 'XLE',
    'Basic Materials': 'XLB', 'Real Estate': 'XLRE',
}


class SectorRotationDetector:
    """Detect defensive sector leadership patterns."""

    def __init__(self, config=None):
        self.config = config
        self.conn = None
        self.cur = None

    def connect(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()
        # Note: sector_rotation_signal table created by init_database.py (schema as code)

    def disconnect(self):
        if self.cur: self.cur.close()
        if self.conn: self.conn.close()
        self.cur = self.conn = None

    def compute(self, eval_date=None):
        """Run sector rotation analysis for the eval_date.

        Uses sector_ranking table (we don't have sector ETF price history).
        Lower rank = stronger sector. We measure: how have defensive sectors'
        ranks improved vs cyclicals' over 4 weeks.
        """
        if eval_date is None:
            eval_date = _date.today()
        self.connect()

        try:
            # Get latest sector ranking for all sectors
            self.cur.execute(
                """
                SELECT sector_name, current_rank, momentum_score,
                       rank_1w_ago, rank_4w_ago, rank_12w_ago
                FROM sector_ranking
                WHERE date_recorded = (
                    SELECT MAX(date_recorded) FROM sector_ranking
                    WHERE date_recorded <= %s
                )
                AND sector_name <> '' AND sector_name IS NOT NULL
                AND sector_name <> 'Benchmark'
                """,
                (eval_date,),
            )
            rows = self.cur.fetchall()
            sector_data = {}
            for sector_name, rank, momentum, r1w, r4w, r12w in rows:
                if rank is None:
                    continue
                rank = int(rank)
                # Improvement = rank getting smaller is better
                # rank went from 8 (4w ago) to 3 (now) = improved by +5
                imp_4w = (int(r4w) - rank) if r4w else 0
                imp_12w = (int(r12w) - rank) if r12w else 0
                imp_1w = (int(r1w) - rank) if r1w else 0

                sector_data[sector_name] = {
                    'rank': rank,
                    'momentum': float(momentum or 0),
                    'rank_improvement_1w': imp_1w,
                    'rank_improvement_4w': imp_4w,
                    'rank_improvement_12w': imp_12w,
                    'is_defensive': sector_name in DEFENSIVE_SECTORS,
                    'is_cyclical': sector_name in CYCLICAL_SECTORS,
                }

            # Compute averages from rank improvement (positive = strengthening)
            defensive = [d for d in sector_data.values() if d['is_defensive']]
            cyclical = [d for d in sector_data.values() if d['is_cyclical']]

            if not defensive or not cyclical:
                return None

            # Average rank improvement over 4 weeks. Defensive improving + cyclical
            # weakening = bearish rotation.
            def_imp_4w = sum(d['rank_improvement_4w'] for d in defensive) / len(defensive)
            cyc_imp_4w = sum(d['rank_improvement_4w'] for d in cyclical) / len(cyclical)
            spread = def_imp_4w - cyc_imp_4w  # positive spread = defensive leadership

            def_avg_momentum = sum(d['momentum'] for d in defensive) / len(defensive)
            cyc_avg_momentum = sum(d['momentum'] for d in cyclical) / len(cyclical)
            momentum_spread = def_avg_momentum - cyc_avg_momentum

            # Score: spread of +3 ranks over 4w = warning, +6 = severe
            defensive_lead_score = max(0, min(100, spread * 15 + 50))

            cyclical_weak_score = max(0, min(100, -cyc_imp_4w * 15 + 50))

            # Persistence not easily computable without historical sector_ranking
            # snapshots — approximate from 1w + 4w + 12w improvement direction
            weeks_persistent = sum([
                1 if (sum(d['rank_improvement_1w'] for d in defensive) / len(defensive)) >
                     (sum(d['rank_improvement_1w'] for d in cyclical) / len(cyclical)) else 0,
                1 if def_imp_4w > cyc_imp_4w else 0,
                1 if (sum(d['rank_improvement_12w'] for d in defensive) / len(defensive)) >
                     (sum(d['rank_improvement_12w'] for d in cyclical) / len(cyclical)) else 0,
            ])

            # Signal classification
            if defensive_lead_score >= 75 and weeks_persistent >= 3:
                signal = 'severe_defensive_rotation'
            elif defensive_lead_score >= 60 and weeks_persistent >= 2:
                signal = 'defensive_rotation_warning'
            elif defensive_lead_score >= 50:
                signal = 'mild_defensive_lead'
            elif def_imp_4w < cyc_imp_4w - 3:
                signal = 'risk_on_confirmed'
            else:
                signal = 'neutral'

            result = {
                'eval_date': str(eval_date),
                'signal': signal,
                'defensive_lead_score': round(defensive_lead_score, 1),
                'cyclical_weak_score': round(cyclical_weak_score, 1),
                'defensive_rank_improvement_4w': round(def_imp_4w, 2),
                'cyclical_rank_improvement_4w': round(cyc_imp_4w, 2),
                'spread_4w': round(spread, 2),
                'momentum_spread': round(momentum_spread, 2),
                'weeks_persistent': weeks_persistent,
                'sector_data': sector_data,
                'reduce_exposure_pts': self._exposure_penalty(defensive_lead_score, weeks_persistent),
            }
            self._persist(eval_date, result)
            return result
        finally:
            self.disconnect()

    def log_phase_result_skip(self):
        pass

    def _exposure_penalty(self, lead_score, weeks):
        """Recommend market exposure reduction in pts based on signal severity."""
        if lead_score >= 75 and weeks >= 3:
            return 10  # severe — reduce 10 pts
        if lead_score >= 60 and weeks >= 2:
            return 5   # warning — reduce 5 pts
        if lead_score >= 50:
            return 2   # mild — reduce 2 pts
        return 0

    def _period_return(self, symbol, end_date, lookback_days):
        self.cur.execute(
            """
            WITH bracket AS (
                SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                FROM price_daily
                WHERE symbol = %s AND date <= %s
                  AND date >= %s::date - INTERVAL '%s days'
            )
            SELECT (SELECT close FROM bracket WHERE rn = 1),
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

    def _compute_persistence(self, eval_date):
        """Count weeks (last 4) where defensive avg outperformed cyclical avg."""
        weeks = 0
        for w in range(4):
            check_date = eval_date - (eval_date.resolution * (w * 7) if False else
                                       _date.fromisoformat(str(eval_date)).__class__.fromordinal(
                                           eval_date.toordinal() - w * 7))
            check_date = _date.fromordinal(eval_date.toordinal() - w * 7)
            try:
                spy_4w = self._period_return('SPY', check_date, 20)
                if spy_4w is None:
                    continue
                def_excess = []
                cyc_excess = []
                for sec in DEFENSIVE_SECTORS:
                    etf = SECTOR_ETF.get(sec)
                    if not etf: continue
                    r = self._period_return(etf, check_date, 20)
                    if r is None: continue
                    def_excess.append(r - spy_4w)
                for sec in CYCLICAL_SECTORS:
                    etf = SECTOR_ETF.get(sec)
                    if not etf: continue
                    r = self._period_return(etf, check_date, 20)
                    if r is None: continue
                    cyc_excess.append(r - spy_4w)
                if def_excess and cyc_excess:
                    if sum(def_excess) / len(def_excess) > sum(cyc_excess) / len(cyc_excess):
                        weeks += 1
            except Exception:
                pass
        return weeks

    def _persist(self, eval_date, result):
        try:
            self.cur.execute(
                """INSERT INTO sector_rotation_signal
                   (date, defensive_lead_score, cyclical_weak_score, signal,
                    defensive_avg_rs, cyclical_avg_rs, spread, weeks_persistent, details)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (date) DO UPDATE SET
                       defensive_lead_score = EXCLUDED.defensive_lead_score,
                       cyclical_weak_score = EXCLUDED.cyclical_weak_score,
                       signal = EXCLUDED.signal,
                       defensive_avg_rs = EXCLUDED.defensive_avg_rs,
                       cyclical_avg_rs = EXCLUDED.cyclical_avg_rs,
                       spread = EXCLUDED.spread,
                       weeks_persistent = EXCLUDED.weeks_persistent,
                       details = EXCLUDED.details""",
                (eval_date, result['defensive_lead_score'], result['cyclical_weak_score'],
                 result['signal'], result['defensive_rank_improvement_4w'],
                 result['cyclical_rank_improvement_4w'],
                 result['spread_4w'], result['weeks_persistent'], json.dumps(result['sector_data'])),
            )
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"  (persist sector_rotation skipped: {e})")


if __name__ == "__main__":
    d = SectorRotationDetector()
    result = d.compute(_date(2026, 4, 24))
    if result:
        print(f"\n{'='*70}\nSECTOR ROTATION — {result['eval_date']}\n{'='*70}\n")
        print(f"  Signal:               {result['signal']}")
        print(f"  Defensive lead score: {result['defensive_lead_score']}/100")
        print(f"  Cyclical weak score:  {result['cyclical_weak_score']}/100")
        print(f"  Defensive avg RS 4w:  {result['defensive_avg_rs_4w']}%")
        print(f"  Cyclical avg RS 4w:   {result['cyclical_avg_rs_4w']}%")
        print(f"  Spread:               {result['spread_4w']}%")
        print(f"  Weeks persistent:     {result['weeks_persistent']}/4")
        print(f"  Recommended exp drop: {result['reduce_exposure_pts']} pts")
        print(f"\n  Per-sector RS:")
        for sec, d in sorted(result['sector_data'].items(),
                              key=lambda x: x[1]['rs_excess_4w'], reverse=True):
            tag = '[DEF]' if d['is_defensive'] else '[CYC]' if d['is_cyclical'] else '[   ]'
            print(f"    {tag} {sec:25s} {d['etf']:5s}  RS_4w={d['rs_excess_4w']:+6.2f}%  RS_12w={d['rs_excess_12w']:+6.2f}%")
