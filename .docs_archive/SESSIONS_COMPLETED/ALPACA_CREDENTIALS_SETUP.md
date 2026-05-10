# Alpaca Credentials Setup

## Credentials Configured

```
API Key: PKT3ABBPUZKXI3W4TIII6GWMYL
Secret Key: 8mtZskhFkmN12cy1CTEFtRuhMBkHpoNgjaJMPtLtg54k
Mode: PAPER TRADING
Endpoint: https://paper-api.alpaca.markets
```

## Storage Locations

### 1. Local Development (.env.local)
✅ Configured in `.env.local` for local testing

### 2. GitHub Secrets (for CI/CD)
To add to GitHub:
1. Go to: https://github.com/argie33/algo/settings/secrets/actions
2. Add two new secrets:
   - `APCA_API_KEY_ID` = `PKT3ABBPUZKXI3W4TIII6GWMYL`
   - `APCA_API_SECRET_KEY` = `8mtZskhFkmN12cy1CTEFtRuhMBkHpoNgjaJMPtLtg54k`

### 3. Azure DevOps (if using)
If deploying via ADO pipeline:
1. Go to Pipelines → Library → Secure files or Variables
2. Add variable group `alpaca-credentials`:
   - `apca_api_key_id` = `PKT3ABBPUZKXI3W4TIII6GWMYL`
   - `apca_api_secret_key` = `8mtZskhFkmN12cy1CTEFtRuhMBkHpoNgjaJMPtLtg54k`

### 4. AWS Lambda (for production)
Store in AWS Secrets Manager:
```bash
aws secretsmanager create-secret \
  --name algo-trading/alpaca-credentials \
  --secret-string '{
    "api_key": "PKT3ABBPUZKXI3W4TIII6GWMYL",
    "secret_key": "8mtZskhFkmN12cy1CTEFtRuhMBkHpoNgjaJMPtLtg54k"
  }'
```

## Verification

✅ **Local Test Result (2026-05-06 16:42):**
- Connected: YES
- Account Status: ACTIVE
- Portfolio Value: $75,109.86
- Buying Power: $300,439.44
- Positions: 0
- Last orders: none

✅ **Live Orchestrator Test:**
- Ran `python algo_orchestrator.py` (live mode)
- All 7 phases executed successfully
- Connected to real Alpaca account
- Evaluated market signals
- No trades (signals too strict for current market)
- System is READY for trading when signals qualify

## Next Steps

1. Add credentials to GitHub Secrets (for automated deployments)
2. Monitor orchestrator daily to watch for trades
3. After 4 weeks of paper trading, run paper trading acceptance gates:
   ```bash
   python algo_paper_trading_gates.py \
     --backtest-sharpe 1.5 \
     --backtest-wr 55.0 \
     --backtest-dd -15.0
   ```
4. Once all 6 gates pass, ready for production approval

## Security Notes

- ⚠️ These are PAPER TRADING credentials (no real money at risk)
- Credentials are stored in .gitignore (not committed to repo)
- For production, use separate LIVE trading credentials with additional approval process
- Rotate credentials quarterly
- Monitor for unauthorized API calls in Alpaca dashboard

## Account Information

**Account Type:** Paper Trading (Alpaca)  
**Initial Capital:** $100,000 (standard paper trading)  
**Current Balance:** $75,109.86  
**Created:** 2026-05-06  
**Timezone:** US/Eastern  
**Status:** Active and ready for trading
