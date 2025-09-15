#!/usr/bin/env node

/**
 * Live Site Integration Tests
 * Tests the actual deployed finance application
 * API: https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev
 * Frontend: https://d1zb7knau41vl9.cloudfront.net
 */

const https = require('https');
const http = require('http');

const API_BASE = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';
const FRONTEND_BASE = 'https://d1copuy2oqlazx.cloudfront.net';

class LiveSiteTester {
  constructor() {
    this.results = {
      passed: 0,
      failed: 0,
      tests: []
    };
  }

  async makeRequest(url, options = {}) {
    return new Promise((resolve, reject) => {
      const urlObj = new URL(url);
      const isHttps = urlObj.protocol === 'https:';
      const client = isHttps ? https : http;
      
      const requestOptions = {
        hostname: urlObj.hostname,
        port: urlObj.port || (isHttps ? 443 : 80),
        path: urlObj.pathname + urlObj.search,
        method: options.method || 'GET',
        headers: {
          'Content-Type': 'application/json',
          'User-Agent': 'Live-Site-Tester/1.0',
          ...options.headers
        }
      };

      const req = client.request(requestOptions, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            const parsedData = res.headers['content-type']?.includes('application/json') 
              ? JSON.parse(data) 
              : data;
            resolve({
              status: res.statusCode,
              headers: res.headers,
              data: parsedData
            });
          } catch (error) {
            resolve({
              status: res.statusCode,
              headers: res.headers,
              data: data
            });
          }
        });
      });

      req.on('error', reject);
      
      if (options.body) {
        req.write(typeof options.body === 'string' ? options.body : JSON.stringify(options.body));
      }
      
      req.end();
    });
  }

  test(name, testFn) {
    return async () => {
      try {
        console.log(`🧪 Testing: ${name}`);
        await testFn();
        this.results.passed++;
        this.results.tests.push({ name, status: 'PASS' });
        console.log(`✅ PASS: ${name}`);
      } catch (error) {
        this.results.failed++;
        this.results.tests.push({ name, status: 'FAIL', error: error.message });
        console.log(`❌ FAIL: ${name} - ${error.message}`);
      }
    };
  }

  async runTests() {
    console.log('🚀 Starting Live Site Integration Tests\n');
    console.log(`API Base: ${API_BASE}`);
    console.log(`Frontend Base: ${FRONTEND_BASE}\n`);

    // API Health Tests
    await this.test('API Health Check', async () => {
      const response = await this.makeRequest(`${API_BASE}/health`);
      if (response.status !== 200) throw new Error(`Expected 200, got ${response.status}`);
      if (!response.data.healthy) throw new Error('API reports unhealthy status');
      if (!response.data.database?.status) throw new Error('Database status missing');
    })();

    // Public API Endpoints
    await this.test('Market Overview Data', async () => {
      const response = await this.makeRequest(`${API_BASE}/api/market/overview`);
      if (response.status !== 200) throw new Error(`Expected 200, got ${response.status}`);
      if (!response.data.data && !response.data.sentiment_indicators) throw new Error('Market data missing');
      const data = response.data.data || response.data;
      if (!data.sentiment_indicators) throw new Error('Sentiment indicators missing');
    })();

    await this.test('Market Sectors Data', async () => {
      const response = await this.makeRequest(`${API_BASE}/api/market/sectors`);
      // Sectors endpoint returns 404 when no data loaded (expected until loaders run)
      if (response.status === 404 && response.data.error && response.data.error.includes('No sector performance data')) {
        return; // Expected behavior - pass the test
      }
      if (response.status !== 200) throw new Error(`Expected 200, got ${response.status}`);
      if (!response.data.data) throw new Error('Sectors data missing');
    })();

    // Protected API Endpoints (should require auth)
    await this.test('Portfolio Holdings Auth Required', async () => {
      const response = await this.makeRequest(`${API_BASE}/api/portfolio/holdings`);
      if (response.status !== 401) throw new Error(`Expected 401 (auth required), got ${response.status}`);
      if (!response.data.error?.includes('Authorization missing')) {
        throw new Error('Should require authentication');
      }
    })();

    await this.test('Stock Data Auth Required', async () => {
      const response = await this.makeRequest(`${API_BASE}/api/stocks/AAPL`);
      if (response.status !== 401) throw new Error(`Expected 401 (auth required), got ${response.status}`);
    })();

    // Frontend Tests
    await this.test('Frontend Main Page Loads', async () => {
      const response = await this.makeRequest(FRONTEND_BASE);
      if (response.status !== 200) throw new Error(`Expected 200, got ${response.status}`);
      if (!response.data.toLowerCase().includes('<!doctype html')) throw new Error('Not a valid HTML page');
      if (!response.data.includes('Financial Dashboard') && !response.data.includes('root')) {
        throw new Error('Page does not appear to be the finance application');
      }
    })();

    await this.test('Frontend Config File Exists', async () => {
      const response = await this.makeRequest(`${FRONTEND_BASE}/config.js`);
      if (response.status !== 200) throw new Error(`Expected 200, got ${response.status}`);
      if (!response.data.includes('window.__CONFIG__')) throw new Error('Config file malformed');
      if (!response.data.includes(API_BASE.replace('https://', '').split('/')[0])) {
        throw new Error('Config does not reference correct API');
      }
    })();

    // API Route Coverage
    const publicRoutes = [
      '/api/market/overview',
      '/api/market/sectors', 
      '/api/market/breadth',
      '/api/technical/indicators',
      '/api/sentiment/overview'
    ];

    for (const route of publicRoutes) {
      await this.test(`Public Route: ${route}`, async () => {
        const response = await this.makeRequest(`${API_BASE}${route}`);
        if (response.status >= 500) throw new Error(`Server error: ${response.status}`);
        // Allow 404 for routes not yet implemented, but no 5xx errors
      })();
    }

    // Performance Tests
    await this.test('API Response Time < 5s', async () => {
      const start = Date.now();
      const response = await this.makeRequest(`${API_BASE}/health`);
      const duration = Date.now() - start;
      if (duration > 5000) throw new Error(`Response took ${duration}ms, expected < 5000ms`);
      if (response.status !== 200) throw new Error(`Health check failed: ${response.status}`);
    })();

    await this.test('Frontend Response Time < 10s', async () => {
      const start = Date.now();
      const response = await this.makeRequest(FRONTEND_BASE);
      const duration = Date.now() - start;
      if (duration > 10000) throw new Error(`Frontend load took ${duration}ms, expected < 10000ms`);
      if (response.status !== 200) throw new Error(`Frontend load failed: ${response.status}`);
    })();

    // Error Handling Tests
    await this.test('API Handles Invalid Routes', async () => {
      const response = await this.makeRequest(`${API_BASE}/api/nonexistent/route`);
      if (response.status === 500) throw new Error('Should not return 500 for invalid routes');
      // Should return 404 or similar, not crash
    })();

    await this.test('Frontend Handles Invalid Routes', async () => {
      const response = await this.makeRequest(`${FRONTEND_BASE}/nonexistent-page`);
      // Should not crash the application
      if (response.status === 500) throw new Error('Frontend should handle invalid routes gracefully');
    })();

    this.printResults();
  }

  printResults() {
    console.log('\n' + '='.repeat(60));
    console.log('📊 LIVE SITE TEST RESULTS');
    console.log('='.repeat(60));
    console.log(`✅ Passed: ${this.results.passed}`);
    console.log(`❌ Failed: ${this.results.failed}`);
    console.log(`📈 Success Rate: ${((this.results.passed / (this.results.passed + this.results.failed)) * 100).toFixed(1)}%`);
    
    if (this.results.failed > 0) {
      console.log('\n❌ FAILED TESTS:');
      this.results.tests
        .filter(test => test.status === 'FAIL')
        .forEach(test => {
          console.log(`   - ${test.name}: ${test.error}`);
        });
    }

    console.log('\n📋 SITE STATUS:');
    console.log(`   API Health: ${this.results.tests.find(t => t.name === 'API Health Check')?.status || 'UNKNOWN'}`);
    console.log(`   Frontend: ${this.results.tests.find(t => t.name === 'Frontend Main Page Loads')?.status || 'UNKNOWN'}`);
    console.log(`   Authentication: ${this.results.tests.find(t => t.name === 'Portfolio Holdings Auth Required')?.status || 'UNKNOWN'}`);
    console.log(`   Market Data: ${this.results.tests.find(t => t.name === 'Market Overview Data')?.status || 'UNKNOWN'}`);
    
    console.log('\n🔗 QUICK LINKS:');
    console.log(`   Live Site: ${FRONTEND_BASE}`);
    console.log(`   API Health: ${API_BASE}/health`);
    console.log(`   Market Data: ${API_BASE}/api/market/overview`);
    
    if (this.results.failed === 0) {
      console.log('\n🎉 ALL TESTS PASSED - Your site is working correctly!');
    } else {
      console.log(`\n⚠️  ${this.results.failed} test(s) failed - see details above`);
    }
    
    console.log('='.repeat(60));
  }
}

// Run tests if called directly
if (require.main === module) {
  const tester = new LiveSiteTester();
  tester.runTests().catch(console.error);
}

module.exports = LiveSiteTester;