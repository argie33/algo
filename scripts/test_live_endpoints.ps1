#!/usr/bin/env pwsh
<#
.SYNOPSIS
Test deployed Lambda endpoints through API Gateway

.PARAMETER ApiEndpoint
The API Gateway endpoint URL (e.g., https://abc123.execute-api.us-east-1.amazonaws.com)

.EXAMPLE
./scripts/test_live_endpoints.ps1 -ApiEndpoint "https://abc123.execute-api.us-east-1.amazonaws.com"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$ApiEndpoint,
    [string]$AuthToken = $null
)

$ErrorActionPreference = "Continue"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Testing Live Endpoints" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Normalize endpoint URL
$ApiEndpoint = $ApiEndpoint.TrimEnd('/')
Write-Host "Testing endpoint: $ApiEndpoint" -ForegroundColor Yellow
Write-Host ""

$Endpoints = @(
    @{
        path = "/api/algo/positions"
        name = "Positions"
        description = "Current open positions"
    }
    @{
        path = "/api/algo/performance"
        name = "Performance"
        description = "Trading performance metrics"
    }
    @{
        path = "/api/algo/swing-scores"
        name = "Swing Scores"
        description = "Entry signal scores"
    }
)

$Results = @()

foreach ($endpoint in $Endpoints) {
    Write-Host "Testing: $($endpoint.name)" -ForegroundColor Yellow
    Write-Host "  Path: $($endpoint.path)" -ForegroundColor Gray
    Write-Host "  Description: $($endpoint.description)" -ForegroundColor Gray

    $Url = "$ApiEndpoint$($endpoint.path)"
    $Headers = @{"Accept" = "application/json"}

    if ($AuthToken) {
        $Headers["Authorization"] = "Bearer $AuthToken"
    }

    try {
        $StartTime = Get-Date
        $Response = Invoke-WebRequest -Uri $Url `
            -Method GET `
            -TimeoutSec 15 `
            -SkipHttpErrorCheck `
            -Headers $Headers

        $Duration = (Get-Date) - $StartTime
        $StatusCode = $Response.StatusCode
        $ContentLength = $Response.Content.Length

        if ($StatusCode -eq 200) {
            Write-Host "  ✓ Status: 200 OK" -ForegroundColor Green
            Write-Host "  ✓ Response time: $([math]::Round($Duration.TotalMilliseconds))ms" -ForegroundColor Green
            Write-Host "  ✓ Content length: $([math]::Round($ContentLength / 1KB, 2)) KB" -ForegroundColor Green

            # Parse JSON response if possible
            try {
                $Content = $Response.Content | ConvertFrom-Json
                if ($Content) {
                    Write-Host "  ✓ Valid JSON response" -ForegroundColor Green
                    # Check for error markers
                    if ($Content.PSObject.Properties -match "_error|error|Error") {
                        Write-Host "  ⚠ Response contains error field" -ForegroundColor Yellow
                    }
                }
            } catch {
                Write-Host "  ⚠ Response is not valid JSON" -ForegroundColor Yellow
            }

            $Results += @{
                endpoint = $endpoint.name
                status = "PASS"
                code = $StatusCode
                duration = $Duration.TotalMilliseconds
            }
        } else {
            Write-Host "  ✗ Status: $StatusCode" -ForegroundColor Red
            Write-Host "  ✗ Response time: $([math]::Round($Duration.TotalMilliseconds))ms" -ForegroundColor Red

            $Results += @{
                endpoint = $endpoint.name
                status = "FAIL"
                code = $StatusCode
                duration = $Duration.TotalMilliseconds
            }
        }
    } catch {
        Write-Host "  ✗ Error: $_" -ForegroundColor Red
        $Results += @{
            endpoint = $endpoint.name
            status = "ERROR"
            code = $null
            duration = $null
        }
    }

    Write-Host ""
    Start-Sleep -Milliseconds 500
}

# Summary
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Test Results Summary" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$PassCount = ($Results | Where-Object { $_.status -eq "PASS" }).Count
$TotalCount = $Results.Count
$PassPercentage = [math]::Round(($PassCount / $TotalCount) * 100)

foreach ($result in $Results) {
    $symbol = if ($result.status -eq "PASS") { "✓" } else { "✗" }
    $color = if ($result.status -eq "PASS") { "Green" } else { "Red" }
    $details = if ($result.duration) { "($($result.code), $([math]::Round($result.duration))ms)" } else { "($($result.status))" }
    Write-Host "$symbol $($result.endpoint): $($result.status) $details" -ForegroundColor $color
}

Write-Host ""
Write-Host "Overall: $PassCount/$TotalCount passed ($PassPercentage%)" -ForegroundColor $(if ($PassCount -eq $TotalCount) { "Green" } else { "Red" })
Write-Host ""

if ($PassCount -eq $TotalCount) {
    Write-Host "✓ All endpoints working!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. Open the dashboard in your browser" -ForegroundColor Yellow
    Write-Host "2. Verify all panels display correctly" -ForegroundColor Yellow
    Write-Host "3. Check CloudWatch logs for any issues:" -ForegroundColor Yellow
    Write-Host "   aws logs tail /aws/lambda/algo-api --follow" -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "✗ Some endpoints failed" -ForegroundColor Red
    Write-Host ""
    Write-Host "Debugging steps:" -ForegroundColor Yellow
    Write-Host "1. Check CloudWatch logs:" -ForegroundColor Yellow
    Write-Host "   aws logs tail /aws/lambda/algo-api --follow" -ForegroundColor Yellow
    Write-Host "2. Verify environment variables in Lambda console" -ForegroundColor Yellow
    Write-Host "3. Check database connectivity from Lambda VPC" -ForegroundColor Yellow
    exit 1
}
