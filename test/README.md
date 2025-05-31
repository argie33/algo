# Test Environment for Load Scripts

This test environment allows you to run your existing Python scripts without modification in a Docker-based environment with a local PostgreSQL database.

## How It Works

The test environment uses a clever approach to avoid modifying your existing scripts:

1. **Mock AWS Secrets Manager**: A custom `mock_boto3.py` module intercepts calls to AWS Secrets Manager and returns local database credentials instead
2. **Docker Environment**: PostgreSQL runs in a Docker container with known credentials
3. **No Script Changes**: Your existing `.py` files run unchanged - they still call `boto3.client("secretsmanager")` but get our mock implementation

## Quick Start

1. **Prerequisites**: 
   - Docker and Docker Compose installed
   - PowerShell (for Windows users)

2. **Run Tests (PowerShell)**:
   ```powershell
   cd c:\code\deploy\loadfundamentals\test
   .\run_tests.ps1
   ```

3. **Run Tests (Command Prompt)**:
   ```cmd
   cd c:\code\deploy\loadfundamentals\test
   run_tests.bat
   ```

4. **Run Tests (Python)**:
   ```bash
   cd c:\code\deploy\loadfundamentals\test
   python run_tests.py
   ```

## Adding Your Other Two Scripts

To add the other two scripts you want to test:

### Method 1: Use the helper script
```powershell
python add_test_script.py loadanalystupgradedowngrade.py
python add_test_script.py loadbuysell.py
```

### Method 2: Manual editing
Edit `test_runner.py` and update the `scripts_to_test` list:
```python
scripts_to_test = [
    ("/app/source/loadstocksymbols_test.py", "loadstocksymbols_test.py"),
    ("/app/source/loadanalystupgradedowngrade.py", "loadanalystupgradedowngrade.py"),
    ("/app/source/loadbuysell.py", "loadbuysell.py"),
]
```

## What Gets Tested

Currently configured to test:
- `loadstocksymbols_test.py` (your test script with 5 stocks + 5 ETFs)

After adding your other scripts, it will test all three in sequence.

## Test Environment Components

### Files Created:
- `docker-compose.yml` - Orchestrates PostgreSQL and test runner containers
- `Dockerfile.test` - Builds the test runner container
- `mock_boto3.py` - Intercepts AWS calls and provides local DB credentials
- `test_runner.py` - Executes your scripts and captures logs
- `run_tests.py` - Simple wrapper to run the entire test suite
- `requirements.txt` - Python dependencies for the test environment
- `init.sql` - PostgreSQL initialization script

### Database Configuration:
- **Host**: postgres (Docker service name)
- **Port**: 5432
- **Database**: stocksdb
- **Username**: stocksuser
- **Password**: stockspass

## Log Output

Logs are captured in two ways:
1. **Real-time console output**: You'll see logs from each script as they run
2. **Log files**: Saved in the `logs/` directory for later review

## Adding More Scripts

To test additional scripts:

1. Edit `test_runner.py`
2. Add entries to the `scripts_to_test` list:
   ```python
   scripts_to_test = [
       ("/app/source/loadstocksymbols_test.py", "loadstocksymbols_test.py"),
       ("/app/source/your_other_script.py", "your_other_script.py"),
       ("/app/source/third_script.py", "third_script.py"),
   ]
   ```

## How the Mock Works

Your existing scripts contain code like:
```python
client = boto3.client("secretsmanager")
secret = json.loads(client.get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"])
```

Our mock intercepts this and returns:
```json
{
  "host": "postgres",
  "port": "5432", 
  "username": "stocksuser",
  "password": "stockspass",
  "dbname": "stocksdb"
}
```

The scripts work exactly as before, but connect to the local test database instead of AWS RDS.

## Troubleshooting

- **PostgreSQL not ready**: The test runner waits up to 60 seconds for PostgreSQL to start
- **Docker issues**: Make sure Docker Desktop is running and you have sufficient resources
- **Permission issues**: On Windows, you may need to run PowerShell as Administrator
- **Port conflicts**: If port 5432 is in use, modify the port mapping in `docker-compose.yml`

## Logs Location

After running tests, check these locations for detailed logs:
- `logs/test_runner.log` - Overall test execution log
- `logs/loadstocksymbols_test.log` - Output from the symbols test script
- Console output - Real-time streaming of all script outputs
