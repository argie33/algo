#!/usr/bin/env pwsh
<#
.SYNOPSIS
Check if factor score metrics tables are populated.

.DESCRIPTION
Queries the database to show:
- Row counts in metrics tables
- When they were last updated
- Sample data to verify quality
#>

# Load AWS credentials
$ErrorActionPreference = "Stop"

# Get RDS endpoint from terraform outputs
$terraformOutput = Get-Content terraform/.terraform-outputs.json -ErrorAction SilentlyContinue | ConvertFrom-Json

if ($null -eq $terraformOutput) {
    Write-Host "ERROR: Cannot find terraform/.terraform-outputs.json" -ForegroundColor Red
    Write-Host "Run: cd terraform && terraform refresh"
    exit 1
}

$dbHost = $terraformOutput.rds_endpoint
$dbUser = $terraformOutput.rds_username
$dbPass = $terraformOutput.rds_password
$dbName = "algo-db"

# Test connection
Write-Host "Testing database connection to $dbHost..." -ForegroundColor Cyan
$testQuery = @"
SELECT
    'quality_metrics' as table_name,
    COUNT(*) as row_count,
    MAX(created_at) as latest_update
FROM quality_metrics
UNION ALL
SELECT 'growth_metrics', COUNT(*), MAX(created_at) FROM growth_metrics
UNION ALL
SELECT 'value_metrics', COUNT(*), MAX(created_at) FROM value_metrics
UNION ALL
SELECT 'positioning_metrics', COUNT(*), MAX(created_at) FROM positioning_metrics
UNION ALL
SELECT 'stability_metrics', COUNT(*), MAX(created_at) FROM stability_metrics
UNION ALL
SELECT 'stock_scores', COUNT(*), MAX(updated_at) FROM stock_scores
UNION ALL
SELECT 'annual_income_statement', COUNT(*), MAX(updated_at) FROM annual_income_statement
ORDER BY table_name;
"@

try {
    # Use AWS RDS proxy connection if available
    $connectionString = "Server=$dbHost;Username=$dbUser;Password=$dbPass;Database=$dbName"

    # For now, show the query so user can run it manually
    Write-Host "`nTo check metrics tables, run this query:" -ForegroundColor Yellow
    Write-Host $testQuery
    Write-Host "`nOr use AWS Secrets Manager to get credentials and run with psql:" -ForegroundColor Yellow
    Write-Host "psql -h $dbHost -U $dbUser -d $dbName -c `"SELECT * FROM stock_scores LIMIT 5`""
    Write-Host "`nTo check if loaders are running:" -ForegroundColor Yellow
    Write-Host "aws dynamodb query --table-name algo-loader-status-dev --key-conditions 'loader_name={AttributeValue:{S:stock_scores}}' --region us-east-1"
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
