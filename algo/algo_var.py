from config.env_loader import load_env
from config.credential_helper import get_db_password, get_db_config
"""
Portfolio Risk Measures — VaR, CVaR, Concentration, Beta Exposure

Institutional risk measurement for portfolio monitoring.

Metrics:
- Historical VaR: "We have 95% confidence portfolio won't lose more than $X in one day"
- Conditional VaR (Expected Shortfall): Mean loss beyond VaR threshold
- Stressed VaR: VaR using worst 12-month historical window
- Beta Exposure: Portfolio beta vs. S&P 500 (systematic risk)
- Concentration: Top holdings %, sector breakdown, industry breakdown

Alerts:
- Daily VaR > 2% of portfolio → WARNING
- Concentration > 30% in top 5 holdings → WARNING
- Beta exposure > 2.0 (2× market risk) → WARNING
"""

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

from utils.db_connection import get_db_connection
import os
import logging
from datetime import datetime, date
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

