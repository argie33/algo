#!/usr/bin/env python3
"""Check NOEM mention details."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.db import DatabaseContext

try:
    with DatabaseContext("read") as cur:
        # Get all NOEM mentions
        cur.execute(
            """
            SELECT created_at, action_type, status, details::TEXT as full_details
            FROM algo_audit_log
            WHERE created_at > NOW() - INTERVAL '3 hours'
            AND (action_type ILIKE '%NOEM%' OR details::TEXT ILIKE '%NOEM%')
            ORDER BY created_at DESC
            """
        )

        noem_logs = cur.fetchall()
        if noem_logs:
            print(f"Found {len(noem_logs)} NOEM mentions:\n")
            for created_at, action_type, status, details in noem_logs:
                print(f"[{created_at}] {action_type} [{status}]")
                if 'NOEM' in details:
                    # Extract just the relevant part
                    import json
                    try:
                        data = json.loads(details)
                        if 'summary' in data:
                            print(f"  Summary: {data['summary'][:100]}")
                    except:
                        idx = details.find('NOEM')
                        print(f"  {details[max(0, idx-20):min(len(details), idx+80)]}")
                print()
        else:
            print("No NOEM mentions found!")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
