# 🚀 Backend Alpaca Integration Design

## Executive Summary

This design provides a comprehensive backend Alpaca integration that addresses all identified gaps in the current portfolio data pipeline. The solution builds upon existing infrastructure while filling critical implementation gaps.

## Current State Analysis

### ✅ What's Working
- **Database Schema**: Complete portfolio tables exist in `sql/portfolio-schema.sql`
- **AlpacaService**: Basic service class exists in `utils/alpacaService.js`
- **API Key Management**: User API key storage and retrieval working
- **Frontend Components**: Ready to display data but getting 504 errors
- **Authentication**: User auth system working properly

### ❌ Critical Gaps Identified
1. **Database Connectivity**: Lambda still can't connect to database (504 timeouts)
2. **Incomplete Alpaca Integration**: Limited portfolio fetching, missing data storage
3. **Missing Data Pipeline**: No storage of Alpaca data in database
4. **Timeout Issues**: Lambda functions timing out on portfolio requests
5. **Real-time Updates**: No WebSocket or data synchronization

## 🏗️ Architecture Design

### Data Flow Architecture
```
User → Settings (API Keys) → Database Storage → Portfolio Request → 
API Key Retrieval → Alpaca API Call → Data Transformation → 
Database Storage → Response to Frontend → Real-time Updates
```

### Component Architecture
```
┌─────────────────┬─────────────────┬─────────────────┐
│   Frontend      │   Lambda        │   External      │
├─────────────────┼─────────────────┼─────────────────┤
│ Portfolio.jsx   │ portfolio.js    │ Alpaca API      │
│ Settings.jsx    │ alpacaService   │ PostgreSQL      │
│ API Indicators  │ Database Conn   │ AWS Secrets     │
│ Error Handling  │ Circuit Breaker │ CloudWatch      │
└─────────────────┴─────────────────┴─────────────────┘
```

## 🔧 Implementation Plan

### Phase 1: Database Connectivity Fix (IMMEDIATE)
**Priority**: CRITICAL - Must fix 504 timeouts first

**Root Cause**: Environment variable priority conflict
- Lambda deployment still has old environment variables
- Database connection manager trying localhost instead of RDS

**Solution**: 
1. Redeploy Lambda with fixed `.env` configuration
2. Verify database connectivity with health checks
3. Test basic portfolio endpoints respond properly

**Expected Result**: 
- ❌ 504 timeouts → ✅ Database connections working
- ❌ Empty responses → ✅ Basic API responses

### Phase 2: Enhanced AlpacaService (URGENT)
**Priority**: HIGH - Complete the Alpaca integration

**Current Gap**: AlpacaService exists but incomplete

**Enhanced AlpacaService Design**:

```javascript
class EnhancedAlpacaService {
  // Core API Methods
  async getAccount()           // Account information
  async getPositions()         // Current holdings
  async getOrders()           // Order history
  async getPortfolioHistory() // Performance history
  
  // Data Management Methods
  async syncPortfolioData(userId)     // Store in database
  async updatePortfolioMetadata(userId) // Sync account info
  async refreshPositions(userId)      // Update holdings
  
  // Real-time Methods
  async subscribeToUpdates()   // WebSocket connection
  async handleRealTimeUpdate() // Process live updates
  
  // Utility Methods
  async validateConnection()   // Test API connectivity
  async getAccountInfo(userId) // Formatted account data
  async calculatePerformance() // Portfolio math
}
```

**Database Integration**:
- Store portfolio holdings in `portfolio_holdings` table
- Update portfolio metadata in `portfolio_metadata` table
- Track performance history in `portfolio_performance_history` table
- Handle real-time price updates

### Phase 3: Complete Data Pipeline (CRITICAL)
**Priority**: HIGH - End-to-end data flow

**Pipeline Components**:

1. **API Key Retrieval Service**
```javascript
// Enhanced getUserApiKey function
const getUserApiKey = async (userId, provider) => {
  // Get from database with proper error handling
  // Support multiple providers (Alpaca, TD Ameritrade, etc.)
  // Decrypt and validate credentials
  // Cache for performance
}
```

