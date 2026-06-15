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
        f"os.environ['DB_HOST'] = {repr(secret.get('host', 'localhost'))}",
        f"os.environ['DB_PORT'] = {repr(str(secret.get('port', 5432)))}",
        f"os.environ['DB_USER'] = {repr(secret.get('username', 'postgres'))}",
        f"os.environ['DB_PASSWORD'] = {repr(secret.get('password', ''))}",
        f"os.environ['DB_NAME'] = {repr(secret.get('dbname', 'algo'))}",
        "os.environ['DB_SSL'] = 'require'",
    ]
    with open("/tmp/db_config.py", "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod("/tmp/db_config.py", 0o600)
    print("Database credentials stored securely")
except Exception as e:
    print(f"ERROR: Failed to process credentials: {e}", file=sys.stderr)
    sys.exit(1)
