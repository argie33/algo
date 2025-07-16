#!/bin/bash

# Debug script to identify stuck resources in CloudFormation stack
STACK_NAME="stocks-webapp-dev"

echo "🔍 Analyzing stuck CloudFormation stack: $STACK_NAME"
echo "================================================="

# Check stack status
echo "📊 Stack Status:"
aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query 'Stacks[0].StackStatus' --output text

echo ""
echo "📋 Stack Events (last 20):"
aws cloudformation describe-stack-events --stack-name "$STACK_NAME" --max-items 20 --query 'StackEvents[*].[Timestamp,ResourceStatus,ResourceType,LogicalResourceId,ResourceStatusReason]' --output table

echo ""
echo "🔍 Stack Resources:"
aws cloudformation describe-stack-resources --stack-name "$STACK_NAME" --query 'StackResources[*].[LogicalResourceId,ResourceType,ResourceStatus,ResourceStatusReason]' --output table

echo ""
echo "💡 Common fixes for stuck stacks:"
echo "1. Check if any Lambda functions are still running"
echo "2. Check if any S3 buckets have objects that need to be deleted"
echo "3. Check if any custom resources are stuck"
echo "4. Contact AWS Support with the stack ARN"