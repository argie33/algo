#!/bin/bash
# Analyze test failure patterns

echo "Running tests and analyzing failures..."
npm test -- --no-coverage 2>&1 > /tmp/test_output_full.txt

echo "========================================="
echo "TOP 3 ERROR PATTERNS BY FREQUENCY"
echo "========================================="
echo ""

echo "1. AUTHENTICATION BYPASS (Expected 401, Received 200)"
auth_count=$(grep -A1 "Expected: 401" /tmp/test_output_full.txt | grep "Received: 200" | wc -l)
auth_tests=$(grep -B10 "Expected: 401" /tmp/test_output_full.txt | grep -B1 "Received: 200" | grep "●" | wc -l)
echo "Tests affected: $auth_tests"
echo "Sample files:"
grep -B15 "Expected: 401" /tmp/test_output_full.txt | grep -A1 "Received: 200" | grep "FAIL tests" | head -3

echo ""
echo "2. DATABASE QUERY FAILURES (Cannot read properties of undefined 'rows')"
db_errors=$(grep "Cannot read properties of undefined (reading 'rows')" /tmp/test_output_full.txt | wc -l)
echo "Total occurrences: $db_errors"
echo "Sample files:"
grep -B10 "Cannot read properties of undefined (reading 'rows')" /tmp/test_output_full.txt | grep "FAIL tests" | sort -u | head -3

echo ""
echo "3. MISSING AWS/CRYPTO MOCKS (ReferenceError: SecretsManagerClient)"
mock_errors=$(grep "ReferenceError: SecretsManagerClient is not defined" /tmp/test_output_full.txt | wc -l)
echo "Total occurrences: $mock_errors"
echo "Sample files:"
grep -B10 "ReferenceError: SecretsManagerClient is not defined" /tmp/test_output_full.txt | grep "FAIL tests" | sort -u | head -3

echo ""
echo "========================================="
echo "FILES WITH MOST FAILURES (>10 tests)"
echo "========================================="
awk '/^FAIL / {file=$2} /^  ● / {counts[file]++} END {for (f in counts) if (counts[f] > 10) print counts[f], f}' /tmp/test_output_full.txt | sort -rn | head -10
