#!/usr/bin/env python3
"""Centralized configuration for the trading algorithm.

All magic numbers and configurable parameters should be defined here for easy tuning
without code changes. Each parameter includes documentation, defaults, and valid ranges.

Configuration Priority (highest to lowest):
1. Environment variables
2. Defaults defined in this file
3. Hardcoded fallbacks in individual modules (deprecated)
"""

import logging
import os
from typing import Final

logger = logging.getLogger(__name__)

# ============================================================================
# ORCHESTRATOR & PHASE CONFIGURATION
# ============================================================================

# Phase event hub: maximum number of events to keep in memory
# Used by: algo/orchestration/phase_event_hub.py:146
# Purpose: Prevent unbounded memory growth when storing phase execution events
# Risk if too high: Memory exhaustion with many phases/runs
# Risk if too low: Event history truncation, lost audit trail
PHASE_EVENT_HISTORY_MAX: Final[int] = int(os.environ.get("PHASE_EVENT_HISTORY_MAX", "1000"))

# ============================================================================
# LOADER CONFIGURATION
# ============================================================================

# Loader execution timeout in minutes
# Used by: loaders/runner.py:39-46
# Purpose: Prevent hung loaders from blocking orchestrator indefinitely
# Typical scenario: SEC API slow/unresponsive, loader waits forever without timeout
# Must be > 0 (validated at load time)
LOADER_TIMEOUT_MINUTES: Final[int] = int(os.environ.get("LOADER_TIMEOUT_MINUTES", "120"))
LOADER_TIMEOUT_SECONDS: Final[int] = LOADER_TIMEOUT_MINUTES * 60

# Maximum days of historical data to backfill per load
# Used by: loaders/optimal_loader.py
# Purpose: Avoid excessive backfill on initial loader setup
# Typical: 0-30 for incremental loads, up to 730+ for full year+ backfill
# Environment: MAX_BACKFILL_DAYS (default 0 = incremental only, no backfill)
MAX_BACKFILL_DAYS: Final[int] = int(os.environ.get("MAX_BACKFILL_DAYS", "0"))
MAX_BACKFILL_DAYS_LIMIT: Final[int] = int(os.environ.get("MAX_BACKFILL_DAYS_LIMIT", "1825"))  # 5 years default

# ============================================================================
# DATABASE CONNECTION POOL CONFIGURATION
# ============================================================================

# Minimum number of idle connections to maintain
# Used by: utils/db/connection.py:105
# Purpose: Cold-start prevention; keep connections ready for immediate use
# Environment:
#   - Lambda/production: recommend 2-5 (low footprint, minimal latency)
#   - Dev/local: can increase to 5-10
DB_POOL_MIN_CONNECTIONS: Final[int] = int(os.environ.get("DB_POOL_MIN_CONNECTIONS", "5"))

# Maximum number of concurrent database connections to allow
# Used by: utils/db/connection.py:106
# Purpose: Prevent resource exhaustion; RDS Proxy limits total to 500
# Environment:
#   - Lambda/production: recommend 10-20 (one invocation per container, bounded)
#   - Dev/staging: can increase to 40-80
#   - Local dev: can increase to 40+ (single-threaded testing)
# Note: Each orchestrator phase can use 1-2 connections, 9 phases = 9-18 connections needed
DB_POOL_MAX_CONNECTIONS: Final[int] = int(os.environ.get("DB_POOL_MAX_CONNECTIONS", "40"))

# Idle connection reaping: connections idle > N seconds are closed
# Used by: utils/db/pooled_connection_manager.py:IdleConnectionPool
# Purpose: Prevent stale connection reuse after network interruptions
# Typical: 300-600 seconds (5-10 min)
DB_POOL_MAX_IDLE_SECONDS: Final[int] = int(os.environ.get("DB_POOL_MAX_IDLE_SECONDS", "300"))

# Idle connection cleanup check interval
# Used by: utils/db/pooled_connection_manager.py:IdleConnectionPool
# Purpose: How often to scan for and close idle connections
# Typical: 30-120 seconds (trade-off between resource cleanup and overhead)
DB_POOL_CLEANUP_INTERVAL_SECONDS: Final[int] = int(os.environ.get("DB_POOL_CLEANUP_INTERVAL_SECONDS", "60"))

# ============================================================================
# TCP KEEPALIVE CONFIGURATION
# ============================================================================
# These values optimize detection of broken connections to RDS
# Risk if too short: Frequent false positives, connection churn
# Risk if too long: Slow detection of genuine network failures

# Enable TCP keepalives (1 = enabled)
# Used by: utils/db/connection.py:119
DB_KEEPALIVES: Final[int] = 1

# Start probing idle connections after N seconds
# Used by: utils/db/connection.py:120
# Previous value: 60s (too slow for hung connection detection)
# Current value: 30s (aggressive early detection)
DB_KEEPALIVES_IDLE_SECONDS: Final[int] = int(os.environ.get("DB_KEEPALIVES_IDLE_SECONDS", "30"))

# Probe interval for keepalive checks
# Used by: utils/db/connection.py:121
# Previous value: 10s (too aggressive)
# Current value: 5s (balanced detection speed vs network overhead)
DB_KEEPALIVES_INTERVAL_SECONDS: Final[int] = int(os.environ.get("DB_KEEPALIVES_INTERVAL_SECONDS", "5"))

