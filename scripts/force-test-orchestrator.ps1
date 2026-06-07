# Force Orchestrator Test Execution (Override Weekend/Market Closed)
# Invokes the orchestrator Lambda with force_execution=true to test live Alpaca connectivity

param(
    [switch]$Live,
    [string]$Region = "us-east-1"
)

# Prepare payload with force_execution to bypass weekend check
$payload = @{
    test = $true
    dry_run = -not $Live
    force_execution = $true  # Override weekend/market-closed checks
    source = "force-test"
    timestamp = (Get-Date -AsUTC).ToString("o")
} | ConvertTo-Json

Write-Host "Invoking algo-algo-dev Lambda..."
Write-Host "Payload: $payload"

if ($Live) {
    $confirm = Read-Host "⚠️  WARNING: This will open REAL positions. Continue? (y/N)"
    if ($confirm -ne "y") {
        Write-Host "Aborted"
        exit 1
    }
}

# Invoke Lambda
$response = aws lambda invoke `
    --function-name algo-algo-dev `
    --region $Region `
    --payload $payload `
    --cli-binary-format raw-in-base64-out `
    response.json 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✓ Lambda invoked successfully"

    # Parse response
    $content = Get-Content response.json | ConvertFrom-Json
    Write-Host "`nResponse:"
    Write-Host ($content | ConvertTo-Json -Depth 5)

    # Extract execution status
    $body = $content.body | ConvertFrom-Json
    Write-Host "`n================================================================================`nEXECUTION RESULT`n================================================================================"

    if ($body.status -eq "success") {
        Write-Host "✓ ORCHESTRATOR EXECUTED SUCCESSFULLY"

        # Show phases
        $body.phases | GetEnumerator | foreach {
            $phase = $_.Value
            if ($phase.status -eq "success") {
                Write-Host "  ✓ Phase $($_.Key): $($phase.summary)"
            } else {
                Write-Host "  → Phase $($_.Key): $($phase.status) - $($phase.summary)"
            }
        }

        # Show positions
        $openPositions = $body.open_positions
        Write-Host "`nOpen Positions: $openPositions"

        if ($openPositions -gt 0) {
            Write-Host "✓✓✓ LIVE ALPACA TRADING VERIFIED ✓✓✓"
            Write-Host "Positions opened in paper account!"
        }
    } else {
        Write-Host "✗ Orchestrator failed: $($body.message)"
    }

    rm response.json
} else {
    Write-Host "✗ Lambda invocation failed"
    $response
}
