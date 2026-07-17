# AWS Account Migration Guide
**From:** edgebrookecapital@gmail.com (626216981288)  
**To:** edgebrookelabs@gmail.com (new account via Organizations)  
**Date:** 2026-07-17  
**Status:** Ready for execution

---

## Phase 1: Create New Account via Terraform (5-10 minutes)

### Prerequisites
- Root AWS credentials for edgebrookecapital account
- AWS Organizations enabled (existing org, new account via member account)

### Step 1.1: Configure Root Credentials

```bash
# Option A: AWS CLI credentials file
cat >> ~/.aws/credentials << 'EOF'
[root]
aws_access_key_id = YOUR_ROOT_ACCESS_KEY
aws_secret_access_key = YOUR_ROOT_SECRET_KEY
EOF

# Option B: Environment variables
export AWS_ACCESS_KEY_ID="YOUR_ROOT_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="YOUR_ROOT_SECRET_KEY"
export AWS_DEFAULT_REGION="us-east-1"
```

### Step 1.2: Initialize Account Creation Terraform

```bash
cd terraform/accounts

# Initialize Terraform with root credentials
AWS_PROFILE=root terraform init

# Plan account creation
AWS_PROFILE=root terraform plan -out=plan.out

# Expected output:
#   + aws_organizations_account.edgebrookelabs
#   + aws_iam_role.cross_account_deployment
#   + aws_db_snapshot.final_backup
#   + aws_s3_bucket.new_account_terraform_state
#   + aws_dynamodb_table.new_account_lock_table
```

### Step 1.3: Execute Account Creation

```bash
# Create the new account, snapshot RDS, and set up cross-account access
AWS_PROFILE=root terraform apply plan.out

# Monitor output - watch for:
# ✓ new_account_id = "XXXXXXXXXX"
# ✓ new_account_email = "edgebrookelabs@gmail.com"
# ✓ rds_snapshot_id = "algo-db-migration-YYYY-MM-DD-hhmm"
# ✓ rds_snapshot_status = "creating" → "available" (5-15 min)

# Save these outputs:
terraform output -json > migration-state.json
```

### Step 1.4: Verify Account Creation

```bash
# Check Organizations
aws organizations list-accounts \
  --query "Accounts[?Email=='edgebrookelabs@gmail.com']" \
  --profile root

# Expected: Account with status "ACTIVE"

# Check RDS Snapshot
aws rds describe-db-snapshots \
  --query "DBSnapshots[?starts_with(DBSnapshotIdentifier, 'algo-db-migration')]" \
  --profile root

# Wait until Status = "available"
```

---

## Phase 2: Restore RDS to New Account (15-30 minutes)

### Step 2.1: Get New Account ID

```bash
# From terraform output
NEW_ACCOUNT_ID=$(terraform output -json | jq -r '.new_account_id.value')
echo "New Account ID: $NEW_ACCOUNT_ID"
```

### Step 2.2: Copy Snapshot to New Account

```bash
# In ROOT ACCOUNT: Share snapshot with new account (ALREADY DONE by Terraform)
# But we need to restore it in the new account

# Get snapshot details
SNAPSHOT_ID=$(terraform output -json | jq -r '.rds_snapshot_id.value')

# Assume role in new account
ROLE_ARN=$(terraform output -json | jq -r '.cross_account_role_arn.value')

# Credentials for new account
NEW_CREDS=$(aws sts assume-role \
  --role-arn "$ROLE_ARN" \
  --role-session-name "terraform-migration" \
  --profile root \
  --output json)

export AWS_ACCESS_KEY_ID=$(echo $NEW_CREDS | jq -r '.Credentials.AccessKeyId')
export AWS_SECRET_ACCESS_KEY=$(echo $NEW_CREDS | jq -r '.Credentials.SecretAccessKey')
export AWS_SESSION_TOKEN=$(echo $NEW_CREDS | jq -r '.Credentials.SessionToken')

# Restore snapshot in new account
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier algo-db \
  --db-snapshot-identifier "$SNAPSHOT_ID" \
  --db-instance-class db.t4g.small \
  --multi-az false \
  --publicly-accessible false \
  --storage-encrypted true \
  --region us-east-1

echo "Restoring RDS snapshot to new account..."
echo "This takes 5-10 minutes. Monitor:"
aws rds describe-db-instances \
  --db-instance-identifier algo-db \
  --query "DBInstances[0].[DBInstanceStatus, PendingModifiedValues]" \
  --region us-east-1
```

