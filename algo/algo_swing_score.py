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
    - Trend Template score < 5 (Minervini 8-point; allows diverse candidates)
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
from utils.db_connection import get_db_connection
import logging
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Dict, Tuple, Any, Optional
from algo.algo_signals import SignalComputer

logger = logging.getLogger(__name__)

