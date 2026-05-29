param([switch]$Verbose)
Write-Host "Verifying both environments..." -ForegroundColor Cyan
$local = @{ name = 'Local'; url = 'http://localhost:3001/api/health' }
$prod = @{ name = 'Production'; url = 'https://d2u93283nn45h2.cloudfront.net/api/health' }
foreach ($env in @($local, $prod)) {
  try {
    $r = Invoke-WebRequest -Uri $env.url -TimeoutSec 10 -ErrorAction Stop
    Write-Host "[PASS] $($env.name)" -ForegroundColor Green
  } catch {
    Write-Host "[FAIL] $($env.name): Connection failed" -ForegroundColor Red
  }
}
