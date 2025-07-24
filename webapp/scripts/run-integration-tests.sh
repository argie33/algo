#!/bin/bash

# Enhanced Integration Test Runner for Session Management and AWS Deployment
# Supports test environment configuration, parallel execution, and comprehensive reporting

set -e

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_RESULTS_DIR="${PROJECT_ROOT}/test-results"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="${TEST_RESULTS_DIR}/integration_test_${TIMESTAMP}.log"

# Test environment configuration
TEST_ENV=${TEST_ENV:-"local"}
SKIP_AWS_TESTS=${SKIP_AWS_TESTS:-"false"}
PARALLEL_TESTS=${PARALLEL_TESTS:-"true"}
VERBOSE=${VERBOSE:-"false"}
COVERAGE=${COVERAGE:-"false"}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case $level in
        "INFO")  echo -e "${BLUE}[INFO]${NC} ${message}" | tee -a "$LOG_FILE" ;;
        "WARN")  echo -e "${YELLOW}[WARN]${NC} ${message}" | tee -a "$LOG_FILE" ;;
        "ERROR") echo -e "${RED}[ERROR]${NC} ${message}" | tee -a "$LOG_FILE" ;;
        "SUCCESS") echo -e "${GREEN}[SUCCESS]${NC} ${message}" | tee -a "$LOG_FILE" ;;
    esac
}

# Print banner
print_banner() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║               Integration Test Suite                           ║"
    echo "║            Session Management & AWS Deployment                ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Setup test environment
setup_test_env() {
    log "INFO" "Setting up test environment: $TEST_ENV"
    
    # Create test results directory
    mkdir -p "$TEST_RESULTS_DIR"
    
    # Set environment variables
    export NODE_ENV="test"
    export SKIP_AWS_TESTS="$SKIP_AWS_TESTS"
    export VITE_API_URL="${VITE_API_URL:-http://localhost:8000}"
    export VITE_SESSION_API_URL="${VITE_SESSION_API_URL:-http://localhost:8001}"
    
    # Load test configuration
    if [ -f "${PROJECT_ROOT}/.env.test" ]; then
        log "INFO" "Loading test environment variables from .env.test"
        set -a
        source "${PROJECT_ROOT}/.env.test"
        set +a
    fi
    
    # Validate required dependencies
    if ! command -v npm &> /dev/null; then
        log "ERROR" "npm is required but not installed"
        exit 1
    fi
    
    # Install dependencies if needed
    if [ ! -d "${PROJECT_ROOT}/node_modules" ]; then
        log "INFO" "Installing dependencies..."
        cd "$PROJECT_ROOT"
        npm install --silent
    fi
    
    log "SUCCESS" "Test environment setup completed"
}

# Validate AWS connectivity (if not skipping AWS tests)
validate_aws_connectivity() {
    if [ "$SKIP_AWS_TESTS" = "true" ]; then
        log "WARN" "Skipping AWS connectivity validation"
        return 0
    fi
    
    log "INFO" "Validating AWS connectivity..."
    
    # Check if AWS CLI is available
    if command -v aws &> /dev/null; then
        # Test AWS connectivity
        if aws sts get-caller-identity &> /dev/null; then
            log "SUCCESS" "AWS connectivity validated"
        else
            log "WARN" "AWS credentials not configured or invalid"
            export SKIP_AWS_TESTS="true"
        fi
    else
        log "WARN" "AWS CLI not available, skipping AWS tests"
        export SKIP_AWS_TESTS="true"
    fi
}

# Run unit tests first (prerequisite)
run_unit_tests() {
    log "INFO" "Running unit tests as prerequisite..."
    
    cd "$PROJECT_ROOT"
    
    local unit_test_cmd="npm run test:unit"
    if [ "$COVERAGE" = "true" ]; then
        unit_test_cmd="npm run test:coverage"
    fi
    
    if eval "$unit_test_cmd" >> "$LOG_FILE" 2>&1; then
        log "SUCCESS" "Unit tests passed"
        return 0
    else
        log "ERROR" "Unit tests failed - stopping integration tests"
        return 1
    fi
}

