# Live Data AWS Integration Fix Strategy

**Date:** July 25, 2025  
**Status:** Implementation Roadmap  
**Priority:** Critical for Production Deployment  

## Executive Summary

🎯 **Objective:** Transform mock implementations into fully functional live data services with user-specific Alpaca API key integration for AWS Lambda deployment.

**Current Status:** 503 Service Unavailable errors resolved (auth middleware fixed), but live data services remain mock implementations requiring real Alpaca API integration.

## Critical Issues Analysis

### ✅ **RESOLVED - 503 Service Issues**
- **Root Cause:** Auth middleware import issue in `hftTrading.js:9`
- **Solution Applied:** Changed from `const auth = require('../middleware/auth')` to `const { authenticateToken } = require('../middleware/auth')`
- **Impact:** All HFT endpoints now properly load and respond

### 🚨 **PRIORITY 1 - User-Specific API Key Integration**

**Current Gap:** Services use hardcoded environment variables instead of user-provided Alpaca API keys.

**Files Requiring Modification:**
- `/utils/liveDataManager.js:888-933` - Provider configurations use env vars
- `/websocket/realBroadcaster.js:77-120` - WebSocket connections need user keys
- `/services/webSocketManager.js:65-80` - Stream management requires user auth
- `/services/hftService.js:496-550` - Order execution needs user credentials

## Comprehensive Fix Implementation Plan

### Phase 1: User API Key Infrastructure (Week 1)

#### 1.1 Enhance Unified API Key Service Integration

**Target:** `/utils/liveDataManager.js`

```javascript
// Replace provider configuration section (lines 888-933)
async initializeProviders(userId) {
  try {
    // Get user-specific API credentials
    const unifiedApiKeyService = require('./unifiedApiKeyService');
    const alpacaCredentials = await unifiedApiKeyService.getAlpacaKey(userId);
    
    if (!alpacaCredentials) {
      throw new Error(`No Alpaca API credentials found for user ${userId}`);
    }
    
    this.providers = {
      alpaca: {
        name: 'Alpaca Markets',
        enabled: true,
        credentials: {
          apiKey: alpacaCredentials.keyId,
          apiSecret: alpacaCredentials.secretKey,
          baseUrl: alpacaCredentials.isPaper ? 
            'https://paper-api.alpaca.markets' : 
            'https://api.alpaca.markets',
          wsUrl: alpacaCredentials.isPaper ?
            'wss://stream.data.alpaca.markets/v2/iex' :
            'wss://stream.data.alpaca.markets/v2/iex'
        },
        symbols: ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'NVDA'],
        dataTypes: ['trades', 'quotes', 'bars'],
        rateLimits: {
          requestsPerMinute: 200,
          connectionsPerUser: 1
        }
      }
    };

    console.log(`✅ Live data providers initialized for user ${userId}`);
    return this.providers;
    
  } catch (error) {
    console.error(`❌ Failed to initialize providers for user ${userId}:`, error);
    throw error;
  }
}
```

#### 1.2 WebSocket Real-Time Connection Enhancement

**Target:** `/websocket/realBroadcaster.js`

