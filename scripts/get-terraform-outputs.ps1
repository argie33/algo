# Get Terraform outputs and export as environment variables
# Usage: . ./scripts/get-terraform-outputs.ps1

param(
    [string]$Environment = "dev",
    [string]$Region = "us-east-1"
)

function Get-TerraformOutput {
    param([string]$OutputName)
    try {
        $value = terraform output -raw $OutputName 2>$null
        if ($LASTEXITCODE -eq 0 -and $value) {
            return $value
        }
    } catch {
        Write-Warning "Could not get Terraform output '$OutputName': $_"
    }
    return $null
}

# Derive infrastructure names from Terraform variables
$ProjectName = "algo"
$env:TF_PROJECT_NAME = $ProjectName
$env:TF_ENVIRONMENT = $Environment
$env:TF_REGION = $Region

# Derived resource names (following Terraform naming conventions)
$env:COGNITO_POOL_NAME = "$ProjectName-pool-$Environment"
$env:COGNITO_CLIENT_NAME = "$ProjectName-web-app-$Environment"
$env:ECS_CLUSTER_NAME = "$ProjectName-cluster"
$env:RDS_INSTANCE_ID = "$ProjectName-db"
$env:SNS_TOPIC_NAME = "$ProjectName-loader-failures-$Environment"

# Try to fetch actual Terraform outputs if available
$TfCognitoPoolId = Get-TerraformOutput "cognito_user_pool_id"
if ($TfCognitoPoolId) {
    $env:COGNITO_USER_POOL_ID = $TfCognitoPoolId
}

$TfEcsCluster = Get-TerraformOutput "ecs_cluster_name"
if ($TfEcsCluster) {
    $env:ECS_CLUSTER_NAME = $TfEcsCluster
}

$TfRdsEndpoint = Get-TerraformOutput "rds_address"
if ($TfRdsEndpoint) {
    $env:RDS_HOST = $TfRdsEndpoint
}

$TfApiUrl = Get-TerraformOutput "api_url"
if ($TfApiUrl) {
    $env:API_URL = $TfApiUrl
}

$TfCloudFrontDomain = Get-TerraformOutput "cloudfront_domain"
if ($TfCloudFrontDomain) {
    $env:CLOUDFRONT_DOMAIN = $TfCloudFrontDomain
}

$TfAwsRegion = Get-TerraformOutput "aws_region"
if ($TfAwsRegion) {
    $env:AWS_REGION = $TfAwsRegion
}

Write-Host "Terraform outputs loaded:" -ForegroundColor Green
Write-Host "  COGNITO_POOL_NAME: $env:COGNITO_POOL_NAME"
Write-Host "  COGNITO_CLIENT_NAME: $env:COGNITO_CLIENT_NAME"
Write-Host "  ECS_CLUSTER_NAME: $env:ECS_CLUSTER_NAME"
Write-Host "  RDS_INSTANCE_ID: $env:RDS_INSTANCE_ID"
if ($env:COGNITO_USER_POOL_ID) { Write-Host "  COGNITO_USER_POOL_ID: $env:COGNITO_USER_POOL_ID" }
if ($env:RDS_HOST) { Write-Host "  RDS_HOST: $env:RDS_HOST" }
if ($env:CLOUDFRONT_DOMAIN) { Write-Host "  CLOUDFRONT_DOMAIN: $env:CLOUDFRONT_DOMAIN" }
