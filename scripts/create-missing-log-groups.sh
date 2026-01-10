#!/bin/bash
# Create missing CloudWatch log groups for ECS tasks
# This ensures all loader tasks have proper logging before they run

set -e

REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID="${AWS_ACCOUNT_ID:-626216981288}"

echo "Setting up CloudWatch log groups in region: $REGION"

# Define loader names and their corresponding log groups
declare -a LOADERS=(
    "loadstockscores"
    "loadpricedaily"
    "loadpriceweekly"
    "loadpricemonthly"
    "loadetfpricedaily"
    "loadetfpriceweekly"
    "loadetfpricemonthly"
    "loadbuyselldaily"
    "loadbuysellweekly"
    "loadbuysellmonthly"
    "loadbuysell_etf_daily"
    "loadbuysell_etf_weekly"
    "loadbuysell_etf_monthly"
    "loaddailycompanydata"
    "loadannualcashflow"
    "loadannualincomestatement"
    "loadannualbalancesheet"
    "loadquarterlycashflow"
    "loadquarterlyincomestatement"
    "loadquarterlybalancesheet"
    "loadfactormetrics"
    "loadbenchmark"
    "loadmarket"
    "loadecondata"
    "loadfeargreed"
    "loadaaiidata"
    "loadnaaim"
    "loadanalystsentiment"
    "loadanalystupgradedowngrade"
    "loadearningshistory"
    "loadttmcashflow"
    "loadttmincomestatement"
)

# Create log group if it doesn't exist
create_log_group() {
    local log_group="/ecs/algo-$1"

    echo "Checking log group: $log_group"

    if aws logs describe-log-groups \
        --log-group-name-prefix "$log_group" \
        --region "$REGION" 2>/dev/null | grep -q "$log_group"; then
        echo "✓ Log group exists: $log_group"
    else
        echo "Creating log group: $log_group"
        aws logs create-log-group \
            --log-group-name "$log_group" \
            --region "$REGION" || echo "Log group may already exist or error creating"

        # Set retention policy (30 days)
        aws logs put-retention-policy \
            --log-group-name "$log_group" \
            --retention-in-days 30 \
            --region "$REGION" || echo "Could not set retention policy"
    fi
}

# Create log groups for each loader
for loader in "${LOADERS[@]}"; do
    create_log_group "$loader" || echo "Warning: Failed to create log group for $loader"
done

echo "✅ CloudWatch log groups setup complete"