```javascript
// Replace WebSocket connection logic (lines 77-120)
async connectToAlpacaStream(userId, symbols = []) {
  try {
    const unifiedApiKeyService = require('../utils/unifiedApiKeyService');
    const credentials = await unifiedApiKeyService.getAlpacaKey(userId);
    
    if (!credentials) {
      throw new Error(`No Alpaca credentials for user ${userId}`);
    }

    const wsUrl = credentials.isPaper ? 
      'wss://stream.data.alpaca.markets/v2/iex' :
      'wss://stream.data.alpaca.markets/v2/iex';

    const ws = new WebSocket(wsUrl);
    
    ws.on('open', () => {
      console.log(`🔌 Alpaca WebSocket connected for user ${userId}`);
      
      // Authenticate with user's API keys
      const authMessage = {
        action: 'auth',
        key: credentials.keyId,
        secret: credentials.secretKey
      };
      
      ws.send(JSON.stringify(authMessage));
    });

    ws.on('message', (data) => {
      try {
        const messages = JSON.parse(data);
        messages.forEach(msg => {
          if (msg.T === 'success' && msg.msg === 'authenticated') {
            // Subscribe to symbols after authentication
            const subscribeMessage = {
              action: 'subscribe',
              trades: symbols,
              quotes: symbols
            };
            ws.send(JSON.stringify(subscribeMessage));
            console.log(`📡 Subscribed to ${symbols.length} symbols for user ${userId}`);
            
          } else if (msg.T === 't') { // Trade data
            this.broadcastToUser(userId, 'trade', {
              symbol: msg.S,
              price: msg.p,
              size: msg.s,
              timestamp: new Date(msg.t).getTime(),
              conditions: msg.c
            });
            
          } else if (msg.T === 'q') { // Quote data
            this.broadcastToUser(userId, 'quote', {
              symbol: msg.S,
              bid: msg.bp,
              ask: msg.ap,
              bidSize: msg.bs,
              askSize: msg.as,
              timestamp: new Date(msg.t).getTime()
            });
          }
        });
      } catch (parseError) {
        console.error(`❌ Error parsing Alpaca message for user ${userId}:`, parseError);
      }
    });

    ws.on('error', (error) => {
      console.error(`❌ Alpaca WebSocket error for user ${userId}:`, error);
      this.reconnectAfterDelay(userId, 5000);
    });

    ws.on('close', () => {
      console.log(`🔌 Alpaca WebSocket closed for user ${userId}`);
      this.reconnectAfterDelay(userId, 3000);
    });

    this.connections.set(`alpaca_${userId}`, {
      ws,
      userId,
      provider: 'alpaca',
      symbols,
      connectedAt: Date.now(),
      lastActivity: Date.now()
    });

    return { success: true, connectionId: `alpaca_${userId}` };
    
  } catch (error) {
    console.error(`❌ Failed to connect to Alpaca for user ${userId}:`, error);
    return { success: false, error: error.message };
  }
}
```

### Phase 2: HFT Service Real Trading Integration (Week 2)

#### 2.1 Real Order Execution Implementation

**Target:** `/services/hftService.js:496-550`

```javascript
// Replace mock executeOrder method
async executeOrder(signal, userId) {
  const orderId = this.generateOrderId();
  const startTime = Date.now();

  try {
    // Get user's Alpaca credentials
    const unifiedApiKeyService = require('../utils/unifiedApiKeyService');
    const credentials = await unifiedApiKeyService.getAlpacaKey(userId);
    
    if (!credentials) {
      throw new Error(`No Alpaca credentials found for user ${userId}`);
    }

    // Initialize Alpaca API client
    const alpacaApi = this.createAlpacaClient(credentials);
    
    // Prepare order request for Alpaca API
    const orderRequest = {
      symbol: signal.symbol,
      qty: signal.quantity.toString(),
      side: signal.type.toLowerCase(), // 'buy' or 'sell'
      type: 'market', // Use market orders for HFT speed
      time_in_force: 'ioc', // Immediate or Cancel for HFT
      extended_hours: false
    };

    // Submit order to Alpaca
    const alpacaOrder = await alpacaApi.createOrder(orderRequest);
    
    // Create internal order tracking
    const order = {
      orderId,
      alpacaOrderId: alpacaOrder.id,
      symbol: signal.symbol,
      type: signal.type,
      quantity: signal.quantity,
      requestedPrice: signal.price,
      executedPrice: parseFloat(alpacaOrder.filled_avg_price) || signal.price,
      strategy: signal.strategy,
      timestamp: signal.timestamp,
      executedAt: Date.now(),
      executionTime: Date.now() - startTime,
      status: alpacaOrder.status,
      slippage: alpacaOrder.filled_avg_price ? 
        Math.abs(parseFloat(alpacaOrder.filled_avg_price) - signal.price) / signal.price : 0,
      userId: userId,
      fees: parseFloat(alpacaOrder.fees) || 0
    };

    // Store order
    this.orders.set(orderId, order);

    // Update position tracking with real data
    await this.updatePositionFromAlpaca(order, alpacaApi);

    // Save to database
    await this.saveOrderToDatabase(order);

    // Update metrics
    this.updateExecutionMetrics(order);

    this.logger.info('Real order executed successfully', {
      orderId,
      alpacaOrderId: alpacaOrder.id,
      symbol: signal.symbol,
      executionTime: order.executionTime,
      userId,
      correlationId: this.correlationId
    });

    return {
      success: true,
      orderId: orderId,
      alpacaOrderId: alpacaOrder.id,
      order: order,
      realExecution: true
    };

  } catch (error) {
    this.logger.error('Real order execution failed', {
      orderId,
      symbol: signal.symbol,
      error: error.message,
      userId,
      correlationId: this.correlationId
    });

    return {
      success: false,
      orderId: orderId,
      error: error.message,
      fallbackExecuted: false
    };
  }
}

// Add Alpaca API client creation method
createAlpacaClient(credentials) {
  const { AlpacaApi } = require('@alpacahq/alpaca-trade-api');
  
  return new AlpacaApi({
    credentials: {
      key: credentials.keyId,
      secret: credentials.secretKey,
      paper: credentials.isPaper !== false // Default to paper trading for safety
    },
    rate_limit: true
  });
}
```

