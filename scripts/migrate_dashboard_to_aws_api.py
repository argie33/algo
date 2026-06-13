#!/usr/bin/env python3
"""
Migrate dashboard.py to use AWS Lambda API exclusively.
Removes all database queries and local fallbacks.
"""

import re
import sys

# Read the file
with open("tools/dashboard/dashboard.py", "r", encoding="utf-8") as f:
    content = f.read()

original = content

# 1. Remove database imports
content = re.sub(
    r'try:\s*from api_data_layer import DashboardDataAPI\nexcept ImportError:\s*DashboardDataAPI = None\n\n',
    '',
    content
)

content = re.sub(
    r'try:\s*import boto3\nexcept ImportError:\s*sys\.exit\("pip install boto3"\)\n\n',
    '',
    content
)

content = re.sub(
    r'try:\s*import psycopg2, psycopg2\.extras, psycopg2\.pool\nexcept ImportError:\s*sys\.exit\("pip install psycopg2-binary"\)\n\n',
    '',
    content
)

# 2. Remove database pool initialization and credential loading code
content = re.sub(
    r'# Connection pool.*?_db_creds_loaded = False\n\ndef _load_db_credentials_from_secrets\(\):.*?return False\n\ndef _init_dashboard_pool\(\):.*?_dashboard_pool = None\n',
    '# Note: All data now comes from AWS APIs - no local database fallbacks.\n',
    content,
    flags=re.DOTALL
)

# 3. Remove database helper functions (get_conn, return_conn, q, q1)
content = re.sub(
    r'# ── DB helpers ──.*?def q1\(c, sql, p=None\):.*?return rows\[0\] if rows else None\n\n',
    '# ── API helpers ──────────────────────────────────────────────────────────────────\n# All database queries now go through the Lambda API.\n\n',
    content,
    flags=re.DOTALL
)

# Count changes
changes = sum(1 for c1, c2 in zip(original, content) if c1 != c2)
print(f"Database code removed: {(len(original) - len(content)) / 1000:.1f}KB")

# Write the file
with open("tools/dashboard/dashboard.py", "w", encoding="utf-8") as f:
    f.write(content)

print("[OK] Migration script executed")
print("Next: Convert fetch_* functions to API calls (see DASHBOARD_API_MIGRATION.md)")
