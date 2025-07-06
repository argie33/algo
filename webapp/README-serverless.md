# Financial Dashboard - Serverless Web Application
<!-- Updated 2025-07-06 to trigger webapp workflow -->

This directory contains the serverless web application built with Lambda + API Gateway + CloudFront architecture, providing **85-95% cost savings** compared to the previous ECS + ALB setup.

# Database init trigger - fix portfolio pages

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌────────────────┐
│   CloudFront    │────│   API Gateway    │────│     Lambda     │
│   (Frontend)    │    │   (API Routes)   │    │   (Backend)    │
└─────────────────┘    └──────────────────┘    └────────────────┘
          │                       │                      │
          │                       │                      │
          ▼                       ▼                      ▼
┌─────────────────┐    ┌──────────────────┐    ┌────────────────┐
│       S3        │    │   CloudWatch     │    │   RDS (Shared) │
│  (Static Files) │    │    (Logging)     │    │   (Database)   │
└─────────────────┘    └──────────────────┘    └────────────────┘
```

### Components

- **Frontend**: React SPA built with Vite, served from S3 via CloudFront
- **Backend**: Express.js app running on AWS Lambda with serverless-http
- **API**: API Gateway with CORS and rate limiting
- **Database**: Shared RDS PostgreSQL instance (unchanged)
- **CDN**: CloudFront for global content delivery and caching

## 💰 Cost Comparison

| Component | ECS Setup | Serverless Setup | Savings |
|-----------|-----------|------------------|---------|
| **Compute** | ECS Fargate: ~$25/month | Lambda: ~$0.50/month | 98% |
| **Load Balancer** | ALB: ~$8/month | API Gateway: ~$0.50/month | 94% |
| **Storage** | EFS: ~$2/month | S3: ~$0.10/month | 95% |
| **Total** | **~$35/month** | **~$1-5/month** | **85-95%** |

## 📁 Directory Structure

```
webapp/
├── frontend/           # React frontend application
│   ├── src/           # Source code
│   ├── public/        # Static assets
│   ├── dist/          # Built files (generated)
│   └── package.json   # Frontend dependencies
├── lambda/            # Serverless Lambda function (replaces backend/)
│   ├── index.js       # Main Lambda handler with serverless-http
│   ├── routes/        # API route handlers (Express routes)
│   ├── utils/         # Database connection and utilities
│   ├── middleware/    # Express middleware
│   └── package.json   # Lambda dependencies
├── template-webapp-lambda.yml  # CloudFormation template
└── README-serverless.md        # This file
```

> **Note**: The `backend/` folder has been removed as it's replaced by the `lambda/` folder which contains the same Express.js application wrapped with `serverless-http` for Lambda execution.

## 🚀 Deployment

### Automated CI/CD via GitHub Actions

The serverless application is deployed automatically using GitHub Actions workflow:

1. **OIDC Authentication**: Uses AWS OIDC for secure, keyless authentication
2. **Automatic Triggers**: 
   - Deploys on push to `main` branch
   - Manual deployment via workflow dispatch
3. **Multi-Environment**: Supports dev, staging, and prod environments
4. **Full Pipeline**: 
   - Builds frontend and Lambda function
   - Deploys CloudFormation stack
   - Updates Lambda code and frontend assets

### Manual Deployment

To trigger a manual deployment:
1. Go to GitHub Actions tab in your repository
2. Select "Deploy Financial Dashboard - Serverless" workflow
3. Click "Run workflow" and select environment

## 📋 Prerequisites

### Required Tools
- [AWS CLI v2](https://aws.amazon.com/cli/) - Configure with `aws configure`
- [SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- [Node.js 18+](https://nodejs.org/) and npm
- Git (for cloning repository)

### AWS Resources
- **RDS Database**: Must exist with secret in AWS Secrets Manager
- **AWS Account**: With appropriate permissions for Lambda, API Gateway, S3, CloudFront

### Required AWS Permissions
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "lambda:*",
        "apigateway:*",
        "s3:*",
        "cloudfront:*",
        "iam:*",
        "logs:*",
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "*"
    }
  ]
}
```

## 🔧 Configuration

### Environment Variables

The application supports these environment variables:

#### Lambda Environment
- `NODE_ENV`: Environment (development/production)
- `DB_SECRET_ARN`: ARN of database secret in Secrets Manager
- `AWS_REGION`: AWS region

#### Frontend Environment (.env files)
- `VITE_API_URL`: API Gateway URL (set automatically during deployment)
- `VITE_SERVERLESS`: Set to 'true' for serverless optimizations

