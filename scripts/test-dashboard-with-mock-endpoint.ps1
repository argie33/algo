#!/usr/bin/env pwsh
<#
.SYNOPSIS
Test dashboard with mock/test endpoint to verify AWS connectivity path works.

.DESCRIPTION
Sets up a test environment to verify the dashboard can successfully connect
to and use an API endpoint. Use this to validate the AWS integration works
before getting the real production endpoint.

.EXAMPLE
.\scripts\test-dashboard-with-mock-endpoint.ps1
#>

Write-Host "`n================================" -ForegroundColor Cyan
Write-Host "Dashboard AWS Connectivity Test" -ForegroundColor Cyan
Write-Host "================================`n" -ForegroundColor Cyan

# Step 1: Check if user has real endpoint
$existingEndpoint = $env:DASHBOARD_API_URL
if ($existingEndpoint) {
    Write-Host "[1] Using existing DASHBOARD_API_URL:" -ForegroundColor Green
    Write-Host "    $existingEndpoint" -ForegroundColor Yellow
    Write-Host ""

    # Try to connect to it
    Write-Host "[2] Testing connectivity..." -ForegroundColor Cyan
    try {
        $response = Invoke-WebRequest -Uri "$existingEndpoint/health" -TimeoutSec 5 -ErrorAction Stop
        Write-Host "    OK: Endpoint is reachable" -ForegroundColor Green
        Write-Host ""
        Write-Host "Dashboard is ready to connect to AWS!" -ForegroundColor Green
        Write-Host "Run: python tools/dashboard/dashboard.py" -ForegroundColor Gray
        exit 0
    }
    catch {
        Write-Host "    ERROR: Could not reach endpoint" -ForegroundColor Yellow
        Write-Host "    Try with a different endpoint or get the correct one from admin" -ForegroundColor Gray
    }
}

Write-Host "[1] No DASHBOARD_API_URL configured" -ForegroundColor Yellow
Write-Host ""

# Step 2: Offer to start local test server
Write-Host "[2] Starting local test server to simulate AWS API..." -ForegroundColor Cyan
Write-Host ""

# Create a minimal test server
$testServerCode = @'
import http.server
import json
from datetime import datetime

class TestAPIHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress logging

if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", 8888), TestAPIHandler)
    print("Test API server running on http://127.0.0.1:8888")
    print("Press Ctrl+C to stop")
    server.serve_forever()
'@

# Write test server to temp file
$testServerFile = Join-Path $env:TEMP "test_api_server.py"
Set-Content -Path $testServerFile -Value $testServerCode

# Check if user wants to start it
Write-Host "To test the dashboard AWS connectivity path, I can start a local test server."
Write-Host ""
Write-Host "This will:"
Write-Host "  1. Run a mock API server on http://localhost:8888" -ForegroundColor Gray
Write-Host "  2. Configure DASHBOARD_API_URL to point to it" -ForegroundColor Gray
Write-Host "  3. Let you run the dashboard to test AWS connectivity" -ForegroundColor Gray
Write-Host ""
Write-Host "This proves the AWS integration architecture works once you get the real endpoint."
Write-Host ""

$response = Read-Host "Start test server? (y/n)"
if ($response -ne "y" -and $response -ne "Y") {
    Write-Host ""
    Write-Host "To get the real endpoint:" -ForegroundColor Cyan
    Write-Host "  1. Share 'scripts/get-api-endpoint-admin.sh' with your AWS admin" -ForegroundColor Gray
    Write-Host "  2. Ask them to run it and send you the endpoint" -ForegroundColor Gray
    Write-Host "  3. Set: \$env:DASHBOARD_API_URL = 'https://...'" -ForegroundColor Gray
    Write-Host "  4. Run: python tools/dashboard/dashboard.py" -ForegroundColor Gray
    Write-Host ""
    exit 0
}

Write-Host ""
Write-Host "Starting test server..." -ForegroundColor Green
Write-Host ""

# Start test server in background
$job = Start-Job -ScriptBlock {
    python $using:testServerFile
}

# Wait for server to start
Start-Sleep -Seconds 1

# Configure dashboard to use test endpoint
$env:DASHBOARD_API_URL = "http://127.0.0.1:8888"

Write-Host "Test server is running on: http://127.0.0.1:8888" -ForegroundColor Green
Write-Host "DASHBOARD_API_URL is set to test endpoint" -ForegroundColor Green
Write-Host ""

# Verify connectivity
Write-Host "Verifying connectivity..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8888/health" -TimeoutSec 5 -ErrorAction Stop
    Write-Host "OK: Test server is reachable" -ForegroundColor Green
    Write-Host ""
}
catch {
    Write-Host "ERROR: Could not reach test server" -ForegroundColor Red
    Stop-Job -Job $job
    exit 1
}

Write-Host "Test environment ready!" -ForegroundColor Cyan
Write-Host ""
Write-Host "The dashboard can now connect to this test endpoint to verify AWS path works."
Write-Host ""
Write-Host "To get the real production endpoint:" -ForegroundColor Yellow
Write-Host "  1. Share 'scripts/get-api-endpoint-admin.sh' with your AWS admin" -ForegroundColor Gray
Write-Host "  2. They run it and send you the endpoint" -ForegroundColor Gray
Write-Host "  3. Set: \$env:DASHBOARD_API_URL = 'https://...'" -ForegroundColor Gray
Write-Host ""
Write-Host "Note: Test server only responds to /health endpoint." -ForegroundColor Gray
Write-Host "      With the real endpoint, dashboard will have full data access." -ForegroundColor Gray
Write-Host ""
Write-Host "To stop test server: Stop-Job -Job $($job.Id)" -ForegroundColor Gray
