#!/usr/bin/env python3
"""Orchestrator execution history CLI tool.

Provides commands to query orchestrator run history, failures, and success metrics.
"""

import sys
import argparse
from pathlib import Path

# Import query functions from the test module
sys.path.insert(0, str(Path(__file__).parent.parent))
from tests.test_execution_history import (
    get_failed_runs,
    get_halt_patterns,
    get_success_rate,
)


def main():
    """CLI interface for orchestrator history queries."""
    parser = argparse.ArgumentParser(description="Query orchestrator execution history")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Subcommand: failed-runs
    failed_parser = subparsers.add_parser("failed-runs", help="Show failed runs")
    failed_parser.add_argument("--limit", type=int, default=10, help="Limit results")
    failed_parser.add_argument("--days", type=int, default=7, help="Days to look back")

    # Subcommand: halt-patterns
    halt_parser = subparsers.add_parser("halt-patterns", help="Show halt patterns")
    halt_parser.add_argument("--limit", type=int, default=20, help="Limit results")

    # Subcommand: success-rate
    rate_parser = subparsers.add_parser("success-rate", help="Show success rate")
    rate_parser.add_argument("--days", type=int, default=30, help="Days to look back")

    args = parser.parse_args()

    if args.command == "failed-runs":
        print(f"Failed runs (last {args.days} days):")
        runs = get_failed_runs(args.days)
        for i, run in enumerate(runs[:args.limit], 1):
            print(f"  {i}. {run}")

    elif args.command == "halt-patterns":
        print("Halt patterns:")
        patterns = get_halt_patterns()
        for i, pattern in enumerate(patterns[:args.limit], 1):
            print(f"  {i}. {pattern}")

    elif args.command == "success-rate":
        print(f"Success rate (last {args.days} days):")
        rate = get_success_rate(args.days)
        print(f"  {rate}%")

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
