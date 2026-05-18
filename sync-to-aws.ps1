# Sync local database to AWS RDS
# Prerequisites: PostgreSQL client tools (psql, pg_dump)

param(
    [string]$LocalDB = "stocks",
    [string]$LocalUser = "stocks",
    [string]$LocalHost = "localhost",
    [string]$LocalPort = "5432",
    [string]$AWSRDS = "",  # Set via command line or env
    [string]$AWSUser = "stocks",
    [string]$BackupFile = "stocks_backup.sql"
)

Write-Host "=== Database Sync: Local → AWS RDS ===" -ForegroundColor Cyan

# Step 1: Get AWS RDS endpoint from Terraform
if (-not $AWSRDS) {
    Write-Host "Fetching RDS endpoint from Terraform..." -ForegroundColor Yellow
    $output = terraform -chdir="terraform" output -json | ConvertFrom-Json
    if ($output.rds_address) {
        $AWSRDS = "$($output.rds_address.value):$($output.rds_port.value)"
        Write-Host "  RDS Endpoint: $AWSRDS" -ForegroundColor Green
    } else {
        Write-Host "ERROR: Could not find RDS endpoint. Check Terraform state." -ForegroundColor Red
        exit 1
    }
}

# Step 2: Backup local database
Write-Host "`nStep 1: Backing up local database..." -ForegroundColor Yellow
$env:PGPASSWORD = $env:DB_PASSWORD
pg_dump -h $LocalHost -p $LocalPort -U $LocalUser -d $LocalDB > $BackupFile
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Backup failed" -ForegroundColor Red
    exit 1
}
Write-Host "  Backup created: $BackupFile" -ForegroundColor Green

# Step 3: Count records in local database
Write-Host "`nStep 2: Counting local records..." -ForegroundColor Yellow
$localQuery = @"
SELECT
    schemaname,
    COUNT(*) as tables,
    SUM(n_live_tup) as total_rows
FROM pg_stat_user_tables
GROUP BY schemaname
ORDER BY schemaname;
"@
psql -h $LocalHost -p $LocalPort -U $LocalUser -d $LocalDB -c $localQuery

# Step 4: Restore to AWS RDS (requires AWS credentials)
Write-Host "`nStep 3: Restoring to AWS RDS..." -ForegroundColor Yellow
Write-Host "  Target: $AWSRDS" -ForegroundColor Cyan
Write-Host "  Run: psql -h $($AWSRDS.Split(':')[0]) -U $AWSUser -d $LocalDB < $BackupFile" -ForegroundColor Yellow
Write-Host "  (Requires AWS RDS password)" -ForegroundColor Gray

# Step 5: Verify sync
Write-Host "`nStep 4: Verification (manual)" -ForegroundColor Yellow
Write-Host "  Connect to AWS RDS and run:" -ForegroundColor Gray
Write-Host "    psql -h $($AWSRDS.Split(':')[0]) -U $AWSUser -d $LocalDB" -ForegroundColor Gray
Write-Host "    \d  -- List tables" -ForegroundColor Gray
Write-Host "    SELECT COUNT(*) FROM price_daily;  -- Check data" -ForegroundColor Gray

Write-Host "`n=== Sync preparation complete ===" -ForegroundColor Green
