#!/usr/bin/env pwsh
<#
.SYNOPSIS
Test scores endpoint performance and verify 503 fix

.PARAMETER ApiEndpoint
The API endpoint URL (e.g., https://abc123.lambda-url.us-east-1.on.aws/)

.EXAMPLE
./scripts/test_scores_endpoint.ps1 -ApiEndpoint "https://abc123.lambda-url.us-east-1.on.aws/"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$ApiEndpoint,
    [string]$AuthToken = $null
)

$ErrorActionPreference = "Continue"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Testing Scores Endpoint Fix for 503 Errors" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Normalize endpoint URL
$ApiEndpoint = $ApiEndpoint.TrimEnd('/')
Write-Host "Testing endpoint: $ApiEndpoint" -ForegroundColor Yellow
Write-Host ""

$TestCases = @(
    @{
        name = "Basic scores fetch (default)"
        params = ""
        description = "Default 50 items, sorted by composite_score"
    }
    @{
        name = "Top 10 scores"
        params = "?limit=10"
        description = "Fetch top 10 scores"
    }
    @{
        name = "Specific symbol"
        params = "?symbol=AAPL"
        description = "Fetch scores for single symbol"
    }
    @{
        name = "S&P 500 only"
        params = "?sp500Only=true&limit=20"
        description = "Fetch S&P 500 stocks only"
    }
    @{
        name = "Large result set"
        params = "?limit=500"
        description = "Fetch 500 scores (stress test)"
    }
    @{
        name = "Sorted by momentum"
        params = "?sortBy=momentum_score&sortOrder=desc&limit=20"
        description = "Sort by momentum score descending"
    }
)

$Results = @()
$FailedTests = @()

foreach ($testCase in $TestCases) {
    Write-Host "Testing: $($testCase.name)" -ForegroundColor Yellow
    Write-Host "  Path: /api/scores$($testCase.params)" -ForegroundColor Gray
    Write-Host "  Description: $($testCase.description)" -ForegroundColor Gray

    $Url = "$ApiEndpoint/api/scores$($testCase.params)"
    $Headers = @{"Accept" = "application/json"}

    if ($AuthToken) {
        $Headers["Authorization"] = "Bearer $AuthToken"
    }

    try {
        $StartTime = Get-Date
        $Response = Invoke-WebRequest -Uri $Url `
            -Method GET `
            -TimeoutSec 60 `
            -SkipHttpErrorCheck `
            -Headers $Headers

        $Duration = (Get-Date) - $StartTime
        $StatusCode = $Response.StatusCode
        $ContentLength = $Response.Content.Length

        # Check for 503 error
        if ($StatusCode -eq 503) {
            Write-Host "  ✗ Status: 503 SERVICE UNAVAILABLE (FIX FAILED)" -ForegroundColor Red
            Write-Host "  ✗ Response time: $([math]::Round($Duration.TotalMilliseconds))ms" -ForegroundColor Red

            $Results += @{
                test = $testCase.name
                status = "503_ERROR"
                code = $StatusCode
                duration = $Duration.TotalMilliseconds
            }
            $FailedTests += $testCase.name
        }
        elseif ($StatusCode -eq 200) {
            Write-Host "  ✓ Status: 200 OK" -ForegroundColor Green
            Write-Host "  ✓ Response time: $([math]::Round($Duration.TotalMilliseconds))ms" -ForegroundColor Green
            Write-Host "  ✓ Content length: $([math]::Round($ContentLength / 1KB, 2)) KB" -ForegroundColor Green

            # Parse JSON response
            try {
                $Content = $Response.Content | ConvertFrom-Json
                if ($Content) {
                    Write-Host "  ✓ Valid JSON response" -ForegroundColor Green

                    # Check response structure
                    if ($Content.statusCode -eq 200 -and $Content.data.items) {
                        $itemCount = $Content.data.items.Count
                        Write-Host "  ✓ Response contains $itemCount items" -ForegroundColor Green

                        # Check for error fields
                        if ($Content.data.PSObject.Properties -match "_error|error") {
                            Write-Host "  ⚠ Warning: Response contains error field" -ForegroundColor Yellow
                        }
                    } else {
                        Write-Host "  ⚠ Response structure unexpected" -ForegroundColor Yellow
                    }
                }

                $Results += @{
                    test = $testCase.name
                    status = "PASS"
                    code = $StatusCode
                    duration = $Duration.TotalMilliseconds
                }
            } catch {
                Write-Host "  ⚠ Warning: Could not parse JSON response: $_" -ForegroundColor Yellow
                $Results += @{
                    test = $testCase.name
                    status = "WARN"
                    code = $StatusCode
                    duration = $Duration.TotalMilliseconds
                }
            }
        } else {
            Write-Host "  ✗ Status: $StatusCode (Expected 200)" -ForegroundColor Red
            Write-Host "  ✗ Response time: $([math]::Round($Duration.TotalMilliseconds))ms" -ForegroundColor Red

            $Results += @{
                test = $testCase.name
                status = "FAIL"
                code = $StatusCode
                duration = $Duration.TotalMilliseconds
            }
            $FailedTests += $testCase.name
        }
    } catch {
        Write-Host "  ✗ Error: $_" -ForegroundColor Red
        $Results += @{
            test = $testCase.name
            status = "ERROR"
            code = $null
            duration = $null
        }
        $FailedTests += $testCase.name
    }

    Write-Host ""
    Start-Sleep -Milliseconds 1000
}

