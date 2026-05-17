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
from pathlib import Path
from datetime import datetime, date as _date

