#!/usr/bin/env python3
"""
Local development API server that wraps Lambda handlers for testing dashboard locally.

This server imports the Lambda handler functions and exposes them via HTTP endpoints
so the dashboard can test against local database without deploying to AWS Lambda.

Usage:
    python dev_api_server.py

Then dashboard can connect to http://localhost:8000/api/algo/scores etc.
"""

import os
import sys
import json
import logging
from typing import Any

# CRITICAL: Force local database for development, not AWS
os.environ.pop('FORCE_AWS', None)
os.environ.pop('DB_SECRET_ARN', None)
os.environ['DB_HOST'] = 'localhost'
os.environ['DB_USER'] = 'postgres'
os.environ['DB_PASSWORD'] = 'postgres'
os.environ['DB_NAME'] = 'stocks'
os.environ['DB_PORT'] = '5432'

import flask
from werkzeug.exceptions import HTTPException

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lambda', 'api'))
sys.path.insert(0, os.path.dirname(__file__))

from routes.algo_handlers.dashboard import (
    _get_algo_positions,
    _get_dashboard_scores,
    _get_algo_trades,
    _get_equity_curve,
)
from config.credential_manager import get_db_config
import psycopg2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = flask.Flask(__name__)


def get_db_cursor():
    """Get a database cursor for route handlers."""
    try:
        config = get_db_config()
        conn = psycopg2.connect(**config)
        return conn.cursor(), conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise


@app.route('/api/algo/scores', methods=['GET'])
def scores():
    """Scores endpoint - wraps Lambda handler."""
    try:
        cur, conn = get_db_cursor()
        result = _get_dashboard_scores(cur)
        cur.close()
        conn.close()

        if isinstance(result, tuple) and len(result) >= 2:
            status_code, response = result[0], result[1]
            return flask.jsonify(response), status_code
        else:
            return flask.jsonify(result), 200
    except Exception as e:
        logger.error(f"Scores endpoint error: {e}")
        return flask.jsonify({'error': str(e)}), 500


@app.route('/api/algo/positions', methods=['GET'])
def positions():
    """Positions endpoint - wraps Lambda handler."""
    try:
        cur, conn = get_db_cursor()
        result = _get_algo_positions(cur)
        cur.close()
        conn.close()

        if isinstance(result, tuple) and len(result) >= 2:
            status_code, response = result[0], result[1]
            return flask.jsonify(response), status_code
        else:
            return flask.jsonify(result), 200
    except Exception as e:
        logger.error(f"Positions endpoint error: {e}")
        return flask.jsonify({'error': str(e)}), 500


@app.route('/api/algo/performance', methods=['GET'])
def performance():
    """Performance endpoint - wraps Lambda handler."""
    try:
        cur, conn = get_db_cursor()
        result = _get_equity_curve(cur)
        cur.close()
        conn.close()

        if isinstance(result, tuple) and len(result) >= 2:
            status_code, response = result[0], result[1]
            return flask.jsonify(response), status_code
        else:
            return flask.jsonify(result), 200
    except Exception as e:
        logger.error(f"Performance endpoint error: {e}")
        return flask.jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    try:
        config = get_db_config()
        conn = psycopg2.connect(**config, connect_timeout=5)
        conn.close()
        return flask.jsonify({'status': 'ok', 'database': 'connected'}), 200
    except Exception as e:
        return flask.jsonify({'status': 'error', 'database': str(e)}), 503


@app.errorhandler(HTTPException)
def handle_exception(e):
    """Handle HTTP exceptions."""
    return flask.jsonify({'error': e.description}), e.code


if __name__ == '__main__':
    logger.info("Starting development API server...")
    logger.info("Dashboard can connect to: http://localhost:8000/api/algo/scores")
    logger.info("Health check: http://localhost:8000/health")

    app.run(host='0.0.0.0', port=8000, debug=True, use_reloader=False)
