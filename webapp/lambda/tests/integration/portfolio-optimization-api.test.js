/**
 * Portfolio Optimization API Integration Test
 * Verifies frontend can successfully consume the API response
 * Tests: API response structure, data types, field names, calculations
 */

const axios = require('axios');
const { Pool } = require('pg');

// Use local test API endpoint
const API_BASE_URL = 'http://localhost:3001';
const TEST_USER_ID = 'test-user-e2e-' + Date.now();

// ⛔ CRITICAL: Database connection MUST use test database, NEVER production
const dbUrl = process.env.DATABASE_URL || 'postgresql://postgres:password@localhost:5432/stocks_db';

// SAFETY CHECK: Prevent test from running against production database
if (!dbUrl.includes('test') && !dbUrl.includes('localhost') && !process.env.ALLOW_TEST_ON_PROD) {
  throw new Error(`
    ❌ CRITICAL SAFETY VIOLATION: This test file inserts FAKE DATA with Math.random()
    into the database. It MUST use a test database, not production.

    Current DATABASE_URL: ${dbUrl}

    This test CORRUPTS the database with synthetic stock scores and holdings.

    To fix:
    1. Set DATABASE_URL to a test database
    2. Or set ALLOW_TEST_ON_PROD=true only in development (NEVER in production)

    Current environment: ${process.env.NODE_ENV || 'development'}
  `);
}

const pool = new Pool({
  connectionString: dbUrl
});

