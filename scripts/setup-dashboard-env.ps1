# Setup dashboard environment variables from AWS Secrets Manager
# Windows PowerShell version

Write-Host "Loading dashboard credentials from AWS Secrets Manager..." -ForegroundColor Cyan
Write-Host ""

try {
    # Get secret
    $secret = aws secretsmanager get-secret-value `
        --secret-id algo/dashboard-config `
        --query 'SecretString' `
        --output text `
        --region us-east-1 2>$null

    if ([string]::IsNullOrEmpty($secret)) {
        Write-Host "ERROR: Could not retrieve secret from Secrets Manager" -ForegroundColor Red
        exit 1
    }

    # Parse JSON and extract values
    $json = $secret | ConvertFrom-Json

    $API_URL = $json.api_url
    $POOL_ID = $json.cognito_user_pool_id
    $CLIENT_ID = $json.cognito_user_pool_client_id
    $USERNAME = $json.cognito_username
    $PASSWORD = $json.cognito_password

    if ([string]::IsNullOrEmpty($API_URL)) {
        Write-Host "ERROR: api_url not found in secret" -ForegroundColor Red
        exit 1
    }

    # Set environment variables
    $env:DASHBOARD_API_URL = $API_URL
    $env:COGNITO_USER_POOL_ID = $POOL_ID
    $env:COGNITO_CLIENT_ID = $CLIENT_ID
    $env:COGNITO_USERNAME = $USERNAME
    $env:COGNITO_PASSWORD = $PASSWORD

    Write-Host "✓ Environment variables loaded:" -ForegroundColor Green
    Write-Host "  DASHBOARD_API_URL: $API_URL"
    Write-Host "  COGNITO_USER_POOL_ID: $POOL_ID"
    Write-Host "  COGNITO_CLIENT_ID: $($CLIENT_ID.Substring(0, 10))..."
    Write-Host ""
    Write-Host "Ready to run dashboard:" -ForegroundColor Cyan
    Write-Host "  python -m dashboard -w 30"
    Write-Host ""
    Write-Host "Environment variables are set in this PowerShell session." -ForegroundColor Yellow

} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    exit 1
}
