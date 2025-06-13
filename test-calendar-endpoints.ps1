#!/usr/bin/env powershell
# Test script to verify calendar endpoints work

# Replace with your actual API Gateway URL
$API_BASE_URL = "https://your-api-gateway-url.execute-api.us-east-1.amazonaws.com"

Write-Host "Testing Calendar Endpoints..." -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green

# Test 1: Health check
Write-Host "`n1. Testing health endpoint..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$API_BASE_URL/health" -Method GET
    Write-Host "Health check: SUCCESS" -ForegroundColor Green
    Write-Host $response | ConvertTo-Json -Depth 3
} catch {
    Write-Host "Health check: FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message
}

# Test 2: Calendar debug
Write-Host "`n2. Testing calendar debug endpoint..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$API_BASE_URL/calendar/debug" -Method GET
    Write-Host "Calendar debug: SUCCESS" -ForegroundColor Green
    Write-Host $response | ConvertTo-Json -Depth 3
} catch {
    Write-Host "Calendar debug: FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message
}

# Test 3: Calendar test
Write-Host "`n3. Testing calendar test endpoint..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$API_BASE_URL/calendar/test" -Method GET
    Write-Host "Calendar test: SUCCESS" -ForegroundColor Green
    Write-Host $response | ConvertTo-Json -Depth 3
} catch {
    Write-Host "Calendar test: FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message
}

# Test 4: Calendar events
Write-Host "`n4. Testing calendar events endpoint..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$API_BASE_URL/calendar/events" -Method GET
    Write-Host "Calendar events: SUCCESS" -ForegroundColor Green
    Write-Host $response | ConvertTo-Json -Depth 3
} catch {
    Write-Host "Calendar events: FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message
}

Write-Host "`n================================" -ForegroundColor Green
Write-Host "Calendar endpoint testing complete." -ForegroundColor Green
