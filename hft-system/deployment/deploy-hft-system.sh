#!/bin/bash

# HFT System Deployment Script for AWS
# Optimized for ultra-low latency trading

set -e  # Exit on any error

# Configuration
ENVIRONMENT=${1:-staging}
REGION=${2:-us-east-1}
STACK_NAME="hft-system-${ENVIRONMENT}"
TEMPLATE_FILE="cloudformation-hft-infrastructure.yml"
KEY_PAIR_NAME=${3:-"hft-key-pair"}
ALERT_EMAIL=${4:-"alerts@yourcompany.com"}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}HFT System Deployment Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Environment: ${GREEN}${ENVIRONMENT}${NC}"
echo -e "Region: ${GREEN}${REGION}${NC}"
echo -e "Stack Name: ${GREEN}${STACK_NAME}${NC}"
echo ""

# Validate AWS CLI and credentials
echo -e "${YELLOW}Validating AWS CLI and credentials...${NC}"
if ! command -v aws &> /dev/null; then
    echo -e "${RED}ERROR: AWS CLI not found. Please install AWS CLI.${NC}"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}ERROR: AWS credentials not configured or invalid.${NC}"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "AWS Account ID: ${GREEN}${ACCOUNT_ID}${NC}"

# Check if key pair exists
echo -e "${YELLOW}Checking EC2 key pair...${NC}"
if ! aws ec2 describe-key-pairs --key-names "${KEY_PAIR_NAME}" --region "${REGION}" &> /dev/null; then
    echo -e "${RED}ERROR: Key pair '${KEY_PAIR_NAME}' not found in ${REGION}.${NC}"
    echo -e "Please create the key pair first:"
    echo -e "aws ec2 create-key-pair --key-name ${KEY_PAIR_NAME} --region ${REGION}"
    exit 1
fi

# Validate CloudFormation template
echo -e "${YELLOW}Validating CloudFormation template...${NC}"
if aws cloudformation validate-template --template-body file://${TEMPLATE_FILE} --region "${REGION}" &> /dev/null; then
    echo -e "${GREEN}✓ Template is valid${NC}"
else
    echo -e "${RED}ERROR: CloudFormation template validation failed.${NC}"
    exit 1
fi

# Check if stack already exists
echo -e "${YELLOW}Checking if stack exists...${NC}"
if aws cloudformation describe-stacks --stack-name "${STACK_NAME}" --region "${REGION}" &> /dev/null; then
    echo -e "${YELLOW}Stack '${STACK_NAME}' already exists. Updating...${NC}"
    OPERATION="update-stack"
    WAIT_CONDITION="stack-update-complete"
else
    echo -e "${GREEN}Creating new stack '${STACK_NAME}'...${NC}"
    OPERATION="create-stack"
    WAIT_CONDITION="stack-create-complete"
fi

# Deploy CloudFormation stack
echo -e "${YELLOW}Deploying CloudFormation stack...${NC}"

CHANGESET_NAME="hft-changeset-$(date +%s)"

if [ "$OPERATION" = "update-stack" ]; then
    # Create change set for updates
    aws cloudformation create-change-set \
        --stack-name "${STACK_NAME}" \
        --change-set-name "${CHANGESET_NAME}" \
        --template-body file://${TEMPLATE_FILE} \
        --parameters \
            ParameterKey=Environment,ParameterValue=${ENVIRONMENT} \
            ParameterKey=KeyPairName,ParameterValue=${KEY_PAIR_NAME} \
            ParameterKey=AlertEmail,ParameterValue=${ALERT_EMAIL} \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "${REGION}"
    
    echo -e "${YELLOW}Waiting for change set to be created...${NC}"
    aws cloudformation wait change-set-create-complete \
        --stack-name "${STACK_NAME}" \
        --change-set-name "${CHANGESET_NAME}" \
        --region "${REGION}"
    
    # Show changes
    echo -e "${YELLOW}Change set summary:${NC}"
    aws cloudformation describe-change-set \
        --stack-name "${STACK_NAME}" \
        --change-set-name "${CHANGESET_NAME}" \
        --region "${REGION}" \
        --query 'Changes[*].[Action,ResourceChange.ResourceType,ResourceChange.LogicalResourceId]' \
        --output table
    
    # Execute change set
    read -p "Execute change set? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        aws cloudformation execute-change-set \
            --stack-name "${STACK_NAME}" \
            --change-set-name "${CHANGESET_NAME}" \
            --region "${REGION}"
    else
        echo -e "${YELLOW}Change set not executed. Cleaning up...${NC}"
        aws cloudformation delete-change-set \
            --stack-name "${STACK_NAME}" \
            --change-set-name "${CHANGESET_NAME}" \
            --region "${REGION}"
        exit 0
    fi
