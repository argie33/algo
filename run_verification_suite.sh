#!/bin/bash
#
# Complete Post-Deployment Verification Suite
#
# Runs all verification tests in sequence to ensure system is production-ready
# Time: 60-90 minutes
# Exit Code: 0 if all tests pass, 1 if any test fails
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Start time
START_TIME=$(date +%s)

# Test results
PASSED=0
FAILED=0

echo ""
echo "================================================================================"
echo "  POST-DEPLOYMENT VERIFICATION SUITE"
echo "  Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================================"
echo ""

# Function to run a test and track results
run_test() {
    local test_name=$1
    local test_script=$2
    local test_duration=$3

    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}[TEST] ${test_name} (~${test_duration} min)${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    if [ ! -f "$test_script" ]; then
        echo -e "${YELLOW}[SKIP] Script not found: $test_script${NC}"
        return 0
    fi

    if python3 "$test_script"; then
        echo ""
        echo -e "${GREEN}[PASS] ${test_name}${NC}"
        ((PASSED++))
    else
        echo ""
        echo -e "${RED}[FAIL] ${test_name}${NC}"
        ((FAILED++))
    fi
}

# Phase 1: Code Quality
echo -e "${YELLOW}PHASE 1: CODE QUALITY VERIFICATION${NC}"
run_test "Python Compilation Check" "verify_tier1_fixes.py" "5"
run_test "System Comprehensive Check" "verify_system_comprehensive.py" "5"

# Phase 2: Data Pipeline
echo ""
echo -e "${YELLOW}PHASE 2: DATA PIPELINE VERIFICATION${NC}"
run_test "Data Pipeline Check" "verify_data_pipeline.py" "10"
run_test "Deployment Verification" "verify_deployment.py" "10"

# Phase 3: Calculations
echo ""
echo -e "${YELLOW}PHASE 3: CALCULATION VERIFICATION${NC}"
run_test "Data Integrity Check" "verify_data_integrity.py" "10"

# Phase 4: API
echo ""
echo -e "${YELLOW}PHASE 4: API VERIFICATION${NC}"
run_test "Post-Deployment Verification" "post_deployment_verification.py" "10"

# Phase 5: Orchestrator
echo ""
echo -e "${YELLOW}PHASE 5: ORCHESTRATOR VERIFICATION${NC}"
run_test "Orchestrator Phases Check" "test_orchestrator_phases.py" "5"

# Summary
echo ""
echo "================================================================================"
echo "  VERIFICATION SUMMARY"
echo "================================================================================"

TOTAL=$((PASSED + FAILED))
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
DURATION_MIN=$((DURATION / 60))

echo ""
echo -e "Total Tests: ${TOTAL}"
echo -e "${GREEN}Passed: ${PASSED}${NC}"
echo -e "${RED}Failed: ${FAILED}${NC}"
echo ""
echo "Duration: ${DURATION_MIN} minutes"
echo "Completed: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "================================================================================"
    echo -e "  ${GREEN}✓ ALL TESTS PASSED${NC}"
    echo "================================================================================"
    echo ""
    echo "Next Steps:"
    echo "1. Run orchestrator dry-run: python3 algo_orchestrator.py --mode paper --dry-run"
    echo "2. Check CloudWatch logs for Phase completions"
    echo "3. Validate frontend dashboards are displaying real data"
    echo "4. Review POST_DEPLOYMENT_TESTING_GUIDE.md for final sign-off checklist"
    echo ""
    echo "System is ready for production deployment!"
    echo ""
    exit 0
else
    echo "================================================================================"
    echo -e "  ${RED}✗ ${FAILED} TEST(S) FAILED${NC}"
    echo "================================================================================"
    echo ""
    echo "Review failures above and run individual tests to debug:"
    echo ""
    echo "  python3 verify_tier1_fixes.py"
    echo "  python3 verify_system_comprehensive.py"
    echo "  python3 verify_data_pipeline.py"
    echo "  python3 verify_deployment.py"
    echo "  python3 verify_data_integrity.py"
    echo "  python3 post_deployment_verification.py"
    echo "  python3 test_orchestrator_phases.py"
    echo ""
    exit 1
fi
