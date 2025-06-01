# ECS Container Test Environment

This directory contains a comprehensive test environment that simulates running data loading scripts in an AWS ECS container environment.

## Overview

The test environment provides:
- **Docker-based PostgreSQL database** that mimics the production database
- **Mock AWS services** (Secrets Manager, S3, SNS, SQS) to avoid real AWS calls during testing
- **Test runners** that execute scripts with proper logging and error handling
- **Database initialization** with required tables and test data

## Files Structure

```
test/
├── docker-compose.yml      # Docker services configuration
├── Dockerfile.test         # Container definition for test environment
├── requirements.txt        # Python dependencies
├── init.sql               # Database initialization script
├── mock_boto3.py          # Mock AWS boto3 implementation
├── wrapper.py             # Script execution wrapper
├── run_direct_test.py     # Direct execution test runner (recommended)
├── test_runner.py         # Subprocess-based test runner
├── test_config.py         # Test configuration and utilities
└── README.md             # This file
```

## Quick Start

### Prerequisites
- Docker and Docker Compose installed
- PowerShell (on Windows)

### Running Tests

1. **Start the test environment:**
   ```powershell
   cd c:\code\deploy\loadfundamentals\test
   docker-compose up --build
   ```

2. **Alternative: Run specific tests manually:**
   ```powershell
   # Start just the database
   docker-compose up -d postgres
   
   # Run tests in the container
   docker-compose run test-runner python run_direct_test.py
   ```

3. **Clean up:**
   ```powershell
   docker-compose down -v
   ```

## Test Environment Features

### Mock AWS Services

The `mock_boto3.py` module intercepts all AWS API calls and provides mock responses:

- **Secrets Manager**: Returns test database credentials
- **S3**: Mocks object storage operations
- **SNS**: Mocks notification publishing
- **SQS**: Mocks message queue operations

### Database Setup

The test database is automatically initialized with:
- **stocks** table for stock symbols and company information
- **earnings** table for earnings data
- **prices** table for price data
- Test data including AAPL, GOOGL, MSFT, TSLA, etc.

### Test Runners

**run_direct_test.py** (Recommended):
- Executes scripts directly in the same process
- Provides complete log visibility
- Better error handling and debugging

**test_runner.py** (Alternative):
- Uses subprocess execution with the wrapper
- Good for isolation between tests
- More complex log capturing

### Environment Variables

The test environment sets these key variables:
- `DB_SECRET_ARN=test-db-secret`
- `PYTHONUNBUFFERED=1`
- `PYTHONPATH=/app:/app/test`

## Adding New Tests

1. **Create a test version of your script:**
   - Copy the original script (e.g., `loadstocksymbols.py`)
   - Rename it with `_test.py` suffix (e.g., `loadstocksymbols_test.py`)
   - Add enhanced logging and any test-specific modifications

2. **Update test runners:**
   - Add the new script to the `test_scripts` list in `run_direct_test.py`
   - Add it to `test_runner.py` if using subprocess execution

3. **Test the new script:**
   ```powershell
   docker-compose run test-runner python run_direct_test.py
   ```

## Debugging

### View logs in real-time:
```powershell
docker-compose logs -f test-runner
```

### Connect to the test database:
```powershell
docker-compose exec postgres psql -U testuser -d testdb
```

### Run health checks:
```powershell
docker-compose run test-runner python test_config.py
```

### Access the test container:
```powershell
docker-compose run test-runner bash
```

## Configuration

### Database Configuration
- Host: `postgres` (Docker service name)
- Port: `5432`
- User: `testuser`
- Password: `testpass`
- Database: `testdb`

### Mock AWS Configuration
- Region: `us-east-1`
- Secret ARN: `test-db-secret`
- All AWS credentials are mocked (no real AWS access needed)

## Troubleshooting

### Common Issues:

1. **Database not ready:**
   - The test runners wait for PostgreSQL to be ready
   - Check logs: `docker-compose logs postgres`

2. **Import errors:**
   - Ensure `PYTHONPATH` includes both `/app` and `/app/test`
   - Check that all dependencies are in `requirements.txt`

3. **Script execution errors:**
   - Check that test scripts have the same dependencies as original scripts
   - Verify mock boto3 is properly intercepting AWS calls

4. **Port conflicts:**
   - If port 5432 is in use, modify the port mapping in `docker-compose.yml`

### Viewing detailed logs:
```powershell
# All services
docker-compose logs

# Specific service
docker-compose logs test-runner
docker-compose logs postgres
```

## Best Practices

1. **Always test locally first** before deploying to production
2. **Use enhanced logging** in test scripts for better debugging
3. **Check database state** before and after tests
4. **Clean up resources** when done testing
5. **Document any test-specific modifications** in your test scripts

## Extending the Environment

The test environment can be extended to support:
- Additional AWS services (Lambda, CloudWatch, etc.)
- Different database configurations
- Performance testing and load simulation
- Integration with CI/CD pipelines
- Custom test data sets

## Production Simulation

This environment closely simulates the AWS ECS production environment by:
- Using the same Python dependencies
- Mocking all AWS service calls
- Providing a PostgreSQL database similar to production
- Setting similar environment variables
- Running scripts in a containerized environment
