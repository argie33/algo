# Initialize Terraform outputs file for git tracking
# Run once after first Terraform deployment to create the initial .terraform-outputs.json
# Usage: ./scripts/init-terraform-outputs.ps1

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Write-Status {
    param([string]$Message, [string]$Color = "Green")
    Write-Host "[$((Get-Date -Format 'HH:mm:ss'))] $Message" -ForegroundColor $Color
}

# Check if file already exists
$outputFile = ".terraform-outputs.json"
if ((Test-Path $outputFile) -and -not $Force) {
    Write-Status "$outputFile already exists. Use -Force to overwrite." "Yellow"
    exit 0
}

# Verify Terraform directory exists
if (-not (Test-Path "terraform")) {
    Write-Status "Terraform directory not found" "Red"
    exit 1
}

Write-Status "Initializing Terraform outputs..." "Cyan"

try {
    # Fetch current Terraform outputs
    Write-Status "Fetching outputs from Terraform..." "Gray"
    $outputs = & terraform -C terraform output -json 2>&1

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to fetch Terraform outputs. Have you run 'terraform apply' yet?"
    }

    # Parse JSON to ensure validity
    $outputsJson = $outputs | ConvertFrom-Json

    # Get current git commit
    $gitCommit = & git rev-parse HEAD

    # Create output structure with metadata
    $outputData = @{
        timestamp = (Get-Date -AsUTC -Format 'o')
        git_commit = $gitCommit
        outputs = $outputsJson
    }

    # Write file
    $outputData | ConvertTo-Json -Depth 10 | Set-Content $outputFile -Encoding UTF8

    Write-Status "Created $outputFile" "Green"

    # Display summary
    Write-Status "Output file contents:" "Cyan"
    Write-Host "  Timestamp: $($outputData.timestamp)" -ForegroundColor Gray
    Write-Host "  Commit: $($gitCommit.Substring(0, 8))" -ForegroundColor Gray
    Write-Host "  Key outputs:" -ForegroundColor Gray

    $criticalOutputs = @(
        "api_gateway_endpoint",
        "cognito_user_pool_id",
        "ecr_repository_url",
        "website_url"
    )

    $criticalOutputs | ForEach-Object {
        if ($outputsJson.PSObject.Properties.Name -contains $_) {
            $value = $outputsJson.$_.value
            if ($value -and $value -ne "null") {
                Write-Host "    $_: $value" -ForegroundColor Gray
            }
        }
    }

    # Commit to git
    Write-Status "Committing to git..." "Cyan"
    & git add $outputFile
    $commitMsg = "INFRA: Initialize Terraform outputs for version control"
    & git commit -m $commitMsg

    Write-Status "Successfully initialized and committed $outputFile" "Green"
    Write-Status "Next: Run 'verify-terraform-outputs.ps1' to validate freshness" "Cyan"
}
catch {
    Write-Status "Error: $_" "Red"
    Write-Status "Make sure Terraform has been applied successfully" "Yellow"
    exit 1
}
