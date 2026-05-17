#!/usr/bin/env python3
import os
import re
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

stats = {
    'files_processed': 0,
    'logs_removed': 0,
    'files_modified': 0,
}

SKIP_DIRS = {'node_modules', '.git', 'dist', 'build', '.next', '__pycache__'}

def clean_js_file(filepath):
    """Remove debug console.log from JS files."""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    removed = 0
    new_lines = []

    for line in lines:
        # Skip pure console.log lines
        if re.match(r'\s*console\.log\(', line):
            if not any(x in line for x in ['error', 'warn', 'logger']):
                removed += 1
                continue
        new_lines.append(line)

    if removed > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

    return removed

def main():
    logger.info('\n[CLEANUP] Starting console log removal...\n')

    files_to_process = []
    for root, dirs, filenames in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in filenames:
            if f.endswith(('.js', '.jsx')):
                filepath = os.path.join(root, f)
                if 'node_modules' not in filepath and '.git' not in filepath:
                    files_to_process.append(filepath)

    logger.info(f'Found {len(files_to_process)} JS files\n')

    for filepath in sorted(files_to_process):
        try:
            removed = clean_js_file(filepath)
            stats['files_processed'] += 1
            stats['logs_removed'] += removed
            if removed > 0:
                stats['files_modified'] += 1
                logger.info(f"  [OK] {filepath} (removed {removed})")
        except Exception as e:
            logger.info(f"  [SKIP] {filepath}: {e}")

    logger.info(f'\n{"=" * 60}')
    logger.info(f'[CLEANUP] COMPLETE')
    logger.info(f'{"=" * 60}')
    logger.info(f'Files: {stats["files_processed"]} processed, {stats["files_modified"]} modified')
    logger.info(f'Logs removed: {stats["logs_removed"]}')
    logger.info(f'{"=" * 60}\n')

if __name__ == '__main__':
    main()
