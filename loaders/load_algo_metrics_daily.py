#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from pathlib import Path

"""
Algo Metrics Daily Loader (ORCHESTRATOR)

Single unified script that calculates ALL algo metrics daily in one efficient pass:
1. Market health daily
2. Trend template fields per symbol
3. Distribution days (stock + market level)
4. Base count per symbol
5. Power trend flag (20% in 21 days)
6. CAN SLIM fundamentals
7. VCP detection
8. Data completeness scores
9. Theme/correlation tags
10. Signal Quality Scores

Runs as single atomic transaction. Idempotent design - safe to run multiple times per day.
"""

from config.credential_helper import get_db_password, get_db_config
try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
import logging
from utils.db_connection import get_db_connection
from datetime import datetime, timedelta
from pathlib import Path
from config.env_loader import load_env

logger = logging.getLogger(__name__)


