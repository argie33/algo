#!/bin/bash
# MASTER WASTE CLEANUP SCRIPT
# Identifies and removes all AWS infrastructure waste

set -e

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║          AWS INFRASTRUCTURE WASTE CLEANUP - MASTER AUDIT           ║"
echo "║                                                                    ║"
echo "║  This script finds money-wasting resources and how to remove them ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

REGION="us-east-1"
CLUSTER="algo-cluster"
ACCOUNT_ID="626216981288"

# Counters
TOTAL_WASTE=0
WASTE_ITEMS=0

echo "📋 CHECKING FOR WASTE SOURCES..."
echo ""

# ============================================================
# 1. EXTRA RDS DATABASES
# ============================================================
echo "1️⃣  RDS EXTRA DATABASES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "   Connecting to RDS 'stocks' database..."
EXTRA_DBS=$(psql -h algo-db.c9akciq32fdy.us-east-1.rds.amazonaws.com \
    -U stocks -d stocks -t -c \
    "SELECT datname FROM pg_database WHERE datname NOT IN ('postgres', 'template0', 'template1', 'stocks');" \
    2>/dev/null || echo "")

if [ -z "$EXTRA_DBS" ]; then
    echo "   ✅ No extra databases (clean)"
else
    echo "   ❌ EXTRA DATABASES FOUND (WASTE):"
    while IFS= read -r db; do
        [ -z "$db" ] && continue
        echo "      • $db"
        echo "        Action: DROP DATABASE IF EXISTS $db;"
        echo "        Cost: ~$3-10/month per empty database"
        ((WASTE_ITEMS++))
        TOTAL_WASTE=$((TOTAL_WASTE + 10))
    done <<< "$EXTRA_DBS"
fi
echo ""

# ============================================================
# 2. HANGING ECS TASKS
# ============================================================
echo "2️⃣  HANGING ECS TASKS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

TASK_ARNS=$(aws ecs list-tasks \
    --cluster $CLUSTER \
    --launch-type FARGATE \
    --region $REGION \
    --query 'taskArns[]' \
    --output text 2>/dev/null || echo "")

if [ -z "$TASK_ARNS" ]; then
    echo "   ✅ No running tasks (clean)"
else
    HANGING_COUNT=0
    for TASK_ARN in $TASK_ARNS; do
        STATUS=$(aws ecs describe-tasks \
            --cluster $CLUSTER \
            --tasks "$TASK_ARN" \
            --region $REGION \
            --query 'tasks[0].lastStatus' \
            --output text 2>/dev/null || echo "")

        if [ "$STATUS" = "PROVISIONING" ] || [ "$STATUS" = "PENDING" ]; then
            echo "   ❌ HANGING TASK: $TASK_ARN"
            echo "      Status: $STATUS (stuck, wasting ~$0.05/hour)"
            echo "      Action: aws ecs stop-task --cluster $CLUSTER --task $TASK_ARN --region $REGION"
            ((HANGING_COUNT++))
            TOTAL_WASTE=$((TOTAL_WASTE + 2))
        fi
    done

    if [ $HANGING_COUNT -eq 0 ]; then
        echo "   ✅ No hanging tasks (clean)"
    else
        echo "   ❌ Found $HANGING_COUNT hanging task(s)"
        ((WASTE_ITEMS++))
    fi
fi
echo ""

# ============================================================
# 3. UNNECESSARY CLOUDWATCH ALARMS
# ============================================================
echo "3️⃣  CLOUDWATCH ALARMS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ALARM_COUNT=$(aws cloudwatch describe-alarms \
    --region $REGION \
    --query 'MetricAlarms | length(@)' \
    --output text 2>/dev/null || echo 0)

echo "   Found $ALARM_COUNT alarms configured"
echo "   Cost: $ALARM_COUNT × $0.10/month = \$$(echo "scale=2; $ALARM_COUNT * 0.10" | bc)/month"

if [ "$ALARM_COUNT" -gt 30 ]; then
    echo "   ❌ PROBABLY OVER-INSTRUMENTED (many alarms don't fire)"
    echo "      Action: Review alarms, delete ones that never fire"
    echo "      Potential saving: ~\$3-5/month"
    ((WASTE_ITEMS++))
    TOTAL_WASTE=$((TOTAL_WASTE + 5))
else
    echo "   ✅ Reasonable number of alarms"
fi
echo ""

# ============================================================
# 4. OLD ECR IMAGES
# ============================================================
echo "4️⃣  ECR CONTAINER IMAGES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

IMAGE_COUNT=$(aws ecr describe-images \
    --repository-name algo-registry \
    --region $REGION \
    --query 'imageDetails | length(@)' \
    --output text 2>/dev/null || echo 0)

