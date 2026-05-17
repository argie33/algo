#!/usr/bin/env python3
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

Load technical indicators into technical_data_daily from price_daily.

Computes: RSI, MACD, SMA, EMA, ATR, ADX, Rate of Change, etc.
Uses watermarks — only inserts rows newer than the existing max date per symbol.
Warm-up: fetches 300 trading days of history before the watermark to seed indicators.
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from config.env_loader import load_env
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
import numpy as np
import pandas as pd
from loaders.loader_validation import validate_technical_row, count_validation_errors

logger = logging.getLogger(__name__)