2. **Portfolio Data Synchronization Service**
```javascript
// New portfolioSyncService.js
class PortfolioSyncService {
  async syncUserPortfolio(userId) {
    // 1. Get user API keys
    // 2. Initialize Alpaca service
    // 3. Fetch portfolio data from Alpaca
    // 4. Transform and validate data
    // 5. Store in database
    // 6. Return formatted response
  }
}
```

3. **Enhanced Portfolio Routes**
```javascript
// Enhanced portfolio.js routes
router.get('/holdings', async (req, res) => {
  // 1. Authenticate user
  // 2. Get from database first (fast response)
  // 3. Trigger background sync if stale
  // 4. Return cached data with sync status
})

router.post('/sync', async (req, res) => {
  // Manual sync trigger
  // Real-time data refresh
  // Force update from Alpaca
})
```

### Phase 4: Database Schema Enhancements (MEDIUM)
**Priority**: MEDIUM - Optimize for real-time data

**Schema Enhancements**:

```sql
-- Add Alpaca-specific fields to existing schema
ALTER TABLE portfolio_holdings ADD COLUMN IF NOT EXISTS alpaca_asset_id VARCHAR(50);
ALTER TABLE portfolio_holdings ADD COLUMN IF NOT EXISTS alpaca_position_id VARCHAR(50);
ALTER TABLE portfolio_holdings ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMP;

-- Add API key tracking
ALTER TABLE portfolio_metadata ADD COLUMN IF NOT EXISTS api_provider VARCHAR(20);
ALTER TABLE portfolio_metadata ADD COLUMN IF NOT EXISTS last_api_call TIMESTAMP;
ALTER TABLE portfolio_metadata ADD COLUMN IF NOT EXISTS api_call_count INTEGER DEFAULT 0;

-- Add real-time updates tracking
CREATE TABLE IF NOT EXISTS portfolio_sync_log (
  sync_id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(user_id),
  sync_type VARCHAR(20) NOT NULL, -- 'auto', 'manual', 'realtime'
  status VARCHAR(20) NOT NULL,    -- 'success', 'failed', 'partial'
  records_updated INTEGER DEFAULT 0,
  api_calls_made INTEGER DEFAULT 0,
  duration_ms INTEGER,
  error_message TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Phase 5: Real-time Features (ENHANCEMENT)
**Priority**: MEDIUM - Live data streaming

**Real-time Architecture**:

1. **WebSocket Integration**
```javascript
// New alpacaWebSocketService.js
class AlpacaWebSocketService {
  async connect(apiKey, apiSecret) {
    // Connect to Alpaca WebSocket
    // Subscribe to portfolio updates
    // Handle real-time price changes
  }
  
