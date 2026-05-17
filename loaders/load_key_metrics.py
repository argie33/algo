#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
from config.credential_helper import get_db_config

Key Metrics Loader — market cap and insider/institution holdings from Finnhub.

Market cap and shareholding data for all stocks in universe.
Uses Finnhub's free tier API.

USAGE:
    python3 load_key_metrics.py                 # all symbols
    python3 load_key_metrics.py --symbols SPY,AAPL,MSFT
    python3 load_key_metrics.py --limit 100     # first 100 symbols
"""

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import argparse
from config.credential_helper import get_db_password, get_db_config
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from config.env_loader import load_env
from typing import Dict, List, Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