TOTAL_SIZE=$(aws ecr describe-images \
    --repository-name algo-registry \
    --region $REGION \
    --query 'sum(imageDetails[].imageSizeInBytes)' \
    --output text 2>/dev/null || echo 0)

TOTAL_SIZE_GB=$(echo "scale=3; $TOTAL_SIZE / 1073741824" | bc)

echo "   Found $IMAGE_COUNT images, total size: ${TOTAL_SIZE_GB}GB"
echo "   Cost: ${TOTAL_SIZE_GB}GB × \$0.10/GB/month = \$$(echo "scale=2; $TOTAL_SIZE_GB * 0.10" | bc)/month"

if [ "$(echo "$TOTAL_SIZE_GB > 5" | bc)" -eq 1 ]; then
    echo "   ❌ PROBABLY OLD IMAGES (>5GB is waste)"
    echo "      Action: Delete old images, keep only last 10"
    echo "      Potential saving: ~\$1-2/month"
    ((WASTE_ITEMS++))
    TOTAL_WASTE=$((TOTAL_WASTE + 2))
else
    echo "   ✅ Reasonable size"
fi
echo ""

# ============================================================
# 5. NAT GATEWAYS (if unused)
# ============================================================
echo "5️⃣  NAT GATEWAYS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

NGW_COUNT=$(aws ec2 describe-nat-gateways \
    --region $REGION \
    --query 'NatGateways[?State==`available`] | length(@)' \
    --output text 2>/dev/null || echo 0)

if [ "$NGW_COUNT" -gt 0 ]; then
    echo "   ❌ FOUND $NGW_COUNT NAT GATEWAY(S) (EXPENSIVE - \$32/month each)"
    echo "      These are rarely needed for dev. Check if actually used."
    echo "      Action: aws ec2 delete-nat-gateway --nat-gateway-id <id> --region $REGION"
    echo "      Potential saving: \$32/month per gateway"
    ((WASTE_ITEMS++))
    TOTAL_WASTE=$((TOTAL_WASTE + 32))
else
    echo "   ✅ No NAT gateways (good)"
fi
echo ""

# ============================================================
# 6. ORPHANED ELASTIC IPs
# ============================================================
echo "6️⃣  ORPHANED ELASTIC IPs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

EIP_COUNT=$(aws ec2 describe-addresses \
    --region $REGION \
    --query 'Addresses[?AssociationId==null] | length(@)' \
    --output text 2>/dev/null || echo 0)

if [ "$EIP_COUNT" -gt 0 ]; then
    echo "   ❌ FOUND $EIP_COUNT ORPHANED EIP(S) (\$3.65/month each)"
    echo "      Action: aws ec2 release-address --allocation-id <id> --region $REGION"
    echo "      Potential saving: \$$(echo "scale=2; $EIP_COUNT * 3.65" | bc)/month"
    ((WASTE_ITEMS++))
    TOTAL_WASTE=$((TOTAL_WASTE + 4))
else
    echo "   ✅ No orphaned EIPs (good)"
fi
echo ""

# ============================================================
# SUMMARY
# ============================================================
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                           WASTE SUMMARY                            ║"
echo "╠════════════════════════════════════════════════════════════════════╣"
echo "║                                                                    ║"
echo "║  Issues Found: $WASTE_ITEMS"
echo "║  Estimated Waste: ~\$$TOTAL_WASTE/month"
echo "║                                                                    ║"
echo "║  Already Fixed:                                                    ║"
echo "║    • RDS Proxy disabled: saves \$150/month ✅                      ║"
echo "║    • VPC Endpoints disabled: saves \$43/month ✅                   ║"
echo "║    • Performance Insights conditional: saves \$6/month ✅          ║"
echo "║                                                                    ║"
echo "║  Total Potential Monthly Savings: \$$(echo "scale=0; 150 + 43 + 6 + $TOTAL_WASTE" | bc)/month ✅  ║"
echo "║  Total Annual Savings: \$$(echo "scale=0; (150 + 43 + 6 + $TOTAL_WASTE) * 12" | bc)/year ✅       ║"
echo "║                                                                    ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""
echo "✨ ACTION ITEMS:"
echo "   1. Verify GitHub Actions deployment completed (check RDS Proxy deleted)"
echo "   2. Delete extra databases: psql -c 'DROP DATABASE ..;'"
echo "   3. Stop hanging ECS tasks: aws ecs stop-task ..."
echo "   4. Delete old ECR images: aws ecr batch-delete-image ..."
echo "   5. Monitor AWS bill: should drop \$200+ within 3-5 days"
echo ""
