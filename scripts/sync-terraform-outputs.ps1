# Sync Terraform outputs to git with version control
# This ensures outputs are tracked in git and prevents staleness
# Usage: ./scripts/sync-terraform-outputs.ps1 [-DryRun]

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$InformationPreference = "Continue"

function Write-Status {
    param([string]$Message, [string]$Color = "Green")
    Write-Host "[$((Get-Date -Format 'HH:mm:ss'))] $Message" -ForegroundColor $Color
}

function Test-OutputsStale {
    param([int]$MaxAgeMinutes = 1440)  # Default: 24 hours

    if (-not (Test-Path ".terraform-outputs.json")) {
        Write-Status "No previous outputs found" "Yellow"
        return $true
    }

    $file = Get-Item ".terraform-outputs.json"
    $age = (Get-Date) - $file.LastWriteTime

    if ($age.TotalMinutes -gt $MaxAgeMinutes) {
        Write-Status "Outputs are stale: $([Math]::Round($age.TotalHours, 2)) hours old (max: $($MaxAgeMinutes / 60) hours)" "Yellow"
        return $true
    }

    Write-Status "Outputs are fresh: $([Math]::Round($age.TotalMinutes, 1)) minutes old" "Green"
    return $false
}

function Sync-TerraformOutputs {
    try {
        # Ensure we're in terraform directory for terraform output
        $terraformDir = "terraform"
        if (-not (Test-Path $terraformDir)) {
            throw "Terraform directory not found at $terraformDir"
        }

        Write-Status "Fetching Terraform outputs..."
        $outputs = & terraform -C $terraformDir output -json 2>&1

        if ($LASTEXITCODE -ne 0) {
            throw "Failed to fetch Terraform outputs: $outputs"
        }

        $outputsJson = $outputs | ConvertFrom-Json

        # Create output file with metadata
        $outputData = @{
            timestamp = (Get-Date -AsUTC -Format 'o')
            git_commit = & git rev-parse HEAD
            outputs = $outputsJson
        }

        # Save to file
        $outputFile = ".terraform-outputs.json"
        $outputData | ConvertTo-Json -Depth 10 | Set-Content $outputFile -Encoding UTF8

        Write-Status "Outputs saved to $outputFile" "Green"

        # Show summary of key outputs (non-sensitive ones)
        Write-Status "Key outputs:" "Cyan"
        @(
            "ecr_repository_url",
            "api_lambda_function_name",
            "api_gateway_endpoint",
            "cognito_user_pool_id",
            "cloudfront_domain",
            "website_url"
        ) | ForEach-Object {
            if ($outputsJson.PSObject.Properties.Name -contains $_) {
                $value = $outputsJson.$_.value
                if ($value -and $value -ne "null" -and $value -ne "") {
                    Write-Host "  $($_): $value" -ForegroundColor Gray
                }
            }
        }

        return $true
    }
    catch {
        Write-Status "Error syncing outputs: $_" "Red"
        return $false
    }
}

function Commit-Outputs {
    $outputFile = ".terraform-outputs.json"

    if (-not (Test-Path $outputFile)) {
        Write-Status "No outputs file to commit" "Yellow"
        return $false
    }

    # Check if file has changes
    $status = & git status --short $outputFile
    if ([string]::IsNullOrEmpty($status)) {
        Write-Status "No changes to Terraform outputs" "Gray"
        return $false
    }

    Write-Status "Committing Terraform outputs..." "Cyan"

    if ($DryRun) {
        Write-Status "[DRY RUN] Would commit: $status" "Yellow"
        return $true
    }

    & git add $outputFile
    & git commit -m "INFRA: Update Terraform outputs with current AWS state" --quiet

    Write-Status "Committed Terraform outputs to git" "Green"
    return $true
}

# Main execution
Write-Status "=== Terraform Outputs Sync ===" "Cyan"

# Step 1: Fetch outputs from Terraform
if (-not (Sync-TerraformOutputs)) {
    Write-Status "Failed to sync outputs" "Red"
    exit 1
}

# Step 2: Check freshness
Test-OutputsStale -MaxAgeMinutes 1440 | Out-Null

# Step 3: Commit to git if changed
if (-not $DryRun) {
    Commit-Outputs | Out-Null
}

Write-Status "Sync complete" "Green"
