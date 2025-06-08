#!/usr/bin/env pwsh
# Debug script to check CloudFormation stack and bucket issues

$STACK_NAME = "financial-dashboard-webapp-prod"

Write-Host "=== CloudFormation Stack Resources ===" -ForegroundColor Yellow
aws cloudformation describe-stack-resources --stack-name $STACK_NAME --query "StackResources[?LogicalResourceId=='FrontendBucket']" --output table

Write-Host "`n=== CloudFormation Stack Outputs ===" -ForegroundColor Yellow  
aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs" --output table

Write-Host "`n=== CloudFormation Stack Events (last 20) ===" -ForegroundColor Yellow
aws cloudformation describe-stack-events --stack-name $STACK_NAME --query "StackEvents[0:20].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]" --output table

Write-Host "`n=== Check if bucket actually exists ===" -ForegroundColor Yellow
$bucketName = aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" --output text

if ($bucketName -and $bucketName -ne "None" -and $bucketName.Trim() -ne "") {
    Write-Host "Bucket name from stack output: $bucketName"
    Write-Host "Checking if bucket exists..."
    aws s3 ls "s3://$bucketName" 2>&1
} else {
    Write-Host "❌ No bucket name found in stack outputs!" -ForegroundColor Red
    
    # Try to find the bucket resource physical ID
    $physicalId = aws cloudformation describe-stack-resources --stack-name $STACK_NAME --logical-resource-id "FrontendBucket" --query "StackResources[0].PhysicalResourceId" --output text 2>$null
    
    if ($physicalId -and $physicalId -ne "None") {
        Write-Host "Physical bucket ID from resource: $physicalId"
        aws s3 ls "s3://$physicalId" 2>&1
    } else {
        Write-Host "❌ No physical bucket resource found!" -ForegroundColor Red
    }
}

Write-Host "`n=== Stack Status ===" -ForegroundColor Yellow
aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].StackStatus" --output text
