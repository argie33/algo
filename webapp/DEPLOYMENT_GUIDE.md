# Production Deployment Guide

This guide outlines the steps to deploy the enhanced portfolio analytics application to AWS with full Alpaca integration.

## Prerequisites

1. **AWS Account Setup**
   - AWS CLI configured with appropriate permissions
   - CloudFormation permissions for creating stacks
   - RDS permissions for database operations
   - Lambda and API Gateway permissions
   - Cognito User Pool created and configured

2. **Database Setup**
   - Run the database migrations in order:
     ```sql
     -- Execute these in your RDS PostgreSQL instance
     \i database/migrations/001_initial_schema.sql
     \i database/migrations/002_add_api_keys_table.sql
     \i database/migrations/003_add_portfolio_tables.sql
     \i database/migrations/004_enhance_portfolio_tables.sql
     ```

3. **Environment Variables**
   - Set up these environment variables in your AWS Lambda/ECS deployment:

## Required Environment Variables

### Production Lambda Environment Variables
```bash
# Database Configuration
DB_HOST=your-rds-endpoint.amazonaws.com
DB_PORT=5432
DB_NAME=financial_dashboard
DB_USER=your-db-username
DB_PASSWORD=your-db-password

# AWS Cognito Configuration
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
COGNITO_CLIENT_ID=your-cognito-client-id
AWS_REGION=us-east-1

# API Security
API_KEY_ENCRYPTION_SECRET=your-very-secure-32-char-secret!!
JWT_SECRET=your-jwt-secret-key

# Application Configuration
NODE_ENV=production
CORS_ORIGIN=https://yourdomain.com
LAMBDA_RUNTIME=nodejs18.x
```

### Frontend Environment Variables
```bash
# Production Build Variables
VITE_API_URL=https://your-api-gateway-url.execute-api.us-east-1.amazonaws.com/prod
VITE_COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
VITE_COGNITO_CLIENT_ID=your-cognito-client-id
VITE_AWS_REGION=us-east-1
NODE_ENV=production
```

## Deployment Steps

### 1. Database Migration
```bash
# Connect to your RDS instance and run migrations
psql -h your-rds-endpoint.amazonaws.com -U your-username -d financial_dashboard
\i database/migrations/004_enhance_portfolio_tables.sql
```

### 2. Backend Lambda Deployment
```bash
cd webapp/lambda

# Install production dependencies
npm install --production

# Package for Lambda
npm run package

# Deploy to AWS Lambda
aws lambda update-function-code \
  --function-name financial-dashboard-api \
  --zip-file fileb://function.zip

# Update environment variables
aws lambda update-function-configuration \
  --function-name financial-dashboard-api \
  --environment Variables="{
    DB_HOST=your-rds-endpoint.amazonaws.com,
    DB_PORT=5432,
    DB_NAME=financial_dashboard,
    DB_USER=your-db-username,
    DB_PASSWORD=your-db-password,
    COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx,
    COGNITO_CLIENT_ID=your-cognito-client-id,
    AWS_REGION=us-east-1,
    API_KEY_ENCRYPTION_SECRET=your-very-secure-32-char-secret!!,
    NODE_ENV=production
  }"
```

### 3. Frontend Deployment
```bash
cd webapp/frontend

# Set production environment variables
export VITE_API_URL=https://your-api-gateway-url.execute-api.us-east-1.amazonaws.com/prod
export VITE_COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
export VITE_COGNITO_CLIENT_ID=your-cognito-client-id
export VITE_AWS_REGION=us-east-1

# Build for production
npm run build

# Deploy to S3 (adjust bucket name)
aws s3 sync dist/ s3://your-frontend-bucket --delete

# Invalidate CloudFront cache if using CDN
aws cloudfront create-invalidation \
  --distribution-id your-distribution-id \
  --paths "/*"
```

### 4. CloudFormation Stack Updates
```bash
# Deploy the enhanced CloudFormation templates
aws cloudformation deploy \
  --stack-name stocks-app-stack \
  --template-file cloudformation/template-app-stocks.yml \
  --parameter-overrides \
    RDSUsername=your-db-username \
    RDSPassword=your-db-password \
    FREDApiKey=your-fred-api-key \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM
```

