#!/usr/bin/env python3
"""
Market Exposure Action Policy - Maps exposure score to concrete actions

The market exposure score (0-100, computed by algo_market_exposure.py) is
useless without a clear policy of what each level MEANS for our portfolio.

Per Minervini, Tharp, O'Neil best practices:
  - Don't blindly panic-sell when exposure drops; each position has its own stop.
  - DO progressively de-risk via stop tightening, partial-profit acceleration,
    and stricter entry gates.
  - At extreme low exposure (correction), DO actively reduce — cut losers
    rather than waiting for stops, take all partials.

5 Regime Tiers:

  CONFIRMED_UPTREND   80-100   Full risk, normal entries, hold winners
  HEALTHY_UPTREND     60-80    Slight risk reduction, tighten extended winners
  PRESSURE            40-60    50% risk, raise quality bar to A, take partials
  CAUTION             20-40    25% risk, halt entries, tighten all stops
  CORRECTION           0-20    No new entries, force-exit losers, take all profits

Each tier has a complete action profile that the orchestrator applies
in Phase 2.5 (between circuit breakers and position monitor).
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


# Each policy tier defines:
#   risk_multiplier:        Multiplier on base_risk_pct (× drawdown × phase)
#   max_new_positions_today: Cap on new entries per day
#   min_swing_score:        Required score for a new entry
#   min_swing_grade:        Required letter grade
#   tighten_winners_at_r:   Tighten stop when position > this R-multiple
#   force_partial_at_r:     Force partial exit when position > this R
#   halt_new_entries:       Block all new positions
#   force_exit_negative_r:  Cut losers (negative R) instead of waiting for stop
#   max_concentration_pct:  Override max single-position concentration
EXPOSURE_TIERS = [
    {
        'name': 'confirmed_uptrend',
        'min_pct': 80,
        'max_pct': 100,
        'description': 'Healthy bull market — full deployment',
        'risk_multiplier': 1.0,
        'max_new_positions_today': 5,
        'min_swing_score': 60.0,
        'min_swing_grade': 'B',
        'tighten_winners_at_r': None,
        'force_partial_at_r': None,
        'halt_new_entries': False,
        'force_exit_negative_r': False,
        'max_concentration_pct': 50.0,
        'color': 'green',
    },
    {
        'name': 'healthy_uptrend',
        'min_pct': 60,
        'max_pct': 80,
        'description': 'Bull market with caution — slightly reduced risk',
        'risk_multiplier': 0.85,
        'max_new_positions_today': 4,
        'min_swing_score': 65.0,
        'min_swing_grade': 'B',
        'tighten_winners_at_r': 3.0,
        'force_partial_at_r': None,
        'halt_new_entries': False,
        'force_exit_negative_r': False,
        'max_concentration_pct': 45.0,
        'color': 'lightgreen',
    },
    {
        'name': 'pressure',
        'min_pct': 40,
        'max_pct': 60,
        'description': 'Uptrend under pressure — defensive posture',
        'risk_multiplier': 0.5,
        'max_new_positions_today': 2,
        'min_swing_score': 70.0,
        'min_swing_grade': 'A',
        'tighten_winners_at_r': 2.0,
        'force_partial_at_r': 3.0,
        'halt_new_entries': False,
        'force_exit_negative_r': False,
        'max_concentration_pct': 35.0,
        'color': 'yellow',
    },
    {
        'name': 'caution',
        'min_pct': 20,
        'max_pct': 40,
        'description': 'Major caution — entries halted unless exceptional',
        'risk_multiplier': 0.25,
        'max_new_positions_today': 1,
        'min_swing_score': 75.0,
        'min_swing_grade': 'A',
        'tighten_winners_at_r': 1.5,
        'force_partial_at_r': 2.0,
        'halt_new_entries': True,
        'force_exit_negative_r': False,
        'max_concentration_pct': 25.0,
        'color': 'orange',
    },
    {
        'name': 'correction',
        'min_pct': 0,
        'max_pct': 20,
        'description': 'Market correction — preserve capital',
        'risk_multiplier': 0.0,
        'max_new_positions_today': 0,
        'min_swing_score': 100.0,
        'min_swing_grade': 'A+',
        'tighten_winners_at_r': 1.0,
        'force_partial_at_r': 1.5,
        'halt_new_entries': True,
        'force_exit_negative_r': True,
        'max_concentration_pct': 15.0,
        'color': 'red',
    },
]


def tier_for_exposure(exposure_pct):
    """Return the active policy tier for a given exposure %."""
    for tier in EXPOSURE_TIERS:
        if tier['min_pct'] <= exposure_pct <= tier['max_pct']:
            return tier
    # Fallback: clip
    if exposure_pct < 0:
        return EXPOSURE_TIERS[-1]
    return EXPOSURE_TIERS[0]


class ExposurePolicy:
    """Apply market exposure tier policies to portfolio state."""

    def __init__(self, config=None):
        self.config = config
        self.conn = None
        self.cur = None

    def connect(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def get_active_tier(self, eval_date=None):
        """Look up the most recent exposure score and return its policy tier."""
        if eval_date is None:
            eval_date = _date.today()
        self.connect()
        try:
            self.cur.execute(
                """SELECT date, exposure_pct, regime, halt_reasons FROM market_exposure_daily
                   WHERE date <= %s ORDER BY date DESC LIMIT 1""",
                (eval_date,),
            )
            row = self.cur.fetchone()
            if not row:
                return None
            exposure = float(row[1])
            tier = tier_for_exposure(exposure)
            return {
                'as_of_date': row[0].isoformat(),
                'exposure_pct': exposure,
                'regime': row[2],
                'halt_reasons': row[3],
                'tier': tier,
            }
        finally:
            self.disconnect()

    def review_existing_positions(self, eval_date=None):
        """Apply tier policy to all open positions.

        Returns list of recommended actions per position:
          { trade_id, symbol, action, reason, new_stop, exit_fraction }

        Actions are recommendations — orchestrator decides whether to execute.
        """
        active = self.get_active_tier(eval_date)
        if not active:
            return []

        tier = active['tier']
        if eval_date is None:
            eval_date = _date.today()

        self.connect()
        try:
            self.cur.execute(
                """
                SELECT t.trade_id, t.symbol, t.entry_price, t.stop_loss_price,
                       t.target_1_price, t.target_2_price, t.target_3_price,
                       t.trade_date,
                       p.position_id, p.quantity, p.target_levels_hit,
                       p.current_stop_price, p.current_price,
                       p.unrealized_pnl_pct
                FROM algo_trades t
                JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
                WHERE t.status IN ('filled','active') AND p.status = 'open' AND p.quantity > 0
                """
            )
            positions = self.cur.fetchall()
            actions = []
            for row in positions:
                action = self._evaluate_position(row, tier, active, eval_date)
                if action and action['action'] != 'hold':
                    actions.append(action)
            return actions
        finally:
            self.disconnect()

    def _evaluate_position(self, row, tier, active, eval_date):
        (trade_id, symbol, entry_price, init_stop, t1_price, t2_price, t3_price,
         trade_date, position_id, qty, target_hits, cur_stop, cur_price, pnl_pct) = row

        entry_price = float(entry_price)
        init_stop = float(init_stop)
        active_stop = float(cur_stop) if cur_stop else init_stop
        target_hits = int(target_hits or 0)
        cur_price = float(cur_price) if cur_price else entry_price

        # R-multiple
        risk_per_share = entry_price - init_stop
        r_mult = ((cur_price - entry_price) / risk_per_share) if risk_per_share > 0 else 0

        # 1. CORRECTION TIER + force_exit_negative_r: cut losers
        if tier.get('force_exit_negative_r') and r_mult < 0:
            return {
                'trade_id': trade_id, 'symbol': symbol, 'position_id': position_id,
                'action': 'force_exit',
                'reason': f"Tier '{tier['name']}': force-exit losers (R={r_mult:.2f})",
                'exit_fraction': 1.0,
                'new_stop': None,
                'r_multiple': r_mult,
                'tier': tier['name'],
            }

        # 2. force_partial_at_r: take partial profits when extended
        if tier.get('force_partial_at_r') and r_mult >= tier['force_partial_at_r']:
            # Only if not already hit a target at this level
            if target_hits < 2:  # haven't taken T2 yet
                return {
                    'trade_id': trade_id, 'symbol': symbol, 'position_id': position_id,
                    'action': 'partial_exit',
                    'reason': (f"Tier '{tier['name']}' force partial: R={r_mult:.2f} >= "
                               f"{tier['force_partial_at_r']}R threshold"),
                    'exit_fraction': 0.50,
                    'new_stop': max(active_stop, entry_price),  # raise to BE at minimum
                    'r_multiple': r_mult,
                    'tier': tier['name'],
                }

        # 3. tighten_winners_at_r: ratchet stop tighter on extended positions
        if tier.get('tighten_winners_at_r') and r_mult >= tier['tighten_winners_at_r']:
            # Compute a tightened stop: midway between entry and current price
            # but never lower than current active stop
            tightened = entry_price + (cur_price - entry_price) * 0.50  # halfway
            tightened = max(active_stop, tightened)
            if tightened > active_stop * 1.005:  # only if meaningfully higher
                return {
                    'trade_id': trade_id, 'symbol': symbol, 'position_id': position_id,
                    'action': 'tighten_stop',
                    'reason': (f"Tier '{tier['name']}' tighten: R={r_mult:.2f} >= "
                               f"{tier['tighten_winners_at_r']}R, raise stop"),
                    'exit_fraction': 0.0,
                    'new_stop': round(tightened, 2),
                    'r_multiple': r_mult,
                    'tier': tier['name'],
                }

        return {'action': 'hold', 'symbol': symbol, 'r_multiple': r_mult}

    def get_entry_constraints(self, eval_date=None):
        """Return current constraints for new entries."""
        active = self.get_active_tier(eval_date)
        if not active:
            return None
        tier = active['tier']
        return {
            'as_of_date': active['as_of_date'],
            'exposure_pct': active['exposure_pct'],
            'regime': active['regime'],
            'tier_name': tier['name'],
            'description': tier['description'],
            'risk_multiplier': tier['risk_multiplier'],
            'max_new_positions_today': tier['max_new_positions_today'],
            'min_swing_score': tier['min_swing_score'],
            'min_swing_grade': tier['min_swing_grade'],
            'halt_new_entries': tier['halt_new_entries'],
            'max_concentration_pct': tier['max_concentration_pct'],
        }


if __name__ == "__main__":
    p = ExposurePolicy()
    active = p.get_active_tier()
    print("=" * 80)
    print("MARKET EXPOSURE POLICY")
    print("=" * 80)
    if active:
        print(f"\nAs of: {active['as_of_date']}")
        print(f"Exposure: {active['exposure_pct']}%")
        print(f"Regime:   {active['regime']}")
        if active.get('halt_reasons'):
            print(f"HALT:     {active['halt_reasons']}")
        print(f"\nActive Tier: {active['tier']['name']} ({active['tier']['min_pct']}-{active['tier']['max_pct']}%)")
        print(f"  {active['tier']['description']}")
        print(f"\nEntry Constraints:")
        constraints = p.get_entry_constraints()
        for k, v in constraints.items():
            if k not in ('as_of_date', 'tier_name', 'description'):
                print(f"  {k:30s} = {v}")
    else:
        print("\nNo market exposure data — run algo_market_exposure.py first")

    actions = p.review_existing_positions()
    print(f"\n\nPosition Review: {len(actions)} actions recommended")
    for a in actions:
        print(f"  {a['symbol']:6s} → {a['action'].upper():15s}  R={a.get('r_multiple', 0):+.2f}  "
              f"{a['reason']}")
        if a.get('new_stop'):
            print(f"            new_stop=${a['new_stop']:.2f}")

    print("\n" + "=" * 80)
    print("ALL TIER DEFINITIONS")
    print("=" * 80)
    for tier in EXPOSURE_TIERS:
        print(f"\n{tier['name'].upper():20s} {tier['min_pct']:>3}-{tier['max_pct']:>3}%")
        print(f"  {tier['description']}")
        print(f"  risk_mult={tier['risk_multiplier']}, max_new/day={tier['max_new_positions_today']}, "
              f"min_grade={tier['min_swing_grade']}")
        if tier.get('tighten_winners_at_r'):
            print(f"  tighten winners @ +{tier['tighten_winners_at_r']}R")
        if tier.get('force_partial_at_r'):
            print(f"  force partial @ +{tier['force_partial_at_r']}R")
        if tier.get('halt_new_entries'):
            print(f"  HALT NEW ENTRIES")
        if tier.get('force_exit_negative_r'):
            print(f"  FORCE EXIT LOSERS")
