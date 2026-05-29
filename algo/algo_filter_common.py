#!/usr/bin/env python3
"""
Shared filter and analysis utilities used across multiple modules.

Consolidates duplicate implementations to reduce code duplication.
Imported by: algo_filter_pipeline, filters/, position_monitor, etc.
"""

from typing import Dict, Any, List, Optional
import logging
import numpy as np

logger = logging.getLogger(__name__)


def check_correlation_with_holdings(cur, new_symbol: str, existing_symbols: List[str], signal_date=None) -> Dict[str, Any]:
    """Check if new symbol is highly correlated (>0.80) with existing open positions.

    Returns {'pass': bool, 'reason': str, 'highest_correlation': float}
    """
    if not existing_symbols:
        return {'pass': True, 'reason': 'No existing positions'}

    try:
        symbols_to_check = [new_symbol] + list(existing_symbols)
        placeholders = ','.join(['%s'] * len(symbols_to_check))
        cur.execute(
            f"""
            SELECT symbol, date, close FROM price_daily
            WHERE symbol IN ({placeholders})
              AND date >= CURRENT_DATE - INTERVAL '60 days'
            ORDER BY symbol, date
            """,
            tuple(symbols_to_check)
        )
        rows = cur.fetchall()

        if not rows:
            return {'pass': True, 'reason': 'Insufficient price history (< 60 days)'}

        prices_by_symbol = {}
        for symbol, date, close in rows:
            if symbol not in prices_by_symbol:
                prices_by_symbol[symbol] = []
            prices_by_symbol[symbol].append(float(close))

        new_prices = np.array(prices_by_symbol.get(new_symbol, []))
        if len(new_prices) < 2:
            return {'pass': True, 'reason': 'Insufficient data for correlation'}

        new_returns = np.diff(new_prices) / new_prices[:-1]
        max_corr = 0.0

        for existing_symbol in existing_symbols:
            existing_prices = np.array(prices_by_symbol.get(existing_symbol, []))
            if len(existing_prices) < 2:
                continue

            existing_returns = np.diff(existing_prices) / existing_prices[:-1]
            if len(new_returns) == len(existing_returns):
                try:
                    corr = np.corrcoef(new_returns, existing_returns)[0, 1]
                    if not np.isnan(corr):
                        max_corr = max(max_corr, abs(corr))
                except Exception:
                    pass

        if max_corr > 0.80:
            return {
                'pass': False,
                'reason': f'Too correlated with existing holdings (r={max_corr:.2f}, max allowed: 0.80)',
                'highest_correlation': max_corr
            }

        return {
            'pass': True,
            'reason': f'Acceptable correlation (r={max_corr:.2f} < 0.80)',
            'highest_correlation': max_corr
        }

    except Exception as e:
        logger.debug(f"Correlation check error: {e}")
        return {'pass': True, 'reason': 'Correlation check skipped (data issue)', 'highest_correlation': None}


def count_sector_industry_overlap(new_info: Dict[str, str], existing_symbols: List[Dict[str, str]]) -> int:
    """Count how many existing positions share sector/industry with new candidate."""
    if not new_info or not existing_symbols:
        return 0

    new_sector = new_info.get('sector')
    new_industry = new_info.get('industry')

    overlap = 0
    for pos in existing_symbols:
        if new_sector and pos.get('sector') == new_sector:
            overlap += 1
        elif new_industry and pos.get('industry') == new_industry:
            overlap += 1

    return overlap


def days_to_earnings(cur, symbol: str) -> Optional[int]:
    """Get days until next earnings announcement for symbol."""
    try:
        cur.execute(
            "SELECT report_date FROM earnings_calendar WHERE symbol = %s AND report_date >= CURRENT_DATE ORDER BY report_date LIMIT 1",
            (symbol,)
        )
        row = cur.fetchone()
        if row:
            from datetime import date as _date
            return (row[0] - _date.today()).days
    except Exception as e:
        logger.debug(f"Earnings lookup failed for {symbol}: {e}")
    return None


def get_db_config_dict(db_host: str, db_port: int, db_user: str, db_name: str, db_password: str) -> Dict[str, Any]:
    """Build database configuration dictionary."""
    return {
        'host': db_host,
        'port': db_port,
        'user': db_user,
        'password': db_password,
        'database': db_name,
        'connect_timeout': 5,
    }


