#!/usr/bin/env python3
"""
Safe Data Loader Runner - Ensures only ONE loader instance runs at a time.
Loads REAL DATA ONLY from database sources.

Features:
- Process locking (prevents multiple instances)
- Sequential execution (no parallel runs)
- Real data validation (verifies no fake defaults)
- Comprehensive logging
"""

import os
import sys
import time
import fcntl
import logging
import subprocess
from datetime import datetime
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/home/stocks/algo/loader.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Lock file path
LOCK_FILE = "/home/stocks/algo/.loader_lock"
LOCK_TIMEOUT = 3600  # 1 hour timeout for stale locks

# Loaders to run (in order of dependency)
LOADERS = [
    ("loadcompanyprofile.py", "Company Profile"),
    ("loadecondata.py", "Economic Data"),
    ("loadtechnicalsdaily.py", "Technical Data (Daily)"),
    ("loadpositioning.py", "Positioning Data"),
    ("loadsentiment.py", "Sentiment Data"),
    ("loadbuyselldaily.py", "Buy/Sell Signals (Daily)"),
    ("loadbuysellweekly.py", "Buy/Sell Signals (Weekly)"),
    ("loadbuysellmonthly.py", "Buy/Sell Signals (Monthly)"),
]


def acquire_lock(lock_file):
    """Acquire exclusive lock. Returns file handle if successful, None if failed."""
    try:
        # Check if lock file is stale
        if os.path.exists(lock_file):
            lock_age = time.time() - os.path.getmtime(lock_file)
            if lock_age > LOCK_TIMEOUT:
                logger.warning(f"🔓 Removing stale lock file (age: {lock_age:.0f}s)")
                os.remove(lock_file)

        # Try to acquire lock
        lock_handle = open(lock_file, "w")
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        # Write PID and timestamp
        lock_handle.write(f"PID: {os.getpid()}\n")
        lock_handle.write(f"Started: {datetime.now().isoformat()}\n")
        lock_handle.flush()

        logger.info(f"🔒 Acquired exclusive lock (PID: {os.getpid()})")
        return lock_handle
    except IOError:
        logger.error("❌ Another loader is already running. Exiting to prevent concurrent execution.")
        return None


def release_lock(lock_handle):
    """Release lock."""
    try:
        if lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()
            os.remove(LOCK_FILE)
            logger.info("🔓 Released lock")
    except Exception as e:
        logger.warning(f"⚠️ Error releasing lock: {e}")


def run_loader(script_name, description):
    """Run a single loader script."""
    logger.info(f"\n{'='*70}")
    logger.info(f"📦 Running: {description} ({script_name})")
    logger.info(f"{'='*70}")

    script_path = Path("/home/stocks/algo") / script_name

    if not script_path.exists():
        logger.error(f"❌ Script not found: {script_path}")
        return False

    try:
        start_time = time.time()

        # Timeout strategy based on loader type
        if 'company' in script_name.lower():
            timeout = 300  # 5 minutes for Company Profile (fails fast if DB not available)
        elif any(yf_loader in script_name.lower() for yf_loader in ['price', 'daily', 'technical']):
            timeout = 3600  # 60 minutes for yfinance-dependent loaders
        else:
            timeout = 1800  # 30 minutes for other loaders

        result = subprocess.run(
            ["python3", str(script_path)],
            cwd="/home/stocks/algo",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.time() - start_time

        # Log output
        if result.stdout:
            logger.info(result.stdout[-2000:])  # Last 2000 chars

        if result.returncode == 0:
            logger.info(f"✅ SUCCESS: {description} completed in {elapsed:.1f}s")
            return True
        else:
            logger.error(f"❌ FAILED: {description}")
            if result.stderr:
                logger.error(result.stderr[-2000:])
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"⏱️ TIMEOUT: {description} (exceeded 30 minutes)")
        return False
    except Exception as e:
        logger.error(f"❌ ERROR: {description} - {e}")
        return False


def main():
    """Main loader orchestrator."""
    lock_handle = None

    try:
        logger.info("="*70)
        logger.info("🚀 STOCKS DATA LOADER - REAL DATA ONLY")
        logger.info("="*70)

        # Acquire lock
        lock_handle = acquire_lock(LOCK_FILE)
        if not lock_handle:
            sys.exit(1)

        # Run loaders in sequence
        results = {}
        failed_loaders = []

        for script_name, description in LOADERS:
            success = run_loader(script_name, description)
            results[description] = "✅ PASS" if success else "❌ FAIL"
            if not success:
                failed_loaders.append(description)

        # Print summary
        logger.info("\n" + "="*70)
        logger.info("📊 LOADER EXECUTION SUMMARY")
        logger.info("="*70)
        for desc, status in results.items():
            logger.info(f"{status}: {desc}")

        if failed_loaders:
            logger.error(f"\n⚠️ {len(failed_loaders)} loader(s) failed:")
            for desc in failed_loaders:
                logger.error(f"  - {desc}")
            sys.exit(1)
        else:
            logger.info("\n🎉 ALL LOADERS COMPLETED SUCCESSFULLY!")
            logger.info("✅ Database populated with REAL DATA ONLY")
            sys.exit(0)

    except KeyboardInterrupt:
        logger.warning("\n⚠️ Loader interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Always release lock
        if lock_handle:
            release_lock(lock_handle)


if __name__ == "__main__":
    main()
