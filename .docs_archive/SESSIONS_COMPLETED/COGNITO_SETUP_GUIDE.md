# 🔐 AWS Cognito Setup Guide

**Current Status**: Using development auth (works fine locally)  
**Next Step**: Switch to real AWS Cognito for production

---

## Prerequisites

- AWS account access
- `aws` CLI configured
- User with IAM permissions to create Cognito resources

---

## Step 1: Create Cognito User Pool (AWS Console or CLI)

### Option A: AWS Console (5 minutes)

1. Go to https://console.aws.amazon.com/cognito
2. Click **"Create user pool"**
3. Choose sign-in options: **Email** (recommended)
4. Configure password policy as needed
5. **Pool name**: `stocks-trading-pool-dev`
6. Click **Create user pool**
7. Note the **User pool ID** (e.g., `us-east-1_ABC123DEF`)

### Option B: AWS CLI

```bash
POOL_ID=$(aws cognito-idp create-user-pool \
  --pool-name stocks-trading-pool-dev \
  --policies PasswordPolicy='MinimumLength=12,RequireUppercase=true,RequireLowercase=true,RequireNumbers=true,RequireSymbols=false' \
  --region us-east-1 \
  --query 'UserPool.Id' \
  --output text)

echo "Created user pool: $POOL_ID"
```

---

## Step 2: Create App Client

### In AWS Console:

1. Go to **User pool** → **stocks-trading-pool-dev**
2. Select **App integration** → **App clients and analytics**
3. Click **Create app client**
4. **App client name**: `stocks-web-app-dev`
5. **Allowed OAuth flows**: `ALLOW_USER_PASSWORD_AUTH`, `ALLOW_REFRESH_TOKEN_AUTH`, `ALLOW_CUSTOM_AUTH`
6. **Allowed OAuth scopes**: `openid`, `profile`, `email`
7. **Callback URLs**: `http://localhost:5173/` (for local dev)
8. Click **Create app client**
9. Note the **Client ID** (e.g., `7a8b9c0d1e2f3g4h5i6j`)

### Via CLI:

```bash
APP_CLIENT=$(aws cognito-idp create-user-pool-client \
  --user-pool-id $POOL_ID \
  --client-name stocks-web-app-dev \
  --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH \
  --supported-login-providers {} \
  --region us-east-1 \
  --query 'UserPoolClient.ClientId' \
  --output text)

echo "Created app client: $APP_CLIENT"
```

---

## Step 3: Get Cognito Domain

### In AWS Console:

1. Go to **User pool** → **App integration** → **Domain**
2. Click **Create Cognito domain**
3. **Domain prefix**: `stocks-trading-dev-unique-name`
   (must be globally unique across all AWS accounts)
4. Click **Create Cognito domain**
5. Domain URL will be: `https://stocks-trading-dev-unique-name.auth.us-east-1.amazoncognito.com`

### Via CLI:

```bash
DOMAIN="stocks-trading-dev-$(date +%s)"

aws cognito-idp create-user-pool-domain \
  --domain $DOMAIN \
  --user-pool-id $POOL_ID \
  --region us-east-1

echo "Domain created: $DOMAIN.auth.us-east-1.amazoncognito.com"
```

---

## Step 4: Update .env.local

Add to `.env.local`:

```bash
# ================================================================
# COGNITO CONFIGURATION
# ================================================================
VITE_COGNITO_USER_POOL_ID=us-east-1_ABC123DEF
VITE_COGNITO_CLIENT_ID=7a8b9c0d1e2f3g4h5i6j
VITE_COGNITO_DOMAIN=https://stocks-trading-dev-unique-name.auth.us-east-1.amazoncognito.com
VITE_AWS_REGION=us-east-1
```

Replace with your actual values from Step 1-3.

---

## Step 5: Create Test User

### In AWS Console:

1. Go to **User pool** → **Users**
2. Click **Create user**
3. **Username**: `testuser@example.com`
4. **Password**: `TempPassword123!`
5. Check **Mark email as verified**
6. Click **Create user**

### Via CLI:

```bash
aws cognito-idp admin-create-user \
  --user-pool-id $POOL_ID \
  --username testuser@example.com \
  --temporary-password TempPassword123! \
  --message-action SUPPRESS \
  --region us-east-1

# Set permanent password
aws cognito-idp admin-set-user-password \
  --user-pool-id $POOL_ID \
  --username testuser@example.com \
  --password TestPassword123! \
  --permanent \
  --region us-east-1
```

---

## Step 6: Test Login

1. **Restart frontend**: `cd webapp/frontend && npm run dev`
2. **Go to**: `http://localhost:5173`
3. **Click Sign In**
4. **Email**: `testuser@example.com`
5. **Password**: `TestPassword123!`

---

## Environment Variables Summary

| Variable | Example | Where to Get |
|----------|---------|--------------|
| `VITE_COGNITO_USER_POOL_ID` | `us-east-1_ABC123DEF` | Cognito > User Pool details |
| `VITE_COGNITO_CLIENT_ID` | `7a8b9c0d1e2f3g4h5i6j` | Cognito > App clients > Client ID |
| `VITE_COGNITO_DOMAIN` | `https://stocks-trading-dev...` | Cognito > Domain |
| `VITE_AWS_REGION` | `us-east-1` | (default: us-east-1) |

---

## Production Checklist

- [ ] Update callback URLs to production domain
- [ ] Enable MFA
- [ ] Configure password policy
- [ ] Set up email verification
- [ ] Create IAM role for production Lambda
- [ ] Update Terraform for production Cognito

---

## Troubleshooting

**"Invalid client id"**
- Check `VITE_COGNITO_CLIENT_ID` matches app client

**"Callback URL mismatch"**
- Add your domain to Cognito app client callback URLs

**"User pool not found"**
- Check `VITE_COGNITO_USER_POOL_ID` format: `region_poolname`

**Still using dev auth?**
- Restart frontend after adding environment variables
- Check browser console: should show "PRODUCTION MODE - Using AWS Cognito"

---

## Useful AWS CLI Commands

```bash
# List user pools
aws cognito-idp list-user-pools --max-results 10 --region us-east-1

# Get pool details
aws cognito-idp describe-user-pool --user-pool-id $POOL_ID --region us-east-1

# List app clients
aws cognito-idp list-user-pool-clients --user-pool-id $POOL_ID --region us-east-1

# List users
aws cognito-idp list-users --user-pool-id $POOL_ID --region us-east-1

# Delete user pool (if needed for cleanup)
aws cognito-idp delete-user-pool --user-pool-id $POOL_ID --region us-east-1
```

---

## Estimated Time

- Creating user pool: **5 min**
- Creating app client: **3 min**
- Creating domain: **5 min** (plus wait time)
- Adding environment variables: **2 min**
- Testing: **5 min**

**Total: ~20 minutes** (plus domain creation wait)
