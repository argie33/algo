#!/usr/bin/env python3
"""
Data patrol check for sector_rotation_signal JSON validity.

Validates that the details column contains valid JSON and logs any issues.
Part of the data patrol system to catch data quality issues early.
"""

import json
import logging
from datetime import datetime
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

def check_sector_rotation_json():
    """Check sector_rotation_signal.details for valid JSON. Returns (passed, issues_count, details)"""
    try:
        with DatabaseContext('read') as cur:
            cur.execute(
                """SELECT id, date, sector, details
                   FROM sector_rotation_signal
                   WHERE details IS NOT NULL
                   LIMIT 1000"""
            )
            rows = cur.fetchall()

        if not rows:
            logger.info("No sector_rotation_signal rows to check")
            return True, 0, "No data"

        invalid_count = 0
        invalid_samples = []

        for row_id, date, sector, details in rows:
            if isinstance(details, dict):
                continue
            if isinstance(details, str):
                try:
                    json.loads(details)
                except (json.JSONDecodeError, ValueError):
                    invalid_count += 1
                    if len(invalid_samples) < 5:
                        invalid_samples.append({
                            'id': row_id,
                            'date': str(date),
                            'sector': sector,
                            'details_preview': details[:100] if details else None
                        })
            else:
                invalid_count += 1
                if len(invalid_samples) < 5:
                    invalid_samples.append({
                        'id': row_id,
                        'date': str(date),
                        'sector': sector,
                        'type': type(details).__name__
                    })

        if invalid_count == 0:
            logger.info(f"✓ sector_rotation_signal.details: All {len(rows)} rows have valid JSON")
            return True, 0, f"Valid JSON in {len(rows)} rows"
        else:
            logger.error(
                f"✗ sector_rotation_signal.details: {invalid_count} rows with invalid JSON\n"
                f"Samples: {json.dumps(invalid_samples, indent=2)}"
            )
            return False, invalid_count, f"{invalid_count} invalid JSON rows (samples logged)"

    except Exception as e:
        logger.error(f"Error checking sector_rotation_signal JSON: {e}", exc_info=True)
        return False, -1, f"Check failed: {str(e)}"

if __name__ == '__main__':
    passed, count, details = check_sector_rotation_json()
    print(f"Passed: {passed}, Issues: {count}, Details: {details}")
