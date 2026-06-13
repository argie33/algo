# Dashboard AWS Authentication Setup

The dashboard requires three values to authenticate with AWS:
1. **DASHBOARD_API_URL** - API Gateway endpoint
2. **COGNITO_USER_POOL_ID** - Cognito User Pool ID
3. **COGNITO_CLIENT_ID** - Cognito App Client ID

## Quick Setup (Choose One Method)

### Method 1: Get Credentials from Terraform (Recommended)

**Step 1:** Initialize Terraform with S3 backend config
```powershell
cd terraform
terraform init -backend-config="bucket=stocks-terraform-state" -backend-config="key=stocks/terraform.tfstate" -backend-config="region=us-east-1" -backend-config="encrypt=true"
```

**Step 2:** Retrieve outputs
```powershell
$apiUrl = terraform output -raw api_url
$poolId = terraform output -raw cognito_user_pool_id
$clientId = terraform output -raw cognito_user_pool_client_id

Write-Host "API URL: $apiUrl"
Write-Host "User Pool ID: $poolId"
Write-Host "Client ID: $clientId"
```

### Method 2: Get Credentials from AWS Console

**API URL (API Gateway):**
- AWS Console → API Gateway → Your API → Stages → `$default` → Copy Invoke URL
- Should look like: `https://xxxxx.execute-api.us-east-1.amazonaws.com`

**User Pool ID:**
- AWS Console → Cognito → User pools → Select your pool → Click the pool name
- Under "General settings" → User Pool ID (e.g., `us-east-1_xxxxxxxxx`)

**Client ID:**
- AWS Console → Cognito → User pools → Your pool → "App integration" → "App clients and analytics"
- Copy the Client ID from the table

### Step 3: Configure Environment Variables

### Option A: Temporary (Current PowerShell Session Only)
```powershell
$env:DASHBOARD_API_URL = "https://xxxxx.execute-api.us-east-1.amazonaws.com"
$env:COGNITO_USER_POOL_ID = "us-east-1_xxxxxxxxx"
$env:COGNITO_CLIENT_ID = "xxxxxxxxxxxxxxxxxx"

# Then run the dashboard
python tools/dashboard/main.py
```

### Option B: Permanent (PowerShell Profile - Recommended)
```powershell
# Add to PowerShell profile (runs every time you open PowerShell)
Add-Content $PROFILE @"

# Algo Dashboard AWS Configuration
`$env:DASHBOARD_API_URL = "https://xxxxx.execute-api.us-east-1.amazonaws.com"
`$env:COGNITO_USER_POOL_ID = "us-east-1_xxxxxxxxx"
`$env:COGNITO_CLIENT_ID = "xxxxxxxxxxxxxxxxxx"
"@

# Reload profile
. $PROFILE
```

### Option C: Permanent (System Environment Variables)
```powershell
# Sets variables at Windows system level (persists across sessions and restarts)
setx DASHBOARD_API_URL "https://xxxxx.execute-api.us-east-1.amazonaws.com"
setx COGNITO_USER_POOL_ID "us-east-1_xxxxxxxxx"
setx COGNITO_CLIENT_ID "xxxxxxxxxxxxxxxxxx"

# Restart PowerShell to apply
```

### Option D: Use Local API (No AWS Credentials Needed)
For development without AWS:
```powershell
python tools/dashboard/main.py --local
```
Requires local API running on `http://localhost:3001`

## Authentication Modes

### AWS Mode (Default)
```bash
python tools/dashboard/main.py
```

**Requires:**
- `DASHBOARD_API_URL` - AWS API endpoint
- `COGNITO_USER_POOL_ID` - Cognito pool ID
- `COGNITO_CLIENT_ID` - Cognito client ID

**Authentication methods (in order):**
1. Cached tokens from `~/.algo/cognito_token.json`
2. Environment variables: `COGNITO_USERNAME` and `COGNITO_PASSWORD`
3. Interactive prompt (if neither cached nor env vars available)

### Local Mode
```bash
python tools/dashboard/main.py --local
```

**Requires:**
- Local API running on `http://localhost:3001`
- No authentication needed

## Usage Examples

### First Run: Authenticate with Username/Password
```powershell
# Set Cognito credentials (one-time for first auth)
$env:COGNITO_USERNAME = "your-email@example.com"
$env:COGNITO_PASSWORD = "YourPassword123!"

# Run dashboard - will cache token for future runs
python tools/dashboard/main.py
```

### Subsequent Runs: Use Cached Token
```powershell
# No credentials needed - uses cached token from ~/.algo/cognito_token.json
python tools/dashboard/main.py
```

### Interactive Prompt (No Environment Variables)
```powershell
# If COGNITO_USERNAME/COGNITO_PASSWORD not set, prompts for credentials
python tools/dashboard/main.py
```

### Local Development (No Authentication)
```powershell
python tools/dashboard/main.py --local
```

### Dashboard Options
```powershell
# Watch mode - auto-refresh every 30 seconds
python tools/dashboard/main.py -w

# Watch mode - auto-refresh every 60 seconds
python tools/dashboard/main.py -w 60

# Compact view - narrower positions table
python tools/dashboard/main.py --compact

# Legend - print guide to all dashboard panels
python tools/dashboard/main.py --legend
```

## Troubleshooting

### "Invalid username or password"
- Check credentials are correct
- Ensure user exists in Cognito User Pool
- Check password meets requirements (12+ chars, uppercase, lowercase, numbers, symbols)

### "User not found"
- Verify username is correct (usually email)
- Check user exists in Cognito User Pool

### "API unavailable"
- Verify DASHBOARD_API_URL is correct
- Check API Gateway is deployed
- Verify internet connection

### Token Expired
- Delete cached token: `rm ~/.algo/cognito_token.json`
- Re-run dashboard with credentials to get new token

## Token Management

Tokens are cached in: `~/.algo/cognito_token.json`

- **Access Token**: 24 hours validity
- **Refresh Token**: 30 days validity  
- **ID Token**: 24 hours validity

To clear cached tokens:
```bash
rm ~/.algo/cognito_token.json
```

## Security Notes

⚠️ **Never commit credentials to git!**
- Use environment variables
- Use `.env` file (add to `.gitignore`)
- Use AWS profiles or temporary credentials

Do NOT store passwords in scripts or environment unless testing locally.
