#!/usr/bin/env python3
"""Local loader scheduler for dev/test environments.

Usage:
  python scripts/local_loader_scheduler.py --now morning
  python scripts/local_loader_scheduler.py --now metrics
  python scripts/local_loader_scheduler.py --now signals
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"


PIPELINES = {
    "morning": [
        "prices",
        "technical",
        "market_status",
    ],
    "metrics": [
        "value_quality_growth",
        "positioning_metrics",
        "stability_metrics",
    ],
    "signals": [
        "prices",
        "technical",
        "scores",
        "buy_sell",
    ],
}


def run_pipeline(pipeline_name: str) -> int:
    """Run all loaders for a given pipeline."""
    loaders = PIPELINES.get(pipeline_name)
    if not loaders:
        print(f"ERROR: Unknown pipeline '{pipeline_name}'", file=sys.stderr)
        print(f"Valid pipelines: {', '.join(PIPELINES.keys())}", file=sys.stderr)
        return 1

    print(f"[LOCAL_SCHEDULER] Starting {pipeline_name} pipeline ({len(loaders)} loaders)...")
    repo_root = Path(__file__).parent.parent

    for loader in loaders:
        print(f"[LOCAL_SCHEDULER] Running {loader} loader...")
        result = subprocess.run(
            [sys.executable, "scripts/run_loader.py", loader],
            cwd=str(repo_root),
            env=os.environ.copy(),
        )
        if result.returncode != 0:
            print(
                f"[LOCAL_SCHEDULER] WARNING: {loader} loader failed (exit code {result.returncode})",
                file=sys.stderr,
            )
            return 1

    print(f"[LOCAL_SCHEDULER] {pipeline_name} pipeline completed successfully")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Local loader scheduler")
    parser.add_argument(
        "--now",
        type=str,
        required=True,
        help="Run this pipeline immediately (morning|metrics|signals)",
    )
    args = parser.parse_args()

    return run_pipeline(args.now)


if __name__ == "__main__":
    sys.exit(main())
