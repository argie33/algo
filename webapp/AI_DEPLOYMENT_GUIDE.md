# AI Assistant Enhanced Deployment Guide

## Overview

The AI Assistant Enhanced Infrastructure has been fully integrated into the existing IaC GitHub workflow. This guide explains how the deployment works and what happens when you push changes.

## Deployment Architecture Integration

### 1. Workflow Integration

The AI infrastructure deployment has been seamlessly integrated into the existing `deploy-webapp.yml` workflow as a new step:

```
1. Setup Environment
2. Setup AWS Services  
3. Filter Changes
4. Smoke Tests
5. Unit Tests
6. Deploy Main Infrastructure
6.5. Deploy AI Enhanced Infrastructure ← NEW STEP
7. Deploy Frontend (Updated with AI URLs)
8. Cleanup & Monitoring
```

### 2. Stack Naming Convention

The AI infrastructure follows the existing naming pattern:
- **Main Stack**: `stocks-webapp-dev`
- **AI Stack**: `stocks-webapp-dev-ai-enhanced`

This ensures consistent resource organization and easy identification.

### 3. Parameter Integration

The AI stack automatically integrates with existing infrastructure:

```yaml
Parameters Passed:
  Environment: dev
  ProjectName: stocks-webapp  
  ExistingStackName: stocks-webapp-dev
  DatabaseSecretArn: (from main stack)
  DatabaseEndpoint: (from main stack)
  BedrockModelHaiku: anthropic.claude-3-haiku-20240307-v1:0
  BedrockModelSonnet: anthropic.claude-3-sonnet-20240229-v1:0
```

## What Gets Deployed

### AI Infrastructure Components

1. **Enhanced IAM Roles**
   - Bedrock model access permissions
   - Secrets Manager access
   - WebSocket API management
   - Database connectivity
   - CloudWatch monitoring

2. **WebSocket API Gateway**
   - Real-time streaming endpoint
   - Connection management
   - Route handling for AI messages
   - Throttling and monitoring

3. **Lambda Functions**
   - Streaming Service (Node.js 18.x, 2048MB)
   - Bedrock Service (Node.js 18.x, 1024MB)  
   - Connection Manager (Node.js 18.x, 512MB)
   - HTTP Handler (Node.js 18.x, 1024MB)

4. **Secrets Management**
   - AI Configuration Secret (models, features, limits)
   - Conversation Encryption Secret (AES-256-GCM)

5. **Storage & Analytics**
   - S3 bucket for conversation analytics
   - Lifecycle policies for cost optimization

6. **Monitoring & Logging**
   - CloudWatch Log Groups with retention policies
   - Performance and error alarms
   - Cost monitoring for Bedrock usage
   - Enhanced dashboard with AI metrics

## Deployment Process

### Automatic Deployment

When you push code changes to the repository:

1. **Main Infrastructure Deploys First**
   - Ensures database and core services are ready
   - Validates existing stack health

2. **AI Infrastructure Deploys**  
   - Gets database credentials from main stack
   - Deploys AI-specific resources
   - Validates secret creation and access

3. **Frontend Builds with AI Configuration**
   - Receives WebSocket URL from AI stack
   - Configures environment variables:
     ```
     VITE_AI_WEBSOCKET_URL=wss://xxx.execute-api.us-east-1.amazonaws.com/dev
     VITE_AI_HTTP_URL=https://xxx.lambda-url.us-east-1.on.aws/
     ```

### Manual Deployment

To deploy just the AI infrastructure:

```bash
# Deploy AI infrastructure only
aws cloudformation deploy \
  --template-file webapp/infrastructure/cloudformation/ai-assistant-enhanced-infrastructure.yml \
  --stack-name stocks-webapp-dev-ai-enhanced \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    Environment=dev \
    ProjectName=stocks-webapp \
    ExistingStackName=stocks-webapp-dev \
    DatabaseSecretArn=arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:stocks-db-credentials-dev \
    DatabaseEndpoint=stocks-db-dev.cluster-cjmjnpvmvfqg.us-east-1.rds.amazonaws.com
```

## Configuration & Environment Variables

### AI Configuration Secret