  async subscribeToPortfolio(userId, symbols) {
    // Subscribe to position updates
    // Real-time P&L calculations
    // Push updates to frontend
  }
}
```

2. **Background Sync Service**
```javascript
// Background job for data freshness
const backgroundSync = {
  // Auto-sync every 5 minutes during market hours
  // Smart refresh based on data age
  // Rate limiting for API calls
  // Error handling and retry logic
}
```

## 🔍 Detailed Component Specifications

### 1. Enhanced Portfolio Routes

**File**: `routes/portfolio.js` (Enhanced)

```javascript
// GET /api/portfolio/holdings
// Enhanced with database storage and caching
router.get('/holdings', async (req, res) => {
  const userId = req.user?.sub;
  const accountType = req.query.accountType || 'paper';
  
  try {
    // 1. Check database for cached data
    const cachedData = await getCachedPortfolioData(userId, accountType);
    const isStale = isDataStale(cachedData, 5 * 60 * 1000); // 5 minutes
    
    // 2. Return cached data if fresh
    if (cachedData && !isStale) {
      return res.json({
        success: true,
        data: cachedData,
        source: 'database',
        lastSync: cachedData.lastSync
      });
    }
    
    // 3. Fetch fresh data from Alpaca
    const apiKeys = await getUserApiKey(userId, 'alpaca');
    if (!apiKeys) {
      // Return sample data if no API keys
      return res.json(getSamplePortfolioData(accountType));
    }
    
    // 4. Initialize Alpaca service and fetch data
    const alpacaService = new AlpacaService(
      apiKeys.apiKey, 
      apiKeys.apiSecret, 
      accountType === 'paper'
    );
    
    const portfolioData = await alpacaService.getPortfolioData();
    
    // 5. Store in database for caching
    await storePortfolioData(userId, portfolioData, accountType);
    
    // 6. Return fresh data
    res.json({
      success: true,
      data: portfolioData,
      source: 'alpaca',
      lastSync: new Date().toISOString()
    });
    
  } catch (error) {
    // Enhanced error handling with fallbacks
    console.error('Portfolio data error:', error);
    
    // Try to return stale data if available
    const staleData = await getCachedPortfolioData(userId, accountType);
    if (staleData) {
      return res.json({
        success: true,
        data: staleData,
        source: 'database_stale',
        warning: 'Data may be outdated',
        lastSync: staleData.lastSync
      });
    }
    
    // Final fallback to sample data
    res.json(getSamplePortfolioData(accountType));
  }
});

// POST /api/portfolio/sync - Manual refresh
router.post('/sync', async (req, res) => {
  const userId = req.user?.sub;
  const { force = false } = req.body;
  
  try {
    const result = await portfolioSyncService.syncUserPortfolio(userId, { force });
    res.json({
      success: true,
      message: 'Portfolio synchronized successfully',
      data: result
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Sync failed',
      details: error.message
    });
  }
});
```

### 2. Database Service Layer

**File**: `utils/portfolioDatabaseService.js` (New)

```javascript
const { query, transaction } = require('./database');

class PortfolioDatabaseService {
  // Store portfolio holdings from Alpaca
  async storePortfolioHoldings(userId, holdings, accountType) {
    const queries = holdings.map(holding => ({
      text: `
        INSERT INTO portfolio_holdings 
        (user_id, symbol, quantity, avg_cost, current_price, market_value, 
         unrealized_pl, sector, alpaca_asset_id, last_sync_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, symbol) 
        DO UPDATE SET
          quantity = EXCLUDED.quantity,
          avg_cost = EXCLUDED.avg_cost,
          current_price = EXCLUDED.current_price,
          market_value = EXCLUDED.market_value,
          unrealized_pl = EXCLUDED.unrealized_pl,
          last_sync_at = CURRENT_TIMESTAMP
      `,
      values: [
        userId, holding.symbol, holding.qty, holding.avg_entry_price,
        holding.current_price, holding.market_value, holding.unrealized_pl,
        holding.sector, holding.asset_id
      ]
    }));
    
    return await transaction(queries);
  }
  
  // Get cached portfolio data
  async getCachedPortfolioData(userId, accountType) {
    const result = await query(`
      SELECT 
        h.*,
        m.total_equity,
        m.buying_power,
        m.cash,
        m.last_sync_at,
        m.account_type
      FROM portfolio_holdings h
      LEFT JOIN portfolio_metadata m ON h.user_id = m.user_id
      WHERE h.user_id = $1
      ORDER BY h.market_value DESC
    `, [userId]);
    
    return this.formatPortfolioResponse(result.rows);
  }
  
  // Update portfolio metadata
  async updatePortfolioMetadata(userId, accountData, accountType) {
    return await query(`
      INSERT INTO portfolio_metadata 
      (user_id, account_id, account_type, total_equity, buying_power, 
       cash, last_sync_at, sync_status)
      VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, 'success')
      ON CONFLICT (user_id) 
      DO UPDATE SET
        total_equity = EXCLUDED.total_equity,
        buying_power = EXCLUDED.buying_power,
        cash = EXCLUDED.cash,
        last_sync_at = CURRENT_TIMESTAMP,
        sync_status = 'success'
    `, [
      userId, accountData.account_number, accountType,
      accountData.equity, accountData.buying_power, accountData.cash
    ]);
  }
  
