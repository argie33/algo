# Dual Environment Setup: Local Development + AWS Production

This document explains how the frontend now automatically adapts to work in both local development and AWS production without manual configuration steps.

## How It Works

### Configuration Resolution Priority

The frontend uses a 3-level automatic URL resolution system:

1. **Runtime Config** (`window.__CONFIG__.API_URL` from public/config.js)
   - **Production (AWS):** GitHub Actions sets this to CloudFront domain (e.g., `https://d2u93283nn45h2.cloudfront.net`)
   - **Local Development:** Empty string (triggers Vite proxy)

2. **Build-Time Environment** (`VITE_API_URL`)
   - **Production (AWS):** Set by GitHub Actions to CloudFront domain
   - **Local Development:** Not set (falls back to #3)

3. **Development Default** (Vite proxy)
   - **Local Development:** Empty baseURL triggers Vite proxy
   - **Production:** N/A (always has explicit URL from #1 or #2)

### Local Development Workflow

```bash
# Terminal 1: Start the backend API (required)
# API server must be running on http://localhost:3001
# This could be: npm run dev, python app.py, or any local server

# Terminal 2: Start the frontend dev server
cd webapp/frontend
npm run dev

# Frontend automatically available at: http://localhost:5173
# All /api/* requests proxied to http://localhost:3001 via Vite
```

**No configuration needed.** The frontend detects development mode and uses the proxy.

### Production Workflow (AWS)

```bash
# Push code to main branch
git push origin main

# GitHub Actions automatically:
# 1. Builds frontend with VITE_API_URL=<CloudFront domain>
# 2. Generates config.js in dist/ with API_URL=<CloudFront domain>
# 3. Deploys to S3 and invalidates CloudFront
# 4. All API requests route through CloudFront proxy
```

**Zero manual configuration.** Terraform + GitHub Actions handle everything.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  LOCAL DEVELOPMENT                                          │
├─────────────────────────────────────────────────────────────┤
│  Browser                                                     │
│  http://localhost:5173 (React app)                          │
│           │                                                  │
│           ├──> /api/stocks               → Vite proxy →    │
│           ├──> /api/signals              → localhost:3001  │
│           └──> /api/health               →                  │
│                                                              │
│  Backend: http://localhost:3001 (your local API server)    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  PRODUCTION (AWS)                                           │
├─────────────────────────────────────────────────────────────┤
│  Browser                                                     │
│  https://d2u93283nn45h2.cloudfront.net (React app)         │
│           │                                                  │
│           ├──> /api/stocks               → CloudFront →   │
│           ├──> /api/signals              → API Gateway     │
│           └──> /api/health               → Lambda          │
│                                                              │
│  Backend: Lambda (algo-api-dev)                            │
│  Auth: Cognito (us-east-1_XJpLb9SKX)                       │
└─────────────────────────────────────────────────────────────┘
```

## Key Configuration Files

| File | Purpose | Managed By |
|------|---------|-----------|
| `webapp/frontend/public/config.js` | Runtime config template | Developer (commit to repo) |
| `webapp/frontend/dist/config.js` | Generated config (production) | GitHub Actions (auto-generated) |
| `vite.config.js` | Dev server + proxy settings | Developer (commit to repo) |
| `webapp/frontend/src/services/api.js` | URL resolution logic | Developer (commit to repo) |

## Making Changes

### Update Frontend Code
```bash
git push origin main
# GitHub Actions automatically rebuilds and deploys to AWS
```

### Update API Locally
```bash
# Start your local backend on http://localhost:3001
npm run dev  # or equivalent for your API

# Frontend dev server detects and uses it
cd webapp/frontend && npm run dev
```

### Update Authentication Config
- **Local Dev:** Edit `webapp/frontend/public/config.js` (USER_POOL_ID, etc.)
- **Production:** Terraform manages Cognito, workflow generates config automatically

## Troubleshooting

### Frontend shows "API request failed" locally
- ✓ Is your backend running on http://localhost:3001?
- ✓ Does your backend have CORS headers configured?
- Check vite.config.js proxy settings (line 55-62)

### Frontend shows authentication errors
- **Local:** Check USER_POOL_ID in public/config.js
- **Production:** Check Cognito pool created by Terraform (steering/algo.md)

### Changes not reflecting in production
- Push to main (GitHub Actions auto-deploys)
- Check workflow status: `gh run list --workflow deploy-code.yml`
- Verify CloudFront cache invalidation completed

## Environment Variables

**Local Development:** Not needed (all automatic)

**Production Build:** Managed by GitHub Actions
- `VITE_API_URL` - Set to CloudFront domain
- Cognito settings - Pulled from Terraform outputs

## Related Documentation

- **Infrastructure:** See `steering/algo.md` for AWS setup
- **Frontend Config:** Check `webapp/frontend/src/services/api.js` for URL resolution logic
- **Deployment:** GitHub Actions: `.github/workflows/deploy-code.yml`
- **Build System:** Vite config: `webapp/frontend/vite.config.js`
