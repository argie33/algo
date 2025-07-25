# Manual CloudFront Fix Instructions

## 🔧 **IMMEDIATE FIX** (Console Method - 10 minutes)

### Step 1: Access CloudFront Console
1. Go to [AWS CloudFront Console](https://console.aws.amazon.com/cloudfront/)
2. Find distribution for `d1zb7knau41vl9.cloudfront.net`
3. Click on the Distribution ID

### Step 2: Check Current Behaviors
1. Click **"Behaviors"** tab
2. Look for `/api/*` pattern
3. Note the current **precedence order**

### Step 3: Create/Edit API Behavior

#### If `/api/*` behavior exists:
1. Select the `/api/*` behavior
2. Click **"Edit"**

#### If no `/api/*` behavior:
1. Click **"Create behavior"**
2. Set **Path pattern**: `/api/*`

### Step 4: Configure API Behavior Settings

```yaml
Path Pattern: /api/*

Origin and Origin Groups:
  - Select your Lambda Function URL or API Gateway origin
  - NOT the S3 bucket origin

Viewer Protocol Policy: Redirect HTTP to HTTPS

Allowed HTTP Methods: 
  ☑ GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE

Cache Policy: 
  - Select "Managed-CachingDisabled"
  - OR create custom with TTL=0

Origin Request Policy:
  - Select "Managed-AllViewerExceptHostHeader"
  - OR "Managed-CORS-S3Origin"

Response Headers Policy:
  - Select "Managed-CORS-with-preflight-and-SecurityHeadersPolicy"

Function Associations: None
```

### Step 5: Set Correct Precedence
**CRITICAL**: Ensure behaviors are in this order:
1. **`/api/*`** (Precedence: 0) → Lambda/API Gateway
2. **Default (`*`)** (Precedence: 1) → S3 Static Website

### Step 6: Save and Deploy
1. Click **"Save changes"**
2. Wait for status to show **"Deployed"** (5-15 minutes)

## 🧪 **TESTING** (After deployment)

### Quick Test:
```bash
# Should return JSON (not HTML)
curl -H "Accept: application/json" https://d1zb7knau41vl9.cloudfront.net/api/health
```

### Comprehensive Test:
```bash
node test-api-routing.js
```

### Expected Results:
- ✅ API endpoints return JSON
- ✅ Frontend pages display live data
- ✅ No more HTML responses from `/api/*` routes

## 🚨 **TROUBLESHOOTING**

### Issue: Still getting HTML responses
**Solution**: Check behavior precedence
- `/api/*` must have **Precedence 0** (highest priority)
- Default behavior should have **Precedence 1**

### Issue: 403/404 errors
**Solution**: Check origin configuration
- Ensure `/api/*` points to Lambda/API Gateway origin
- Verify origin domain is correct

### Issue: CORS errors
**Solution**: Check response headers policy
- Use "Managed-CORS-with-preflight-and-SecurityHeadersPolicy"
- Or ensure custom policy includes CORS headers

## 📊 **VALIDATION CHECKLIST**

After fix is deployed:
- [ ] `curl https://d1zb7knau41vl9.cloudfront.net/api/health` returns JSON
- [ ] Dashboard shows live data instead of empty widgets
- [ ] Portfolio page loads actual holdings
- [ ] All API endpoints in test script pass
- [ ] No HTML responses from any `/api/*` route

## ⏱️ **TIMELINE**
- Configuration: 5 minutes
- Propagation: 5-15 minutes
- Testing: 2 minutes
- **Total: ~20 minutes**

## 🎯 **SUCCESS CRITERIA**
All frontend pages display live data instead of loading states or errors.