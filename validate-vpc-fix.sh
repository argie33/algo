#!/bin/bash

# Validate VPC configuration fixes for Lambda
echo "🔍 Validating CloudFormation template with VPC fixes..."

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Please install AWS CLI to validate templates."
    exit 1
fi

# Validate the CloudFormation template syntax
echo "📋 Validating template syntax..."
aws cloudformation validate-template --template-body file://template-webapp-lambda.yml

if [ $? -eq 0 ]; then
    echo "✅ CloudFormation template validation passed!"
else
    echo "❌ CloudFormation template validation failed!"
    exit 1
fi

echo ""
echo "🔧 VPC Configuration Changes Summary:"
echo "==========================================="
echo "✅ Lambda VPC Configuration:"
echo "   - Added VpcConfig with public subnets"
echo "   - SecurityGroupIds: LambdaSecurityGroup"
echo "   - SubnetIds: PublicSubnet1Id, PublicSubnet2Id"
echo ""
echo "✅ Security Groups:"
echo "   - LambdaSecurityGroup: Allows PostgreSQL (5432) and HTTPS (443/80)"
echo "   - SecretsManagerEndpointSecurityGroup: Allows HTTPS from VPC"
echo ""
echo "✅ VPC Endpoint:"
echo "   - SecretsManagerVPCEndpoint: Interface endpoint for secure access"
echo ""
echo "✅ IAM Permissions:"
echo "   - Added AWSLambdaVPCAccessExecutionRole managed policy"
echo ""
echo "🎯 Expected Benefits:"
echo "   - Lambda can connect to RDS in same public subnets"
echo "   - Secrets Manager access via VPC endpoint (secure and fast)"
echo "   - Proper network isolation with security groups"
echo "   - Internet access maintained for external API calls"
echo ""
echo "⚠️  Next Steps:"
echo "   1. Deploy using: sam deploy --parameter-overrides DatabaseSecretArn=<actual-arn>"
echo "   2. Test database connectivity from Lambda"
echo "   3. Verify Secrets Manager access works"
echo "   4. Monitor CloudWatch logs for connection errors"