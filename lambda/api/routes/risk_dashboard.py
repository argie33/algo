"""Route: risk_dashboard - Real-time risk metrics for decision-making.

Endpoints:
  /api/algo/risk-dashboard — All current risk metrics
  /api/algo/risk-dashboard/drawdown — Current drawdown %
  /api/algo/risk-dashboard/exposure-tier — Current tier and why
  /api/algo/risk-dashboard/position-sizing-audit — Why trades were sized as they were
  /api/algo/risk-dashboard/stop-loss-audit — Why stops were chosen
  /api/algo/risk-dashboard/exit-rules — Which exit rules fired most
"""

import psycopg2, json
from typing import Dict, Any
import logging
from datetime import datetime, timedelta, date
from .utils import error_response, success_response, json_response, safe_limit, handle_db_error

logger = logging.getLogger(__name__)


def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
    """Route risk dashboard endpoints."""
    if path == '/api/algo/risk-dashboard':
        return _get_comprehensive_risk_dashboard(cur)
    elif path == '/api/algo/risk-dashboard/drawdown':
        return _get_drawdown_metrics(cur)
    elif path == '/api/algo/risk-dashboard/exposure-tier':
        return _get_exposure_tier_info(cur)
    elif path == '/api/algo/risk-dashboard/position-sizing-audit':
        days = params.get('days', ['30'])
        days_int = safe_limit(days[0], max_val=365, default=30)
        return _get_position_sizing_audit(cur, days_int)
    elif path == '/api/algo/risk-dashboard/stop-loss-audit':
        days = params.get('days', ['30'])
        days_int = safe_limit(days[0], max_val=365, default=30)
        return _get_stop_loss_audit(cur, days_int)
    elif path == '/api/algo/risk-dashboard/exit-rules':
        days = params.get('days', ['30'])
        days_int = safe_limit(days[0], max_val=365, default=30)
        return _get_exit_rules_distribution(cur, days_int)
    else:
        return error_response(404, 'not_found', f'No risk dashboard handler for {path}')


def _get_comprehensive_risk_dashboard(cur) -> Dict:
    """Get all current risk metrics in one view."""
    try:
        result = {
            'timestamp': datetime.now().isoformat(),
            'drawdown': None,
            'exposure_tier': None,
            'vix_metrics': None,
            'position_sizing_stats': None,
            'exit_rules_distribution': None,
        }

        # Drawdown
        try:
            drawdown_info = _fetch_drawdown_info(cur)
            result['drawdown'] = drawdown_info
        except Exception as e:
            logger.warning(f"Drawdown fetch failed: {e}")
            result['drawdown'] = {'error': str(e)}

        # Exposure tier
        try:
            tier_info = _fetch_exposure_tier_info(cur)
            result['exposure_tier'] = tier_info
        except Exception as e:
            logger.warning(f"Exposure tier fetch failed: {e}")
            result['exposure_tier'] = {'error': str(e)}

        # VIX metrics
        try:
            cur.execute("""
                SELECT vix_level FROM market_health_daily
                ORDER BY date DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                vix = float(row[0]) if row[0] else None
                risk_reduction = 1.0
                if vix and vix > 25 and vix < 35:
                    risk_reduction = 0.75
                result['vix_metrics'] = {
                    'vix_level': vix,
                    'caution_threshold': 25.0,
                    'halt_threshold': 35.0,
                    'risk_reduction_multiplier': risk_reduction,
                }
        except Exception as e:
            logger.warning(f"VIX fetch failed: {e}")

        # Position sizing statistics
        try:
            cur.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    AVG(cascade_multiplier) as avg_cascade,
                    MIN(cascade_multiplier) as min_cascade,
                    MAX(cascade_multiplier) as max_cascade,
                    AVG(position_size_pct) as avg_position_size_pct
                FROM algo_position_sizing_audit
                WHERE created_at >= NOW() - INTERVAL '30 days'
            """)
            row = cur.fetchone()
            if row:
                result['position_sizing_stats'] = {
                    'trades_30d': row[0] or 0,
                    'avg_cascade_multiplier': float(row[1]) if row[1] else 1.0,
                    'min_cascade_multiplier': float(row[2]) if row[2] else 1.0,
                    'max_cascade_multiplier': float(row[3]) if row[3] else 1.0,
                    'avg_position_size_pct': float(row[4]) if row[4] else 0,
                }
        except Exception as e:
            logger.warning(f"Position sizing stats fetch failed: {e}")

        # Exit rules distribution (top 5)
        try:
            cur.execute("""
                SELECT exit_rule, COUNT(*) as count
                FROM algo_exit_rules_distribution
                WHERE created_at >= NOW() - INTERVAL '30 days'
                GROUP BY exit_rule
                ORDER BY count DESC
                LIMIT 5
            """)
            rules = {}
            for row in cur.fetchall():
                rules[row[0]] = row[1]
            result['exit_rules_distribution'] = rules
        except Exception as e:
            logger.warning(f"Exit rules fetch failed: {e}")

        return json_response(200, result)
    except Exception as e:
        return handle_db_error(e, logger, 'fetch comprehensive risk dashboard')


