#!/usr/bin/env python3
"""Local development API server for dashboard testing."""

import os
import sys
import logging

os.environ.pop('FORCE_AWS', None)
os.environ.pop('DB_SECRET_ARN', None)
os.environ['DB_HOST'] = 'localhost'
os.environ['DB_USER'] = 'postgres'
os.environ['DB_PASSWORD'] = 'postgres'
os.environ['DB_NAME'] = 'stocks'
os.environ['DB_PORT'] = '5432'

import flask
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lambda', 'api'))
sys.path.insert(0, os.path.dirname(__file__))

from routes.algo_handlers.dashboard import (
    _get_algo_positions,
    _get_dashboard_scores,
    _get_algo_trades,
    _get_equity_curve,
    _get_algo_status,
    _get_dashboard_signals,
    _get_circuit_breakers,
)
from routes.algo_handlers.market import (
    _get_markets,
    _get_market_sentiment,
)
from routes.algo_handlers.monitoring import (
    _get_notifications,
)
from routes.algo_handlers.metrics import (
    _get_algo_portfolio,
    _get_daily_return_histogram,
    _get_holding_period_distribution,
    _get_stage_distribution,
    _get_trade_distribution,
)
from config.credential_manager import get_db_config
import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = flask.Flask(__name__)


def get_db_cursor():
    config = get_db_config()
    conn = psycopg2.connect(**config)
    # Use DictCursor so rows can be accessed as dicts (not tuples)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    return cur, conn


def safe_call(handler_func):
    try:
        cur, conn = get_db_cursor()
        logger.info(f"[safe_call] Calling {handler_func.__name__}...")

        # Validate cursor is valid before calling handler
        try:
            cur.execute("SELECT 1")
            _ = cur.fetchone()
            logger.debug("[safe_call] Cursor validation: OK")
        except Exception as e:
            logger.error(f"[safe_call] Cursor validation failed: {type(e).__name__}: {e}")
            raise RuntimeError(f"Database cursor invalid: {e}") from e
        result = handler_func(cur)
        cur.close()
        conn.close()

        result_type = type(result).__name__
        status = result.get('statusCode') if isinstance(result, dict) else 'N/A'
        logger.info(f"[safe_call] {handler_func.__name__} returned {result_type}, statusCode={status}")

        if isinstance(result, tuple) and len(result) >= 2:
            logger.info(f"[safe_call] Result is tuple, returning tuple[1] and tuple[0]")
            return result[1], result[0]

        # CRITICAL FIX: Use statusCode from response dict, not hardcoded 200
        # Handler functions return error responses with proper HTTP status codes (500, 503, etc)
        # Using statusCode 200 for all responses breaks error handling in the dashboard
        if isinstance(result, dict) and 'statusCode' in result:
            status_code = result.get('statusCode', 200)
            logger.info(f"[safe_call] Returning dict with statusCode {status_code}")
            return result, status_code
        logger.info(f"[safe_call] Result is not dict with statusCode, returning as-is with 200")
        return result, 200
    except Exception as e:
        # Log full traceback to help debug handler failures
        import traceback
        tb = traceback.format_exc()
        logger.error(f"[safe_call] {handler_func.__name__} EXCEPTION:\n{tb}")
        error_detail = str(e)[:500]  # Limit error message length
        logger.error(f"[safe_call] Returning error response: {error_detail}")
        return {'error': error_detail, 'statusCode': 500}, 500


@app.route('/api/algo/scores', methods=['GET'])
def scores():
    data, code = safe_call(_get_dashboard_scores)
    return flask.jsonify(data), code


@app.route('/api/algo/positions', methods=['GET'])
def positions():
    data, code = safe_call(_get_algo_positions)
    return flask.jsonify(data), code


@app.route('/api/algo/performance', methods=['GET'])
def performance():
    data, code = safe_call(_get_equity_curve)
    return flask.jsonify(data), code


@app.route('/api/algo/portfolio', methods=['GET'])
def portfolio():
    data, code = safe_call(_get_algo_portfolio)
    return flask.jsonify(data), code


@app.route('/api/algo/trades', methods=['GET'])
def trades():
    data, code = safe_call(_get_algo_trades)
    return flask.jsonify(data), code


@app.route('/api/algo/markets', methods=['GET'])
def markets():
    data, code = safe_call(_get_markets)
    return flask.jsonify(data), code


@app.route('/api/algo/status', methods=['GET'])
def status():
    data, code = safe_call(_get_algo_status)
    return flask.jsonify(data), code


@app.route('/api/algo/signals', methods=['GET'])
def signals():
    data, code = safe_call(_get_dashboard_signals)
    return flask.jsonify(data), code


@app.route('/api/algo/circuit-breakers', methods=['GET'])
def circuit_breakers():
    data, code = safe_call(_get_circuit_breakers)
    return flask.jsonify(data), code


@app.route('/api/algo/daily-return-histogram', methods=['GET'])
def daily_return_histogram():
    data, code = safe_call(_get_daily_return_histogram)
    return flask.jsonify(data), code


@app.route('/api/algo/holding-period-distribution', methods=['GET'])
def holding_period_distribution():
    data, code = safe_call(_get_holding_period_distribution)
    return flask.jsonify(data), code


@app.route('/api/algo/stage-distribution', methods=['GET'])
def stage_distribution():
    data, code = safe_call(_get_stage_distribution)
    return flask.jsonify(data), code


@app.route('/api/algo/trade-distribution', methods=['GET'])
def trade_distribution():
    data, code = safe_call(_get_trade_distribution)
    return flask.jsonify(data), code


@app.route('/api/algo/notifications', methods=['GET'])
def notifications():
    data, code = safe_call(_get_notifications)
    return flask.jsonify(data), code


@app.route('/api/market/sentiment', methods=['GET'])
def market_sentiment():
    data, code = safe_call(_get_market_sentiment)
    return flask.jsonify(data), code


@app.route('/health', methods=['GET'])
def health():
    try:
        config = get_db_config()
        conn = psycopg2.connect(**config, connect_timeout=5)
        conn.close()
        return flask.jsonify({'status': 'ok', 'database': 'connected'}), 200
    except Exception as e:
        return flask.jsonify({'status': 'error', 'database': str(e)}), 503


if __name__ == '__main__':
    logger.info("Starting development API server on 0.0.0.0:3001")
    logger.info("Routes:")
    for rule in app.url_map.iter_rules():
        if str(rule).startswith('/api') or str(rule) == '/health':
            logger.info(f"  {rule}")
    app.run(host='0.0.0.0', port=3001, debug=False, use_reloader=False)
