# Alpaca Credentials Setup - CRITICAL FOR LIVE TRADING

**Status:** BLOCKING Phase 8 trade execution

## Current State

```
algo_config values:
  alpaca_api_key:     'PK0123456789ABCDEF' (DUMMY/TEST)
  alpaca_api_secret:  'test_secret_key_for_development' (DUMMY/TEST)
  alpaca_base_url:    'https://paper-api.alpaca.markets' (OK)
  alpaca_paper_trading: 'true' (OK)
```

**Problem:** Dummy credentials cause Phase 8 to reject trades:
- Market circuit breaker can't verify safety gates
- Trade execution fails with "credentials not found"
- No Alpaca connection possible

## How to Fix

### Option 1: Local Development (For Testing)

Get your real Alpaca API credentials from https://app.alpaca.markets

```sql
UPDATE algo_config SET value = 'YOUR_REAL_API_KEY' 
WHERE key = 'alpaca_api_key';

UPDATE algo_config SET value = 'YOUR_REAL_API_SECRET' 
WHERE key = 'alpaca_api_secret';
```

### Option 2: Production (GitHub Actions Deployment)

Credentials should be injected from AWS Secrets Manager:

```bash
# In your GitHub Actions deployment:
export ALPACA_API_KEY=$(aws secretsmanager get-secret-value --secret-id algo/alpaca/api-key --query SecretString --output text)
export ALPACA_API_SECRET=$(aws secretsmanager get-secret-value --secret-id algo/alpaca/api-secret --query SecretString --output text)

# Then lambda_function.py or local_orchestrator.py loads from env vars
```

## What Gets Unlocked After Fix

1. ✓ Phase 8: Trade execution (currently fails)
2. ✓ Market safety verification (currently skipped)
3. ✓ Circuit breaker market checks
4. ✓ Live paper trading execution

## Verification After Fix

```bash
# Run orchestrator
python3 scripts/run_local_orchestrator.py --morning

# Check Phase 8 output for:
# - "CSWC: Executed trade" (instead of FK violation)
# - Trades inserted into algo_trades table
# - No "credentials NOT FOUND" errors
```

## Security Notes

- Never commit real credentials to git
- Always use AWS Secrets Manager or env vars
- Test credentials are acceptable ONLY for local dev
- Production deployment must use real Alpaca paper account
