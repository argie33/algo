# GitHub Actions Secrets Setup

To enable orchestrator execution via GitHub Actions, add these secrets to your repository:

**Settings → Secrets and variables → Actions**

Add the following secrets:

1. **AWS_ACCESS_KEY_ID**
   - Value: Your AWS IAM access key

2. **AWS_SECRET_ACCESS_KEY**
   - Value: Your AWS IAM secret access key

3. **APCA_API_KEY_ID**
   - Value: Your Alpaca API key ID

4. **APCA_API_SECRET_KEY**
   - Value: Your Alpaca API secret key

5. **APCA_API_BASE_URL**
   - Value: `https://paper-api.alpaca.markets` (for paper trading)

Once secrets are added, the orchestrator-scheduler.yml workflow will automatically:
- Trigger on the configured schedule (9:30 AM, 1 PM, 3 PM, 4:05 PM ET on weekdays)
- Load these environment variables
- Execute the orchestrator Lambda via GitHub Actions
- Update dashboard with current data

## Testing

To manually test the workflow:
```bash
gh workflow run orchestrator-scheduler.yml --repo argie33/algo
```

Check execution:
```bash
gh run view <RUN_ID> --log
```
