#!/bin/bash
# Redeploy CloudFormation Stack for ECS Loaders

set -e

STACK_NAME="stocks-ecs-tasks-stack"
TEMPLATE_FILE="template-app-ecs-tasks.yml"
REGION="us-east-1"

echo "🚀 Deploying CloudFormation Stack: $STACK_NAME"
echo "Template: $TEMPLATE_FILE"
echo "Region: $REGION"
echo ""

# Step 1: Validate template
echo "1️⃣ Validating CloudFormation template..."
aws cloudformation validate-template \
  --template-body "file://$TEMPLATE_FILE" \
  --region $REGION > /dev/null && echo "✅ Template valid"

# Step 2: Deploy stack
echo ""
echo "2️⃣ Creating/Updating CloudFormation stack..."
aws cloudformation create-stack \
  --stack-name $STACK_NAME \
  --template-body "file://$TEMPLATE_FILE" \
  --region $REGION \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --on-failure DELETE || true

# If create fails (stack already exists), update instead
if [ $? -ne 0 ]; then
  echo "Stack exists, updating instead..."
  aws cloudformation update-stack \
    --stack-name $STACK_NAME \
    --template-body "file://$TEMPLATE_FILE" \
    --region $REGION \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM || true
fi

# Step 3: Wait for stack to complete
echo ""
echo "3️⃣ Waiting for stack to complete (this may take 10-30 minutes)..."
aws cloudformation wait stack-create-complete \
  --stack-name $STACK_NAME \
  --region $REGION 2>/dev/null || \
aws cloudformation wait stack-update-complete \
  --stack-name $STACK_NAME \
  --region $REGION 2>/dev/null || \
echo "⏳ Stack creation/update started - check status with:"
echo "   aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION"

# Step 4: Check status
echo ""
echo "4️⃣ Checking stack status..."
STATUS=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].StackStatus' \
  --output text 2>/dev/null || echo "UNKNOWN")

echo "Stack Status: $STATUS"

if [[ "$STATUS" == "CREATE_COMPLETE" || "$STATUS" == "UPDATE_COMPLETE" ]]; then
  echo "✅ Stack deployment successful!"

  # Step 5: Verify ECS services
  echo ""
  echo "5️⃣ Checking ECS services..."
  aws ecs list-services --cluster stocks-cluster --region $REGION | head -10

  echo ""
  echo "✅ CloudFormation stack ready!"
  echo "ECS loaders should start running automatically."

elif [[ "$STATUS" == *"IN_PROGRESS"* ]]; then
  echo "⏳ Stack creation still in progress..."
  echo "Check back in a few minutes."

else
  echo "❌ Stack status unexpected: $STATUS"
  echo ""
  echo "Checking stack events for errors..."
  aws cloudformation describe-stack-events \
    --stack-name $STACK_NAME \
    --region $REGION | grep -i "failed\|error" | head -10 || echo "No errors found in events"
fi

echo ""
echo "Done!"
