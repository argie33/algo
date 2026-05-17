#!/usr/bin/env python3

"""
Quantitative Market Exposure Engine - Research-backed 11-factor composite

Replaces simple "Stage 2 yes/no" gating with a 0-100 portfolio risk allocation
score driven by these inputs (weights from synthesis of IBD, O'Neil, Weinstein,
Zweig, AAII/NAAIM contrarian, Schwab/Fidelity breadth research, Apollo/Goldman
credit cycle research):

    18pt  IBD MARKET STATE      Confirmed Uptrend / Pressure / Correction
    15pt  TREND 30-WK MA        SPY price vs rising/flat/falling 30-week MA
    14pt  BREADTH % > 50-DMA    short-term participation (linear 20-80%)
    10pt  BREADTH % > 200-DMA   longer-term health (linear 30-80%)
     9pt  MCCLELLAN OSCILLATOR  short-term momentum (-100 to +100 zone)
     8pt  VIX REGIME            <15 / 15-25 / 25-35 / 35+
     7pt  NEW HIGHS - LOWS      regime health indicator
     7pt  CREDIT SPREADS        HY OAS (BAMLH0A0HYM2) - credit leads equity
     5pt  ADVANCE-DECLINE LINE  confirmation / divergence vs index
     4pt  AAII SENTIMENT        contrarian: extreme bullish = caution
     3pt  NAAIM EXPOSURE        professional manager positioning (0-200 scale)

PLUS HARD VETOES (cap at ≤25-35%):
  - SPY < rising 30-wk MA AND breadth_50 < 30%
  - VIX > 40 with rising trend
  - 6+ distribution days in last 25 sessions
  - No follow-through day after correction
  - HY credit spread > 8.5% (systemic stress)

PLUS ECONOMIC REGIME OVERLAY (penalty, not a factor):
  - Computed from: T10Y2Y yield curve, HY spread trend, jobless claims trend
  - Macro stress 40-60: -4pts
  - Macro stress > 60: -7pts, cap at 40%

Output:
    market_exposure_pct (0-100): drives dynamic risk allocation
    state: 'confirmed_uptrend' | 'uptrend_under_pressure' | 'correction'
    factors: dict of each input + sub-score
    halt_reasons: list of any active hard vetoes

Persists daily to market_exposure_daily table for dashboard / audit.
"""

from config.credential_helper import get_db_config
from config.env_loader import load_env
from config.credential_helper import get_db_password, get_db_config

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
import json
import logging
from utils.db_connection import get_db_connection
from pathlib import Path
from datetime import date as _date

logger = logging.getLogger(__name__)

