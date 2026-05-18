#!/bin/bash
# Test AWS loaders and orchestrator deployment

set -e
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
AWS_REGION="us-east-1"

echo "🔍 AWS Loader & Orchestrator Testing"
echo "===================================="

# ============================================================
# 1. Check if AWS credentials are configured
# ============================================================
echo ""
echo "1️⃣  Checking AWS credentials..."
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "❌ AWS credentials not configured"
    echo "Run: aws configure"
    exit 1
fi
echo "✅ AWS credentials OK"

# ============================================================
# 2. Verify ECS cluster exists
# ============================================================
echo ""
echo "2️⃣  Checking ECS cluster..."
CLUSTER=$(aws ecs list-clusters --region $AWS_REGION --query 'clusterArns[0]' --output text 2>/dev/null || echo "")
if [ -z "$CLUSTER" ] || [ "$CLUSTER" == "None" ]; then
    echo "❌ No ECS cluster found"
    exit 1
fi
CLUSTER_NAME=$(echo $CLUSTER | cut -d/ -f2)
echo "✅ ECS Cluster: $CLUSTER_NAME"

# ============================================================
# 3. Verify RDS database connectivity
# ============================================================
echo ""
echo "3️⃣  Checking RDS database..."
DB_HOST=$(aws rds describe-db-instances \
    --region $AWS_REGION \
    --query 'DBInstances[0].Endpoint.Address' \
    --output text 2>/dev/null || echo "")
if [ -z "$DB_HOST" ] || [ "$DB_HOST" == "None" ]; then
    echo "❌ No RDS database found"
    exit 1
fi
echo "✅ RDS Host: $DB_HOST"

# ============================================================
# 4. Check Lambda functions
# ============================================================
echo ""
echo "4️⃣  Checking Lambda functions..."
API_LAMBDA=$(aws lambda list-functions \
    --region $AWS_REGION \
    --query 'Functions[?contains(FunctionName, `api`)].FunctionName' \
    --output text 2>/dev/null | head -1)
if [ -z "$API_LAMBDA" ]; then
    echo "❌ API Lambda function not found"
else
    echo "✅ API Lambda: $API_LAMBDA"

    # Check last error
    echo ""
    echo "   Recent API Lambda errors:"
    aws logs tail "/aws/lambda/$API_LAMBDA" \
        --region $AWS_REGION \
        --since 1h \
        --max-items 10 \
        --format short 2>/dev/null || echo "   (No logs found in last hour)"
fi

# ============================================================
# 5. Check API Gateway
# ============================================================
echo ""
echo "5️⃣  Checking API Gateway..."
API_ENDPOINT=$(aws apigatewayv2 get-apis \
    --region $AWS_REGION \
    --query 'Items[0].ApiEndpoint' \
    --output text 2>/dev/null || echo "")
if [ -n "$API_ENDPOINT" ] && [ "$API_ENDPOINT" != "None" ]; then
    echo "✅ API Endpoint: $API_ENDPOINT"

    # Test health endpoint
    echo ""
    echo "   Testing /health endpoint..."
    HEALTH_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$API_ENDPOINT/health" 2>/dev/null || echo "000")
    echo "   Response code: $HEALTH_RESPONSE"

    if [ "$HEALTH_RESPONSE" == "200" ]; then
        echo "   ✅ Health endpoint responding"
    else
        echo "   ❌ Health endpoint not responding (got $HEALTH_RESPONSE)"
    fi
fi

# ============================================================
# 6. List available ECS task definitions
# ============================================================
echo ""
echo "6️⃣  Available ECS task definitions..."
aws ecs list-task-definition-families \
    --region $AWS_REGION \
    --status ACTIVE \
    --query 'taskDefinitionFamilies' \
    --output text 2>/dev/null | tr '\t' '\n' | head -20 | while read family; do
    if [ -n "$family" ]; then echo "   - $family"; fi
done

# ============================================================
# 7. List recent ECS task executions
# ============================================================
echo ""
echo "7️⃣  Recent ECS task executions..."
aws ecs list-tasks \
    --cluster $CLUSTER_NAME \
    --region $AWS_REGION \
    --query 'taskArns[0:5]' \
    --output text 2>/dev/null | while read task_arn; do
    if [ -n "$task_arn" ] && [ "$task_arn" != "None" ]; then
        echo "   Running: $(echo $task_arn | rev | cut -d/ -f1 | rev)"
    fi
done

# ============================================================
# 8. Check CloudWatch logs for loader activity
# ============================================================
echo ""
echo "8️⃣  Recent loader activity in CloudWatch..."
echo "   Looking for ECS loader logs from the last 24 hours..."
aws logs describe-log-groups \
    --log-group-name-prefix "/ecs/" \
    --region $AWS_REGION \
    --query 'logGroups[0:5].logGroupName' \
    --output text 2>/dev/null | tr '\t' '\n' | while read log_group; do
    if [ -n "$log_group" ] && [ "$log_group" != "None" ]; then
        echo ""
        echo "   📋 $log_group"
        aws logs tail "$log_group" \
            --region $AWS_REGION \
            --since 24h \
            --max-items 3 \
            --format short 2>/dev/null | head -5 || true
    fi
done

echo ""
echo "✨ Diagnostic complete!"
echo ""
echo "📚 Next steps:"
echo "   1. Deploy fix: git push origin main"
echo "   2. Monitor deployment: watch GitHub Actions"
echo "   3. Verify API: curl $API_ENDPOINT/health"
echo "   4. Test loader: aws logs tail /ecs/algo-* --follow"
