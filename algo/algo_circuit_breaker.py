#!/usr/bin/env python3

"""
Circuit Breakers - Kill-switch risk halts (institutional safety layer)

Halts trading when any of these fire:
  CB1. PORTFOLIO DRAWDOWN  >= halt_drawdown_pct (default 20%)
  CB2. DAILY LOSS          >= max_daily_loss_pct (default 2%)
  CB3. CONSECUTIVE LOSSES  >= max_consecutive_losses (default 3)
  CB4. TOTAL OPEN RISK     >= max_total_risk_pct (default 4%)
  CB5. VIX SPIKE           > vix_max_threshold (default 35)
  CB6. MARKET STAGE BREAK  market_stage = 4 (downtrend)
  CB7. WEEKLY LOSS         >= max_weekly_loss_pct (default 5%)
  CB8. DATA STALENESS      latest data > N days old

Each check returns (halted, reason). The orchestrator runs all checks before
new entries — any halt blocks new positions but does NOT auto-exit existing
ones (those are managed by exit_engine + position_monitor).

When a circuit breaker fires:
  - logged in algo_audit_log with action_type='circuit_breaker'
  - returned to caller for display / notification
  - persists state until cleared (e.g., recovery threshold met)
"""

from config.env_loader import load_env
from config.credential_helper import get_db_password, get_db_config

import os
import json
from utils.db_connection import get_db_connection
from pathlib import Path
from datetime import datetime, timedelta, date as _date
from typing import Dict, Any, List, Tuple, Optional
from utils.trade_status import TradeStatus, PositionStatus
import logging

logger = logging.getLogger(__name__)

