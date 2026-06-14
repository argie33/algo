#!/usr/bin/env python3
"""Equity Curve Daily Loader - Pre-compute rolling Sharpe, Sortino, max drawdown, Calmar."""
import sys
import logging
import statistics
from datetime import date, timedelta, datetime, timezone
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.infrastructure.timezone import EASTERN_TZ
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

class EquityCurveDailyLoader(OptimalLoader):
