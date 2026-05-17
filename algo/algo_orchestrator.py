#!/usr/bin/env python3
"""
Master Orchestrator - Daily Trading Workflow (institutional desk style)

Runs the complete day's logic in 7 explicit phases. Each phase has a clear
contract: what it consumes, what it produces, what makes it fail-closed
(halt the whole pipeline) vs fail-open (log and continue).

PHASE 1 — DATA FRESHNESS CHECK
  Confirms our market data is recent enough to make decisions on.
  FAIL-CLOSED: stale data > 7 days -> halt.

PHASE 2 — CIRCUIT BREAKERS
  Runs all kill-switch checks (drawdown, daily loss, consecutive losses,
  total open risk, VIX, market stage, weekly loss).
  FAIL-CLOSED on any breaker firing.

PHASE 3 — POSITION MONITOR (existing positions first)
  For every open position:
    - Refresh current price + P&L
    - Compute trailing stop (only ratchets up)
    - Score health (RS, sector, time decay, earnings proximity, etc.)
    - PROPOSE actions: HOLD / RAISE_STOP / EARLY_EXIT
  FAIL-OPEN: log errors but continue.

PHASE 4 — EXIT EXECUTION
  Apply exit decisions from Phase 3 (full and partial) and from the
  exit_engine's tiered targets / stops / time / Minervini-break logic.
  FAIL-OPEN per position.

PHASE 5 — SIGNAL GENERATION (new entries)
  Evaluate today's BUY signals through:
    - Tiers 1-5 (data quality, market, trend template, SQS, portfolio fit)
    - Tier 6 (multi-factor advanced filters: momentum/quality/catalyst/risk)
  Rank by composite score, take top N up to max_positions cap minus
  current open positions.
  FAIL-OPEN: log and proceed with whatever passed.

PHASE 6 — ENTRY EXECUTION
  For each ranked candidate, in priority order:
    - Final pre-flight checks (still no duplicate, room left, etc.)
    - TradeExecutor.execute_trade() with idempotency
  FAIL-OPEN per trade.

PHASE 7 — RECONCILIATION & SNAPSHOT
  Pull live Alpaca account data, sync positions, calculate P&L,
  create daily portfolio snapshot.
  FAIL-OPEN: log if Alpaca down.

After every phase, results are written to algo_audit_log so the dashboard
can show exactly what happened and when.
"""

from config.credential_helper import get_db_config
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.env_loader import load_env
load_env()
from config.credential_helper import get_db_password, get_db_config
try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
import sys
import tempfile
from utils.db_connection import get_db_connection
import psycopg2.extensions
from psycopg2 import pool as psycopg2_pool
import traceback
from pathlib import Path
from datetime import datetime, date as _date, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple, Union
from algo.algo_alerts import AlertManager
from algo.algo_market_calendar import MarketCalendar
from algo.algo_sql_safety import assert_safe_table, assert_safe_column
from utils.trade_status import PositionStatus
import logging
from utils.monitoring_context import TimeBlock, log_metrics_summary, clear_metrics_buffer

logger = logging.getLogger(__name__)