# Run session management integration tests
run_session_tests() {
    log "INFO" "Running session management integration tests..."
    
    cd "$PROJECT_ROOT"
    
    local test_files=(
        "src/tests/integration/session-management.test.js"
        "src/tests/integration/aws-session-backend.test.js"
    )
    
    local test_cmd="npx vitest run"
    if [ "$PARALLEL_TESTS" = "true" ]; then
        test_cmd="$test_cmd --pool=threads --poolOptions.threads.minThreads=2 --poolOptions.threads.maxThreads=4"
    fi
    
    if [ "$VERBOSE" = "true" ]; then
        test_cmd="$test_cmd --reporter=verbose"
    fi
    
    for test_file in "${test_files[@]}"; do
        if [ -f "$test_file" ]; then
            log "INFO" "Running $test_file"
            
            if eval "$test_cmd '$test_file'" >> "$LOG_FILE" 2>&1; then
                log "SUCCESS" "✅ $(basename "$test_file") passed"
            else
                log "ERROR" "❌ $(basename "$test_file") failed"
                return 1
            fi
        else
            log "WARN" "Test file not found: $test_file"
        fi
    done
    
    return 0
}

# Run E2E tests using Playwright
run_e2e_tests() {
    log "INFO" "Running E2E workflow tests..."
    
    cd "$PROJECT_ROOT"
    
    # Check if Playwright is installed
    if ! npx playwright --version &> /dev/null; then
        log "INFO" "Installing Playwright..."
        npx playwright install >> "$LOG_FILE" 2>&1
    fi
    
    local e2e_test_file="src/tests/integration/e2e-session-workflow.test.js"
    
    if [ -f "$e2e_test_file" ]; then
        local playwright_cmd="npx playwright test '$e2e_test_file'"
        
        if [ "$PARALLEL_TESTS" = "true" ]; then
            playwright_cmd="$playwright_cmd --workers=2"
        else
            playwright_cmd="$playwright_cmd --workers=1"
        fi
        
        if eval "$playwright_cmd" >> "$LOG_FILE" 2>&1; then
            log "SUCCESS" "✅ E2E tests passed"
            return 0
        else
            log "ERROR" "❌ E2E tests failed"
            return 1
        fi
    else
        log "WARN" "E2E test file not found: $e2e_test_file"
        return 0
    fi
}

# Run deployment validation tests
run_deployment_tests() {
    log "INFO" "Running deployment validation tests..."
    
    cd "$PROJECT_ROOT"
    
    local deployment_test_file="src/tests/integration/deployment-validation.test.js"
    
    if [ -f "$deployment_test_file" ]; then
        local test_cmd="npx vitest run '$deployment_test_file'"
        
        if [ "$VERBOSE" = "true" ]; then
            test_cmd="$test_cmd --reporter=verbose"
        fi
        
        if eval "$test_cmd" >> "$LOG_FILE" 2>&1; then
            log "SUCCESS" "✅ Deployment validation passed"
            return 0
        else
            log "ERROR" "❌ Deployment validation failed"
            return 1
        fi
    else
        log "WARN" "Deployment test file not found: $deployment_test_file"
        return 0
    fi
}

