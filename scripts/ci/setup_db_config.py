#!/usr/bin/env python3
"""Write /tmp/db_config.py from the SECRET env var (JSON from Secrets Manager).

Called by the deploy-all-infrastructure.yml run-migrations job.
Keeps credentials out of GITHUB_ENV and process argv.
"""

import json
import os
import sys

secret_str = os.environ.get("SECRET")
if not secret_str:
    print("ERROR: SECRET environment variable not set. Cannot configure database credentials.", file=sys.stderr)
    sys.exit(1)

try:
    secret = json.loads(secret_str)

    # All database credentials are REQUIRED - no defaults allowed for production safety
    required_keys = ["host", "port", "username", "password", "dbname"]
    missing_keys = [k for k in required_keys if k not in secret or secret[k] is None]
    if missing_keys:
        print(
            f"ERROR: Secret missing required database credential fields: {missing_keys}. "
            f"All of {required_keys} must be present in AWS Secrets Manager.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate port is numeric
    try:
        port = int(secret["port"])
    except (ValueError, TypeError):
        print(f"ERROR: DB_PORT must be a valid integer, got: {secret['port']}", file=sys.stderr)
        sys.exit(1)

    # Validate password is not empty
    if not secret["password"] or not str(secret["password"]).strip():
        print("ERROR: DB_PASSWORD must not be empty. Check AWS Secrets Manager for valid credentials.", file=sys.stderr)
        sys.exit(1)

    lines = [
        "import os",
        f"os.environ['DB_HOST'] = {secret['host']!r}",
        f"os.environ['DB_PORT'] = {str(port)!r}",
        f"os.environ['DB_USER'] = {secret['username']!r}",
        f"os.environ['DB_PASSWORD'] = {secret['password']!r}",
        f"os.environ['DB_NAME'] = {secret['dbname']!r}",
        "os.environ['DB_SSL'] = 'require'",
    ]
    with open("/tmp/db_config.py", "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod("/tmp/db_config.py", 0o600)
    print("Database credentials stored securely")
except json.JSONDecodeError as e:
    print(f"ERROR: Failed to parse SECRET as JSON: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Failed to process credentials: {e}", file=sys.stderr)
    sys.exit(1)
