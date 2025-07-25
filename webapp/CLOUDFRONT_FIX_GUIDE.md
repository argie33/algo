# CloudFront API Routing Fix Guide

## 🚨 Critical Issue
**All API endpoints are returning HTML instead of JSON**, preventing frontend pages from displaying data.

## Root Cause
CloudFront distribution is serving frontend static files for `/api/*` routes instead of forwarding requests to the Lambda function.

## Infrastructure Fix Required

### Step 1: Access CloudFront Console
```bash
# Get your CloudFront distribution ID
aws cloudfront list-distributions --query 'DistributionList.Items[?Aliases.Items[0]==`d1zb7knau41vl9.cloudfront.net`].Id' --output text
```

### Step 2: Configure API Behavior
In AWS CloudFront Console:

1. **Navigate to your distribution**: `d1zb7knau41vl9.cloudfront.net`
2. **Go to "Behaviors" tab**
3. **Create a new behavior** (or edit existing one)

#### Required Configuration:
```yaml
Path Pattern: "/api/*"
Origin and Origin Groups: 
  - Origin: [Your Lambda Function/API Gateway Origin]
  - NOT the S3 bucket origin

Cache and Origin Request Settings:
  - Cache Policy: "Managed-CachingDisabled" 
  - Origin Request Policy: "Managed-AllViewerExceptHostHeader"
  - Response Headers Policy: "Managed-CORS-with-preflight-and-SecurityHeadersPolicy"

Allowed HTTP Methods: 
  - GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE

Function Associations: None (unless specifically needed)

Precedence: 0 (MUST be higher priority than default behavior)
```

### Step 3: Behavior Order (Critical)
The behaviors must be in this order:
1. **`/api/*` → Lambda/API Gateway** (Precedence: 0)
2. **Default (`*`) → S3 Static Website** (Precedence: 1)

### Step 4: Validate Origins
Ensure you have two origins configured:
```yaml
Origin 1 (Lambda/API Gateway):
  - Origin Domain: [your-api-gateway-domain].execute-api.[region].amazonaws.com
  - OR: [your-lambda-function-url]
  - Protocol: HTTPS only
  - Port: 443

Origin 2 (S3 Static Website):
  - Origin Domain: [your-s3-bucket].s3-website-[region].amazonaws.com
  - Protocol: HTTP only (S3 website)
  - Port: 80
```

## Quick Test Commands

### Before Fix (Current State):
```bash
# This returns HTML (wrong)
curl -H "Accept: application/json" https://d1zb7knau41vl9.cloudfront.net/api/health
```

### After Fix (Expected):
```bash
# This should return JSON
curl -H "Accept: application/json" https://d1zb7knau41vl9.cloudfront.net/api/health
# Expected response:
# {"success": true, "message": "API health check passed", ...}
```

### Test All Endpoints:
```bash
# Run our comprehensive test
node test-api-routing.js
```

## Common Mistakes to Avoid

### ❌ Wrong Behavior Order
```
Default (*) - Precedence 0  ← WRONG
/api/* - Precedence 1       ← This never gets reached
```

### ✅ Correct Behavior Order  
```
/api/* - Precedence 0       ← Matches first
Default (*) - Precedence 1  ← Fallback for everything else
```

### ❌ Wrong Origin Assignment
```
/api/* → S3 Origin          ← WRONG - Returns HTML
```

### ✅ Correct Origin Assignment
```
/api/* → Lambda/API Gateway Origin  ← CORRECT - Returns JSON
Default → S3 Origin                 ← Static files
```

## Deployment Timeline

### Immediate (5 minutes):
1. Create/update `/api/*` behavior in CloudFront
2. Set correct origin and precedence
3. Save configuration

### Propagation (5-15 minutes):
- CloudFront edge locations update
- New routing takes effect globally

### Validation (2 minutes):
- Run test script to confirm fix
- Check sample pages for data loading

## Alternative Solutions (If Lambda URL)

If using Lambda Function URLs instead of API Gateway:

```yaml
Origin Configuration:
  Domain: [function-url].lambda-url.[region].on.aws
  Protocol: HTTPS
  Path: /api  # If your Lambda handles /api prefix
```

## Terraform/CDK Configuration

### Terraform Example:
```hcl
resource "aws_cloudfront_behavior" "api_behavior" {
  distribution_id = aws_cloudfront_distribution.main.id
  path_pattern    = "/api/*"
  
  target_origin_id       = "lambda-origin"
  viewer_protocol_policy = "redirect-to-https"
  allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
  cached_methods         = ["GET", "HEAD"]
  
  cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" # Managed-CachingDisabled
  origin_request_policy_id = "88a5eaf4-2fd4-4709-b370-b4c650ea3fcf" # Managed-AllViewerExceptHostHeader
  
  precedence = 0  # Higher priority than default
}
```

### CDK Example:
```typescript
const apiBehavior = {
  pathPattern: "/api/*",
  origin: lambdaOrigin,
  cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
  originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
  allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
  viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
};

new cloudfront.Distribution(this, 'Distribution', {
  defaultBehavior: staticBehavior,
  additionalBehaviors: {
    '/api/*': apiBehavior  // This automatically gets higher precedence
  }
});
```

## Post-Fix Validation

After implementing the fix:

1. **Test API endpoints**:
   ```bash
   node test-api-routing.js
   ```

2. **Check frontend pages**:
   - Dashboard should show live data
   - Portfolio should load holdings  
   - All widgets should display content

3. **Monitor CloudWatch logs**:
   - Lambda function should receive API requests
   - No 404s in CloudFront logs for /api/* paths

## Rollback Plan

If the fix breaks something:

1. **Immediate rollback**: Delete the `/api/*` behavior
2. **Temporary fix**: Update frontend to call Lambda directly
3. **Debug**: Check origins and behavior configuration

## Success Metrics

✅ **Fixed when**:
- `curl https://d1zb7knau41vl9.cloudfront.net/api/health` returns JSON
- Frontend pages display live data instead of empty states
- No HTML responses from API endpoints
- Test script shows 100% working endpoints

## Estimated Timeline: 30 minutes total
- Configuration: 10 minutes
- Propagation: 15 minutes  
- Validation: 5 minutes