# Number of failed keepalive probes before declaring connection dead
# Used by: utils/db/connection.py:122
# Previous value: 5 probes (slow failover: 5 * 5s = 25 seconds)
# Current value: 3 probes (faster failover: 3 * 5s = 15 seconds)
DB_KEEPALIVES_COUNT: Final[int] = int(os.environ.get("DB_KEEPALIVES_COUNT", "3"))

# ============================================================================
# VALIDATION & INITIALIZATION
# ============================================================================


def validate_config() -> None:
    """Validate all configuration values at startup.

    Called by orchestrator and loaders to catch invalid config early.
    Raises RuntimeError if any value fails validation.
    """
    errors = []

    if PHASE_EVENT_HISTORY_MAX <= 0:
        errors.append(f"PHASE_EVENT_HISTORY_MAX must be > 0, got {PHASE_EVENT_HISTORY_MAX}")

    if LOADER_TIMEOUT_MINUTES <= 0:
        errors.append(f"LOADER_TIMEOUT_MINUTES must be > 0, got {LOADER_TIMEOUT_MINUTES}")

    if MAX_BACKFILL_DAYS < 0 or MAX_BACKFILL_DAYS > MAX_BACKFILL_DAYS_LIMIT:
        errors.append(f"MAX_BACKFILL_DAYS must be 0-{MAX_BACKFILL_DAYS_LIMIT}, got {MAX_BACKFILL_DAYS}")

    if DB_POOL_MIN_CONNECTIONS <= 0:
        errors.append(f"DB_POOL_MIN_CONNECTIONS must be > 0, got {DB_POOL_MIN_CONNECTIONS}")

    if DB_POOL_MAX_CONNECTIONS <= 0:
        errors.append(f"DB_POOL_MAX_CONNECTIONS must be > 0, got {DB_POOL_MAX_CONNECTIONS}")

    if DB_POOL_MIN_CONNECTIONS > DB_POOL_MAX_CONNECTIONS:
        errors.append(
            f"DB_POOL_MIN_CONNECTIONS ({DB_POOL_MIN_CONNECTIONS}) > DB_POOL_MAX_CONNECTIONS ({DB_POOL_MAX_CONNECTIONS})"
        )

    if DB_POOL_MAX_IDLE_SECONDS <= 0:
        errors.append(f"DB_POOL_MAX_IDLE_SECONDS must be > 0, got {DB_POOL_MAX_IDLE_SECONDS}")

    if DB_POOL_CLEANUP_INTERVAL_SECONDS <= 0:
        errors.append(f"DB_POOL_CLEANUP_INTERVAL_SECONDS must be > 0, got {DB_POOL_CLEANUP_INTERVAL_SECONDS}")

    if DB_KEEPALIVES_IDLE_SECONDS <= 0:
        errors.append(f"DB_KEEPALIVES_IDLE_SECONDS must be > 0, got {DB_KEEPALIVES_IDLE_SECONDS}")

    if DB_KEEPALIVES_INTERVAL_SECONDS <= 0:
        errors.append(f"DB_KEEPALIVES_INTERVAL_SECONDS must be > 0, got {DB_KEEPALIVES_INTERVAL_SECONDS}")

    if DB_KEEPALIVES_COUNT <= 0:
        errors.append(f"DB_KEEPALIVES_COUNT must be > 0, got {DB_KEEPALIVES_COUNT}")

    if errors:
        error_msg = "Configuration validation failed:\n  " + "\n  ".join(errors)
        logger.critical(f"[CONFIG] {error_msg}")
        raise RuntimeError(error_msg)

    logger.info(
        "[CONFIG] Configuration validated: "
        f"event_history={PHASE_EVENT_HISTORY_MAX}, "
        f"loader_timeout={LOADER_TIMEOUT_MINUTES}m, "
        f"db_pool={DB_POOL_MIN_CONNECTIONS}-{DB_POOL_MAX_CONNECTIONS}, "
        f"keepalives_idle={DB_KEEPALIVES_IDLE_SECONDS}s"
    )


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    logger.info("Current Configuration:")
    logger.info(f"  PHASE_EVENT_HISTORY_MAX = {PHASE_EVENT_HISTORY_MAX}")
    logger.info(f"  LOADER_TIMEOUT_MINUTES = {LOADER_TIMEOUT_MINUTES}")
    logger.info(f"  LOADER_TIMEOUT_SECONDS = {LOADER_TIMEOUT_SECONDS}")
    logger.info(f"  MAX_BACKFILL_DAYS = {MAX_BACKFILL_DAYS}")
    logger.info(f"  DB_POOL_MIN_CONNECTIONS = {DB_POOL_MIN_CONNECTIONS}")
    logger.info(f"  DB_POOL_MAX_CONNECTIONS = {DB_POOL_MAX_CONNECTIONS}")
    logger.info(f"  DB_POOL_MAX_IDLE_SECONDS = {DB_POOL_MAX_IDLE_SECONDS}")
    logger.info(f"  DB_POOL_CLEANUP_INTERVAL_SECONDS = {DB_POOL_CLEANUP_INTERVAL_SECONDS}")
    logger.info(f"  DB_KEEPALIVES_IDLE_SECONDS = {DB_KEEPALIVES_IDLE_SECONDS}")
    logger.info(f"  DB_KEEPALIVES_INTERVAL_SECONDS = {DB_KEEPALIVES_INTERVAL_SECONDS}")
    logger.info(f"  DB_KEEPALIVES_COUNT = {DB_KEEPALIVES_COUNT}")

    validate_config()
    logger.info("✓ Configuration is valid")
