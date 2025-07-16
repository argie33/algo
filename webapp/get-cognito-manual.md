# Manual Cognito Configuration Guide

Your hardcoded URLs have been fixed! Now you need to get your Cognito configuration.

## ✅ Completed Fixes:
- All environment files now use dynamic configuration
- Server CORS now uses environment variables  
- Setup scripts no longer have hardcoded defaults
- Runtime config is dynamic

## 🔧 Get Your Cognito Configuration:

### Method 1: AWS Console (Recommended)
1. Go to [AWS Cognito Console](https://console.aws.amazon.com/cognito/v2/identity/user-pools?region=us-east-1)
2. Look for a User Pool related to `stocks-serverless-webapp`
3. Click on your User Pool
4. Copy these values:
   - **User Pool ID**: Found in "User pool overview" (format: `us-east-1_XXXXXXXXX`)
   - **Client ID**: Go to "App integration" tab, scroll to "App clients" (format: long alphanumeric string)
   - **Domain**: Go to "App integration" tab, look for "Domain" section

### Method 2: CloudFormation Console
1. Go to [CloudFormation Console](https://console.aws.amazon.com/cloudformation/home?region=us-east-1)
2. Find stack named `stocks-serverless-webapp`
3. Click on "Outputs" tab
4. Look for:
   - `UserPoolId`
   - `UserPoolClientId` 
   - `UserPoolDomain`

### Method 3: Install AWS CLI
```bash
# Install AWS CLI
sudo apt update && sudo apt install -y awscli unzip

# Configure credentials
aws configure

# Run the provided script
./get-cognito-config.sh
```

## 📝 Update Configuration:

Once you have your values, update these files:

### Backend (`lambda/.env`):
```bash
COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
COGNITO_CLIENT_ID=XXXXXXXXXXXXXXXXXXXXXXXXXX
```

### Frontend Development (`frontend/.env.development`):  
```bash
VITE_COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
VITE_COGNITO_CLIENT_ID=XXXXXXXXXXXXXXXXXXXXXXXXXX
VITE_COGNITO_DOMAIN=your-domain.auth.us-east-1.amazoncognito.com
```

### Frontend Production (`frontend/.env.production`):
```bash
VITE_COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
VITE_COGNITO_CLIENT_ID=XXXXXXXXXXXXXXXXXXXXXXXXXX  
VITE_COGNITO_DOMAIN=your-domain.auth.us-east-1.amazoncognito.com
VITE_COGNITO_REDIRECT_SIGN_IN=https://YOUR_CLOUDFRONT_DOMAIN
VITE_COGNITO_REDIRECT_SIGN_OUT=https://YOUR_CLOUDFRONT_DOMAIN
```

## 🚀 Test Authentication:
After updating, your auth endpoints will be available:
- `/api/auth/login`
- `/api/auth/register`
- `/api/auth/logout`
- `/api/auth/user`

Your API will automatically detect when Cognito is configured and switch from development mode to production authentication.