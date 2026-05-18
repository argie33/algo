# Infrastructure Deployment Runbook

**Last Updated:** 2026-05-18  
**Status:** Ready for execution  
**Estimated Time:** 2-3 hours

## Prerequisites

Before starting, ensure you have:
- [ ] AWS account with admin access
- [ ] AWS CLI installed and configured: `aws configure`
- [ ] Terraform installed: `terraform version` (should be 1.7+)
- [ ] Git push access to main repository
- [ ] PostgreSQL running locally (for testing): `psql -U postgres`

---

## Phase 1: VPC Cleanup (30-45 minutes)

**⚠️ CRITICAL:** Clean up orphaned VPCs before deploying new infrastructure.  
Recent git history shows multiple VPC creation attempts. We need a single Terraform-managed VPC.

### Step 1.1: Audit Current VPCs

```bash
# List all VPCs in account
aws ec2 describe-vpcs --query 'Vpcs[*].[VpcId,CidrBlock,Tags]' --output table

# Expected output: Should see ~3 VPCs. Find the one with tag "ManagedBy=Terraform"
# Example:
# vpc-xxxxx1 | 10.0.0.0/16 | [{Key: Name, Value: algo-vpc-dev}, {Key: ManagedBy, Value: Terraform}]
# vpc-xxxxx2 | 10.1.0.0/16 | [{Key: Name, Value: algo-vpc}] <- no ManagedBy tag (DELETE)
# vpc-xxxxx3 | 10.2.0.0/16 | [] <- no tags (DELETE)
```

**Document the VPC IDs:**
```
TERRAFORM_VPC_ID = vpc-xxxxxxxxxxxxxx  (should have ManagedBy=Terraform tag)
ORPHAN_VPC_ID_1 = vpc-yyyyyyyyyyyy     (to delete)
ORPHAN_VPC_ID_2 = vpc-zzzzzzzzzzzz     (to delete)
```

### Step 1.2: Find Dependencies of Orphaned VPCs

For each orphaned VPC, delete associated resources:

```bash
# For ORPHAN_VPC_ID_1:
VPC_ID="vpc-yyyyyyyyyyyy"

# 1. Find and terminate EC2 instances
aws ec2 describe-instances --filters "Name=vpc-id,Values=$VPC_ID" --query 'Reservations[*].Instances[*].InstanceId' --output text
# If any instances: aws ec2 terminate-instances --instance-ids i-xxxxx i-yyyyy

# 2. Find and delete ENIs (Elastic Network Interfaces)
aws ec2 describe-network-interfaces --filters "Name=vpc-id,Values=$VPC_ID" --query 'NetworkInterfaces[*].[NetworkInterfaceId,Description]' --output table
# If any ENIs not in use: aws ec2 delete-network-interface --network-interface-id eni-xxxxx

# 3. Find and delete RDS instances
aws rds describe-db-instances --query "DBInstances[?DBSubnetGroup.VpcSecurityGroupMemberships[?VpcId=='$VPC_ID']].DBInstanceIdentifier" --output text
# If any RDS: aws rds delete-db-instance --db-instance-identifier xxx --skip-final-snapshot

# 4. Delete ECS clusters
aws ecs list-clusters --query 'clusterArns[*]' --output text | while read arn; do
  CLUSTER_NAME=$(echo $arn | cut -d'/' -f2)
  aws ecs list-container-instances --cluster $CLUSTER_NAME --query 'containerInstanceArns[*]' --output text | while read ci; do
    aws ecs deregister-container-instance --cluster $CLUSTER_NAME --container-instance $ci --force
  done
done

# 5. Delete Security Groups
aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" --query 'SecurityGroups[*].[GroupId,GroupName]' --output table
# For each SG (except default): aws ec2 delete-security-group --group-id sg-xxxxx

# 6. Delete subnets
aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query 'Subnets[*].SubnetId' --output text
# For each subnet: aws ec2 delete-subnet --subnet-id subnet-xxxxx

# 7. Finally, delete the VPC
aws ec2 delete-vpc --vpc-id $VPC_ID
echo "✅ Deleted VPC: $VPC_ID"
```

