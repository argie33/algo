# Get RDS Working — Quick Start

## Run This First
```bash
./diagnose_rds.sh
```

This script checks:
- RDS instance exists and is "available"
- Secrets Manager has credentials
- Lambda environment variables are set
- VPC and security groups are configured
- Lambda CloudWatch logs for errors

## Then Follow These Steps

### If RDS Status ≠ "available"
→ Wait for instance to finish starting or check AWS Console

### If Credentials Mismatch
→ See "Reset RDS Password" in `RDS_FIX_SUMMARY.md`

### If Security Group Rules Missing
→ See "Add Missing Security Group Rules" in `RDS_FIX_SUMMARY.md`

### If CloudWatch Shows Connection Errors
→ See `RDS_CONNECTIVITY_DIAGNOSTIC.md` Step 7

## Test It Works
1. Go to AWS Lambda console → `algo-api-dev` → Test
2. Create test event:
   ```json
   {
     "rawPath": "/api/health/detailed",
     "requestContext": { "http": { "method": "GET", "path": "/api/health/detailed" } },
     "headers": {}
   }
   ```
3. Click Test
4. Should return 200 with `"dbStatus": "connected"`

## Detailed Guides
- `RDS_CONNECTIVITY_DIAGNOSTIC.md` — Complete troubleshooting steps
- `RDS_FIX_SUMMARY.md` — Quick reference for each issue type
