#!/usr/bin/env python3
"""
API: GET /api/data-coverage

Returns comprehensive data coverage diagnostics:
- Price data freshness
- Technical indicators completeness
- Symbol coverage
- Loader health
- Metric availability

For use in dashboard and automated monitoring.
"""

import json
import logging
from datetime import datetime, date as _date, timedelta
from typing import Dict, Any, Tuple

from utils.db_connection import get_db_connection

logger = logging.getLogger(__name__)


def get_price_coverage() -> Dict[str, Any]:
    """Get price_daily coverage metrics."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                COUNT(DISTINCT symbol) as total_symbols,
                (SELECT COUNT(DISTINCT symbol) FROM stock_symbols WHERE is_sp500 = TRUE) as sp500_total,
                MAX(date) as latest_date,
                COUNT(*) as total_rows,
                COUNT(CASE WHEN volume = 0 OR volume IS NULL THEN 1 END) as zero_volume_rows,
                COUNT(CASE WHEN close <= 0 THEN 1 END) as invalid_price_rows
            FROM price_daily
            WHERE date > NOW() - INTERVAL '7 days'
        """)

        row = cur.fetchone()
        total_symbols, sp500_total, latest_date, total_rows, zero_vol, invalid_prices = row

        days_stale = (_date.today() - latest_date).days if latest_date else 999
        zero_vol_pct = (zero_vol / total_rows * 100) if total_rows else 0
        invalid_pct = (invalid_prices / total_rows * 100) if total_rows else 0

        cur.close()
        conn.close()

        return {
            'total_symbols': total_symbols,
            'sp500_target': sp500_total,
            'coverage_pct': round(total_symbols / sp500_total * 100, 1) if sp500_total else 0,
            'latest_date': str(latest_date),
            'days_stale': days_stale,
            'status': 'fresh' if days_stale <= 1 else 'stale',
            'data_quality': {
                'zero_volume_pct': round(zero_vol_pct, 2),
                'invalid_price_pct': round(invalid_pct, 2)
            }
        }
    except Exception as e:
        return {'error': str(e), 'status': 'error'}


def get_technical_coverage() -> Dict[str, Any]:
    """Get technical_data_daily coverage and completeness."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                COUNT(DISTINCT symbol) as symbols,
                MAX(date) as latest_date,
                COUNT(*) as total_rows,
                COUNT(CASE WHEN rsi IS NOT NULL THEN 1 END)::FLOAT / COUNT(*) as rsi_coverage,
                COUNT(CASE WHEN ema_50 IS NOT NULL THEN 1 END)::FLOAT / COUNT(*) as ema50_coverage,
                COUNT(CASE WHEN atr IS NOT NULL THEN 1 END)::FLOAT / COUNT(*) as atr_coverage,
                COUNT(CASE WHEN rsi IS NULL OR ema_50 IS NULL OR atr IS NULL THEN 1 END) as incomplete_rows
            FROM technical_data_daily
            WHERE date > NOW() - INTERVAL '7 days'
        """)

        row = cur.fetchone()
        symbols, latest_date, total_rows, rsi_cov, ema_cov, atr_cov, incomplete = row

        cur.close()
        conn.close()

        min_coverage = min(rsi_cov, ema_cov, atr_cov) if None not in (rsi_cov, ema_cov, atr_cov) else 0

        return {
            'symbols_with_technicals': symbols,
            'latest_date': str(latest_date),
            'indicator_coverage': {
                'rsi_pct': round(rsi_cov * 100, 1) if rsi_cov else 0,
                'ema50_pct': round(ema_cov * 100, 1) if ema_cov else 0,
                'atr_pct': round(atr_cov * 100, 1) if atr_cov else 0,
                'min_coverage_pct': round(min_coverage * 100, 1)
            },
            'incomplete_rows': incomplete,
            'status': 'complete' if min_coverage >= 0.95 else 'incomplete'
        }
    except Exception as e:
        return {'error': str(e), 'status': 'error'}


def get_market_data_coverage() -> Dict[str, Any]:
    """Get market_health_daily and other market data coverage."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Market health
        cur.execute("""
            SELECT
                MAX(date) as latest_date,
                COUNT(*) as rows,
                COUNT(CASE WHEN distribution_days IS NULL THEN 1 END) as null_dist_days
            FROM market_health_daily
            WHERE date > NOW() - INTERVAL '7 days'
        """)

        mh_date, mh_rows, mh_nulls = cur.fetchone()

        # Economic data (FRED)
        cur.execute("""
            SELECT MAX(date) as latest_date, COUNT(DISTINCT symbol) as indicators
            FROM economic_data
            WHERE date > NOW() - INTERVAL '30 days'
        """)

        econ_date, econ_count = cur.fetchone()

        cur.close()
        conn.close()

        return {
            'market_health': {
                'latest_date': str(mh_date),
                'days_stale': (_date.today() - mh_date).days if mh_date else 999,
                'recent_rows': mh_rows,
                'status': 'available' if mh_rows > 0 else 'missing'
            },
            'economic_data': {
                'latest_date': str(econ_date) if econ_date else None,
                'indicators_tracked': econ_count,
                'status': 'available' if econ_count > 0 else 'missing'
            }
        }
    except Exception as e:
        return {'error': str(e), 'status': 'error'}


def get_loader_health() -> Dict[str, Any]:
    """Get recent loader execution health."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                loader_name,
                status,
                MAX(executed_at) as latest_run,
                COUNT(*) as total_runs,
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_count
            FROM data_loader_status
            WHERE executed_at > NOW() - INTERVAL '7 days'
            GROUP BY loader_name, status
            ORDER BY loader_name, latest_run DESC
        """)

        rows = cur.fetchall()
        cur.close()
        conn.close()

        failed_loaders = [
            row[0] for row in rows if row[1] == 'FAILED'
        ]

        return {
            'total_checks': len(rows),
            'failed_loaders': list(set(failed_loaders)),
            'recent_failures': len(set(failed_loaders)),
            'status': 'healthy' if not failed_loaders else 'degraded'
        }
    except Exception as e:
        return {'error': str(e), 'status': 'error'}


def get_overall_coverage_summary() -> Dict[str, Any]:
    """Get overall data coverage summary."""
    summary = {
        'timestamp': datetime.utcnow().isoformat(),
        'price_data': get_price_coverage(),
        'technical_data': get_technical_coverage(),
        'market_data': get_market_data_coverage(),
        'loaders': get_loader_health()
    }

    # Determine overall status
    statuses = []
    for section_name, section_data in summary.items():
        if section_name == 'timestamp':
            continue
        if isinstance(section_data, dict):
            status = section_data.get('status')
            if status == 'error' or status == 'missing':
                statuses.append('critical')
            elif status in ['stale', 'incomplete', 'degraded']:
                statuses.append('warning')
            elif status in ['fresh', 'complete', 'available', 'healthy', 'ok']:
                statuses.append('ok')

    if 'critical' in statuses:
        summary['overall_health'] = 'critical'
    elif 'warning' in statuses:
        summary['overall_health'] = 'warning'
    else:
        summary['overall_health'] = 'healthy'

    return summary


def handle_request(event: Dict, context: Any) -> Tuple[int, Dict[str, Any]]:
    """Handle API request for data coverage."""

    try:
        summary = get_overall_coverage_summary()
        return 200, summary

    except Exception as e:
        return 500, {
            'error': 'Data coverage check failed',
            'message': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }


# For FastAPI integration
async def get_data_coverage():
    """FastAPI endpoint for /api/data-coverage."""
    status_code, body = handle_request({}, {})
    return {
        'statusCode': status_code,
        'body': body
    }
