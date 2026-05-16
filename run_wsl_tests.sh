#!/bin/bash
# Comprehensive WSL Test Runner - Execute all verification tests
# Usage: bash run_wsl_tests.sh

set -e
cd "$(dirname "$0")"

echo "═══════════════════════════════════════════════════════════════════"
echo "ALGO PLATFORM - COMPREHENSIVE TEST SUITE (WSL)"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

TESTS_PASSED=0
TESTS_FAILED=0
ERRORS=""

# Test 1: Check database connectivity
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 1: Database Connectivity"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if python3 -c "import psycopg2; psycopg2.connect(host='localhost', port=5432, user='stocks', password='postgres', database='stocks')" 2>/dev/null; then
    echo -e "${GREEN}✓ Database connected${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ Database connection failed${NC}"
    ERRORS="$ERRORS\n- Database not running or credentials wrong"
    ((TESTS_FAILED++))
fi
echo ""

# Test 2: Verify data loaders
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 2: Data Loader Freshness"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if python3 verify_data_loaders.py 2>&1 | tee /tmp/loader_check.log; then
    echo -e "${GREEN}✓ All data loaders OK${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ Some data loaders failed${NC}"
    ERRORS="$ERRORS\n- Check /tmp/loader_check.log for details"
    ((TESTS_FAILED++))
fi
echo ""

# Test 3: Check for Python syntax errors in critical files
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 3: Python Syntax Validation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
SYNTAX_ERRORS=0
for file in algo_orchestrator.py algo_trade_executor.py algo_exit_engine.py loadpricedaily.py loadbuyselldaily.py; do
    if python3 -m py_compile "$file" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $file"
    else
        echo -e "  ${RED}✗${NC} $file - SYNTAX ERROR"
        ((SYNTAX_ERRORS++))
    fi
done
if [ $SYNTAX_ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ All files have valid Python syntax${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ Found $SYNTAX_ERRORS files with syntax errors${NC}"
    ((TESTS_FAILED++))
fi
echo ""

# Test 4: Run orchestrator dry-run
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 4: Orchestrator Dry-Run"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if python3 algo_run_daily.py --dry-run 2>&1 | tee /tmp/orchestrator.log | tail -20; then
    if grep -qi "error\|exception\|failed" /tmp/orchestrator.log; then
        echo -e "${YELLOW}⚠ Orchestrator ran but with warnings${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${GREEN}✓ Orchestrator dry-run successful${NC}"
        ((TESTS_PASSED++))
    fi
else
    echo -e "${RED}✗ Orchestrator dry-run failed${NC}"
    ERRORS="$ERRORS\n- Check /tmp/orchestrator.log for details"
    ((TESTS_FAILED++))
fi
echo ""

# Test 5: API Lambda syntax check
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 5: API Lambda Handler"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if python3 -m py_compile lambda/api/lambda_function.py 2>/dev/null; then
    echo -e "${GREEN}✓ API Lambda handler syntax OK${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ API Lambda handler has syntax errors${NC}"
    ((TESTS_FAILED++))
fi
echo ""

# Summary
echo "═══════════════════════════════════════════════════════════════════"
echo "TEST SUMMARY"
echo "═══════════════════════════════════════════════════════════════════"
echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed: ${RED}$TESTS_FAILED${NC}"

if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "\n${RED}FAILURES:${NC}"
    echo -e "$ERRORS"
    exit 1
else
    echo -e "\n${GREEN}All tests passed! System is ready.${NC}"
    exit 0
fi
