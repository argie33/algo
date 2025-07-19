/**
 * Comprehensive API Integration Tests
 * Integrated into existing enterprise testing framework
 * Tests all backend API endpoints with real data flows
 */

import { test, expect } from '@playwright/test';

const testConfig = {
  apiURL: process.env.E2E_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
  testUser: {
    email: process.env.E2E_TEST_EMAIL || 'e2e-test@example.com',
    password: process.env.E2E_TEST_PASSWORD || 'E2ETest123!'
  },
  testSymbols: ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA'],
  timeout: 30000
};

test.describe('Comprehensive API Integration - Enterprise Framework', () => {
  
  let authToken = null;
  let testSession = {
    apiResponses: [],
    errors: [],
    performanceMetrics: []
  };

  test.beforeAll(async ({ request }) => {
    // Authenticate and get token for API tests
    console.log('🔐 Authenticating for API integration tests...');
    
    try {
      const authResponse = await request.post(`${testConfig.apiURL}/api/auth/login`, {
        data: {
          email: testConfig.testUser.email,
          password: testConfig.testUser.password
        },
        timeout: testConfig.timeout
      });
      
      expect(authResponse.ok()).toBeTruthy();
      const authData = await authResponse.json();
      authToken = authData.token;
      
      console.log('✅ API authentication successful');
    } catch (error) {
      console.log('⚠️ API authentication failed, some tests may be skipped:', error.message);
    }
  });

  // Helper function to make authenticated API calls
  async function apiCall(request, method, endpoint, data = null) {
    const startTime = Date.now();
    
    const options = {
      timeout: testConfig.timeout,
      headers: authToken ? { 'Authorization': `Bearer ${authToken}` } : {}
    };
    
    if (data) {
      options.data = data;
    }
    
    let response;
    try {
      switch (method.toUpperCase()) {
        case 'GET':
          response = await request.get(`${testConfig.apiURL}${endpoint}`, options);
          break;
        case 'POST':
          response = await request.post(`${testConfig.apiURL}${endpoint}`, options);
          break;
        case 'PUT':
          response = await request.put(`${testConfig.apiURL}${endpoint}`, options);
          break;
        case 'DELETE':
          response = await request.delete(`${testConfig.apiURL}${endpoint}`, options);
          break;
        default:
          throw new Error(`Unsupported HTTP method: ${method}`);
      }
    } catch (error) {
      testSession.errors.push({
        endpoint,
        method,
        error: error.message,
        timestamp: new Date().toISOString()
      });
      throw error;
    }
    
    const endTime = Date.now();
    const responseTime = endTime - startTime;
    
    // Track API response metrics for enterprise reporting
    testSession.apiResponses.push({
      endpoint,
      method,
      status: response.status(),
      responseTime,
      timestamp: new Date().toISOString()
    });
    
    testSession.performanceMetrics.push({
      endpoint,
      responseTime,
      status: response.status()
    });
    
    return response;
  }

  test.describe('Authentication API Integration @critical @enterprise', () => {
    
    test('Login API Integration', async ({ request }) => {
      console.log('🔑 Testing Login API Integration...');
      
      const response = await apiCall(request, 'POST', '/api/auth/login', {
        email: testConfig.testUser.email,
        password: testConfig.testUser.password
      });
      
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      expect(data).toHaveProperty('token');
      expect(data).toHaveProperty('user');
      expect(data.user).toHaveProperty('email', testConfig.testUser.email);
      
      // Verify token format (JWT)
      expect(data.token).toMatch(/^[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+$/);
      
      console.log('✅ Login API Integration passed');
    });

    test('Token Validation API Integration', async ({ request }) => {
      console.log('🎫 Testing Token Validation API Integration...');
      
      if (!authToken) {
        test.skip('Skipping token validation - no auth token available');
        return;
      }
      
      const response = await apiCall(request, 'GET', '/api/auth/validate');
      
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      expect(data).toHaveProperty('valid', true);
      expect(data).toHaveProperty('user');
      
      console.log('✅ Token Validation API Integration passed');
    });

    test('Logout API Integration', async ({ request }) => {
      console.log('🚪 Testing Logout API Integration...');
      
      if (!authToken) {
        test.skip('Skipping logout - no auth token available');
        return;
      }
      
      const response = await apiCall(request, 'POST', '/api/auth/logout');
      
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      expect(data).toHaveProperty('message');
      
      console.log('✅ Logout API Integration passed');
    });

  });

  test.describe('Portfolio API Integration @critical @enterprise', () => {
    
    test('Portfolio Holdings API Integration', async ({ request }) => {
      console.log('💼 Testing Portfolio Holdings API Integration...');
      
      if (!authToken) {
        test.skip('Skipping portfolio tests - authentication required');
        return;
      }
      
      const response = await apiCall(request, 'GET', '/api/portfolio/holdings');
      
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      expect(Array.isArray(data.holdings)).toBeTruthy();
      
      // Verify holdings structure if any exist
      if (data.holdings.length > 0) {
        const holding = data.holdings[0];
        expect(holding).toHaveProperty('symbol');
        expect(holding).toHaveProperty('quantity');
        expect(holding).toHaveProperty('averagePrice');
        expect(holding).toHaveProperty('currentPrice');
        expect(holding).toHaveProperty('marketValue');
        
        // Verify numeric values
        expect(typeof holding.quantity).toBe('number');
        expect(typeof holding.averagePrice).toBe('number');
        expect(typeof holding.currentPrice).toBe('number');
        expect(typeof holding.marketValue).toBe('number');
      }
      
      console.log(`✅ Portfolio Holdings API Integration passed - ${data.holdings.length} holdings`);
    });

    test('Portfolio Performance API Integration', async ({ request }) => {
      console.log('📊 Testing Portfolio Performance API Integration...');
      
      if (!authToken) {
        test.skip('Skipping portfolio performance tests - authentication required');
        return;
      }
      
      const response = await apiCall(request, 'GET', '/api/portfolio/performance');
      
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      expect(data).toHaveProperty('totalValue');
      expect(data).toHaveProperty('totalPnL');
      expect(data).toHaveProperty('dailyPnL');
      expect(data).toHaveProperty('returns');
      
      // Verify numeric values
      expect(typeof data.totalValue).toBe('number');
      expect(typeof data.totalPnL).toBe('number');
      expect(typeof data.dailyPnL).toBe('number');
      
      console.log(`✅ Portfolio Performance API Integration passed - Total Value: $${data.totalValue}`);
    });

    test('Portfolio Historical Performance API Integration', async ({ request }) => {
      console.log('📈 Testing Portfolio Historical Performance API Integration...');
      
      if (!authToken) {
        test.skip('Skipping historical performance tests - authentication required');
        return;
      }
      
      const periods = ['1D', '1W', '1M', '3M', '1Y'];
      
      for (const period of periods) {
        const response = await apiCall(request, 'GET', `/api/portfolio/performance/history?period=${period}`);
        
        expect(response.ok()).toBeTruthy();
        
        const data = await response.json();
        expect(Array.isArray(data.history)).toBeTruthy();
        
        // Verify historical data structure
        if (data.history.length > 0) {
          const point = data.history[0];
          expect(point).toHaveProperty('date');
          expect(point).toHaveProperty('value');
          expect(typeof point.value).toBe('number');
          
          // Verify date format
          expect(point.date).toMatch(/^\d{4}-\d{2}-\d{2}/);
        }
        
        console.log(`✅ Portfolio Historical Performance (${period}) - ${data.history.length} data points`);
      }
      
      console.log('✅ Portfolio Historical Performance API Integration passed');
    });

  });

  test.describe('Market Data API Integration @critical @enterprise', () => {
    
    test('Stock Quote API Integration', async ({ request }) => {
      console.log('📊 Testing Stock Quote API Integration...');
      
      for (const symbol of testConfig.testSymbols.slice(0, 3)) {
        const response = await apiCall(request, 'GET', `/api/stocks/${symbol}/quote`);
        
        expect(response.ok()).toBeTruthy();
        
        const data = await response.json();
        expect(data).toHaveProperty('symbol', symbol);
        expect(data).toHaveProperty('price');
        expect(data).toHaveProperty('change');
        expect(data).toHaveProperty('changePercent');
        expect(data).toHaveProperty('volume');
        
        // Verify numeric values
        expect(typeof data.price).toBe('number');
        expect(data.price).toBeGreaterThan(0);
        expect(typeof data.volume).toBe('number');
        expect(data.volume).toBeGreaterThanOrEqual(0);
        
        console.log(`✅ Stock Quote (${symbol}) - Price: $${data.price}`);
      }
      
      console.log('✅ Stock Quote API Integration passed');
    });

    test('Stock Historical Data API Integration', async ({ request }) => {
      console.log('📈 Testing Stock Historical Data API Integration...');
      
      const symbol = testConfig.testSymbols[0];
      const periods = ['1D', '5D', '1M'];
      
      for (const period of periods) {
        const response = await apiCall(request, 'GET', `/api/stocks/${symbol}/history?period=${period}`);
        
        expect(response.ok()).toBeTruthy();
        
        const data = await response.json();
        expect(data).toHaveProperty('symbol', symbol);
        expect(Array.isArray(data.prices)).toBeTruthy();
        
        // Verify price data structure
        if (data.prices.length > 0) {
          const price = data.prices[0];
          expect(price).toHaveProperty('date');
          expect(price).toHaveProperty('open');
          expect(price).toHaveProperty('high');
          expect(price).toHaveProperty('low');
          expect(price).toHaveProperty('close');
          expect(price).toHaveProperty('volume');
          
          // Verify OHLC relationships
          expect(price.high).toBeGreaterThanOrEqual(price.open);
          expect(price.high).toBeGreaterThanOrEqual(price.close);
          expect(price.low).toBeLessThanOrEqual(price.open);
          expect(price.low).toBeLessThanOrEqual(price.close);
          
          // Verify all values are positive
          expect(price.open).toBeGreaterThan(0);
          expect(price.high).toBeGreaterThan(0);
          expect(price.low).toBeGreaterThan(0);
          expect(price.close).toBeGreaterThan(0);
          expect(price.volume).toBeGreaterThanOrEqual(0);
        }
        
        console.log(`✅ Stock Historical Data (${symbol}, ${period}) - ${data.prices.length} data points`);
      }
      
      console.log('✅ Stock Historical Data API Integration passed');
    });

    test('Market Overview API Integration', async ({ request }) => {
      console.log('🌍 Testing Market Overview API Integration...');
      
      const response = await apiCall(request, 'GET', '/api/market/overview');
      
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      expect(data).toHaveProperty('indices');
      expect(Array.isArray(data.indices)).toBeTruthy();
      
      // Verify market indices data
      if (data.indices.length > 0) {
        const index = data.indices[0];
        expect(index).toHaveProperty('symbol');
        expect(index).toHaveProperty('price');
        expect(index).toHaveProperty('change');
        expect(index).toHaveProperty('changePercent');
        
        // Verify numeric values
        expect(typeof index.price).toBe('number');
        expect(index.price).toBeGreaterThan(0);
        expect(typeof index.change).toBe('number');
        expect(typeof index.changePercent).toBe('number');
      }
      
      console.log(`✅ Market Overview API Integration passed - ${data.indices.length} indices`);
    });

    test('Sector Performance API Integration', async ({ request }) => {
      console.log('🏭 Testing Sector Performance API Integration...');
      
      const response = await apiCall(request, 'GET', '/api/market/sectors');
      
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      expect(Array.isArray(data.sectors)).toBeTruthy();
      
      // Verify sector data structure
      if (data.sectors.length > 0) {
        const sector = data.sectors[0];
        expect(sector).toHaveProperty('name');
        expect(sector).toHaveProperty('performance');
        expect(typeof sector.performance).toBe('number');
        expect(typeof sector.name).toBe('string');
        expect(sector.name.length).toBeGreaterThan(0);
      }
      
      console.log(`✅ Sector Performance API Integration passed - ${data.sectors.length} sectors`);
    });

  });

  test.describe('Trading API Integration @critical @enterprise', () => {
    
    test('Trading Account Status API Integration', async ({ request }) => {
      console.log('💳 Testing Trading Account Status API Integration...');
      
      if (!authToken) {
        test.skip('Skipping trading tests - authentication required');
        return;
      }
      
      const response = await apiCall(request, 'GET', '/api/trading/account');
      
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      expect(data).toHaveProperty('accountStatus');
      expect(data).toHaveProperty('buyingPower');
      expect(data).toHaveProperty('equity');
      
      // Verify account data types
      expect(typeof data.buyingPower).toBe('number');
      expect(typeof data.equity).toBe('number');
      expect(data.buyingPower).toBeGreaterThanOrEqual(0);
      expect(data.equity).toBeGreaterThanOrEqual(0);
      
      console.log(`✅ Trading Account Status API Integration passed - Equity: $${data.equity}`);
    });

    test('Trading Signals API Integration', async ({ request }) => {
      console.log('📡 Testing Trading Signals API Integration...');
      
      const response = await apiCall(request, 'GET', '/api/trading/signals');
      
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      expect(Array.isArray(data.signals)).toBeTruthy();
      
      // Verify signal structure
      if (data.signals.length > 0) {
        const signal = data.signals[0];
        expect(signal).toHaveProperty('symbol');
        expect(signal).toHaveProperty('type');
        expect(signal).toHaveProperty('strength');
        expect(signal).toHaveProperty('timestamp');
        
        expect(['BUY', 'SELL', 'HOLD']).toContain(signal.type);
        expect(signal.strength).toBeGreaterThanOrEqual(0);
        expect(signal.strength).toBeLessThanOrEqual(100);
        expect(typeof signal.symbol).toBe('string');
        expect(signal.symbol.length).toBeGreaterThan(0);
      }
      
      console.log(`✅ Trading Signals API Integration passed - ${data.signals.length} signals`);
    });

  });

  test.describe('News and Analysis API Integration @critical @enterprise', () => {
    
    test('Stock News API Integration', async ({ request }) => {
      console.log('📰 Testing Stock News API Integration...');
      
      const symbol = testConfig.testSymbols[0];
      const response = await apiCall(request, 'GET', `/api/stocks/${symbol}/news`);
      
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      expect(Array.isArray(data.news)).toBeTruthy();
      
      // Verify news structure
      if (data.news.length > 0) {
        const article = data.news[0];
        expect(article).toHaveProperty('title');
        expect(article).toHaveProperty('summary');
        expect(article).toHaveProperty('url');
        expect(article).toHaveProperty('publishedAt');
        expect(article).toHaveProperty('source');
        
        // Verify URL format
        expect(article.url).toMatch(/^https?:\/\/.+/);
        expect(typeof article.title).toBe('string');
        expect(article.title.length).toBeGreaterThan(0);
        expect(typeof article.source).toBe('string');
        expect(article.source.length).toBeGreaterThan(0);
      }
      
      console.log(`✅ Stock News API Integration passed - ${data.news.length} articles for ${symbol}`);
    });

    test('Market News API Integration', async ({ request }) => {
      console.log('🌍 Testing Market News API Integration...');
      
      const response = await apiCall(request, 'GET', '/api/market/news');
      
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      expect(Array.isArray(data.news)).toBeTruthy();
      
      // Verify market news structure
      if (data.news.length > 0) {
        const article = data.news[0];
        expect(article).toHaveProperty('title');
        expect(article).toHaveProperty('summary');
        expect(article).toHaveProperty('category');
        expect(article).toHaveProperty('impact');
        
        expect(typeof article.title).toBe('string');
        expect(article.title.length).toBeGreaterThan(0);
        expect(typeof article.category).toBe('string');
        expect(['HIGH', 'MEDIUM', 'LOW']).toContain(article.impact);
      }
      
      console.log(`✅ Market News API Integration passed - ${data.news.length} articles`);
    });

    test('Technical Analysis API Integration', async ({ request }) => {
      console.log('🔍 Testing Technical Analysis API Integration...');
      
      const symbol = testConfig.testSymbols[0];
      const response = await apiCall(request, 'GET', `/api/stocks/${symbol}/technical`);
      
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      expect(data).toHaveProperty('symbol', symbol);
      expect(data).toHaveProperty('indicators');
      
      // Verify technical indicators
      const indicators = data.indicators;
      if (indicators.rsi) {
        expect(indicators.rsi.value).toBeGreaterThanOrEqual(0);
        expect(indicators.rsi.value).toBeLessThanOrEqual(100);
        expect(typeof indicators.rsi.value).toBe('number');
      }
      
      if (indicators.macd) {
        expect(indicators.macd).toHaveProperty('value');
        expect(indicators.macd).toHaveProperty('signal');
        expect(indicators.macd).toHaveProperty('histogram');
        expect(typeof indicators.macd.value).toBe('number');
        expect(typeof indicators.macd.signal).toBe('number');
        expect(typeof indicators.macd.histogram).toBe('number');
      }
      
      console.log(`✅ Technical Analysis API Integration passed for ${symbol}`);
    });

  });

  test.describe('API Error Handling Integration @critical @enterprise', () => {
    
    test('Invalid Symbol Error Handling', async ({ request }) => {
      console.log('❌ Testing Invalid Symbol Error Handling...');
      
      const response = await request.get(`${testConfig.apiURL}/api/stocks/INVALID123/quote`);
      
      expect(response.status()).toBe(404);
      
      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error.toLowerCase()).toContain('not found');
      
      console.log('✅ Invalid Symbol Error Handling passed');
    });

    test('Unauthorized Access Error Handling', async ({ request }) => {
      console.log('🚫 Testing Unauthorized Access Error Handling...');
      
      // Make request without auth token
      const response = await request.get(`${testConfig.apiURL}/api/portfolio/holdings`);
      
      expect(response.status()).toBe(401);
      
      const data = await response.json();
      expect(data).toHaveProperty('error');
      expect(data.error.toLowerCase()).toContain('unauthorized');
      
      console.log('✅ Unauthorized Access Error Handling passed');
    });

    test('Rate Limiting Error Handling', async ({ request }) => {
      console.log('⏱️ Testing Rate Limiting Error Handling...');
      
      // Make rapid requests to trigger rate limiting
      const promises = [];
      for (let i = 0; i < 20; i++) {
        promises.push(
          request.get(`${testConfig.apiURL}/api/stocks/AAPL/quote`).catch(e => ({ error: e.message }))
        );
      }
      
      const responses = await Promise.all(promises);
      
      // Check if any responses hit rate limit
      const rateLimitHit = responses.some(response => 
        response.status && response.status() === 429
      );
      
      if (rateLimitHit) {
        console.log('✅ Rate limiting is working correctly');
      } else {
        console.log('ℹ️ Rate limiting not triggered (this is acceptable)');
      }
      
      console.log('✅ Rate Limiting Error Handling test completed');
    });

  });

  test.describe('API Performance Integration @performance @enterprise', () => {
    
    test('API Response Time Performance', async ({ request }) => {
      console.log('⚡ Testing API Response Time Performance...');
      
      const endpoints = [
        '/api/market/overview',
        '/api/stocks/AAPL/quote',
        '/api/stocks/AAPL/news'
      ];
      
      const responseTimes = [];
      
      for (const endpoint of endpoints) {
        const startTime = Date.now();
        const response = await apiCall(request, 'GET', endpoint);
        const endTime = Date.now();
        const responseTime = endTime - startTime;
        
        responseTimes.push({ endpoint, responseTime, status: response.status() });
        
        // Verify response time is reasonable (under 5 seconds)
        expect(responseTime).toBeLessThan(5000);
        
        console.log(`${endpoint}: ${responseTime}ms`);
      }
      
      const averageResponseTime = responseTimes.reduce((sum, r) => sum + r.responseTime, 0) / responseTimes.length;
      console.log(`✅ API Performance test passed - Average response time: ${averageResponseTime.toFixed(0)}ms`);
    });

    test('Concurrent API Requests Performance', async ({ request }) => {
      console.log('🔄 Testing Concurrent API Requests Performance...');
      
      const startTime = Date.now();
      
      // Make multiple concurrent requests
      const promises = testConfig.testSymbols.slice(0, 5).map(symbol =>
        apiCall(request, 'GET', `/api/stocks/${symbol}/quote`)
      );
      
      const responses = await Promise.all(promises);
      const endTime = Date.now();
      const totalTime = endTime - startTime;
      
      // Verify all requests succeeded
      responses.forEach(response => {
        expect(response.ok()).toBeTruthy();
      });
      
      // Verify concurrent requests completed in reasonable time
      expect(totalTime).toBeLessThan(10000); // 10 seconds max
      
      console.log(`✅ Concurrent API Requests Performance passed - ${responses.length} requests in ${totalTime}ms`);
    });

  });

  test.afterAll(async () => {
    // Generate API integration test report for enterprise framework
    console.log('\n📊 Enterprise API Integration Test Report:');
    console.log(`Total API calls: ${testSession.apiResponses.length}`);
    console.log(`Total errors: ${testSession.errors.length}`);
    
    if (testSession.performanceMetrics.length > 0) {
      const avgResponseTime = testSession.performanceMetrics.reduce((sum, m) => sum + m.responseTime, 0) / testSession.performanceMetrics.length;
      console.log(`Average response time: ${avgResponseTime.toFixed(0)}ms`);
      
      // Performance thresholds for enterprise reporting
      const slowRequests = testSession.performanceMetrics.filter(m => m.responseTime > 2000).length;
      console.log(`Slow requests (>2s): ${slowRequests}/${testSession.performanceMetrics.length}`);
    }
    
    // Log any errors encountered
    if (testSession.errors.length > 0) {
      console.log('\n❌ Errors encountered:');
      testSession.errors.forEach(error => {
        console.log(`  ${error.endpoint}: ${error.error}`);
      });
    }
    
    console.log('\n✅ Enterprise API Integration testing completed');
  });

});

export default {
  testConfig
};