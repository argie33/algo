# Getting AWS Data on the Algo Dashboard

## Current Status

The API server has been fixed to properly load utilities. The following dashboard options are available:

### Option 1: Local Development with API Server (Recommended for Development)
**Command:** `python tools/dashboard/dashboard-dev.py` (with `python lambda/api/dev_server.py` running)

**How it works:**
- `dev_server.py` runs the Lambda API locally on http://localhost:3001
- `dashboard-dev.py` connects to localhost:3001 and fetches AWS RDS data through the API
- Works from your local machine without AWS VPC access

**Working endpoints (tested):**
- ✓ `/api/algo/status` — operational status, portfolio summary
- ✓ `/api/algo/markets` — market data, exposure, tier information
- ✓ `/api/algo/config` — algorithm configuration
- ✓ `/api/algo/trades` — recent trade history
- ✓ `/api/algo/sector-rotation` — sector rotation analysis
- ✓ `/api/algo/swing-scores` — swing trading scores

**Failing endpoints (need database schema/data):**
- ✗ `/api/algo/positions` — needs algo_positions_with_risk view
- ✗ `/api/algo/performance` — needs performance metrics precomputed
- ✗ `/api/algo/dashboard-signals` — needs signal data

### Option 2: Direct AWS RDS Connection (Production)
**Command:** `python tools/dashboard/dashboard.py` (from EC2 or within AWS VPC)

**How it works:**
- Loads DB credentials from AWS Secrets Manager (algo/database)
- Connects directly to RDS Proxy (VPC-internal only)
- Lowest latency, but only accessible from within VPC

**Requirements:**
- Must run from EC2 instance or environment with VPC access
- AWS credentials with Secrets Manager access
- RDS must be running and accessible

### Option 3: Web Frontend (Full-Featured, Production)
**Access:** https://<cloudfront-domain> (from `terraform output`)

**How it works:**
- React frontend served by CloudFront
- Connects to API Lambda through API Gateway
- Real-time data via `/api/algo/*` endpoints
- Full authentication via Cognito

**Advantages:**
- ✓ Multi-user support with authentication
- ✓ Real-time updates
- ✓ Works from anywhere (no VPC required)
- ✓ Scales automatically

## How to Use Each Option

### Using dashboard-dev.py (Local)

```bash
# Terminal 1: Start the API server
python lambda/api/dev_server.py
# Output: Starting API dev server on http://localhost:3001

# Terminal 2: Run the dashboard
python tools/dashboard/dashboard-dev.py
# Or with watch mode:
python tools/dashboard/dashboard-dev.py -w 30  # auto-refresh every 30s
```

### Using dashboard.py (AWS RDS)

```bash
# Requires AWS credentials and VPC access
# From EC2 or bastion host:
python tools/dashboard/dashboard.py
# Or with watch mode:
python tools/dashboard/dashboard.py -w 30
```

### Using Web Frontend

```bash
# Get the frontend URL:
terraform output website_url

# Open in browser:
# https://<cloudfront-domain>
```

## Troubleshooting

### "API 404: Connection Error"
- Check `dev_server.py` is running on port 3001
- Verify no firewall is blocking localhost:3001
- Check `DASHBOARD_API_URL` environment variable

### "Database connection failed" or "Data unavailable"
- Check AWS credentials: `aws sts get-caller-identity`
- Verify RDS is running in AWS console
- For dev: ensure local database (stocks/stocks) has schema
- Check `lambda/db-init/schema.sql` for required tables/views

### Dashboard freezes or hangs
- Some queries may timeout if database schema is incomplete
- Check server logs for database errors: `tail -f /tmp/dev_server.log`
- Simplest fix: use web frontend (always works with AWS RDS)

## Next Steps

1. **For local development:** Use `dashboard-dev.py` with `dev_server.py`
   - Fastest iteration cycle
   - Immediate feedback on changes

2. **For AWS testing:** Deploy and test the web frontend
   - `git push main` triggers deployment
   - Access via CloudFront URL
   - No local setup required

3. **To fix missing endpoints:**
   - Positions endpoint needs `algo_positions_with_risk` view
   - Performance endpoint needs precomputed metrics in database
   - Signal endpoint needs signal data from loaders
   - All should auto-populate if loaders are running

## Key Files

- **API:** `lambda/api/lambda_function.py`, `lambda/api/routes/algo.py`
- **Dev Server:** `lambda/api/dev_server.py` (for local testing)
- **Dashboard (Dev):** `tools/dashboard/dashboard-dev.py` (localhost API)
- **Dashboard (Prod):** `tools/dashboard/dashboard.py` (AWS RDS)
- **Web Frontend:** `webapp/frontend/src/` (React app)
- **API Routes:** `lambda/api/routes/*.py` (endpoint handlers)

## Architecture Summary

```
┌─────────────────────────────────────────────────────┐
│ AWS Environment (RDS, Secrets Manager)              │
└────────────────┬──────────────────────────────────────┘
                 │
     ┌───────────┴──────────────┬─────────────────┐
     │                          │                 │
┌────▼──────┐          ┌────────▼────┐   ┌───────▼────┐
│   API      │          │ Dashboard   │   │ Web        │
│  Lambda    │          │ (dashboard  │   │ Frontend   │
│            │          │  -prod.py)  │   │            │
└────▲──────┘          └─────────────┘   └──────▲─────┘
     │                                           │
     │                     API Gateway           │
     │                    (Production)            │
     └───────────────────────────┬───────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
              ┌─────▼────┐          ┌────────▼──────┐
              │ Dev Server│          │  CloudFront   │
              │           │          │  (Frontend)   │
              └───────────┘          └───────────────┘
                    │
              ┌─────▼─────┐
              │ Dashboard │
              │ (dev.py)  │
              └───────────┘
```

