# AWS RDS Integration for Dashboard

This guide explains how to integrate AWS RDS credentials fetching into the dashboard.

## Overview

The dashboard can now fetch RDS credentials from AWS Secrets Manager and automatically connect to production AWS RDS instead of localhost.

**Two new modules:**
1. `dashboard/aws_rds_init.py` - Credential fetching and environment setup
2. `dashboard/bootstrap.py` - Integration with dashboard startup

## Quick Start

### Option 1: Automatic Bootstrap (Recommended)

Add this to `dashboard/__main__.py` or `dashboard/dashboard.py` BEFORE any database imports:

```python
#!/usr/bin/env python3
"""Dashboard entry point with AWS RDS bootstrap."""

import os
import sys

# Bootstrap RDS credentials FIRST (before any database imports)
if __name__ == "__main__":
    from dashboard.bootstrap import bootstrap_dashboard_database

    # Initialize AWS RDS credentials from Secrets Manager or environment
    bootstrap_dashboard_database(
        aws_region=os.getenv("AWS_REGION", "us-east-1"),
        force_aws=os.getenv("FORCE_AWS", "").lower() in ("true", "1"),
        verbose=True,  # Log bootstrap steps
    )

# NOW import modules that use the database
from dashboard.dashboard import main

if __name__ == "__main__":
    main()
```

### Option 2: Manual Setup

If you need more control:

```python
from dashboard.aws_rds_init import initialize_aws_rds_credentials

# Fetch credentials and set environment variables
credentials = initialize_aws_rds_credentials(
    secret_name="algo/rds",  # AWS Secrets Manager secret name/ARN
    aws_region="us-east-1",
    force_aws=False,  # Allow local dev to use env vars
    validate_connection=True,  # Fail fast if connection doesn't work
)

print(f"Connected to {credentials['host']}:{credentials['port']}/{credentials['dbname']}")

# Now use database as normal
from utils.db import DatabaseContext
with DatabaseContext('read') as cur:
    cur.execute("SELECT version()")
    version = cur.fetchone()
    print(f"PostgreSQL version: {version}")
```

## Environment Configuration

### AWS Deployment

Set these environment variables on your Lambda/ECS container:

```bash
# RDS Secret (full ARN preferred)
DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123456789:secret:algo/rds-xxxxx

# Alternatively, simple name (if using same region)
DB_SECRET_NAME=algo/rds

# AWS Region
AWS_REGION=us-east-1

# Optional: Force AWS Secrets Manager in local dev
FORCE_AWS=false
```

### Local Development

For local development WITHOUT AWS credentials, set these directly:

```bash
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=algo
```

The system will use these environment variables as fallback if AWS Secrets Manager is unavailable.

## How It Works

### Priority Order for Credentials

1. **AWS Secrets Manager** (if `DB_SECRET_ARN` or `DB_SECRET_NAME` set and in AWS environment)
   - Fetches credentials from AWS Secrets Manager
   - Secret must contain: `host`, `port`, `username`, `password`, `dbname`
   - Fast timeout (3s connect, 5s read) to fail fast if SM unavailable

2. **Environment Variables** (fallback)
   - `DB_HOST` or `DB_ENDPOINT` - database host
   - `DB_PORT` - database port (default 5432)
   - `DB_USER` - database user
   - `DB_PASSWORD` - database password
   - `DB_NAME` - database name

3. **Fail Fast** - If credentials cannot be obtained, raises `AWSRDSInitializationError`

### Connection Validation

By default, `initialize_aws_rds_credentials()` performs a `SELECT 1` query to validate the connection works BEFORE the dashboard starts. This prevents:

- Hanging dashboard on bad credentials
- Silent connection failures during dashboard rendering
- Wasting time debugging connection issues later

Disable validation with `validate_connection=False` if needed.

### Environment Variable Setting

After fetching credentials, the system sets environment variables:

```python
os.environ["DB_HOST"] = "prod-rds.xxxxx.rds.amazonaws.com"
os.environ["DB_PORT"] = "5432"
os.environ["DB_USER"] = "postgres"
os.environ["DB_PASSWORD"] = "secret_password"
os.environ["DB_NAME"] = "algo"
```

These are automatically picked up by `utils.db.connection.get_db_connection()`.

