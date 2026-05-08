#!/usr/bin/env python3
"""
Systematically fix all remaining resource leaks.
Focus on supporting modules and data loaders.
"""

import os
import logging

logger = logging.getLogger(__name__)
import re
from pathlib import Path

def find_unprotected_connections(filepath):
    """Find psycopg2.connect calls without proper try-finally wrapping."""
    with open(filepath, 'r', errors='ignore') as f:
        content = f.read()

    if 'psycopg2.connect' not in content:
        return False

    # Check if file has proper try-finally pattern
    # Pattern: try: ... psycopg2.connect ... finally: ... close()
    if re.search(r'try:\s*.*psycopg2\.connect.*finally:\s*.*\.close\(\)', content, re.DOTALL):
        return False

    return True

def main():
    logger.info("=" * 80)
    logger.info(f"IDENTIFYING ALL REMAINING RESOURCE LEAKS")
    logger.info("=" * 80)

    # Categorize files
    supporting_modules = []
    data_loaders = []
    other_files = []

    for py_file in sorted(Path('.').glob('*.py')):
        if py_file.name.startswith('fix_') or 'test' in py_file.name.lower():
            continue

        if find_unprotected_connections(str(py_file)):
            if py_file.name.startswith('load'):
                data_loaders.append(py_file.name)
            elif py_file.name.startswith('algo_'):
                supporting_modules.append(py_file.name)
            else:
                other_files.append(py_file.name)

    logger.info(f"\nSUPPORTING MODULES WITH RESOURCE LEAKS")
    logger.info("-" * 80)
    logger.info(f"Found {len(supporting_modules)} files:")
    for f in supporting_modules:
        logger.info(f"  {f}")

    logger.info(f"\nDATA LOADERS WITH RESOURCE LEAKS")
    logger.info("-" * 80)
    logger.info(f"Found {len(data_loaders)} files:")
    for f in data_loaders[:10]:
        logger.info(f"  {f}")
    if len(data_loaders) > 10:
        logger.info(f"  ... and {len(data_loaders) - 10} more")

    logger.info(f"\nOTHER FILES WITH RESOURCE LEAKS")
    logger.info("-" * 80)
    logger.info(f"Found {len(other_files)} files:")
    for f in other_files:
        logger.info(f"  {f}")

    total = len(supporting_modules) + len(data_loaders) + len(other_files)
    logger.info(f"\n{'=' * 80}")
    logger.info(f"TOTAL: {total} files need fixing")
    logger.info(f"  Supporting modules: {len(supporting_modules)}")
    logger.info(f"  Data loaders: {len(data_loaders)}")
    logger.info(f"  Other files: {len(other_files)}")
    logger.info(f"\nEstimated effort: 4-5 hours total")
    logger.info(f"Status: Ready to execute systematic fixes")

if __name__ == '__main__':
    main()
