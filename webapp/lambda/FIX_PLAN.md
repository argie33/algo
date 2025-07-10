# Lambda-RDS Connectivity Fix Plan

## 🔥 CRITICAL ISSUES TO FIX IMMEDIATELY

### 1. Deploy Code Fix (URGENT)
**Problem**: Lambda still has syntax error preventing startup
**Solution**: 
```bash
cd /home/stocks/algo/webapp/lambda
./deploy-fix.sh
```

### 2. Fix VPC Networking (CRITICAL)
**Problem**: Lambda in private subnet without NAT Gateway
**Current Config**:
- VPC: vpc-01bac8b5a4479dad9
- Lambda Subnets: subnet-0142dc004c9fc3e0c, subnet-0458999323649c79d
- Security Group: sg-0075699472f6edb04

**Required Actions**:
1. Create NAT Gateway in public subnet
2. Update route tables to route 0.0.0.0/0 to NAT Gateway
3. Verify security group allows outbound on port 5432

### 3. Increase Lambda Memory
**Problem**: 128MB too low for database connections
**Solution**: Increase to 512MB minimum
```bash
aws lambda update-function-configuration \
  --function-name financial-dashboard-api-dev \
  --memory-size 512 \
  --region us-east-1
```

### 4. Security Group Rules
**Problem**: May not allow outbound to RDS
**Required Rule**: 
- Type: PostgreSQL (5432)
- Protocol: TCP
- Port: 5432
- Destination: RDS security group or 0.0.0.0/0

### 5. RDS Subnet Group
**Problem**: Lambda and RDS may be in incompatible subnets
**Check**: Ensure RDS is in same VPC and accessible AZs

## 🔧 DIAGNOSTIC COMMANDS

### Check VPC Configuration
```bash
node diagnose-vpc.js
```

### Test Lambda Deployment
```bash
aws lambda invoke \
  --function-name financial-dashboard-api-dev \
  --payload '{"httpMethod":"GET","path":"/health","queryStringParameters":{"quick":"true"}}' \
  --region us-east-1 \
  response.json && cat response.json
```

### Check Lambda Logs
```bash
aws logs tail /aws/lambda/financial-dashboard-api-dev --follow --region us-east-1
```

## 🚀 STEP-BY-STEP FIX PROCESS

### Step 1: Fix Code and Deploy
```bash
cd /home/stocks/algo/webapp/lambda
./deploy-fix.sh
```

### Step 2: Increase Lambda Resources
```bash
aws lambda update-function-configuration \
  --function-name financial-dashboard-api-dev \
  --memory-size 512 \
  --timeout 60 \
  --region us-east-1
```

### Step 3: Check VPC Setup
```bash
node diagnose-vpc.js
```

### Step 4: Fix Networking (if needed)
- Create NAT Gateway in public subnet
- Update route tables
- Fix security group rules

### Step 5: Test Database Connection
```bash
# Test health endpoint
curl "https://q570hqc8i9.execute-api.us-east-1.amazonaws.com/dev/health?quick=true"

# Test database endpoint
curl "https://q570hqc8i9.execute-api.us-east-1.amazonaws.com/dev/health"
```

## 📊 COMMON ERROR PATTERNS

### "Connection refused" (ECONNREFUSED)
- RDS not running or wrong endpoint
- Security group blocking connection
- Wrong port (should be 5432)

### "Connection timeout" (ETIMEDOUT)
- No route to RDS (missing NAT Gateway)
- Lambda in wrong subnet
- VPC routing issue

### "DNS lookup failed" (ENOTFOUND)
- Wrong RDS endpoint
- VPC DNS settings issue
- RDS not in same VPC

### "Authentication failed" (28000)
- Wrong username/password in Secrets Manager
- User doesn't exist in database
- Database name incorrect

## 🎯 SUCCESS CRITERIA

1. ✅ Lambda starts without syntax errors
2. ✅ Lambda can connect to internet via NAT Gateway
3. ✅ Security group allows outbound port 5432
4. ✅ RDS accepts connections from Lambda security group
5. ✅ Health endpoint returns database connection success

## 🔄 ALTERNATIVE ARCHITECTURE

If VPC issues persist, consider:
1. **RDS Proxy**: Add RDS Proxy for connection pooling
2. **Public RDS**: Temporarily make RDS publicly accessible for testing
3. **Lambda in Public Subnet**: Move Lambda to public subnet (not recommended)
4. **VPC Endpoints**: Use VPC endpoints for AWS services

## 📞 EMERGENCY ROLLBACK

If changes break the system:
```bash
# Revert Lambda to previous version
aws lambda update-function-code \
  --function-name financial-dashboard-api-dev \
  --zip-file fileb://backup-function.zip \
  --region us-east-1
```