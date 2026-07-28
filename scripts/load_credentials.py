#!/usr/bin/env python3
"""
Load Alpaca credentials from database and set environment variables.

This ensures credentials persist across runs without files or secrets.
Credentials are stored in algo_config table and loaded before orchestrator/loader execution.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging

import psycopg2

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)


def load_credentials_from_database() -> dict[str, str]:
    """Load Alpaca credentials from algo_config database table.

    Returns:
        Dict with keys: APCA_API_KEY_ID, APCA_API_SECRET_KEY, APCA_API_BASE_URL
    """
    try:
        conn = psycopg2.connect(
            dbname=os.getenv('DB_NAME', 'stocks'),
            user=os.getenv('DB_USER', 'stocks'),
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', '5432'),
        )
        cur = conn.cursor()

        # Map database keys to environment variable names
        config_keys = {
            'alpaca_api_key': 'APCA_API_KEY_ID',
            'alpaca_api_secret': 'APCA_API_SECRET_KEY',
            'alpaca_api_key_id': 'APCA_API_KEY_ID',  # Alternative name
            'alpaca_api_secret_key': 'APCA_API_SECRET_KEY',  # Alternative name
            'alpaca_base_url': 'APCA_API_BASE_URL',
        }

        credentials = {}

        # Try both naming conventions (snake_case and explicit names)
        for db_key, env_var in config_keys.items():
            cur.execute(
                'SELECT value FROM algo_config WHERE key = %s',
                (db_key,)
            )
            row = cur.fetchone()
            if row and row[0]:
                credentials[env_var] = row[0]
                logger.debug(f'[CREDS] Loaded {env_var} from database ({db_key})')

        conn.close()

        # Validate required credentials
        if 'APCA_API_KEY_ID' not in credentials:
            logger.error('[CREDS] APCA_API_KEY_ID not found in database (checked: alpaca_api_key, alpaca_api_key_id)')
            raise ValueError('Alpaca API key not found in database')

        if 'APCA_API_SECRET_KEY' not in credentials:
            logger.error('[CREDS] APCA_API_SECRET_KEY not found in database (checked: alpaca_api_secret, alpaca_api_secret_key)')
            raise ValueError('Alpaca API secret not found in database')

        # Set defaults
        if 'APCA_API_BASE_URL' not in credentials:
            credentials['APCA_API_BASE_URL'] = 'https://paper-api.alpaca.markets'
            logger.info('[CREDS] Using default APCA_API_BASE_URL: https://paper-api.alpaca.markets')

        return credentials

    except psycopg2.OperationalError as e:
        logger.error(f'[CREDS] Database connection failed: {e}')
        raise
    except Exception as e:
        logger.error(f'[CREDS] Failed to load credentials: {e}')
        raise


def set_environment_variables(credentials: dict[str, str]) -> None:
    """Set environment variables from credentials dict."""
    for env_var, value in credentials.items():
        os.environ[env_var] = value
        # Don't log actual secrets
        logger.info(f'[CREDS] Set {env_var} (length: {len(value)} chars)')


def ensure_credentials_loaded() -> dict[str, str]:
    """
    Ensure Alpaca credentials are loaded and available.

    Priority:
    1. Check environment variables (already set)
    2. Load from database if not set

    Returns:
        Dict with credentials that are now set in environment
    """
    # Check if already set
    if os.getenv('APCA_API_KEY_ID') and os.getenv('APCA_API_SECRET_KEY'):
        logger.info('[CREDS] Alpaca credentials already in environment')
        return {
            'APCA_API_KEY_ID': os.getenv('APCA_API_KEY_ID'),
            'APCA_API_SECRET_KEY': os.getenv('APCA_API_SECRET_KEY'),
            'APCA_API_BASE_URL': os.getenv('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets'),
        }

    # Load from database
    logger.info('[CREDS] Loading Alpaca credentials from database...')
    credentials = load_credentials_from_database()
    set_environment_variables(credentials)
    logger.info('[CREDS] Alpaca credentials loaded and set successfully')

    return credentials


if __name__ == '__main__':
    try:
        creds = ensure_credentials_loaded()
        print('[SUCCESS] Credentials loaded:')
        for key in ['APCA_API_KEY_ID', 'APCA_API_SECRET_KEY', 'APCA_API_BASE_URL']:
            if key in creds:
                print(f'  {key}: SET')
        sys.exit(0)
    except Exception as e:
        print(f'[ERROR] {e}', file=sys.stderr)
        sys.exit(1)