else
    # Create new stack
    aws cloudformation create-stack \
        --stack-name "${STACK_NAME}" \
        --template-body file://${TEMPLATE_FILE} \
        --parameters \
            ParameterKey=Environment,ParameterValue=${ENVIRONMENT} \
            ParameterKey=KeyPairName,ParameterValue=${KEY_PAIR_NAME} \
            ParameterKey=AlertEmail,ParameterValue=${ALERT_EMAIL} \
        --capabilities CAPABILITY_NAMED_IAM \
        --enable-termination-protection \
        --region "${REGION}" \
        --tags \
            Key=Environment,Value=${ENVIRONMENT} \
            Key=Project,Value=HFT-System \
            Key=Owner,Value=TradingTeam \
            Key=CostCenter,Value=Trading
fi

# Wait for stack operation to complete
echo -e "${YELLOW}Waiting for stack operation to complete...${NC}"
echo -e "This may take 10-15 minutes..."

aws cloudformation wait ${WAIT_CONDITION} \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Stack operation completed successfully!${NC}"
else
    echo -e "${RED}ERROR: Stack operation failed or timed out.${NC}"
    
    # Show stack events for debugging
    echo -e "${YELLOW}Recent stack events:${NC}"
    aws cloudformation describe-stack-events \
        --stack-name "${STACK_NAME}" \
        --region "${REGION}" \
        --query 'StackEvents[0:10].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]' \
        --output table
    exit 1
fi

# Get stack outputs
echo -e "${YELLOW}Retrieving stack outputs...${NC}"
OUTPUTS=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query 'Stacks[0].Outputs')

echo -e "${GREEN}Stack outputs:${NC}"
echo "${OUTPUTS}" | jq -r '.[] | "\(.OutputKey): \(.OutputValue)"'

# Save outputs to configuration file
CONFIG_FILE="hft-${ENVIRONMENT}-config.json"
echo "${OUTPUTS}" > "${CONFIG_FILE}"
echo -e "${GREEN}✓ Configuration saved to ${CONFIG_FILE}${NC}"

# Setup post-deployment tasks
echo -e "${YELLOW}Setting up post-deployment configurations...${NC}"

# 1. Setup CloudWatch agent on EC2 instances (if needed)
echo -e "${YELLOW}Installing CloudWatch agent...${NC}"

# 2. Configure database schemas
DB_ENDPOINT=$(echo "${OUTPUTS}" | jq -r '.[] | select(.OutputKey=="DatabaseEndpoint") | .OutputValue')
if [ ! -z "$DB_ENDPOINT" ] && [ "$DB_ENDPOINT" != "null" ]; then
    echo -e "Database endpoint: ${GREEN}${DB_ENDPOINT}${NC}"
    
    # Note: In production, you would run database migrations here
    echo -e "${YELLOW}Note: Run database migrations manually after deployment${NC}"
fi

# 3. Setup monitoring dashboards
echo -e "${YELLOW}Setting up enhanced monitoring...${NC}"

# Create custom CloudWatch dashboard
DASHBOARD_BODY=$(cat << 'EOF'
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["HFT/Trading", "SignalsGenerated", {"stat": "Sum"}],
          [".", "OrdersSent", {"stat": "Sum"}],
          [".", "OrdersFilled", {"stat": "Sum"}],
          [".", "AverageLatency", {"stat": "Average"}]
        ],
        "period": 60,
        "stat": "Sum",
        "region": "us-east-1",
        "title": "Trading Performance",
        "view": "timeSeries"
      }
    },
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["HFT/Risk", "RiskChecksPerformed", {"stat": "Sum"}],
          [".", "RiskChecksFailed", {"stat": "Sum"}],
          [".", "GrossExposure", {"stat": "Average"}],
          [".", "NetExposure", {"stat": "Average"}]
        ],
        "period": 60,
        "stat": "Average",
        "region": "us-east-1",
        "title": "Risk Management",
        "view": "timeSeries"
      }
    },
    {
      "type": "log",
      "properties": {
        "query": "SOURCE '/aws/ec2/hft' | fields @timestamp, @message\n| filter @message like /ERROR/\n| sort @timestamp desc\n| limit 100",
        "region": "us-east-1",
        "title": "Recent Errors",
        "view": "table"
      }
    }
  ]
}
EOF
)