  // Check if data is stale
  isDataStale(data, maxAgeMs = 5 * 60 * 1000) {
    if (!data || !data.lastSync) return true;
    const age = Date.now() - new Date(data.lastSync).getTime();
    return age > maxAgeMs;
  }
  
  // Format database response for frontend
  formatPortfolioResponse(rows) {
    if (rows.length === 0) return null;
    
    const metadata = rows[0];
    const holdings = rows.filter(row => row.symbol).map(row => ({
      symbol: row.symbol,
      quantity: parseFloat(row.quantity),
      avgCost: parseFloat(row.avg_cost),
      currentPrice: parseFloat(row.current_price),
      marketValue: parseFloat(row.market_value),
      unrealizedPL: parseFloat(row.unrealized_pl),
      sector: row.sector,
      lastUpdated: row.updated_at
    }));
    
    return {
      holdings,
      summary: {
        totalEquity: parseFloat(metadata.total_equity),
        buyingPower: parseFloat(metadata.buying_power),
        cash: parseFloat(metadata.cash),
        accountType: metadata.account_type
      },
      lastSync: metadata.last_sync_at
    };
  }
}

module.exports = new PortfolioDatabaseService();
```

### 3. Portfolio Synchronization Service

**File**: `utils/portfolioSyncService.js` (New)

```javascript
const AlpacaService = require('./alpacaService');
const portfolioDb = require('./portfolioDatabaseService');
const apiKeyService = require('./apiKeyService');

class PortfolioSyncService {
  async syncUserPortfolio(userId, options = {}) {
    const { force = false, accountType = 'paper' } = options;
    const startTime = Date.now();
    
    try {
      console.log(`🔄 Starting portfolio sync for user ${userId}`);
      
      // 1. Get user API keys
      const apiKeys = await apiKeyService.getApiKey(userId, 'alpaca');
      if (!apiKeys) {
        throw new Error('No Alpaca API keys found for user');
      }
      
      // 2. Check if sync needed (unless forced)
      if (!force) {
        const cachedData = await portfolioDb.getCachedPortfolioData(userId, accountType);
        if (cachedData && !portfolioDb.isDataStale(cachedData)) {
          console.log('📋 Portfolio data is fresh, skipping sync');
          return cachedData;
        }
      }
      
      // 3. Initialize Alpaca service
      const isPaper = accountType === 'paper';
      const alpacaService = new AlpacaService(
        apiKeys.keyId,
        apiKeys.secretKey,
        isPaper
      );
      
      // 4. Fetch data from Alpaca API
      console.log('📡 Fetching portfolio data from Alpaca...');
      const [account, positions, orders] = await Promise.all([
        alpacaService.getAccount(),
        alpacaService.getPositions(),
        alpacaService.getOrders({ status: 'all', limit: 50 })
      ]);
      
      // 5. Store in database
      console.log('💾 Storing portfolio data in database...');
      await Promise.all([
        portfolioDb.storePortfolioHoldings(userId, positions, accountType),
        portfolioDb.updatePortfolioMetadata(userId, account, accountType)
      ]);
      
      // 6. Log sync completion
      const duration = Date.now() - startTime;
      await this.logSyncActivity(userId, 'success', {
        recordsUpdated: positions.length,
        apiCallsMade: 3,
        duration
      });
      
      console.log(`✅ Portfolio sync completed in ${duration}ms`);
      
      // 7. Return fresh data
      return await portfolioDb.getCachedPortfolioData(userId, accountType);
      
    } catch (error) {
      console.error('❌ Portfolio sync failed:', error);
      
      // Log sync failure
      const duration = Date.now() - startTime;
      await this.logSyncActivity(userId, 'failed', {
        duration,
        errorMessage: error.message
      });
      
      throw error;
    }
  }
  
