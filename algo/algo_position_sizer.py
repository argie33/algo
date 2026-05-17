#!/usr/bin/env python3
"""
Position Sizer - Calculates trade size based on risk management rules

Rules:
- Base risk: 0.75% of portfolio per trade
- Drawdown defense: reduce risk at -5%, -10%, -15%, -20%
- Pyramid entry: 50/33/17 split across multiple entries
- Max position size: 8% of portfolio
- Max concentration: 50% in single position
- Max positions: 12 concurrent
"""

from config.env_loader import load_env
import os
from utils.db_connection import get_db_connection
from pathlib import Path
from config.credential_helper import get_db_password, get_db_config
from utils.structured_logger import get_logger

logger = get_logger(__name__)

