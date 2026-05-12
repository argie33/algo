#!/usr/bin/env python3
"""
Market Data Batch Runner

Runs all small market-level loaders in parallel within a single ECS task,
replacing 8 separate ECS task startups (8 x 3-5 min overhead) with one.

Each loader runs as a subprocess so that asyncio event loops, DB connections,
and credentials are fully isolated. Exit 0 only if every loader succeeds.
"""

import logging
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("market_data_batch")

LOADERS = [
    "loadmarket.py",
    "loadmarketindices.py",
    "loadsectors.py",
    "loadecondata.py",
    "loadaaiidata.py",
    "loadnaaim.py",
    "loadfeargreed.py",
    "loadcalendar.py",
]

SCRIPT_DIR = Path(__file__).parent


def run_loader(script_name: str) -> tuple:
    script_path = SCRIPT_DIR / script_name
    if not script_path.exists():
        log.error("[%s] script not found at %s", script_name, script_path)
        return script_name, 1, 0.0

    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=False,  # let stdout/stderr flow to CloudWatch
        env=os.environ.copy(),
    )
    elapsed = time.monotonic() - start
    return script_name, result.returncode, elapsed


def main() -> int:
    log.info("Starting market data batch -- %d loaders in parallel", len(LOADERS))
    start_all = time.monotonic()

    failures = []
    with ThreadPoolExecutor(max_workers=len(LOADERS)) as pool:
        futures = {pool.submit(run_loader, name): name for name in LOADERS}
        for future in as_completed(futures):
            name, code, elapsed = future.result()
            status = "OK" if code == 0 else "FAILED (exit %d)" % code
            log.info("[%s] %s in %.1fs", name, status, elapsed)
            if code != 0:
                failures.append(name)

    total = time.monotonic() - start_all
    if failures:
        log.error("BATCH FAILED -- %d loader(s) errored: %s", len(failures), failures)
        log.info("Completed in %.1fs (wall clock)", total)
        return 1

    log.info("All %d loaders succeeded in %.1fs (wall clock)", len(LOADERS), total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
