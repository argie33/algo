#!/usr/bin/env python3
"""
ISSUE 4: Validation Thresholds Configuration

Centralized configuration for all validation thresholds used in Phase 7/8.
These values can be dynamically adjusted via algo_config table for future
tuning without code changes.

All thresholds are defined with documentation explaining the rationale.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# =============================================================================
# PHASE 8: ENTRY EXECUTION THRESHOLDS
# =============================================================================

# Minimum ATR (Average True Range) for valid signal
# ATR measures volatility; values < 0.01 indicate stale/frozen data or penny stocks
# RATIONALE: Prevents position sizing errors on stocks with zero recent movement
MIN_ATR_THRESHOLD = 0.01  # Minimum 1 cent average true range

# Minimum SMA_50 (50-period Simple Moving Average) for valid signal
# SMA_50 < 0 is impossible (prices are positive), so check for > 0
# RATIONALE: Ensures technical data is valid and not corrupted
MIN_SMA_50_THRESHOLD = 0.0  # SMA must be positive (> 0)

# Minimum entry price for valid signal
# RATIONALE: Excludes penny stocks and ensures numeric stability
MIN_ENTRY_PRICE = 0.0  # Prices must be positive (> 0)

# Maximum number of concurrent open positions
# RATIONALE: Portfolio risk and monitoring capacity
MAX_CONCURRENT_POSITIONS = 15

# Maximum new positions to enter in a single day
# RATIONALE: Prevents overexposure and liquidity issues
MAX_NEW_POSITIONS_PER_DAY = 5

# Maximum total portfolio risk (as percentage)
# RATIONALE: Circuit breaker - no new entries if total risk exceeds this
MAX_TOTAL_RISK_PCT = 4.0

# Minimum available risk capacity before blocking entries (safety buffer)
# RATIONALE: Conservative approach - don't trade right at the limit
MIN_RISK_CAPACITY_PCT = 0.3

# Maximum concentration per position (% of portfolio)
# RATIONALE: Prevents single-stock risk dominance
MAX_CONCENTRATION_PCT = 20.0

# =============================================================================
# PHASE 7: SIGNAL GENERATION THRESHOLDS
# =============================================================================

# Minimum signal quality score (0-100 scale) to qualify for entry
# RATIONALE: Filters weak signals; composite scoring includes momentum (RSI, MACD)
MIN_SIGNAL_QUALITY_SCORE = 30  # Median ~32.75, so this filters ~60% of universe

# Minimum buy_sell_daily signal count to consider data "normal"
# If count drops below this, Phase 7 halts (data quality issue)
# RATIONALE: Catches upstream loader failures early
BUY_SELL_DAILY_ANOMALY_THRESHOLD = 250  # Historical median 300-1000+

# Maximum number of signals to run liquidity checks on
# (Liquidity checks are expensive, so we sample top-ranked candidates)
# RATIONALE: Performance vs completeness tradeoff
LIQUIDITY_CHECK_LIMIT = 20  # Increased from 10 to 20 (AUDIT FIX Session 276)

# Number of worker threads for parallel liquidity checks in Phase 7
# RATIONALE: Limits I/O contention on database connections
PHASE7_LIQUIDITY_CHECK_WORKERS = 4

# =============================================================================
# DATA QUALITY THRESHOLDS
# =============================================================================

# Maximum signal rejection reason string length (for database audit trail)
# algo_signal_rejections.rejection_reason is VARCHAR(200)
# RATIONALE: Prevents truncation from exception wrapping layers
REJECTION_REASON_MAX_LEN = 200

# Minimum price history age (in days) before data is considered stale
# Used to validate technical data freshness
# RATIONALE: Ensures we have recent price movement for ATR calculation
MIN_PRICE_HISTORY_DAYS = 1

# =============================================================================
# POSITION SIZING THRESHOLDS
# =============================================================================

# Minimum risk per trade (as percentage of portfolio)
# RATIONALE: Position sizing floor - prevents micro positions
MIN_RISK_PER_TRADE_PCT = 0.1

# Maximum leverage ratio
# RATIONALE: Prevents over-leverage in position sizing
MAX_LEVERAGE_RATIO = 2.0

# =============================================================================
# DEGRADATION & MONITORING THRESHOLDS
# =============================================================================

# Minimum record count to consider a loader "successful"
# Used for data_patrol and loader health monitoring
# RATIONALE: Catches empty/corrupted loads early
MIN_LOADER_SUCCESS_RECORD_COUNT = 100

# Warning threshold for locked resources (e.g., contended DB connections)
# RATIONALE: Log WARNING when lock contention detected
LOCK_CONTENTION_WARNING_THRESHOLD = 3  # retries before logging warning


def get_threshold(key: str, default: Any = None) -> Any:
    """Get a validation threshold value.

    In production, this could be extended to fetch from algo_config table
    for dynamic adjustment without code deployment.

    Args:
        key: Threshold key (e.g., 'MIN_ATR_THRESHOLD')
        default: Default value if not found

    Returns:
        Threshold value or default
    """
    thresholds = {
        'MIN_ATR_THRESHOLD': MIN_ATR_THRESHOLD,
        'MIN_SMA_50_THRESHOLD': MIN_SMA_50_THRESHOLD,
        'MIN_ENTRY_PRICE': MIN_ENTRY_PRICE,
        'MAX_CONCURRENT_POSITIONS': MAX_CONCURRENT_POSITIONS,
        'MAX_NEW_POSITIONS_PER_DAY': MAX_NEW_POSITIONS_PER_DAY,
        'MAX_TOTAL_RISK_PCT': MAX_TOTAL_RISK_PCT,
        'MIN_RISK_CAPACITY_PCT': MIN_RISK_CAPACITY_PCT,
        'MAX_CONCENTRATION_PCT': MAX_CONCENTRATION_PCT,
        'MIN_SIGNAL_QUALITY_SCORE': MIN_SIGNAL_QUALITY_SCORE,
        'BUY_SELL_DAILY_ANOMALY_THRESHOLD': BUY_SELL_DAILY_ANOMALY_THRESHOLD,
        'LIQUIDITY_CHECK_LIMIT': LIQUIDITY_CHECK_LIMIT,
        'PHASE7_LIQUIDITY_CHECK_WORKERS': PHASE7_LIQUIDITY_CHECK_WORKERS,
        'REJECTION_REASON_MAX_LEN': REJECTION_REASON_MAX_LEN,
        'MIN_PRICE_HISTORY_DAYS': MIN_PRICE_HISTORY_DAYS,
        'MIN_RISK_PER_TRADE_PCT': MIN_RISK_PER_TRADE_PCT,
        'MAX_LEVERAGE_RATIO': MAX_LEVERAGE_RATIO,
        'MIN_LOADER_SUCCESS_RECORD_COUNT': MIN_LOADER_SUCCESS_RECORD_COUNT,
        'LOCK_CONTENTION_WARNING_THRESHOLD': LOCK_CONTENTION_WARNING_THRESHOLD,
    }

    if key not in thresholds:
        logger.warning(f"[VALIDATION_THRESHOLDS] Unknown threshold key: {key}")
        return default

    return thresholds[key]


def log_threshold_values() -> None:
    """Log all threshold values for audit trail and debugging."""
    logger.info("[VALIDATION_THRESHOLDS] Loaded configuration:")
    logger.info(f"  ATR: min={MIN_ATR_THRESHOLD}")
    logger.info(f"  SMA_50: min={MIN_SMA_50_THRESHOLD}")
    logger.info(f"  Entry price: min={MIN_ENTRY_PRICE}")
    logger.info(f"  Positions: max={MAX_CONCURRENT_POSITIONS}, max_new_today={MAX_NEW_POSITIONS_PER_DAY}")
    logger.info(f"  Risk: max_total={MAX_TOTAL_RISK_PCT}%, min_capacity={MIN_RISK_CAPACITY_PCT}%")
    logger.info(f"  Concentration: max={MAX_CONCENTRATION_PCT}%")
    logger.info(f"  Signal quality: min={MIN_SIGNAL_QUALITY_SCORE}")
    logger.info(f"  Buy/sell signals: anomaly_threshold={BUY_SELL_DAILY_ANOMALY_THRESHOLD}")
