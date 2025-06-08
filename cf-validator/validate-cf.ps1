# CloudFormation Fast Validation Script
# Runs multiple validation methods to catch issues without full deployments

param(
    [Parameter(Mandatory=$true)]
    [string]$TemplatePath,
    
    [Parameter(Mandatory=$false)]
    [string]$StackName,
    
    [Parameter(Mandatory=$false)]
    [string]$ParametersFile,
    
    [Parameter(Mandatory=$false)]
    [string]$Region = "us-east-1",
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipAWS,
    
    [Parameter(Mandatory=$false)]
    [switch]$QuickOnly
)

# Colors for output
$Red = "Red"
$Green = "Green"
$Yellow = "Yellow"
$Blue = "Cyan"

function Write-ColorOutput {
    param([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Color
}

function Test-Prerequisites {
    Write-ColorOutput "🔧 Checking prerequisites..." $Blue
    
    # Check if template file exists
    if (-not (Test-Path $TemplatePath)) {
        Write-ColorOutput "❌ Template file not found: $TemplatePath" $Red
        return $false
    }
    
    # Check Python
    try {
        $pythonVersion = python --version 2>&1
        Write-ColorOutput "✅ Python available: $pythonVersion" $Green
    } catch {
        Write-ColorOutput "❌ Python not found. Please install Python 3.7+" $Red
        return $false
    }
    
    # Check AWS CLI (only if not skipping AWS)
    if (-not $SkipAWS) {
        try {
            $awsVersion = aws --version 2>&1
            Write-ColorOutput "✅ AWS CLI available: $awsVersion" $Green
        } catch {
            Write-ColorOutput "⚠️ AWS CLI not found. Skipping AWS validations." $Yellow
            $Script:SkipAWS = $true
        }
        
        # Check AWS credentials
        if (-not $SkipAWS) {
            try {
                $identity = aws sts get-caller-identity --output text --query 'Account' 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-ColorOutput "✅ AWS credentials configured (Account: $identity)" $Green
                } else {
                    Write-ColorOutput "⚠️ AWS credentials not configured. Skipping AWS validations." $Yellow
                    $Script:SkipAWS = $true
                }
            } catch {
                Write-ColorOutput "⚠️ Cannot verify AWS credentials. Skipping AWS validations." $Yellow
                $Script:SkipAWS = $true
            }
        }
    }
    
    return $true
}

function Invoke-LocalValidation {
    Write-ColorOutput "`n🚀 Running LOCAL validation (Ultra-fast, no AWS calls)..." $Blue
    Write-ColorOutput "=" * 60 $Blue
    
    try {
        $result = python "local-cf-validator.py" $TemplatePath
        
        if ($LASTEXITCODE -eq 0) {
            Write-ColorOutput "✅ Local validation PASSED" $Green
            return $true
        } else {
            Write-ColorOutput "❌ Local validation FAILED" $Red
            return $false
        }
    } catch {
        Write-ColorOutput "❌ Local validation script error: $_" $Red
        return $false
    }
}

function Invoke-AWSValidation {
    param([string]$ValidationLevel = "syntax")
    
    if ($SkipAWS) {
        Write-ColorOutput "⏭️ Skipping AWS validation (--SkipAWS specified)" $Yellow
        return $true
    }
    
    Write-ColorOutput "`n🌍 Running AWS validation ($ValidationLevel)..." $Blue
    Write-ColorOutput "=" * 60 $Blue
    
    $args = @($ValidationLevel, "--template", $TemplatePath, "--region", $Region)
    
    if ($StackName) {
        $args += @("--stack-name", $StackName)
    }
    
    if ($ParametersFile) {
        $args += @("--parameters", $ParametersFile)
    }
    
    try {
        python "cloudformation-validator.py" @args
        
        if ($LASTEXITCODE -eq 0) {
            Write-ColorOutput "✅ AWS validation ($ValidationLevel) PASSED" $Green
            return $true
        } else {
            Write-ColorOutput "❌ AWS validation ($ValidationLevel) FAILED" $Red
            return $false
        }
    } catch {
        Write-ColorOutput "❌ AWS validation script error: $_" $Red
        return $false
    }
}

function Show-ValidationSummary {
    param(
        [bool]$LocalPassed,
        [bool]$SyntaxPassed,
        [bool]$ChangesetPassed,
        [bool]$EstimatePassed
    )
    
    Write-ColorOutput "`n📊 VALIDATION SUMMARY" $Blue
    Write-ColorOutput "=" * 60 $Blue
    
    $totalTests = 1
    $passedTests = 0
    
    # Local validation
    if ($LocalPassed) {
        Write-ColorOutput "✅ Local Template Validation: PASSED" $Green
        $passedTests++
    } else {
        Write-ColorOutput "❌ Local Template Validation: FAILED" $Red
    }
    
    if (-not $SkipAWS) {
        $totalTests++
        if ($SyntaxPassed) {
            Write-ColorOutput "✅ AWS Syntax Validation: PASSED" $Green
            $passedTests++
        } else {
            Write-ColorOutput "❌ AWS Syntax Validation: FAILED" $Red
        }
        
        if (-not $QuickOnly -and $StackName) {
            $totalTests++
            if ($ChangesetPassed) {
                Write-ColorOutput "✅ AWS Changeset Analysis: PASSED" $Green
                $passedTests++
            } else {
                Write-ColorOutput "❌ AWS Changeset Analysis: FAILED" $Red
            }
        }
        
        $totalTests++
        if ($EstimatePassed) {
            Write-ColorOutput "✅ Deployment Time Estimate: COMPLETED" $Green
            $passedTests++
        } else {
            Write-ColorOutput "❌ Deployment Time Estimate: FAILED" $Red
        }
    }
    
    Write-ColorOutput "`n📈 Results: $passedTests/$totalTests tests passed" $(if ($passedTests -eq $totalTests) { $Green } else { $Yellow })
    
    if ($passedTests -eq $totalTests) {
        Write-ColorOutput "🎉 All validations passed! Template is ready for deployment." $Green
    } else {
        Write-ColorOutput "⚠️ Some validations failed. Review issues before deployment." $Yellow
    }
    
    # Additional recommendations
    Write-ColorOutput "`n💡 RECOMMENDATIONS:" $Blue
    
    if ($passedTests -eq $totalTests) {
        Write-ColorOutput "• Template validation successful - consider testing in dev environment" $Blue
        if ($StackName -and -not $SkipAWS) {
            Write-ColorOutput "• Run drift detection on existing stack if updating" $Blue
        }
    } else {
        Write-ColorOutput "• Fix validation errors before attempting deployment" $Blue
        Write-ColorOutput "• Test locally first, then validate with AWS" $Blue
    }
    
    Write-ColorOutput "• Use changeset preview before deploying to production" $Blue
    Write-ColorOutput "• Monitor CloudFormation events during deployment" $Blue
}

function Show-FastValidationTips {
    Write-ColorOutput "`n🚀 FAST VALIDATION METHODS (No CloudFront wait!):" $Blue
    Write-ColorOutput "=" * 60 $Blue
    Write-ColorOutput "1. LOCAL validation (instant):" $Green
    Write-ColorOutput "   python local-cf-validator.py template.yml" $Blue
    Write-ColorOutput ""
    Write-ColorOutput "2. AWS SYNTAX validation (1-2 seconds):" $Green
    Write-ColorOutput "   aws cloudformation validate-template --template-body file://template.yml" $Blue
    Write-ColorOutput ""
    Write-ColorOutput "3. CHANGESET analysis (5-10 seconds vs 15 minutes):" $Green
    Write-ColorOutput "   python cloudformation-validator.py changeset --template template.yml --stack-name stack" $Blue
    Write-ColorOutput ""
    Write-ColorOutput "4. DRIFT detection (30 seconds):" $Green
    Write-ColorOutput "   python cloudformation-validator.py drift --stack-name stack" $Blue
    Write-ColorOutput ""
    Write-ColorOutput "5. TIME estimation (instant):" $Green
    Write-ColorOutput "   python cloudformation-validator.py estimate --template template.yml" $Blue
}

# Main execution
Write-ColorOutput "🔍 CloudFormation Fast Validation Tool" $Blue
Write-ColorOutput "📁 Template: $TemplatePath" $Blue
if ($StackName) {
    Write-ColorOutput "📦 Stack: $StackName" $Blue
}
Write-ColorOutput "🌍 Region: $Region" $Blue
Write-ColorOutput "=" * 60 $Blue

# Check prerequisites
if (-not (Test-Prerequisites)) {
    Write-ColorOutput "❌ Prerequisites check failed. Exiting." $Red
    exit 1
}

# Initialize results
$localPassed = $false
$syntaxPassed = $false
$changesetPassed = $false
$estimatePassed = $false

# 1. Local validation (always run - fastest)
$localPassed = Invoke-LocalValidation

# Stop here if local validation fails
if (-not $localPassed) {
    Write-ColorOutput "`n❌ Local validation failed. Fix template issues first." $Red
    Show-FastValidationTips
    exit 1
}

# 2. AWS syntax validation
if (-not $SkipAWS) {
    $syntaxPassed = Invoke-AWSValidation "syntax"
    
    # 3. Deployment time estimation
    $estimatePassed = Invoke-AWSValidation "estimate"
    
    # 4. Changeset analysis (only if stack name provided and not quick-only)
    if ($StackName -and -not $QuickOnly) {
        $changesetPassed = Invoke-AWSValidation "changeset"
    } else {
        $changesetPassed = $true  # Skip this test
    }
}

# Show summary
Show-ValidationSummary $localPassed $syntaxPassed $changesetPassed $estimatePassed

# Exit with appropriate code
$allPassed = $localPassed -and ($SkipAWS -or ($syntaxPassed -and $estimatePassed -and $changesetPassed))
exit $(if ($allPassed) { 0 } else { 1 })
