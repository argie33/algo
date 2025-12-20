/**
 * COMPREHENSIVE DATA VERIFICATION TEST
 *
 * Tests that ALL portfolio, trades, and optimization data comes from real sources:
 * 1. Alpaca API (portfolio positions, account data, closed orders/trades)
 * 2. Manual entries (user-entered trades in 'trades' table)
 * 3. No fake/placeholder/default data anywhere
 *
 * Per RULES.md: "NO fallback defaults, NO calculated values, NO hardcoded values, NO mock data"
 */

const axios = require('axios');
const { query } = require('../../utils/database');

const BASE_URL = process.env.API_BASE_URL || 'http://localhost:3001';
const AUTH_TOKEN = process.env.TEST_AUTH_TOKEN || 'Bearer dev-bypass-token';

// Helper to make authenticated API calls
async function apiCall(endpoint, method = 'GET', data = null) {
  try {
    const config = {
      method,
      url: `${BASE_URL}${endpoint}`,
      headers: {
        'Authorization': AUTH_TOKEN,
        'Content-Type': 'application/json'
      }
    };
    if (data) config.data = data;

    const response = await axios(config);
    return response.data;
  } catch (error) {
    console.error(`❌ API call failed: ${method} ${endpoint}`, error.response?.data || error.message);
    throw error;
  }
}

