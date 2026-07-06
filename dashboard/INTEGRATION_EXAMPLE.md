# Integration Example: Updating Dashboard to Use AWS RDS

This document shows concrete examples of how to integrate the AWS RDS initialization into existing dashboard files.

## Example 1: Update `dashboard/__main__.py`

**Before:**
```python
"""Entry point for running dashboard as a module."""

from .dashboard import main

if __name__ == "__main__":
    main()
```

**After:**
```python
"""Entry point for running dashboard as a module."""

import os
import sys

# Bootstrap RDS credentials FIRST (before any database imports)
if __name__ == "__main__":
    from dashboard.bootstrap import bootstrap_dashboard_database

    try:
        bootstrap_dashboard_database(
            aws_region=os.getenv("AWS_REGION"),
            force_aws=os.getenv("FORCE_AWS", "").lower() in ("true", "1"),
            verbose=True,
        )
    except RuntimeError as e:
        print(f"CRITICAL: Failed to initialize database: {e}")
        sys.exit(1)

# NOW import modules that use the database
from .dashboard import main

if __name__ == "__main__":
    main()
```

## Example 2: Update `dashboard/local_api_server.py`

**Before:**
```python
#!/usr/bin/env python3
"""Local API server for development - serves dashboard data."""

import json
import os
import sys
from pathlib import Path
import psycopg2.extras

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "lambda" / "api"))
os.environ['ENVIRONMENT'] = 'dev'

from utils.data_queries import get_open_positions
from utils.db import get_db_connection  # Uses localhost by default

class APIHandler(BaseHTTPRequestHandler):
    def _handle_positions(self):
        try:
            conn = get_db_connection()  # Connects to localhost
            # ... rest of handler
```

**After:**
```python
#!/usr/bin/env python3
"""Local API server for development - serves dashboard data."""

import json
import os
import sys
from pathlib import Path
import psycopg2.extras

# Bootstrap RDS credentials FIRST (before any database imports)
from dashboard.bootstrap import bootstrap_dashboard_database

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "lambda" / "api"))
os.environ['ENVIRONMENT'] = 'dev'

# Initialize AWS RDS credentials
try:
    bootstrap_dashboard_database(
        aws_region=os.getenv("AWS_REGION", "us-east-1"),
        force_aws=os.getenv("FORCE_AWS", "").lower() in ("true", "1"),
        verbose=True,
    )
except RuntimeError as e:
    print(f"CRITICAL: Failed to initialize database: {e}")
    sys.exit(1)

# NOW import database modules
from utils.data_queries import get_open_positions
from utils.db import get_db_connection  # Now connects to AWS RDS!

class APIHandler(BaseHTTPRequestHandler):
    def _handle_positions(self):
        try:
            conn = get_db_connection()  # Connects to AWS RDS
            # ... rest of handler (no changes needed)
```

## Example 3: Update Dashboard Main Function

**Before:**
```python
def main():
    """Main entry point."""
    from rich.layout import Layout
    from rich.live import Live

    from dashboard.api_data_layer import set_api_url, set_cognito_auth, validate_api_config
    from dashboard.fetchers import load_all
    from dashboard.renderers import render_dashboard_body

    # Direct imports - no DB initialization
    # ... rest of function
```

**After:**
```python
def main():
    """Main entry point."""
    import os
    import sys

    # Bootstrap RDS credentials FIRST
    from dashboard.bootstrap import bootstrap_dashboard_database

    try:
        bootstrap_dashboard_database(
            aws_region=os.getenv("AWS_REGION"),
            force_aws=os.getenv("FORCE_AWS", "").lower() in ("true", "1"),
            verbose=True,
        )
    except RuntimeError as e:
        print(f"CRITICAL: Failed to initialize database: {e}")
        sys.exit(1)

    # Now import other modules
    from rich.layout import Layout
    from rich.live import Live

    from dashboard.api_data_layer import set_api_url, set_cognito_auth, validate_api_config
    from dashboard.fetchers import load_all
    from dashboard.renderers import render_dashboard_body

    # ... rest of function (unchanged)
```

