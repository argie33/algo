#!/usr/bin/env python3
"""Sentiment Aggregate Loader - Combines AAII + NAAIM sentiment into unified metric (Market-wide)."""
import sys
import logging
from datetime import date
from typing import Optional, List

from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

class SentimentAggregateLoader(OptimalLoader):
