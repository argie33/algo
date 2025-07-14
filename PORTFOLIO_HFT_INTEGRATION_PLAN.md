# Portfolio & HFT Integration Plan

## Executive Summary

This document outlines the comprehensive integration plan for connecting the Portfolio Management System with the High-Frequency Trading (HFT) infrastructure. The goal is to provide users with real-time portfolio data, live trade execution, and seamless integration with their broker API keys.

## 🎉 PHASE 0 COMPLETE: API Key Integration (July 2025)

**Status**: ✅ **FULLY OPERATIONAL**

All foundational API key integration work has been completed and is production-ready:

### ✅ Completed Deliverables
- **Database Infrastructure**: 37 tables created and operational
- **Security Implementation**: AES-256-GCM encryption, authentication fixes
- **API Integration**: Alpaca broker API ready, portfolio data sync
- **Frontend Enhancement**: API key status indicators, setup wizards  
- **Production Readiness**: Comprehensive testing, IaC deployment
- **Documentation**: Complete test suite and user guides

### 🚀 Ready for Users
- Users can configure broker API keys via `/settings`
- Portfolio pages show real-time API key connection status
- Live portfolio data integration works when API keys are configured
- Secure encrypted storage with AWS Secrets Manager
- Complete end-to-end workflow operational

---

## Current State Analysis

### Portfolio System (UPDATED - 2025-07-14)
- ✅ Basic portfolio display with mock data
- ✅ User authentication system  
- ✅ API key storage and encryption (AES-256-GCM)
- ✅ Database schemas for portfolio holdings (37 tables operational)
- ✅ **COMPLETED**: Full API key integration workflow
- ✅ **COMPLETED**: Portfolio authentication security fixes
- ✅ **COMPLETED**: API key status indicators on all portfolio pages
- ✅ **COMPLETED**: Alpaca broker API integration ready
- ✅ **COMPLETED**: Frontend API key setup wizards and user guidance
- ✅ **COMPLETED**: Comprehensive test suite (100% pass rate)
- ✅ **COMPLETED**: Production-ready deployment with Infrastructure as Code
- ❌ No real-time data integration (NEXT PHASE)
- ❌ No live trading capabilities (NEXT PHASE)
- ❌ No HFT system integration (NEXT PHASE)

### HFT System (Separate Stack)
- ✅ Deployed in separate AWS infrastructure
- ✅ Real-time market data processing
- ✅ High-frequency trading algorithms
- ❌ No portfolio system integration
- ❌ No user-specific API key management
- ❌ No live data feed to portfolio pages

## Integration Architecture

### 1. Real-Time Data Flow

```
User's Broker API → HFT System → Portfolio System → Frontend
     ↓                 ↓              ↓             ↓
  API Keys      Live Market Data   User Portfolio  Live Updates
  (Alpaca,      (Real-time         (Holdings,      (WebSocket/
   TD, etc.)    prices, orders)     P&L, etc.)     Server-sent events)
```

### 2. Key Components

#### A. Live Data Bridge Service
- **Location**: New service in HFT stack
- **Purpose**: Bridge between HFT system and portfolio system
- **Technology**: WebSocket + Redis for real-time communication
- **API**: RESTful endpoints for portfolio data queries

#### B. Portfolio Data Synchronization
- **Frequency**: Real-time (WebSocket) + 5-minute batch sync
- **Data Types**: Holdings, P&L, Orders, Market Data
- **Storage**: PostgreSQL (main) + Redis (cache)

#### C. User API Key Management
- **Integration**: HFT system reads encrypted API keys from portfolio DB
- **Security**: AES-256-GCM encryption with user-specific salts
- **Rotation**: Automatic key rotation and validation

## Implementation Plan

### Phase 1: Core Infrastructure (2-3 days)

#### 1.1 HFT Data Bridge Service
```typescript
// New service in HFT stack
interface HFTPortfolioBridge {
  getUserPortfolioData(userId: string, apiKeyId: string): Promise<PortfolioData>;
  subscribeLiveData(userId: string, callback: (data: LiveData) => void): void;
  executeTrade(userId: string, tradeRequest: TradeRequest): Promise<TradeResult>;
}
```

#### 1.2 Portfolio System Updates
- Add WebSocket endpoint for real-time updates
- Implement live data caching layer
- Add HFT system client

