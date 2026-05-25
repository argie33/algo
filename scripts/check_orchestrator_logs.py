#!/usr/bin/env python3
"""Check orchestrator audit logs."""
import os
import sys
from datetime import datetime, timedelta
import psycopg2
from config.credential_helper import get_db_config

def main():
    try:
        config = get_db_config()
        conn = psycopg2.connect(
            host=config['host'],
            port=config['port'],
            database=config['database'],
            user=config['user'],
            password=config['password'],
            sslmode=config.get('sslmode', 'disable')
        )
        cursor = conn.cursor()

        # Check recent orchestrator runs (look for entries in the last 3 days)
        query = """
        SELECT
            action_type,
            symbol,
            status,
            error_message,
            created_at
        FROM algo_audit_log
        WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '3 days'
        ORDER BY created_at DESC
        LIMIT 100
        """

        cursor.execute(query)
        results = cursor.fetchall()

        print("=" * 140)
        print("RECENT ORCHESTRATOR/ALGO ACTIONS (Last 3 days)")
        print("=" * 140)
        print(f"{'Action Type':<30} {'Symbol':<10} {'Status':<12} {'Error':<50} {'Time':<25}")
        print("-" * 140)

        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        today_actions = []
        yesterday_actions = []

        for row in results:
            action_type, symbol, status, error_message, created_at = row
            exec_date = created_at.date() if created_at else None
            
            if exec_date == today:
                today_actions.append((action_type, status))
            elif exec_date == yesterday:
                yesterday_actions.append((action_type, status))
            
            error_str = (error_message[:47] + "...") if error_message else ""
            symbol_str = str(symbol) if symbol else ""
            time_str = str(created_at) if created_at else "N/A"
            
            print(f"{action_type:<30} {symbol_str:<10} {status:<12} {error_str:<50} {time_str:<25}")

        print("\n" + "=" * 140)
        print(f"Today is: {today}")
        print(f"Actions TODAY: {len(today_actions)}")
        print(f"Actions YESTERDAY: {len(yesterday_actions)}")
        
        if today_actions:
            print(f"\nToday's actions:")
            for action, status in today_actions:
                print(f"  {action}: {status}")

        if not results:
            print("No recent algo actions found in database!")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
