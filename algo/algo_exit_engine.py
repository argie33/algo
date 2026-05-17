#!/usr/bin/env python3

"""
Exit Engine - Monitor positions and execute exits (HARDENED)

Exit hierarchy (checked in order):
1. STOP    — current price <= active stop (initial or trailed)
2. MINERVINI BREAK — close < 21-EMA on volume > 50d avg (or close < 50-DMA cleanly)
3. TIME    — held >= max_hold_days
4. T3      — price >= target_3 (4R) → exit final 25%
5. T2      — price >= target_2 (3R) → exit 25% on pullback, raise stop to T1 area
6. T1      — price >= target_1 (1.5R) → exit 50% on pullback, raise stop to entry (breakeven)
7. CHANDELIER TRAIL — 3×ATR from highest high (or 21-EMA after 10d)
8. TD SEQUENTIAL — 9-count (50%) or 13-count (100%) exhaustion
9. FIRST RED DAY — after 2.5R+ gain, first big down day on heavy volume → exit 50%
10. CLIMAX RUN EXHAUSTION — 30+ days, 5R+ gain, 20%+ in last 10d → exit 50%
11. DISTRIBUTION — market distribution day count exceeds limit (config-gated)

State tracked on algo_positions:
  - target_levels_hit (0/1/2/3): which T-levels have already triggered
  - current_stop_price: trailed stop after T1/T2 hits
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
from utils.db_connection import get_db_connection
from pathlib import Path
from datetime import datetime, timedelta, date as _date
try:
    from trade_performance_auditor import TradePerformanceAuditor
except ImportError:
    TradePerformanceAuditor = None
from algo.algo_trade_executor import TradeExecutor
from algo.algo_signals import SignalComputer
from utils.trade_status import TradeStatus, PositionStatus
import logging
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)

