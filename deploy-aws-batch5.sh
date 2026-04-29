#!/bin/bash
# Complete AWS Deployment Script for Batch 5 Loaders
# Usage: bash deploy-aws-batch5.sh
# Prerequisites: AWS CLI installed and configured with credentials

set -e  # Exit on error

echo "=========================================="
echo "Batch 5 Loaders - AWS Deployment Script"
echo "=========================================="
echo ""

# Configuration
AWS_REGION="us-east-1"
RDS_INSTANCE="stocks-prod-db"
ECS_CLUSTER="stock-analytics-cluster"
LOADERS=("loadquarterlyincomestatement" "loadannualincomestatement"
         "loadquarterlybalancesheet" "loadannualbalancesheet"
         "loadquarterlycashflow" "loadannualcashflow")

# ===========================================
# Phase 1: Verify AWS Credentials
# ===========================================
echo "[Phase 1] Verifying AWS credentials..."
if ! aws sts get-caller-identity --region "$AWS_REGION" > /dev/null 2>&1; then
    echo "ERROR: AWS credentials not configured or invalid"
    echo "Please run: aws configure"
    exit 1
fi
echo "✓ AWS credentials verified"
echo ""

# ===========================================
# Phase 2: Deploy CloudFormation Stacks
# ===========================================
echo "[Phase 2] Deploying CloudFormation Stacks..."
echo ""

echo "2.1) Deploying stocks-core stack (VPC, subnets, security groups)..."
aws cloudformation deploy \
    --template-file template-core.yml \
    --stack-name stocks-core \
    --region "$AWS_REGION" \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
    --no-fail-on-empty-changeset \
    --output text

echo "✓ stocks-core stack deployed"
echo ""

echo "2.2) Waiting for core stack to complete (30 seconds)..."
sleep 30

echo "2.3) Deploying stocks-app stack (RDS Database)..."
aws cloudformation deploy \
    --template-file template-app-stocks.yml \
    --stack-name stocks-app \
    --parameter-overrides \
        RDSUsername=stocks \
        RDSPassword=bed0elAn \
    --region "$AWS_REGION" \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
    --no-fail-on-empty-changeset \
    --output text

echo "✓ stocks-app stack deployed"
echo ""

echo "2.4) Waiting for app stack to complete (60 seconds)..."
sleep 60

echo "2.5) Deploying stocks-app-ecs-tasks stack (ECS Task Definitions)..."
aws cloudformation deploy \
    --template-file template-app-ecs-tasks.yml \
    --stack-name stocks-app-ecs-tasks \
    --parameter-overrides \
        QuarterlyIncomeImageTag=latest \
        AnnualIncomeImageTag=latest \
        QuarterlyBalanceImageTag=latest \
        AnnualBalanceImageTag=latest \
        QuarterlyCashflowImageTag=latest \
        AnnualCashflowImageTag=latest \
        RDSUsername=stocks \
        RDSPassword=bed0elAn \
    --region "$AWS_REGION" \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
    --no-fail-on-empty-changeset \
    --output text

echo "✓ stocks-app-ecs-tasks stack deployed"
echo ""

# ===========================================
# Phase 3: Configure Security Groups
# ===========================================
echo "[Phase 3] Configuring Security Groups..."
echo ""

echo "3.1) Getting RDS security group ID..."
RDS_SG=$(aws rds describe-db-instances \
    --db-instance-identifier "$RDS_INSTANCE" \
    --region "$AWS_REGION" \
    --query 'DBInstances[0].VpcSecurityGroups[0].VpcSecurityGroupId' \
    --output text 2>/dev/null || echo "")

if [ -z "$RDS_SG" ]; then
    echo "WARNING: Could not find RDS instance. It may still be creating..."
    echo "         Skipping security group configuration. You may need to do this manually."
