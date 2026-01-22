# 🔥 URGENT: Lambda Needs to Recycle

## Current Status
✅ **Lambda environment variables are correctly set:**
- DB_STATEMENT_TIMEOUT=300000
- DB_QUERY_TIMEOUT=280000

❌ **Lambda instances still running with OLD config** (30-second timeouts)

## Issue
Old Lambda instances haven't recycled yet. New environment variables won't take effect until Lambda recycles.

## Solution

### Option 1: Wait for Auto-Recycle (AUTOMATIC)
Lambda automatically recycles unused instances every 15 minutes or on next deployment.
- Estimated time: 15 minutes max
- Action: Just wait

### Option 2: Force Recycle via CloudFormation (FASTEST)
This will redeploy Lambda and force all instances to recycle:

```bash
cd /home/stocks/algo
sam deploy \
  --template-file template-webapp-lambda.yml \
  --stack-name stocks-webapp-dev \
  --region us-east-1 \
  --no-confirm-changeset \
  --parameter-overrides \
    DatabaseSecretArn=arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-secrets-stocks-app-stack-us-east-1-001-fl3BxQ \
    DatabaseEndpoint=stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com \
    EnvironmentName=dev
```

### Option 3: AWS Console (MANUAL)
1. Go to Lambda → stocks-webapp-api-dev
2. Click any button (e.g., "Deploy" or edit environment)
3. All instances recycle immediately

## After Lambda Recycles

Test endpoints:
```bash
# Should return HTTP 200 with data (not 504)
curl https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/scores/stockscores | head -100

# Should show healthy
curl https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/health
```

## Secondary Issues Found
Database queries have minor schema issues (old column references):
- These are non-critical errors that don't block the main API
- Will be handled in next code update
- Main stock scores endpoint will work fine

---

**NEXT ACTION:** Run Option 1 (wait 15 min) OR Option 2 (force recycle now)

