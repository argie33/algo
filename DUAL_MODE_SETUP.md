# Dual-Mode Dashboard: Local + AWS

Quick setup for running the dashboard in both **local development** and **AWS production** modes.

## Quick Start

### Local Mode (Recommended)
```bash
# Automatic (Linux/macOS)
./start_system.sh local

# Manual
python api-pkg/dev_server.py           # Terminal 1
python -m dashboard --local            # Terminal 2
```

### AWS Mode
```bash
# Automatic (Linux/macOS)
./start_system.sh aws

# Direct
python -m dashboard
```

## Environment Setup

**Local:** Database on localhost (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)

**AWS:** Cognito credentials (DASHBOARD_API_URL, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID)

See `SESSION_45_DUAL_MODE_SETUP.md` for detailed setup and troubleshooting.
