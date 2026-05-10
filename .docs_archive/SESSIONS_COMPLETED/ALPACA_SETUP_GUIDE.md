# Alpaca Historical Data Loader Setup

## Overview

Your data loading pipeline **already has Alpaca as the primary source** for historical OHLCV data. This guide walks through activating it, which eliminates dependency on unreliable yfinance and provides a fallback chain: **Alpaca → yfinance**.

**Why Alpaca?**
- Reliable API (no weekly breaks like yfinance)
- Paper trading credentials already available
- Free for paper trading accounts
- Direct market data (not scraped)

## Step 1: Get Alpaca API Credentials

### Option A: Paper Trading Account (Recommended for testing)
1. Go to https://app.alpaca.markets/signup
2. Create a paper trading account (free, no money required)
3. Navigate to "Account Settings" → "API Keys"
4. Click "Generate" under "Paper Trading" section
5. Copy **API Key ID** and **API Secret Key**
6. Keep these safe (like a password)

### Option B: Use Existing Account
If you already have an Alpaca account:
1. Log in to https://app.alpaca.markets
2. Settings → API Keys → Paper Trading
3. Generate new key if needed

## Step 2: Populate Secrets Manager

### Method 1: Automatic Script (Easiest)
```bash
python3 setup-alpaca-credentials.py \
  --api-key pk_xxxxxxxxxxxxxxxx \
  --api-secret sk_xxxxxxxxxxxxxxxx
```

Or with environment variables:
```bash
export ALPACA_API_KEY_ID=pk_xxxxxxxxxxxxxxxx
export ALPACA_API_SECRET_KEY=sk_xxxxxxxxxxxxxxxx
python3 setup-alpaca-credentials.py
```

### Method 2: Manual AWS CLI
```bash
aws secretsmanager update-secret \
  --secret-id stocks-algo-secrets \
  --secret-string '{
    "APCA_API_KEY_ID": "pk_xxxxxxxxxxxxxxxx",
    "APCA_API_SECRET_KEY": "sk_xxxxxxxxxxxxxxxx",
    "APCA_API_BASE_URL": "https://paper-api.alpaca.markets",
    "ALPACA_PAPER_TRADING": "true"
  }'
```

### Method 3: AWS Console
1. Go to https://console.aws.amazon.com/secretsmanager
2. Search for "stocks-algo-secrets"
3. Click "Edit secret"
4. Update the JSON with your API credentials
5. Click "Save changes"

## Step 3: Verify Setup

### Test Locally
```bash
python3 -c "
from data_source_router import DataSourceRouter
from datetime import date
router = DataSourceRouter()
data = router.fetch_ohlcv('AAPL', date(2024, 1, 1), date(2024, 1, 31))
print(f'Fetched {len(data) if data else 0} rows from {router.last_source}')
"
```

Expected output: `Fetched 21 rows from alpaca` (or similar)

### Test on Production (via Lambda)
```bash
aws lambda invoke \
  --function-name algo-orchestrator \
  --payload '{}' \
  --region us-east-1 \
  /tmp/test.json
  
aws logs tail /aws/lambda/algo-orchestrator --follow --region us-east-1
```

Look for log lines like:
```
Source 'alpaca' served OHLCV[AAPL 2024-01-01..2024-01-31]
```

### Check Health Report
After a few loader runs:
```bash
python3 -c "
from data_source_router import DataSourceRouter
router = DataSourceRouter()
import json
print(json.dumps(router.health_report(), indent=2))
"
```

## Step 4: Monitor Data Source

### Watch which source is being used
The `data_source_router.py` automatically tracks source health and switches to fallback if Alpaca fails.

**Current behavior:**
- Primary: Alpaca (reliable, direct)
- Fallback: yfinance (slower, scraped)

**Automatic fallback triggers:**
- If Alpaca success rate drops below 50% over 20 requests
- Pauses Alpaca for 5 minutes, retries after
- Returns to Alpaca once health recovers

### Check source distribution in logs
```bash
grep "Source.*served OHLCV" logs.txt | cut -d' ' -f2 | sort | uniq -c
```

This shows how many times each source served data.

## Troubleshooting

### "No data returned from Alpaca"
- **Check credentials**: `aws secretsmanager get-secret-value --secret-id stocks-algo-secrets --region us-east-1`
- **Check network**: Alpaca API might be temporarily down
- **Fallback working?**: Should use yfinance automatically

### "Alpaca is paused"
- Source had >50% failure rate recently
- Automatically resumes after 5 minutes
- Check CloudWatch logs for specific errors

### "yfinance is being used instead of Alpaca"
- Either Alpaca failed, or credentials are empty
- Verify setup with test command above
- Check `data_source_router.health_report()`

## Next Steps

Once Alpaca is active:

1. **Monitor source reliability** — watch health_report() over a week
2. **Add Polygon ($30/mo)** — additional fallback for ultra-reliability
3. **Implement incremental loading** — only fetch what's new (5-day effort)
4. **Test data consistency** — compare Alpaca vs yfinance results

## References

- [Alpaca API Docs](https://alpaca.markets/docs/api-references/market-data-api/)
- [data_source_router.py](./data_source_router.py) — Implementation
- [loadpricedaily.py](./loadpricedaily.py) — Example loader using router
- [setup-alpaca-credentials.py](./setup-alpaca-credentials.py) — Credential setup

## Cost

- Alpaca paper trading: **FREE**
- Data API: FREE (included)
- No additional costs

Total additional cost: **$0**
