# RDS Connectivity Troubleshooting Guide

## Setup
API Lambda (`algo-api-dev`) → RDS instance (`algo-db`) at `algo-db.*.us-east-1.rds.amazonaws.com`

## Infrastructure Configuration (Verified)
- RDS Instance: `algo-db` (identified as `${var.project_name}-db` where project_name="algo")
- RDS Endpoint: `algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com:5432`
- RDS Security Group: `algo-rds-sg`
- Lambda Security Group: `algo-api-lambda-sg`
- Database Name: `stocks` (var.rds_db_name)
- Master User: `stocks` (var.rds_username)
- Credentials: Stored in `algo-db-credentials-dev` Secrets Manager secret
- Port: 5432 (PostgreSQL default)

## Security Group Rules (Verified in Code)
✅ API Lambda egress rule: TCP 5432 to VPC CIDR
✅ RDS Security Group ingress rule: TCP 5432 from API Lambda SG
✅ RDS Security Group ingress rule: TCP 5432 from ECS tasks SG
✅ RDS Security Group ingress rule: TCP 5432 from Algo Lambda SG

## Diagnostic Steps

### Step 1: Verify RDS Instance Status
**AWS Console → RDS → Databases → algo-db**
- [ ] Status: Should be **"available"** (not "creating", "modifying", "failed", "deleting")
- [ ] Engine: PostgreSQL
- [ ] Endpoint: `algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com`
- [ ] Port: 5432

**If Status ≠ "available":**
- Wait for instance to finish starting (can take 5-15 minutes)
- Check Reboot status under "Maintenance & Backups" tab
- If permanently failed: Contact AWS Support or restart the instance manually

### Step 2: Verify Security Group Configuration
**AWS Console → RDS → algo-db → Connectivity & Security tab → Security Groups → algo-rds-sg**
- [ ] Inbound Rules exist:
  - [ ] TCP 5432 from `algo-api-lambda-sg` (Description: "Allow PostgreSQL from API Lambda")
  - [ ] TCP 5432 from `algo-ecs-tasks-sg` (Description: "Allow PostgreSQL from ECS tasks")
  - [ ] TCP 5432 from `algo-algo-lambda-sg` (Description: "Allow PostgreSQL from Algo Lambda")

**If rules are missing:**
1. Click "Edit inbound rules"
2. Add rules:
   ```
   Type: PostgreSQL
   Protocol: TCP
   Port Range: 5432
   Source: <select the Lambda/ECS security group>
   Description: "Allow PostgreSQL from [source]"
   ```
3. Save

### Step 3: Verify Credentials in Secrets Manager
**AWS Console → Secrets Manager → algo-db-credentials-dev**
- [ ] Secret exists and contains JSON with:
  ```json
  {
    "username": "stocks",
    "password": "<32-char random string>",
    "host": "algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com",
    "port": 5432,
    "dbname": "stocks",
    "engine": "postgresql"
  }
  ```

**Critical Check:**
- [ ] Password in secret matches password set in RDS when instance was created
- [ ] To verify: 
  - Get secret password: `aws secretsmanager get-secret-value --secret-id algo-db-credentials-dev`
  - Copy the password value
  - Try logging in via CloudShell (see Step 4)

### Step 4: Test Connection from CloudShell
**AWS Console → CloudShell (top-right terminal icon)**

Run this command to test connectivity:
```bash
psql \
  -h algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com \
  -U stocks \
  -d stocks \
  -c "SELECT 1 as connection_test;"
```

When prompted for password, paste the password from Secrets Manager (from Step 3).

**Expected Output:**
```
connection_test
────────────────
              1
(1 row)
```

**If Connection Fails:**
- [ ] "Connection timed out" → RDS security group not allowing traffic (check Step 2)
- [ ] "password authentication failed" → Credentials mismatch (check Step 3, may need to reset RDS password)
- [ ] "cannot connect to server" → RDS instance not in "available" state (check Step 1)

### Step 5: Verify Lambda Environment Variables
**AWS Console → Lambda → algo-api-dev → Configuration → Environment variables**
- [ ] `DB_SECRET_ARN`: Should be ARN from Step 3 secret (e.g., `arn:aws:secretsmanager:us-east-1:...`)
- [ ] `DB_HOST`: Should be `algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com` (or use RDS Proxy if enabled)
- [ ] `DB_PORT`: Should be `5432`
- [ ] `DB_NAME`: Should be `stocks`
- [ ] `DB_USER`: Should be `stocks`
- [ ] `DB_SSL`: Should be `require` (for Secrets Manager secret retrieval; RDS Proxy requires TLS)

