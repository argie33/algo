#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from pathlib import Path

"""
Loader SLA Tracker - Track loader success/failure and data freshness

Used by:
1. Individual loaders (log their results)
2. data_quality_validator.py (record daily SLA)
3. algo_orchestrator.py (check if data is fresh before trading)

Provides visibility into:
- Which loaders ran today and succeeded/failed
- What data is fresh vs stale
- Loader success rate over time
"""

import logging
from utils.db_connection import get_db_connection
from datetime import datetime, date
from typing import Optional, Dict, List
import os
from config.credential_helper import get_db_password, get_db_config
from algo.algo_sql_safety import assert_safe_table
from pathlib import Path
from config.env_loader import load_env

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None


