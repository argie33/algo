# Unified API Key Service - Complete Design

## Overview
Complete redesign of the API key management system to support thousands of users with a single, reliable endpoint that replaces the failing multiple-endpoint architecture.

## 🎯 Design Goals
- **Simplicity**: Single endpoint for all API key operations
- **Reliability**: Eliminate the "fails and fails" troubleshooting hell
- **Scale**: Support thousands of concurrent users efficiently 
- **Security**: Secure variable passing via AWS Parameter Store + KMS
- **IaC**: Fully configured and deployed via CloudFormation

## 🏗️ Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React)                         │
├─────────────────────────────────────────────────────────────┤
│ ApiKeyManager.jsx → unifiedApiKeyService.js                │
│ - Single UI component for all API key operations           │
│ - Client-side validation and caching                       │
│ - Graceful error handling and retry logic                  │
└─────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                 API Gateway + Lambda                        │
├─────────────────────────────────────────────────────────────┤
│ /api/api-keys → unified-api-keys.js                        │
│ - Single route handler for all operations                  │
│ - Authentication & authorization                           │
│ - Input validation & rate limiting                         │
│ - Performance monitoring                                   │
└─────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│              Unified API Key Service                        │
├─────────────────────────────────────────────────────────────┤
│ unifiedApiKeyService.js                                     │
│ - LRU cache (10K users, 5min TTL)                         │
│ - Batch operations for efficiency                          │
│ - Circuit breaker for AWS failures                         │
│ - Performance optimization                                  │
└─────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                 AWS Parameter Store                         │
├─────────────────────────────────────────────────────────────┤
│ /financial-platform/users/{userId}/alpaca/api-key         │
│ /financial-platform/users/{userId}/alpaca/secret-key      │
│ - KMS encryption for all secrets                           │
│ - Organized hierarchical structure                         │
│ - Tags for metadata and monitoring                         │
└─────────────────────────────────────────────────────────────┘
```

## 📡 API Endpoints

### Single Unified Route: `/api/api-keys`

| Method | Endpoint | Purpose | Response |
|--------|----------|---------|----------|
| `GET` | `/api/api-keys` | Get user's API keys | `{ success: true, data: [key], count: 1 }` |
| `POST` | `/api/api-keys` | Add/Update API key | `{ success: true, message: "Key saved" }` |
| `DELETE` | `/api/api-keys` | Remove API key | `{ success: true, message: "Key removed" }` |
| `GET` | `/api/api-keys/status` | Check if user has key | `{ success: true, hasApiKey: true }` |
| `GET` | `/api/api-keys/health` | Service health check | `{ healthy: true, cache: {...} }` |

### Internal Service Endpoint
| Method | Endpoint | Purpose | Usage |
|--------|----------|---------|-------|
| `GET` | `/api/api-keys/internal/:userId` | Get keys for internal services | Portfolio, Trading, Live Data |

## 🔐 Security & Scale Features

### Secure Variable Passing
- **KMS Encryption**: All API keys encrypted with customer-managed KMS key
- **IAM Roles**: Lambda execution role with least-privilege SSM permissions
- **Parameter Hierarchy**: Organized `/financial-platform/users/{userId}/...`
- **Access Control**: Users can only access their own keys
- **Audit Trail**: CloudTrail logging for all Parameter Store operations

### High-Scale Optimizations
- **LRU Cache**: 10,000 user capacity with intelligent eviction
- **Batch Operations**: Process multiple requests efficiently
- **Connection Pooling**: Optimized AWS SDK connections
- **Circuit Breaker**: Automatic failover during AWS outages
- **Rate Limiting**: 100 requests/user/minute with memory-efficient tracking
- **Performance Monitoring**: Real-time metrics and health checks

## 🚀 Performance Characteristics

### Cache Performance
- **Hit Rate**: Target >85% for active users
- **Memory Usage**: <500MB for 10K cached users  
- **Cache TTL**: 5 minutes with auto-cleanup
- **Eviction**: LRU-based when approaching capacity

### Request Performance
- **API Response**: <200ms for cached keys
- **Parameter Store**: <500ms for cache misses
- **Batch Requests**: 10 users per batch, 100ms window
- **Circuit Breaker**: 10 errors/minute threshold

### Scale Metrics
- **Concurrent Users**: Tested for 1000+ users
- **Requests/Second**: >100 RPS sustained
- **Memory Efficiency**: <50MB baseline + 50KB per cached user
- **Error Recovery**: <5 second recovery from AWS failures

## 📋 Implementation Files

### Backend Services
| File | Purpose | Key Features |
|------|---------|--------------|
| `utils/unifiedApiKeyService.js` | Core service logic | LRU cache, batch ops, health checks |
| `routes/unified-api-keys.js` | API endpoint handler | Auth, validation, error handling |
| `utils/apiKeyPerformanceOptimizer.js` | Scale optimizations | Batching, circuit breaker, metrics |
| `utils/apiKeyMigrationService.js` | Migration from old system | Discovery, validation, rollback |

### Frontend Components  
| File | Purpose | Key Features |
|------|---------|--------------|
| `components/ApiKeyManager.jsx` | Complete UI component | Forms, validation, error handling |
| `services/unifiedApiKeyService.js` | Frontend service | Caching, retry logic, validation |

### Infrastructure
| File | Purpose | Configuration |
|------|---------|---------------|
| `template-webapp-lambda.yml` | CloudFormation | SSM permissions, KMS, Lambda config |

## 🔄 Migration Strategy

### Phase 1: Deploy New System
1. Deploy unified service alongside existing system
2. Configure CloudFormation with enhanced SSM permissions  
3. Test with pilot users to validate functionality

### Phase 2: Migrate Users
1. Discover existing API keys from database/Parameter Store
2. Batch migrate users (10 at a time) to avoid AWS limits
3. Validate each migration with health checks
4. Maintain rollback capability throughout process

### Phase 3: Switch Over
1. Update frontend to use new ApiKeyManager component
2. Route portfolio/trading services to new unified endpoint
3. Monitor performance and error rates during transition
4. Remove old endpoint handlers after validation

### Phase 4: Cleanup
1. Remove old API key tables and routes
2. Clean up unused Parameter Store entries
3. Update documentation and monitoring alerts

## 🎛️ Usage Across Site

### Portfolio Page
```javascript
// Before: Multiple failing endpoints
const apiKey = await portfolioApiService.getApiKey(); // 503 errors