**If variables are incorrect:**
1. Update the variables
2. Deploy the Lambda code:
   ```bash
   git push main  # Triggers deploy-code.yml workflow
   ```

### Step 6: Verify Lambda VPC Configuration
**AWS Console → Lambda → algo-api-dev → Configuration → VPC**
- [ ] VPC: Should match RDS VPC (`algo-vpc`)
- [ ] Subnets: Should be private subnets (same ones as RDS)
- [ ] Security Groups: Should include `algo-api-lambda-sg`

**If VPC config is wrong:**
1. Edit VPC settings
2. Select correct VPC, private subnets, and security group
3. Save (Lambda needs 1-2 minutes to update)

### Step 7: Test Lambda Connection
**AWS Console → Lambda → algo-api-dev → Code tab**
1. Create a test event:
   ```json
   {
     "routeKey": "GET /api/health",
     "requestContext": {
       "http": {
         "method": "GET",
         "path": "/api/health"
       }
     },
     "headers": {}
   }
   ```
2. Click "Test"
3. Check the result in the execution result panel

**Expected:**
- [ ] Status: 200 (success)
- [ ] Response includes database info

**If fails:**
- [ ] Check CloudWatch logs: **CloudWatch → Log groups → /aws/lambda/algo-api-dev**
- [ ] Look for connection errors in recent logs

## Recovery Steps (If Still Failing)

### Option A: Reset RDS Password
If you suspect credentials mismatch:

1. **AWS Console → RDS → algo-db → Modify**
2. **Master password**: Generate new password
3. **Apply immediately**: Yes
4. Wait for reboot (2-5 minutes)
5. **Update Secrets Manager**:
   ```bash
   aws secretsmanager update-secret \
     --secret-id algo-db-credentials-dev \
     --secret-string '{"username":"stocks","password":"<NEW_PASSWORD>","host":"algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com","port":5432,"dbname":"stocks","engine":"postgresql"}'
   ```
6. Deploy Lambda code to pick up new secret

### Option B: Recreate RDS Instance
If RDS instance is permanently failed:
1. Backup existing database (if possible)
2. Delete the failed RDS instance
3. Run Terraform to recreate:
   ```bash
   cd terraform
   terraform apply -target=module.database.aws_db_instance.main
   ```
4. Reinitialize database schema using DB Init Lambda workflow

### Option C: Enable RDS Proxy (Already Configured)
RDS Proxy is enabled by default and provides connection pooling. Verify it's working:

**AWS Console → RDS → Proxies → algo-proxy**
- [ ] Status: Should be **"available"**
- [ ] Use proxy endpoint instead of direct RDS: `algo-proxy.cojggi2mkthi.proxy-us-east-1.rds.amazonaws.com:5432`

## Code-Level Verification

### API Lambda Connection Logic
File: `lambda/api/lambda_function.py` lines 36-90
- Tries to connect using `DB_SECRET_ARN` or environment variables
- Logs connection attempts to CloudWatch
- Implements 10-second connection timeout

### DB Init Lambda
File: `lambda/db-init/lambda_function.py` lines 93-240
- Runs after infrastructure deploy
- Creates `stocks` user if missing
- Initializes database schema from `schema.sql`
- Idempotent: safe to run multiple times

## Summary Checklist
- [ ] RDS instance is "available"
- [ ] Security group rules allow Lambda → RDS on port 5432
- [ ] Secrets Manager secret has correct password matching RDS
- [ ] Lambda environment variables point to correct secret ARN and RDS endpoint
- [ ] Lambda is in same VPC as RDS
- [ ] Test connection from CloudShell succeeds
- [ ] Lambda execution logs show successful database connection

## Next Steps
Once RDS is responding to connections:
1. Invoke DB Init Lambda: `aws lambda invoke --function-name algo-db-init-dev --payload '{}' response.json`
2. Verify database tables: `psql -h ... -U stocks -d stocks -c "\\dt"`
3. Test API endpoint: `curl https://<api-gateway-url>/api/health`
4. Check frontend loads data: `https://<cloudfront-domain>`
