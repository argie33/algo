#!/usr/bin/env python3
"""
Swing Trading Algo - Filter Pipeline (HARDENED)

5-tier filtering system to identify trade-worthy signals:
Tier 1: Data quality gates (completeness, price floor, recent data)
Tier 2: Market health gates (stage 2 uptrend, distribution days, VIX)
Tier 3: Trend template confirmation (Minervini 8-pt, distance from 52w hi/lo)
Tier 4: Signal quality scores (composite SQS ranking)
Tier 5: Portfolio health (open positions, concentration, sector limits)

Only signals passing ALL tiers reach the final trade list, ranked by SQS.
"""

from config.credential_helper import get_db_config
from config.env_loader import load_env
import os
from utils.db_connection import get_db_connection
from pathlib import Path
from datetime import datetime, timedelta, date as _date
from typing import Dict, List, Any, Optional, Tuple
from config.credential_helper import get_db_password, get_db_config
from algo.algo_config import get_config
from algo.algo_advanced_filters import AdvancedFilters
from algo.algo_swing_score import SwingTraderScore
from utils.filter_rejection_tracker import RejectionTracker
from algo.algo_earnings_blackout import EarningsBlackout
from algo.algo_trendline_support import TrendlineSupport
from utils.trade_status import PositionStatus
from utils.feature_flags import get_flags
import logging

logger = logging.getLogger(__name__)