// After: Unified reliable service  
const keyData = await unifiedApiKeyService.getAlpacaKey(userId);
```

### Live Data Service
```javascript
// Before: Settings API key endpoint
const response = await fetch('/api/settings/api-keys'); // Empty arrays

// After: Internal service endpoint
const response = await fetch(`/api/api-keys/internal/${userId}`);
```

### Trading Operations
```javascript
// Before: Database queries with SSL issues
const keys = await db.query('SELECT * FROM api_keys...'); // SSL errors

// After: Cached service call
const keyData = await unifiedApiKeyService.getAlpacaKey(userId);
```

## 📊 Monitoring & Health

### Service Health Endpoints
- `/api/api-keys/health` - Service health with cache metrics
- Cache hit rates, error rates, performance metrics
- Circuit breaker status and AWS connectivity

### Performance Metrics
- Request count and response times
- Cache utilization and hit rates  
- Batch efficiency and error tracking
- Memory usage and optimization alerts

### Error Handling
- Graceful degradation during AWS outages
- Automatic retry with exponential backoff
- User-friendly error messages with troubleshooting hints
- Comprehensive logging for operational monitoring

## 🔧 Deployment Commands

### Deploy Infrastructure
```bash
# Deploy CloudFormation changes
sam build && sam deploy

# Validate SSM permissions
aws iam simulate-principal-policy \
  --policy-source-arn $(aws sts get-caller-identity --query Arn --output text) \
  --action-names ssm:GetParameter ssm:PutParameter \
  --resource-arns "arn:aws:ssm:*:*:parameter/financial-platform/users/*"
```

### Run Migration
```bash
# Test migration (dry run)
node -e "require('./utils/apiKeyMigrationService').runMigration({ dryRun: true })"

# Execute migration
node -e "require('./utils/apiKeyMigrationService').runMigration({ batchSize: 10 })"

# Monitor health
curl https://your-api-gateway/api/api-keys/health
```

## ✅ Success Criteria

### Reliability Improvements
- [ ] Zero 503 Service Unavailable errors
- [ ] <1% error rate under normal operations  
- [ ] <5 second recovery from AWS service issues
- [ ] Graceful degradation with user-friendly error messages

### Performance Targets
- [ ] <200ms response for cached API key requests
- [ ] >85% cache hit rate for active users
- [ ] Support for 1000+ concurrent users
- [ ] <500MB memory usage at full scale

### User Experience
- [ ] Single location in account settings for API key management
- [ ] Clear error messages with actionable troubleshooting steps
- [ ] Consistent behavior across portfolio, live data, and trading features
- [ ] Zero configuration required for new Alpaca API key additions

This unified design eliminates the troubleshooting hell by providing a single, reliable, well-tested service that scales efficiently to thousands of users while maintaining security best practices.