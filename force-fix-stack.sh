#!/bin/bash

set -e

STACK_NAME="stocks-webapp-dev"

echo "🔥 NUCLEAR OPTION: Force fixing stuck CloudFormation stack"
echo "=========================================================="

echo "📊 Current stack status:"
aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query 'Stacks[0].StackStatus' --output text

echo ""
echo "🔧 Step 1: Try continue-update-rollback first..."
aws cloudformation continue-update-rollback --stack-name "$STACK_NAME" || {
    echo "❌ Continue-update-rollback failed, proceeding with force fix..."
}

echo ""
echo "🔧 Step 2: Deploy minimal template to unstick resources..."
sam build --template fix-stuck-lambda.yml
sam deploy --template-file fix-stuck-lambda.yml --stack-name "$STACK_NAME" --capabilities CAPABILITY_IAM --parameter-overrides EnvironmentName=dev --no-confirm-changeset || {
    echo "❌ Minimal template deployment failed"
}

echo ""
echo "🔧 Step 3: Wait for stack to stabilize..."
aws cloudformation wait stack-update-complete --stack-name "$STACK_NAME" || {
    echo "⚠️ Stack didn't complete normally, checking status..."
    STATUS=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query 'Stacks[0].StackStatus' --output text)
    echo "Current status: $STATUS"
    
    if [[ "$STATUS" == "UPDATE_ROLLBACK_COMPLETE" ]]; then
        echo "✅ Stack is now in rollback complete state"
    fi
}

echo ""
echo "🗑️ Step 4: Delete the stack..."
aws cloudformation delete-stack --stack-name "$STACK_NAME"

echo ""
echo "⏰ Step 5: Wait for deletion to complete..."
aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" || {
    echo "❌ Stack deletion failed or timed out"
    echo "💡 You may need to manually delete remaining resources"
}

echo ""
echo "✅ Stack should now be completely removed!"
echo "🚀 You can now re-run your deployment workflow"