# Algo Deployment — Complete Setup Guide

**Run this guide step-by-step before deploying the algo orchestrator.**

---

## STEP 1: Verify AWS Credentials

```bash
# Check you're logged in to AWS
aws sts get-caller-identity

# Output should show:
# {
#     "UserId": "...",
#     "Account": "YOUR_ACCOUNT_ID",  ← Save this
#     "Arn": "arn:aws:iam::..."
# }
```

Save your **AWS_ACCOUNT_ID** (12-digit number).

---

## STEP 2: Create AWS Secrets (Database Credentials)

```bash
# Get your RDS endpoint
aws rds describe-db-instances \
  --query 'DBInstances[0].[DBInstanceIdentifier,Endpoint.Address]' \
  --output text

# Output: instance-name  rds-endpoint.rds.amazonaws.com

# Create secret with your RDS credentials
aws secretsmanager create-secret \
  --name stocks-db-credentials \
  --secret-string '{
    "host": "your-rds-endpoint.rds.amazonaws.com",
    "port": 5432,
    "username": "postgres",
    "password": "your-rds-password",
    "dbname": "stocks"
  }'

# Verify it was created
aws secretsmanager get-secret-value --secret-id stocks-db-credentials
# Should return the secret you just created
```

---

## STEP 3: Create AWS Secrets (Alpaca API Keys)

```bash
# Create secret with Alpaca credentials
aws secretsmanager create-secret \
  --name alpaca-api-keys \
  --secret-string '{
    "api_key": "your-alpaca-api-key",
    "api_secret": "your-alpaca-api-secret"
  }'

# Verify it was created
aws secretsmanager get-secret-value --secret-id alpaca-api-keys
# Should return the secret you just created
```

---

## STEP 4: Create S3 Bucket for Lambda Artifacts

```bash
# Create bucket with unique name
BUCKET_NAME="algo-lambda-artifacts-$(date +%s)"
aws s3 mb s3://$BUCKET_NAME

# Verify it was created
aws s3 ls s3://$BUCKET_NAME

# Save the bucket name for next step
echo "LAMBDA_ARTIFACTS_BUCKET=$BUCKET_NAME"
```

---

## STEP 5: Set Up GitHub Secrets

Go to your GitHub repository:

1. Click **Settings** (top right)
2. Left sidebar → **Secrets and variables** → **Actions**
3. Click **New repository secret**

Add these secrets:

**Secret 1: AWS_ACCOUNT_ID**
- Name: `AWS_ACCOUNT_ID`
- Value: Your 12-digit AWS account ID (from Step 1)
- Click **Add secret**

**Secret 2: LAMBDA_ARTIFACTS_BUCKET**
- Name: `LAMBDA_ARTIFACTS_BUCKET`
- Value: Bucket name from Step 4 (e.g., `algo-lambda-artifacts-1715000000`)
- Click **Add secret**

**Verify:**
- You should see both secrets listed on the Secrets page
- Don't show the values in console logs

---

## STEP 6: Set Up GitHub OIDC & IAM Role

Run these AWS CLI commands:

```bash
# 1. Create GitHub OIDC Provider (one-time)
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 2>/dev/null || \
  echo "OIDC provider already exists"

# 2. Create GitHub Actions Deployment Role
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REPO_OWNER="your-github-username"
REPO_NAME="algo"

cat > /tmp/trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:${REPO_OWNER}/${REPO_NAME}:ref:refs/heads/main"
        }
      }
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name GitHubActionsDeployRole \
  --assume-role-policy-document file:///tmp/trust-policy.json 2>/dev/null || \
  echo "Role already exists"

# 3. Attach necessary policies to role
aws iam put-role-policy \
  --role-name GitHubActionsDeployRole \
  --policy-name GitHubActionsDeployPolicy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "cloudformation:*",
          "lambda:*",
          "events:*",
          "iam:GetRole",
          "iam:PassRole",
          "iam:CreateRole",
          "iam:PutRolePolicy",
          "secretsmanager:GetSecretValue",
          "s3:*"
        ],
        "Resource": "*"
      }
    ]
  }'

# Verify role was created
aws iam get-role --role-name GitHubActionsDeployRole
```

---

## STEP 7: Verify All Prerequisites

