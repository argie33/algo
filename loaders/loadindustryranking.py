#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
loadindustryranking.py — Compute industry_ranking from constituent stock returns

Computes 4-week momentum per industry by averaging 4-week returns of all
stocks in that industry. Ranks all 197+ industries.

Pure SQL — uses company_profile.industry to group, price_daily for returns.
Run after loadpricedaily.py and loaddailycompanydata.py.

USAGE:
  python3 loadindustryranking.py
"""

import os
from pathlib import Path
from config.env_loader import load_env
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


