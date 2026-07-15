#!/usr/bin/env python3
"""Diagnose and clear stale orchestrator locks."""
import os
import sys

import psycopg2

# Fix encoding on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def get_db_connection():
    """Connect to database using environment or Lambda execution context."""
    try:
        # Try Lambda/VPC endpoint first
        host = os.getenv("DB_HOST") or "localhost"
        user = os.getenv("DB_USER") or "stocks"
        password = os.getenv("DB_PASSWORD")
        if not password:
            raise ValueError("DB_PASSWORD environment variable must be set")
        dbname = os.getenv("DB_NAME") or "stocks"
        ssl_mode = os.getenv("DB_SSL", "require")

        # Normalize ssl_mode value
        if ssl_mode in ("false", "0", "no", "False", "False"):
            ssl_mode = "disable"
        elif ssl_mode in ("true", "1", "yes", "True", "True") or ssl_mode == "require":
            ssl_mode = "require"
        elif ssl_mode not in ("disable", "allow", "prefer", "require"):
            ssl_mode = "prefer"

        conn = psycopg2.connect(
            host=host,
            user=user,
            password=password,
            dbname=dbname,
            sslmode=ssl_mode,
            connect_timeout=5
        )
        return conn
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}", file=sys.stderr)
        return None

def check_locks() -> dict | None:
    """Check active orchestrator locks."""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                id, instance_id, lock_acquired_at, last_heartbeat_at,
                EXTRACT(EPOCH FROM (NOW() - last_heartbeat_at)) as heartbeat_age_sec,
                is_active
            FROM algo_orchestrator_locks
            ORDER BY lock_acquired_at DESC
            LIMIT 10
        """)

        locks = cur.fetchall()
        conn.close()

        if not locks:
            return {"status": "no_locks", "message": "No orchestrator locks found"}

        result = {"status": "found_locks", "locks": []}
        for lock in locks:
            lock_id, instance_id, acquired_at, heartbeat_at, age_sec, is_active = lock
            result["locks"].append({
                "id": lock_id,
                "instance_id": instance_id,
                "acquired_at": acquired_at.isoformat() if acquired_at else None,
                "heartbeat_at": heartbeat_at.isoformat() if heartbeat_at else None,
                "age_seconds": int(age_sec) if age_sec else None,
                "is_active": is_active,
                "is_stale": age_sec > 300 if age_sec else False  # > 5 min = stale
            })

        return result

    except Exception as e:
        print(f"[ERROR] Error checking locks: {e}", file=sys.stderr)
        return None

def clear_stale_locks(max_age_seconds: int = 300) -> bool:
    """Clear locks older than max_age_seconds."""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        cur = conn.cursor()
        cur.execute(f"""
            UPDATE algo_orchestrator_locks
            SET is_active = false
            WHERE is_active = true
            AND EXTRACT(EPOCH FROM (NOW() - last_heartbeat_at)) > {max_age_seconds}
        """)

        deleted = cur.rowcount
        conn.commit()
        conn.close()

        if deleted > 0:
            print(f"[OK] Cleared {deleted} stale lock(s) (age > {max_age_seconds}s)")
            return True
        else:
            print("[INFO]  No stale locks to clear")
            return False

    except Exception as e:
        print(f"[ERROR] Error clearing locks: {e}", file=sys.stderr)
        if conn:
            conn.close()
        return False

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Diagnose orchestrator locks")
    parser.add_argument("--clear", action="store_true", help="Clear stale locks (age > 5min)")
    parser.add_argument("--max-age", type=int, default=300, help="Max lock age in seconds (default 300)")
    args = parser.parse_args()

    print("[INFO] Checking orchestrator locks...\n")

    lock_status = check_locks()
    if not lock_status:
        print("[ERROR] Failed to check locks")
        return 1

    if lock_status["status"] == "no_locks":
        print("[OK] No orchestrator locks found")
        return 0

    print(f"Found {len(lock_status['locks'])} lock record(s):\n")
    for lock in lock_status["locks"]:
        age = lock.get("age_seconds", 0) or 0
        status = "[ACTIVE] ACTIVE" if lock["is_active"] else "[INACTIVE] INACTIVE"
        stale = "[WARN] STALE" if lock.get("is_stale") else "[OK] OK"

        print(f"  {status} {stale}")
        print(f"    Instance: {lock['instance_id']}")
        print(f"    Acquired: {lock['acquired_at']}")
        print(f"    Heartbeat: {lock['heartbeat_at']} ({age}s ago)")
        print()

    # Check if any are stale
    stale_locks = [l for l in lock_status["locks"] if l.get("is_stale")]

    if stale_locks:
        print(f"[WARN]  Found {len(stale_locks)} stale lock(s) (not updated for > 5min)")

        if args.clear:
            print("\nClearing stale locks...")
            if clear_stale_locks(args.max_age):
                print("[OK] Stale locks cleared. Orchestrator can run now.")
                return 0
            else:
                print("[ERROR] Failed to clear locks")
                return 1
        else:
            print("\nRun with --clear flag to remove stale locks")
            print("Orchestrator will skip execution while locks are held.")
            return 1
    else:
        print("[OK] No stale locks detected")
        return 0

if __name__ == "__main__":
    sys.exit(main())