### Step 2.3: Wait for RDS Restore

```bash
# Monitor restore progress
watch -n 10 'aws rds describe-db-instances \
  --db-instance-identifier algo-db \
  --query "DBInstances[0].DBInstanceStatus" \
  --region us-east-1'

# Wait for Status = "available"
```

---

## Phase 3: Deploy Infrastructure to New Account (10-20 minutes)

### Step 3.1: Prepare New Account Configuration

```bash
cd terraform/new-account

# Copy example to actual config
cp terraform.tfvars.example terraform.tfvars

# Edit with new account details
cat terraform.tfvars

# Update new_account_id in terraform.tfvars
# NEW_ACCOUNT_ID=$(echo $NEW_CREDS | jq -r '.Account')
sed -i "s/XXXXXXXXXX/$NEW_ACCOUNT_ID/g" terraform.tfvars
```

### Step 3.2: Initialize Terraform for New Account

```bash
# Use assumed role credentials from Step 2.2
terraform init \
  -backend-config="bucket=algo-terraform-state-$NEW_ACCOUNT_ID" \
  -backend-config="key=stocks/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="encrypt=true" \
  -backend-config="dynamodb_table=algo-terraform-locks"

# Verify connection to new account
terraform providers
# Should show: provider[registry.terraform.io/hashicorp/aws] (assumed role)
```

### Step 3.3: Deploy Infrastructure

```bash
# Plan deployment
terraform plan -var-file=terraform.tfvars -out=plan.out

# Expected resources:
#   + module.vpc (subnets, security groups, NAT)
#   + module.storage (S3 buckets with terraform state)
#   + module.database (RDS (using restored snapshot), secrets)
#   + module.iam (Lambda roles, ECS roles)
#   + module.compute (ECS cluster, ECR repository)
#   + module.loaders (ECS task definitions)
#   + module.services (Lambda functions, API Gateway, Cognito)
#   + module.pipeline (Step Functions state machines, EventBridge)
#   + module.monitoring (CloudWatch alarms, SNS topics)

# Apply deployment
terraform apply plan.out

# Monitor output for:
#   ✓ VPC created
#   ✓ RDS endpoint
#   ✓ Lambda functions deployed
#   ✓ API Gateway endpoint
#   ✓ ECS cluster ready

echo "Infrastructure deployed to new account!"
```

### Step 3.4: Verify New Infrastructure

```bash
# Get new endpoints
terraform output

# Test API Gateway
NEW_API_ENDPOINT=$(terraform output -json | jq -r '.api_gateway_endpoint.value')
curl -s "$NEW_API_ENDPOINT/api/health" | jq .

# Test RDS connectivity
NEW_RDS_ENDPOINT=$(terraform output -json | jq -r '.rds_endpoint.value')
psql -h "$NEW_RDS_ENDPOINT" -U stocks -d stocks -c "SELECT COUNT(*) FROM prices LIMIT 1;"

# List Lambda functions
aws lambda list-functions --query "Functions[].FunctionName" --region us-east-1

# List ECS tasks
aws ecs list-tasks --cluster algo-cluster --region us-east-1
```

---

## Phase 4: Verify Data & Functionality (10-15 minutes)

### Step 4.1: Check Data Integrity

```bash
# Connect to new RDS
psql -h "$NEW_RDS_ENDPOINT" -U stocks -d stocks << 'EOF'

-- Check table counts
SELECT 'prices' as table_name, COUNT(*) as row_count FROM prices
UNION ALL
SELECT 'factors', COUNT(*) FROM factors
UNION ALL
SELECT 'portfolios', COUNT(*) FROM portfolios
UNION ALL
SELECT 'positions', COUNT(*) FROM positions;

-- Verify recent price data
SELECT symbol, date, close FROM prices 
WHERE date > NOW() - INTERVAL '7 days' 
ORDER BY date DESC LIMIT 10;

-- Check for data corruption
SELECT COUNT(*) FROM prices WHERE close IS NULL OR close <= 0;
EOF
```

