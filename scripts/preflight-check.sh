#!/bin/bash
# Pre-Flight Check for AWS Optimization Deployment
# Validates all prerequisites before terraform apply

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=========================================="
echo "AWS OPTIMIZATION PRE-FLIGHT CHECK"
echo "=========================================="
echo ""

CHECKS_PASSED=0
CHECKS_FAILED=0

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
check_pass() {
  echo -e "${GREEN}✅ PASS${NC}: $1"
  ((CHECKS_PASSED++))
}

check_fail() {
  echo -e "${RED}❌ FAIL${NC}: $1"
  ((CHECKS_FAILED++))
}

check_warn() {
  echo -e "${YELLOW}⚠️  WARN${NC}: $1"
}

# ============================================================
# 1. Git Verification
# ============================================================
echo "1. GIT VERIFICATION"
echo "---"

# Check commit exists
if git log --oneline -1 | grep -q "cost optimization"; then
  COMMIT=$(git log -1 --format="%H %s")
  check_pass "Tier 1 optimization commit found: $COMMIT"
else
  check_fail "Tier 1 optimization commit NOT found"
  echo "   Expected commit with message containing 'cost optimization'"
fi

# Check terraform file was modified
if git diff HEAD~1 terraform/modules/loaders/main.tf 2>/dev/null | grep -q "memory"; then
  CHANGES=$(git diff HEAD~1 terraform/modules/loaders/main.tf 2>/dev/null | grep -E "memory|parallelism" | wc -l)
  check_pass "Terraform changes verified ($CHANGES lines modified)"
else
  check_fail "Terraform changes NOT found in git diff"
fi

echo ""

# ============================================================
# 2. File Verification
# ============================================================
echo "2. FILE VERIFICATION"
echo "---"

# Check critical files exist
FILES=(
  "terraform/modules/loaders/main.tf"
  "scripts/aws-cost-audit.sh"
  "DEPLOYMENT_RUNBOOK.md"
  "DEPLOYMENT_CHECKLIST.md"
  "AWS_OPTIMIZATION_SUMMARY.md"
  "EXECUTION_TRACKER.md"
)

for file in "${FILES[@]}"; do
  if [ -f "$file" ]; then
    check_pass "File exists: $file"
  else
    check_fail "File NOT found: $file"
  fi
done

echo ""

# ============================================================
# 3. AWS CLI Verification
# ============================================================
echo "3. AWS CLI VERIFICATION"
echo "---"

if ! command -v aws &> /dev/null; then
  check_fail "AWS CLI not found (install: https://aws.amazon.com/cli/)"
else
  check_pass "AWS CLI is installed"
fi

if aws sts get-caller-identity &>/dev/null; then
  ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
  USER=$(aws sts get-caller-identity --query Arn --output text)
  check_pass "AWS credentials configured (Account: $ACCOUNT)"
  check_pass "AWS user/role: $USER"
else
  check_fail "AWS credentials NOT configured or invalid"
  echo "   Run: aws configure"
fi

echo ""

# ============================================================
# 4. Terraform Verification
# ============================================================
echo "4. TERRAFORM VERIFICATION"
echo "---"

if ! command -v terraform &> /dev/null; then
  check_fail "Terraform not found (install: https://www.terraform.io/downloads)"
else
  TF_VERSION=$(terraform version | head -1)
  check_pass "Terraform installed: $TF_VERSION"
fi

cd terraform
if [ -f "terraform.tfstate" ] || [ -d ".terraform" ]; then
  check_pass "Terraform state/backend initialized"
else
  check_warn "Terraform backend not initialized (will initialize on first plan)"
fi

# Syntax check
if terraform validate &>/dev/null; then
  check_pass "Terraform syntax is valid"
else
  check_fail "Terraform syntax error detected"
  terraform validate
fi
cd "$REPO_ROOT"

echo ""

# ============================================================
# 5. Network/Connectivity Verification
# ============================================================
echo "5. NETWORK VERIFICATION"
echo "---"

if curl -s --connect-timeout 5 https://api.github.com &>/dev/null; then
  check_pass "Internet connectivity OK"
else
  check_warn "May not have internet connectivity (needed for AWS API calls)"
fi

if aws ec2 describe-regions --query 'Regions[0].RegionName' --output text &>/dev/null; then
  check_pass "AWS API connectivity OK"
else
  check_fail "Cannot reach AWS API (check credentials and network)"
fi

echo ""