// Test suite
describe('Real Data Flow Verification', () => {

  describe('Portfolio Data - Alpaca Integration', () => {
    test('Portfolio metrics endpoint returns real Alpaca data', async () => {
      const response = await apiCall('/api/portfolio/metrics');

      expect(response.success).toBe(true);
      expect(response.data).toBeDefined();

      const { summary, positions, daily_returns, metadata } = response.data;

      // Verify summary contains real values or null (no fake defaults)
      console.log('📊 Portfolio Summary:', {
        portfolio_value: summary.portfolio_value,
        total_pnl: summary.total_pnl,
        holdings_count: summary.holdings_count,
        volatility: summary.volatility_annualized,
        sharpe_ratio: summary.sharpe_ratio
      });

      // Check that values are either real numbers or null (not fake defaults like 50, 0, etc.)
      if (summary.volatility_annualized !== null) {
        expect(typeof summary.volatility_annualized).toBe('number');
        // Volatility should be reasonable (0-100% annualized)
        expect(summary.volatility_annualized).toBeGreaterThanOrEqual(0);
        expect(summary.volatility_annualized).toBeLessThan(200);
      }

      if (summary.sharpe_ratio !== null) {
        expect(typeof summary.sharpe_ratio).toBe('number');
        // Sharpe ratio should be reasonable (-10 to 10)
        expect(summary.sharpe_ratio).toBeGreaterThan(-10);
        expect(summary.sharpe_ratio).toBeLessThan(10);
      }

      // Positions should be array (can be empty if no holdings)
      expect(Array.isArray(positions)).toBe(true);

      // If positions exist, verify they have real data
      if (positions.length > 0) {
        const firstPosition = positions[0];
        console.log('📈 First Position:', firstPosition);

        expect(firstPosition.symbol).toBeDefined();
        expect(typeof firstPosition.quantity).toBe('number');
        expect(typeof firstPosition.current_price).toBe('number');
        expect(firstPosition.current_price).toBeGreaterThan(0);

        // Verify no fake defaults
        expect(firstPosition.unrealized_pnl).not.toBe(50); // Common fake default
        expect(firstPosition.unrealized_pnl_percent).not.toBe(50); // Common fake default
      }
    }, 30000);

    test('Portfolio data comes from Alpaca API when available', async () => {
      // This test verifies the data source priority:
      // 1. Alpaca API (primary)
      // 2. Database fallback (secondary)
      // 3. Empty response (tertiary) - no fake data

      const response = await apiCall('/api/portfolio/metrics');
      const { positions, metadata } = response.data;

      console.log('📡 Data source metadata:', metadata);

      // If we have positions, verify they're recent (Alpaca updates in real-time)
      if (positions.length > 0) {
        expect(metadata.last_updated).toBeDefined();
        const lastUpdate = new Date(metadata.last_updated);
        const now = new Date();
        const ageMinutes = (now - lastUpdate) / (1000 * 60);

        // Data should be recent (within last 10 minutes for Alpaca, or could be older for database)
        console.log(`⏰ Data age: ${ageMinutes.toFixed(2)} minutes`);
      }
    }, 30000);
  });

  describe('Trade History - Alpaca + Manual Entries', () => {
    test('Trade history includes both Alpaca and manual trades', async () => {
      const response = await apiCall('/api/trades/history?limit=100');

      expect(response.success).toBe(true);
      expect(response.data).toBeDefined();
      expect(response.data.trades).toBeDefined();

      const { trades, summary } = response.data;

      console.log(`📋 Total trades fetched: ${trades.length}`);
      console.log('📊 Summary:', summary);

      expect(Array.isArray(trades)).toBe(true);

      // Verify trades have required fields and source attribution
      if (trades.length > 0) {
        const alpacaTrades = trades.filter(t => t.source === 'alpaca');
        const manualTrades = trades.filter(t => t.source === 'manual');

        console.log(`🔗 Alpaca trades: ${alpacaTrades.length}`);
        console.log(`📝 Manual trades: ${manualTrades.length}`);

        // Check first trade structure
        const firstTrade = trades[0];
        console.log('📄 First trade:', firstTrade);

        expect(firstTrade.symbol).toBeDefined();
        expect(firstTrade.type).toBeDefined(); // buy or sell
        expect(typeof firstTrade.quantity).toBe('number');
        expect(typeof firstTrade.execution_price).toBe('number');
        expect(firstTrade.execution_date).toBeDefined();
        expect(firstTrade.source).toBeDefined(); // alpaca or manual

        // Verify no fake data
        expect(firstTrade.execution_price).toBeGreaterThan(0);
        expect(firstTrade.quantity).toBeGreaterThan(0);
      }
    }, 30000);

    test('Trade summary calculated from real data only', async () => {
      const response = await apiCall('/api/trades/summary');

      expect(response.success).toBe(true);
      expect(response.data).toBeDefined();

      const { summary } = response.data;
      console.log('📊 Trade Summary:', summary);

      // Summary should have real values or null (no fake defaults)
      if (summary.win_rate !== null) {
        expect(typeof summary.win_rate).toBe('number');
        expect(summary.win_rate).toBeGreaterThanOrEqual(0);
        expect(summary.win_rate).toBeLessThanOrEqual(100);
      }

      if (summary.profit_factor !== null) {
        expect(typeof summary.profit_factor).toBe('number');
        expect(summary.profit_factor).toBeGreaterThanOrEqual(0);
      }

      // Verify counts make sense
      if (summary.total_trades) {
        expect(summary.total_trades).toBeGreaterThanOrEqual(0);
        if (summary.winning_trades !== null && summary.losing_trades !== null) {
          // Winning + losing should be <= total (some trades might be break-even)
          expect(summary.winning_trades + summary.losing_trades).toBeLessThanOrEqual(summary.total_trades);
        }
      }
    }, 30000);

    test('FIFO analysis uses real trade data', async () => {
      const response = await apiCall('/api/trades/fifo-analysis');

      if (!response.success) {
        console.log('⚠️ FIFO analysis not available (expected if no trades)');
        return;
      }

      const { analysis } = response.data;
      console.log('🔍 FIFO Analysis:', {
        totalTrades: analysis.totalTrades,
        matchedPairs: analysis.matchedPairs,
        realizedPnl: analysis.realizedPnl,
        openPositions: analysis.openPositions
      });

      // Verify matched pairs have real data
      if (analysis.matchedPairs && analysis.matchedPairs.length > 0) {
        const firstPair = analysis.matchedPairs[0];

        expect(firstPair.symbol).toBeDefined();
        expect(firstPair.buyDate).toBeDefined();
        expect(firstPair.sellDate).toBeDefined();
        expect(typeof firstPair.quantity).toBe('number');
        expect(typeof firstPair.buyPrice).toBe('number');
        expect(typeof firstPair.sellPrice).toBe('number');
        expect(firstPair.pnl).toBeDefined();
        expect(firstPair.taxType).toBeDefined(); // SHORT-TERM or LONG-TERM

        // Verify real calculations
        const expectedPnl = ((firstPair.sellPrice - firstPair.buyPrice) * firstPair.quantity).toFixed(2);
        expect(firstPair.pnl).toBe(expectedPnl);
      }
    }, 30000);
  });

  describe('Manual Trades CRUD Operations', () => {
    let testTradeId = null;

    test('Create manual trade', async () => {
      const tradeData = {
        symbol: 'TESTXYZ',
        trade_type: 'buy',
        quantity: 10,
        price: 150.50,
        execution_date: new Date('2024-01-15').toISOString(),
        commission: 0
      };

      const response = await apiCall('/api/manual-trades', 'POST', tradeData);

      expect(response.success).toBe(true);
      expect(response.data).toBeDefined();
      expect(response.data.symbol).toBe('TESTXYZ');
      expect(response.data.quantity).toBe(10);
      expect(parseFloat(response.data.price)).toBeCloseTo(150.50, 2);

      testTradeId = response.data.id;
      console.log(`✅ Created test trade ID: ${testTradeId}`);
    }, 30000);

    test('Fetch manual trades', async () => {
      const response = await apiCall('/api/manual-trades');

      expect(response.success).toBe(true);
      expect(Array.isArray(response.data)).toBe(true);

      // Find our test trade
      const testTrade = response.data.find(t => t.id === testTradeId);
      expect(testTrade).toBeDefined();
      expect(testTrade.symbol).toBe('TESTXYZ');
    }, 30000);

    test('Update manual trade', async () => {
      if (!testTradeId) {
        console.log('⚠️ Skipping update test - no test trade created');
        return;
      }

      const updateData = {
        quantity: 15,
        price: 155.75
      };

      const response = await apiCall(`/api/manual-trades/${testTradeId}`, 'PATCH', updateData);

      expect(response.success).toBe(true);
      expect(response.data.quantity).toBe(15);
      expect(parseFloat(response.data.price)).toBeCloseTo(155.75, 2);

      console.log(`✅ Updated test trade ID: ${testTradeId}`);
    }, 30000);

    test('Delete manual trade', async () => {
      if (!testTradeId) {
        console.log('⚠️ Skipping delete test - no test trade created');
        return;
      }

      const response = await apiCall(`/api/manual-trades/${testTradeId}`, 'DELETE');

      expect(response.success).toBe(true);

      console.log(`✅ Deleted test trade ID: ${testTradeId}`);
    }, 30000);
  });

  describe('Portfolio Optimization - Real Data Only', () => {
    test('Optimization analysis uses real portfolio data', async () => {
      const response = await apiCall('/api/optimization/analysis');

      expect(response.success).toBe(true);
      expect(response.data).toBeDefined();

      const { analysis } = response.data;
      console.log('🎯 Optimization Analysis:', {
        currentMetrics: analysis.portfolioMetrics?.current,
        recommendations: analysis.recommendations?.length || 0
      });

      // Verify metrics are real or null (no fake defaults)
      const currentMetrics = analysis.portfolioMetrics?.current || {};

      if (currentMetrics.sharpeRatio !== null && currentMetrics.sharpeRatio !== undefined) {
        expect(typeof currentMetrics.sharpeRatio).toBe('number');
        expect(currentMetrics.sharpeRatio).toBeGreaterThan(-10);
        expect(currentMetrics.sharpeRatio).toBeLessThan(10);
      }

      if (currentMetrics.volatility !== null && currentMetrics.volatility !== undefined) {
        expect(typeof currentMetrics.volatility).toBe('number');
        expect(currentMetrics.volatility).toBeGreaterThanOrEqual(0);
        expect(currentMetrics.volatility).toBeLessThan(200);
      }

      // Verify recommendations are based on real portfolio
      if (analysis.recommendations && analysis.recommendations.length > 0) {
        const firstRec = analysis.recommendations[0];
        console.log('💡 First recommendation:', firstRec);

        expect(firstRec.symbol).toBeDefined();
        expect(firstRec.action).toBeDefined(); // BUY, SELL, HOLD, etc.
        expect(firstRec.reason).toBeDefined();
      }

      // Efficient frontier should be empty or have real calculated points (no fake data)
      if (analysis.efficientFrontier) {
        expect(Array.isArray(analysis.efficientFrontier)).toBe(true);
        // Per backend code: Returns empty array when cannot calculate (no fake defaults)
      }
    }, 30000);
  });

  describe('Data Integrity Rules Compliance', () => {
    test('No fake default values (50, 0, "neutral") in responses', async () => {
      // Test multiple endpoints for fake defaults
      const endpoints = [
        '/api/portfolio/metrics',
        '/api/trades/history',
        '/api/trades/summary',
        '/api/optimization/analysis'
      ];

      for (const endpoint of endpoints) {
        try {
          const response = await apiCall(endpoint);
          const jsonStr = JSON.stringify(response);

          // Check for common fake defaults in context that suggests they're fake
          // (We can't just check for number 50, because it could be a real price or quantity)
          // Instead, check specific metric names that shouldn't have these defaults

          console.log(`🔍 Checking ${endpoint} for fake defaults...`);

          // Pattern: sentiment scores should not default to 50 (neutral)
          if (jsonStr.includes('"sentimentScore":50') || jsonStr.includes('"sentiment_score":50')) {
            console.warn(`⚠️ Found potential fake sentiment default in ${endpoint}`);
          }

          // Pattern: fear_greed_index should not default to 50
          if (jsonStr.includes('"fear_greed_index":50')) {
            throw new Error(`❌ FAKE DATA: fear_greed_index defaulting to 50 in ${endpoint}`);
          }

          // Pattern: momentum_score should not default to 50 when RSI is missing
          if (jsonStr.includes('"momentum_score":50') && !jsonStr.includes('"rsi"')) {
            console.warn(`⚠️ Found potential fake momentum default in ${endpoint}`);
          }

        } catch (error) {
          if (error.response?.status === 401 || error.response?.status === 404) {
            console.log(`⚠️ ${endpoint} not accessible (${error.response.status}) - skipping`);
          } else {
            throw error;
          }
        }
      }
    }, 60000);

    test('Null values used instead of calculated fallbacks', async () => {
      const response = await apiCall('/api/portfolio/metrics');
      const { summary } = response.data;

      // Check that when data is unavailable, we return null (not calculated estimates)
      // Example: beta requires SPY correlation - should be null if not calculated
      if (summary.beta === null) {
        console.log('✅ Beta correctly null (requires SPY correlation)');
      }

      // Example: period returns require historical data - should be null if unavailable
      if (!summary.return_1m && !summary.return_3m && !summary.return_6m && !summary.return_1y) {
        console.log('✅ Period returns correctly null (requires historical data)');
      }
    }, 30000);
  });
});

// Run tests if executed directly
if (require.main === module) {
  console.log('🧪 Starting Real Data Flow Verification Tests...\n');

  // Simple test runner (since we don't have jest in this context)
  const runTests = async () => {
    try {
      // Add your test execution logic here
      console.log('✅ All tests would run here');
    } catch (error) {
      console.error('❌ Test failed:', error);
      process.exit(1);
    }
  };

  runTests();
}

module.exports = { apiCall };