## Integration Examples

### Example 1: Dashboard Module Integration

**File: `dashboard/dashboard.py`**

```python
#!/usr/bin/env python3
"""Algo Ops Terminal Dashboard"""

import os
import sys

# Bootstrap RDS credentials FIRST (before any database imports)
from dashboard.bootstrap import bootstrap_dashboard_database

def main():
    """Main entry point."""
    # Initialize AWS RDS credentials before dashboard starts
    try:
        bootstrap_dashboard_database(
            aws_region=os.getenv("AWS_REGION"),
            force_aws=os.getenv("FORCE_AWS", "").lower() in ("true", "1"),
            verbose=True,
        )
    except RuntimeError as e:
        print(f"CRITICAL: Failed to initialize database: {e}")
        sys.exit(1)

    # Now import and run dashboard
    from dashboard.core import run_dashboard
    run_dashboard()

if __name__ == "__main__":
    main()
```

### Example 2: Local API Server Integration

**File: `dashboard/local_api_server.py`**

```python
#!/usr/bin/env python3
"""Local API server for development - serves dashboard data."""

import json
import os
import sys
from pathlib import Path

# Bootstrap RDS credentials FIRST
from dashboard.bootstrap import bootstrap_dashboard_database

# Setup paths
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

# Initialize database
bootstrap_dashboard_database(
    force_aws=os.getenv("FORCE_AWS", "").lower() in ("true", "1"),
    skip_validation=False,
    verbose=True,
)

# NOW import database modules
from utils.db import get_db_connection
import psycopg2.extras

class APIHandler:
    """Handle HTTP requests and return dashboard data."""

    def _handle_positions(self):
        """Return positions data from AWS RDS."""
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Now this uses AWS RDS, not localhost!
            cur.execute("SELECT * FROM algo_positions")
            positions = cur.fetchall()

            cur.close()
            conn.close()

            return {
                'statusCode': 200,
                'data': {'items': positions}
            }
        except Exception as e:
            return {'statusCode': 500, 'error': str(e)}
```

### Example 3: Testing Connection

```python
from dashboard.bootstrap import (
    bootstrap_dashboard_database,
    check_database_connectivity,
    get_dashboard_database_config,
)

# Bootstrap
bootstrap_dashboard_database()

# Check config
config = get_dashboard_database_config()
print(f"Connected to: {config['host']}:{config['port']}/{config['database']}")

# Verify connectivity
if check_database_connectivity():
    print("✓ Database connection OK")
else:
    print("✗ Database connection failed")
```

## Troubleshooting

### Problem: "DB_HOST environment variable not set"

**Cause:** Bootstrap wasn't called or failed silently

**Solution:** Ensure `bootstrap_dashboard_database()` is called BEFORE any database imports:

```python
# BEFORE any "from utils.db import..." statements
from dashboard.bootstrap import bootstrap_dashboard_database
bootstrap_dashboard_database()

# AFTER bootstrap, then import
from utils.db import DatabaseContext
```

### Problem: "Failed to fetch from Secrets Manager"

**Cause:** AWS Secrets Manager secret not found or IAM permissions missing

**Solution:**
1. Verify secret exists: `aws secretsmanager get-secret-value --secret-id algo/rds`
2. Verify IAM role has `secretsmanager:GetSecretValue` permission
3. Verify `DB_SECRET_ARN` or `DB_SECRET_NAME` is set correctly
4. Check `AWS_REGION` is correct

To force using environment variables instead of Secrets Manager:

```bash
# Don't set DB_SECRET_ARN
unset DB_SECRET_ARN

# Set environment variables directly
export DB_HOST=your_host
export DB_PORT=5432
export DB_USER=your_user
export DB_PASSWORD=your_password
export DB_NAME=your_db

# Now bootstrap will use env vars
python -m dashboard
```

### Problem: "Database connection validation failed"

**Cause:** RDS endpoint unreachable, wrong credentials, or network issue

**Solution:**
1. Test connection manually:
   ```bash
   psql -h $DB_HOST -U $DB_USER -d $DB_NAME
   ```

2. Check RDS security group allows your IP

3. Verify credentials in AWS Secrets Manager