  async logSyncActivity(userId, status, details) {
    try {
      await query(`
        INSERT INTO portfolio_sync_log 
        (user_id, sync_type, status, records_updated, api_calls_made, 
         duration_ms, error_message)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
      `, [
        userId, 'manual', status, details.recordsUpdated || 0,
        details.apiCallsMade || 0, details.duration || 0,
        details.errorMessage || null
      ]);
    } catch (logError) {
      console.error('Failed to log sync activity:', logError);
    }
  }
  
  // Background sync for all users
  async syncAllUsers() {
    // Get all users with API keys
    // Stagger sync requests to avoid rate limits
    // Only sync if data is stale
    // Handle errors gracefully
  }
}

module.exports = new PortfolioSyncService();
```

## 🚨 Critical Issues Resolution

### Issue 1: 504 Timeout Errors
**Root Cause**: Database connectivity failure
**Solution**: 
1. Immediate Lambda redeployment with fixed `.env`
2. Database connection verification
3. Circuit breaker pattern implementation

### Issue 2: Missing Database Integration
**Root Cause**: Alpaca data not stored in database
**Solution**:
1. Complete portfolioDatabaseService implementation
2. Portfolio sync service for data persistence
3. Caching layer for performance

### Issue 3: Incomplete API Key Flow
**Root Cause**: API keys not properly retrieved and used
**Solution**:
1. Enhanced getUserApiKey function
2. Proper error handling and fallbacks
3. Multiple provider support

### Issue 4: No Real-time Updates
**Root Cause**: Static data, no live updates
**Solution**:
1. WebSocket integration with Alpaca
2. Background sync service
3. Real-time P&L calculations

## 📊 Success Metrics

### Performance Targets
- **Response Time**: < 2 seconds for cached data
- **Sync Time**: < 10 seconds for full portfolio sync
- **Availability**: 99.9% uptime for portfolio endpoints
- **Data Freshness**: < 5 minutes for market hours

### User Experience Goals
- ✅ Portfolio loads without 504 errors
- ✅ Live data displays from user's actual Alpaca account
- ✅ Real-time updates during market hours
- ✅ Seamless fallback to sample data when needed

## 🚀 Implementation Timeline

### Phase 1 (Immediate - 2 hours)
- Fix database connectivity issue
- Redeploy Lambda with correct environment
- Test basic portfolio endpoints

### Phase 2 (Day 1 - 6 hours)
- Implement portfolioDatabaseService
- Enhance portfolio routes with database integration
- Add portfolio sync service

### Phase 3 (Day 2 - 4 hours)
- Complete Alpaca service integration
- Add real-time data fetching
- Implement background sync

### Phase 4 (Day 3 - 4 hours)
- Add WebSocket integration
- Implement real-time updates
- Performance optimization

### Phase 5 (Day 4 - 2 hours)
- End-to-end testing
- Production deployment
- Monitoring and alerting setup

## 🔒 Security Considerations

### API Key Security
- API keys encrypted at rest in database
- Never logged or exposed in responses
- Secure retrieval with user authentication
- Rate limiting to prevent abuse

### Data Privacy
- User portfolio data isolated by user ID
- No cross-user data leakage
- Secure database connections
- GDPR compliance for data deletion

### Error Handling
- Graceful degradation to sample data
- Circuit breaker pattern for external APIs
- Comprehensive logging without sensitive data
- User-friendly error messages

## 📈 Monitoring & Alerting

### Key Metrics
- Portfolio sync success rate
- API response times
- Database connection health
- Alpaca API rate limits
- User error rates

### Alerts
- 504 errors > 5% in 5 minutes
- Database connection failures
- Alpaca API rate limit warnings
- Sync failures for > 10% of users

This design provides a complete, production-ready backend Alpaca integration that will resolve all current issues and provide a robust foundation for the portfolio features.