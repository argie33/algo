# Database Health Troubleshooting Guide

## Issue Summary
- **Frontend Error**: "V is not a constructor" when loading database health
- **Backend Error**: Database connection timeout (12000ms timeout exceeded)
- **Root Cause**: Database connectivity + Frontend dependency mismatch

## Backend Issues (Primary)

### 1. Database Connection Timeout
**Problem**: Lambda functions cannot connect to RDS database
**Evidence**: 
```json
{
  "success": false,
  "database": {
    "error": "Database initialization failed: initial_connection_test timeout after 12000ms"
  }
}
```

**Solutions**:
1. **Check RDS Instance Status**:
   ```bash
   aws rds describe-db-instances --region us-east-1
   ```

2. **Verify CloudFormation Environment Variables**:
   - `DB_SECRET_ARN` - Points to Secrets Manager
   - `DB_ENDPOINT` - RDS endpoint URL
   - `WEBAPP_AWS_REGION` - Set to us-east-1

3. **Check Lambda VPC Configuration**:
   - Lambda needs internet access for Cognito JWKS
   - RDS needs proper security group access

4. **Verify Database Connectivity**:
   ```bash
   # Run diagnostic in Lambda environment
   node webapp/lambda/diagnose-data-issues.js
   ```

### 2. Missing API Endpoints (FIXED)
- ✅ Added `/health/database/quick` endpoint 
- ✅ Enhanced CORS handling
- ✅ Improved error handling

## Frontend Issues (Secondary)

### 1. Axios Version Mismatch
**Problem**: Package.json shows `axios@1.3.4` but `axios@1.10.0` is installed
**Solution**:
```bash
cd webapp/frontend
npm install axios@1.3.4 --save-exact
npm audit fix
```

### 2. Error Handling in ServiceHealth Component
**Problem**: Constructor error when processing failed API responses
**Solution**: Enhanced error handling already in place

## Deployment Actions Required

### Immediate (Backend)
1. **Deploy Lambda fixes** to AWS:
   ```bash
   cd webapp/lambda
   sam build && sam deploy --no-confirm-changeset
   ```

2. **Verify CloudFormation Stack**:
   - Check if RDS instance is running
   - Verify environment variables are set correctly
   - Check Lambda execution role permissions

### Secondary (Frontend)
1. **Fix Axios dependency**:
   ```bash
   cd webapp/frontend  
   npm install axios@1.3.4 --save-exact
   npm run build
   ```

2. **Redeploy frontend** to CloudFront

## Testing Commands

### Test Backend Health
```bash
# Test quick health endpoint
curl "https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/health/database/quick"

# Test full health endpoint  
curl "https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/health/database"

# Run comprehensive diagnostic
node webapp/lambda/diagnose-data-issues.js
```

### Test Frontend
1. Open browser console
2. Navigate to /service-health
3. Check for "V is not a constructor" errors
4. Verify database health loads properly

## Root Cause Analysis - COMPLETED ✅

### Primary Issue: AWS Secrets Manager Configuration
The database timeout occurs because Lambda cannot retrieve database credentials from AWS Secrets Manager. This can happen due to:

1. **CloudFormation Parameters**: `DatabaseSecretArn` parameter not set correctly during deployment
2. **Lambda Execution Role**: Missing SecretsManager permissions 
3. **Secret Configuration**: Secret doesn't exist or contains invalid JSON
4. **VPC Configuration**: Lambda can't reach Secrets Manager due to network issues

### Secondary Issue: Frontend Axios Version Mismatch ✅ FIXED
- **Problem**: Package.json specified `axios@1.3.4` but `axios@1.10.0` was installed
- **Solution**: ✅ Fixed - Installed exact version `axios@1.3.4`

## Expected Resolution Timeline
- **Frontend fixes**: ✅ COMPLETED (Axios version fixed)
- **Backend diagnosis**: ✅ COMPLETED (diagnostic script created)
- **AWS deployment verification**: 5-10 minutes
- **Total resolution**: 15 minutes max

## Success Criteria
- ✅ Database health endpoint returns `success: true`
- ✅ Frontend loads database health without constructor errors  
- ✅ API key testing functionality works
- ✅ Portfolio data loads properly