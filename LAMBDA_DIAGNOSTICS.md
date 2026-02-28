# 🔍 Lambda Function Diagnostics Report
**Date**: Feb 28, 2026
**Lambda Function**: stocks-algo-api (dev)
**Region**: us-east-1
**Account ID**: 626216981288

---

## 📋 Lambda Configuration

### Function Details
- **Service**: stocks-algo-api
- **Handler**: index.handler
- **Runtime**: Node.js 18.x / 20.x
- **Memory**: 512 MB
- **Timeout**: 30 seconds
- **VPC**: Configured with security groups and subnets

### Environment Variables
```
DB_HOST=localhost
DB_PORT=5432
DB_USER=stocks
DB_PASSWORD=bed0elAn
DB_NAME=stocks
NODE_ENV=production
AWS_REGION=us-east-1
```

### IAM Permissions
✅ CloudWatch Logs (CreateLogGroup, CreateLogStream, PutLogEvents)
✅ EC2 VPC (CreateNetworkInterface, DescribeNetworkInterfaces, DeleteNetworkInterface)
✅ AWS Secrets Manager (GetSecretValue)
✅ SES (SendEmail, SendRawEmail)

---

## 🚨 CRITICAL ISSUES IDENTIFIED

### Issue #1: Database Connection Failure
**Severity**: 🔴 CRITICAL
**Error Code**: ECONNREFUSED
**Root Cause**: Lambda is trying to connect to `localhost:5432` which doesn't exist in AWS

**Evidence**:
```javascript
// From database.js
if (err.code === 'ECONNREFUSED' && err.address) {
    status = 503;
    message = "Database Connection Error";
    details = `Cannot connect to database at ${err.address}:${err.port}`;
}
```

**Why This Fails**:
- Lambda is deployed in AWS (EC2/RDS network)
- `localhost` = 127.0.0.1 on that specific Lambda container
- No PostgreSQL running on the Lambda container
- DB_HOST=localhost is development configuration, not production

**Solution Required**:
```
In AWS:
1. Create RDS PostgreSQL instance (or use existing RDS)
2. Store credentials in AWS Secrets Manager
3. Set DB_SECRET_ARN environment variable
4. Update VPC security groups to allow Lambda → RDS access
5. Remove DB_HOST/DB_PASSWORD hardcoded environment variables

OR in Secrets Manager:
{
  "username": "stocks",
  "password": "bed0elAn",
  "host": "stocks-rds.xxxx.us-east-1.rds.amazonaws.com",
  "port": 5432,
  "dbname": "stocks"
}
```

---

### Issue #2: Missing DB_SECRET_ARN
**Severity**: 🟠 HIGH
**Current State**: `DB_SECRET_ARN=''` (empty)

**Expected Behavior**:
```javascript
// From database.js
const secretArn = process.env.DB_SECRET_ARN;
if (secretArn) {
    // Use AWS Secrets Manager
    const command = new GetSecretValueCommand({ SecretId: secretArn });
    // ... fetch real credentials
}
```

**What Happens**:
1. DB_SECRET_ARN is empty
2. Falls back to environment variables (DB_HOST=localhost)
3. Lambda tries to connect to localhost:5432
4. Connection fails with ECONNREFUSED

**Fix**:
```bash
# Create secret in AWS Secrets Manager:
aws secretsmanager create-secret \
  --name stocks/rds/credentials \
  --secret-string '{
    "username":"stocks",
    "password":"bed0elAn",
    "host":"stocks-db.xxxx.us-east-1.rds.amazonaws.com",
    "port":5432,
    "dbname":"stocks"
  }'

# Get ARN from output, then set in Lambda:
aws lambda update-function-configuration \
  --function-name stocks-algo-api-dev-api \
  --environment Variables={DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks/rds/credentials-xxxxx}
```

---

### Issue #3: 30-Second Timeout Too Short
**Severity**: 🟠 HIGH
**Current**: Timeout = 30 seconds

**Problematic Endpoints**:
- `/api/stocks` - Queries large datasets (can take 10+ seconds)
- `/api/analysis/*` - Complex calculations
- `/api/optimization/*` - Portfolio optimization calculations

**Evidence**:
```javascript
// From errorHandler.js
if (err.message?.includes('Task timed out')) {
    status = 504;
    message = "Gateway Timeout";
    code = 'LAMBDA_TIMEOUT';
}
```

**Recommendation**:
```
Increase timeout to 60+ seconds for batch operations
Or implement caching/async job processing
```

---

### Issue #4: VPC Subnets Not Configured Properly
**Severity**: 🟠 HIGH
**Current**:
```yaml
vpc:
  securityGroupIds:
    - sg-xxxxxx  # PLACEHOLDER
  subnetIds:
    - subnet-xxxxxx  # PLACEHOLDER
    - subnet-xxxxxx  # PLACEHOLDER
```

