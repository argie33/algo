#!/usr/bin/env python3
"""Check for extra RDS databases (waste)."""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import psycopg2


def check_extra_databases():
    """Check for extra/orphaned RDS databases."""
    print("=" * 70)
    print("EXTRA RDS DATABASES AUDIT")
    print("=" * 70)
    print("\nChecking for databases beyond 'stocks' database...")
    print("Extra databases = WASTE (billed even if empty)\n")

    try:
        from config.credential_manager import CredentialManager

        cred_mgr = CredentialManager()
        creds = cred_mgr.get_db_credentials()

        conn = psycopg2.connect(**creds)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT datname, pg_database_size(datname) as size_bytes
            FROM pg_database
            WHERE datname NOT IN ('postgres', 'template0', 'template1', 'stocks')
            ORDER BY datname
        """)

        extra_dbs = cursor.fetchall()
        cursor.close()
        conn.close()

        if not extra_dbs:
            print("[OK] NO EXTRA DATABASES FOUND")
            print("     Only 'stocks' database exists (correct)")
            return 0

        print(f"[WASTE] FOUND {len(extra_dbs)} EXTRA DATABASE(S):\n")

        total_waste_bytes = 0
        for db_name, size_bytes in extra_dbs:
            size_mb = size_bytes / (1024 * 1024)
            size_gb = size_bytes / (1024 * 1024 * 1024)
            total_waste_bytes += size_bytes

            print(f"  Database: {db_name}")
            print(f"  Size: {size_mb:.2f} MB ({size_gb:.4f} GB)")
            print(f"  Cost: ${0.23 * size_gb:.2f}/month (storage @ $0.23/GB)")
            print(f"  Delete: DROP DATABASE IF EXISTS {db_name};")
            print()

        total_waste_gb = total_waste_bytes / (1024 * 1024 * 1024)
        total_waste_cost = 0.23 * total_waste_gb

        print(f"[TOTAL WASTE] {total_waste_gb:.2f} GB (~${total_waste_cost:.2f}/month)")
        print(f"[ACTION] Delete via: psql -h <rds-host> -U stocks -d stocks -c 'DROP DATABASE ..;'")

        return len(extra_dbs)

    except Exception as e:
        print(f"[ERROR] {e}")
        print("        This is expected without AWS credentials.")
        print("        Check manually in AWS RDS Console")
        return -1


if __name__ == "__main__":
    num_extra = check_extra_databases()
    sys.exit(0 if num_extra >= 0 else 1)
