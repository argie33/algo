#!/bin/bash

# Force CloudFormation to skip the stuck resource
# This will get your stack back to UPDATE_COMPLETE state

echo "FIXING STUCK CLOUDFORMATION STACK..."
echo "=================================="

# Install unzip first
sudo apt-get update -qq && sudo apt-get install -y unzip

# Download and install AWS CLI
curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -q awscliv2.zip
sudo ./aws/install

# Now force the stack to skip the problematic security group
echo ""
echo "Forcing stack to skip the stuck LambdaSecurityGroup..."
aws cloudformation continue-update-rollback \
    --stack-name stocks-webapp-dev \
    --resources-to-skip LambdaSecurityGroup \
    --region us-east-1

echo ""
echo "Stack rollback initiated - it will skip the security group deletion."
echo "Your stack will be back to a stable UPDATE_COMPLETE state in a few minutes."
echo ""
echo "The old security group will remain but won't block future deployments."