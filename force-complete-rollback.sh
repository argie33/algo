#!/bin/bash

STACK_NAME="stocks-webapp-dev"

echo "🔧 Attempting to force complete rollback for stuck stack: $STACK_NAME"
echo "================================================================"

# Check current status
echo "📊 Current stack status:"
aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query 'Stacks[0].StackStatus' --output text

echo ""
echo "🔍 Checking for stuck resources..."
aws cloudformation describe-stack-resources --stack-name "$STACK_NAME" --query 'StackResources[?ResourceStatus==`UPDATE_ROLLBACK_FAILED`].[LogicalResourceId,ResourceType,ResourceStatus,ResourceStatusReason]' --output table

echo ""
echo "🔧 Attempting continue-update-rollback..."
aws cloudformation continue-update-rollback --stack-name "$STACK_NAME" && {
    echo "✅ Continue-update-rollback initiated successfully"
    echo "⏰ Waiting for rollback to complete..."
    
    # Wait for completion
    while true; do
        STATUS=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "STACK_NOT_FOUND")
        echo "Current status: $STATUS"
        
        if [[ "$STATUS" == "UPDATE_ROLLBACK_COMPLETE" ]]; then
            echo "✅ Stack rollback completed! Now attempting to delete..."
            aws cloudformation delete-stack --stack-name "$STACK_NAME"
            echo "🗑️ Stack deletion initiated"
            break
        elif [[ "$STATUS" == "STACK_NOT_FOUND" ]]; then
            echo "✅ Stack no longer exists"
            break
        elif [[ "$STATUS" == *"FAILED"* ]]; then
            echo "❌ Stack failed. Manual intervention required."
            break
        fi
        
        sleep 30
    done
} || {
    echo "❌ Continue-update-rollback failed"
    echo "💡 You may need to:"
    echo "   1. Identify stuck resources and skip them"
    echo "   2. Contact AWS Support"
    echo "   3. Wait for automatic resolution"
}