# Trigger deploy-app-stocks workflow - fix ECS task None exit code v8
# Common requirements for stock loading tasks

## Core Dependencies - PROVEN WORKING
psycopg2-binary>=2.9.5  # Database connectivity - STANDARDIZED pattern working
yfinance>=0.2.28        # Market data API - Group 1 loaders successful
boto3>=1.26.0          # AWS services - Secrets Manager integration working
pandas>=1.5.0          # Data processing - All data transformations working
numpy>=1.24.0          # Numerical operations - Required for financial calculations
python-dateutil>=2.8.0 # Date handling - Calendar and timestamp processing

## Database Connection Pattern - WORKING
# IDENTICAL pattern applied to all loaders based on successful loadcalendar.py:
# - get_db_config() returns tuple (user, pwd, host, port, dbname)
# - Auto-negotiate SSL with cursor_factory=RealDictCursor
# - 3-retry logic with exponential backoff (5s, 10s, 20s)
# - Network connectivity pre-test for diagnostics

## Additional Requirements for Specific Loaders
requests>=2.28.0       # HTTP requests - AAII sentiment data download
xlrd==2.0.1           # Excel file reading - AAII sentiment .xls files
openpyxl==3.1.2       # Excel file processing - Alternative Excel support
fredapi>=0.5.0        # Federal Reserve economic data
pytz>=2022.0          # Timezone handling for market data