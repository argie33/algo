#!/usr/bin/env python3
"""
Hedge-Fund-Style Multi-Factor Filter & Scoring (Tier 6+)

Layered ON TOP of the 5-tier filter pipeline. The 5 tiers ensure technical
qualification (Minervini-style); this layer applies institutional discipline:

    MOMENTUM (40 pts)  - is the stock + its sector + its tape moving right?
    QUALITY  (30 pts)  - is the business actually good?
    CATALYST (15 pts)  - is there a fundamental reason driving it?
    RISK     (15 pts)  - is the entry well-priced relative to risk?

Total = 100 pts. Used for final ranking among T5 passers, plus HARD-FAIL
gates that block obvious mistakes.

HARD-FAIL gates:
    H1. Earnings within block window           (default <= 5 days)
    H2. Over-extended above 50-DMA              (default >  15%)
    H4. Insufficient liquidity                  (avg $vol < min, default $5M)
    H5. Strong sector requirement (configurable, default off)

Design notes:
    - Hard fails are independent — any one blocks the trade.
    - Soft scoring rewards quality across many dimensions.
    - Each factor reads from a real table (no synthetic data).
    - Failures gracefully default to neutral when data is missing.
"""

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

try:
    from config.credential_helper import get_db_password, get_db_config
except ImportError:
    # Fallback if credential_helper not available
    def get_db_password():
        return credential_manager.get_db_credentials()["password"] if credential_manager else ""
    def get_db_config():
        return credential_manager.get_db_credentials() if credential_manager else {}

from config.credential_helper import get_db_config
from config.env_loader import load_env
import os
import logging
from utils.db_connection import get_db_connection
from pathlib import Path
from datetime import datetime, timedelta, date as _date
from algo.algo_signals import SignalComputer

logger = logging.getLogger(__name__)

