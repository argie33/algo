# AWS Cognito Configuration Guide

Your authentication service has been fixed and is now ready for configuration. Here's what was completed:

## ✅ Fixed Issues:
1. **Auth routes registered** in `lambda/server.js:12,49`
2. **CORS updated** to allow AWS domains in `lambda/server.js:31-40`

## 🔧 Next Steps - Get Your Cognito Values:

### Option 1: AWS Console (Recommended)
1. Go to [AWS Cognito Console](https://console.aws.amazon.com/cognito/home?region=us-east-1)
2. Find your User Pool for `stocks-serverless-webapp`
3. Copy these values:
   - **User Pool ID**: `us-east-1_XXXXXXXXX`
   - **Client ID**: `XXXXXXXXXXXXXXXXXXXXXXXXXX`
   - **Domain**: `your-domain.auth.us-east-1.amazoncognito.com`

### Option 2: AWS CLI (if available)
Run the provided script once AWS CLI is configured:
```bash
./get-cognito-config.sh
```

### Option 3: CloudFormation Outputs
Check your CloudFormation stack `stocks-serverless-webapp` outputs in AWS Console.

## 📝 Environment Variables to Update:

### Backend (`lambda/.env`):
```bash
COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
COGNITO_CLIENT_ID=XXXXXXXXXXXXXXXXXXXXXXXXXX
AWS_REGION=us-east-1
```

### Frontend (`frontend/.env.development`):
```bash
VITE_COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
VITE_COGNITO_CLIENT_ID=XXXXXXXXXXXXXXXXXXXXXXXXXX
VITE_AWS_REGION=us-east-1
VITE_COGNITO_DOMAIN=your-domain.auth.us-east-1.amazoncognito.com
```

## 🚀 Test Authentication:
Once configured, your auth endpoints will be available at:
- `/api/auth/login`
- `/api/auth/register` 
- `/api/auth/logout`
- `/api/auth/user`

The system will automatically switch from development mode to production authentication once these values are set.