aws cloudwatch put-dashboard \
    --dashboard-name "HFT-System-${ENVIRONMENT}" \
    --dashboard-body "${DASHBOARD_BODY}" \
    --region "${REGION}"

# 4. Create parameter store entries for configuration
echo -e "${YELLOW}Setting up Parameter Store configurations...${NC}"

aws ssm put-parameter \
    --name "/hft/${ENVIRONMENT}/database/endpoint" \
    --value "${DB_ENDPOINT}" \
    --type "String" \
    --description "HFT Database Endpoint" \
    --region "${REGION}" \
    --overwrite 2>/dev/null || echo "Parameter may already exist"

# Redis endpoint
REDIS_ENDPOINT=$(echo "${OUTPUTS}" | jq -r '.[] | select(.OutputKey=="RedisEndpoint") | .OutputValue')
if [ ! -z "$REDIS_ENDPOINT" ] && [ "$REDIS_ENDPOINT" != "null" ]; then
    aws ssm put-parameter \
        --name "/hft/${ENVIRONMENT}/redis/endpoint" \
        --value "${REDIS_ENDPOINT}" \
        --type "String" \
        --description "HFT Redis Endpoint" \
        --region "${REGION}" \
        --overwrite 2>/dev/null || echo "Parameter may already exist"
fi

# Market data stream
KINESIS_STREAM=$(echo "${OUTPUTS}" | jq -r '.[] | select(.OutputKey=="MarketDataStreamName") | .OutputValue')
if [ ! -z "$KINESIS_STREAM" ] && [ "$KINESIS_STREAM" != "null" ]; then
    aws ssm put-parameter \
        --name "/hft/${ENVIRONMENT}/kinesis/stream" \
        --value "${KINESIS_STREAM}" \
        --type "String" \
        --description "HFT Market Data Stream" \
        --region "${REGION}" \
        --overwrite 2>/dev/null || echo "Parameter may already exist"
fi

# 5. Setup initial alarms
echo -e "${YELLOW}Setting up additional CloudWatch alarms...${NC}"

# CPU utilization alarm for trading servers
aws cloudwatch put-metric-alarm \
    --alarm-name "HFT-Trading-High-CPU-${ENVIRONMENT}" \
    --alarm-description "High CPU utilization on trading servers" \
    --metric-name "CPUUtilization" \
    --namespace "AWS/EC2" \
    --statistic "Average" \
    --period 300 \
    --threshold 80 \
    --comparison-operator "GreaterThanThreshold" \
    --evaluation-periods 2 \
    --alarm-actions "$(echo "${OUTPUTS}" | jq -r '.[] | select(.OutputKey=="AlertsTopicArn") | .OutputValue')" \
    --region "${REGION}"

# Memory utilization alarm
aws cloudwatch put-metric-alarm \
    --alarm-name "HFT-Trading-High-Memory-${ENVIRONMENT}" \
    --alarm-description "High memory utilization on trading servers" \
    --metric-name "MemoryUtilization" \
    --namespace "CWAgent" \
    --statistic "Average" \
    --period 300 \
    --threshold 85 \
    --comparison-operator "GreaterThanThreshold" \
    --evaluation-periods 2 \
    --alarm-actions "$(echo "${OUTPUTS}" | jq -r '.[] | select(.OutputKey=="AlertsTopicArn") | .OutputValue')" \
    --region "${REGION}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}HFT System Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "1. Configure trading servers with application code"
echo -e "2. Set up market data feeds and connectivity"
echo -e "3. Run database migrations"
echo -e "4. Configure monitoring and alerting"
echo -e "5. Perform system testing and validation"
echo ""
echo -e "${YELLOW}Important Files:${NC}"
echo -e "- Configuration: ${GREEN}${CONFIG_FILE}${NC}"
echo -e "- CloudFormation Template: ${GREEN}${TEMPLATE_FILE}${NC}"
echo ""
echo -e "${YELLOW}Monitoring:${NC}"
echo -e "- CloudWatch Dashboard: HFT-System-${ENVIRONMENT}"
echo -e "- Log Groups: /aws/ec2/hft, /aws/lambda/hft"
echo ""
echo -e "${BLUE}For support, contact the Trading Technology team.${NC}"