## Example 4: Create a Dashboard Configuration Module

**New file: `dashboard/config.py`**

```python
"""Dashboard configuration with RDS initialization."""

import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)


class DashboardConfig:
    """Dashboard configuration with AWS RDS support."""

    def __init__(self):
        self.aws_region = os.getenv("AWS_REGION", "us-east-1")
        self.force_aws = os.getenv("FORCE_AWS", "").lower() in ("true", "1")
        self.environment = os.getenv("ENVIRONMENT", "dev")
        self.debug = self.environment == "dev"
        self.db_initialized = False

    def initialize(self) -> None:
        """Initialize AWS RDS connection.

        Call this at startup, before any database operations.
        """
        if self.db_initialized:
            logger.debug("Database already initialized")
            return

        try:
            from dashboard.bootstrap import bootstrap_dashboard_database

            bootstrap_dashboard_database(
                aws_region=self.aws_region,
                force_aws=self.force_aws,
                verbose=self.debug,
            )
            self.db_initialized = True
            logger.info("Database initialized successfully")
        except RuntimeError as e:
            logger.error(f"Failed to initialize database: {e}")
            if self.environment != "dev":
                # Fail hard in production
                sys.exit(1)
            # In dev, allow continued operation (may fail on first DB call)

    def get_database_config(self) -> dict[str, Any]:
        """Get database configuration."""
        from dashboard.bootstrap import get_dashboard_database_config

        return get_dashboard_database_config()

    def check_database_connectivity(self) -> bool:
        """Check if database is accessible."""
        from dashboard.bootstrap import check_database_connectivity

        try:
            return check_database_connectivity()
        except Exception as e:
            logger.error(f"Database connectivity check failed: {e}")
            return False


# Global config instance
_config = None


def get_config() -> DashboardConfig:
    """Get or create global dashboard config."""
    global _config
    if _config is None:
        _config = DashboardConfig()
    return _config


def initialize_dashboard() -> None:
    """Initialize dashboard (call at startup)."""
    config = get_config()
    config.initialize()
```

**Usage in dashboard:**

```python
def main():
    from dashboard.config import initialize_dashboard, get_config

    # Initialize dashboard (includes RDS setup)
    initialize_dashboard()

    config = get_config()
    print(f"Environment: {config.environment}")
    print(f"Database initialized: {config.db_initialized}")

    # Now use database
    from utils.db import DatabaseContext
    with DatabaseContext('read') as cur:
        cur.execute("SELECT version()")
        version = cur.fetchone()
        print(f"PostgreSQL: {version}")
```

## Example 5: Docker Integration

**Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .

# Install dependencies
RUN pip install -r requirements.txt

# Set environment for AWS RDS
ENV ENVIRONMENT=prod
ENV AWS_REGION=us-east-1
ENV PYTHONUNBUFFERED=1

# Run dashboard with bootstrap
CMD ["python", "-m", "dashboard"]
```

**Docker run command:**

```bash
# With AWS Secrets Manager
docker run -e AWS_REGION=us-east-1 \
           -e DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123:secret:algo/rds \
           algo-dashboard:latest

# With environment variables
docker run -e DB_HOST=localhost \
           -e DB_PORT=5432 \
           -e DB_USER=postgres \
           -e DB_PASSWORD=secret \
           -e DB_NAME=algo \
           algo-dashboard:latest
```

## Example 6: Lambda Function Integration

**lambda/dashboard_handler.py**

```python
"""AWS Lambda handler for dashboard API."""

import json
import os
from typing import Any

# Bootstrap RDS at Lambda cold start
from dashboard.bootstrap import bootstrap_dashboard_database

