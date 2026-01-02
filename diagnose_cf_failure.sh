#!/bin/bash
# CloudFormation Deployment Failure Diagnostic Script
# Run this to investigate why the stocks-ecs-tasks-stack deployment is failing

echo "================================================================"
echo "CloudFormation Deployment Diagnostic Tool"
echo "================================================================"
echo ""

# Check if stack exists
echo "1. Checking if stack exists..."
if aws cloudformation describe-stacks --stack-name stocks-ecs-tasks-stack 2>/dev/null; then
  echo "✅ Stack exists"
  STACK_STATUS=$(aws cloudformation describe-stacks --stack-name stocks-ecs-tasks-stack --query 'Stacks[0].StackStatus' --output text)
  echo "   Status: $STACK_STATUS"

  # Get stack events
  echo ""
  echo "2. Recent stack events (last 20):"
  aws cloudformation describe-stack-events --stack-name stocks-ecs-tasks-stack --max-items 20 --query 'StackEvents[*].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]' --output table
else
  echo "❌ Stack does not exist (likely rolled back and deleted)"
  echo ""
  echo "2. Attempting to get deleted stack events..."
  # Try to get events even for deleted stack (this might not work)
  aws cloudformation describe-stack-events --stack-name stocks-ecs-tasks-stack --max-items 50 2>&1 | head -100
fi

echo ""
echo "3. Checking prerequisite stacks..."
echo ""
echo "stocks-core-stack:"
aws cloudformation describe-stacks --stack-name stocks-core-stack --query 'Stacks[0].StackStatus' --output text 2>&1

echo ""
echo "stocks-app-stack:"
aws cloudformation describe-stacks --stack-name stocks-app-stack --query 'Stacks[0].StackStatus' --output text 2>&1

echo ""
echo "4. Checking required CloudFormation exports..."
REQUIRED_EXPORTS="StocksCore-ContainerRepositoryUri StocksCore-PublicSubnet1Id StocksCore-PublicSubnet2Id StocksApp-ClusterArn StocksApp-EcsTasksSecurityGroupId StocksApp-SecretArn StocksApp-DBEndpoint StocksApp-DBPort StocksApp-DBName"

for export in $REQUIRED_EXPORTS; do
  if aws cloudformation list-exports --query "Exports[?Name=='$export'].Value" --output text 2>&1 | grep -q "."; then
    VALUE=$(aws cloudformation list-exports --query "Exports[?Name=='$export'].Value" --output text)
    echo "✅ $export = $VALUE"
  else
    echo "❌ $export MISSING"
  fi
done

echo ""
echo "5. Checking ECR repository..."
REPO_URI=$(aws cloudformation list-exports --query "Exports[?Name=='StocksCore-ContainerRepositoryUri'].Value" --output text)
if [ -n "$REPO_URI" ]; then
  REPO_NAME=$(echo $REPO_URI | awk -F'/' '{print $2}')
  echo "Repository: $REPO_NAME"
  echo "Available image tags:"
  aws ecr list-images --repository-name $REPO_NAME --query 'imageIds[*].imageTag' --output text | tr '\t' '\n' | sort | head -20
fi

echo ""
echo "6. Validating CloudFormation template..."
aws cloudformation validate-template --template-url https://stocks-cf-templates-626216981288.s3.amazonaws.com/template-app-ecs-tasks.yml 2>&1 | head -10

echo ""
echo "7. Checking S3 template file..."
aws s3api head-object --bucket stocks-cf-templates-626216981288 --key template-app-ecs-tasks.yml --query '{LastModified:LastModified,Size:ContentLength}' --output table

echo ""
echo "8. Checking recent GitHub Actions workflow runs..."
curl -s "https://api.github.com/repos/argie33/algo/actions/runs?per_page=3" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    runs = data.get('workflow_runs', [])
    for r in runs[:3]:
        if 'Data Loaders Pipeline' in r.get('name', ''):
            print(f\"Run: {r['name']}\")
            print(f\"  Status: {r['status']} ({r['conclusion']})\")
            print(f\"  Created: {r['created_at']}\")
            print(f\"  URL: {r['html_url']}\")
            print()
except:
    print('Could not fetch GitHub Actions data')
"

echo ""
echo "================================================================"
echo "Diagnostic complete!"
echo ""
echo "To get more details, check the GitHub Actions workflow logs at:"
echo "https://github.com/argie33/algo/actions"
echo ""
echo "Look for the 'Deploy Infrastructure' job and expand the"
echo "'Deploy ECS tasks stack' step to see the actual CloudFormation error."
echo "================================================================"
