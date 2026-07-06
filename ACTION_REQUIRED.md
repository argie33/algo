# ACTION REQUIRED: Deploy AWS Infrastructure to Fix Dashboard Data Unavailable

## Status
✓ All code correct and tested locally  
✓ Database has all data  
✗ AWS Lambda API functions not deployed  
→ **Dashboard shows "data_unavailable" because API endpoints don't exist**

---

## What You Need to Do

### IMMEDIATE: Get AWS Admin

You need someone with **AWS admin credentials** (or full IAM permissions) to run ONE command:

```bash
cd /path/to/algo/terraform
terraform apply -lock=false -auto-approve
```

**Time**: 10-15 minutes
**What it does**: Creates Lambda functions, API Gateway, EventBridge, database schema
**Cost**: Minimal (Lambda and API Gateway free tier)

---

## Why This is Needed

Your `algo-developer` IAM user lacks read-only permissions needed to refresh terraform state:
- CloudFront policies
- DynamoDB table attributes
- SNS/EC2/S3/IAM/CloudWatch resources

This blocks any terraform apply, preventing infrastructure deployment.

---

## After AWS Admin Deploys

Verify it worked:
```bash
# 1. Check Lambda functions exist
aws lambda list-functions --region us-east-1 | grep algo

# 2. Check API responds
curl https://{API_GATEWAY_URL}/api/algo/last-run

# 3. Set dashboard URL and run
export DASHBOARD_API_URL="https://{API_GATEWAY_URL}"
python -m dashboard
```

Dashboard should now display data instead of "unavailable".

---

## Alternative: Grant Permissions to algo-developer

If AWS admin wants `algo-developer` to handle this:

Ask them to add this policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "cloudfront:ListCachePolicies",
      "cloudfront:ListOriginRequestPolicies",
      "dynamodb:DescribeTable",
      "dynamodb:DescribeContinuousBackups",
      "sns:GetTopicAttributes",
      "sns:ListTagsForResource",
      "ec2:DescribeVpcs",
      "ec2:DescribeVpcAttribute",
      "s3:GetBucketPolicy",
      "iam:GetRole",
      "iam:GetPolicy",
      "logs:ListTagsForResource",
      "logs:DescribeLogGroups",
      "events:DescribeRule",
      "events:ListTargets"
    ],
    "Resource": "*"
  }]
}
```

Then you can run: `cd terraform && terraform apply -lock=false`

---

## Evidence This Will Fix It

✓ Database layer works → 61 trades, 10.5k scores verified in database
✓ API code works → Tested locally, successfully fetches all data  
✓ Only missing piece → AWS Lambda functions to serve the API

Once deployed, dashboard endpoints will be accessible and data will display.

---

## Documentation

See these files for technical details:
- `DASHBOARD_FIX_SUMMARY.md` - Complete root cause analysis
- `terraform/` - Infrastructure code ready to deploy
- `lambda/api/routes/` - API handlers (code is correct)
