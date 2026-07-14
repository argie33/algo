#!/usr/bin/env python3
"""RDS Database Cleanup Utility - Remove extra databases, keep only 'stocks'.

⚠️ DEPRECATED: Emergency workaround script — bypasses RDS Proxy connection pooling.
This script connects directly to AWS RDS and performs database cleanup operations.

DO NOT use this script except as a last resort during infrastructure failures.
Connection issues should be fixed in algo/infrastructure/db/pool.py instead.
"""

import argparse
import os
import sys

import psycopg2

RDS_HOST = "algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com"
RDS_PORT = 5432
RDS_USER = "postgres"
RDS_DB = "postgres"
EXPECTED_DBS = {"stocks", "postgres", "template0", "template1"}


def get_password():
    password = os.environ.get("DB_PASSWORD")
    if not password:
        print(" DB_PASSWORD environment variable not set")
        print("Set it: export DB_PASSWORD='your_password'")
        sys.exit(1)
    return password


def connect_to_rds(password):
    try:
        return psycopg2.connect(
            host=RDS_HOST, port=RDS_PORT, database=RDS_DB, user=RDS_USER, password=password, connect_timeout=10
        )
    except psycopg2.OperationalError as e:
        print(f" Connection failed: {e}")
        sys.exit(1)


def list_databases(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname")
    dbs = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return dbs


def drop_database(conn, db_name):
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = %s AND pid <> pg_backend_pid()",
            (db_name,),
        )
        conn.commit()
        cursor.execute(f"DROP DATABASE IF EXISTS {db_name}")
        conn.commit()
        return True
    except Exception as e:
        print(f"   Error: {e}")
        return False
    finally:
        cursor.close()


def main():
    parser = argparse.ArgumentParser(description="Clean up extra RDS databases")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List all databases")
    group.add_argument("--clean", action="store_true", help="Drop all extra databases")
    group.add_argument("--drop", metavar="DBNAME", help="Drop specific database")
    args = parser.parse_args()

    password = get_password()
    conn = connect_to_rds(password)

    try:
        if args.list:
            print("\n Databases in RDS:\n")
            dbs = list_databases(conn)
            extra_dbs = [db for db in dbs if db not in EXPECTED_DBS]

            for db in dbs:
                if db == "stocks":
                    print(f"  OK [EXPECTED] {db}")
                elif db in EXPECTED_DBS:
                    print(f"  INFO  [SYSTEM]  {db}")
                else:
                    print(f"  WARN  [EXTRA]   {db}")

            print(f"\n Summary: {len(dbs)} total, {len(extra_dbs)} extra")
            if extra_dbs:
                print("To clean up: python3 scripts/cleanup_rds_databases.py --clean")

        elif args.clean:
            dbs = list_databases(conn)
            extra_dbs = [db for db in dbs if db not in EXPECTED_DBS]

            if not extra_dbs:
                print("OK No extra databases found!")
                return

            print(f"\nWARN  Found {len(extra_dbs)} extra database(s):")
            for db in extra_dbs:
                print(f"   - {db}")

            response = input("\nDrop these databases? (yes/no): ")
            if response.lower() != "yes":
                print("Cancelled.")
                return

            print("\n Cleaning up...\n")
            for db in extra_dbs:
                if drop_database(conn, db):
                    print(f"  OK Dropped {db}")
                else:
                    print(f"   Failed {db}")

            print("\nOK Cleanup complete")

        elif args.drop:
            dbs = list_databases(conn)
            if args.drop not in dbs:
                print(f" Database {args.drop} not found")
                return
            if args.drop == "stocks":
                print(" Cannot drop stocks - it's the required database")
                return

            response = input(f"\nDrop {args.drop}? (yes/no): ")
            if response.lower() == "yes":
                if drop_database(conn, args.drop):
                    print(f"OK Dropped {args.drop}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