### Step 1.3: Verify Cleanup

```bash
# Confirm orphaned VPCs are gone
aws ec2 describe-vpcs --query 'Vpcs[*].VpcId' --output text

# Should only show: vpc-xxxxxxxxxxxxxx (Terraform-managed)
```

---

## Phase 2: Initialize Terraform (15 minutes)

### Step 2.1: Navigate to Terraform Directory

```bash
cd terraform/
pwd  # Verify you're in the terraform/ directory
```

### Step 2.2: Configure Terraform State Backend

```bash
# Initialize Terraform (reads S3 backend config)
terraform init \
  -backend-config="bucket=stocks-terraform-state" \
  -backend-config="key=stocks/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="encrypt=true" \
  -reconfigure

# Output should show:
# ✓ Backend initialized
# ✓ Modules installed
```

### Step 2.3: Validate Configuration

```bash
terraform validate
# Should output: "Success! The configuration is valid."
```

---

## Phase 3: Review & Plan Terraform Changes (15 minutes)

### Step 3.1: Generate Terraform Plan

```bash
terraform plan -out=tfplan

# Review the output - should see resources for:
# ✓ VPC (1)
# ✓ Subnets (3)
# ✓ RDS (database)
# ✓ Lambda functions (api, algo, db-init)
# ✓ API Gateway
# ✓ CloudFront
# ✓ S3 buckets
# ✓ ECS cluster

# If you see "No changes", infrastructure is already created
```

### Step 3.2: Review Plan Details

```bash
# Show specific resource changes
terraform show tfplan | grep -E "resource|->|changed"

# Check outputs that will be available after apply
terraform plan -out=tfplan -json | grep -A5 "outputs"
```

---

## Phase 4: Apply Terraform (30-45 minutes)

### Step 4.1: Apply Infrastructure

```bash
# PRODUCTION: Apply the plan
terraform apply tfplan

# Progress:
# - VPC: 1-2 min
# - RDS: 10-15 min (longest step)
# - Lambda: 2-3 min
# - API Gateway: 1-2 min
# - CloudFront: 2-3 min
```

### Step 4.2: Capture Outputs

```bash
# Display all outputs
terraform output

# Save to file for reference
terraform output -json > terraform-outputs.json

# Key outputs to note:
# - api_gateway_endpoint: The API URL (e.g., https://xxxxx.execute-api.us-east-1.amazonaws.com/dev)
# - cloudfront_domain_name: The frontend URL (e.g., d123456.cloudfront.net)
# - rds_endpoint: Database endpoint (e.g., algo-rds-dev.xxxxx.us-east-1.rds.amazonaws.com)

API_URL=$(terraform output -raw api_gateway_endpoint 2>/dev/null || echo "NOT_AVAILABLE")
FRONTEND_URL=$(terraform output -raw cloudfront_domain_name 2>/dev/null || echo "NOT_AVAILABLE")

echo "✅ API URL: $API_URL"
echo "✅ Frontend URL: https://$FRONTEND_URL"
```

### Step 4.3: Verify AWS Resources

```bash
# Verify API Gateway created
aws apigateway get-apis --query 'Items[*].[Id,Name]' --output table

# Verify Lambda functions deployed
aws lambda list-functions --query 'Functions[*].[FunctionName,Runtime]' --output table | grep algo

# Verify RDS running
aws rds describe-db-instances --query 'DBInstances[*].[DBInstanceIdentifier,DBInstanceStatus]' --output table

# Verify S3 frontend bucket exists
aws s3 ls | grep frontend

# Verify CloudFront distribution
aws cloudfront list-distributions --query 'DistributionList.Items[*].[Id,DomainName]' --output table
```

---

## Phase 5: Set GitHub Actions Secrets (5 minutes)

### Step 5.1: Get API Endpoint from Terraform

