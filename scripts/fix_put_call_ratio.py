#!/usr/bin/env python3
"""Fix stale put_call_ratio values in database."""

import logging
from utils.db import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Clear the stale 0.0 put_call_ratio values from market_health_daily
try:
    with DatabaseContext('write') as cur:
        # Check current state
        cur.execute('''
            SELECT date, put_call_ratio, put_call_ratio_data_unavailable
            FROM market_health_daily
            WHERE put_call_ratio = 0.0 OR (put_call_ratio IS NOT NULL AND put_call_ratio < 0.2)
            ORDER BY date DESC LIMIT 10
        ''')
        rows = cur.fetchall()

        print(f'Found {len(rows)} records with invalid put_call_ratio values:')
        for row in rows:
            print(f'  {row[0]}: ratio={row[1]}, marked_unavailable={row[2]}')

        if rows:
            # Update these records to mark data as unavailable
            cur.execute('''
                UPDATE market_health_daily
                SET put_call_ratio = NULL,
                    put_call_ratio_data_unavailable = TRUE,
                    put_call_ratio_unavailable_reason = 'Invalid ratio - outside realistic range (0.2-3.0)'
                WHERE put_call_ratio = 0.0 OR (put_call_ratio IS NOT NULL AND put_call_ratio < 0.2)
            ''')
            print(f'\nUpdated {cur.rowcount} records to mark put_call_ratio as unavailable')

except Exception as e:
    logger.error(f'Error: {e}', exc_info=True)
