# Alpaca Credentials Setup Guide

## Local Development (Quick Start)

Set environment variables in your terminal:

```bash
export APCA_API_KEY_ID="your_alpaca_paper_key_id"
export APCA_API_SECRET_KEY="your_alpaca_paper_secret_key"

# Then run orchestrator
python3 scripts/trigger_orchestrator.py --mode paper --run morning
```

**Get Your Credentials**:
1. Go to https://app.alpaca.markets
2. Log in or create account
3. Click Settings → API Keys
4. Copy API Key ID and Secret Key
5. Make sure you're using **Paper Trading** (not live)

## Production AWS Setup

Credentials must be in AWS Secrets Manager for cloud deployment.

### Option 1: Single Shared Credential (Recommended for Single-User)

```bash
# Store in AWS Secrets Manager
aws secretsmanager create-secret \
  --name algo/alpaca/shared \
  --secret-string '{
    "APCA_API_KEY_ID": "your_key_id",
    "APCA_API_SECRET_KEY": "your_secret_key"
  }' \
  --region us-east-1
```

### Option 2: User-Specific Credentials (Multi-User)

```bash
# Store per-user credentials
aws secretsmanager create-secret \
  --name algo/alpaca/user-12345 \
  --secret-string '{
    "APCA_API_KEY_ID": "user_key_id",
    "APCA_API_SECRET_KEY": "user_secret_key"
  }' \
  --region us-east-1
```

### Option 3: JSON Blob via Environment Variable

Store JSON directly in environment variable:

```bash
export ALGO_SECRETS_ARN='{"APCA_API_KEY_ID": "key_id", "APCA_API_SECRET_KEY": "secret"}'
```

## Verify Credentials Work

```bash
# Test credentials locally
python3 -c "
import os
os.environ['APCA_API_KEY_ID'] = 'YOUR_KEY_ID'
os.environ['APCA_API_SECRET_KEY'] = 'YOUR_SECRET_KEY'

from config.credential_manager import get_alpaca_credentials
creds = get_alpaca_credentials()
print('✓ Credentials loaded successfully')
print(f'  Key ID: {creds.get(\"APCA_API_KEY_ID\", \"?\")[:10]}...')
"
```

## Kubernetes/ECS Deployment

Add credentials to Dockerfile or ECS Task Definition:

**ECS Task Definition**:
```json
{
  "environment": [
    {
      "name": "APCA_API_KEY_ID",
      "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:algo/alpaca/shared:APCA_API_KEY_ID::"
    },
    {
      "name": "APCA_API_SECRET_KEY", 
      "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:algo/alpaca/shared:APCA_API_SECRET_KEY::"
    }
  ]
}
```

## Security Best Practices

1. **Never commit credentials to git**
   - `.gitignore` should exclude `.env` files
   - Keep API keys in environment variables or Secrets Manager

2. **Use paper trading for testing**
   - Don't give real trading credentials to dev/staging environments
   - Paper trading API has same interface but trades simulation accounts

3. **Rotate credentials regularly**
   - Generate new keys in Alpaca dashboard
   - Update in Secrets Manager
   - Orchestrator will automatically use fresh credentials

4. **Restrict IAM access**
   - Only Lambda/ECS tasks should have permission to read Alpaca secrets
   - Use least-privilege IAM roles

## Testing Paper Trading

After credentials are configured:

```bash
# Run orchestrator in paper mode
python3 scripts/trigger_orchestrator.py --mode paper --run morning

# Monitor execution
# - Phase 1: Data freshness check ✓
# - Phase 2-6: Position & exposure checks ✓
# - Phase 7: Signal generation ✓
# - Phase 8: Paper trades placed ✓
```

Expected output:
- Signals generated in Phase 7
- Paper orders placed in Phase 8 (visible in Alpaca dashboard)
- Positions updated in Phase 9

## Troubleshooting

**Error: "Credentials not found"**
- Verify env vars are set: `echo $APCA_API_KEY_ID`
- For AWS: check Secrets Manager has the secret
- For local: export before running orchestrator

**Error: "Credentials are stale"**
- Credentials are cached for 5 minutes
- Wait 5 minutes or restart orchestrator
- Check Secrets Manager for correct values

**Error: "Authentication failed"**
- Verify API keys in Alpaca dashboard (Settings → API Keys)
- Ensure using **Paper Trading** account (not live)
- Check credentials haven't been rotated/invalidated

**Paper orders not placed**
- Check Phase 8 logs for order placement
- Verify Alpaca account has sufficient buying power ($0 simulator)
- Check market hours (orders only place during 9:30 AM - 4:00 PM ET)

## References

- [Alpaca API Documentation](https://docs.alpaca.markets)
- [Paper Trading Guide](https://docs.alpaca.markets/trading/getting-started)
- [API Key Management](https://docs.alpaca.markets/api-references/broker-api/authentication)
