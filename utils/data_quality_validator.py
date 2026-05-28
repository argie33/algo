#!/usr/bin/env python3
"""Data Quality Validator - Issues #36-38: Validates price and market data quality.

Checks:
- Issue #36: Price data has volume > 0
- Issue #37: Technical indicators skip gaps > 1 trading day
- Issue #38: Market health uses fallback for missing data
"""

import logging
from datetime import datetime, timedelta, date as _date
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


def validate_price_data(symbol: str, price: float, volume: int, date: _date) -> Tuple[bool, Optional[str]]:
    """Issue #36: Validate price data has non-zero volume.

    Returns: (valid, error_message)
    """
    if volume <= 0:
        msg = f"{symbol} on {date}: volume={volume} (zero volume bars indicate halts/delists)"
        logger.warning(msg)
        return False, msg

    if price <= 0:
        msg = f"{symbol} on {date}: price={price} (invalid price)"
        logger.warning(msg)
        return False, msg

    return True, None


def check_data_gaps(dates: List[_date], trading_day_gaps_threshold: int = 1) -> Tuple[bool, List[Tuple[_date, _date]]]:
    """Issue #37: Check for data gaps > N trading days.

    Returns: (valid, list_of_gaps)
    """
    gaps = []
    for i in range(len(dates) - 1):
        calendar_days_gap = (dates[i + 1] - dates[i]).days
        if calendar_days_gap > trading_day_gaps_threshold * 2:  # Conservative: 2x trading days
            gaps.append((dates[i], dates[i + 1]))
            logger.warning(f"Data gap detected: {dates[i]} → {dates[i+1]} ({calendar_days_gap} calendar days)")

    return len(gaps) == 0, gaps


def get_market_health_with_fallback(current_data: Optional[Dict], previous_data: Dict) -> Dict:
    """Issue #38: Use previous day's data if current data missing.

    Prevents circuit breakers from using stale data on early closes/holidays.
    """
    if current_data and current_data.get('vix_level'):
        return current_data

    # Fallback to previous day with staleness warning
    if previous_data:
        logger.warning("Market health data missing for today, using previous day with staleness warning")
        return {**previous_data, 'stale': True, 'staleness_days': 1}

    # Ultimate fallback
    logger.critical("No market health data available (current or previous)")
    return {'vix_level': 20.0, 'market_trend': 'unknown', 'fallback': True}


def reset_technical_indicators_on_gap(has_gap: bool, atr: float, sma_50: float, ema_12: float) -> Tuple[float, float, float]:
    """Issue #37: Reset technical indicators if data gap detected (suspended stock).

    Returns: (atr, sma_50, ema_12) with None/defaults if gap found
    """
    if has_gap:
        logger.warning("Stock has trading gap (suspension/delisting), resetting technical indicators")
        return None, None, None

    return atr, sma_50, ema_12
