# Test API endpoint fixes and data quality
$baseUrl = "http://localhost:3001"

Write-Host "=== API ENDPOINT TESTING ===" -ForegroundColor Cyan
Write-Host ""

# Test 1: Scores endpoint response shape
Write-Host "Test 1: Scores endpoint returns { items: [] }" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$baseUrl/api/scores/stockscores?limit=10" -Method GET -Headers @{"Content-Type"="application/json"} -ErrorAction Stop
    $data = $response.Content | ConvertFrom-Json
    
    if ($data.items) {
        Write-Host "  PASS: Response has 'items' key" -ForegroundColor Green
        Write-Host "  Items count: $($data.items.Count)"
        if ($data.items[0].symbol) {
            Write-Host "  First item symbol: $($data.items[0].symbol)" -ForegroundColor Green
        }
    } else {
        Write-Host "  FAIL: Response missing 'items' key" -ForegroundColor Red
        Write-Host "  Keys: $($data | Get-Member -MemberType NoteProperty | Select-Object -ExpandProperty Name)"
    }
} catch {
    Write-Host "  ERROR: Could not connect to API" -ForegroundColor Red
    Write-Host "  Make sure the Express server is running: npm start" -ForegroundColor Yellow
}

Write-Host ""

# Test 2: Signals /stocks endpoint returns { items: [] }
Write-Host "Test 2: Signals /stocks endpoint returns { items: [] }" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$baseUrl/api/signals/stocks?timeframe=daily&limit=5" -Method GET -Headers @{"Content-Type"="application/json"} -ErrorAction Stop
    $data = $response.Content | ConvertFrom-Json
    
    if ($data.items) {
        Write-Host "  PASS: Response has 'items' key" -ForegroundColor Green
        Write-Host "  Items count: $($data.items.Count)"
        if ($data.items[0]) {
            Write-Host "  First signal symbol: $($data.items[0].symbol)" -ForegroundColor Green
            Write-Host "  Has RSI: $($null -ne $data.items[0].rsi)" -ForegroundColor Green
            Write-Host "  Has ATR: $($null -ne $data.items[0].atr)" -ForegroundColor Green
            Write-Host "  Has ADX: $($null -ne $data.items[0].adx)" -ForegroundColor Green
        }
    } else {
        Write-Host "  FAIL: Response missing 'items' key" -ForegroundColor Red
    }
} catch {
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Test 3: Signals /etf endpoint returns { items: [] }
Write-Host "Test 3: Signals /etf endpoint returns { items: [] }" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$baseUrl/api/signals/etf?timeframe=daily&limit=5" -Method GET -Headers @{"Content-Type"="application/json"} -ErrorAction Stop
    $data = $response.Content | ConvertFrom-Json
    
    if ($data.items) {
        Write-Host "  PASS: Response has 'items' key" -ForegroundColor Green
        Write-Host "  Items count: $($data.items.Count)"
    } else {
        Write-Host "  FAIL: Response missing 'items' key" -ForegroundColor Red
    }
} catch {
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Test 4: Signals main endpoint 
Write-Host "Test 4: Signals main endpoint returns { signals: [] }" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$baseUrl/api/signals?timeframe=daily&limit=5" -Method GET -Headers @{"Content-Type"="application/json"} -ErrorAction Stop
    $data = $response.Content | ConvertFrom-Json
    
    if ($data.signals) {
        Write-Host "  PASS: Response has 'signals' key" -ForegroundColor Green
        Write-Host "  Signals count: $($data.signals.Count)"
    } else {
        Write-Host "  WARNING: Response missing 'signals' key (this endpoint may return items)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== TEST COMPLETE ===" -ForegroundColor Cyan
