#!/usr/bin/env python3
"""
Trade Executor - Execute trades via Alpaca and track positions

Features:
- Idempotent entry (no duplicate trades for same symbol on same day)
- Atomic DB transactions for entry/exit
- Partial exits with weighted-cost-basis P&L (T1 = 50%, T2 = 25%, T3 = 25%)
- R-multiple computed against actual stop loss (not a placeholder)
- Trailing stop adjustments after profit-taking levels
- Paper, dry, review, and auto execution modes
"""

from config.credential_helper import get_db_config
from config.env_loader import load_env
from config.credential_helper import get_db_password, get_db_config
try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
import json
from utils.db_connection import get_db_connection
import uuid
from pathlib import Path
from datetime import datetime, date, timedelta
import requests
import time
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Dict, Any, Optional

from utils.trade_status import TradeStatus, PositionStatus
from utils.alpaca_response_validator import AlpacaResponseValidator
from utils.db_retry_helper import OptimisticLockRetry, RetryConfig
from algo.algo_notifications import TradeNotificationService

logger = logging.getLogger(__name__)
validator = AlpacaResponseValidator()

def _redact_for_logs(message: str) -> str:
    """Redact sensitive trade data from log messages. Masks prices and shares."""
    import re
    # Mask prices: $123.45 → $***
    message = re.sub(r'\$[\d.]+', '$***', message)
    # Mask shares: 100sh → ***sh
    message = re.sub(r'(\d+)sh\b', '***sh', message)
    # Mask slippage: +1.23% → +***%
    message = re.sub(r'([+-]\d+\.\d+)%', '***%', message)
    return message

