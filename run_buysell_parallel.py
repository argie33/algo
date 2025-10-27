#!/usr/bin/env python3
"""
Parallel Buy/Sell Loader - Runs all 3 buy/sell loaders in PARALLEL
Executes: loadbuyselldaily, loadbuysellweekly, loadbuysellmonthly simultaneously
"""

import subprocess
import time
import logging
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/home/stocks/algo/loader.log", mode="a"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Loaders to run in PARALLEL
LOADERS = [
    ("loadbuyselldaily.py", "Buy/Sell Signals (Daily)"),
    ("loadbuysellweekly.py", "Buy/Sell Signals (Weekly)"),
    ("loadbuysellmonthly.py", "Buy/Sell Signals (Monthly)"),
]

TIMEOUT = 1800  # 30 minutes per loader


def run_loader(script_name, description):
    """Run a single loader script."""
    logger.info(f"📦 Running: {description} ({script_name})")

    script_path = Path("/home/stocks/algo") / script_name

    if not script_path.exists():
        logger.error(f"❌ Script not found: {script_path}")
        return False

    try:
        start_time = time.time()

        result = subprocess.run(
            ["python3", str(script_path)],
            cwd="/home/stocks/algo",
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        elapsed = time.time() - start_time

        # Log output
        if result.stdout:
            logger.info(result.stdout[-1000:])

        if result.returncode == 0:
            logger.info(f"✅ SUCCESS: {description} completed in {elapsed:.1f}s")
            return True
        else:
            logger.error(f"❌ FAILED: {description}")
            if result.stderr:
                logger.error(result.stderr[-1000:])
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"⏱️ TIMEOUT: {description}")
        return False
    except Exception as e:
        logger.error(f"❌ ERROR: {description} - {e}")
        return False


def main():
    """Run all buy/sell loaders in PARALLEL."""
    logger.info("=" * 70)
    logger.info("🚀 PARALLEL BUY/SELL LOADERS - RUNNING IN PARALLEL")
    logger.info("=" * 70)

    results = {}
    failed_loaders = []

    # Run loaders in PARALLEL using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(run_loader, script, desc): (script, desc)
            for script, desc in LOADERS
        }

        for future in as_completed(futures):
            script, desc = futures[future]
            try:
                success = future.result()
                results[desc] = "✅ PASS" if success else "❌ FAIL"
                if not success:
                    failed_loaders.append(desc)
            except Exception as e:
                logger.error(f"❌ Exception in {desc}: {e}")
                results[desc] = "❌ FAIL"
                failed_loaders.append(desc)

    # Print summary
    logger.info("\n" + "=" * 70)
    logger.info("📊 BUY/SELL PARALLEL EXECUTION SUMMARY")
    logger.info("=" * 70)
    for desc, status in results.items():
        logger.info(f"{status}: {desc}")

    if failed_loaders:
        logger.error(f"\n⚠️ {len(failed_loaders)} loader(s) failed:")
        for desc in failed_loaders:
            logger.error(f"  - {desc}")
        return False
    else:
        logger.info("\n🎉 ALL BUY/SELL LOADERS COMPLETED SUCCESSFULLY!")
        logger.info("✅ Real data loaded for all timeframes")
        return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