# ============================================================
# 6. ECS Resources Verification
# ============================================================
echo "6. ECS RESOURCES VERIFICATION"
echo "---"

if aws ecs describe-clusters --clusters algo-cluster --query 'clusters[0].clusterArn' --output text &>/dev/null; then
  check_pass "ECS cluster 'algo-cluster' found"
else
  check_fail "ECS cluster 'algo-cluster' NOT found"
fi

# Check key task definitions exist (before optimization)
TASK_DEF_COUNT=$(aws ecs list-task-definitions --family-prefix algo- --region us-east-1 --query 'taskDefinitionArns | length(@)' --output text 2>/dev/null || echo "0")
if [ "$TASK_DEF_COUNT" -gt 25 ]; then
  check_pass "ECS task definitions found ($TASK_DEF_COUNT total)"
else
  check_fail "Expected >25 ECS task definitions, found $TASK_DEF_COUNT"
fi

echo ""

# ============================================================
# 7. RDS Verification
# ============================================================
echo "7. RDS VERIFICATION"
echo "---"

if aws rds describe-db-instances --db-instance-identifier algo-db --query 'DBInstances[0].DBInstanceIdentifier' --output text &>/dev/null; then
  check_pass "RDS instance 'algo-db' found"

  # Check RDS Proxy
  if aws rds describe-db-proxies --db-proxy-name algo-rds-proxy-dev --query 'DBProxies[0].DBProxyName' --output text &>/dev/null; then
    check_pass "RDS Proxy 'algo-rds-proxy-dev' found"
  else
    check_warn "RDS Proxy not found (connection pooling may not be active)"
  fi
else
  check_fail "RDS instance 'algo-db' NOT found"
fi

echo ""

# ============================================================
# 8. CloudWatch Verification
# ============================================================
echo "8. CLOUDWATCH VERIFICATION"
echo "---"

# Check if log groups exist
LOG_GROUPS=$(aws logs describe-log-groups --query 'logGroups | length(@)' --output text 2>/dev/null || echo "0")
if [ "$LOG_GROUPS" -gt 5 ]; then
  check_pass "CloudWatch log groups found ($LOG_GROUPS total)"
else
  check_warn "Few CloudWatch log groups found ($LOG_GROUPS), may need monitoring setup"
fi

# Check specific loader log group
if aws logs describe-log-groups --log-group-name-prefix "/ecs/algo-" --query 'logGroups[0]' &>/dev/null; then
  check_pass "ECS loader log groups exist"
else
  check_warn "ECS loader log groups not yet created (will be created on first loader run)"
fi

echo ""

# ============================================================
# 9. Cost Explorer Access
# ============================================================
echo "9. AWS COST EXPLORER VERIFICATION"
echo "---"

if aws ce get-cost-and-usage --time-period Start=2026-06-27,End=2026-06-28 --granularity DAILY --metrics UnblendedCost --query 'ResultsByTime[0]' &>/dev/null; then
  check_pass "AWS Cost Explorer accessible (can verify cost savings)"
else
  check_warn "AWS Cost Explorer may not be accessible (check IAM permissions)"
fi

echo ""

# ============================================================
# SUMMARY
# ============================================================
echo "=========================================="
echo "SUMMARY"
echo "=========================================="
echo -e "Checks Passed: ${GREEN}$CHECKS_PASSED${NC}"
echo -e "Checks Failed: ${RED}$CHECKS_FAILED${NC}"
echo ""

if [ $CHECKS_FAILED -eq 0 ]; then
  echo -e "${GREEN}✅ ALL CHECKS PASSED${NC}"
  echo ""
  echo "Ready to proceed with deployment."
  echo ""
  echo "Next steps:"
  echo "1. Run: bash scripts/aws-cost-audit.sh"
  echo "2. Run: cd terraform && terraform plan -out=tfplan"
  echo "3. Run: terraform apply tfplan"
  echo "4. Monitor overnight loader run"
  echo "5. Verify cost savings tomorrow morning"
  echo ""
  echo "See EXECUTION_TRACKER.md for detailed status tracking"
  exit 0
else
  echo -e "${RED}❌ SOME CHECKS FAILED${NC}"
  echo ""
  echo "Please fix the failed checks before proceeding:"
  echo "- Install missing tools (AWS CLI, Terraform)"
  echo "- Configure AWS credentials"
  echo "- Verify ECS/RDS/CloudWatch resources exist"
  echo ""
  echo "Refer to DEPLOYMENT_RUNBOOK.md for troubleshooting"
  exit 1
fi
