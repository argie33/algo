# Deployment Expectations & Issue Resolution

## Current Deployment Run
- **Workflow**: deploy-all-infrastructure.yml (manual trigger)
- **Time Started**: 2026-05-05 ~15:36 UTC
- **Skip Bootstrap**: true (OIDC already set up)
- **Run URL**: https://github.com/argie33/algo/actions/runs/25400911218

---

## Expected Sequence & What Should Happen

### Phase 1: Bootstrap (SKIPPED)
- ❌ Skip OIDC Provider (already done)

### Phase 2: Deploy Core Infrastructure
Expected timeline: ~5-10 minutes

**Pre-flight checks should:**
- ✓ Verify AWS credentials configured
- ✓ Confirm GitHubActionsDeployRole access

**Deploy should:**
- ✓ Create VPC (10.0.0.0/16)
- ✓ Create public/private subnets
- ✓ Create ECR repository (stocks-app-registry)
- ✓ Create S3 buckets (code, CF templates, algo artifacts)
- ✓ Create bastion ASG and auto-shutdown Lambda
- ✓ Create VPC endpoints for private networking
- ✓ Export: StocksCore-VpcId, -PublicSubnet1Id, -PublicSubnet2Id, -ContainerRepositoryUri, -AlgoArtifactsBucketName (18 total)

**Verify outputs should show:**
- All 18 exports available for downstream stacks

### Phase 3: Deploy Data Infrastructure
Expected timeline: ~10-15 minutes (includes RDS creation)

**Pre-flight checks should:**
- ✓ Verify stocks-core stack exists and is COMPLETE
- ✓ Verify StocksCore exports available

**Deploy should:**
- ✓ Create RDS PostgreSQL instance (public, DeletionPolicy: Retain)
- ✓ Create Secrets Manager secrets (DB creds, email config, algo secrets)
- ✓ Create ECS cluster
- ✓ Create ECS task execution role
- ✓ Create CloudWatch log groups
- ✓ Create S3 log archive bucket with lifecycle policies
- ✓ Export: StocksApp-DBEndpoint, -DBPort, -DBName, -SecretArn, -ClusterArn, -EcsTasksSecurityGroupId

### Phase 4: Parallel Deployments
After Phase 3 completes, these run in parallel:

**4a. Deploy Loaders** (~3-5 min)
- 62+ ECS task definitions
- EventBridge rules for scheduled loaders
- Export: StocksLoaders-* task definition ARNs

**4b. Deploy Webapp** (~5-10 min)
- Lambda API Gateway
- CloudFront distribution
- Cognito user pool
- S3 frontend bucket
- Export: CloudFront URL, API endpoint

**4c. Deploy Algo** (~3-5 min)
- Algo Lambda function
- EventBridge scheduler (daily 5:30pm ET)
- Export: Lambda ARN, scheduler ARN

### Phase 5: Summary & Verification
- All stacks should be CREATE_COMPLETE or UPDATE_COMPLETE
- All exports should be available
- No REVIEW_IN_PROGRESS or ROLLBACK states

---

## Potential Issues & How to Fix

### Issue 1: Stack Creation Timeout
**Symptom**: Deployment takes >30 minutes, times out  
**Cause**: RDS creation slow, Lambda zip upload slow, or CloudFormation delays  
**Fix**: 
- RDS auto-scales to 40GB max for cost control
- Check CloudWatch logs for bottlenecks
- Re-run deployment (stacks are idempotent)

### Issue 2: Permission Denied Errors
**Symptom**: "User is not authorized to perform cloudformation:CreateStack"  
**Cause**: Using wrong IAM user/role  
**Fix**:
- Verify GitHub Actions using GitHubActionsDeployRole (not "reader" user)
- Check OIDC trust policy allows GitHub repo
- Verify role has AdministratorAccess

### Issue 3: Export Not Found
**Symptom**: "Export StocksCore-XXX not found"  
**Cause**: Dependency stack didn't deploy or exports not created  
**Fix**:
- Verify previous stack is CREATE_COMPLETE (not UPDATE_COMPLETE from old deploy)
- Check stack outputs in CloudFormation console
- Re-run pre-flight checks

### Issue 4: RDS Creation Fails
**Symptom**: "Cannot create database instance"  
**Cause**: Storage quota exceeded, subnet issues, or parameter issues  
**Fix**:
- Check available RDS instances in account
- Verify VPC and subnet IDs correct
- Check RDS Parameter Group compatibility

### Issue 5: Lambda Deployment Fails
**Symptom**: "Cannot assume role" or "Code too large"  
**Cause**: Missing Lambda execution role or zip file > 50MB  
**Fix**:
- Verify EcsTaskExecutionRole created in data stack
- Check algo_orchestrator.zip size (should be <5MB)
- Verify S3 bucket has the zip file

### Issue 6: CloudFront/Cognito Issues
**Symptom**: "CloudFront distribution creation timeout" or "Cognito pool creation failed"  
**Cause**: Callback URL mismatch or security group issues  
**Fix**:
- Callback URLs should match CloudFront domain (set dynamically post-deploy)
- Check that all security groups are created
- Verify Cognito domain is unique in region

---

## Quick Diagnosis Commands

If deployment fails, run these to diagnose:

```bash
# Check all stacks and their status
python aws_diagnostic.py

# Get specific stack events (substitute stack name)
aws cloudformation describe-stack-events \
  --stack-name stocks-core \
  --query 'StackEvents[*].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]' \
  --output table

# Check if stuck in REVIEW_IN_PROGRESS
aws cloudformation list-stacks \
  --stack-status-filter REVIEW_IN_PROGRESS \
  --query 'StackSummaries[*].[StackName,StackStatus]' \
  --output table

# If stuck, run cleanup
python aws_cleanup_and_fix.py
```

---

## Success Criteria

Deployment is successful when:
- ✓ All 6 stacks in CREATE_COMPLETE or UPDATE_COMPLETE state
- ✓ All exports accessible via `aws cloudformation list-exports`
- ✓ stocks-core: VPC created, ECR/S3 buckets available
- ✓ stocks-data: RDS endpoint available, secrets created
- ✓ stocks-loaders: 62+ task definitions exported
- ✓ stocks-webapp-dev: CloudFront URL accessible
- ✓ stocks-algo-dev: Lambda scheduled in EventBridge

---

## Expected Failures & Recovery

**If Core fails**: Delete core stack, fix template, redeploy
**If Data fails**: Delete data stack, verify core intact, redeploy  
**If services fail**: Delete individual service stack, redeploy (doesn't affect others)
**If export missing**: Wait 2-3 mins for stack to stabilize, then check again

---

## Timeline Expectations

| Phase | Expected Duration | Actual Duration |
|-------|-------------------|-----------------|
| Bootstrap | skipped | - |
| Pre-flight | 2 min | - |
| Core Deploy | 5-10 min | - |
| Data Deploy | 10-15 min | - |
| Loaders Deploy | 3-5 min | - |
| Webapp Deploy | 5-10 min | - |
| Algo Deploy | 3-5 min | - |
| **Total** | **28-45 min** | - |

Longest step is RDS creation (usually 8-10 min).
