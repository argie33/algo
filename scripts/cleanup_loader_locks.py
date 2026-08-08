#!/usr/bin/env python3
"""Clean up stale loader lock files from crashed runs.

Lock files prevent concurrent loader execution (ensures idempotency). But when a loader
crashes without releasing its lock, subsequent runs block for the full lock TTL (1-2 hours).
This script aggressively cleans up stale locks.

Usage:
    python scripts/cleanup_loader_locks.py                 # Remove locks older than 30 min
    python scripts/cleanup_loader_locks.py --max-age 120   # Remove locks older than 2 hours
"""

import argparse
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

def cleanup_locks(max_age_minutes: int = 30) -> None:
    """Remove loader lock files older than max_age_minutes.

    Args:
        max_age_minutes: Maximum age for a lock file before removal (default: 30 min)
    """
    lock_dir = Path(tempfile.gettempdir()) / "algo-locks"

    if not lock_dir.exists():
        print(f"[CLEANUP] Lock directory doesn't exist: {lock_dir}")
        return

    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(minutes=max_age_minutes)
    removed_count = 0
    removed_locks = []

    try:
        for lock_file in lock_dir.glob("*.lock"):
            try:
                # Check file modification time
                file_mtime = datetime.fromtimestamp(lock_file.stat().st_mtime, tz=timezone.utc)

                if file_mtime < stale_threshold:
                    lock_file.unlink()
                    removed_count += 1
                    removed_locks.append(lock_file.name)
                    age_minutes = int((now - file_mtime).total_seconds() / 60)
                    print(f"[CLEANUP] Removed stale lock: {lock_file.name} ({age_minutes} min old)")
            except Exception as e:
                print(f"[CLEANUP] Failed to remove {lock_file.name}: {e}", file=sys.stderr)

        if removed_count > 0:
            print(f"\n[CLEANUP] SUCCESS: Removed {removed_count} stale lock file(s)")
            print(f"[CLEANUP] Locks removed: {', '.join(removed_locks)}")
        else:
            print(f"[CLEANUP] No stale locks found (max age: {max_age_minutes} min)")

            # Show status of existing locks
            existing_locks = list(lock_dir.glob("*.lock"))
            if existing_locks:
                print(f"[CLEANUP] Existing lock files:")
                for lock_file in sorted(existing_locks):
                    file_mtime = datetime.fromtimestamp(lock_file.stat().st_mtime, tz=timezone.utc)
                    age_minutes = int((now - file_mtime).total_seconds() / 60)
                    # Try to read lock content to see expiry time
                    try:
                        with open(lock_file, "r") as f:
                            content = f.read().strip()
                            if "|" in content:
                                expiry_str = content.split("|")[1]
                                print(f"  - {lock_file.name}: {age_minutes} min old, expires at {expiry_str}")
                            else:
                                print(f"  - {lock_file.name}: {age_minutes} min old")
                    except Exception:
                        print(f"  - {lock_file.name}: {age_minutes} min old")

    except Exception as e:
        print(f"[CLEANUP] Error during cleanup: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Clean up stale loader lock files from crashed runs"
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=30,
        help="Maximum age in minutes for lock files before removal (default: 30)"
    )
    args = parser.parse_args()

    cleanup_locks(max_age_minutes=args.max_age)

if __name__ == "__main__":
    main()
