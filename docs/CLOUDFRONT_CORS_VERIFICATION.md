# CloudFront CORS Verification Guide

Verify that the CloudFront distribution domain is properly configured in the API Lambda's CORS whitelist (ALLOWED_ORIGINS environment variable).

## Background

The API Lambda is in a VPC and requires proper CORS configuration to accept requests from the CloudFront-hosted frontend. The deploy-code.yml workflow:

1. Dynamically discovers the CloudFront domain from Terraform outputs
2. Adds it to the ALLOWED_ORIGINS environment variable
3. Includes a fallback domain for development/testing

## Verification Steps

### Step 1: Identify Your CloudFront Domain

```bash
# Get CloudFront distribution ID
CF_ID=$(aws cloudfront list-distributions \
  --query 'DistributionList.Items[0].Id' \
  --output text)

# Get CloudFront domain name
CF_DOMAIN=$(aws cloudfront get-distribution \
  --id "$CF_ID" \
  --query 'Distribution.DomainName' \
  --output text)

echo "CloudFront Domain: $CF_DOMAIN"
# Example output: d2u93283nn45h2.cloudfront.net
```

### Step 2: Check Lambda ALLOWED_ORIGINS

```bash
# Get API Lambda function name
API_LAMBDA=$(aws lambda list-functions \
  --query 'Functions[?contains(FunctionName, `api`)].FunctionName | [0]' \
  --output text)

# Get ALLOWED_ORIGINS environment variable
ALLOWED_ORIGINS=$(aws lambda get-function-configuration \
  --function-name "$API_LAMBDA" \
  --query 'Environment.Variables.ALLOWED_ORIGINS' \
  --output text)

echo "ALLOWED_ORIGINS: $ALLOWED_ORIGINS"
```

**Expected output format:**
```
ALLOWED_ORIGINS: http://localhost:3000,http://localhost:5173,https://d2u93283nn45h2.cloudfront.net
```

### Step 3: Verify CloudFront Domain is Included

The ALLOWED_ORIGINS should contain:
- ✓ `http://localhost:3000` (for local development with Vite)
- ✓ `http://localhost:5173` (for local development)
- ✓ `https://<YOUR_CLOUDFRONT_DOMAIN>` (for production)
- ✓ `https://d2u93283nn45h2.cloudfront.net` (fallback for development/testing)

If your CloudFront domain is missing, re-run the deployment:

```bash
git push main  # Triggers deploy-code.yml
```

### Step 4: Test CORS from CloudFront

```bash
# Option 1: Test from command line
API_ENDPOINT=$(aws apigatewayv2 get-apis \
  --query 'Items[0].ApiEndpoint' \
  --output text)

curl -i \
  -H "Origin: https://$CF_DOMAIN" \
  -H "Access-Control-Request-Method: GET" \
  "$API_ENDPOINT/api/health"

# Expected response headers:
# Access-Control-Allow-Origin: https://$CF_DOMAIN
# Access-Control-Allow-Methods: GET, POST, PUT, DELETE, PATCH, OPTIONS
```

**Expected response:**
```
HTTP/2 200
access-control-allow-origin: https://d2u93283nn45h2.cloudfront.net
access-control-allow-methods: GET, POST, PUT, DELETE, PATCH, OPTIONS
access-control-allow-headers: Content-Type, Authorization, X-Requested-With
```

### Step 5: Test from Browser

Open your CloudFront URL and check the browser console:

```javascript
// In browser console on CloudFront domain
fetch('https://<API_ENDPOINT>/api/health')
  .then(r => r.json())
  .then(data => console.log('Success:', data))
  .catch(e => console.error('CORS Error:', e))
```

**Expected output:** `Success: { status: 'ok', ... }`

**If you see CORS error:**
```
Access to XMLHttpRequest at 'https://...' from origin 'https://d2u93283nn45h2.cloudfront.net'
has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present
on the requested resource.
```

Then the ALLOWED_ORIGINS environment variable is missing the CloudFront domain.

## Troubleshooting

### CORS Error After Deployment

1. **Check that Lambda was updated:**
   ```bash
   aws lambda get-function-configuration \
     --function-name algo-api-dev \
     --query 'LastModified' --output text
   ```
   
   Should be recent (within last 5 minutes of your deployment).

2. **Check CloudWatch logs:**
   ```bash
   aws logs tail /aws/lambda/algo-api-dev --follow --region us-east-1 --since 30m
   ```
   
   Look for error messages or CORS-related logs.

3. **Force Lambda container refresh:**
   ```bash
   aws lambda update-function-configuration \
     --function-name algo-api-dev \
     --environment Variables={KEY=VALUE} \
     --region us-east-1
   ```

4. **Wait for cold-start:**
   First request after deployment may take 15-40 seconds (VPC initialization). Subsequent requests are much faster.

### ALLOWED_ORIGINS Doesn't Include CloudFront Domain

1. **Verify deploy-code.yml added it:**
   ```bash
   # Check recent workflow runs
   gh workflow list --repo argie33/algo
   ```

2. **Re-run deployment manually:**
   ```bash
   git push main
   # or trigger manually in GitHub Actions
   ```

3. **Manually update if urgent:**
   ```bash
   aws lambda update-function-configuration \
     --function-name algo-api-dev \
     --environment Variables='{
       "DB_HOST":"...",
       "ALLOWED_ORIGINS":"http://localhost:3000,http://localhost:5173,https://YOUR_CLOUDFRONT_DOMAIN",
       ...other vars...
     }' \
     --region us-east-1
   ```

### CloudFront Domain Changed

If you recreated the CloudFront distribution:

1. Get new domain:
   ```bash
   aws cloudfront get-distribution \
     --id <CF_ID> \
     --query 'Distribution.DomainName' \
     --output text
   ```

2. Update Lambda's ALLOWED_ORIGINS to include new domain

3. Redeploy or update Lambda config

## CORS Headers Reference

The API Lambda should return these headers for CORS:

| Header | Value | Purpose |
|--------|-------|---------|
| `Access-Control-Allow-Origin` | `https://d2u93283nn45h2.cloudfront.net` | Allows requests from this origin |
| `Access-Control-Allow-Methods` | `GET, POST, PUT, DELETE, PATCH, OPTIONS` | Allowed HTTP methods |
| `Access-Control-Allow-Headers` | `Content-Type, Authorization, X-Requested-With` | Allowed request headers |
| `Access-Control-Max-Age` | `86400` | Browser caches CORS config for 24 hours |

## Additional Resources

- [AWS CloudFront Documentation](https://docs.aws.amazon.com/cloudfront/)
- [CORS MDN Documentation](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)
- [API Gateway CORS Configuration](https://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-cors.html)

## Production Checklist

Before going live:

- [ ] CloudFront domain is in ALLOWED_ORIGINS
- [ ] CORS preflight requests return 200 OK
- [ ] Browser console shows no CORS errors
- [ ] API requests succeed from CloudFront domain
- [ ] Lambda configuration shows recent update time
- [ ] CloudWatch logs show successful requests