### Phase 3: Lambda Environment Configuration (Week 3)

#### 3.1 Environment Variables Setup

**Lambda Environment Variables Required:**
```yaml
# Core Configuration
AWS_REGION: us-east-1
NODE_ENV: production
ALLOW_DEV_BYPASS: false

# Database Configuration  
DB_ENDPOINT: financial-dashboard-db.cluster-xyz.us-east-1.rds.amazonaws.com
DB_SECRET_ARN: arn:aws:secretsmanager:us-east-1:account:secret:rds-db-credentials/cluster-xyz

# API Key Management
UNIFIED_API_KEY_ENABLED: true
API_KEY_CACHE_TTL: 300  # 5 minutes
API_KEY_MAX_CACHE_SIZE: 10000

# WebSocket Configuration
WS_MAX_CONNECTIONS_PER_USER: 5
WS_HEARTBEAT_INTERVAL: 30000
WS_RECONNECT_DELAY: 5000

# HFT Configuration
HFT_MAX_POSITION_SIZE: 1000
HFT_MAX_DAILY_LOSS: 500
HFT_EXECUTION_TIMEOUT: 5000

# Rate Limiting
ALPACA_RATE_LIMIT_REQUESTS_PER_MINUTE: 200
ALPACA_MAX_CONCURRENT_CONNECTIONS: 1
```

#### 3.2 Lambda Function Configuration

```yaml
# serverless.yml or CloudFormation additions
FunctionConfiguration:
  Timeout: 30  # Increased for real-time operations
  MemorySize: 1024  # Increased for WebSocket handling
  ReservedConcurrencyLimit: 50  # Prevent overwhelming Alpaca API
  
  VpcConfig:  # If database access required
    SecurityGroupIds:
      - sg-database-access
    SubnetIds:
      - subnet-private-a
      - subnet-private-b
      
  Environment:
    Variables:
      # See environment variables above
      
  Layers:
    - arn:aws:lambda:us-east-1:account:layer:node-modules-layer:1
    
  EventSourceMapping:  # For WebSocket API Gateway
    EventSourceArn: arn:aws:apigateway:us-east-1:websocket-api
```

### Phase 4: User Authentication & Authorization Enhancement (Week 4)

#### 4.1 User Context Enhancement

**Target:** Route-level user context integration