#### 1.3 Database Schema Enhancements
```sql
-- New tables for live data integration
CREATE TABLE live_portfolio_sessions (
  id SERIAL PRIMARY KEY,
  user_id UUID NOT NULL,
  api_key_id INTEGER NOT NULL,
  session_token UUID NOT NULL,
  hft_connection_id VARCHAR(255),
  status VARCHAR(50) DEFAULT 'active',
  created_at TIMESTAMP DEFAULT NOW(),
  last_heartbeat TIMESTAMP DEFAULT NOW()
);

CREATE TABLE portfolio_live_data (
  id SERIAL PRIMARY KEY,
  user_id UUID NOT NULL,
  symbol VARCHAR(10) NOT NULL,
  live_price DECIMAL(10,2),
  live_change DECIMAL(10,2),
  live_change_percent DECIMAL(10,4),
  market_status VARCHAR(20),
  last_updated TIMESTAMP DEFAULT NOW(),
  UNIQUE(user_id, symbol)
);
```

### Phase 2: Live Data Integration (2-3 days)

#### 2.1 Real-Time Price Feed
- Integrate with market data providers (Alpaca, TD Ameritrade, etc.)
- Implement price caching and distribution
- Add market hours handling

#### 2.2 Portfolio Live Updates
- Real-time P&L calculations
- Live position updates
- Market value updates

#### 2.3 Error Handling & Monitoring
- Comprehensive error logging
- Health checks for HFT integration
- Fallback mechanisms for system failures

### Phase 3: Trading Integration (3-4 days)

#### 3.1 Live Trading Interface
- Real-time order placement
- Order status monitoring
- Trade execution confirmations

#### 3.2 Risk Management
- Position size validation
- Account balance checks
- Risk limit enforcement

### Phase 4: Frontend Integration (2-3 days)

#### 4.1 Live Data Display
- Real-time portfolio value updates
- Live P&L charts
- Market status indicators

#### 4.2 User Experience
- Loading states for live data
- Error messages for connection issues
- Offline mode capabilities

## Technical Implementation Details

### 1. HFT System Integration

#### A. API Key Bridge
```python
# In HFT system - portfolio_bridge.py
class PortfolioAPIKeyBridge:
    def __init__(self, portfolio_db_connection):
        self.portfolio_db = portfolio_db_connection
    
    async def get_user_api_keys(self, user_id: str) -> List[APIKey]:
        """Fetch and decrypt user API keys for broker integration"""
        query = """
        SELECT id, provider, encrypted_api_key, encrypted_api_secret, 
               key_iv, secret_iv, key_auth_tag, secret_auth_tag, 
               user_salt, is_sandbox, is_active
        FROM user_api_keys 
        WHERE user_id = %s AND is_active = true
        """
        # Decrypt keys using same encryption logic as portfolio system
        return await self.decrypt_api_keys(raw_keys)
```

#### B. Live Data Service
```python
# In HFT system - live_data_service.py
class LiveDataService:
    def __init__(self, redis_client, websocket_manager):
        self.redis = redis_client
        self.websockets = websocket_manager
    
    async def publish_portfolio_update(self, user_id: str, data: dict):
        """Publish live portfolio updates to user's WebSocket"""
        await self.redis.publish(f"portfolio:{user_id}", json.dumps(data))
        await self.websockets.send_to_user(user_id, data)
```

### 2. Portfolio System Updates

