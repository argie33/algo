# Local Development Setup - Dashboard + AWS API

## Quick Start (5 minutes)

### 1. Set PowerShell Environment Variables

Add these to your PowerShell profile (`$PROFILE`):

```powershell
# AWS API Gateway
$env:VITE_PROXY_TARGET = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"

# Cognito Configuration
$env:VITE_COGNITO_USER_POOL_ID = "us-east-1_XJpLb9SKX"
$env:VITE_COGNITO_CLIENT_ID = "6smb0vrcidd9kvhju2kn2a3qrl"
$env:VITE_COGNITO_DOMAIN = "https://algo-dev.auth.us-east-1.amazoncognito.com"

# AWS Profile (for terminal dashboard)
$env:AWS_PROFILE = "algo-developer"
```

Then reload your profile:
```powershell
& $PROFILE
```

### 2. Browser Dashboard

```powershell
cd webapp/frontend
npm run dev
```

Then open: `http://localhost:5173`

**Expected behavior:**
- Public pages (markets, sectors, economic, sentiment, scores) → Load AWS data immediately
- Protected pages (algo-dashboard, portfolio, trades) → Redirect to login
- Click "Sign In" → Login with `argeropolos@gmail.com` + Cognito password
- After login → Protected pages load with real AWS data

**How it works:**
- Vite dev server listens on `localhost:5173`
- Browser requests to `/api/*` are proxied to `$VITE_PROXY_TARGET` (AWS API Gateway)
- Cognito JWT tokens passed through transparently (no CORS issues)

### 3. Terminal Dashboard

```powershell
.\run-dashboard.ps1
```

**Expected behavior:**
- Fetches API URL and Cognito credentials (from Terraform state or hardcoded fallback)
- Prompts for Cognito login
- Displays live metrics from AWS

## Troubleshooting

### "401 Unauthorized" on protected pages
- Did you add the env vars to your PowerShell profile and reload?
- Is `$VITE_PROXY_TARGET` set to the correct API Gateway URL?

### "Login redirect loop"
- Clear browser localStorage: DevTools → Application → Storage → Clear All
- Verify Cognito credentials in `config.js` match your AWS Cognito user pool

### Terminal dashboard fails with "Could not fetch AWS credentials"
- Check: `aws sts get-caller-identity --profile algo-developer`
- If failed, run: `scripts/refresh-aws-credentials.ps1`

### Public pages show "No data"
- Check browser DevTools → Network tab → `/api/*` requests
- Should see 200 responses from AWS API Gateway (proxied through localhost:5173)
- If 404 or CORS errors, verify `VITE_PROXY_TARGET` is set correctly

## Architecture

```
Browser (localhost:5173)
  ↓ (requests to /api/*)
Vite Dev Server Proxy
  ↓ (rewrites to full URL)
AWS API Gateway (https://2iqq1qhltj...)
  ↓
Lambda Functions + RDS
```

**Why proxy?** Eliminates CORS issues. AWS API Gateway has strict CORS rules, but server-to-server requests (Vite proxy) bypass them entirely. Tokens still pass through transparently.
