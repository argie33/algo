# Verify Terraform outputs are fresh and accurate
# Compares git-tracked outputs against live AWS state
# Usage: ./scripts/verify-terraform-outputs.ps1 [-MaxAgeHours 24]

param(
    [int]$MaxAgeHours = 24
)

$ErrorActionPreference = "Stop"

function Write-Status {
    param([string]$Message, [string]$Color = "Green")
    Write-Host "[$((Get-Date -Format 'HH:mm:ss'))] $Message" -ForegroundColor $Color
}

function Get-GitOutputs {
    $outputFile = ".terraform-outputs.json"

    if (-not (Test-Path $outputFile)) {
        return $null
    }

    try {
        $data = Get-Content $outputFile -Raw | ConvertFrom-Json
        return $data
    }
    catch {
        Write-Status "Failed to parse git outputs: $_" "Red"
        return $null
    }
}

function Get-LiveOutputs {
    try {
        Write-Status "Fetching live outputs from Terraform..." "Cyan"
        $outputs = & terraform -C terraform output -json 2>&1

        if ($LASTEXITCODE -ne 0) {
            Write-Status "Failed to fetch live outputs: $outputs" "Red"
            return $null
        }

        return $outputs | ConvertFrom-Json
    }
    catch {
        Write-Status "Error fetching live outputs: $_" "Red"
        return $null
    }
}

function Test-OutputFreshness {
    param($OutputData)

    if (-not $OutputData) {
        Write-Status "No outputs to check" "Yellow"
        return $false
    }

    $timestamp = $OutputData.timestamp
    if (-not $timestamp) {
        Write-Status "No timestamp in outputs" "Yellow"
        return $false
    }

    try {
        $outputTime = [DateTime]::Parse($timestamp)
        $age = (Get-Date) - $outputTime
        $ageHours = [Math]::Round($age.TotalHours, 2)

        if ($age.TotalHours -gt $MaxAgeHours) {
            Write-Status "Outputs are STALE: $ageHours hours old (max: $MaxAgeHours hours)" "Red"
            return $false
        }

        Write-Status "Outputs are FRESH: $ageHours hours old" "Green"
        return $true
    }
    catch {
        Write-Status "Failed to parse timestamp: $_" "Yellow"
        return $false
    }
}

function Compare-Outputs {
    param($GitOutputs, $LiveOutputs)

    if (-not $GitOutputs -or -not $LiveOutputs) {
        Write-Status "Cannot compare - missing outputs" "Yellow"
        return $true
    }

    $gitOutputValues = $GitOutputs.outputs
    $differences = @()

    # Check critical outputs
    $criticalOutputs = @(
        "api_gateway_endpoint",
        "cognito_user_pool_id",
        "cognito_user_pool_client_id",
        "ecr_repository_url",
        "ecs_cluster_name"
    )

    $criticalOutputs | ForEach-Object {
        if ($LiveOutputs.PSObject.Properties.Name -contains $_) {
            $liveValue = $LiveOutputs.$_.value
            $gitValue = $gitOutputValues.$_.value

            if ($liveValue -ne $gitValue) {
                $differences += @{
                    output = $_
                    git = $gitValue
                    live = $liveValue
                }

                Write-Status "DIFF: $_ changed!" "Red"
                Write-Host "  Git:  $gitValue" -ForegroundColor Gray
                Write-Host "  Live: $liveValue" -ForegroundColor Gray
            }
        }
    }

    if ($differences.Count -eq 0) {
        Write-Status "All critical outputs match live AWS state" "Green"
        return $true
    }

    Write-Status "Found $($differences.Count) differences - outputs may be stale" "Red"
    return $false
}

# Main execution
Write-Status "=== Terraform Outputs Verification ===" "Cyan"

# Check freshness of git-tracked outputs
$gitOutputs = Get-GitOutputs
if ($gitOutputs) {
    $isFresh = Test-OutputFreshness $gitOutputs
}
else {
    Write-Status "No git-tracked outputs found - run sync-terraform-outputs.ps1" "Yellow"
    $isFresh = $false
}

# Verify against live AWS state
$liveOutputs = Get-LiveOutputs
if ($liveOutputs -and $gitOutputs) {
    $isAccurate = Compare-Outputs $gitOutputs $liveOutputs
}
else {
    Write-Status "Cannot verify against live state" "Yellow"
    $isAccurate = $false
}

# Summary
Write-Status ""
Write-Status "=== Summary ===" "Cyan"
Write-Host "Freshness: $(if ($isFresh) { 'PASS' } else { 'FAIL' })" -ForegroundColor (if ($isFresh) { 'Green' } else { 'Red' })
Write-Host "Accuracy:  $(if ($isAccurate) { 'PASS' } else { 'FAIL' })" -ForegroundColor (if ($isAccurate) { 'Green' } else { 'Red' })

if (-not $isFresh -or -not $isAccurate) {
    Write-Status "Outputs need to be refreshed! Run: ./scripts/sync-terraform-outputs.ps1" "Red"
    exit 1
}

Write-Status "Verification complete - outputs are fresh and accurate" "Green"
exit 0
