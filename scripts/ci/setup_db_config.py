#!/usr/bin/env python3
"""Write /tmp/db_config.py from the SECRET env var (JSON from Secrets Manager).

Called by the deploy-all-infrastructure.yml run-migrations job.
Keeps credentials out of GITHUB_ENV and process argv.
"""

import json
import os
import sys

secret_str = os.environ.get("SECRET", "{}")
try:
    secret = json.loads(secret_str)
    lines = [
        "import os",
        f"os.environ['DB_HOST'] = {secret.get('host', 'localhost')!r}",
        f"os.environ['DB_PORT'] = {str(secret.get('port', 5432))!r}",
        f"os.environ['DB_USER'] = {secret.get('username', 'postgres')!r}",
        f"os.environ['DB_PASSWORD'] = {secret.get('password', '')!r}",
        f"os.environ['DB_NAME'] = {secret.get('dbname', 'algo')!r}",
        "os.environ['DB_SSL'] = 'require'",
    ]
    with open("/tmp/db_config.py", "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod("/tmp/db_config.py", 0o600)
    print("Database credentials stored securely")
except Exception as e:
    print(f"ERROR: Failed to process credentials: {e}", file=sys.stderr)
    sys.exit(1)
