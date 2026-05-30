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

from algo.signals.signal_base import SignalBase
from algo.signals.signal_trend import SignalTrendMixin
from algo.signals.signal_patterns import SignalPatternsMixin
from algo.signals.signal_momentum import SignalMomentumMixin
from algo.signals.signal_options import SignalOptionsMixin

from datetime import date as _date
import logging

logger = logging.getLogger(__name__)

class SignalComputer(SignalBase, SignalTrendMixin, SignalPatternsMixin,
                     SignalMomentumMixin, SignalOptionsMixin):
    """All technical signals via mixin composition."""
    pass

if __name__ == "__main__":
    from utils.database_context import DatabaseContext

    s = SignalComputer()
    with DatabaseContext('read') as cur:
        s.cur = cur  # Temporarily set for test script
        eval_date = _date(2026, 4, 24)
        for sym in ('AROC', 'NBHC', 'EW', 'LRCX', 'NVDA', 'AAPL'):
            logger.info(f"\n{'='*70}\n{sym}\n{'='*70}")
            mt = s.minervini_trend_template(sym, eval_date)
            logger.info(f"\nMinervini 8-Pt Trend Template: score={mt['score']}/8, pass={mt['pass']}")
            for k, v in mt['criteria'].items():
                if not k.startswith('_'):
                    logger.info(f"   {k:42s} : {v}")
                else:
                    logger.info(f"   ({k:40s}: {v})")

            ws = s.weinstein_stage(sym, eval_date)
            logger.info(f"Weinstein Stage: {ws.get('stage')} (slope={ws.get('slope_pct', 0):+.2f}%, "
                  f"price_vs_ma={ws.get('price_vs_ma_pct', 0):+.2f}%, conf={ws.get('confidence', 0)})")

            bd = s.base_detection(sym, eval_date)
            logger.info(f"Base Detection: in_base={bd.get('in_base')}, "
                  f"depth={bd.get('base_depth_pct')}%, weeks={bd.get('weeks_in_base')}, "
                  f"pivot=${bd.get('pivot_high')}, breakout_imminent={bd.get('breakout_imminent')}, "
                  f"volume_dryup={bd.get('volume_dryup')}")

            td = s.td_sequential(sym, eval_date)
            logger.info(f"TD Sequential: count={td['setup_count']}, type={td['setup_type']}, "
                  f"completed_9={td['completed_9']}, perfected={td['perfected']}")

            vcp = s.vcp_detection(sym, eval_date)
            logger.info(f"VCP: is_vcp={vcp.get('is_vcp')}, contractions={vcp.get('contractions')}, "
                  f"depths={vcp.get('depth_progression')}, tight={vcp.get('tight_pattern')}")

            pt = s.power_trend(sym, eval_date)
            logger.info(f"\nPower Trend: {pt}")

            rs = s.mansfield_rs(sym, eval_date)
            logger.info(f"Mansfield RS: {rs}")

            pivot = s.pivot_breakout(sym, eval_date)
            logger.info(f"Pivot breakout: {pivot}")

            dd = s.distribution_days(sym, eval_date)
            logger.info(f"Distribution days (last 20): {dd}")
