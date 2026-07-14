#!/usr/bin/env python3
"""
Verify growth_score and rs_percentile data in production RDS.

Uses direct PostgreSQL connection to diagnose why dashboard shows NULL values.
Database credentials are fetched from Secrets Manager using IAM role.
"""

import json
import boto3
import psycopg2
import sys
from typing import Any


def get_secret(secret_name: str) -> dict[str, Any]:
    """Retrieve secret from Secrets Manager."""
    sm_client = boto3.client("secretsmanager", region_name="us-east-1")
    try:
        response = sm_client.get_secret_value(SecretId=secret_name)
        if "SecretString" in response:
            return json.loads(response["SecretString"])
    except Exception as e:
        print(f"❌ Failed to get secret {secret_name}: {e}")
        sys.exit(1)
    return {}


def execute_query(connection_params: dict, database: str, sql: str) -> list[dict]:
    """Execute SQL via psycopg2."""
    try:
        conn = psycopg2.connect(
            host=connection_params["host"],
            port=connection_params["port"],
            user=connection_params["username"],
            password=connection_params["password"],
            database=database,
            connect_timeout=10,
        )

        cursor = conn.cursor()
        cursor.execute(sql)

        # Fetch column names
        columns = [desc[0] for desc in cursor.description]
        records = []

        # Fetch all rows
        for row in cursor.fetchall():
            record = {}
            for i, col in enumerate(columns):
                record[col] = row[i]
            records.append(record)

        cursor.close()
        conn.close()
        return records
    except Exception as e:
        print(f"[!] Query failed: {type(e).__name__}: {str(e)[:150]}")
        return []


def main():
    print("[*] Verifying Growth Score & RS Percentile Data (Production RDS)")
    print("=" * 70)

    try:
        db_secret = get_secret("algo-db-credentials-dev")
        if not db_secret:
            print("[!] Could not retrieve database credentials")
            sys.exit(1)
    except Exception as e:
        print(f"[!] Error: {type(e).__name__}: {e}")
        sys.exit(1)

    database = "stocks"

    print(f"\n[+] Database Connection:")
    print(f"    Host: {db_secret.get('host')}")
    print(f"    Database: {database}")

    print(f"\n[+] Checking stock_scores table schema and data")
    print("-" * 70)

    # Query 1: Check if growth_score and rs_percentile columns exist and have data
    query1 = """
    SELECT
        COUNT(*) as total_rows,
        COUNT(growth_score) as growth_score_non_null,
        COUNT(rs_percentile) as rs_percentile_non_null,
        MIN(growth_score) as min_growth_score,
        MAX(growth_score) as max_growth_score,
        MIN(rs_percentile) as min_rs_percentile,
        MAX(rs_percentile) as max_rs_percentile
    FROM stock_scores
    """

    print("[*] Query 1: Overall statistics")
    result = execute_query(db_secret, database, query1)
    if result:
        row = result[0]
        total = row.get("total_rows", 0)
        growth_non_null = row.get("growth_score_non_null", 0)
        rs_non_null = row.get("rs_percentile_non_null", 0)
        print(f"    Total rows: {total}")
        print(f"    growth_score non-NULL: {growth_non_null} ({100 * growth_non_null // max(1, total)}%)")
        print(f"    rs_percentile non-NULL: {rs_non_null} ({100 * rs_non_null // max(1, total)}%)")
        print(f"    growth_score range: {row.get('min_growth_score')} to {row.get('max_growth_score')}")
        print(f"    rs_percentile range: {row.get('min_rs_percentile')} to {row.get('max_rs_percentile')}")
    else:
        print("    [!] No results from query")

    # Query 2: Sample of actual data
    print("\n[*] Query 2: Sample data (first 5 rows)")
    print("-" * 70)
    query2 = """
    SELECT
        symbol,
        growth_score,
        rs_percentile,
        updated_at
    FROM stock_scores
    LIMIT 5
    """

    result = execute_query(db_secret, database, query2)
    if result:
        for row in result:
            print(
                f"    {row.get('symbol')}: growth_score={row.get('growth_score')}, rs_percentile={row.get('rs_percentile')}, updated={row.get('updated_at')}"
            )
    else:
        print("    [!] No sample data found")

    # Query 3: Check data freshness
    print("\n[*] Query 3: Data freshness")
    print("-" * 70)
    query3 = """
    SELECT
        COUNT(DISTINCT symbol) as symbols_with_non_null_growth,
        MAX(updated_at) as latest_update,
        CURRENT_TIMESTAMP - MAX(updated_at) as time_since_update
    FROM stock_scores
    WHERE growth_score IS NOT NULL
    """

    result = execute_query(db_secret, database, query3)
    if result:
        row = result[0]
        print(f"    Symbols with growth_score: {row.get('symbols_with_non_null_growth')}")
        print(f"    Latest update: {row.get('latest_update')}")
        print(f"    Time since update: {row.get('time_since_update')}")
    else:
        print("    [!] No growth_score data found")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