```bash
echo "═══════════════════════════════════════════════════════"
echo "VERIFICATION CHECKLIST"
echo "═══════════════════════════════════════════════════════"

echo ""
echo "✓ AWS Secrets..."
aws secretsmanager get-secret-value --secret-id stocks-db-credentials > /dev/null && \
  echo "  ✅ stocks-db-credentials" || echo "  ❌ stocks-db-credentials MISSING"
aws secretsmanager get-secret-value --secret-id alpaca-api-keys > /dev/null && \
  echo "  ✅ alpaca-api-keys" || echo "  ❌ alpaca-api-keys MISSING"

echo ""
echo "✓ S3 Bucket..."
# Replace with your bucket name
BUCKET="algo-lambda-artifacts-YOUR_TIMESTAMP"
aws s3 ls s3://$BUCKET > /dev/null 2>&1 && \
  echo "  ✅ S3 bucket exists" || echo "  ❌ S3 bucket not found"

echo ""
echo "✓ GitHub Secrets..."
echo "  Check GitHub UI → Settings → Secrets:"
echo "    AWS_ACCOUNT_ID = $(aws sts get-caller-identity --query Account --output text)"
echo "    LAMBDA_ARTIFACTS_BUCKET = (check manually in GitHub)"

echo ""
echo "✓ OIDC Provider..."
aws iam list-open-id-connect-providers | grep -q token.actions.githubusercontent && \
  echo "  ✅ OIDC provider exists" || echo "  ❌ OIDC provider missing"

echo ""
echo "✓ IAM Role..."
aws iam get-role --role-name GitHubActionsDeployRole > /dev/null 2>&1 && \
  echo "  ✅ GitHubActionsDeployRole exists" || echo "  ❌ Role missing"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "If all checks pass, you're ready to deploy!"
echo "═══════════════════════════════════════════════════════"
```

---

## STEP 8: Deploy the Algo Orchestrator

Once all prerequisites are verified, deploy:

```bash
# Option A: Automatic deployment (push to main)
git push origin main

# GitHub Actions will automatically:
# 1. Trigger deploy-algo-orchestrator.yml
# 2. Validate algo components
# 3. Install dependencies
# 4. Package code
# 5. Deploy Lambda function
# 6. Deploy EventBridge rule
# 7. Algo will run daily at 5:30pm ET

# Track deployment progress:
# Go to GitHub → Actions → Deploy Algo Orchestrator
# Watch for green checkmarks (success) or red X (failure)
```

---

## STEP 9: Verify Deployment Success

After push completes, verify:

```bash
# 1. Check CloudFormation stack was created
aws cloudformation describe-stacks \
  --stack-name stocks-algo-orchestrator \
  --query 'Stacks[0].StackStatus'
# Should return: CREATE_COMPLETE

# 2. Check Lambda function exists
aws lambda get-function --function-name algo-orchestrator
# Should return function details

# 3. Check EventBridge rule exists
aws events describe-rule --name algo-eod-orchestrator
# Should show rule with state: ENABLED

# 4. Check SNS topic was created
aws sns list-topics | grep algo-orchestrator-alerts
# Should list the topic

# 5. View Lambda logs
aws logs tail /aws/lambda/algo-orchestrator --follow
```

---

## STEP 10: Test Algo Execution

```bash
# Test with dry-run (preview trades, no execution)
aws lambda invoke \
  --function-name algo-orchestrator \
  --payload '{"dry_run": true}' \
  /tmp/response.json

# View response
cat /tmp/response.json | jq .

# View execution logs
aws logs tail /aws/lambda/algo-orchestrator --follow
```

---

## TROUBLESHOOTING

### CloudFormation deployment fails

```bash
# Check what went wrong
aws cloudformation describe-stack-events \
  --stack-name stocks-algo-orchestrator \
  --query 'StackEvents[0:5]'

# Common issues:
# - SecurityGroup/VPC not found → Check EC2 security groups exist
# - IAM role permissions → Check GitHubActionsDeployRole has correct policies
# - Lambda code zip invalid → Check S3 bucket exists and is accessible
```

### Lambda can't connect to database

```bash
# Check RDS security group allows Lambda
aws ec2 describe-security-groups \
  --group-ids sg-xxxxx \
  --query 'SecurityGroups[0].IpPermissions'

# Lambda needs:
# - Inbound rule: Port 5432, source = VPC CIDR or Lambda security group
```

### EventBridge rule not triggering

```bash
# Check rule is enabled
aws events describe-rule --name algo-eod-orchestrator

# Enable if disabled
aws events enable-rule --name algo-eod-orchestrator

# Check targets
aws events list-targets-by-rule --rule algo-eod-orchestrator
```

---

## DAILY OPERATION

After deployment, the algo will:

**Every day at 5:30pm ET (market close):**
1. EventBridge triggers Lambda automatically
2. Lambda runs: patrol → load → remediate → orchestrator
3. Sends SNS alert (success or failure)
4. All logs in CloudWatch

**Monitor:**
```bash
# Watch logs live
aws logs tail /aws/lambda/algo-orchestrator --follow

# Subscribe to SNS alerts
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:algo-orchestrator-alerts-dev \
  --protocol email \
  --notification-endpoint your@email.com
```

---

## See Also

- `ALGO_DEPLOYMENT.md` — Architecture details
- `AWS_DEPLOYMENT.md` — AWS infrastructure overview
- `TROUBLESHOOTING.md` — Common issues
