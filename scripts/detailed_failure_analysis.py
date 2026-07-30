#!/usr/bin/env python3
"""Analyze specific orchestrator failures in detail."""

import json
import logging
from datetime import datetime, timedelta

import psycopg2

from utils.db import get_db_connection

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def analyze_failures():
    """Analyze recent orchestrator run failures in detail."""

    print("\n" + "="*80)
    print("DETAILED FAILURE ANALYSIS")
    print("="*80)

    conn = get_db_connection()
    cur = conn.cursor()

    # Get runs with errors in last 24h
    cur.execute("""
        SELECT run_id, started_at, overall_status, halt_reason, phases_completed, phases_errored
        FROM orchestrator_execution_log
        WHERE overall_status IN ('error', 'halted')
           OR phases_errored > 0
        ORDER BY started_at DESC
        LIMIT 10
    """)

    runs = cur.fetchall()

    for run_id, started_at, status, halt_reason, completed, errored in runs:
        print(f"\n{'='*80}")
        print(f"RUN: {run_id}")
        print(f"  Time: {started_at}")
        print(f"  Status: {status}")
        print(f"  Phases: {completed} completed, {errored} errored")
        print(f"  Halt Reason:")
        if halt_reason:
            for line in halt_reason.split('\n'):
                if line.strip():
                    print(f"    {line}")
        else:
            print(f"    (none)")

    # Summary by error type
    print(f"\n{'='*80}")
    print("SUMMARY BY ERROR TYPE")
    print(f"{'='*80}")

    cur.execute("""
        SELECT
            SUBSTRING(halt_reason FROM 1 FOR 100) as error_type,
            COUNT(*) as count,
            MAX(started_at) as latest
        FROM orchestrator_execution_log
        WHERE halt_reason IS NOT NULL
        GROUP BY SUBSTRING(halt_reason FROM 1 FOR 100)
        ORDER BY count DESC
    """)

    for error_type, count, latest in cur.fetchall():
        print(f"\n{count}x: {error_type}...")
        print(f"   Latest: {latest}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    analyze_failures()