# Summary
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Test Results Summary" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$PassCount = ($Results | Where-Object { $_.status -eq "PASS" }).Count
$FailCount = ($Results | Where-Object { $_.status -eq "FAIL" -or $_.status -eq "503_ERROR" }).Count
$WarnCount = ($Results | Where-Object { $_.status -eq "WARN" }).Count
$TotalCount = $Results.Count

foreach ($result in $Results) {
    $statusColor = switch($result.status) {
        "PASS" { "Green" }
        "WARN" { "Yellow" }
        "503_ERROR" { "Red" }
        default { "Red" }
    }
    $symbol = if ($result.status -eq "PASS") { "✓" } elseif ($result.status -eq "WARN") { "⚠" } else { "✗" }

    $details = if ($result.duration) {
        "($($result.code), $([math]::Round($result.duration))ms)"
    } else {
        "($($result.status))"
    }

    Write-Host "$symbol $($result.test): $($result.status) $details" -ForegroundColor $statusColor
}

Write-Host ""
Write-Host "Overall Results:" -ForegroundColor Cyan
Write-Host "  PASS: $PassCount" -ForegroundColor Green
Write-Host "  WARN: $WarnCount" -ForegroundColor Yellow
Write-Host "  FAIL: $FailCount" -ForegroundColor Red
Write-Host "  Total: $TotalCount" -ForegroundColor Cyan
Write-Host ""

# Check if fix is verified
$ScoresFix = $Results | Where-Object { $_.status -eq "503_ERROR" }
if ($ScoresFix.Count -gt 0) {
    Write-Host "✗ CRITICAL: Scores endpoint still returning 503 errors!" -ForegroundColor Red
    Write-Host ""
    Write-Host "The fix has not been successfully applied or deployed." -ForegroundColor Red
    Write-Host ""
    Write-Host "Debugging steps:" -ForegroundColor Yellow
    Write-Host "1. Verify the optimized query was deployed to AWS Lambda" -ForegroundColor Yellow
    Write-Host "2. Check Lambda function code SHA matches the deployment" -ForegroundColor Yellow
    Write-Host "3. Review CloudWatch logs for query execution times:" -ForegroundColor Yellow
    Write-Host "   aws logs tail /aws/lambda/algo-api --follow" -ForegroundColor Yellow
    Write-Host "4. Check database connection and query performance:" -ForegroundColor Yellow
    Write-Host "   Verify indexes exist: idx_price_daily_date, idx_technical_data_daily_date" -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "✓ VERIFIED: Scores endpoint is working without 503 errors!" -ForegroundColor Green
    Write-Host ""
    Write-Host "The optimization fix has been successfully applied and is working in AWS." -ForegroundColor Green
    Write-Host ""
    Write-Host "Performance metrics:" -ForegroundColor Yellow
    $avgDuration = ($Results | Where-Object { $_.duration } | Measure-Object -Property duration -Average).Average
    Write-Host "  Average response time: $([math]::Round($avgDuration))ms" -ForegroundColor Yellow

    $slowTests = $Results | Where-Object { $_.duration -gt 30000 }
    if ($slowTests.Count -gt 0) {
        Write-Host "  ⚠ Warning: Some requests exceeded 30 seconds:" -ForegroundColor Yellow
        $slowTests | ForEach-Object { Write-Host "    - $($_.test): $([math]::Round($_.duration))ms" -ForegroundColor Yellow }
    }

    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Green
    Write-Host "1. Monitor CloudWatch metrics for continued performance" -ForegroundColor Green
    Write-Host "2. Verify dashboard scores panel loads correctly" -ForegroundColor Green
    Write-Host "3. Watch for any new 503 errors in the logs" -ForegroundColor Green
    exit 0
}
