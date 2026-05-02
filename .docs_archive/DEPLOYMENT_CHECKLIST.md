# Deployment Checklist — Ready for AWS

## Pre-Deployment Verification

### ✅ Credentials & Secrets
- [x] No hardcoded passwords in any config files
- [x] No hardcoded API keys in source code
- [x] `.env.local` in `.gitignore` 
- [x] Only `.env.example` files committed
- [x] All credentials read from environment variables
- [x] Database uses AWS Secrets Manager ARN (production)

### ✅ Configuration
- [x] serverless.yml: DB_PASSWORD not hardcoded
- [x] serverless.yml: CORS restricted (not wildcard)
- [x] docker-compose.yml: Postgres password from `${DB_PASSWORD}`
- [x] Dockerfile: Port is 3001 (not 3000)
- [x] API Gateway: Uses HTTP (not REST) for performance

### ✅ API Configuration  
- [x] vite.config.js: Proxy only in development mode
- [x] api.js: 3-level URL resolution (runtime → build → default)
- [x] CORS_ORIGIN configurable via environment
- [x] Frontend API points to localhost:3001 in dev
- [x] Frontend API points to CloudFront in production

### ✅ Security
- [x] Error handling doesn't expose sensitive data
- [x] Stack traces hidden in production
- [x] Authentication middleware working
- [x] CORS properly restricted
- [x] IAM permissions scoped correctly
- [x] Non-root user in Docker (nodejs)

### ✅ Database
- [x] Connection uses Secrets Manager (AWS)
- [x] Connection uses env vars (local)
- [x] Pool configuration present
- [x] Timeouts configured appropriately

### ✅ Loaders  
- [x] All use `os.getenv()` for credentials
- [x] Check for missing credentials and exit
- [x] No hardcoded database connection strings
- [x] Use db_helper.py for database access

---

## Local Development Setup

```bash
# 1. Create environment file
cp .env.example .env.local

# 2. Edit with your credentials
nano .env.local
# Set: DB_PASSWORD, ALPACA_API_KEY, ALPACA_SECRET_KEY

# 3. Start database
docker-compose up -d postgres

# 4. Start API server
PORT=3001 node webapp/lambda/index.js

# 5. Start frontend (in another terminal)
cd webapp/frontend
npm run dev
```

Open http://localhost:5173

---

## AWS Production Deployment

### Step 1: Set up Secrets Manager
```bash
aws secretsmanager create-secret \
  --name rds-stocks-secret \
  --secret-string '{
    "username": "stocks",
    "password": "SECURE_PASSWORD_HERE",
    "engine": "postgres",
    "host": "stocks-db.xxxxx.rds.amazonaws.com",
    "port": 5432,
    "dbname": "stocks"
  }' \
  --region us-east-1
```

### Step 2: Set Lambda Environment Variables
In AWS Lambda console or via AWS CLI:
```bash
DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:rds-stocks-secret
ALPACA_API_KEY=your_alpaca_key
ALPACA_SECRET_KEY=your_alpaca_secret
CORS_ORIGIN=https://YOUR_CLOUDFRONT_DOMAIN
NODE_ENV=production
```

### Step 3: Deploy
```bash
cd webapp/lambda
serverless deploy --stage prod

# Or with AWS SAM:
sam build --template template-webapp-lambda.yml
sam deploy --guided
```

### Step 4: Update CloudFront Origin
Point CloudFront to the new API Gateway URL from deployment output

### Step 5: Update Cognito
Configure Cognito redirect URIs to CloudFront domain

---

## Post-Deployment Verification

```bash
# Test API health
curl https://YOUR_CLOUDFRONT_DOMAIN/api/health

# Test stocks endpoint
curl https://YOUR_CLOUDFRONT_DOMAIN/api/stocks?limit=5

# Check CloudWatch logs
aws logs tail /aws/lambda/stocks-algo-api --follow
```

---

## Rollback Plan

If deployment fails:
1. Revert Lambda function code: `serverless rollback`
2. Check CloudWatch logs for errors
3. Verify Secrets Manager is accessible
4. Verify security group allows RDS connection
5. Re-deploy: `serverless deploy --stage prod`

---

## Monitoring

### CloudWatch Metrics
- Lambda: Duration, Errors, Throttles, ConcurrentExecutions
- RDS: DatabaseConnections, CPUUtilization, FreeableMemory
- API Gateway: Count, 4XX, 5XX

### Alarms to Set
- Lambda errors > 5 per minute
- Lambda duration > 30 seconds
- RDS CPU > 80%
- RDS connections > 80% of max

---

## Summary

✅ All systems ready for AWS deployment
✅ Credentials properly managed
✅ CORS and security configured
✅ Configuration environment-specific
✅ Monitoring and rollback planned

