#!/bin/bash
# Complete Credential Pipeline Verification
# Checks all three layers: Local → GitHub → AWS

set -e

echo "========================================================================"
echo "COMPLETE CREDENTIAL PIPELINE VERIFICATION"
echo "========================================================================"
echo ""

PASSED=0
FAILED=0
WARNED=0

# Test 1: PowerShell Profile (Local)
echo "[TEST 1] Local Development - PowerShell Environment"
echo "------------------------------------------------------------------------"

if [ -z "$DB_HOST" ]; then
    echo "[ERROR] DB_HOST not set in environment"
    ((FAILED++))
else
    echo "[OK] DB_HOST = $DB_HOST"
    ((PASSED++))
fi

if [ -z "$DB_PASSWORD" ]; then
    echo "[ERROR] DB_PASSWORD not set in environment"
    ((FAILED++))
else
    echo "[OK] DB_PASSWORD is set"
    ((PASSED++))
fi

if [ -z "$DB_USER" ]; then
    echo "[WARN] DB_USER not set (using default: stocks)"
    ((WARNED++))
else
    echo "[OK] DB_USER = $DB_USER"
    ((PASSED++))
fi

echo ""

# Test 2: Python Credential Pipeline
echo "[TEST 2] Python Credential Pipeline"
echo "------------------------------------------------------------------------"

if command -v python3 &> /dev/null; then
    echo "[INFO] Testing credential manager..."
    if python3 -c "
from config.credential_manager import get_credential_manager
cm = get_credential_manager()
db = cm.get_db_credentials()
print(f'[OK] Credentials loaded: {db[\"user\"]}@{db[\"host\"]}')
" 2>/dev/null; then
        ((PASSED++))
    else
        echo "[ERROR] Credential manager failed"
        ((FAILED++))
    fi
else
    echo "[WARN] Python3 not found - skipping credential manager test"
    ((WARNED++))
fi

echo ""

# Test 3: GitHub Secrets
echo "[TEST 3] GitHub Secrets Configuration"
echo "------------------------------------------------------------------------"

if ! command -v gh &> /dev/null; then
    echo "[WARN] gh CLI not installed - cannot verify GitHub Secrets"
    ((WARNED++))
elif ! gh auth status &> /dev/null; then
    echo "[WARN] gh CLI not authenticated - cannot verify GitHub Secrets"
    ((WARNED++))
else
    echo "[INFO] Checking GitHub Secrets..."

    SECRETS=$(gh secret list 2>/dev/null || echo "")

    required_secrets=("AWS_ACCOUNT_ID" "API_GATEWAY_URL" "DB_SECRET_ARN" "COGNITO_USER_POOL_ID" "COGNITO_CLIENT_ID")

    for secret in "${required_secrets[@]}"; do
        if echo "$SECRETS" | grep -q "$secret"; then
            echo "[OK] $secret is set"
            ((PASSED++))
        else
            echo "[ERROR] $secret is not set"
            ((FAILED++))
        fi
    done
fi

echo ""

# Test 4: AWS Secrets Manager
echo "[TEST 4] AWS Secrets Manager"
echo "------------------------------------------------------------------------"

if ! command -v aws &> /dev/null; then
    echo "[WARN] AWS CLI not installed - cannot verify AWS Secrets"
    ((WARNED++))
elif ! aws sts get-caller-identity &> /dev/null; then
    echo "[WARN] AWS credentials not configured - cannot verify AWS Secrets"
    ((WARNED++))
else
    echo "[INFO] Checking AWS Secrets Manager..."

    REGION=${AWS_REGION:-us-east-1}

    if aws secretsmanager describe-secret --secret-id "algo/db/postgres" --region "$REGION" &> /dev/null; then
        echo "[OK] algo/db/postgres secret exists"

        SECRET_ARN=$(aws secretsmanager describe-secret \
            --secret-id "algo/db/postgres" \
            --region "$REGION" \
            --query 'ARN' \
            --output text 2>/dev/null)

        echo "[INFO] Secret ARN: $SECRET_ARN"
        ((PASSED++))

        # Verify readable
        if aws secretsmanager get-secret-value --secret-id "algo/db/postgres" --region "$REGION" &> /dev/null; then
            echo "[OK] Secret is readable"
            ((PASSED++))
        else
            echo "[ERROR] Secret is not readable"
            ((FAILED++))
        fi
    else
        echo "[ERROR] algo/db/postgres secret does not exist"
        ((FAILED++))
    fi
fi

echo ""

# Test 5: Lambda Configuration
echo "[TEST 5] Lambda Environment Variables (via Terraform)"
echo "------------------------------------------------------------------------"

if command -v aws &> /dev/null && aws sts get-caller-identity &> /dev/null; then
    echo "[INFO] Checking Lambda configuration..."

    FUNCTION_NAME="${1:-algo-api-dev}"
    REGION=${AWS_REGION:-us-east-1}

    if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" &> /dev/null; then
        echo "[OK] Lambda function found: $FUNCTION_NAME"
        ((PASSED++))

        # Check environment variables
        ENV_VARS=$(aws lambda get-function-configuration \
            --function-name "$FUNCTION_NAME" \
            --region "$REGION" \
            --query 'Environment.Variables' \
            --output json 2>/dev/null)

        if echo "$ENV_VARS" | grep -q "DB_SECRET_ARN"; then
            echo "[OK] DB_SECRET_ARN in Lambda environment"
            ((PASSED++))
        else
            echo "[WARN] DB_SECRET_ARN not in Lambda environment"
            ((WARNED++))
        fi

        if echo "$ENV_VARS" | grep -q "COGNITO_USER_POOL_ID"; then
            echo "[OK] COGNITO_USER_POOL_ID in Lambda environment"
            ((PASSED++))
        else
            echo "[WARN] COGNITO_USER_POOL_ID not in Lambda environment"
            ((WARNED++))
        fi
    else
        echo "[WARN] Lambda function not found: $FUNCTION_NAME"
        ((WARNED++))
    fi
else
    echo "[WARN] AWS CLI not available - skipping Lambda check"
    ((WARNED++))
fi

echo ""

# Summary
echo "========================================================================"
echo "VERIFICATION SUMMARY"
echo "========================================================================"
echo ""
echo "Passed:  $PASSED"
echo "Failed:  $FAILED"
echo "Warned:  $WARNED"
echo ""

if [ $FAILED -eq 0 ] && [ $PASSED -gt 0 ]; then
    echo "[OK] CREDENTIAL PIPELINE VERIFIED"
    exit 0
elif [ $FAILED -eq 0 ]; then
    echo "[WARN] Some checks could not be completed - see above"
    exit 0
else
    echo "[ERROR] Credential pipeline has issues - see above"
    exit 1
fi