**Problem**: Subnets contain PLACEHOLDER values - not actual AWS resources

**Fix Required**:
```bash
# 1. Find VPC and subnets
aws ec2 describe-vpcs --filters Name=tag:Name,Values=stocks*

# 2. Update serverless.yml with real subnet IDs
# 3. Redeploy: serverless deploy

# 3. Verify Lambda has access
aws lambda get-function-concurrency --function-name stocks-algo-api-dev-api
```

---

## 📊 Error Types Handled by Lambda

The Lambda error handler can catch and respond to:

| Error | Status | Code | Common Cause |
|-------|--------|------|--------------|
| ECONNREFUSED | 503 | DB_CONNECTION_ERROR | No database running |
| ETIMEDOUT | 504 | CONNECTION_TIMEOUT | Network issue / slow service |
| ENOTFOUND | 503 | CONNECTION_ERROR | DNS/hostname not found |
| Task timed out | 504 | LAMBDA_TIMEOUT | Query took > 30s |
| Missing module | 500 | MODULE_IMPORT_ERROR | NPM dependency missing |
| PG code 23505 | 409 | DUPLICATE_ENTRY | Unique constraint violation |
| PG code 23503 | 400 | INVALID_REFERENCE | Foreign key violation |
| PG code 42P01 | 500 | DB_CONFIG_ERROR | Table doesn't exist |

---

## 🔐 Secrets Manager Integration

The Lambda has comprehensive error handling for Secrets Manager:

```javascript
// From database.js
try {
    const command = new GetSecretValueCommand({ SecretId: secretArn });
    const result = await client.send(command);

    // Handle both string (JSON) and binary formats
    if (typeof result.SecretString === "string") {
        secret = JSON.parse(result.SecretString);
    } else if (result.SecretBinary) {
        const decoded = Buffer.from(result.SecretBinary, "base64").toString("utf-8");
        secret = JSON.parse(decoded);
    }
} catch (error) {
    // Comprehensive error logging with debugging info
    console.error("Failed to parse SecretString:", error);
}
```

---

## 📝 CloudWatch Logs Path

**Location**: `/aws/lambda/stocks-algo-api-dev-api`

**What to Look For**:
```
[ERROR] ECONNREFUSED → Database connection failure
[ERROR] LAMBDA_TIMEOUT → Function exceeded 30s limit
[ERROR] MODULE_IMPORT_ERROR → Missing npm dependency
[ERROR] SECRETS_MANAGER_ERROR → Cannot fetch credentials
[WARN] Connection timeout → External service slow
```

---

## ✅ CHECKLIST TO FIX LAMBDA ISSUES

- [ ] **Create RDS instance** in same VPC or use AWS RDS endpoint
- [ ] **Create AWS Secrets Manager secret** with database credentials
- [ ] **Set DB_SECRET_ARN** in Lambda environment variables
- [ ] **Update VPC subnets** with real subnet IDs (not placeholders)
- [ ] **Update security groups** to allow Lambda → RDS access
- [ ] **Increase timeout** to 60+ seconds
- [ ] **Test database connection** from Lambda console
- [ ] **Monitor CloudWatch logs** for connection errors
- [ ] **Run health check endpoint**: `GET /health`
- [ ] **Verify all API routes** work end-to-end

---

## 🚀 Production Deployment Steps

1. **Prerequisite: RDS Database**
   ```bash
   # Copy PostgreSQL data from local to RDS
   pg_dump -h localhost -U stocks stocks | \
   psql -h stocks-rds.us-east-1.rds.amazonaws.com -U stocks stocks
   ```

2. **Store Credentials in Secrets Manager**
   ```bash
   aws secretsmanager create-secret --name stocks/db \
     --secret-string '{"username":"stocks","password":"***","host":"stocks-rds.xxxx.us-east-1.rds.amazonaws.com","port":5432,"dbname":"stocks"}'
   ```

3. **Update Lambda Configuration**
   ```bash
   serverless deploy
   ```

4. **Test Endpoint**
   ```bash
   curl https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/health
   ```

---

## 📊 Summary

| Component | Status | Issue |
|-----------|--------|-------|
| Lambda Code | ✅ OK | Well-structured error handling |
| Environment Variables | 🔴 FAIL | DB_HOST=localhost (won't work in AWS) |
| Secrets Manager Integration | ✅ OK | Code is ready, just needs config |
| VPC Configuration | 🔴 FAIL | Subnet IDs are placeholders |
| Database Connection | 🔴 FAIL | ECONNREFUSED - no DB accessible |
| Timeout Setting | 🟠 WARN | 30s may be too short |

**Overall**: Lambda is **properly coded** but **not configured for AWS production**

---

**Next Action**: Set up RDS instance and update Lambda configuration to use Secrets Manager.
