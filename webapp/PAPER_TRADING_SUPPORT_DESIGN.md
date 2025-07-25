# Paper Trading Support Design Specification

## Overview
This document outlines the comprehensive design for implementing paper trading support across all Alpaca-integrated API endpoints and frontend pages.

## Current Status Analysis

### ✅ **Endpoints with Paper Trading Support**
1. **Portfolio (`/api/portfolio/`)** - **COMPLETE**
   - ✅ `accountType=paper` parameter support
   - ✅ Alpaca service paper/live mode switching
   - ✅ Database caching with account type awareness
   - ✅ Enhanced response format with paper trading indicators

2. **Trades (`/api/trades/`)** - **PARTIAL**
   - ✅ `isSandbox` flag in API key helper
   - ✅ AlpacaService integration with paper mode
   - ⚠️ Missing `accountType` parameter standardization

3. **Live Data (`/api/liveData/`)** - **PARTIAL**
   - ✅ Paper trading API key support
   - ⚠️ Limited paper-specific features (market data same for both)

### ❌ **Endpoints Missing Paper Trading Support**
1. **Trading (`/api/trading/`)** - **NEEDS IMPLEMENTATION**
   - ❌ No `accountType` parameter support
   - ❌ Missing paper trading mode detection
   - ❌ Order execution without paper/live distinction

2. **Performance (`/api/performance/`)** - **NEEDS IMPLEMENTATION**
   - ❌ No paper trading metrics separation
   - ❌ Missing account type filtering
   - ❌ Performance calculations don't distinguish paper vs live

3. **Backtest (`/api/backtest/`)** - **NEEDS IMPLEMENTATION**
   - ❌ No integration with user's paper trading data
   - ❌ Missing paper account initialization capital
   - ❌ No paper trading simulation comparison

4. **Risk Management (`/api/risk/`)** - **NEEDS IMPLEMENTATION**
   - ❌ Risk calculations don't consider paper vs live differences
   - ❌ Missing paper trading risk parameters
   - ❌ No account type risk profiling

5. **Trading Strategies (`/api/trading-strategies/`)** - **NEEDS IMPLEMENTATION**
   - ❌ Strategy execution without paper/live mode selection
   - ❌ Missing paper trading performance tracking
   - ❌ No paper trading backtesting integration

## Design Architecture

### 1. **Unified API Key Service Enhancement**

```javascript
// Enhanced API Key Service with Paper Trading Support
class UnifiedApiKeyService {
  async getApiKeyWithAccountType(userId, provider, accountType = 'paper') {
    const credentials = await this.getApiKey(userId, provider);
    if (!credentials) return null;
    
    return {
      apiKey: credentials.keyId,
      apiSecret: credentials.secretKey,
      isSandbox: accountType === 'paper' || credentials.version === '1.0',
      accountType: accountType,
      provider: provider,
      supportsLive: credentials.version !== '1.0', // v1.0 is paper-only
      supportsPaper: true // Alpaca always supports paper
    };
  }
  
  async validateAccountTypeAccess(userId, provider, requestedAccountType) {
    const credentials = await this.getApiKey(userId, provider);
    if (!credentials) return false;
    
    // Paper trading always allowed
    if (requestedAccountType === 'paper') return true;
    
    // Live trading only if not restricted to paper-only
    if (requestedAccountType === 'live') {
      return credentials.version !== '1.0';
    }
    
    return false;
  }
}
```

### 2. **Standard Route Parameter Schema**

```javascript
// Universal paper trading validation schema
const paperTradingValidationSchema = {
  accountType: {
    type: 'string',
    sanitizer: (value) => sanitizers.string(value, { defaultValue: 'paper' }),
    validator: (value) => ['paper', 'live'].includes(value),
    errorMessage: 'accountType must be paper or live'
  },
  force: {
    type: 'boolean',
    sanitizer: (value) => sanitizers.boolean(value, { defaultValue: false }),
    validator: (value) => typeof value === 'boolean',
    errorMessage: 'force must be true or false'
  }
};
```

### 3. **AlpacaService Integration Pattern**

```javascript
// Standard pattern for all routes
const setupAlpacaService = async (userId, accountType = 'paper') => {
  const credentials = await apiKeyService.getApiKeyWithAccountType(
    userId, 
    'alpaca', 
    accountType
  );
  
  if (!credentials) {
    throw new Error(`No Alpaca API keys configured for ${accountType} trading`);
  }
  
  // Validate account type access
  const hasAccess = await apiKeyService.validateAccountTypeAccess(
    userId, 
    'alpaca', 
    accountType
  );
  
  if (!hasAccess) {
    throw new Error(`Access denied for ${accountType} trading with current API keys`);
  }
  
  return new AlpacaService(
    credentials.apiKey,
    credentials.apiSecret,
    credentials.isSandbox
  );
};
```

## Implementation Plan

### Phase 1: Core Infrastructure (HIGH PRIORITY)

#### 1.1 **Enhanced API Key Service**
- Extend `unifiedApiKeyService.js` with paper trading methods
- Add account type validation logic
- Implement paper/live access control

#### 1.2 **Trading Routes Enhancement** (`/api/trading/`)
- Add `accountType` parameter to all trading endpoints
- Implement paper/live order execution separation
- Add paper trading validation and safety checks

#### 1.3 **Performance Routes Enhancement** (`/api/performance/`)
- Add account type filtering to performance metrics
- Separate paper and live performance calculations
- Add paper trading performance indicators