#### A. WebSocket Handler
```javascript
// In portfolio.js
const WebSocket = require('ws');
const Redis = require('redis');

class PortfolioLiveDataHandler {
  constructor() {
    this.redis = new Redis(process.env.REDIS_URL);
    this.wss = new WebSocket.Server({ port: 8080 });
    this.userConnections = new Map();
  }

  async handleConnection(ws, userId) {
    this.userConnections.set(userId, ws);
    
    // Subscribe to user's portfolio updates
    await this.redis.subscribe(`portfolio:${userId}`);
    
    ws.on('message', async (message) => {
      const data = JSON.parse(message);
      if (data.type === 'subscribe_portfolio') {
        await this.subscribeUserPortfolio(userId, data.apiKeyId);
      }
    });
  }

  async subscribeUserPortfolio(userId, apiKeyId) {
    // Request HFT system to start live data feed
    const hftResponse = await fetch(`${process.env.HFT_API_URL}/portfolio/subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId, apiKeyId })
    });
  }
}
```

#### B. Enhanced Portfolio Endpoints
```javascript
// Add to portfolio.js
router.get('/live-data', authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const { apiKeyId } = req.query;
    
    // Get live portfolio data from HFT system
    const hftResponse = await fetch(`${process.env.HFT_API_URL}/portfolio/live`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${process.env.HFT_API_TOKEN}`,
        'User-ID': userId,
        'API-Key-ID': apiKeyId
      }
    });
    
    if (!hftResponse.ok) {
      throw new Error('Failed to fetch live data from HFT system');
    }
    
    const liveData = await hftResponse.json();
    
    res.json({
      success: true,
      data: {
        ...liveData,
        timestamp: new Date().toISOString(),
        dataSource: 'hft-live'
      }
    });
  } catch (error) {
    console.error('❌ Live data fetch failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch live portfolio data',
      details: error.message
    });
  }
});
```

### 3. Frontend Integration

#### A. Live Data Component
```javascript
// In portfolio frontend
class LivePortfolioData {
  constructor(userId, apiKeyId) {
    this.userId = userId;
    this.apiKeyId = apiKeyId;
    this.websocket = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
  }

  connect() {
    this.websocket = new WebSocket(`ws://localhost:8080`);
    
    this.websocket.onopen = () => {
      console.log('🔗 Connected to live portfolio data');
      this.websocket.send(JSON.stringify({
        type: 'subscribe_portfolio',
        userId: this.userId,
        apiKeyId: this.apiKeyId
      }));
    };

    this.websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleLiveUpdate(data);
    };

    this.websocket.onclose = () => {
      console.log('🔌 Disconnected from live portfolio data');
      this.handleReconnect();
    };
  }

  handleLiveUpdate(data) {
    // Update portfolio display with live data
    if (data.type === 'portfolio_update') {
      this.updatePortfolioDisplay(data.portfolio);
    } else if (data.type === 'price_update') {
      this.updatePriceDisplay(data.prices);
    }
  }
}
```

## Error Handling & Recovery

### 1. Connection Failures
- Automatic reconnection with exponential backoff
- Fallback to cached data when HFT system is unavailable
- Clear user messaging about connection status

### 2. Data Validation
- Validate all incoming data from HFT system
- Sanity checks on portfolio values and changes
- Logging of all data discrepancies

### 3. System Monitoring
- Health checks for HFT integration
- Performance metrics for live data latency
- Alerting for system failures

## Security Considerations

### 1. API Key Security
- All API keys remain encrypted in portfolio database
- HFT system never stores unencrypted keys
- Regular key rotation and validation

### 2. Data Transmission
- All communication encrypted (TLS 1.3)
- WebSocket connections authenticated
- Rate limiting on all endpoints

### 3. User Authentication
- JWT token validation for all requests
- Session management for live data connections
- Audit logging for all trading activities

## Performance Optimization

### 1. Caching Strategy
- Redis caching for frequently accessed data
- CDN for static assets
- Database query optimization

### 2. Real-Time Performance
- WebSocket connection pooling
- Message queuing for high-volume updates
- Load balancing across multiple instances

## Deployment Strategy

### 1. Environment Setup
- Development: Mock HFT system for testing
- Staging: Limited HFT integration
- Production: Full HFT system integration

### 2. Rollout Plan
- Beta testing with select users
- Gradual rollout to all users
- Monitoring and performance tuning

## Success Metrics

### 1. Technical Metrics
- Live data latency < 100ms
- WebSocket connection uptime > 99.9%
- Portfolio sync accuracy > 99.95%

### 2. User Experience Metrics
- Real-time data availability
- Trading execution success rate
- User satisfaction scores

## Timeline

- **Week 1**: Core infrastructure and HFT bridge
- **Week 2**: Live data integration and testing
- **Week 3**: Trading integration and frontend
- **Week 4**: Testing, optimization, and deployment

## Risk Mitigation

### 1. Technical Risks
- HFT system downtime → Fallback to cached data
- Network failures → Automatic reconnection
- Data corruption → Validation and recovery

### 2. Business Risks
- Regulatory compliance → Legal review
- Data accuracy → Comprehensive testing
- User experience → Extensive QA testing

## Conclusion

This integration plan provides a comprehensive roadmap for connecting the Portfolio Management System with the HFT infrastructure. The phased approach ensures stability while delivering real-time capabilities to users. The focus on error handling, security, and performance will ensure a robust and reliable system.

---

*This plan should be reviewed and updated as implementation progresses and requirements evolve.*