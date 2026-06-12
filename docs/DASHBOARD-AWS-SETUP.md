# Dashboard AWS Setup - Complete Guide

## What Was Changed

The dashboard has been converted to **AWS-only mode** - it no longer falls back to localhost and exclusively connects to AWS data sources.

### Changes Made:
1. **Removed localhost fallback** - dashboard always attempts AWS connection
2. **Integrated credential_manager.py** - centralized credential handling with Secrets Manager support
3. **Improved error messaging** - clear, actionable guidance when AWS is unreachable
4. **Created setup scripts** - automated tools to configure AWS access
5. **Added documentation** - comprehensive guides for different access methods

## Quick Start

### Step 1: Verify AWS Configuration
```powershell
./scripts/verify-dashboard-aws.ps1
```

This checks:
- AWS credentials are loaded ✓
- Dashboard code is AWS-only ✓
- credential_manager.py is configured ✓
- RDS proxy connectivity status

### Step 2: Set Up AWS Access (Choose One)

#### Option A: Lambda API Endpoint (RECOMMENDED)
```powershell
./scripts/setup-dashboard-aws.ps1
```
This script:
- Auto-detects Lambda API endpoint
- Tests connectivity
- Configures DASHBOARD_API_URL environment variable

#### Option B: VPN/Bastion Access (Advanced)
1. Connect to AWS VPN or establish bastion tunnel
2. Verify connectivity: `Test-NetConnection algo-rds-proxy-dev.proxy-cojggi2mkthi.us-east-1.rds.amazonaws.com -Port 5432`
3. Run dashboard (will connect directly to RDS)

#### Option C: Manual Configuration (Advanced)
```powershell
# Get API endpoint from Terraform
$env:DASHBOARD_API_URL = terraform -chdir=terraform output api_url

# Or set database credentials directly (requires VPN/bastion)
$env:DB_HOST = "algo-rds-proxy-dev.proxy-cojggi2mkthi.us-east-1.rds.amazonaws.com"
$env:DB_PASSWORD = "from-secrets-manager-or-env"
```

### Step 3: Run Dashboard
```powershell
python tools/dashboard/dashboard.py
```

## How It Works

### Credential Flow

```
┌─────────────────────────────────────┐
│ Run: python tools/dashboard.py       │
└────────────┬────────────────────────┘
             │
             ↓
┌─────────────────────────────────────┐
│ Dashboard (AWS-only mode)           │
│ - Always uses RDS proxy endpoint     │
│ - No localhost fallback             │
└────────────┬────────────────────────┘
             │
             ↓
┌─────────────────────────────────────┐
│ credential_manager.py                │
│ Priority:                            │
│ 1. Environment variables             │
│ 2. AWS Secrets Manager               │
│ 3. Cached credentials                │
└────────────┬────────────────────────┘
             │
             ↓
    ┌────────┴────────┐
    ↓                 ↓
┌──────────┐      ┌──────────────┐
│ AWS RDS  │      │ Lambda API    │
│ (direct) │      │ (via HTTP)    │
└──────────┘      └──────────────┘
```

### Connectivity Solutions

| Problem | Solution | Setup Time | Pros | Cons |
|---------|----------|-----------|------|------|
| RDS is VPC-internal | Lambda API | 2 min | No infrastructure needed | Requires API endpoint |
| Can't reach API | VPN/Bastion | 5-10 min | Direct access | Requires AWS access setup |
| Want local database | Localhost | N/A | Simple | Not production data |

## Architecture

### Why AWS-Only?

Production dashboard should never silently switch to development data. The AWS-only mode ensures:

✓ Always using production data source
✓ No accidental localhost fallback
✓ Clear error messages when AWS unreachable
✓ Consistent with production Lambda deployment

### Why Not Direct RDS?

The RDS proxy (`algo-rds-proxy-dev.proxy-cojggi2mkthi.us-east-1.rds.amazonaws.com`) is intentionally VPC-internal for security:

- ✓ Prevents external access to database
- ✓ Requires authentication for VPC access
- ✓ Limits blast radius of credentials

Local machines can access AWS data via:
1. **Lambda API** - Best for development (HTTP endpoint, no VPN needed)
2. **VPN/Bastion** - For advanced users with AWS access
3. **Direct tunnel** - For CI/CD environments

## Troubleshooting

### "Could not translate host name"
RDS proxy is not reachable. This is normal on local machines.

**Fix:** Run `./scripts/setup-dashboard-aws.ps1` to use Lambda API endpoint.

### "AWS Secrets Manager: Access Denied"
IAM user doesn't have Secrets Manager permission.

**Fix:** Set credentials via environment variables:
```powershell
$env:DB_PASSWORD = "your-password"
python tools/dashboard/dashboard.py
```

### "API endpoint not found"
setup-dashboard-aws.ps1 couldn't auto-detect endpoint.

**Fix:** Get manually from Terraform:
```powershell
terraform -chdir=terraform output api_url
$env:DASHBOARD_API_URL = "https://..." # use output value
```

### "Connection timeout"
API or RDS is slow or unreachable.

**Check:**
1. Verify AWS credentials: `aws sts get-caller-identity`
2. Test API: `Invoke-WebRequest -Uri $env:DASHBOARD_API_URL/health`
3. Check network: `Test-NetConnection algo-rds-proxy-dev.proxy-cojggi2mkthi.us-east-1.rds.amazonaws.com -Port 5432`

## Files Changed

```
tools/dashboard/dashboard.py          # AWS-only mode, credential_manager integration
config/credential_manager.py          # (unchanged - already supports this)
Documents/PowerShell/profile.ps1      # Updated with AWS setup examples
scripts/setup-dashboard-aws.ps1       # NEW: Auto-configure API endpoint
scripts/verify-dashboard-aws.ps1      # NEW: Verify AWS configuration
docs/dashboard-aws-access.md          # NEW: Detailed access guide
docs/DASHBOARD-AWS-SETUP.md           # THIS FILE
```

## Environment Variables

### For Local Development

```powershell
# Use Lambda API endpoint (recommended)
$env:DASHBOARD_API_URL = "https://your-api-endpoint.lambda-url.us-east-1.on.aws"

# Or use direct RDS access (requires VPN/bastion or Secrets Manager access)
$env:DB_HOST = "algo-rds-proxy-dev.proxy-cojggi2mkthi.us-east-1.rds.amazonaws.com"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_PASSWORD = "from-secrets-manager"
$env:DB_NAME = "stocks"
```

### For Persistent Configuration

Add to PowerShell profile (`$PROFILE`):
```powershell
# Dashboard AWS configuration
$env:DASHBOARD_API_URL = "https://your-api-endpoint.lambda-url.us-east-1.on.aws"
# or
$env:DB_PASSWORD = "your-password"
```

## Testing

```powershell
# Verify AWS setup
./scripts/verify-dashboard-aws.ps1

# Set up API endpoint
./scripts/setup-dashboard-aws.ps1

# Run dashboard
python tools/dashboard/dashboard.py

# Or with specific refresh interval
python tools/dashboard/dashboard.py -w 30  # refresh every 30 seconds
```

## Support

For detailed access methods and troubleshooting, see:
- `docs/dashboard-aws-access.md` - Detailed AWS access guide
- `docs/algo.md` → LOCAL AWS CREDENTIALS - Credential setup details

For issues:
1. Run `./scripts/verify-dashboard-aws.ps1` to diagnose
2. Check `dashboard.log` for detailed error messages
3. Review error messages - they now include AWS-specific guidance
