#!/usr/bin/env pwsh

Write-Host "EOD Pipeline Test" -ForegroundColor Cyan

# Find the EOD pipeline state machine
Write-Host "Finding EOD pipeline state machine..." -ForegroundColor Yellow
$allSMs = aws stepfunctions list-state-machines --region us-east-1 | ConvertFrom-Json
$sm = $allSMs.stateMachines | Where-Object { $_.name -like "*EodBulk*" -or $_.name -like "*eod*" } | Select-Object -First 1

if (-not $sm) {
    Write-Host "No EOD pipeline state machine found" -ForegroundColor Red
    exit 1
}

$smArn = $sm.stateMachineArn
$smName = $sm.name

Write-Host "Found: $smName" -ForegroundColor Green
Write-Host "ARN: $smArn" -ForegroundColor Gray

# Prepare input payload
Write-Host ""
Write-Host "Preparing pipeline trigger..." -ForegroundColor Yellow

$inputObj = @{
    "loader_mode" = "FULL_DATASET"
    "timestamp" = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
}
$inputJson = $inputObj | ConvertTo-Json -Compress

Write-Host "Input: $inputJson" -ForegroundColor Gray

# Trigger execution
Write-Host ""
Write-Host "Triggering EOD pipeline..." -ForegroundColor Yellow

$execution = aws stepfunctions start-execution --state-machine-arn $smArn --name "test-$(Get-Date -Format 'HHmmss')" --input $inputJson --region us-east-1 | ConvertFrom-Json

$executionArn = $execution.executionArn
Write-Host "Execution started" -ForegroundColor Green
Write-Host "ARN: $executionArn" -ForegroundColor Gray

# Wait for completion
Write-Host ""
Write-Host "Monitoring execution..." -ForegroundColor Yellow

$maxWait = 14400
$elapsed = 0
$checkInterval = 30

while ($elapsed -lt $maxWait) {
    Start-Sleep -Seconds $checkInterval
    $elapsed += $checkInterval

    $status = aws stepfunctions describe-execution --execution-arn $executionArn --region us-east-1 | ConvertFrom-Json

    $currentStatus = $status.status
    $elapsed_min = [math]::Round($elapsed / 60, 1)

    Write-Host "[$elapsed_min min] Status: $currentStatus" -ForegroundColor Cyan

    if ($currentStatus -eq "SUCCEEDED") {
        Write-Host ""
        Write-Host "Pipeline completed successfully!" -ForegroundColor Green
        break
    } elseif ($currentStatus -eq "FAILED") {
        Write-Host ""
        Write-Host "Pipeline failed!" -ForegroundColor Red
        if ($status.cause) {
            Write-Host "Cause: $($status.cause)" -ForegroundColor Gray
        }
        exit 1
    }
}

if ($elapsed -ge $maxWait) {
    Write-Host ""
    Write-Host "Pipeline still running after 4 hours" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Execution ARN: $executionArn" -ForegroundColor Gray