### Step 4.2: Test Dashboard Connection

```bash
# Set environment for new account
export AWS_REGION=us-east-1
export API_ENDPOINT="$NEW_API_ENDPOINT"

# Test dashboard in AWS mode
python dashboard.py

# Verify:
# ✓ Dashboard loads
# ✓ All 26 metrics panels populated
# ✓ No "Data not available" messages
# ✓ Recent prices visible
```

### Step 4.3: Test Orchestrator

```bash
# Trigger a morning data pipeline run
python3 scripts/trigger_morning_pipeline.py

# Monitor execution
aws stepfunctions describe-execution \
  --execution-arn $(aws stepfunctions list-executions \
    --state-machine-arn "arn:aws:states:us-east-1:$NEW_ACCOUNT_ID:stateMachine:algo-morning-prep-pipeline-dev" \
    --query "executions[0].executionArn" -o text) \
  --region us-east-1 | jq '.status'

# Wait for status = "SUCCEEDED"
```

---

## Phase 5: Switch Traffic to New Account (5 minutes)

### Step 5.1: Update DNS/Environment

```bash
# Update dashboard to use new account endpoints
# Option A: Update environment variables
export AWS_ACCOUNT_ID="$NEW_ACCOUNT_ID"

# Option B: Update ~/.aws/config default profile
aws configure set region us-east-1
aws configure set profile default

# Verify new account is active
aws sts get-caller-identity
# Should show new account ID
```

### Step 5.2: Update GitHub Secrets (if using CI/CD)

```bash
# Update GitHub Actions secrets to point to new account
gh secret set AWS_ACCOUNT_ID -b "$NEW_ACCOUNT_ID"
gh secret set AWS_ROLE_TO_ASSUME -b "arn:aws:iam::$NEW_ACCOUNT_ID:role/github-actions-role"

# Update Terraform backend reference
cd terraform
sed -i "s/626216981288/$NEW_ACCOUNT_ID/g" backend.tf
git add backend.tf
git commit -m "ci: Update Terraform backend to new account ($NEW_ACCOUNT_ID)"
git push
```

---

## Phase 6: Close Old Account (5 minutes)

### Step 6.1: Cleanup Old Account Resources

```bash
# Switch back to old account credentials
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
export AWS_PROFILE=root

# Disable RDS deletion protection (if enabled)
aws rds modify-db-instance \
  --db-instance-identifier algo-db \
  --no-deletion-protection \
  --apply-immediately

# Stop/delete old RDS database
aws rds delete-db-instance \
  --db-instance-identifier algo-db \
  --skip-final-snapshot

# Empty S3 buckets (required before account closure)
for bucket in algo-* stocks-*; do
  echo "Emptying $bucket..."
  aws s3 rm "s3://$bucket" --recursive
  aws s3api delete-bucket --bucket "$bucket"
done

# Delete Lambda functions, ECS clusters, VPC, etc.
# (They'll be deleted when we close the account, but can clean up now)

echo "Old account cleaned up"
```

### Step 6.2: Close Old Account

```bash
# Final confirmation - this is irreversible
read -p "Close account 626216981288 (edgebrookecapital@gmail.com)? (y/N) " confirm

if [ "$confirm" = "y" ]; then
  aws organizations close-account \
    --account-id 626216981288 \
    --profile root
  
  echo "Account closure requested"
  echo "Account will be fully deleted in 90 days"
  echo "You have 90 days to cancel if needed"
fi
```

### Step 6.3: Verify Closure

```bash
# Check account status
aws organizations describe-account \
  --account-id 626216981288 \
  --profile root \
  --query "Account.[Id, Name, Status, Email]"

# Expected Status: "SUSPENDED" → "CLOSED" (after 90 days)
```

---

## Phase 7: Documentation & Handoff (5 minutes)

### Step 7.1: Update Project Documentation

