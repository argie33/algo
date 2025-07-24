# Troubleshooting: CloudFormation Config API 500 Error

## Issue Summary

**Error**: Site not available with 500 Internal Server Error from CloudFormation config endpoint
**Endpoint**: `GET https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/config/cloudformation?stackName=stocks-webapp-dev`
**Root Cause**: Lambda function lacks CloudFormation permissions to describe stacks

## Error Analysis

### Frontend Error Messages
```javascript
configurationService.js:87 GET https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/config/cloudformation?stackName=stocks-webapp-dev 500 (Internal Server Error)
configurationService.js:116 ⚠️ Failed to fetch CloudFormation config from both main and emergency API: 500
configurationService.js:123 🔐 IAM Permission Error: Lambda function needs CloudFormation permissions
configurationService.js:124 💡 Solution: Update CloudFormation template to add cloudformation:DescribeStacks permission
```

### Backend Error (Expected)
```json
{
  "error": "Access denied",
  "message": "Lambda function does not have permission to describe CloudFormation stacks",
  "code": "AccessDenied"
}
```

## Root Cause Analysis

### 1. Missing IAM Permissions
The Lambda execution role in the CloudFormation template was missing CloudFormation permissions:

**Missing Permissions**:
- `cloudformation:DescribeStacks` - Required to get stack outputs
- `cloudformation:ListStacks` - Required to list available stacks

### 2. Configuration Service Flow
The frontend `configurationService.js` tries to fetch CloudFormation configuration in this order:
1. Check `window.__CLOUDFORMATION_CONFIG__` (not set)
2. Fetch from `/api/config/cloudformation` endpoint (fails with 500)
3. Try emergency endpoint `/api/health/config/cloudformation` (also fails)
4. Falls back to safety configuration with auth disabled

### 3. Impact
- Site becomes unavailable because authentication configuration fails
- Frontend gets safety fallback config with `authentication: false`
- User cannot access protected resources

## Solution Implementation

### Step 1: Added CloudFormation Permissions to IAM Role

Updated `/home/stocks/algo/webapp/lambda/cloudformation/aws-services-stack.yml`:

```yaml
LambdaExecutionRole:
  Type: AWS::IAM::Role
  Properties:
    # ... existing configuration
    Policies:
      # ... existing policies
      - PolicyName: CloudFormationAccess
        PolicyDocument:
          Version: '2012-10-17'
          Statement:
            - Effect: Allow
              Action:
                - cloudformation:DescribeStacks
                - cloudformation:ListStacks
              Resource: '*'
```

### Step 2: Error Handling in Configuration Service

The configuration service already includes proper error detection and handling:

```javascript
// configurationService.js:119-125
if (response.status === 500) {
  try {
    const errorData = await response.json();
    if (errorData.message && errorData.message.includes('not authorized to perform: cloudformation:DescribeStacks')) {
      console.error('🔐 IAM Permission Error: Lambda function needs CloudFormation permissions');
      console.error('💡 Solution: Update CloudFormation template to add cloudformation:DescribeStacks permission');
    }
  } catch (parseError) {
    // Ignore JSON parse errors
  }
}
```

### Step 3: CloudFormation Route Error Handling

The backend route properly catches and reports IAM permission errors:

```javascript
// routes/cloudformation.js:116-122
if (error.code === 'AccessDenied') {
  return res.status(403).json({
    error: 'Access denied',
    message: 'Lambda function does not have permission to describe CloudFormation stacks',
    code: error.code
  });
}
```

## Deployment Steps

### 1. Update CloudFormation Stack

Deploy the updated template with CloudFormation permissions:

```bash
cd /home/stocks/algo/webapp/lambda
aws cloudformation update-stack \
  --stack-name your-services-stack \
  --template-body file://cloudformation/aws-services-stack.yml \
  --parameters ParameterKey=EnvironmentName,ParameterValue=dev \
               ParameterKey=VpcId,ParameterValue=vpc-xxxxxx \
               ParameterKey=SubnetIds,ParameterValue=subnet-xxxxx,subnet-yyyyy \
  --capabilities CAPABILITY_IAM
```

### 2. Wait for Stack Update

Monitor the stack update:

```bash
aws cloudformation wait stack-update-complete --stack-name your-services-stack
aws cloudformation describe-stacks --stack-name your-services-stack --query 'Stacks[0].StackStatus'
```

### 3. Test Lambda Permissions

Verify the Lambda function can now access CloudFormation:

```bash
# Test the endpoint directly
curl "https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/config/cloudformation?stackName=stocks-webapp-dev"
```

Expected response:
```json
{
  "success": true,
  "stackName": "stocks-webapp-dev",
  "region": "us-east-1",
  "stackStatus": "UPDATE_COMPLETE",
  "api": {
    "gatewayUrl": "https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev"
  },
  "cognito": {
    "userPoolId": "us-east-1_XXXXXXXXX",
    "clientId": "xxxxxxxxxxxxxxxxxxxxxxxxxx"
  }
}
```

### 4. Verify Frontend Access

1. Clear browser cache
2. Reload the site
3. Check browser console - should see:
   ```
   ✅ CloudFormation config fetched from api
   ```
4. Site should now be available with proper authentication

## Prevention

### 1. IAM Policy Template
Always include CloudFormation permissions in Lambda execution roles that need to access stack outputs:

```yaml
- PolicyName: CloudFormationAccess
  PolicyDocument:
    Version: '2012-10-17'
    Statement:
      - Effect: Allow
        Action:
          - cloudformation:DescribeStacks
          - cloudformation:ListStacks
        Resource: '*'
```

### 2. Testing Checklist
- [ ] Test `/api/config/cloudformation` endpoint returns 200
- [ ] Test frontend configuration service initialization
- [ ] Verify authentication works after configuration load
- [ ] Check browser console for configuration errors

### 3. Monitoring
Set up CloudWatch alarms for:
- Lambda function errors (particularly 500s from config endpoints)
- CloudFormation API call failures
- Authentication configuration load failures

## Related Issues

This issue is related to:
- Authentication system depending on CloudFormation configuration
- Frontend configuration service fallback mechanisms
- Lambda IAM role permissions for AWS service access

## Status

**Resolution**: ✅ **FIXED**
- Added CloudFormation permissions to Lambda execution role
- Updated CloudFormation template with proper IAM policy
- Ready for deployment to resolve site availability issue

The site should be accessible after deploying the updated CloudFormation template.