#!/usr/bin/env python3
"""
Filter Pipeline Rejection Tracking

Logs every signal through all 5 tiers + advanced filters.
Captures rejection reason at each tier for explainability.

Enables:
- Rejection funnel analysis: 150 signals -> 80 pass T1 -> 30 pass T2 -> 8 qualified
- Per-gate rejection counts: "Distribution days blocked 20 signals"
- Tuning feedback: "If we loosen Tier 2, we get 5 additional trades"
"""

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

from config.credential_helper import get_db_config
from config.env_loader import load_env
import os
from config.credential_helper import get_db_password, get_db_config
from utils.db_connection import get_db_connection
from pathlib import Path
from datetime import datetime, date
import logging
logger = logging.getLogger(__name__)
from typing import Dict, List, Optional

logging.basicConfig(
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

