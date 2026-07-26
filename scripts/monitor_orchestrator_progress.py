#!/usr/bin/env python3
"""Monitor orchestrator progress in real-time via CloudWatch logs."""

import sys
import time
from datetime import datetime, timezone


def check_scores_freshness():
    """Check if AWS scores have been updated."""
    import sys

    sys.path.insert(0, "/c/Users/arger/code/algo")

    from dashboard.api_data_layer import api_call

    try:
        response = api_call("/api/algo/scores", params={"limit": 1, "offset": 0})
        if isinstance(response, dict) and "top" in response:
            top = response["top"]
            if top:
                first = top[0]
                updated = first.get("updated_at")
                growth = first.get("growth_score")
                composite = first.get("composite_score")

                print("\n[SCORES DATA CHECK]")
                print(f"  Composite Score: {composite}")
                print(f"  Growth Score: {growth}")
                print(f"  Last Updated: {updated}")

                if growth is not None and growth > 0:
                    print("  STATUS: [OK] Growth scores calculated!")
                    return True
                elif growth is None:
                    print("  STATUS: [PENDING] Growth scores still NULL")
                    return False
        return None
    except Exception as e:
        print(f"  ERROR checking scores: {e}")
        return None


def main():
    print("=" * 60)
    print("ORCHESTRATOR PROGRESS MONITORING")
    print("=" * 60)
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("Orchestrator request ID: 6ef18061-0f9f-4e30-ab30-2a2aa6fcac7a")
    print("\nExpected execution time: 11-15 minutes")
    print("Checking growth score freshness every 30 seconds...\n")

    # Poll for updates
    start_time = time.time()
    max_wait = 20 * 60  # 20 minute timeout
    check_interval = 30  # 30 second checks

    last_check = 0
    while time.time() - start_time < max_wait:
        elapsed = time.time() - start_time
        if elapsed - last_check >= check_interval:
            result = check_scores_freshness()
            last_check = elapsed

            if result is True:
                print("\n[SUCCESS] Orchestrator completed and scores updated!")
                print(f"Elapsed time: {int(elapsed / 60)}m {int(elapsed % 60)}s")
                return 0

            # Show progress
            mins = int(elapsed / 60)
            secs = int(elapsed % 60)
            print(f"[{mins}m {secs}s] Still waiting for orchestrator to complete...")

            time.sleep(1)  # Small sleep to avoid tight polling

    print("\n[TIMEOUT] Orchestrator did not complete within 20 minutes")
    print("Check CloudWatch logs manually:")
    print("  aws logs tail /aws/lambda/algo-algo-dev --follow")
    return 1


if __name__ == "__main__":
    sys.exit(main())
