# URGENT: AWS Lambda Fix Required

## Problem
The production Lambda function `stocks-webapp-api-dev` is failing with syntax errors causing 502 Bad Gateway errors across the entire site.

## Error
```
Runtime.UserCodeSyntaxError: SyntaxError: Invalid or unexpected token
```

## Solution

### Option 1: Quick Redeploy with AWS CLI (Recommended)
```bash
cd /home/stocks/algo/webapp

# Use admin credentials (not the 'reader' user)
aws configure --profile admin

# Redeploy Lambda function
cd lambda
zip -r ../lambda-deploy.zip . -x "*.git*" -x "*node_modules*" -x "*.log"
cd ..
aws lambda update-function-code \
  --function-name stocks-webapp-api-dev \
  --zip-file fileb://lambda-deploy.zip \
  --profile admin
```

### Option 2: Use CloudFormation/SAM
```bash
# If SAM CLI is available
sam deploy --guided
```

### Option 3: AWS Console
1. Go to AWS Lambda Console
2. Find function: `stocks-webapp-api-dev`
3. Upload new deployment package: `/home/stocks/algo/webapp/lambda-package.zip`
4. Click "Deploy"

## Verification
After deployment, test the endpoint:
```bash
curl https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/health
```

## Current Status
- **API Gateway**: `qda42av7je` (working)
- **Lambda**: `stocks-webapp-api-dev` (FAILING with syntax error)
- **CloudFront**: `d1copuy2oqlazx.cloudfront.net` (working, but returning Lambda errors)
- **Last Deployment**: 2025-10-02 22:36:41 UTC
- **Current AWS User**: `reader` (insufficient permissions)

## Notes
- Local Lambda code (`webapp/lambda/server.js`) has no syntax errors
- Issue is with deployed code only
- Need admin AWS credentials to redeploy