def _fetch_drawdown_info(cur) -> Dict[str, Any]:
    """Get current portfolio drawdown and thresholds."""
    cur.execute("""
        SELECT MAX(total_portfolio_value) as peak,
               (SELECT total_portfolio_value FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1) as current
        FROM algo_portfolio_snapshots
    """)
    row = cur.fetchone()
    if not row or not row[0] or not row[1]:
        return {'current_drawdown_pct': 0, 'status': 'no_history'}

    peak = float(row[0])
    current = float(row[1])
    drawdown_pct = ((peak - current) / peak) * 100 if peak > 0 else 0

    return {
        'current_drawdown_pct': max(0, drawdown_pct),
        'peak_portfolio_value': peak,
        'current_portfolio_value': current,
        'thresholds': {
            'caution_5pct': -5.0,
            'caution_10pct': -10.0,
            'caution_15pct': -15.0,
            'halt_20pct': -20.0,
        },
        'risk_multipliers': {
            'at_minus_5': 0.75,
            'at_minus_10': 0.5,
            'at_minus_15': 0.25,
            'at_minus_20': 0.0,
        },
        'status': _get_drawdown_status(drawdown_pct),
    }


def _fetch_exposure_tier_info(cur) -> Dict[str, Any]:
    """Get current market exposure tier (NORMAL/CAUTION/PRESSURE)."""
    try:
        cur.execute("""
            SELECT exposure_pct, exposure_tier, rationale
            FROM market_exposure_daily
            ORDER BY date DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            exposure_pct = float(row[0]) if row[0] else 100
            tier = row[1] or 'NORMAL'
            rationale = row[2] or 'No data'
            return {
                'current_tier': tier,
                'exposure_pct': exposure_pct,
                'rationale': rationale,
                'position_size_multiplier': {
                    'NORMAL': 1.0,
                    'CAUTION': 0.75,
                    'PRESSURE': 0.5,
                    'HALT': 0.0,
                }.get(tier, 1.0),
            }
    except Exception:
        pass

    return {
        'current_tier': 'NORMAL',
        'exposure_pct': 100,
        'rationale': 'Default (no data)',
        'position_size_multiplier': 1.0,
    }


def _get_drawdown_metrics(cur) -> Dict:
    """GET /api/algo/risk-dashboard/drawdown"""
    try:
        info = _fetch_drawdown_info(cur)
        return json_response(200, info)
    except Exception as e:
        return handle_db_error(e, logger, 'fetch drawdown metrics')


def _get_exposure_tier_info(cur) -> Dict:
    """GET /api/algo/risk-dashboard/exposure-tier"""
    try:
        info = _fetch_exposure_tier_info(cur)
        return json_response(200, info)
    except Exception as e:
        return handle_db_error(e, logger, 'fetch exposure tier info')


def _get_position_sizing_audit(cur, days: int) -> Dict:
    """GET /api/algo/risk-dashboard/position-sizing-audit?days=30"""
    try:
        cur.execute("""
            SELECT symbol, signal_date, entry_price, stop_loss_price,
                   base_shares, final_shares, position_size_pct,
                   cascade_multiplier, reasons_json, created_at
            FROM algo_position_sizing_audit
            WHERE created_at >= NOW() - INTERVAL '%d days'
            ORDER BY created_at DESC
            LIMIT 100
        """ % days)

        items = []
        for row in cur.fetchall():
            try:
                reasons = json.loads(row[8]) if row[8] else {}
            except (json.JSONDecodeError, TypeError):
                reasons = {}

            items.append({
                'symbol': row[0],
                'signal_date': row[1].isoformat() if row[1] else None,
                'entry_price': float(row[2]) if row[2] else None,
                'stop_loss_price': float(row[3]) if row[3] else None,
                'base_shares': row[4],
                'final_shares': row[5],
                'position_size_pct': float(row[6]) if row[6] else 0,
                'cascade_multiplier': float(row[7]) if row[7] else 1.0,
                'reasons': reasons,
                'created_at': row[9].isoformat() if row[9] else None,
            })

        return json_response(200, {'items': items})
    except Exception as e:
        return handle_db_error(e, logger, 'fetch position sizing audit')


def _get_stop_loss_audit(cur, days: int) -> Dict:
    """GET /api/algo/risk-dashboard/stop-loss-audit?days=30"""
    try:
        cur.execute("""
            SELECT symbol, signal_date, entry_price, stop_loss_price,
                   distance_pct, stop_method, stop_reasoning, candidates_json, created_at
            FROM algo_stop_loss_audit
            WHERE created_at >= NOW() - INTERVAL '%d days'
            ORDER BY created_at DESC
            LIMIT 100
        """ % days)

        items = []
        for row in cur.fetchall():
            try:
                candidates = json.loads(row[7]) if row[7] else {}
            except (json.JSONDecodeError, TypeError):
                candidates = {}

            items.append({
                'symbol': row[0],
                'signal_date': row[1].isoformat() if row[1] else None,
                'entry_price': float(row[2]) if row[2] else None,
                'stop_loss_price': float(row[3]) if row[3] else None,
                'distance_pct': float(row[4]) if row[4] else 0,
                'stop_method': row[5],
                'stop_reasoning': row[6],
                'candidates': candidates,
                'created_at': row[8].isoformat() if row[8] else None,
            })

        return json_response(200, {'items': items})
    except Exception as e:
        return handle_db_error(e, logger, 'fetch stop loss audit')


def _get_exit_rules_distribution(cur, days: int) -> Dict:
    """GET /api/algo/risk-dashboard/exit-rules?days=30"""
    try:
        cur.execute("""
            SELECT exit_rule, COUNT(*) as count,
                   AVG(pnl_pct) as avg_pnl_pct,
                   AVG(r_multiple) as avg_r_multiple,
                   COUNT(CASE WHEN pnl_dollars > 0 THEN 1 END) as winning_count,
                   COUNT(CASE WHEN pnl_dollars < 0 THEN 1 END) as losing_count
            FROM algo_exit_rules_distribution
            WHERE created_at >= NOW() - INTERVAL '%d days'
            GROUP BY exit_rule
            ORDER BY count DESC
        """ % days)

        items = []
        for row in cur.fetchall():
            items.append({
                'exit_rule': row[0],
                'count': row[1],
                'avg_pnl_pct': float(row[2]) if row[2] else 0,
                'avg_r_multiple': float(row[3]) if row[3] else 0,
                'winning_count': row[4] or 0,
                'losing_count': row[5] or 0,
                'win_rate_pct': (row[4] / row[1] * 100) if row[1] > 0 else 0,
            })

        return json_response(200, {'items': items})
    except Exception as e:
        return handle_db_error(e, logger, 'fetch exit rules distribution')


def _get_drawdown_status(drawdown_pct: float) -> str:
    """Determine drawdown status."""
    if drawdown_pct >= 20:
        return 'HALT'
    elif drawdown_pct >= 15:
        return 'SEVERE'
    elif drawdown_pct >= 10:
        return 'CAUTION'
    elif drawdown_pct >= 5:
        return 'CAUTION'
    else:
        return 'NORMAL'
