@echo off
REM ════════════════════════════════════════════════════════════════════════════
REM TimescaleDB Local Setup Script (Windows)
REM
REM Run this to:
REM   1. Start PostgreSQL with TimescaleDB
REM   2. Initialize database schema
REM   3. Apply TimescaleDB migration
REM   4. Run performance benchmarks
REM
REM Usage: setup_timescaledb_local.bat
REM ════════════════════════════════════════════════════════════════════════════

setlocal enabledelayedexpansion

echo.
echo ════════════════════════════════════════════════════════════════
echo TimescaleDB Local Setup
echo ════════════════════════════════════════════════════════════════

REM Step 1: Stop existing containers
echo.
echo Step 1: Stopping existing containers...
docker-compose -f docker-compose.local.yml down 2>nul

REM Step 2: Start PostgreSQL with TimescaleDB
echo.
echo Step 2: Starting PostgreSQL 15 with TimescaleDB...
docker-compose -f docker-compose.local.yml up -d postgres

REM Step 3: Wait for database to be ready
echo.
echo Step 3: Waiting for database to start ^(30 seconds^)...
timeout /t 30 /nobreak

REM Step 4: Verify connection
echo.
echo Step 4: Verifying database connection...
docker exec stocks_postgres_local psql -U stocks -d stocks -c "SELECT version();" >nul 2>&1

if !errorlevel! neq 0 (
    echo X Failed to connect. Check container logs:
    echo   docker-compose -f docker-compose.local.yml logs postgres
    exit /b 1
)

echo OK Database is online

REM Step 5: Initialize schema (if needed)
echo.
echo Step 5: Ensuring schema is initialized...
python -c "import os; os.system('docker exec stocks_postgres_local psql -U stocks -d stocks -c \"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = \\'public\\';\" > nul 2>&1')"

python init_database.py 2>nul || echo Schema already initialized

REM Step 6: Apply TimescaleDB migration
echo.
echo Step 6: Applying TimescaleDB migration...
python migrate_timescaledb.py

REM Step 7: Run benchmarks
echo.
echo Step 7: Running performance benchmarks...
python test_timescaledb_performance.py

echo.
echo ════════════════════════════════════════════════════════════════
echo OK Setup complete!
echo ════════════════════════════════════════════════════════════════
echo.
echo Database is running at: localhost:5432
echo   User: stocks
echo   Password: ^(from .env.local^)
echo   Database: stocks
echo.
echo Next steps:
echo   1. Verify queries are fast: python test_timescaledb_performance.py
echo   2. Check hypertable stats: SELECT * FROM timescaledb_information.hypertables;
echo   3. Deploy to AWS RDS: terraform apply -target=aws_db_parameter_group.main
echo.
