# Financial Dashboard API Documentation

## Authentication Overview

### Development Environment
- **Auto-bypass**: Enabled when `NODE_ENV=development`, `ALLOW_DEV_BYPASS=true`, or no `AWS_REGION`
- **Mock user**: `{ id: 'dev-user', username: 'dev-user', sub: 'dev-user-123' }`

### Production Environment  
- **Cognito JWT**: Required for all protected endpoints
- **Format**: `Authorization: Bearer <jwt-token>`

## API Endpoints

### Public Endpoints (No Authentication)
```
GET /api/health                 - System health check
GET /api/health/quick           - Quick health status  
GET /api/stocks/popular         - Popular stocks (with fallbacks)
GET /api/stocks/sectors         - Market sectors
```

### Protected Endpoints (Authentication Required)
```
GET /api/dashboard              - Main dashboard data aggregation
GET /api/dashboard/overview     - Dashboard overview  
GET /api/dashboard/widgets      - Available widgets
GET /api/portfolio              - Portfolio overview
GET /api/portfolio/holdings     - Portfolio holdings
GET /api/stocks/signals/buy     - Buy signals
GET /api/stocks/signals/sell    - Sell signals  
GET /api/settings               - User settings
```

## Standard Response Format

### Success Response
```json
{
  "success": true,
  "data": {...},
  "timestamp": "2025-07-25T23:40:01.498Z",
  "responseTime": 150,
  "dataSource": "database|fallback|cache"
}
```

### Error Response  
```json
{
  "success": false,
  "error": "Error message",
  "details": {
    "requestId": "uuid",
    "errorType": "VALIDATION_ERROR|AUTH_ERROR|DB_ERROR",
    "timestamp": "2025-07-25T23:40:01.498Z"
  }
}
```

## Fallback Data Strategy

### Database Unavailable
- **Health endpoints**: Always return operational status
- **Stocks endpoints**: Use hardcoded popular stocks data
- **Portfolio endpoints**: Return sample/demo data
- **Error handling**: Graceful degradation, never return 5xx

### Authentication Bypass (Development)
- **Automatic detection**: Multiple environment indicators
- **Mock user injection**: Consistent across all routes
- **Logging**: Clear bypass notifications in console

## Performance & Reliability

### Timeout Settings
- **Database queries**: 10 seconds max
- **API responses**: 5 seconds target
- **Circuit breaker**: 25 failures threshold, 60s timeout

### Connection Pooling
- **Max connections**: 5 (Lambda optimized)
- **Connection timeout**: 5 seconds
- **Query timeout**: 10 seconds
- **Pool scaling**: 0 minimum (scales to zero)

## Error Handling

### Database Errors
- **Connection timeout**: Return fallback data
- **Query timeout**: Return cached/sample data  
- **Connection refused**: Enable emergency bypass mode

### Authentication Errors
- **Invalid token**: Return 401 with clear message
- **Missing token**: Return 401 with expected format
- **Development mode**: Automatic bypass with logging

## Data Sources

### Primary: Database
- **PostgreSQL**: Live portfolio and market data
- **Connection**: AWS RDS with connection pooling
- **Backup**: Circuit breaker with fallback chains

### Fallback: Static Data
- **Popular stocks**: Hardcoded FAANG+ companies  
- **Portfolio**: Demo data with realistic values
- **Market status**: Assumed market hours

### Emergency: Minimal Data
- **Always working**: Never return empty responses
- **User experience**: Graceful degradation messaging
- **System status**: Operational with limited features

## Development vs Production

### Development Mode Indicators
- `NODE_ENV === 'development'`
- `ALLOW_DEV_BYPASS === 'true'`  
- `!process.env.AWS_REGION` (local development)

### Production Mode Requirements
- **Cognito configuration**: USER_POOL_ID and CLIENT_ID required
- **AWS region**: Must be set for production deployment
- **Database credentials**: Retrieved from AWS Secrets Manager
- **Security**: Full authentication and authorization

## Common Issues & Solutions

### White Screen / No Data
1. **Check authentication**: Verify dev bypass is enabled
2. **Check database**: Look for timeout or connection errors  
3. **Check fallbacks**: Ensure fallback data is loading
4. **Check console**: Look for bypass and error messages

### API Endpoint Not Found
1. **Check route loading**: Verify route is loaded in index.js
2. **Check URL paths**: Ensure frontend matches backend routes
3. **Check middleware**: Verify auth middleware isn't blocking

### Authentication Failures  
1. **Development**: Verify bypass conditions are met
2. **Production**: Check Cognito configuration  
3. **Tokens**: Verify JWT format and expiration
4. **Environment**: Confirm AWS_REGION and settings

## Testing

### Health Check
```bash
curl https://api-url/api/health
```

### Authentication Test (Development)
```bash  
curl https://api-url/api/portfolio/holdings
# Should work without Authorization header in dev mode
```

### Database Status
```bash
curl https://api-url/api/health | grep databaseHealth
# Shows: "healthy", "degraded", or "unavailable"
```

This documentation reflects the current state after applying all fixes for authentication bypass, database optimization, and standardized error handling.