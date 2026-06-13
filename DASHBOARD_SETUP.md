# Algo Dashboard - Setup & Usage Guide

## Quick Start

### LOCAL MODE (Development)
```powershell
# Terminal 1: Start dev server
python lambda/api/dev_server.py

# Terminal 2: Start dashboard (in another terminal)
python tools/dashboard/main.py --local
```

### AWS MODE (Production)
```powershell
# Set environment variables
$env:DASHBOARD_API_URL = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"
$env:COGNITO_USER_POOL_ID = "us-east-1_XJpLb9SKX"
$env:COGNITO_CLIENT_ID = "6smb0vrcidd9kvhju2kn2a3qrl"
$env:AWS_PROFILE = "algo-developer"

# Run dashboard
python tools/dashboard/main.py
```

## Dashboard Options

```
python tools/dashboard/main.py [OPTIONS]

Options:
  --local              Use local API (localhost:3001) instead of AWS
  -w, --watch [SECS]   Watch mode, auto-refresh every N seconds (default: 30s)
  -c, --compact        Narrow positions table (omit T1 and Sector columns)
  -l, --legend         Print dashboard legend and exit
```

## Examples

```powershell
# LOCAL: Live view
python tools/dashboard/main.py --local

# LOCAL: Auto-refresh every 60 seconds
python tools/dashboard/main.py --local -w 60

# AWS: Live view (with proper auth)
python tools/dashboard/main.py

# AWS: Compact view with auto-refresh
python tools/dashboard/main.py -c -w 45
```

## Architecture

### LOCAL Mode
- **Dev Server**: `lambda/api/dev_server.py` runs on `localhost:3001`
- **Data**: Returns stub/test data
- **Auth**: Dev bypass enabled (no Cognito required)
- **Use**: Development, testing, no AWS access needed

### AWS Mode
- **API Gateway**: Production endpoint at `https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com`
- **Auth**: Cognito authentication required
- **Data**: Live trading data from RDS
- **Use**: Production monitoring, real algorithm data

## Credentials Setup

### AWS Credentials
```powershell
# Get fresh credentials from Secrets Manager
scripts/refresh-aws-credentials.ps1

# Verify credentials are set
aws sts get-caller-identity --profile algo-developer
```

### Cognito Credentials
For AWS mode, you need:
1. **COGNITO_USERNAME** - Your Cognito user email
2. **COGNITO_PASSWORD** - Your Cognito user password

Set as environment variables before running AWS mode:
```powershell
$env:COGNITO_USERNAME = "your-email@example.com"
$env:COGNITO_PASSWORD = "YourPassword123!"
python tools/dashboard/main.py
```

Or use cached tokens (created after first successful login):
```powershell
# First run: prompts for credentials, saves token
python tools/dashboard/main.py

# Subsequent runs: uses cached token from ~/.algo/cognito_token.json
python tools/dashboard/main.py
```

## Dashboard Panels

**Top Row:**
- MARKET: Market status, hours, VIX, market stage
- EXPOSURE FACTORS: 12-factor breakdown of allocation % 
- MASCOT: Animated indicator of data loading state

**Row 2:**
- CIRCUIT BREAKERS: Drawdown, daily/weekly loss, halts
- ALGO HEALTH: Run status, phases completed, notifications

**Row 3:**
- PORTFOLIO: Total value, cash, positions, P&L
- PERFORMANCE: Trade stats, equity curve, returns
- ECONOMIC INPUTS: Treasury yields, Fed rate, credit spreads

**Row 4:**
- BUY SIGNALS: Screened candidates, signal grades (A/B/C/D)
- SECTORS: Sector rotation, industry rankings

**Row 5:**
- POSITIONS: Open trades with entry, price, P&L, stops
- RECENT TRADES: Latest closed trades

## Keyboard Commands

| Key | Action |
|-----|--------|
| `p` | Toggle positions view (expanded/compact) |
| `s` | Toggle signals view |
| `h` | Toggle algo health view |
| `r` | Toggle sectors view |
| `q` | Quit dashboard |

## Troubleshooting

### LOCAL Mode Issues

**"Connection refused on localhost:3001"**
- Dev server not running. Start it first: `python lambda/api/dev_server.py`
- Check port 3001 is open: `netstat -ano | findstr :3001`

**"API error 503"**
- Dev server crashed. Restart it and the dashboard.

### AWS Mode Issues

**"API unavailable - circuit breaker open"**
- AWS API not responding. Check API Gateway is deployed.
- Verify DASHBOARD_API_URL is correct.

**"Invalid username or password"**
- Cognito credentials are wrong.
- Check user exists in the Cognito pool.
- Password requirements: 12+ chars, uppercase, lowercase, numbers, symbols

**"User not found"**
- Username (email) doesn't exist in Cognito pool.

**"Token expired"**
- Delete cached token: `rm ~/.algo/cognito_token.json`
- Login again to refresh: `python tools/dashboard/main.py`

## File Structure

```
tools/dashboard/
├── main.py              # Entry point & main loop
├── utilities.py         # API calls, logging, helpers
├── fetchers.py          # Data fetching from endpoints
├── panels.py            # UI panel rendering (Rich)
├── formatters.py        # Formatting helpers
├── cognito_auth.py      # Cognito authentication
├── data_validation.py   # Data validation utilities
├── api_data_layer.py    # API response handling
└── COGNITO_SETUP.md     # Detailed auth setup

lambda/api/
└── dev_server.py        # Local dev server (localhost:3001)
```

## Performance Notes

- **Refresh Rate**: Default 30s (watch mode)
- **API Timeout**: 20 seconds per endpoint
- **Max Retries**: 3 attempts with exponential backoff
- **Parallel Fetchers**: ~25 concurrent API calls
- **Circuit Breaker**: Prevents hammering failed APIs

## Development

### Adding New Data Panels

1. Create fetcher in `fetchers.py`: `def fetch_new_data()`
2. Add panel renderer in `panels.py`: `def panel_new_data()`
3. Add to `load_all()` in `fetchers.py`
4. Add to layout in `main.py: `render_dashboard()`

### Testing

```powershell
# Test LOCAL mode data fetching
python -c "
import os
os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
from tools.dashboard.utilities import api_call
data = api_call('/api/algo/config')
print(data)
"
```

## References

- Cognito Setup: `tools/dashboard/COGNITO_SETUP.md`
- API Endpoints: `config/api_endpoints.py`
- Dev Server: `lambda/api/dev_server.py`
