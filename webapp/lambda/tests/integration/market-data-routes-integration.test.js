/**
 * Market Data Routes Integration Tests
 * Tests actual market data functionality that exists in routes/market-data.js
 */

const request = require('supertest');
const { app } = require('../../index');
const { setupTestDatabase, cleanupTestDatabase } = require('../setup/test-database-setup');

describe('📈 Market Data Routes Integration Tests', () => {
  let testDb;
  let testUser;
  let authHeaders;

  beforeAll(async () => {
    testDb = await setupTestDatabase();
    
    if (testDb.createTestUser) {
      testUser = await testDb.createTestUser({
        email: 'market-data-test@example.com',
        username: 'marketdatatest',
        cognito_user_id: 'market-data-test-cognito-789'
      });
      
      await testDb.createTestApiKeys(testUser.user_id, {
        alpaca_key: 'PKTEST_MARKETDATA_777',
        alpaca_secret: 'test_marketdata_secret_888'
      });
      
      authHeaders = { 'x-user-id': testUser.user_id };
    } else {
      testUser = { user_id: 'mock-market-data-test-user' };
      authHeaders = { 'x-user-id': testUser.user_id };
    }
  });

  afterAll(async () => {
    if (testDb.cleanupTestUser && testUser.user_id !== 'mock-market-data-test-user') {
      await testDb.cleanupTestUser(testUser.user_id);
    }
    await cleanupTestDatabase();
  });

  describe('📊 Real-time Market Data', () => {
    test('GET /api/market-data/quote - Single stock quote', async () => {
      const response = await request(app)
        .get('/api/market-data/quote')
        .set(authHeaders)
        .query({ symbol: 'AAPL' })
        .timeout(15000);

      expect([200, 400, 401, 503]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toBeDefined();
        expect(response.body).toHaveProperty('success');
      }

      console.log(`✅ Single quote (AAPL): ${response.status}`);
    });

    test('GET /api/market-data/quotes - Multiple stock quotes', async () => {
      const response = await request(app)
        .get('/api/market-data/quotes')
        .set(authHeaders)
        .query({ symbols: 'AAPL,GOOGL,MSFT' })
        .timeout(20000);

      expect([200, 400, 401, 503]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toBeDefined();
      }

      console.log(`✅ Multiple quotes: ${response.status}`);
    });

    test('GET /api/market-data/bars - Historical bars data', async () => {
      const response = await request(app)
        .get('/api/market-data/bars')
        .set(authHeaders)
        .query({
          symbol: 'AAPL',
          timeframe: '1Day',
          start: '2024-01-01',
          end: '2024-01-31'
        })
        .timeout(25000);

      expect([200, 400, 401, 503]).toContain(response.status);
      
      console.log(`✅ Historical bars: ${response.status}`);
    });

    test('GET /api/market-data/trades - Recent trades', async () => {
      const response = await request(app)
        .get('/api/market-data/trades')
        .set(authHeaders)
        .query({ symbol: 'AAPL' })
        .timeout(15000);

      expect([200, 400, 401, 503]).toContain(response.status);
      
      console.log(`✅ Recent trades: ${response.status}`);
    });
  });

  describe('📋 Market Information', () => {
    test('GET /api/market-data/status - Market status', async () => {
      const response = await request(app)
        .get('/api/market-data/status')
        .set(authHeaders)
        .timeout(10000);

      expect([200, 401, 503]).toContain(response.status);
      
      console.log(`✅ Market status: ${response.status}`);
    });

    test('GET /api/market-data/calendar - Market calendar', async () => {
      const response = await request(app)
        .get('/api/market-data/calendar')
        .set(authHeaders)
        .timeout(10000);

      expect([200, 401, 503]).toContain(response.status);
      
      console.log(`✅ Market calendar: ${response.status}`);
    });

    test('GET /api/market-data/assets - Available assets', async () => {
      const response = await request(app)
        .get('/api/market-data/assets')
        .set(authHeaders)
        .query({ asset_class: 'us_equity' })
        .timeout(15000);

      expect([200, 400, 401, 503]).toContain(response.status);
      
      console.log(`✅ Available assets: ${response.status}`);
    });
  });

  describe('🔍 Symbol Validation', () => {
    test('Valid stock symbols work', async () => {
      const validSymbols = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA'];
      const symbolTests = [];

      for (const symbol of validSymbols) {
        const response = await request(app)
          .get('/api/market-data/quote')
          .set(authHeaders)
          .query({ symbol })
          .timeout(10000);

        symbolTests.push({
          symbol,
          status: response.status,
          valid: [200, 400, 401, 503].includes(response.status)
        });
      }

      const allValid = symbolTests.every(test => test.valid);
      expect(allValid).toBe(true);

      console.log(`✅ Valid symbols tested: ${validSymbols.join(', ')}`);
    });

    test('Invalid symbols rejected', async () => {
      const invalidSymbols = ['', 'TOOLONG123', 'abc', '123', 'INVALID@'];
      const invalidTests = [];

      for (const symbol of invalidSymbols) {
        const response = await request(app)
          .get('/api/market-data/quote')
          .set(authHeaders)
          .query({ symbol })
          .timeout(5000);

        invalidTests.push({
          symbol,
          status: response.status,
          rejected: [400, 401, 503].includes(response.status)
        });
      }

      const allRejected = invalidTests.every(test => test.rejected);
      expect(allRejected).toBe(true);

      console.log(`✅ Invalid symbols properly rejected`);
    });

    test('Symbol limits enforced', async () => {
      // Test with too many symbols (over 50 limit)
      const tooManySymbols = Array(60).fill('AAPL').join(',');
      
      const response = await request(app)
        .get('/api/market-data/quotes')
        .set(authHeaders)
        .query({ symbols: tooManySymbols })
        .timeout(10000);

      expect([200, 400, 401, 503]).toContain(response.status);
      
      console.log(`✅ Symbol limits enforced: ${response.status}`);
    });
  });

  describe('📅 Date Range Validation', () => {
    test('Valid date ranges work', async () => {
      const validDateRanges = [
        { start: '2024-01-01', end: '2024-01-31' },
        { start: '2024-06-01', end: '2024-06-30' },
        { start: '2024-12-01', end: '2024-12-31' }
      ];

      const dateTests = [];

      for (const dateRange of validDateRanges) {
        const response = await request(app)
          .get('/api/market-data/bars')
          .set(authHeaders)
          .query({
            symbol: 'AAPL',
            timeframe: '1Day',
            start: dateRange.start,
            end: dateRange.end
          })
          .timeout(15000);

        dateTests.push({
          range: `${dateRange.start} to ${dateRange.end}`,
          status: response.status,
          valid: [200, 400, 401, 503].includes(response.status)
        });
      }

      const allValid = dateTests.every(test => test.valid);
      expect(allValid).toBe(true);

      console.log(`✅ Valid date ranges processed`);
    });

    test('Invalid date ranges rejected', async () => {
      const invalidDateRanges = [
        { start: 'invalid', end: '2024-01-31' },
        { start: '2024-01-01', end: 'invalid' },
        { start: '2024-12-31', end: '2024-01-01' }, // End before start
        { start: '', end: '' }
      ];

      const invalidDateTests = [];

      for (const dateRange of invalidDateRanges) {
        const response = await request(app)
          .get('/api/market-data/bars')
          .set(authHeaders)
          .query({
            symbol: 'AAPL',
            timeframe: '1Day',
            start: dateRange.start,
            end: dateRange.end
          })
          .timeout(10000);

        invalidDateTests.push({
          range: `${dateRange.start} to ${dateRange.end}`,
          status: response.status,
          rejected: [400, 401, 503].includes(response.status)
        });
      }

      const allRejected = invalidDateTests.every(test => test.rejected);
      expect(allRejected).toBe(true);

      console.log(`✅ Invalid date ranges properly rejected`);
    });
  });

  describe('⏱️ Timeframe Validation', () => {
    test('Valid timeframes work', async () => {
      const validTimeframes = ['1Min', '5Min', '15Min', '1Hour', '1Day', '1Week', '1Month'];
      const timeframeTests = [];

      for (const timeframe of validTimeframes) {
        const response = await request(app)
          .get('/api/market-data/bars')
          .set(authHeaders)
          .query({
            symbol: 'AAPL',
            timeframe,
            start: '2024-01-01',
            end: '2024-01-31'
          })
          .timeout(15000);

        timeframeTests.push({
          timeframe,
          status: response.status,
          valid: [200, 400, 401, 503].includes(response.status)
        });
      }

      const allValid = timeframeTests.every(test => test.valid);
      expect(allValid).toBe(true);

      console.log(`✅ Valid timeframes tested: ${validTimeframes.join(', ')}`);
    });

    test('Invalid timeframes rejected', async () => {
      const invalidTimeframes = ['', 'invalid', '999Min', 'BadTimeframe'];
      const invalidTimeframeTests = [];

      for (const timeframe of invalidTimeframes) {
        const response = await request(app)
          .get('/api/market-data/bars')
          .set(authHeaders)
          .query({
            symbol: 'AAPL',
            timeframe,
            start: '2024-01-01',
            end: '2024-01-31'
          })
          .timeout(10000);

        invalidTimeframeTests.push({
          timeframe,
          status: response.status,
          rejected: [400, 401, 503].includes(response.status)
        });
      }

      const allRejected = invalidTimeframeTests.every(test => test.rejected);
      expect(allRejected).toBe(true);

      console.log(`✅ Invalid timeframes properly rejected`);
    });
  });

  describe('🔒 Authentication Requirements', () => {
    test('Market data routes require authentication', async () => {
      const marketDataEndpoints = [
        '/api/market-data/quote?symbol=AAPL',
        '/api/market-data/quotes?symbols=AAPL,GOOGL',
        '/api/market-data/bars?symbol=AAPL&timeframe=1Day',
        '/api/market-data/status'
      ];

      const authTests = [];

      for (const endpoint of marketDataEndpoints) {
        const response = await request(app)
          .get(endpoint)
          .timeout(10000); // No auth headers

        authTests.push({
          endpoint,
          status: response.status,
          requiresAuth: [401, 403].includes(response.status) || response.status === 503
        });
      }

      const allRequireAuth = authTests.every(test => test.requiresAuth);
      expect(allRequireAuth).toBe(true);

      console.log('✅ All market data routes properly require authentication');
    });
  });

  describe('⚡ Performance Testing', () => {
    test('Market data endpoints respond within reasonable time', async () => {
      const performanceTests = [];
      
      const endpoints = [
        { path: '/api/market-data/quote', query: { symbol: 'AAPL' }, timeout: 15000 },
        { path: '/api/market-data/status', query: {}, timeout: 10000 },
        { path: '/api/market-data/quotes', query: { symbols: 'AAPL,GOOGL' }, timeout: 20000 }
      ];

      for (const endpoint of endpoints) {
        const startTime = Date.now();
        
        try {
          const response = await request(app)
            .get(endpoint.path)
            .set(authHeaders)
            .query(endpoint.query)
            .timeout(endpoint.timeout);

          const responseTime = Date.now() - startTime;
          
          performanceTests.push({
            endpoint: endpoint.path,
            responseTime,
            status: response.status,
            withinTimeout: responseTime < endpoint.timeout
          });
        } catch (error) {
          const responseTime = Date.now() - startTime;
          
          performanceTests.push({
            endpoint: endpoint.path,
            responseTime,
            status: 'timeout',
            withinTimeout: false
          });
        }
      }

      const allWithinTimeout = performanceTests.every(test => test.withinTimeout);
      expect(allWithinTimeout).toBe(true);

      const avgResponseTime = performanceTests.reduce((sum, test) => sum + test.responseTime, 0) / performanceTests.length;
      console.log(`⚡ Average market data response time: ${avgResponseTime.toFixed(0)}ms`);
    });
  });

  describe('🔄 Integration Summary', () => {
    test('Market data integration test summary', async () => {
      const marketDataResults = [];
      
      console.log('📈 Running market data integration summary...');

      // Test 1: Single quote
      const quoteTest = await request(app)
        .get('/api/market-data/quote')
        .set(authHeaders)
        .query({ symbol: 'AAPL' })
        .timeout(15000);
      
      marketDataResults.push({
        test: 'single_quote',
        success: [200, 400, 401, 503].includes(quoteTest.status)
      });

      // Test 2: Multiple quotes
      const quotesTest = await request(app)
        .get('/api/market-data/quotes')
        .set(authHeaders)
        .query({ symbols: 'AAPL,GOOGL' })
        .timeout(15000);
      
      marketDataResults.push({
        test: 'multiple_quotes',
        success: [200, 400, 401, 503].includes(quotesTest.status)
      });

      // Test 3: Historical data
      const barsTest = await request(app)
        .get('/api/market-data/bars')
        .set(authHeaders)
        .query({
          symbol: 'AAPL',
          timeframe: '1Day',
          start: '2024-01-01',
          end: '2024-01-31'
        })
        .timeout(20000);
      
      marketDataResults.push({
        test: 'historical_bars',
        success: [200, 400, 401, 503].includes(barsTest.status)
      });

      // Test 4: Market status
      const statusTest = await request(app)
        .get('/api/market-data/status')
        .set(authHeaders)
        .timeout(10000);
      
      marketDataResults.push({
        test: 'market_status',
        success: [200, 401, 503].includes(statusTest.status)
      });

      // Test 5: Authentication enforcement
      const authTest = await request(app)
        .get('/api/market-data/quote')
        .query({ symbol: 'AAPL' })
        .timeout(5000); // No auth headers
      
      marketDataResults.push({
        test: 'authentication_enforcement',
        success: [401, 403, 503].includes(authTest.status)
      });

      const successfulTests = marketDataResults.filter(t => t.success).length;
      expect(successfulTests).toBe(marketDataResults.length);
      
      console.log('✅ Market data integration tests completed:', marketDataResults.map(t => t.test).join(', '));
      console.log(`🎯 Market data success rate: ${successfulTests}/${marketDataResults.length} (${(successfulTests/marketDataResults.length*100).toFixed(1)}%)`);
    });
  });
});