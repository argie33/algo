#!/usr/bin/env python3
"""
Cleanup stale locks that are blocking loader execution.

Detects locks older than 2 hours and safely removes them if the owning process is dead.

Usage:
    python scripts/cleanup_stale_locks.py --dry-run  # Preview what would be cleaned
    python scripts/cleanup_stale_locks.py --fix      # Actually remove stale locks
    python scripts/cleanup_stale_locks.py --force    # Force remove all stale locks (dangerous)
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db.context import DatabaseContext


def check_process_alive(pid: int) -> bool:
    """Check if a process with given PID is still running.

    Returns:
        True if process is running, False if dead or PID doesn't exist
    """
    if pid is None or pid <= 0:
        return False

    try:
        # Check if process exists (Windows and Unix compatible)
        if os.name == 'nt':  # Windows
            import subprocess
            result = subprocess.run(
                ['tasklist', '/FI', f'PID eq {pid}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return str(pid) in result.stdout
        else:  # Unix
            os.kill(pid, 0)  # Signal 0 checks if process exists without sending signal
            return True
    except (OSError, ProcessLookupError):
        return False
    except Exception:
        # If we can't determine, assume it's alive (safe default)
        return True


class LockCleanup:
    """Cleanup manager for stale locks."""

    def __init__(self, dry_run: bool = True, force: bool = False):
        self.dry_run = dry_run
        self.force = force
        self.stale_threshold = 2  # hours
        self.critical_loaders = {
            'price_daily', 'buy_sell_daily', 'technical_data_daily',
            'quality_metrics', 'growth_metrics', 'positioning_metrics'
        }

    def get_stale_locks(self) -> list:
        """Get list of stale locks from database.

        Returns:
            List of lock records older than stale_threshold
        """
        try:
            with DatabaseContext('read', timeout=10, enable_correlation_tracking=False) as cur:
                query = """
                SELECT
                    lock_id,
                    resource_name,
                    owner_id,
                    started_at,
                    EXTRACT(EPOCH FROM (NOW() - started_at)) as age_seconds
                FROM loader_execution_locks
                WHERE started_at < NOW() - INTERVAL '%d hours'
                ORDER BY started_at DESC
                """ % self.stale_threshold

                cur.execute(query)
                return cur.fetchall()
        except Exception as e:
            if 'does not exist' in str(e).lower():
                print("[INFO] loader_execution_locks table not found (using DynamoDB?)")
                return []
            raise

    def remove_lock(self, lock_id, resource_name: str):
        """Remove a single lock from the database.

        Args:
            lock_id: The lock ID to remove
            resource_name: Name of the resource (for logging)
        """
        try:
            with DatabaseContext('write', timeout=10, enable_correlation_tracking=False) as cur:
                cur.execute("""
                    DELETE FROM loader_execution_locks
                    WHERE lock_id = %s
                """, (lock_id,))

                # Connection auto-commits on exit
                print(f"[REMOVED] Lock {lock_id} for {resource_name}")
        except Exception as e:
            print(f"[ERROR] Failed to remove lock {lock_id}: {e}")

    def cleanup_dry_run(self, stale_locks: list) -> int:
        """Preview what would be cleaned without making changes.

        Returns:
            Count of stale locks that would be removed
        """
        if not stale_locks:
            print("[DRY-RUN] No stale locks found")
            return 0

        print(f"[DRY-RUN] Found {len(stale_locks)} stale locks:")
        print()

        to_remove = 0
        for lock in stale_locks:
            age_hours = lock['age_seconds'] / 3600
            is_critical = any(critical in lock['resource_name']
                            for critical in self.critical_loaders)
            critical_tag = " [CRITICAL]" if is_critical else ""

            # Check if process is still alive
            is_alive = check_process_alive(lock.get('owner_id'))
            alive_tag = " [PROCESS ALIVE]" if is_alive else " [PROCESS DEAD]"

            print(f"  Lock ID: {lock['lock_id']}")
            print(f"    Resource: {lock['resource_name']}{critical_tag}")
            print(f"    Owner PID: {lock['owner_id']}{alive_tag}")
            print(f"    Age: {age_hours:.1f} hours (since {lock['started_at']})")

            if not is_alive or self.force:
                print(f"    Action: WOULD REMOVE")
                to_remove += 1
            else:
                print(f"    Action: SKIP (process still running)")
            print()

        return to_remove

    def cleanup_fix(self, stale_locks: list) -> int:
        """Actually remove stale locks.

        Returns:
            Count of locks successfully removed
        """
        if not stale_locks:
            print("[INFO] No stale locks found")
            return 0

        print(f"[CLEANUP] Found {len(stale_locks)} stale locks")
        print()

        removed = 0
        for lock in stale_locks:
            age_hours = lock['age_seconds'] / 3600
            is_critical = any(critical in lock['resource_name']
                            for critical in self.critical_loaders)

            # Check if process is still alive
            is_alive = check_process_alive(lock.get('owner_id'))

            print(f"Processing: {lock['resource_name']} (age={age_hours:.1f}h)")

            if is_critical and is_alive:
                print(f"  SKIPPING: Critical loader process still running (PID {lock['owner_id']})")
                continue

            if not is_alive or self.force:
                try:
                    self.remove_lock(lock['lock_id'], lock['resource_name'])
                    removed += 1
                except Exception as e:
                    print(f"  ERROR: {e}")
            else:
                print(f"  SKIPPING: Process {lock['owner_id']} still running")

        print()
        print(f"[SUMMARY] Removed {removed}/{len(stale_locks)} stale locks")
        return removed

    def run(self) -> int:
        """Run cleanup process.

        Returns:
            Exit code (0 = success)
        """
        try:
            stale_locks = self.get_stale_locks()

            if self.dry_run:
                self.cleanup_dry_run(stale_locks)
            else:
                self.cleanup_fix(stale_locks)

            return 0
        except Exception as e:
            print(f"[FATAL] Cleanup failed: {e}")
            return 1


def main():
    parser = argparse.ArgumentParser(
        description='Clean up stale database locks that may block loaders'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Preview what would be cleaned (default)'
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Actually remove stale locks'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force remove all stale locks (dangerous - bypasses safety checks)'
    )

    args = parser.parse_args()

    # Determine mode
    if args.fix:
        dry_run = False
    else:
        dry_run = True

    if args.force and not args.fix:
        print("[WARNING] --force requires --fix to actually do anything")

    cleanup = LockCleanup(dry_run=dry_run, force=args.force)
    exit_code = cleanup.run()

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
