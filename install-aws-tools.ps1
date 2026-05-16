# ================================================================
# INSTALL AWS TOOLS - AWS CLI, Terraform
# Run as Administrator to install deployment tools
# ================================================================

if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "INSTALLING AWS TOOLS" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# =================================================================
# AWS CLI
# =================================================================
Write-Host "STEP 1: Installing AWS CLI v2..." -ForegroundColor Yellow

if (Get-Command aws -ErrorAction SilentlyContinue) {
    Write-Host "✓ AWS CLI already installed" -ForegroundColor Green
    aws --version
} else {
    Write-Host "Downloading AWS CLI v2..." -ForegroundColor Cyan

    $awsInstallerUrl = "https://awscli.amazonaws.com/AWSCLIV2.msi"
    $awsInstallerPath = "$env:TEMP\AWSCLIV2.msi"

    try {
        Invoke-WebRequest -Uri $awsInstallerUrl -OutFile $awsInstallerPath -UseBasicParsing

        Write-Host "Installing..." -ForegroundColor Cyan
        $process = Start-Process -FilePath "msiexec.exe" -ArgumentList "/i", $awsInstallerPath, "/quiet", "/norestart" -PassThru -Wait

        if ($process.ExitCode -eq 0) {
            Write-Host "✓ AWS CLI installed successfully" -ForegroundColor Green
            aws --version
        } else {
            Write-Host "⚠ Installation completed with code: $($process.ExitCode)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "✗ Error downloading/installing AWS CLI: $_" -ForegroundColor Red
    }
}

Write-Host ""

# =================================================================
# Terraform
# =================================================================
Write-Host "STEP 2: Installing Terraform..." -ForegroundColor Yellow

if (Get-Command terraform -ErrorAction SilentlyContinue) {
    Write-Host "✓ Terraform already installed" -ForegroundColor Green
    terraform --version
} else {
    Write-Host "Downloading Terraform..." -ForegroundColor Cyan

    # Get latest version
    $terraformUrl = "https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_windows_amd64.zip"
    $terraformPath = "$env:TEMP\terraform.zip"

    try {
        Invoke-WebRequest -Uri $terraformUrl -OutFile $terraformPath -UseBasicParsing

        # Extract to C:\Program Files\Terraform
        $terraformDir = "C:\Program Files\Terraform"
        New-Item -ItemType Directory -Path $terraformDir -Force | Out-Null

        Expand-Archive -Path $terraformPath -DestinationPath $terraformDir -Force

        # Add to PATH (permanent)
        $currentPath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
        if (-not $currentPath.Contains($terraformDir)) {
            [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$terraformDir", "Machine")
            Write-Host "✓ Added Terraform to PATH" -ForegroundColor Green
        }

        # Test
        & "$terraformDir\terraform.exe" --version
        Write-Host "✓ Terraform installed successfully" -ForegroundColor Green

    } catch {
        Write-Host "✗ Error downloading/installing Terraform: $_" -ForegroundColor Red
    }
}

Write-Host ""

# =================================================================
# Configure AWS Credentials
# =================================================================
Write-Host "STEP 3: Configure AWS Credentials (Optional)" -ForegroundColor Yellow

$configChoice = Read-Host "Configure AWS credentials now? (y/n)"

if ($configChoice -eq "y" -or $configChoice -eq "Y") {
    Write-Host "Running: aws configure" -ForegroundColor Cyan
    Write-Host "You'll need:" -ForegroundColor Yellow
    Write-Host "  - AWS Access Key ID" -ForegroundColor Cyan
    Write-Host "  - AWS Secret Access Key" -ForegroundColor Cyan
    Write-Host "  - Default region: us-east-1" -ForegroundColor Cyan
    Write-Host ""

    aws configure
} else {
    Write-Host "Skipping AWS configuration" -ForegroundColor Yellow
    Write-Host "Run 'aws configure' later to set up credentials" -ForegroundColor Cyan
}

Write-Host ""

# =================================================================
# Summary
# =================================================================
Write-Host "================================================" -ForegroundColor Green
Write-Host "✓ TOOLS INSTALLATION COMPLETE" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Installed Tools:" -ForegroundColor Cyan

$tools = @(
    @{Name = "AWS CLI"; Command = "aws"; Ver = "aws --version" },
    @{Name = "Terraform"; Command = "terraform"; Ver = "terraform --version" }
)

foreach ($tool in $tools) {
    if (Get-Command $tool.Command -ErrorAction SilentlyContinue) {
        Write-Host "  ✓ $($tool.Name)" -ForegroundColor Green
        & ([scriptblock]::Create($tool.Ver))
    } else {
        Write-Host "  ✗ $($tool.Name) - not found" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Review AWS_SETUP_CHECKLIST.md" -ForegroundColor Cyan
Write-Host "  2. Configure GitHub secrets for deployment" -ForegroundColor Cyan
Write-Host "  3. Run: terraform init" -ForegroundColor Cyan
Write-Host "  4. Run: terraform plan" -ForegroundColor Cyan
Write-Host "  5. Deploy with: terraform apply" -ForegroundColor Cyan
Write-Host ""