## Production Security Checklist

### 1. API Key Security
- ✅ API keys are encrypted using AES-256-GCM
- ✅ User-specific salts for encryption
- ✅ Keys are never logged in plaintext
- ✅ Secure key rotation capability implemented

### 2. Authentication Security
- ✅ Production uses AWS Cognito (not dev auth)
- ✅ JWT tokens properly validated
- ✅ Session management with refresh tokens
- ✅ Proper CORS configuration

### 3. Database Security
- ✅ RDS encryption at rest enabled
- ✅ SSL/TLS connections enforced
- ✅ Database credentials in AWS Secrets Manager
- ✅ Parameterized queries prevent SQL injection

### 4. Network Security
- ✅ HTTPS enforced for all communications
- ✅ API Gateway with proper throttling
- ✅ Lambda functions in private subnets
- ✅ Security groups restrict access

## Alpaca Integration Configuration

### 1. Alpaca API Setup
Users need to:
1. Create an Alpaca account at https://alpaca.markets/
2. Generate API keys (paper trading recommended for testing)
3. Add keys through the Settings page in the application

### 2. Supported Features
- ✅ Portfolio import with real-time data
- ✅ Position tracking with P&L calculations
- ✅ Performance history analysis
- ✅ Risk metrics calculation
- ✅ Sector allocation analysis
- ✅ Account validation and testing

### 3. Rate Limiting
- 200 requests per minute per user
- Automatic retry with exponential backoff
- Error handling for API limits

## Monitoring and Logging

### 1. CloudWatch Configuration
```bash
# Set up CloudWatch alarms for Lambda errors
aws cloudwatch put-metric-alarm \
  --alarm-name "FinancialDashboard-LambdaErrors" \
  --alarm-description "Monitor Lambda function errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=financial-dashboard-api
```

### 2. Application Logs
- Lambda logs automatically sent to CloudWatch
- Frontend errors tracked via error boundaries
- API request/response logging (excluding sensitive data)

## Performance Optimization

### 1. Frontend Optimizations
- Code splitting by route
- Lazy loading of components
- Image optimization
- Bundle size monitoring

### 2. Backend Optimizations
- Database connection pooling
- API response caching where appropriate
- Efficient database queries with indexes
- Rate limiting to prevent abuse

## Troubleshooting

### Common Issues

1. **Authentication Not Working**
   - Verify Cognito configuration matches environment variables
   - Check CORS settings for your domain
   - Ensure JWT secrets match between services

2. **Alpaca Connection Fails**
   - Verify API keys are correct (paper vs live environment)
   - Check if Alpaca account has necessary permissions
   - Test connection using the "Test Connection" button

3. **Database Connection Issues**
   - Verify RDS security groups allow Lambda access
   - Check database credentials in environment variables
   - Ensure database migrations have been run

4. **Import Fails with Large Portfolios**
   - Check Lambda timeout settings (increase if needed)
   - Monitor CloudWatch logs for specific errors
   - Verify database has sufficient storage

### Support

For issues specific to this implementation:
1. Check CloudWatch logs for detailed error messages
2. Use the application's "Test Connection" feature to validate API keys
3. Review database connection logs in RDS CloudWatch

## Production Readiness Checklist

- [ ] Database migrations completed
- [ ] Environment variables configured
- [ ] Cognito User Pool configured
- [ ] SSL certificates installed
- [ ] CloudWatch monitoring enabled
- [ ] Database backups configured
- [ ] API throttling configured
- [ ] Security groups reviewed
- [ ] CORS policies updated
- [ ] Error handling tested
- [ ] Performance benchmarks met
- [ ] User acceptance testing completed

## Scaling Considerations

### Database Scaling
- Monitor database performance metrics
- Consider read replicas for reporting queries
- Plan for connection pooling at scale

### Lambda Scaling
- Configure reserved concurrency if needed
- Monitor cold start times
- Consider provisioned concurrency for critical functions

### Frontend Scaling
- Use CloudFront for global distribution
- Monitor Core Web Vitals
- Implement progressive web app features

This deployment guide ensures your enhanced portfolio analytics application with Alpaca integration is production-ready and secure.