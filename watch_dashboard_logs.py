#!/usr/bin/env python3
"""Watch dashboard logs in real-time while dashboard is running.

Usage:
  python watch_dashboard_logs.py              # Show last 50 lines, then tail new logs
  python watch_dashboard_logs.py --tail 20    # Show last 20 lines, then tail
  python watch_dashboard_logs.py --grep ERROR # Only show ERROR level messages
"""

import os
import sys
import argparse
import time
import io
from pathlib import Path

# Fix Windows console encoding
if sys.platform.startswith("win"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

log_file = Path.home() / ".algo" / "logs" / "dashboard.log"


def tail_file(filepath, lines_to_show=50, grep_pattern=None):
    """Tail log file in real-time."""
    if not filepath.exists():
        print(f"❌ Log file not found: {filepath}")
        print("   Make sure dashboard.py is running first")
        sys.exit(1)

    print(f"📋 Dashboard logs: {filepath}")
    print(f"{'─' * 80}")

    # Show last N lines
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
        lines = all_lines[-lines_to_show:]
        for line in lines:
            if grep_pattern is None or grep_pattern.upper() in line.upper():
                print(line.rstrip())

    print(f"{'─' * 80}")
    print("✅ Listening for new logs (Ctrl+C to stop)...\n")

    # Get current file size
    last_size = filepath.stat().st_size

    try:
        while True:
            time.sleep(0.5)
            current_size = filepath.stat().st_size

            if current_size > last_size:
                # File grew, read new lines
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(last_size)
                    new_lines = f.readlines()
                    for line in new_lines:
                        if grep_pattern is None or grep_pattern.upper() in line.upper():
                            print(line.rstrip())
                last_size = current_size
            elif current_size < last_size:
                # File was rotated, start from beginning
                last_size = 0

    except KeyboardInterrupt:
        print("\n\n✋ Stopped watching logs")
        sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Watch dashboard logs in real-time")
    parser.add_argument("--tail", type=int, default=50, help="Number of lines to show initially (default: 50)")
    parser.add_argument("--grep", help="Only show lines matching this pattern (e.g., ERROR, WARNING)")

    args = parser.parse_args()
    tail_file(log_file, lines_to_show=args.tail, grep_pattern=args.grep)
