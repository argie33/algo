# AWS Reachability Blocker - Solution Required

## Current Status

Dashboard is **configured for AWS-only** but **AWS is NOT reachable** because:

1. **RDS Proxy is VPC-Internal** (expected, by design)
   - `algo-rds-proxy-dev.proxy-cojggi2mkthi.us-east-1.rds.amazonaws.com` cannot be reached from local machines
   - This is intentional security isolation

2. **Lambda API Endpoint Not Configured** (blocker)
   - Endpoint is deployed but endpoint URL is not available to the dashboard
   - Requires one of these to obtain the endpoint:
     - Terraform state access (S3 backend)
     - AWS API Gateway permissions
     - AWS Lambda function URL permissions

3. **IAM Permissions Missing**
   - `algo-developer` user lacks:
     - `secretsmanager:ListSecrets` (to find credentials)
     - `apigateway:GetApis` (to find API endpoint)
     - S3 access to Terraform state backend

## Solution: Get the API Endpoint

### Step 1: Ask Your AWS Admin to Run This

Have someone with AWS admin access run:

```bash
./scripts/get-api-endpoint-admin.sh
```

This script will:
- Check Terraform outputs
- Query AWS API Gateway
- Check Lambda function URLs
- Return the endpoint URL

### Step 2: They Send You the Endpoint

It will look like one of these:
```
https://abc123def.execute-api.us-east-1.amazonaws.com
https://abc123def.lambda-url.us-east-1.on.aws
```

### Step 3: You Configure the Dashboard

Once you have the endpoint, set it:

```powershell
$env:DASHBOARD_API_URL = "https://the-endpoint-from-admin"
python tools/dashboard/dashboard.py
```

Or add to PowerShell profile for permanent configuration:

```powershell
# Add to $PROFILE
$env:DASHBOARD_API_URL = "https://the-endpoint-from-admin"
```

## Alternative: Grant Permissions

If you want `algo-developer` to be able to get the endpoint itself, ask your AWS admin to grant these IAM permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "apigateway:GetApis",
        "apigateway:GetApiEndpoint",
        "lambda:GetFunctionUrlConfig"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::*terraform*state*"
    }
  ]
}
```

Then the setup script will work automatically:

```powershell
./scripts/setup-dashboard-aws.ps1
```

## Current Architecture

```
┌──────────────────────────────┐
│  Dashboard (AWS-only mode)   │
│  Waiting for API endpoint    │
└──────────────┬───────────────┘
               │
               ├─→ [BLOCKED] RDS Proxy (VPC-internal)
               │
               └─→ [BLOCKED] Lambda API (endpoint unknown)
                       ↓
                  Admin needs to provide:
                  - Endpoint URL from Terraform
                  - Or IAM permissions to discover it
```

## Files That Help

- `scripts/get-api-endpoint-admin.sh` - For admin to run (gets endpoint)
- `scripts/setup-dashboard-aws.ps1` - For you to run (needs permissions)
- `scripts/verify-dashboard-aws.ps1` - For you to verify setup
- `docs/DASHBOARD-AWS-SETUP.md` - Complete setup guide

## Summary

**You Cannot Proceed Without:**
1. The Lambda API endpoint URL from your AWS admin, OR
2. IAM permissions to discover it yourself

**Next Action:**
1. Share `scripts/get-api-endpoint-admin.sh` with your AWS admin
2. Ask them to run it and send you the endpoint URL
3. Set `$env:DASHBOARD_API_URL` to that URL
4. Dashboard will then work with AWS data

## Why This Is Happening

- **RDS VPC-internal**: Security best practice - database is not exposed to the internet
- **API Gateway not accessible**: IAM role for `algo-developer` was intentionally restricted
- **Terraform state not accessible**: S3 backend is restricted to admins only

This is intentional security isolation. The dashboard is ready to use AWS data once you have the endpoint URL.