### Phase 2: Advanced Features (MEDIUM PRIORITY)

#### 2.1 **Risk Management Enhancement** (`/api/risk/`)
- Add paper trading risk parameter sets
- Implement account type-specific risk calculations
- Add paper trading risk simulation features

#### 2.2 **Backtest Integration** (`/api/backtest/`)
- Connect backtests with user's paper trading account
- Add paper account capital initialization
- Implement paper vs backtest performance comparison

#### 2.3 **Trading Strategies Enhancement** (`/api/trading-strategies/`)
- Add paper trading strategy execution
- Implement paper trading performance tracking
- Add paper trading strategy validation

### Phase 3: UI/UX Enhancement (LOW PRIORITY)

#### 3.1 **Frontend Component Updates**
- Add paper trading mode indicators
- Implement account type switcher components
- Add paper trading onboarding flow

#### 3.2 **Enhanced Error Handling**
- Paper trading specific error messages
- Account type validation error responses
- Paper trading limitation notifications

## Technical Specifications

### API Endpoint Pattern

```javascript
// Standard implementation pattern for all routes
router.get('/endpoint', 
  createValidationMiddleware({
    ...paperTradingValidationSchema,
    // endpoint-specific validation
  }), 
  async (req, res) => {
    const { accountType = 'paper' } = req.query;
    const userId = req.user?.sub;
    
    try {
      // Setup Alpaca service with account type
      const alpacaService = await setupAlpacaService(userId, accountType);
      
      // Execute endpoint logic with paper/live awareness
      const result = await executeEndpointLogic(alpacaService, accountType);
      
      res.json({
        success: true,
        data: result,
        accountType: accountType,
        tradingMode: accountType === 'paper' ? 'Paper Trading' : 'Live Trading',
        timestamp: new Date().toISOString()
      });
      
    } catch (error) {
      // Enhanced error handling with account type context
      handlePaperTradingError(error, accountType, res);
    }
  }
);
```

### Database Schema Considerations

```sql
-- Add account type tracking to relevant tables
ALTER TABLE portfolio_holdings ADD COLUMN account_type VARCHAR(10) DEFAULT 'paper';
ALTER TABLE trade_history ADD COLUMN account_type VARCHAR(10) DEFAULT 'paper';
ALTER TABLE performance_metrics ADD COLUMN account_type VARCHAR(10) DEFAULT 'paper';
ALTER TABLE risk_assessments ADD COLUMN account_type VARCHAR(10) DEFAULT 'paper';

-- Add indexes for efficient querying
CREATE INDEX idx_portfolio_holdings_account_type ON portfolio_holdings(user_id, account_type);
CREATE INDEX idx_trade_history_account_type ON trade_history(user_id, account_type);
CREATE INDEX idx_performance_metrics_account_type ON performance_metrics(user_id, account_type);
```

### Response Format Standardization

```javascript
// Standard success response format
{
  success: true,
  data: {}, // endpoint-specific data
  accountType: "paper|live",
  tradingMode: "Paper Trading|Live Trading",
  source: "alpaca|database|cache",
  responseTime: 1234,
  timestamp: "2025-07-25T19:54:46.295Z",
  
  // Paper trading specific fields
  paperTradingInfo: {
    isPaperAccount: true,
    virtualCash: 100000,
    restrictions: ["No real money risk", "Delayed market data"],
    benefits: ["Risk-free testing", "Strategy development"]
  }
}
```

## Security Considerations

### 1. **Access Control**
- Paper trading: Available to all users with Alpaca keys
- Live trading: Restricted to users with live API keys (not v1.0)
- Account type validation on every request

### 2. **Data Isolation**
- Strict separation of paper and live trading data
- Account type included in all database queries
- No cross-contamination between paper and live metrics

### 3. **Error Prevention**
- Clear paper/live mode indicators in UI
- Confirmation dialogs for live trading operations
- Paper trading limitations clearly communicated

## Testing Strategy

### 1. **Unit Tests**
- API key service paper trading methods
- Account type validation logic
- AlpacaService paper/live mode initialization

### 2. **Integration Tests**
- End-to-end paper trading flows
- Account type parameter validation
- Cross-endpoint consistency

### 3. **User Acceptance Tests**
- Paper trading user journey
- Account type switching workflows
- Error handling and recovery scenarios

## Rollout Plan

### Phase 1: Core Trading Functions (Week 1)
1. Implement enhanced API key service
2. Update trading routes with paper support
3. Add performance routes paper trading support

### Phase 2: Advanced Features (Week 2)
1. Risk management paper trading support
2. Backtest integration improvements
3. Trading strategies paper support

### Phase 3: Polish & Testing (Week 3)
1. Frontend UI/UX enhancements
2. Comprehensive testing and validation
3. Documentation and user guides

## Success Metrics

### Technical Metrics
- ✅ 100% of Alpaca-integrated endpoints support paper trading
- ✅ <200ms response time for paper trading operations
- ✅ 99.9% uptime for paper trading features

### User Experience Metrics
- ✅ Clear paper/live mode indication on all pages
- ✅ Zero accidental live trading from paper mode
- ✅ Seamless account type switching experience

### Business Metrics
- ✅ Increased user engagement with paper trading features
- ✅ Higher conversion from paper to live trading
- ✅ Reduced support tickets related to account confusion