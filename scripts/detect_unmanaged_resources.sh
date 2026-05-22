#!/bin/bash
# Continuous detection and alerting for unmanaged AWS resources
# Run as CloudWatch Event rule every 6 hours or on-demand via Lambda

set -e

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
SLACK_WEBHOOK=${SLACK_WEBHOOK_URL:-""}
EMAIL=${NOTIFICATION_EMAIL:-"argeropolos@gmail.com"}

echo "[$(date)] Starting unmanaged resource detection..."

# ==============================================================================
# Function: Check for unmanaged S3 buckets
# ==============================================================================
check_s3_buckets() {
    echo "[S3] Checking for unmanaged buckets..."

    UNMANAGED=$(aws s3api list-buckets \
        --query 'Buckets[].Name' \
        --output text | tr '\t' '\n' | sort)

    # Expected managed buckets (from Terraform state)
    MANAGED_BUCKETS=(
        "algo-cloudtrail-logs-us-east-1-626216981288"
        "algo-code-626216981288"
        "algo-config-bucket-626216981288"
        "algo-data-loading-626216981288"
        "algo-frontend-626216981288"
        "algo-lambda-artifacts-626216981288"
        "algo-log-archive-626216981288"
        "stocks-terraform-state"
    )

    FOUND_UNMANAGED=0
    for bucket in $UNMANAGED; do
        if [[ ! " ${MANAGED_BUCKETS[@]} " =~ " ${bucket} " ]]; then
            echo "  [ALERT] Unmanaged S3 bucket: $bucket"
            FOUND_UNMANAGED=1
        fi
    done

    return $FOUND_UNMANAGED
}

# ==============================================================================
# Function: Check for unmanaged Lambda functions
# ==============================================================================
check_lambda_functions() {
    echo "[Lambda] Checking for unmanaged functions..."

    FUNCTIONS=$(aws lambda list-functions \
        --region $REGION \
        --query 'Functions[].FunctionName' \
        --output text | tr '\t' '\n' | sort)

    # Expected managed functions
    MANAGED_FUNCTIONS=(
        "algo-algo-dev"
        "algo-api-dev"
        "algo-data-freshness-monitor-dev"
        "algo-execution-monitor-dev"
        "algo-rds-rotation-dev"
    )

    FOUND_UNMANAGED=0
    for func in $FUNCTIONS; do
        if [[ ! " ${MANAGED_FUNCTIONS[@]} " =~ " ${func} " ]]; then
            echo "  [ALERT] Unmanaged Lambda: $func"
            FOUND_UNMANAGED=1
        fi
    done

    return $FOUND_UNMANAGED
}

# ==============================================================================
# Function: Check for unmanaged RDS instances
# ==============================================================================
check_rds_instances() {
    echo "[RDS] Checking for unmanaged instances..."

    INSTANCES=$(aws rds describe-db-instances \
        --region $REGION \
        --query 'DBInstances[].DBInstanceIdentifier' \
        --output text | tr '\t' '\n' | sort)

    # Expected managed instances
    MANAGED_INSTANCES=(
        "algo-db"
    )

    FOUND_UNMANAGED=0
    for instance in $INSTANCES; do
        if [[ ! " ${MANAGED_INSTANCES[@]} " =~ " ${instance} " ]]; then
            # Check if it has the terraform tag
            TAGS=$(aws rds list-tags-for-resource \
                --resource-name "arn:aws:rds:$REGION:$ACCOUNT_ID:db:$instance" \
                --query 'TagList[?Key==`terraform`].Value' \
                --output text 2>/dev/null || echo "")

            if [ -z "$TAGS" ] || [ "$TAGS" != "managed" ]; then
                echo "  [ALERT] Unmanaged RDS: $instance"
                FOUND_UNMANAGED=1
            fi
        fi
    done

    return $FOUND_UNMANAGED
}

# ==============================================================================
# Function: Check for unmanaged ECS clusters
# ==============================================================================
check_ecs_clusters() {
    echo "[ECS] Checking for unmanaged clusters..."

    CLUSTERS=$(aws ecs list-clusters \
        --region $REGION \
        --query 'clusterArns[]' \
        --output text | xargs -n1 basename | sort)

    # Expected managed clusters
    MANAGED_CLUSTERS=(
        "algo-cluster"
    )

    FOUND_UNMANAGED=0
    for cluster in $CLUSTERS; do
        if [[ ! " ${MANAGED_CLUSTERS[@]} " =~ " ${cluster} " ]]; then
            # Skip AWS Batch temporary clusters
            if [[ ! $cluster =~ ^terraform- ]]; then
                echo "  [ALERT] Unmanaged ECS cluster: $cluster"
                FOUND_UNMANAGED=1
            fi
        fi
    done

    return $FOUND_UNMANAGED
}

# ==============================================================================
# Function: Send alert to Slack and/or email
# ==============================================================================
send_alert() {
    local message=$1

    if [ -n "$SLACK_WEBHOOK" ]; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"$message\"}" \
            "$SLACK_WEBHOOK" 2>/dev/null || true
    fi

    if [ -n "$EMAIL" ]; then
        echo "$message" | mail -s "AWS: Unmanaged Resources Detected" "$EMAIL" || true
    fi
}

# ==============================================================================
# Main execution
# ==============================================================================
UNMANAGED_FOUND=0

check_s3_buckets || UNMANAGED_FOUND=1
check_lambda_functions || UNMANAGED_FOUND=1
check_rds_instances || UNMANAGED_FOUND=1
check_ecs_clusters || UNMANAGED_FOUND=1

if [ $UNMANAGED_FOUND -eq 1 ]; then
    echo ""
    echo "[ERROR] Unmanaged resources detected!"
    send_alert "[AWS] ALERT: Unmanaged resources detected in account $ACCOUNT_ID. Check logs for details."
    exit 1
else
    echo "[OK] All AWS resources are Terraform-managed."
    exit 0
fi
