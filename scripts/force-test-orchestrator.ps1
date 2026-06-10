# Force Orchestrator Test Execution (Override Weekend/Market Closed)
# Invokes the orchestrator Lambda with force_execution=true to test live Alpaca connectivity

param(
    [switch]$Live,
    [string]$Region = "us-east-1"
)

# Prepare payload with force_execution to bypass weekend check
$utcNow = [System.DateTime]::UtcNow.ToString("o")
$payload = @{
    test = $true
    dry_run = -not $Live
    force_execution = $true  # Override weekend/market-closed checks
    source = "force-test"
    timestamp = $utcNow
} | ConvertTo-Json

Write-Host "Invoking algo-algo-dev Lambda..."
Write-Host "Payload: $payload"

# Set AWS profile for credentials
$env:AWS_PROFILE = "algo-developer"

if ($Live) {
    $confirm = Read-Host "WARNING: This will open REAL positions. Continue? (y/N)"
    if ($confirm -ne "y") {
        Write-Host "Aborted"
        exit 1
    }
}

# Invoke Lambda - write payload to temp file to avoid escaping issues
$tempPayloadFile = "$env:TEMP\lambda_payload_$(Get-Random).json"
$payload | Set-Content -Path $tempPayloadFile -Encoding UTF8

Write-Host "Calling AWS Lambda with payload from: $tempPayloadFile"

$invokeCmd = "aws lambda invoke --function-name algo-algo-dev --region $Region --payload file://$tempPayloadFile response.json"
Write-Host "Command: $invokeCmd"
Invoke-Expression $invokeCmd 2>&1

$response = $LASTEXITCODE

Remove-Item $tempPayloadFile -ErrorAction SilentlyContinue

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[SUCCESS] Lambda invoked successfully"

    # Parse response
    $content = Get-Content response.json | ConvertFrom-Json
    Write-Host "`nResponse:"
    Write-Host ($content | ConvertTo-Json -Depth 5)

    # Extract execution status
    $body = $content.body | ConvertFrom-Json
    Write-Host "`n================================================================================"
    Write-Host "EXECUTION RESULT"
    Write-Host "================================================================================"

    if ($body.status -eq "success") {
        Write-Host "[OK] ORCHESTRATOR EXECUTED SUCCESSFULLY"

        # Show phases
        if ($body.phases) {
            foreach ($phaseKey in $body.phases.PSObject.Properties.Name) {
                $phase = $body.phases.$phaseKey
                if ($phase.status -eq "success") {
                    Write-Host "  [OK] Phase $phaseKey`: $($phase.summary)"
                } else {
                    Write-Host "  [*] Phase $phaseKey`: $($phase.status) - $($phase.summary)"
                }
            }
        }

        # Show positions
        $openPositions = $body.open_positions
        Write-Host "`nOpen Positions: $openPositions"

        if ($openPositions -gt 0) {
            Write-Host "[SUCCESS] LIVE ALPACA TRADING VERIFIED"
            Write-Host "Positions opened in paper account!"
        }
    } else {
        Write-Host "[ERROR] Orchestrator failed: $($body.message)"
    }

    rm response.json
} else {
    Write-Host "[ERROR] Lambda invocation failed"
    $response
}
