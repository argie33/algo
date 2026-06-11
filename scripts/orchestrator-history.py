#!/usr/bin/env python3
"""Orchestrator execution history CLI tool.

Provides commands to query orchestrator run history, failures, and success metrics.
"""

import sys
import argparse
from pathlib import Path

# Import query functions from the utils module
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.orchestrator_query import (
    print_recent_runs,
    print_failed_runs,
    print_halt_patterns,
    print_success_rate,
    get_run_details,
)
import json


def main():
    """CLI interface for orchestrator history queries."""
    parser = argparse.ArgumentParser(description="Query orchestrator execution history")

    parser.add_argument("--latest", type=int, default=10, help="Show latest N runs")
    parser.add_argument("--show-errors", action="store_true", help="Show failed/halted runs")
    parser.add_argument("--patterns", action="store_true", help="Show halt patterns")
    parser.add_argument("--stats", action="store_true", help="Show success statistics")
    parser.add_argument("--days", type=int, default=7, help="Days to look back")
    parser.add_argument("--details", type=str, help="Show details for specific run ID")

    args = parser.parse_args()

    if args.details:
        details = get_run_details(args.details)
        if details:
            print(json.dumps(details, indent=2))
        else:
            print(f"Run {args.details} not found")
        return 0

    if args.show_errors:
        print_failed_runs(args.days)
        return 0

    if args.patterns:
        print_halt_patterns(args.days)
        return 0

    if args.stats:
        print_success_rate(args.days)
        return 0

    # Default: show recent runs and success rate
    print_recent_runs(args.days, args.latest)
    print_success_rate(args.days)
    return 0


if __name__ == "__main__":
    sys.exit(main())
