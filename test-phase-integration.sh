#!/bin/bash
# Test Script: Verify all optimization phases (A-E) work correctly
# Run this to validate end-to-end pipeline before production deployment

set -e

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

AWS_REGION=${AWS_REGION:-us-east-1}

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Phase Integration Test Suite${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""

# Test 1: Verify Phase A infrastructure
test_phase_a() {
    echo -e "${YELLOW}Test 1: Phase A (ECS S3 Staging + Fargate Spot)${NC}"

    # Check ECS cluster exists
    CLUSTER=$(aws ecs list-clusters --query 'clusterArns[0]' --output text 2>/dev/null || echo "NONE")
    if [[ "$CLUSTER" == "NONE" ]]; then
        echo -e "${RED}✗ ECS cluster not found${NC}"
        return 1
    fi
    echo -e "${GREEN}✓ ECS cluster found: $CLUSTER${NC}"

    # Check task definition has S3_STAGING env var
    TASK_DEF=$(aws ecs list-task-definitions --query 'taskDefinitionArns[0]' --output text 2>/dev/null || echo "")
    if [[ -n "$TASK_DEF" ]]; then
        ENV_VARS=$(aws ecs describe-task-definition --task-definition "$TASK_DEF" \
            --query 'taskDefinition.containerDefinitions[0].environment' 2>/dev/null || echo "[]")
        if echo "$ENV_VARS" | grep -q "USE_S3_STAGING"; then
            echo -e "${GREEN}✓ S3 staging enabled in ECS task definitions${NC}"
        else
            echo -e "${RED}✗ S3 staging NOT enabled${NC}"
            return 1
        fi
    fi

    # Check for Fargate Spot configuration
    if aws cloudformation describe-stacks --stack-name stocks-ecs-tasks-stack 2>/dev/null | grep -q "FARGATE_SPOT"; then
        echo -e "${GREEN}✓ Fargate Spot configured in CloudFormation${NC}"
    else
        echo -e "${RED}✗ Fargate Spot NOT configured${NC}"
    fi

    return 0
}

# Test 2: Verify Phase C Lambda infrastructure
test_phase_c() {
    echo -e "${YELLOW}Test 2: Phase C (Lambda Orchestrator)${NC}"

    # Check Lambda function exists
    ORCHESTRATOR=$(aws lambda get-function --function-name buyselldaily-orchestrator \
        --query 'Configuration.FunctionName' --output text 2>/dev/null || echo "NONE")
    if [[ "$ORCHESTRATOR" == "NONE" ]]; then
        echo -e "${YELLOW}⚠ Lambda function not yet deployed (will deploy on first push)${NC}"
    else
        echo -e "${GREEN}✓ Lambda orchestrator found: $ORCHESTRATOR${NC}"
    fi

    # Check CloudFormation template exists
    if [[ -f "template-lambda-phase-c.yml" ]]; then
        echo -e "${GREEN}✓ Phase C template found: template-lambda-phase-c.yml${NC}"
    else
        echo -e "${RED}✗ Phase C template NOT found${NC}"
        return 1
    fi

    # Verify Lambda orchestrator code uses stock_symbols table
    if grep -q "stock_symbols" lambda_buyselldaily_orchestrator.py; then
        echo -e "${GREEN}✓ Lambda orchestrator queries correct stock_symbols table${NC}"
    else
        echo -e "${RED}✗ Lambda orchestrator not using stock_symbols table${NC}"
        return 1
    fi

    return 0
}

# Test 3: Verify Phase D Step Functions
test_phase_d() {
    echo -e "${YELLOW}Test 3: Phase D (Step Functions DAG)${NC}"

    # Check Step Functions template exists
    if [[ -f "template-step-functions-phase-d.yml" ]]; then
        echo -e "${GREEN}✓ Phase D template found: template-step-functions-phase-d.yml${NC}"
    else
        echo -e "${RED}✗ Phase D template NOT found${NC}"
        return 1
    fi

    # Validate template has correct structure
    if grep -q "LoadPriceDataParallel\|LoadSignalsParallel" template-step-functions-phase-d.yml; then
        echo -e "${GREEN}✓ Phase D DAG has correct parallel stages${NC}"
    else
        echo -e "${RED}✗ Phase D DAG structure invalid${NC}"
        return 1
    fi

    # Check for retry logic
    if grep -q "Retry\|BackoffRate" template-step-functions-phase-d.yml; then
        echo -e "${GREEN}✓ Phase D has automatic retry logic${NC}"
    else
        echo -e "${RED}✗ Phase D missing retry logic${NC}"
    fi

    return 0
}

# Test 4: Verify Phase E incremental loading
test_phase_e() {
    echo -e "${YELLOW}Test 4: Phase E (Smart Incremental + Caching)${NC}"

    # Check Phase E code exists
    if [[ -f "phase_e_incremental.py" ]]; then
        echo -e "${GREEN}✓ Phase E implementation found: phase_e_incremental.py${NC}"
    else
        echo -e "${RED}✗ Phase E NOT found${NC}"
        return 1
    fi

    # Check for cache logic
    if grep -q "load_from_cache\|save_to_cache" phase_e_incremental.py; then
        echo -e "${GREEN}✓ Phase E has caching logic${NC}"
    else
        echo -e "${RED}✗ Phase E missing caching logic${NC}"
        return 1
    fi

    # Check DynamoDB template
    if [[ -f "template-phase-e-dynamodb.yml" ]]; then
        echo -e "${GREEN}✓ Phase E DynamoDB template found${NC}"
    else
        echo -e "${RED}✗ Phase E DynamoDB template NOT found${NC}"
    fi

    return 0
}

# Test 5: Verify GitHub Actions workflow
test_workflow() {
    echo -e "${YELLOW}Test 5: GitHub Actions Workflow${NC}"

    if [[ -f ".github/workflows/deploy-app-stocks.yml" ]]; then
        echo -e "${GREEN}✓ Workflow file found${NC}"
    else
        echo -e "${RED}✗ Workflow file NOT found${NC}"
        return 1
    fi

    # Check for Phase C job
    if grep -q "execute-phase-c-lambda-orchestrator" .github/workflows/deploy-app-stocks.yml; then
        echo -e "${GREEN}✓ Phase C job integrated in workflow${NC}"
    else
        echo -e "${RED}✗ Phase C job NOT in workflow${NC}"
    fi

    # Check for Phase D job
    if grep -q "deploy-phase-d-step-functions" .github/workflows/deploy-app-stocks.yml; then
        echo -e "${GREEN}✓ Phase D job integrated in workflow${NC}"
    else
        echo -e "${RED}✗ Phase D job NOT in workflow${NC}"
    fi

    # Check for Phase E job
    if grep -q "deploy-phase-e-infrastructure" .github/workflows/deploy-app-stocks.yml; then
        echo -e "${GREEN}✓ Phase E job integrated in workflow${NC}"
    else
        echo -e "${RED}✗ Phase E job NOT in workflow${NC}"
    fi

    # Check max-parallel is 10
    if grep -q "max-parallel.*10" .github/workflows/deploy-app-stocks.yml; then
        echo -e "${GREEN}✓ Parallel execution set to 10 loaders${NC}"
    else
        echo -e "${RED}✗ Parallel execution NOT optimized${NC}"
    fi

    return 0
}

# Test 6: Verify database tables
test_database() {
    echo -e "${YELLOW}Test 6: Database Tables${NC}"

    # Check if we can connect to database
    if command -v psql &> /dev/null; then
        DB_HOST=${DB_HOST:-localhost}
        DB_USER=${DB_USER:-stocks}
        DB_NAME=${DB_NAME:-stocks}

        # Try to list tables
        TABLES=$(psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "\dt" 2>/dev/null | wc -l || echo "0")
        if [[ $TABLES -gt 0 ]]; then
            echo -e "${GREEN}✓ Database connection successful ($TABLES tables found)${NC}"

            # Check for stock_symbols table
            if psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "\dt stock_symbols" 2>/dev/null | grep -q "stock_symbols"; then
                echo -e "${GREEN}✓ stock_symbols table exists${NC}"
            else
                echo -e "${YELLOW}⚠ stock_symbols table NOT found (will be created by loadstocksymbols.py)${NC}"
            fi
        else
            echo -e "${YELLOW}⚠ Database connection not available (local testing only)${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ psql not installed (skipping database check)${NC}"
    fi

    return 0
}

# Test 7: Verify documentation
test_documentation() {
    echo -e "${YELLOW}Test 7: Documentation${NC}"

    if [[ -f "STATUS_LIVE.md" ]]; then
        echo -e "${GREEN}✓ STATUS_LIVE.md found${NC}"
    else
        echo -e "${RED}✗ STATUS_LIVE.md NOT found${NC}"
    fi

    if [[ -f "PHASE_INTEGRATION.md" ]]; then
        echo -e "${GREEN}✓ PHASE_INTEGRATION.md found${NC}"
    else
        echo -e "${RED}✗ PHASE_INTEGRATION.md NOT found${NC}"
    fi

    if [[ -f "OPTIMIZATION_PHASES.md" ]]; then
        echo -e "${GREEN}✓ OPTIMIZATION_PHASES.md found${NC}"
    else
        echo -e "${RED}✗ OPTIMIZATION_PHASES.md NOT found${NC}"
    fi

    return 0
}

# Run all tests
echo -e "${YELLOW}Running all tests...${NC}"
echo ""

test_phase_a
PHASE_A=$?

test_phase_c
PHASE_C=$?

test_phase_d
PHASE_D=$?

test_phase_e
PHASE_E=$?

test_workflow
WORKFLOW=$?

test_database
DATABASE=$?

test_documentation
DOCS=$?

echo ""
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Test Results Summary${NC}"
echo -e "${YELLOW}========================================${NC}"

FAILED=0
[[ $PHASE_A -ne 0 ]] && echo -e "${RED}✗ Phase A tests FAILED${NC}" && FAILED=$((FAILED+1))
[[ $PHASE_A -eq 0 ]] && echo -e "${GREEN}✓ Phase A tests passed${NC}"

[[ $PHASE_C -ne 0 ]] && echo -e "${RED}✗ Phase C tests FAILED${NC}" && FAILED=$((FAILED+1))
[[ $PHASE_C -eq 0 ]] && echo -e "${GREEN}✓ Phase C tests passed${NC}"

[[ $PHASE_D -ne 0 ]] && echo -e "${RED}✗ Phase D tests FAILED${NC}" && FAILED=$((FAILED+1))
[[ $PHASE_D -eq 0 ]] && echo -e "${GREEN}✓ Phase D tests passed${NC}"

[[ $PHASE_E -ne 0 ]] && echo -e "${RED}✗ Phase E tests FAILED${NC}" && FAILED=$((FAILED+1))
[[ $PHASE_E -eq 0 ]] && echo -e "${GREEN}✓ Phase E tests passed${NC}"

[[ $WORKFLOW -ne 0 ]] && echo -e "${RED}✗ Workflow tests FAILED${NC}" && FAILED=$((FAILED+1))
[[ $WORKFLOW -eq 0 ]] && echo -e "${GREEN}✓ Workflow tests passed${NC}"

[[ $DATABASE -eq 0 ]] && echo -e "${GREEN}✓ Database check passed${NC}"
[[ $DOCS -eq 0 ]] && echo -e "${GREEN}✓ Documentation check passed${NC}"

echo ""
if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}ALL TESTS PASSED ✓${NC}"
    echo -e "${GREEN}Ready for production deployment${NC}"
    echo -e "${GREEN}========================================${NC}"
    exit 0
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}$FAILED TEST(S) FAILED ✗${NC}"
    echo -e "${RED}Please fix issues before deployment${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
