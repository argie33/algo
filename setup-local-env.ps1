# Local environment setup script for PostgreSQL credentials
# Run this before running loaders, orchestrator, or tests
# See LOCAL_CRED_SETUP.md for details

$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_NAME = "stocks"

# Set DB_PASSWORD from environment or prompt
if (-not $env:DB_PASSWORD) {
    Write-Host "ERROR: DB_PASSWORD environment variable not set"
    Write-Host "Please set it before running this script"
    exit 1
}

# Optional: Test credentials
Write-Host "Testing database connection..."
python -c "from utils.db_connection import get_db_connection; conn = get_db_connection(); print('OK - Connected'); conn.close()" 2>&1

Write-Host ""
Write-Host "Environment variables set:"
Write-Host "  DB_HOST = $env:DB_HOST"
Write-Host "  DB_PORT = $env:DB_PORT"
Write-Host "  DB_USER = $env:DB_USER"
Write-Host "  DB_NAME = $env:DB_NAME"
Write-Host ""
Write-Host "Ready to run:"
Write-Host "  python run-all-loaders.py"
Write-Host "  python algo/algo_orchestrator.py --mode paper --dry-run"
Write-Host "  python -m pytest tests/ -q"