The AI stack creates a comprehensive configuration secret:

```json
{
  "models": {
    "claude-3-haiku": {
      "modelId": "anthropic.claude-3-haiku-20240307-v1:0",
      "maxTokens": 2000,
      "temperature": 0.1,
      "costPerInputToken": 0.00000025,
      "costPerOutputToken": 0.00000125,
      "streamingSupported": true,
      "useCase": "fast_responses"
    },
    "claude-3-sonnet": {
      "modelId": "anthropic.claude-3-sonnet-20240229-v1:0", 
      "maxTokens": 2000,
      "temperature": 0.1,
      "costPerInputToken": 0.000003,
      "costPerOutputToken": 0.000015,
      "streamingSupported": true,
      "useCase": "complex_analysis"
    }
  },
  "defaultModel": "claude-3-haiku",
  "features": {
    "streamingEnabled": true,
    "enhancedContext": true,
    "portfolioIntegration": true,
    "marketDataIntegration": true,
    "conversationAnalytics": true
  },
  "limits": {
    "conversationRetentionDays": 90,
    "maxTokensPerRequest": 4000,
    "rateLimitPerMinute": 100,
    "maxConcurrentStreams": 10
  }
}
```

### Frontend Environment Variables

The frontend automatically receives these environment variables:

```bash
VITE_API_URL=https://xxx.execute-api.us-east-1.amazonaws.com/dev
VITE_AI_WEBSOCKET_URL=wss://xxx.execute-api.us-east-1.amazonaws.com/dev  
VITE_AI_HTTP_URL=https://xxx.lambda-url.us-east-1.on.aws/
```

## Monitoring & Troubleshooting

### CloudWatch Dashboard

The deployment creates an enhanced dashboard at:
```
https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=stocks-webapp-dev-AI-Enhanced-Assistant
```

### Key Metrics to Monitor

1. **Lambda Performance**
   - Invocations, Errors, Duration
   - Memory utilization
   - Concurrent executions

2. **WebSocket API**
   - Connection count
   - Integration latency  
   - Error rates

3. **Bedrock Usage**
   - Token consumption
   - Cost estimation
   - Model performance

4. **Security & Access**
   - Secret access patterns
   - IAM role usage
   - Failed authentication attempts

### Common Issues & Solutions

#### 1. AI Infrastructure Deployment Fails
```bash
# Check stack status
aws cloudformation describe-stacks --stack-name stocks-webapp-dev-ai-enhanced

# View events for error details
aws cloudformation describe-stack-events --stack-name stocks-webapp-dev-ai-enhanced
```

#### 2. Frontend Can't Connect to AI
- Verify WebSocket URL in browser dev tools
- Check CORS configuration in API Gateway
- Validate environment variables in deployed frontend

#### 3. Bedrock Access Denied
- Verify Bedrock model access in IAM role
- Check if Bedrock is enabled in AWS region
- Validate model IDs are correct

## Cost Optimization

### Bedrock Costs
- **Haiku**: ~$0.25 per 1M input tokens, $1.25 per 1M output tokens
- **Sonnet**: ~$3.00 per 1M input tokens, $15.00 per 1M output tokens
- Cost alarm set at $100/day for dev, $1000/day for prod

### Lambda Costs
- Streaming Service: 2048MB, avg 10s execution
- Other functions: 512-1024MB, avg 2-5s execution
- Reserved concurrency limits prevent runaway costs

### Storage Costs
- S3 analytics bucket with lifecycle policies
- Automatic transition to IA (30 days) and Glacier (90 days)
- Automatic deletion after retention period

## Next Steps

1. **Code Integration**: Update frontend AI components to use the new WebSocket URL
2. **Testing**: Run end-to-end tests with real Bedrock integration
3. **Monitoring**: Set up alerts for high token usage or errors
4. **Optimization**: Fine-tune model selection based on usage patterns

## Support

For issues with the AI infrastructure deployment:
1. Check CloudWatch logs for specific Lambda function errors
2. Review CloudFormation stack events for deployment issues
3. Validate IAM permissions for Bedrock access
4. Monitor cost and usage through the enhanced dashboard