```bash
API_URL=$(terraform output -raw api_gateway_endpoint)
echo $API_URL
# Copy this URL
```

### Step 5.2: Add GitHub Secret

```bash
# Option 1: Using GitHub CLI (recommended)
gh secret set API_GATEWAY_URL --body "$API_URL"

# Option 2: Via GitHub Web UI
# 1. Go to: https://github.com/argie33/algo/settings/secrets/actions
# 2. Click "New repository secret"
# 3. Name: API_GATEWAY_URL
# 4. Value: [paste API URL from above]
# 5. Click "Add secret"

echo "✅ Secret set: API_GATEWAY_URL=$API_URL"
```

### Step 5.3: Verify Secret

```bash
gh secret list | grep API_GATEWAY_URL
# Should show API_GATEWAY_URL when listed
```

---

## Phase 6: Deploy Application Code (10 minutes)

### Step 6.1: Trigger Deployment via Git Push

```bash
cd /path/to/algo  # Go back to repo root

# Ensure main branch is up to date
git pull origin main

# Push a commit to trigger GitHub Actions
git log --oneline -1
# (if there are uncommitted changes)
git add -A
git commit -m "deploy: Trigger application deployment after infrastructure setup"
git push origin main

# Alternative: Use workflow_dispatch
# gh workflow run deploy-code.yml --ref main
```

### Step 6.2: Monitor Deployment

```bash
# Watch GitHub Actions
gh run list --limit 3

# Monitor a specific run
gh run watch <RUN_ID>

# Check frontend build logs
gh run view <RUN_ID> --log

# Expected steps:
# 1. Resolve Infrastructure (2 min)
# 2. Deploy Algo Lambda (3 min)
# 3. Deploy API Lambda (3 min)
# 4. Deploy DB Init Lambda (2 min)
# 5. Build & Deploy Frontend (5 min)
```

---

## Phase 7: Verify Deployment (15-20 minutes)

### Step 7.1: Test API Endpoint

```bash
API_URL=$(terraform output -raw api_gateway_endpoint)

# Test health endpoint
curl -v "$API_URL/health"
# Expected: HTTP 200 with {"status":"ok"} or similar

# Test actual endpoint
curl -s "$API_URL/api/sectors" | jq '.' | head -20

# Expected: JSON response with sector data
```

### Step 7.2: Test Frontend

```bash
# Get frontend URL
FRONTEND_URL="https://$(terraform output -raw cloudfront_domain_name)"

# Open in browser or curl
curl -I "$FRONTEND_URL"
# Expected: HTTP 200

# Full page load
curl "$FRONTEND_URL" | head -50
# Should see HTML content
```

### Step 7.3: Test Database Connection from Lambda

```bash
# Invoke API Lambda with test request
aws lambda invoke \
  --function-name algo-api-dev \
  --payload '{"requestContext":{"http":{"method":"GET","path":"/health"}}}' \
  /tmp/response.json

cat /tmp/response.json | jq .

# Expected: statusCode 200
```

### Step 7.4: Check Logs

```bash
# API Lambda logs
aws logs tail /aws/lambda/algo-api-dev --follow

# Check for errors - should see:
# - Database connection successful
# - API endpoints registered
# - No authentication errors (initially)

# Stop tailing: Ctrl+C
```

### Step 7.5: Full Integration Test

```bash
# 1. Open frontend in browser
FRONTEND_URL="https://$(terraform output -raw cloudfront_domain_name)"
echo "Open: $FRONTEND_URL"

# 2. Check browser console (F12 → Console)
# Look for any errors or failed API calls

# 3. Navigate to a dashboard page (e.g., Scores)
# Should load data without errors

# 4. If errors appear, check:
# - API endpoint in frontend config matches Terraform output
# - API Gateway CORS settings allow CloudFront domain
# - Lambda has database credentials via Secrets Manager
```

---

## Phase 8: Troubleshooting

### Issue: API Gateway returns 502 Bad Gateway