_db_initialized = False


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle Lambda invocation."""
    global _db_initialized

    # Initialize database on first invocation (cold start)
    if not _db_initialized:
        try:
            bootstrap_dashboard_database(
                aws_region=os.getenv("AWS_REGION", "us-east-1"),
                force_aws=True,  # Force AWS in Lambda environment
                verbose=True,
            )
            _db_initialized = True
        except RuntimeError as e:
            return {
                "statusCode": 500,
                "body": json.dumps({"error": f"Database initialization failed: {e}"}),
            }

    # Handle request
    path = event.get("path", "/")

    if path == "/api/positions":
        return handle_positions()
    elif path == "/api/portfolio":
        return handle_portfolio()
    # ... other endpoints
    else:
        return {
            "statusCode": 404,
            "body": json.dumps({"error": "Not found"}),
        }


def handle_positions() -> dict[str, Any]:
    """Get positions from AWS RDS."""
    from utils.db import DatabaseContext

    try:
        with DatabaseContext('read') as cur:
            cur.execute("SELECT * FROM algo_positions WHERE status='open'")
            positions = cur.fetchall()

        return {
            "statusCode": 200,
            "body": json.dumps({
                "data": positions,
                "count": len(positions),
            }),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }
```

## Example 7: Testing Integration

**tests/test_dashboard_rds.py**

```python
"""Test dashboard RDS integration."""

import os
import pytest


@pytest.fixture
def setup_db():
    """Setup database for testing."""
    from dashboard.bootstrap import bootstrap_dashboard_database

    bootstrap_dashboard_database(
        skip_validation=False,
        verbose=True,
    )
    yield
    # Teardown if needed


def test_dashboard_database_connection(setup_db):
    """Test dashboard can connect to database."""
    from dashboard.bootstrap import check_database_connectivity

    assert check_database_connectivity()


def test_dashboard_positions_query(setup_db):
    """Test positions query works."""
    from utils.db import DatabaseContext

    with DatabaseContext('read') as cur:
        cur.execute("SELECT COUNT(*) FROM algo_positions")
        count = cur.fetchone()
        assert count is not None
        assert count[0] >= 0


def test_credentials_from_env():
    """Test credentials loaded from environment."""
    os.environ["DB_HOST"] = "test-host"
    os.environ["DB_PORT"] = "5432"
    os.environ["DB_USER"] = "test-user"
    os.environ["DB_PASSWORD"] = "test-password"
    os.environ["DB_NAME"] = "test-db"

    from dashboard.bootstrap import get_dashboard_database_config

    config = get_dashboard_database_config()
    assert config["host"] == "test-host"
    assert config["database"] == "test-db"
```

## Step-by-Step Migration Checklist

- [ ] Add `aws_rds_init.py` to dashboard
- [ ] Add `bootstrap.py` to dashboard
- [ ] Update `dashboard/__main__.py` with bootstrap call
- [ ] Update `dashboard/dashboard.py` main() with bootstrap call
- [ ] Update `dashboard/local_api_server.py` with bootstrap call
- [ ] Test with environment variables locally
- [ ] Test with AWS Secrets Manager in dev AWS account
- [ ] Deploy to production Lambda/ECS
- [ ] Set `DB_SECRET_ARN` environment variable
- [ ] Verify dashboard connects to production RDS
- [ ] Monitor CloudWatch logs for connection issues
- [ ] Document in runbooks

## Testing Before Deployment

```bash
# 1. Test with environment variables
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=postgres
export DB_PASSWORD=secret
export DB_NAME=algo
python dashboard/test_aws_rds_connection.py

# 2. Test with AWS Secrets Manager (dev account)
export AWS_REGION=us-east-1
export DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123:secret:algo/rds
export FORCE_AWS=true
python dashboard/test_aws_rds_connection.py --all

# 3. Test dashboard startup
python -m dashboard --local

# 4. Test API endpoints
curl http://localhost:8000/api/algo/positions
curl http://localhost:8000/api/algo/portfolio
```

## Rollback Plan

If issues occur in production:

1. **Quick rollback** - Set environment variables directly (revert to using localhost or backup RDS):
   ```bash
   export DB_HOST=backup-rds-endpoint
   export FORCE_AWS=false
   ```

2. **Code rollback** - Remove bootstrap calls, revert changes to `__main__.py` and `dashboard.py`

3. **Database failover** - Update `DB_SECRET_ARN` to point to backup RDS instance

4. **Verify** - Test with `python dashboard/test_aws_rds_connection.py`