```bash
# Update CLAUDE.md with new account info
cat >> CLAUDE.md << 'EOF'

## Migration Complete (Session 201)
- **Old Account:** 626216981288 (edgebrookecapital@gmail.com) - CLOSED
- **New Account:** $NEW_ACCOUNT_ID (edgebrookelabs@gmail.com) - ACTIVE
- **Migration Date:** 2026-07-17
- **Data Restored:** RDS snapshot migrated successfully
- **Infrastructure:** All modules deployed and verified

### New Account Access
```bash
export AWS_ACCOUNT_ID="$NEW_ACCOUNT_ID"
aws sts get-caller-identity
```

### Post-Migration Changes
- Terraform state now in: `s3://algo-terraform-state-$NEW_ACCOUNT_ID`
- Secrets Manager updated with new account credentials
- GitHub Actions updated to use new account ID
- All data preserved from old account

### Rollback Plan (if needed)
- 90-day cancellation window on old account closure
- Contact AWS Support to reactivate if necessary
- RDS snapshot retained (can restore to new location if needed)
EOF
```

### Step 7.2: Save Migration State

```bash
# Archive migration details for future reference
mkdir -p .migrations/2026-07-17-account-migration
cp terraform/accounts/migration-state.json .migrations/2026-07-17-account-migration/
cp terraform/new-account/terraform.tfvars .migrations/2026-07-17-account-migration/
git add .migrations/
git commit -m "docs: Archive 2026-07-17 AWS account migration details"
```

---

## Timeline & Monitoring

| Phase | Task | Duration | Status |
|-------|------|----------|--------|
| 1 | Create new account via Organizations | 5-10 min | ⏳ Pending |
| 1 | Create RDS snapshot | 5-15 min | ⏳ Pending |
| 2 | Restore RDS to new account | 10-15 min | ⏳ Pending |
| 3 | Deploy infrastructure (Terraform) | 10-20 min | ⏳ Pending |
| 4 | Verify data & functionality | 10-15 min | ⏳ Pending |
| 5 | Switch traffic to new account | 5 min | ⏳ Pending |
| 6 | Close old account | 5 min | ⏳ Pending |
| 7 | Documentation & handoff | 5 min | ⏳ Pending |
| | **TOTAL** | **50-80 min** | ⏳ Pending |

---

## Troubleshooting

### Issue: RDS Snapshot Fails
```bash
# Check snapshot status
aws rds describe-db-snapshots \
  --db-snapshot-identifier algo-db-migration-YYYY-MM-DD-hhmm \
  --query "DBSnapshots[0].[Status, PercentProgress]"

# If stuck, manually create snapshot:
aws rds create-db-snapshot \
  --db-instance-identifier algo-db \
  --db-snapshot-identifier algo-db-manual-$(date +%s)
```

### Issue: Cross-Account Role Assumption Fails
```bash
# Verify role exists in new account
aws iam get-role \
  --role-name TerraformCrossAccountDeploymentRole \
  --profile root

# Check trust policy
aws iam get-role-policy \
  --role-name TerraformCrossAccountDeploymentRole \
  --policy-name AssumeRolePolicy \
  --profile root
```

### Issue: Terraform Deploy Fails
```bash
# Check new account credentials
AWS_PROFILE=new_account aws sts get-caller-identity

# Verify Terraform backend
terraform init -reconfigure -upgrade

# Enable debug logging
export TF_LOG=DEBUG
terraform apply -var-file=terraform.tfvars
```

### Issue: RDS Restore Hangs
```bash
# Check restore progress
aws rds describe-db-instances \
  --db-instance-identifier algo-db \
  --query "DBInstances[0].[DBInstanceStatus, LatestRestorableTime]"

# If stuck >30 minutes, check CloudWatch logs
aws logs describe-log-streams \
  --log-group-name /aws/rds/instance/algo-db/error \
  --order-by LastEventTime --descending --max-items 5
```

---

## Success Criteria

✅ New AWS account created (edgebrookelabs@gmail.com)
✅ RDS snapshot created and restored to new account
✅ All infrastructure deployed to new account
✅ Dashboard connects to new account API
✅ Data integrity verified (8.6M+ prices intact)
✅ Orchestrator runs successfully in new account
✅ Old account closed (90-day pending window)
✅ GitHub Actions/Terraform updated to new account

---

## Contact & Support

- **AWS Support:** [AWS Console](https://console.aws.amazon.com) → Support
- **Documentation:** See `steering/` directory
- **Rollback:** Contact AWS within 90 days to reactivate old account