```bash
# Probable cause: Lambda doesn't have database credentials

# Fix:
aws lambda get-function-configuration --function-name algo-api-dev | jq '.Environment.Variables'

# Should show:
# DB_SECRET_ARN: "arn:aws:secretsmanager:..."
# DB_ENDPOINT: "algo-rds-dev.xxxxx.rds.amazonaws.com"

# If missing, update Lambda:
aws lambda update-function-configuration \
  --function-name algo-api-dev \
  --environment Variables={DB_SECRET_ARN=arn:aws:secretsmanager:...,DB_ENDPOINT=...}
```

### Issue: Frontend can't connect to API

```bash
# Probable cause: CORS headers not allowing CloudFront

# Check API Gateway CORS settings
aws apigateway get-rest-api --rest-api-id <API_ID> | jq '.description'

# Update API Gateway CORS if needed:
# terraform apply -target=aws_apigatewayv2_api.main -var 'api_cors_allowed_origins=["https://cloudfront-domain.com"]'
```

### Issue: Database says "connection refused"

```bash
# Check RDS security group
RDS_SG=$(aws rds describe-db-instances --db-instance-identifier algo-rds-dev --query 'DBInstances[0].VpcSecurityGroups[0].VpcSecurityGroupId' --output text)

# Verify inbound rules allow Lambda SG
aws ec2 describe-security-groups --group-ids $RDS_SG --query 'SecurityGroups[0].IpPermissions' | jq '.'

# Should allow:
# - Source: api_lambda_security_group_id (port 5432)
# - Source: algo_lambda_security_group_id (port 5432)
```

### Issue: Terraform state locked

```bash
# If you see "Error acquiring the lock"

# Option 1: Wait (someone else is applying)
sleep 60
terraform apply

# Option 2: Force unlock (use carefully)
terraform force-unlock <LOCK_ID>

# Check lock status
terraform force-unlock -help
```

---

## Success Criteria

After following this runbook, verify:

- [ ] VPC cleanup complete (only 1 VPC remains)
- [ ] Terraform apply succeeded (all resources created)
- [ ] API health endpoint returns 200
- [ ] Frontend loads and displays data
- [ ] API calls from frontend succeed (check browser console)
- [ ] Logs show no errors
- [ ] Lambda functions have database credentials

---

## Rollback Plan

If something goes wrong:

```bash
# Option 1: Destroy and start over
terraform destroy

# Option 2: Revert specific resources
terraform apply -target=<resource> -auto-approve

# Option 3: Check git for last working state
git log --oneline terraform/ | head -5
git show <COMMIT>:terraform/main.tf
```

---

## Post-Deployment

After successful deployment:

1. **Update documentation**
   ```bash
   # Update README.md with new API endpoint and frontend URL
   API_URL=$(terraform output -raw api_gateway_endpoint)
   FRONTEND_URL=$(terraform output -raw cloudfront_domain_name)
   
   # Edit README.md:
   # API: $API_URL
   # Frontend: https://$FRONTEND_URL
   ```

2. **Load initial data**
   ```bash
   # Run data loading pipeline
   python3 run-all-loaders.py
   ```

3. **Enable monitoring**
   ```bash
   # Set up CloudWatch dashboards
   aws cloudwatch put-dashboard --dashboard-name algo-prod \
     --dashboard-body file://terraform/modules/monitoring/dashboard.json
   ```

4. **Configure backups**
   ```bash
   # Verify RDS automated backups
   aws rds describe-db-instances --db-instance-identifier algo-rds-dev \
     --query 'DBInstances[0].[BackupRetentionPeriod,PreferredBackupWindow]'
   ```

---

## Support

If issues persist:

1. Check CloudWatch Logs: `aws logs tail /aws/lambda/algo-api-dev --follow`
2. Review Terraform state: `terraform show`
3. Check AWS console for resource details
4. Refer to CLEANUP_AUDIT.md for known issues

**Last tested:** 2026-05-18  
**Maintainer:** DevOps Team
