#!/usr/bin/env python3
"""Earnings Calendar Loader - Fetches upcoming earnings dates."""
import sys
import argparse
import logging
import os
from datetime import date
from typing import List, Optional

from utils.optimal_loader import OptimalLoader
from utils.loaders.helpers import get_active_symbols
from utils.loaders.config import get_parallelism, get_default_parallelism

logger = logging.getLogger(__name__)

class EarningsCalendarLoader(OptimalLoader):
