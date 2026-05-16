#!/bin/bash
# Quick AWS verification commands
# Usage: source aws-verify-quick.sh

PROFILE="algo-dev"
REGION="us-east-1"

echo "=========================================="
echo "AWS VERIFICATION COMMANDS"
echo "=========================================="
echo ""
echo "Data Verification (Local + AWS):"
echo ""

echo "1. LOCAL DATABASE STATUS:"
echo "   python3 -c 'import psycopg2; conn = psycopg2.connect(host=\"localhost\", user=\"postgres\", password=\"...\", dbname=\"stocks\"); cur = conn.cursor(); cur.execute(\"SELECT COUNT(*) FROM stock_symbols\"); print(f\"Stock symbols: {cur.fetchone()[0]}\")'"
echo ""

echo "2. AWS RDS STATUS:"
echo "   aws rds describe-db-instances --region $REGION --profile $PROFILE --query 'DBInstances[*].[DBInstanceIdentifier,DBInstanceStatus,Engine]' --output table"
echo ""

echo "3. RDS ENDPOINT:"
echo "   aws rds describe-db-instances --region $REGION --profile $PROFILE --query 'DBInstances[0].Endpoint.Address' --output text"
echo ""

echo "4. RDS CREDENTIALS (from Secrets Manager):"
echo "   aws secretsmanager get-secret-value --secret-id algo-rds-credentials --region $REGION --profile $PROFILE --query 'SecretString' --output text | jq ."
echo ""

echo "5. CONNECT TO RDS:"
echo "   psql -h <endpoint-from-step-3> -U postgres -d stocks"
echo ""

echo "6. AWS LAMBDA FUNCTIONS:"
echo "   aws lambda list-functions --region $REGION --profile $PROFILE --query 'Functions[*].[FunctionName,Runtime]' --output table"
echo ""

echo "7. EVENT BRIDGE SCHEDULES:"
echo "   aws scheduler list-schedules --region $REGION --profile $PROFILE --query 'Schedules[*].[Name,Schedule,State]' --output table"
echo ""

echo "=========================================="
echo ""
echo "SETUP FIRST:"
echo "  1. Create access key for algo-developer user (AWS Console)"
echo "  2. aws configure --profile algo-dev"
echo "  3. Run commands above with --profile algo-dev"
echo ""
echo "See AWS_CLI_SETUP.md for detailed instructions"
echo ""
