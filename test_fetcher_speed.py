#!/usr/bin/env python3
"""Measure individual fetcher performance."""
import logging
import os
import sys
import time

sys.path.insert(0, '.')

os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
os.environ['LOCAL_MODE'] = 'true'

logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from dashboard.fetchers import FETCHERS

print("[SPEED] Testing individual fetcher performance...")
print(f"[SPEED] Found {len(FETCHERS)} fetchers\n")

times = {}
for name, fn in sorted(FETCHERS.items()):
    t0 = time.time()
    try:
        result = fn(None)
        elapsed = time.time() - t0
        is_error = isinstance(result, dict) and '_error' in result
        status = "ERROR" if is_error else "OK"
        times[name] = elapsed
        print(f"[SPEED] {name:20s}: {elapsed:7.3f}s [{status}]")
    except TimeoutError as e:
        elapsed = time.time() - t0
        times[name] = elapsed
        logger.error(
            f"[SPEED_TEST] Fetcher '{name}' timed out after {elapsed:.2f}s: "
            f"TimeoutError: {e}. Fetcher may be hanging or service unreachable."
        )
        print(f"[SPEED] {name:20s}: {elapsed:7.3f}s [TIMEOUT]", file=sys.stderr)
    except ConnectionError as e:
        elapsed = time.time() - t0
        times[name] = elapsed
        logger.warning(
            f"[SPEED_TEST] Fetcher '{name}' connection failed after {elapsed:.2f}s: "
            f"ConnectionError: {e}. API service may be unavailable."
        )
        print(f"[SPEED] {name:20s}: {elapsed:7.3f}s [CONNECTION_ERROR]", file=sys.stderr)
    except ValueError as e:
        elapsed = time.time() - t0
        times[name] = elapsed
        logger.error(
            f"[SPEED_TEST] Fetcher '{name}' raised ValueError after {elapsed:.2f}s: {e}. "
            "Data validation or parsing error in fetcher."
        )
        print(f"[SPEED] {name:20s}: {elapsed:7.3f}s [VALIDATION_ERROR]", file=sys.stderr)
    except Exception as e:
        elapsed = time.time() - t0
        times[name] = elapsed
        logger.exception(
            f"[SPEED_TEST] Fetcher '{name}' raised unexpected exception after {elapsed:.2f}s: "
            f"{type(e).__name__}: {e}"
        )
        print(f"[SPEED] {name:20s}: {elapsed:7.3f}s [EXCEPTION]", file=sys.stderr)

print("\n[SPEED] SLOWEST FETCHERS:")
sorted_times = sorted(times.items(), key=lambda x: -x[1])
for name, elapsed in sorted_times[:10]:
    print(f"[SPEED]   {name:20s}: {elapsed:.3f}s")

total = sum(times.values())
print(f"\n[SPEED] Total time: {total:.3f}s")
print(f"[SPEED] Average: {total/len(times):.3f}s per fetcher")