# Generate test report
generate_test_report() {
    log "INFO" "Generating test report..."
    
    local report_file="${TEST_RESULTS_DIR}/integration_test_report_${TIMESTAMP}.html"
    
    cat > "$report_file" << EOF
<!DOCTYPE html>
<html>
<head>
    <title>Integration Test Report - $TIMESTAMP</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background: #f5f5f5; padding: 20px; border-radius: 5px; }
        .success { color: #28a745; }
        .error { color: #dc3545; }
        .warning { color: #ffc107; }
        .info { color: #17a2b8; }
        .section { margin: 20px 0; padding: 15px; border-left: 4px solid #ddd; }
        pre { background: #f8f9fa; padding: 10px; border-radius: 3px; overflow-x: auto; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Integration Test Report</h1>
        <p><strong>Timestamp:</strong> $TIMESTAMP</p>
        <p><strong>Environment:</strong> $TEST_ENV</p>
        <p><strong>Skip AWS Tests:</strong> $SKIP_AWS_TESTS</p>
        <p><strong>Parallel Execution:</strong> $PARALLEL_TESTS</p>
    </div>
    
    <div class="section">
        <h2>Test Execution Log</h2>
        <pre>$(cat "$LOG_FILE" | tail -100)</pre>
    </div>
    
    <div class="section">
        <h2>Test Results Summary</h2>
        <ul>
            <li>Session Management Tests: $(grep -c "session-management.test.js.*passed" "$LOG_FILE" || echo "0") passed</li>
            <li>AWS Backend Tests: $(grep -c "aws-session-backend.test.js.*passed" "$LOG_FILE" || echo "0") passed</li>
            <li>E2E Workflow Tests: $(grep -c "E2E tests passed" "$LOG_FILE" || echo "0") passed</li>
            <li>Deployment Validation: $(grep -c "Deployment validation passed" "$LOG_FILE" || echo "0") passed</li>
        </ul>
    </div>
    
    <div class="section">
        <h2>Environment Information</h2>
        <ul>
            <li><strong>Node Version:</strong> $(node --version)</li>
            <li><strong>NPM Version:</strong> $(npm --version)</li>
            <li><strong>API URL:</strong> ${VITE_API_URL}</li>
            <li><strong>Session API URL:</strong> ${VITE_SESSION_API_URL}</li>
        </ul>
    </div>
    
    <div class="section">
        <h2>Recommendations</h2>
        <ul>
            <li>Review failed tests in the execution log above</li>
            <li>Check AWS connectivity if deployment tests failed</li>
            <li>Verify API endpoints are accessible for E2E tests</li>
            <li>Consider running tests with --verbose for more details</li>
        </ul>
    </div>
</body>
</html>
EOF
    
    log "SUCCESS" "Test report generated: $report_file"
}

# Upload test results (if configured)
upload_test_results() {
    if [ -n "$TEST_RESULTS_S3_BUCKET" ]; then
        log "INFO" "Uploading test results to S3..."
        
        if command -v aws &> /dev/null; then
            aws s3 cp "$TEST_RESULTS_DIR" "s3://$TEST_RESULTS_S3_BUCKET/integration-tests/$TIMESTAMP/" --recursive
            log "SUCCESS" "Test results uploaded to S3"
        else
            log "WARN" "AWS CLI not available, skipping S3 upload"
        fi
    fi
}

# Cleanup function
cleanup() {
    log "INFO" "Cleaning up test environment..."
    
    # Kill any remaining test processes
    pkill -f "vitest" 2>/dev/null || true
    pkill -f "playwright" 2>/dev/null || true
    
    # Clean up temporary files
    rm -rf "${PROJECT_ROOT}/coverage/.tmp" 2>/dev/null || true
    
    log "SUCCESS" "Cleanup completed"
}

# Main execution function
main() {
    local exit_code=0
    
    print_banner
    
    # Setup trap for cleanup
    trap cleanup EXIT
    
    # Setup test environment
    setup_test_env
    
    # Validate AWS connectivity
    validate_aws_connectivity
    
    # Run tests in sequence
    log "INFO" "Starting integration test suite..."
    
    # Run unit tests first
    if ! run_unit_tests; then
        exit_code=1
    fi
    
    # Run session management tests
    if [ $exit_code -eq 0 ]; then
        if ! run_session_tests; then
            exit_code=1
        fi
    fi
    
    # Run E2E tests
    if [ $exit_code -eq 0 ]; then
        if ! run_e2e_tests; then
            exit_code=1
        fi
    fi
    
    # Run deployment validation
    if [ $exit_code -eq 0 ]; then
        if ! run_deployment_tests; then
            exit_code=1
        fi
    fi
    
    # Generate report
    generate_test_report
    
    # Upload results if configured
    upload_test_results
    
    # Final status
    if [ $exit_code -eq 0 ]; then
        log "SUCCESS" "🎉 All integration tests passed!"
        echo -e "\n${GREEN}✅ Integration test suite completed successfully${NC}"
        echo -e "📊 Test report: ${TEST_RESULTS_DIR}/integration_test_report_${TIMESTAMP}.html"
        echo -e "📝 Test log: ${LOG_FILE}"
    else
        log "ERROR" "❌ Some integration tests failed"
        echo -e "\n${RED}❌ Integration test suite failed${NC}"
        echo -e "📊 Test report: ${TEST_RESULTS_DIR}/integration_test_report_${TIMESTAMP}.html"
        echo -e "📝 Test log: ${LOG_FILE}"
    fi
    
    exit $exit_code
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --env)
            TEST_ENV="$2"
            shift 2
            ;;
        --skip-aws)
            SKIP_AWS_TESTS="true"
            shift
            ;;
        --no-parallel)
            PARALLEL_TESTS="false"
            shift
            ;;
        --verbose)
            VERBOSE="true"
            shift
            ;;
        --coverage)
            COVERAGE="true"
            shift
            ;;
        --help)
            echo "Integration Test Runner"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --env ENV          Set test environment (default: local)"
            echo "  --skip-aws         Skip AWS-dependent tests"
            echo "  --no-parallel      Disable parallel test execution"
            echo "  --verbose          Enable verbose test output"
            echo "  --coverage         Generate coverage reports"
            echo "  --help             Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  VITE_API_URL       API base URL for testing"
            echo "  VITE_SESSION_API_URL Session API base URL"
            echo "  TEST_RESULTS_S3_BUCKET S3 bucket for uploading results"
            echo ""
            exit 0
            ;;
        *)
            log "ERROR" "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Run main function
main "$@"