### Custom Domains (Optional)

To use a custom domain, update the CloudFormation template parameters:

```yaml
Parameters:
  FrontendDomainName:
    Type: String
    Default: 'dashboard.yourdomain.com'
```

## 🧪 Testing Locally

### Run Frontend Locally
```bash
cd webapp/frontend
npm install
npm run dev
```

### Run Lambda Locally
```bash
cd webapp/lambda
npm install
npm start
```

### Test API Endpoints
```bash
# Health check
curl https://your-api-gateway-url/health

# Get stocks
curl https://your-api-gateway-url/stocks

# Market overview
curl https://your-api-gateway-url/metrics/overview
```

## 📊 Monitoring & Observability

### CloudWatch Logs
- Lambda logs: `/aws/lambda/financial-dashboard-api-{env}`
- API Gateway logs: `/aws/apigateway/financial-dashboard-{env}`

### Metrics to Monitor
- **Lambda**: Duration, errors, cold starts, concurrency
- **API Gateway**: Request count, latency, error rate
- **CloudFront**: Cache hit ratio, origin latency

### Alarms (Recommended)
```bash
# High error rate
aws cloudwatch put-metric-alarm \
  --alarm-name "Lambda-HighErrorRate" \
  --metric-name "Errors" \
  --namespace "AWS/Lambda" \
  --statistic "Sum" \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 10

# High duration
aws cloudwatch put-metric-alarm \
  --alarm-name "Lambda-HighDuration" \
  --metric-name "Duration" \
  --namespace "AWS/Lambda" \
  --statistic "Average" \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 25000
```

## 🔒 Security Features

- **CORS**: Properly configured for CloudFront origin
- **Rate Limiting**: API Gateway throttling + Express rate limiter
- **Security Headers**: Helmet.js for security headers
- **SSL/TLS**: End-to-end encryption via CloudFront + API Gateway
- **IAM**: Least privilege access for Lambda execution role
- **VPC**: Lambda can be configured for VPC access if needed

## 🚨 Troubleshooting

### Common Issues

#### 1. Lambda Cold Starts
- **Symptom**: First request takes 5-10 seconds
- **Solution**: Retry logic implemented in frontend, consider provisioned concurrency for production

#### 2. Database Connection Timeout
- **Symptom**: 503 errors on database queries
- **Solution**: Check VPC configuration, security groups, and connection pooling

#### 3. CORS Errors
- **Symptom**: Frontend can't call API
- **Solution**: Verify API Gateway CORS configuration matches CloudFront domain

#### 4. Build Failures
- **Symptom**: Deployment fails during build
- **Solution**: Check Node.js version, clear npm cache, verify file permissions

### Debug Commands

```bash
# Check Lambda logs
aws logs tail /aws/lambda/financial-dashboard-api-prod --follow

# Test API Gateway directly
curl -X GET https://your-api-id.execute-api.region.amazonaws.com/prod/health

# Validate CloudFormation template
sam validate --template webapp/template-webapp-lambda.yml

# Check stack status
aws cloudformation describe-stacks --stack-name financial-dashboard-prod
```

## 📈 Performance Optimization

### Lambda Optimizations
- Connection pooling with reduced pool size
- Warm-up strategies for critical paths
- Proper error handling and retries
- Memory/timeout tuning based on usage

### Frontend Optimizations
- Code splitting with Vite
- Asset compression and caching
- CDN cache optimization
- Progressive loading strategies

### Database Optimizations
- Connection pooling
- Query optimization
- Read replicas for heavy read workloads
- Connection timeout adjustments

## 🔄 Migration from ECS

If migrating from the ECS setup:

1. **Deploy Serverless**: Follow deployment instructions above
2. **Test Thoroughly**: Ensure all functionality works
3. **Update DNS**: Point domain to CloudFront distribution
4. **Monitor**: Watch metrics and logs for any issues
5. **Cleanup ECS**: Once confident, delete ECS resources to save costs

## 📞 Support

For issues related to:
- **Infrastructure**: Check CloudFormation events and stack status
- **Lambda**: Check CloudWatch logs and function configuration
- **Frontend**: Check browser console and network tab
- **Database**: Verify connectivity and query performance

## 🎯 Next Steps

- [ ] Set up monitoring and alerting
- [ ] Configure custom domain (optional)
- [ ] Add API caching strategies
- [ ] Implement blue/green deployments
- [ ] Set up cost budgets and alerts
- [ ] Consider reserved concurrency for Lambda
