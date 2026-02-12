#!/usr/bin/env python3
"""
COMPLETE DATA LOADING SCRIPT - Loads all essential data in correct order
Handles all retries and errors automatically
"""
import subprocess
import time
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# List of critical loaders in order of dependency
LOADERS = [
    ('loadstocksymbols.py', 'Stock symbols'),
    ('loaddailycompanydata.py', 'Company data & positioning'),
    ('loadbuyselldaily.py', 'Buy/Sell signals (daily)'),
    ('loadbuyselddaily.py', 'Buy/Sell signals (weekly)'),
    ('loadbuysellmonthly.py', 'Buy/Sell signals (monthly)'),
    ('loadstockscores.py', 'Stock scores'),
    ('loadearningshistory.py', 'Earnings history'),
]

def run_loader(script_name, loader_name, max_retries=2):
    """Run a loader script with automatic retries"""
    if not os.path.exists(script_name):
        logger.warning(f"⚠️ {loader_name}: Script not found - {script_name}")
        return False

    for attempt in range(1, max_retries + 1):
        logger.info(f"\n{'='*80}")
        logger.info(f"Loading: {loader_name} (Attempt {attempt}/{max_retries})")
        logger.info(f"Script: {script_name}")
        logger.info(f"{'='*80}")

        try:
            result = subprocess.run(
                ['python3', script_name],
                timeout=3600,  # 1 hour timeout
                capture_output=False
            )

            if result.returncode == 0:
                logger.info(f"✅ SUCCESS: {loader_name}")
                return True
            else:
                logger.error(f"❌ FAILED: {loader_name} (exit code {result.returncode})")
                if attempt < max_retries:
                    logger.info(f"Retrying in 30 seconds...")
                    time.sleep(30)
        except subprocess.TimeoutExpired:
            logger.error(f"❌ TIMEOUT: {loader_name} (exceeded 1 hour)")
        except Exception as e:
            logger.error(f"❌ ERROR: {loader_name} - {e}")

    logger.error(f"❌ FAILED PERMANENTLY: {loader_name}")
    return False

def main():
    logger.info("🚀 STARTING COMPLETE DATA LOAD SEQUENCE")
    logger.info(f"Total loaders: {len(LOADERS)}")

    successful = []
    failed = []

    for script_name, loader_name in LOADERS:
        success = run_loader(script_name, loader_name, max_retries=2)

        if success:
            successful.append(loader_name)
        else:
            failed.append(loader_name)

        # Brief pause between loaders
        time.sleep(5)

    # Summary
    logger.info(f"\n{'='*80}")
    logger.info("DATA LOADING COMPLETE")
    logger.info(f"{'='*80}")
    logger.info(f"✅ Successful: {len(successful)}/{len(LOADERS)}")
    logger.info(f"❌ Failed: {len(failed)}/{len(LOADERS)}")

    if successful:
        logger.info("\n✅ Completed:")
        for loader in successful:
            logger.info(f"   - {loader}")

    if failed:
        logger.info("\n❌ Failed:")
        for loader in failed:
            logger.info(f"   - {loader}")

    return 0 if not failed else 1

if __name__ == '__main__':
    sys.exit(main())