4. Skip validation during debug (NOT for production):
   ```python
   bootstrap_dashboard_database(skip_validation=True, verbose=True)
   ```

### Problem: "Connection timeout"

**Cause:** RDS endpoint not responding or network unreachable

**Solution:**
1. Verify RDS instance is running
2. Check security group inbound rules
3. Check VPC/subnet routing to RDS
4. Verify RDS endpoint is correct

## Architecture

```
dashboard startup
    ↓
bootstrap_dashboard_database()
    ↓
    ├─ RDSCredentialFetcher.get_credentials_from_env_or_secrets()
    │   ├─ Try AWS Secrets Manager (if secret_name provided)
    │   └─ Fall back to environment variables
    │
    ├─ set_aws_rds_environment_variables()
    │   └─ Sets DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
    │
    └─ validate_aws_rds_connection() [optional]
        └─ Runs SELECT 1 to verify connectivity
            ↓
utils.db.connection.get_db_connection()
    ↓
    Reads environment variables (now pointing to AWS RDS)
    ↓
psycopg2 connects to AWS RDS
    ↓
Dashboard uses AWS production data
```

## Security Considerations

1. **Never hardcode credentials** - Always use Secrets Manager or environment variables
2. **Credentials are validated** - Missing or invalid credentials fail fast
3. **No credential logging** - Passwords never appear in logs (truncated)
4. **Short timeouts** - Secrets Manager calls timeout after 5s to fail fast
5. **Connection pooling** - utils.db handles connection reuse safely
6. **Encryption in transit** - Always use TLS/SSL to RDS

## API Reference

### `initialize_aws_rds_credentials()`

```python
def initialize_aws_rds_credentials(
    secret_name: str | None = None,
    aws_region: str | None = None,
    force_aws: bool = False,
    validate_connection: bool = True,
    verbose: bool = True,
) -> dict[str, Any]:
    """Initialize AWS RDS credentials.

    Returns:
        {'host': str, 'port': int, 'username': str, 'password': str, 'dbname': str}

    Raises:
        AWSRDSInitializationError: If initialization fails
    """
```

### `bootstrap_dashboard_database()`

```python
def bootstrap_dashboard_database(
    aws_region: str | None = None,
    secret_name: str | None = None,
    force_aws: bool = False,
    skip_validation: bool = False,
    verbose: bool = True,
) -> None:
    """Bootstrap dashboard database.

    Call this BEFORE any database imports.

    Raises:
        RuntimeError: If bootstrap fails
    """
```

### `get_dashboard_database_config()`

```python
def get_dashboard_database_config() -> dict[str, Any]:
    """Get current database configuration.

    Returns:
        {'host': str, 'port': int, 'user': str, 'password': str, 'database': str}

    Raises:
        RuntimeError: If configuration is incomplete
    """
```

### `check_database_connectivity()`

```python
def check_database_connectivity() -> bool:
    """Check if database connection works.

    Returns:
        True if connection OK, False if not initialized

    Raises:
        RuntimeError: If connection fails
    """
```

## Testing

### Manual Test

```bash
# Set credentials
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=postgres
export DB_PASSWORD=your_password
export DB_NAME=algo

# Test bootstrap
python -c "
from dashboard.bootstrap import bootstrap_dashboard_database, check_database_connectivity
bootstrap_dashboard_database(skip_validation=False)
print('✓ Bootstrap successful')
"
```

### With AWS Secrets Manager

```bash
export AWS_REGION=us-east-1
export DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123:secret:algo/rds-xxxxx
export FORCE_AWS=true

python -c "
from dashboard.aws_rds_init import initialize_aws_rds_credentials
creds = initialize_aws_rds_credentials()
print(f'Connected to {creds[\"host\"]}')
"
```

## Next Steps

1. Add bootstrap call to `dashboard/__main__.py`
2. Test with local PostgreSQL (using environment variables)
3. Deploy to AWS Lambda/ECS
4. Set `DB_SECRET_ARN` environment variable pointing to RDS secret
5. Verify dashboard connects to production AWS RDS

## Additional Resources

- AWS Secrets Manager: https://docs.aws.amazon.com/secretsmanager/
- RDS Connection Best Practices: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/
- PostgreSQL psycopg2: https://www.psycopg.org/
