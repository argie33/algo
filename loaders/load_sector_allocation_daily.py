#!/usr/bin/env python3
"""Sector Allocation Daily Loader - Pre-compute sector exposures and aggregations."""
import sys
import logging
from datetime import date, datetime, timezone
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.infrastructure.timezone import EASTERN_TZ
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

class SectorAllocationDailyLoader(OptimalLoader):
