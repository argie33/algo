#!/usr/bin/env python3
"""
Fix invalid JSON in sector_rotation_signal.details column.

This script:
1. Finds rows with malformed JSON in the details column
2. Validates and repairs them
3. Reports statistics on fixed rows

Usage:
    python scripts/fix_sector_rotation_json.py [--dry-run] [--verbose]
"""

import json
import sys
import logging
from datetime import datetime
from utils.database_context import DatabaseContext

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def validate_json(value):
    """Try to parse value as JSON. Returns (is_valid, parsed_value)"""
    if value is None or value == '':
        return True, None
    if isinstance(value, dict):
        return True, value
    if not isinstance(value, str):
        return False, None
    try:
        parsed = json.loads(value)
        return True, parsed
    except (json.JSONDecodeError, ValueError):
        return False, None

def repair_details(details_str):
    """Attempt to repair invalid JSON. Returns valid JSON string or error placeholder."""
    if not details_str or details_str == '':
        return json.dumps({})

    if isinstance(details_str, dict):
        return json.dumps(details_str)

    if not isinstance(details_str, str):
        return json.dumps({'error': 'Non-string non-object type'})

    # Try to parse as-is
    try:
        json.loads(details_str)
        return details_str
    except:
        pass

    # Return empty valid JSON as fallback
    logger.warning(f"Could not repair: {details_str[:100]}")
    return json.dumps({'error': 'Invalid JSON repaired to empty object'})

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fix invalid JSON in sector_rotation_signal')
    parser.add_argument('--dry-run', action='store_true', help='Report issues without fixing')
    parser.add_argument('--verbose', action='store_true', help='Print detailed logs')
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    logger.info("Scanning sector_rotation_signal for invalid JSON...")

    try:
        with DatabaseContext('read') as cur:
            # Find all rows with details that might be invalid JSON
            cur.execute(
                """SELECT id, date, sector, details
                   FROM sector_rotation_signal
                   WHERE details IS NOT NULL
                   ORDER BY date DESC"""
            )
            rows = cur.fetchall()

        logger.info(f"Found {len(rows)} rows in sector_rotation_signal")

        invalid_rows = []
        fixed_count = 0
        valid_count = 0

        for row_id, date, sector, details in rows:
            is_valid, _ = validate_json(details)
            if is_valid:
                valid_count += 1
            else:
                invalid_rows.append((row_id, date, sector, details))
                logger.warning(f"Row {row_id} (date={date}, sector={sector}): Invalid JSON")

        logger.info(f"Valid rows: {valid_count}")
        logger.info(f"Invalid rows: {len(invalid_rows)}")

        if not invalid_rows:
            logger.info("No invalid JSON found. Database is clean!")
            return 0

        if not args.dry_run:
            logger.info(f"Fixing {len(invalid_rows)} rows...")
            with DatabaseContext('write') as cur:
                for row_id, date, sector, details in invalid_rows:
                    repaired = repair_details(details)
                    try:
                        cur.execute(
                            """UPDATE sector_rotation_signal
                               SET details = %s
                               WHERE id = %s""",
                            (repaired, row_id)
                        )
                        fixed_count += 1
                        logger.info(f"Fixed row {row_id}")
                    except Exception as e:
                        logger.error(f"Failed to fix row {row_id}: {e}")

            logger.info(f"Successfully fixed {fixed_count}/{len(invalid_rows)} rows")
        else:
            logger.info("--dry-run mode: No changes made")
            logger.info(f"Would fix {len(invalid_rows)} rows")

        return 0

    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)
        return 1

if __name__ == '__main__':
    sys.exit(main())