```javascript
// Add to route handlers requiring live data
const enhanceUserContext = async (req, res, next) => {
  try {
    if (!req.user || !req.user.sub) {
      return res.status(401).json({
        success: false,
        error: 'User authentication required for live data access'
      });
    }

    // Verify user has API keys configured
    const unifiedApiKeyService = require('../utils/unifiedApiKeyService');
    const hasApiKey = await unifiedApiKeyService.hasAlpacaKey(req.user.sub);
    
    if (!hasApiKey) {
      return res.status(403).json({
        success: false,
        error: 'Alpaca API key required for live data access',
        action: 'configure_api_key',
        redirectTo: '/api-keys'
      });
    }

    // Add user context for downstream services
    req.userContext = {
      userId: req.user.sub,
      hasLiveDataAccess: true,
      apiKeyConfigured: true
    };

    next();
  } catch (error) {
    console.error('User context enhancement failed:', error);
    return res.status(500).json({
      success: false,
      error: 'Failed to verify user data access permissions'
    });
  }
};

// Apply to relevant routes
router.use('/live-data/*', authenticateToken, enhanceUserContext);
router.use('/hft/*', authenticateToken, enhanceUserContext);
```

## Testing Strategy

### Phase 1 Testing: Paper Trading Validation
```bash
# Test user API key retrieval
curl -H "Authorization: Bearer $TEST_TOKEN" \
  "$API_BASE/api/api-keys/summary"

# Test live data connection with user keys
curl -H "Authorization: Bearer $TEST_TOKEN" \
  "$API_BASE/api/live-data/start"

# Test HFT paper trading execution
curl -X POST -H "Authorization: Bearer $TEST_TOKEN" \
  -d '{"strategies": ["scalping_btc"]}' \
  "$API_BASE/api/hft/start"
```

### Phase 2 Testing: Real-Time Data Validation
```javascript
// WebSocket connection test
const ws = new WebSocket(`${WS_BASE}/live-data`, {
  headers: { Authorization: `Bearer ${token}` }
});

ws.on('message', (data) => {
  const message = JSON.parse(data);
  console.log('Real-time data:', message);
  // Verify: message contains real Alpaca trade/quote data
  // Verify: timestamps are current (< 1 second old)
  // Verify: data format matches expected schema
});
```

## Risk Mitigation

### 1. **Gradual Rollout Strategy**
- Phase 1: Paper trading only for all users
- Phase 2: Live trading for admin/test users only  
- Phase 3: Live trading for verified users with position limits
- Phase 4: Full production rollout

### 2. **Safety Mechanisms**
- Default to paper trading mode
- Position size limits per user ($1000 initial limit)
- Daily loss limits ($500 initial limit)
- Emergency stop functionality
- Real-time risk monitoring

### 3. **Monitoring & Alerting**
- Real-time execution latency monitoring
- API error rate tracking
- Position exposure alerts
- Unusual trading pattern detection

## Success Metrics

### Technical Metrics
- ✅ 503 errors eliminated (completed)
- 🎯 Real-time data latency < 100ms  
- 🎯 Order execution success rate > 95%
- 🎯 WebSocket connection uptime > 99.5%
- 🎯 API key retrieval time < 200ms

### Business Metrics  
- 🎯 User onboarding completion rate > 80%
- 🎯 Live trading adoption rate > 50%
- 🎯 Average daily active users > 100
- 🎯 User satisfaction score > 4.0/5.0

## Implementation Timeline

| Week | Focus | Deliverables | Risk Level |
|------|-------|-------------|------------|
| **Week 1** | User API Key Integration | Live data with user keys | Medium |
| **Week 2** | Real Order Execution | Paper trading functional | Medium |  
| **Week 3** | Lambda Configuration | Production deployment ready | High |
| **Week 4** | User Auth Enhancement | Security & permissions | Low |
| **Week 5** | Testing & Validation | Full integration testing | Medium |
| **Week 6** | Production Rollout | Gradual user onboarding | High |

## Conclusion

The foundation is solid with the 503 errors resolved and comprehensive architecture in place. The primary remaining work involves:

1. **API Key Integration** - Replace environment variables with user-specific credentials
2. **Real API Connections** - Replace mock implementations with actual Alpaca API calls  
3. **Lambda Configuration** - Proper environment and resource allocation
4. **Security Enhancement** - User authentication and authorization for live trading

**Estimated Total Effort:** 6 weeks for full production deployment
**Risk Level:** Medium (well-defined scope, proven architecture)
**Success Probability:** High (clear implementation path, existing test coverage)

The system is ready for production-grade implementation with user-specific Alpaca API key integration.