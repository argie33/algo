# Get Terraform outputs from git-tracked cache
# Falls back to live Terraform if cache is missing or stale
# Usage: . ./scripts/get-cached-terraform-outputs.ps1

param(
    [switch]$Refresh,
    [int]$MaxAgeHours = 24
)

$ErrorActionPreference = "Stop"

function Write-Debug {
    param([string]$Message)
    if ($VerbosePreference -eq "Continue") {
        Write-Host "[DEBUG] $Message" -ForegroundColor Gray
    }
}

function Get-CachedOutputs {
    if (-not (Test-Path ".terraform-outputs.json")) {
        Write-Debug "No cached outputs found"
        return $null
    }

    try {
        $data = Get-Content ".terraform-outputs.json" -Raw | ConvertFrom-Json
        return $data
    }
    catch {
        Write-Host "[WARN] Failed to parse cached outputs: $_" -ForegroundColor Yellow
        return $null
    }
}

function Test-CacheValidity {
    param($CachedData, [int]$MaxAgeHours)

    if (-not $CachedData.timestamp) {
        Write-Debug "No timestamp in cached outputs"
        return $false
    }

    try {
        $cacheTime = [DateTime]::Parse($CachedData.timestamp)
        $age = (Get-Date -AsUTC) - $cacheTime
        $ageHours = [Math]::Round($age.TotalHours, 2)

        if ($age.TotalHours -gt $MaxAgeHours) {
            Write-Host "[WARN] Cached outputs are stale: $ageHours hours old (max: $MaxAgeHours hours)" -ForegroundColor Yellow
            return $false
        }

        Write-Debug "Cache is valid: $ageHours hours old"
        return $true
    }
    catch {
        Write-Debug "Failed to parse cache timestamp: $_"
        return $false
    }
}

function Get-LiveOutputs {
    try {
        Write-Host "[INFO] Fetching live Terraform outputs..." -ForegroundColor Cyan
        $terraformDir = "terraform"
        if (-not (Test-Path $terraformDir)) {
            Write-Host "[WARN] Terraform directory not found" -ForegroundColor Yellow
            return $null
        }

        $outputs = & terraform -C $terraformDir output -json 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[WARN] Failed to fetch live outputs: $outputs" -ForegroundColor Yellow
            return $null
        }

        return $outputs | ConvertFrom-Json
    }
    catch {
        Write-Host "[WARN] Error fetching live outputs: $_" -ForegroundColor Yellow
        return $null
    }
}

function Export-OutputsAsEnv {
    param($Outputs)

    $criticalOutputs = @{
        "ecr_repository_url" = "ECR_REPOSITORY_URL"
        "api_lambda_function_name" = "API_LAMBDA_NAME"
        "algo_lambda_function_name" = "ALGO_LAMBDA_NAME"
        "api_gateway_endpoint" = "API_GATEWAY_ENDPOINT"
        "cognito_user_pool_id" = "COGNITO_USER_POOL_ID"
        "cognito_user_pool_client_id" = "COGNITO_USER_POOL_CLIENT_ID"
        "cloudfront_domain" = "CLOUDFRONT_DOMAIN"
        "website_url" = "WEBSITE_URL"
        "ecs_cluster_name" = "ECS_CLUSTER_NAME"
        "aws_region" = "AWS_REGION"
    }

    foreach ($tfKey in $criticalOutputs.Keys) {
        $envKey = $criticalOutputs[$tfKey]

        if ($Outputs.PSObject.Properties.Name -contains $tfKey) {
            $value = $Outputs.$tfKey.value
            if ($value -and $value -ne "null") {
                Set-Item -Path "env:$envKey" -Value $value
                Write-Debug "Set $envKey from Terraform output"
            }
        }
    }
}

# Main execution
Write-Debug "Loading Terraform outputs..."

# Get cached outputs
$cached = Get-CachedOutputs
$isCacheValid = if ($cached) { Test-CacheValidity $cached $MaxAgeHours } else { $false }

# Decide whether to use cache or fetch live
$outputs = $null
$source = $null

if ($Refresh) {
    Write-Host "[INFO] Refresh requested - fetching live outputs" -ForegroundColor Cyan
    $outputs = Get-LiveOutputs
    $source = "live"
}
elseif ($isCacheValid) {
    Write-Host "[OK] Using cached Terraform outputs" -ForegroundColor Green
    $outputs = $cached.outputs
    $source = "cache"
}
else {
    Write-Host "[WARN] Cache missing or stale - fetching live outputs" -ForegroundColor Yellow
    $outputs = Get-LiveOutputs
    if ($outputs) {
        $source = "live"
    }
    else {
        # Fallback to stale cache if live fetch fails
        if ($cached) {
            Write-Host "[WARN] Live fetch failed, using stale cache" -ForegroundColor Yellow
            $outputs = $cached.outputs
            $source = "stale-cache"
        }
    }
}

if ($outputs) {
    Export-OutputsAsEnv $outputs
    Write-Host "[OK] Terraform outputs loaded from $source" -ForegroundColor Green
    return $outputs
}
else {
    Write-Host "[ERROR] Failed to load Terraform outputs" -ForegroundColor Red
    exit 1
}