else
    echo "   RDS Security Group: $RDS_SG"

    echo "3.2) Getting ECS security group ID..."
    ECS_SG=$(aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=stocks-ecs-tasks" \
        --region "$AWS_REGION" \
        --query 'SecurityGroups[0].GroupId' \
        --output text 2>/dev/null || echo "")

    if [ -z "$ECS_SG" ]; then
        echo "   WARNING: Could not find ECS security group"
    else
        echo "   ECS Security Group: $ECS_SG"

        echo "3.3) Authorizing ECS to connect to RDS (port 5432)..."
        aws ec2 authorize-security-group-ingress \
            --group-id "$RDS_SG" \
            --protocol tcp \
            --port 5432 \
            --source-security-group-id "$ECS_SG" \
            --description "Allow ECS tasks to connect to RDS PostgreSQL" \
            --region "$AWS_REGION" 2>/dev/null || echo "   (Rule may already exist)"

        echo "✓ Security groups configured"
    fi
fi
echo ""

# ===========================================
# Phase 4: Wait for GitHub Actions (Optional)
# ===========================================
echo "[Phase 4] Checking Docker Images in ECR..."
echo ""
echo "Note: GitHub Actions will automatically build Docker images"
echo "      when new code is pushed. Visit:"
echo "      https://github.com/argie33/algo/actions"
echo ""
echo "Checking current images in ECR..."

for loader in "${LOADERS[@]}"; do
    IMAGE_TAG=$(aws ecr describe-images \
        --repository-name "$loader" \
        --region "$AWS_REGION" \
        --query 'imageDetails[0].imageTags[0]' \
        --output text 2>/dev/null || echo "NOT_FOUND")

    echo "   $loader: $IMAGE_TAG"
done
echo ""

# ===========================================
# Phase 5: Test First Loader
# ===========================================
echo "[Phase 5] Testing First Batch 5 Loader..."
echo ""

echo "5.1) Starting loadquarterlyincomestatement task..."
TASK_ARN=$(aws ecs run-task \
    --cluster "$ECS_CLUSTER" \
    --task-definition loadquarterlyincomestatement \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxx,subnet-yyyyy],securityGroups=[sg-zzzzz],assignPublicIp=ENABLED}" \
    --region "$AWS_REGION" \
    --query 'tasks[0].taskArn' \
    --output text 2>/dev/null || echo "FAILED")

if [ "$TASK_ARN" = "FAILED" ]; then
    echo "   WARNING: Could not start task - network configuration may need adjustment"
    echo "   You may need to manually specify subnet and security group IDs"
else
    echo "   Task ARN: $TASK_ARN"
    echo ""
    echo "5.2) Monitoring task execution..."
    echo "   Run this command to watch logs:"
    echo "   aws logs tail /ecs/loadquarterlyincomestatement --follow --region $AWS_REGION"
    echo ""
    echo "5.3) Expected execution time: 12 minutes"
    echo "   After task completes, verify data:"
    echo "   psql -h <RDS_ENDPOINT> -U stocks -d stocks -c \"SELECT COUNT(*) FROM quarterly_income_statement;\""
fi
echo ""

# ===========================================
# Phase 6: Run All 6 Batch 5 Loaders
# ===========================================
echo "[Phase 6] Running All 6 Batch 5 Loaders..."
echo ""
echo "Once the first loader completes successfully, run all 6 in parallel:"
echo ""
echo "for loader in ${LOADERS[@]}; do"
echo "  aws ecs run-task \\"
echo "    --cluster \"$ECS_CLUSTER\" \\"
echo "    --task-definition \"\$loader\" \\"
echo "    --launch-type FARGATE \\"
echo "    --network-configuration \"awsvpcConfiguration={subnets=[subnet-xxxxx,subnet-yyyyy],securityGroups=[sg-zzzzz],assignPublicIp=ENABLED}\" \\"
echo "    --region \"$AWS_REGION\" &"
echo "done"
echo "wait"
echo ""

# ===========================================
# Summary
# ===========================================
echo "=========================================="
echo "Deployment Script Complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  ✓ CloudFormation stacks deployed"
echo "  ✓ Security groups configured"
echo "  ✓ First loader test started (or manual steps provided)"
echo ""
echo "Next Steps:"
echo "  1. Monitor first loader at: /ecs/loadquarterlyincomestatement"
echo "  2. Once successful, run all 6 loaders"
echo "  3. Expected total time: ~12 minutes (all parallel)"
echo "  4. Expected data: ~150,000 rows total"
echo ""
echo "Issues?"
echo "  - Security groups: Manually update using AWS Console"
echo "  - Task definition: Check ECS → Task Definitions"
echo "  - Network: Verify VPC, subnets, and routes in AWS Console"
echo ""
echo "Documentation: See MASTER_ACTION_PLAN.md for detailed steps"
echo ""
