# Dashboard Cognito Authentication

Complete guide to running the Algo dashboard with AWS Cognito authentication.

## Quick Start (30 seconds)

```powershell
# 1. Refresh AWS credentials
scripts/refresh-aws-credentials.ps1

# 2. Create test user (one-time)
$env:AWS_PROFILE = 'algo-developer'
python scripts/setup-cognito-test-user.py

# 3. Run dashboard (will prompt for Cognito credentials)
python -m tools.dashboard.dashboard
```

## How It Works

The dashboard uses **dynamic authentication** — it handles Cognito auth automatically:

```
Dashboard Startup
    ↓
Check for Cognito config (env vars or Terraform)
    ↓
Try authentication (in order):
  1. COGNITO_USERNAME + COGNITO_PASSWORD env vars
  2. Cached token from ~/.algo/cognito_token.json
  3. Interactive prompt if running in terminal
    ↓
API requests include Bearer token automatically
    ↓
Tokens refresh in background as needed
```

## Setup Options

### Option 1: Environment Variables (Recommended for CI/CD)

```powershell
# Set credentials
$env:COGNITO_USERNAME = "edgebrookecapital@gmail.com"
$env:COGNITO_PASSWORD = "TestPassword123!"

# Run dashboard
python -m tools.dashboard.dashboard
```

### Option 2: Interactive Prompt (Recommended for Local Dev)

```powershell
python -m tools.dashboard.dashboard
# Dashboard will prompt:
# Email: edgebrookecapital@gmail.com
# Password: ***hidden***
```

The credentials are cached to `~/.algo/cognito_token.json` for future runs.

### Option 3: Manual Credential Setup

```powershell
# Get Terraform outputs
$env:AWS_PROFILE = 'algo-developer'
cd terraform
$apiUrl = terraform output -raw api_url
$poolId = terraform output -raw cognito_user_pool_id
$clientId = terraform output -raw cognito_user_pool_client_id

# Set environment
$env:DASHBOARD_API_URL = $apiUrl
$env:COGNITO_USER_POOL_ID = $poolId
$env:COGNITO_CLIENT_ID = $clientId
$env:COGNITO_USERNAME = "your.email@example.com"
$env:COGNITO_PASSWORD = "your.password"

# Run dashboard
cd ..
python -m tools.dashboard.dashboard
```

## Test User Management

### Create/Reset Test User

```powershell
$env:AWS_PROFILE = 'algo-developer'
python scripts/setup-cognito-test-user.py
```

Output:
```
[OK] User created
[OK] Password set
[OK] Authentication successful

Test user ready:
  Email: edgebrookecapital@gmail.com
  Password: TestPassword123!
```

### Set Custom Test User Password

```powershell
$env:AWS_PROFILE = 'algo-developer'
$env:COGNITO_TEST_USER_EMAIL = "your.email@example.com"
$env:COGNITO_TEST_USER_PASSWORD = "YourPassword123!"
python scripts/setup-cognito-test-user.py
```

## Dashboard Modes

### AWS Mode (Default)

Requires Cognito authentication. Shows live data from Lambda API.

```powershell
python -m tools.dashboard.dashboard
```

**Endpoints available:** All protected endpoints require Bearer token

### Local Mode

No authentication needed. Connect to local dev server on localhost:3001.

```powershell
# In terminal 1: Start local dev server
npm run dev --prefix webapp/frontend

# In terminal 2: Run dashboard in local mode
python -m tools.dashboard.dashboard --local
```

## Troubleshooting

### "No cached credentials" + "Cannot authenticate interactively"

**Problem:** Running in non-interactive environment (CI/CD, background process)

**Solution:** Set environment variables explicitly:
```powershell
$env:COGNITO_USERNAME = "email@example.com"
$env:COGNITO_PASSWORD = "password"
```

### "Token expired" error

**Problem:** Cached token is expired

**Solution:** Delete cache, dashboard will re-authenticate:
```powershell
rm ~/.algo/cognito_token.json
python -m tools.dashboard.dashboard
```

### "Authentication failed - invalid credentials"

**Problem:** Wrong email or password

**Solution:** Reset test user and try again:
```powershell
python scripts/setup-cognito-test-user.py
```

### "Protected endpoint requires authentication"

**Problem:** Dashboard running without Cognito token (local mode only)

**Solution:** Use AWS mode with credentials:
```powershell
$env:COGNITO_USERNAME = "email@example.com"
$env:COGNITO_PASSWORD = "password"
python -m tools.dashboard.dashboard
```

## API Endpoint Authentication

Protected endpoints require `Authorization: Bearer <token>` header.

**Protected endpoints (require auth):**
- `/api/algo/*` — algo performance, signals, positions, trades
- `/api/trades/*` — trade history
- `/api/audit/*` — audit logs
- `/api/settings/*` — user settings

**Public endpoints (no auth):**
- `/api/health` — health check
- `/api/market*` — market data
- `/api/prices` — historical prices
- `/api/sectors` — sector analysis
- `/api/sentiment` — market sentiment

## Token Lifecycle

### Token Storage

```
~/.algo/cognito_token.json
{
  "access_token": "...",
  "refresh_token": "...",
  "id_token": "...",
  "username": "...",
  "expires_at": 1234567890,
  "saved_at": "2026-06-13T..."
}
```

### Automatic Refresh

Dashboard automatically refreshes tokens when:
- Access token expires (checked before each API call)
- 5-minute buffer: refreshes if <5 min remaining

### Manual Refresh

Delete the token file, dashboard will re-authenticate on next run:
```powershell
rm ~/.algo/cognito_token.json
```

## CI/CD Integration

For GitHub Actions or other CI/CD:

```yaml
env:
  AWS_PROFILE: algo-developer
  COGNITO_USERNAME: ${{ secrets.COGNITO_TEST_USER_EMAIL }}
  COGNITO_PASSWORD: ${{ secrets.COGNITO_TEST_USER_PASSWORD }}

script:
  - python -m tools.dashboard.dashboard --watch 30
```

Store credentials in GitHub Secrets, never in code.

## Security Notes

- **Never commit credentials** to git (pre-commit hook prevents this)
- **Use Secrets Manager** for production credentials
- **Rotate credentials quarterly** (see CLAUDE.md)
- **Use environment variables** for CI/CD, not hardcoded passwords
- **Delete cache if machine compromised:** `rm ~/.algo/cognito_token.json`

## Architecture

Dashboard authentication is **stateless and resilient**:

1. **No persistent auth state** — Each run authenticates independently
2. **Multiple fallbacks** — Env vars → cache → interactive prompt
3. **Automatic refresh** — Tokens refresh without user intervention
4. **Graceful degradation** — Public endpoints work without auth

This allows dashboard to work seamlessly across:
- Local development (interactive prompt)
- CI/CD pipelines (environment variables)
- Scheduled tasks (cached tokens)
