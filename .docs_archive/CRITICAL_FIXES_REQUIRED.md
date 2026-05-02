# 🚨 CRITICAL FIXES REQUIRED - Phase 2 Won't Run Without These

**Status:** 6 blocking issues preventing Phase 2 from executing in AWS

---

## ISSUE #1: GitHub Secrets Not Configured ⚠️ CRITICAL

**Why it blocks Phase 2:** GitHub Actions workflow can't authenticate to AWS without credentials

**What to do:**

Go to: https://github.com/argie33/algo/settings/secrets/actions

Add these secrets:

```
AWS_ACCOUNT_ID = 626216981288
RDS_USERNAME = stocks
RDS_PASSWORD = bed0elAn
FRED_API_KEY = 4f87c213871ed1a9508c06957fa9b577
```

**How:** 
1. Click "New repository secret"
2. Name: `AWS_ACCOUNT_ID`
3. Value: `626216981288`
4. Repeat for each secret

**Time:** 5 minutes
**Impact:** Without this, workflows won't even start

---

## ISSUE #2: AWS OIDC Provider Not Configured ⚠️ CRITICAL

**Why it blocks Phase 2:** Workflow can't assume role to deploy infrastructure

**What needs to exist in AWS:**
1. OIDC Identity Provider
2. GitHubActionsDeployRole IAM role

**How to set up:**

### Step 1: Create OIDC Identity Provider

AWS Console → IAM → Identity Providers → Add Provider

```
Provider Type: OpenID Connect
Provider URL: https://token.actions.githubusercontent.com
Audience: arn:aws:iam::626216981288:repo:argie33/algo:*
```

### Step 2: Create IAM Role for GitHub Actions

Create role named `GitHubActionsDeployRole` with trust policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::626216981288:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "arn:aws:iam::626216981288:repo:argie33/algo:*"
        }
      }
    }
  ]
}
```

### Step 3: Attach Policies to Role

Add these managed policies:
- `AWSCloudFormationFullAccess`
- `AmazonRDSFullAccess`
- `AmazonECS_FullAccess`
- `AmazonEC2FullAccess`
- `IAMFullAccess`
- `AmazonS3FullAccess`
- `AmazonEC2ContainerRegistryFullAccess`
- `SecretsManagerReadWrite`
- `CloudWatchLogsFullAccess`

**Time:** 15 minutes
**Impact:** Workflow can now authenticate and deploy

---

## ISSUE #3: CloudFormation Stack Creation Failing ⚠️ HIGH

**Why it blocks Phase 2:** Infrastructure (RDS, ECS, etc.) won't deploy

**What we need:**
1. S3 bucket for CloudFormation templates
2. Proper RDS configuration
3. Security group rules
4. VPC and subnet setup

**How to fix:**
1. Check AWS console → CloudFormation → Stacks
2. Find failed stacks
3. Look at Events tab for error message
4. Common issues:
   - S3 bucket doesn't exist
   - RDS credentials wrong
   - Security group rules missing
   - IAM role permissions insufficient

**Next:** We need to see the actual error. Check CloudFormation console.

**Time:** 30 minutes
**Impact:** Infrastructure becomes available

---

## ISSUE #4: RDS Connectivity ⚠️ MEDIUM

**Why it matters:** Loaders can't store data if they can't reach RDS

**What to verify:**

1. RDS instance exists and is running
2. Security group allows inbound on port 5432
3. Credentials work

**Test connection:**
```bash
psql -h rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com \
     -U stocks \
     -d stocks \
     -c "SELECT 1"
```

If it fails, check:
- RDS endpoint in security group rules
- ECS security group has egress to RDS on 5432
- Credentials are correct

**Time:** 10 minutes
**Impact:** Loaders can write data

---

## ISSUE #5: ECS Network Configuration ⚠️ MEDIUM

**Why it matters:** ECS tasks need to reach RDS in the same VPC

**Verify:**
- ECS tasks in same VPC as RDS
- Security groups allow traffic
- Subnets configured correctly

**Check:** CloudFormation outputs should have:
- `ECSTasksSecurityGroupId`
- `VPCId`
- `PublicSubnet1Id`
- `PublicSubnet2Id`

**Time:** 10 minutes
**Impact:** Networking becomes reliable

---

## ISSUE #6: Docker Images Not In ECR ⚠️ MEDIUM

**Why it matters:** ECS tasks can't run without Docker images

**What to check:**
1. GitHub Actions builds and pushes Docker images
2. Images exist in AWS ECR

**Fix:**
1. Ensure GitHub Actions workflow runs successfully
2. Check ECR repositories created
3. Verify images are pushed

**Time:** 5 minutes (if workflow runs, this is automatic)
**Impact:** Containers can be deployed

---

## PRIORITY ORDER - FIX THESE NOW

### RIGHT NOW (Do first):
```
1. Add GitHub Secrets (5 min) ← DO THIS
   AWS_ACCOUNT_ID, RDS credentials, API keys
   
2. Configure AWS OIDC (15 min) ← DO THIS  
   Create OIDC provider + GitHubActionsDeployRole
```

### THEN (Check after):
```
3. Verify CloudFormation (5 min)
   Check AWS console for stack status
   
4. Test RDS connection (5 min)
   Try psql to database
   
5. Check ECS/ECR (5 min)
   Verify clusters and images exist
```

### Total time: ~35 minutes

---

## COMMANDS TO RUN AFTER FIXES

Once you add GitHub secrets:

```bash
# Push a loader change to trigger workflow
git commit -am "Trigger Phase 2 workflow" --allow-empty
git push origin main
```

Then check:
```bash
# Monitor GitHub Actions
# https://github.com/argie33/algo/actions

# Monitor CloudFormation deployment
aws cloudformation list-stacks --region us-east-1

# Watch CloudWatch logs
aws logs tail /ecs/algo-loadsectors --follow
```

---

## SUCCESS CRITERIA

Phase 2 is working when you see:

✅ GitHub Actions workflow completes successfully (green checkmark)
✅ CloudFormation stacks show CREATE_COMPLETE
✅ CloudWatch logs show loader execution
✅ RDS database has new data in sector_technical_data, economic_data, etc.
✅ Execution completes in ~25 minutes (was 53 minutes)

---

## Next: Complete Data Loading

After Phase 2 works:

1. Verify Batch 5 data (should be ~150k rows)
2. Add performance metrics logging
3. Document before/after numbers
4. Move to Phase 3 (S3 staging, Lambda)

---

**Status: BLOCKED - Cannot proceed until GitHub secrets and AWS OIDC configured**

These are prerequisites, not optional.