describe('Portfolio Optimization API Integration Tests', () => {

  beforeAll(async () => {
    // ⛔ WARNING: This test inserts FAKE financial data (Math.random() scores)
    console.warn('⚠️ INTEGRATION TEST: Setting up fake test data - do NOT run in production');
    console.warn('⚠️ This test corrupts: stock_scores, portfolio_holdings with synthetic data');

    // Set up test data in database
    await setupTestData();
  });

  afterAll(async () => {
    // Clean up test data
    await cleanupTestData();
    await pool.end();
  });

  test('GET /api/portfolio-optimization returns required fields in response', async () => {
    const response = await axios.get(`${API_BASE_URL}/api/portfolio-optimization`, {
      params: {
        user_id: TEST_USER_ID,
        min_fit_score: 70,
        market_exposure: 50,
        limit: 15
      }
    });

    expect(response.status).toBe(200);
    const data = response.data;

    // Verify top-level structure
    expect(data).toHaveProperty('optimization_id');
    expect(data).toHaveProperty('timestamp');
    expect(data).toHaveProperty('portfolio_state');
    expect(data).toHaveProperty('sector_allocation');
    expect(data).toHaveProperty('recommended_trades');
    expect(data).toHaveProperty('portfolio_metrics');

    console.log('✅ API response contains all required top-level fields');
  });

  test('Portfolio state includes required metrics', async () => {
    const response = await axios.get(`${API_BASE_URL}/api/portfolio-optimization`, {
      params: {
        user_id: TEST_USER_ID,
        min_fit_score: 70,
        market_exposure: 50
      }
    });

    const portfolio = response.data.portfolio_state;

    // Verify portfolio metrics
    expect(portfolio).toHaveProperty('total_value');
    expect(portfolio).toHaveProperty('unrealized_pnl');
    expect(portfolio).toHaveProperty('unrealized_pnl_pct');
    expect(portfolio).toHaveProperty('composite_score');
    expect(portfolio).toHaveProperty('concentration_ratio');
    expect(portfolio).toHaveProperty('top_holdings');

    // Verify data types
    expect(typeof portfolio.total_value).toBe('number');
    expect(typeof portfolio.unrealized_pnl).toBe('number');
    expect(typeof portfolio.unrealized_pnl_pct).toBe('number');
    expect(typeof portfolio.composite_score).toBe('number');
    expect(typeof portfolio.concentration_ratio).toBe('number');
    expect(Array.isArray(portfolio.top_holdings)).toBe(true);

    console.log('✅ Portfolio state has correct structure and data types');
  });

  test('Top holdings have required fields for display', async () => {
    const response = await axios.get(`${API_BASE_URL}/api/portfolio-optimization`, {
      params: {
        user_id: TEST_USER_ID,
        min_fit_score: 70,
        market_exposure: 50
      }
    });

    const topHoldings = response.data.portfolio_state.top_holdings;

    if (topHoldings.length > 0) {
      const holding = topHoldings[0];

      // Verify required fields for table display
      expect(holding).toHaveProperty('symbol');
      expect(holding).toHaveProperty('quantity');
      expect(holding).toHaveProperty('current_price');
      expect(holding).toHaveProperty('market_value');
      expect(holding).toHaveProperty('unrealized_gain_pct');
      expect(holding).toHaveProperty('weight_pct');
      expect(holding).toHaveProperty('composite_score');

      // Verify data types
      expect(typeof holding.symbol).toBe('string');
      expect(typeof holding.quantity).toBe('number');
      expect(typeof holding.current_price).toBe('number');
      expect(typeof holding.market_value).toBe('number');

      console.log('✅ Top holdings have all required fields for display');
    }
  });

  test('Sector allocation has correct structure and calculations', async () => {
    const response = await axios.get(`${API_BASE_URL}/api/portfolio-optimization`, {
      params: {
        user_id: TEST_USER_ID,
        min_fit_score: 70,
        market_exposure: 50
      }
    });

    const sectors = response.data.sector_allocation;
    expect(Array.isArray(sectors)).toBe(true);
    expect(sectors.length).toBeGreaterThan(0);

    let totalPct = 0;

    sectors.forEach(sector => {
      // Verify required fields
      expect(sector).toHaveProperty('sector');
      expect(sector).toHaveProperty('current_pct');
      expect(sector).toHaveProperty('target_pct');
      expect(sector).toHaveProperty('drift_pct');

      // Verify data types
      expect(typeof sector.sector).toBe('string');
      expect(typeof sector.current_pct).toBe('number');
      expect(typeof sector.target_pct).toBe('number');
      expect(typeof sector.drift_pct).toBe('number');

      // Verify drift calculation
      const calculatedDrift = sector.current_pct - sector.target_pct;
      expect(Math.abs(sector.drift_pct - calculatedDrift)).toBeLessThan(0.01);

      totalPct += sector.current_pct;
    });

    // Current allocation should sum to approximately 100%
    expect(Math.abs(totalPct - 100)).toBeLessThan(1);

    console.log('✅ Sector allocation has correct structure and calculations');
  });

  test('Recommended trades have correct structure', async () => {
    const response = await axios.get(`${API_BASE_URL}/api/portfolio-optimization`, {
      params: {
        user_id: TEST_USER_ID,
        min_fit_score: 70,
        market_exposure: 50,
        limit: 15
      }
    });

    const trades = response.data.recommended_trades;
    expect(Array.isArray(trades)).toBe(true);

    if (trades.length > 0) {
      const trade = trades[0];

      // Verify required fields for table display
      expect(trade).toHaveProperty('rank');
      expect(trade).toHaveProperty('action');
      expect(trade).toHaveProperty('symbol');
      expect(trade).toHaveProperty('fit_score');
      expect(trade).toHaveProperty('rationale');
      expect(trade).toHaveProperty('suggested_amount');

      // Verify data types
      expect(typeof trade.rank).toBe('number');
      expect(['BUY', 'SELL', 'REDUCE', 'HOLD']).toContain(trade.action);
      expect(typeof trade.symbol).toBe('string');
      expect(typeof trade.fit_score).toBe('number');
      expect(typeof trade.rationale).toBe('string');
      expect(typeof trade.suggested_amount).toBe('number');

      // Verify fit score is in valid range
      expect(trade.fit_score).toBeGreaterThanOrEqual(0);
      expect(trade.fit_score).toBeLessThanOrEqual(100);

      console.log('✅ Recommended trades have correct structure');
    }
  });

  test('Portfolio metrics are consistent and valid', async () => {
    const response = await axios.get(`${API_BASE_URL}/api/portfolio-optimization`, {
      params: {
        user_id: TEST_USER_ID,
        min_fit_score: 70,
        market_exposure: 50
      }
    });

    const metrics = response.data.portfolio_metrics;
    expect(metrics).toHaveProperty('current');
    expect(metrics).toHaveProperty('projected');

    const current = metrics.current;
    const projected = metrics.projected;

    // Verify current metrics
    expect(current).toHaveProperty('avg_composite_score');
    expect(current).toHaveProperty('concentration_ratio');
    expect(current).toHaveProperty('sector_diversification');
    expect(current).toHaveProperty('estimated_sharpe_ratio');
    expect(current).toHaveProperty('correlation_to_market');

    // Verify projected metrics
    expect(projected).toHaveProperty('avg_composite_score');
    expect(projected).toHaveProperty('concentration_ratio');
    expect(projected).toHaveProperty('sector_diversification');
    expect(projected).toHaveProperty('estimated_sharpe_ratio');
    expect(projected).toHaveProperty('correlation_to_market');

    // Verify metrics are numbers
    Object.values(current).forEach(val => {
      if (val !== null) {
        expect(typeof val).toBe('number');
      }
    });

    Object.values(projected).forEach(val => {
      if (val !== null) {
        expect(typeof val).toBe('number');
      }
    });

    console.log('✅ Portfolio metrics are consistent and valid');
  });

  test('No null or undefined scores in recommendations', async () => {
    const response = await axios.get(`${API_BASE_URL}/api/portfolio-optimization`, {
      params: {
        user_id: TEST_USER_ID,
        min_fit_score: 70,
        market_exposure: 50,
        limit: 15
      }
    });

    const trades = response.data.recommended_trades;

    trades.forEach((trade, idx) => {
      expect(trade.fit_score).not.toBeNull();
      expect(trade.fit_score).not.toBeUndefined();
      expect(trade.fit_score).not.toBeNaN();

      // BUY trades should have positive fit scores
      if (trade.action === 'BUY') {
        expect(trade.fit_score).toBeGreaterThanOrEqual(70);
      }

      // REDUCE trades should have rationale
      if (trade.action === 'REDUCE') {
        expect(trade.rationale).toBeTruthy();
      }
    });

    console.log('✅ No null or undefined scores in recommendations');
  });

  test('Optimization ID is valid for POST requests', async () => {
    const getResponse = await axios.get(`${API_BASE_URL}/api/portfolio-optimization`, {
      params: {
        user_id: TEST_USER_ID,
        min_fit_score: 70,
        market_exposure: 50
      }
    });

    const optimizationId = getResponse.data.optimization_id;
    expect(optimizationId).toBeTruthy();
    expect(typeof optimizationId).toBe('string');

    // Try to use the ID in a POST request
    const trades = getResponse.data.recommended_trades.filter(t => t.action === 'BUY').slice(0, 2);

    if (trades.length > 0) {
      const postResponse = await axios.post(`${API_BASE_URL}/api/portfolio-optimization/apply`, {
        user_id: TEST_USER_ID,
        optimization_id: optimizationId,
        trades_to_execute: trades.map(t => ({
          symbol: t.symbol,
          action: t.action,
          amount: t.suggested_amount
        }))
      });

      expect(postResponse.status).toBe(200);
      expect(postResponse.data).toHaveProperty('success');
      expect(postResponse.data).toHaveProperty('executed_trades');

      console.log('✅ Optimization ID works for POST requests');
    }
  });

  // Helper functions
  async function setupTestData() {
    try {
      console.log('Setting up test data...');

      const client = await pool.connect();

      try {
        // Create test company profiles
        const symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'];
        const sectors = ['tech', 'tech', 'tech', 'consumer', 'consumer'];

        for (let i = 0; i < symbols.length; i++) {
          await client.query(
            `INSERT INTO company_profile (ticker, short_name, sector)
             VALUES ($1, $2, $3)
             ON CONFLICT (ticker) DO UPDATE
             SET short_name = EXCLUDED.short_name, sector = EXCLUDED.sector`,
            [symbols[i], symbols[i] + ' Inc', sectors[i]]
          );
        }

        // Create test stock scores
        for (const symbol of symbols) {
          await client.query(
            `INSERT INTO stock_scores (symbol, composite_score, momentum_score, value_score, quality_score,
                                       growth_score, stability_score, sentiment_score, positioning_score,
                                       current_price, volume_avg_30d)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
             ON CONFLICT (symbol) DO UPDATE
             SET composite_score = EXCLUDED.composite_score, current_price = EXCLUDED.current_price`,
            [
              symbol,
              75 + Math.random() * 15,  // composite_score 75-90
              70 + Math.random() * 20,  // momentum_score
              65 + Math.random() * 20,  // value_score
              80 + Math.random() * 15,  // quality_score
              70 + Math.random() * 20,  // growth_score
              75 + Math.random() * 20,  // stability_score
              70 + Math.random() * 20,  // sentiment_score
              65 + Math.random() * 25,  // positioning_score
              100 + Math.random() * 200, // current_price
              1000000 + Math.random() * 5000000 // volume_avg_30d
            ]
          );
        }

        // Create test portfolio holdings
        for (const symbol of symbols) {
          await client.query(
            `INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price,
                                            market_value, unrealized_gain, unrealized_gain_pct)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
             ON CONFLICT (user_id, symbol) DO UPDATE
             SET quantity = EXCLUDED.quantity, current_price = EXCLUDED.current_price`,
            [
              TEST_USER_ID,
              symbol,
              Math.floor(10 + Math.random() * 90), // quantity
              100 + Math.random() * 50,  // average_cost
              120 + Math.random() * 100, // current_price
              0,  // market_value (calculated)
              1000 + Math.random() * 5000, // unrealized_gain
              5 + Math.random() * 15  // unrealized_gain_pct
            ]
          );
        }

        console.log('✅ Test data created successfully');
      } finally {
        client.release();
      }
    } catch (error) {
      console.error('Error setting up test data:', error.message);
    }
  }

  async function cleanupTestData() {
    try {
      console.log('Cleaning up test data...');

      const client = await pool.connect();

      try {
        await client.query('DELETE FROM portfolio_holdings WHERE user_id = $1', [TEST_USER_ID]);
        console.log('✅ Test data cleaned up');
      } finally {
        client.release();
      }
    } catch (error) {
      console.error('Error cleaning up test data:', error.message);
    }
  }
});
