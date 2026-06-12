# Dashboard AWS Access Guide

The dashboard now runs in **AWS-only mode** and no longer falls back to localhost. This ensures all data comes from the production AWS environment.

## Problem: RDS Proxy is VPC-Internal

The RDS proxy (`algo-rds-proxy-dev.proxy-cojggi2mkthi.us-east-1.rds.amazonaws.com`) is intentionally VPC-internal and cannot be accessed from local machines for security reasons.

## Solution: Use Lambda API Endpoint

Instead of connecting directly to RDS, the dashboard can connect to the **Lambda API** (`algo-api-dev`) which has VPC access and can reach the RDS proxy.

### Setup

1. **Get the API endpoint URL** from AWS:
   ```powershell
   # Option A: From Terraform outputs
   terraform -chdir=terraform output api_url
   
   # Option B: From AWS CLI (requires permissions)
   aws apigatewayv2 get-apis --region us-east-1 --query 'Items[?contains(Name, `algo-api`)].[ApiEndpoint]' --output text
   ```

2. **Set environment variable** before running dashboard:
   ```powershell
   $env:DASHBOARD_API_URL = "https://<api-endpoint-from-above>"
   python tools/dashboard/dashboard.py
   ```

   Or set it permanently in your PowerShell profile:
   ```powershell
   $PROFILE # Print the path to your profile
   # Edit that file and add:
   $env:DASHBOARD_API_URL = "https://your-api-endpoint"
   ```

3. **Run dashboard**:
   ```powershell
   python tools/dashboard/dashboard.py
   ```

## Alternative: VPN/Bastion Access (Advanced)

If you have VPN or bastion access to AWS:

1. Connect to VPN or establish bastion tunnel
2. Verify RDS proxy is reachable:
   ```powershell
   Test-NetConnection -ComputerName algo-rds-proxy-dev.proxy-cojggi2mkthi.us-east-1.rds.amazonaws.com -Port 5432
   ```
3. Set DB credentials in environment:
   ```powershell
   $env:DB_HOST = "algo-rds-proxy-dev.proxy-cojggi2mkthi.us-east-1.rds.amazonaws.com"
   $env:DB_PORT = "5432"
   $env:DB_USER = "stocks"
   $env:DB_PASSWORD = "..." # From AWS Secrets Manager or local env
   $env:DB_NAME = "stocks"
   ```
4. Run dashboard:
   ```powershell
   python tools/dashboard/dashboard.py
   ```

## Troubleshooting

### Error: "Cannot reach AWS RDS"

**Cause:** RDS proxy is VPC-internal and your local machine is not in the VPC.

**Fix:** Use the Lambda API endpoint (see Setup above) or establish VPN/bastion access.

### Error: "AWS Secrets Manager: Access Denied"

**Cause:** IAM role/user doesn't have permission to access Secrets Manager.

**Fix:** 
- Use environment variables instead: `DB_PASSWORD=$env:DB_PASSWORD python tools/dashboard/dashboard.py`
- Or grant IAM permissions to your user/role for `secretsmanager:GetSecretValue`

### Error: "Credentials not found"

**Cause:** Missing DB_PASSWORD or AWS Secrets Manager not accessible.

**Fix:**
```powershell
# Set credentials via environment
$env:DB_PASSWORD = "your-password"
python tools/dashboard/dashboard.py
```

## Credentials Priority Order

The dashboard uses `credential_manager.py` which fetches credentials in this order:

1. **Environment variables** (`DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT`)
2. **AWS Secrets Manager** (`DB_SECRET_ARN` or `algo-db-credentials` secret)
3. **Cached credentials** (from previous fetch, if available)
4. **Fail fast** with clear error message

This is why setting environment variables is the fastest local development approach.
