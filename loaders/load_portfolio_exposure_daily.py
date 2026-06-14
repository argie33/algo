#!/usr/bin/env python3
"""Portfolio Exposure Daily Loader - Pre-compute portfolio metrics and risk indicators."""
import sys
import logging
import statistics
from datetime import date, datetime, timezone
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.infrastructure.timezone import EASTERN_TZ
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

class PortfolioExposureDailyLoader(OptimalLoader):
