#!/usr/bin/env node

/**
 * Comprehensive API Tests for Live Finance Application
 * Tests all endpoints with the actual deployed API
 */

const https = require('https');
const http = require('http');

const API_BASE = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

class ApiTester {
  constructor() {
    this.results = {
      passed: 0,
      failed: 0,
      tests: [],
      endpoints: {
        public: [],
        protected: [],
        broken: []
      }
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
          'User-Agent': 'API-Comprehensive-Tester/1.0',
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
              data: parsedData,
              url: url
            });
          } catch (error) {
            resolve({
              status: res.statusCode,
              headers: res.headers,
              data: data,
              url: url
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
        console.log(`🧪 ${name}`);
        const result = await testFn();
        this.results.passed++;
        this.results.tests.push({ name, status: 'PASS', result });
        console.log(`✅ PASS: ${name}`);
        return result;
      } catch (error) {
        this.results.failed++;
        this.results.tests.push({ name, status: 'FAIL', error: error.message });
        console.log(`❌ FAIL: ${name} - ${error.message}`);
        throw error;
      }
    };
  }

  async runTests() {
    console.log('🚀 Starting Comprehensive API Tests\n');
    console.log(`API Base: ${API_BASE}\n`);

    // Core Health Tests
    await this.test('API Health Check', async () => {
      const response = await this.makeRequest(`${API_BASE}/health`);
      if (response.status !== 200) throw new Error(`Expected 200, got ${response.status}`);
      if (!response.data.healthy) throw new Error('API reports unhealthy status');
      return response.data;
    })();

    // Test All Public Market Endpoints
    const marketEndpoints = [
      '/api/market/overview',
      '/api/market/breadth', 
      '/api/market/sectors',
      '/api/market/economic-indicators',
      '/api/market/seasonality'
    ];

    for (const endpoint of marketEndpoints) {
      await this.test(`Market API: ${endpoint}`, async () => {
        const response = await this.makeRequest(`${API_BASE}${endpoint}`);
        
        if (response.status === 200) {
          this.results.endpoints.public.push(endpoint);
          if (!response.data) throw new Error('No data returned');
          return { status: 'working', data: response.data };
        } else if (response.status === 401) {
          this.results.endpoints.protected.push(endpoint);
          return { status: 'protected', message: 'Requires authentication' };
        } else if (response.status >= 500) {
          this.results.endpoints.broken.push(endpoint);
          throw new Error(`Server error: ${response.status} - ${response.data?.error || 'Unknown error'}`);
        } else {
          return { status: 'other', code: response.status, data: response.data };
        }
      })();
    }

    // Test Technical Analysis Endpoints
    const technicalEndpoints = [
      '/api/technical/indicators',
      '/api/technical/patterns',
      '/api/technical/analysis'
    ];

    for (const endpoint of technicalEndpoints) {
      await this.test(`Technical API: ${endpoint}`, async () => {
        const response = await this.makeRequest(`${API_BASE}${endpoint}`);
        
        if (response.status === 200) {
          this.results.endpoints.public.push(endpoint);
          return { status: 'working', data: response.data };
        } else if (response.status === 401) {
          this.results.endpoints.protected.push(endpoint);
          return { status: 'protected' };
        } else if (response.status >= 500) {
          this.results.endpoints.broken.push(endpoint);
          throw new Error(`Server error: ${response.status}`);
        } else {
          return { status: 'other', code: response.status };
        }
      })();
    }

    // Test Sentiment Endpoints
    const sentimentEndpoints = [
      '/api/sentiment/overview',
      '/api/sentiment/analysis',
      '/api/sentiment/history'
    ];

    for (const endpoint of sentimentEndpoints) {
      await this.test(`Sentiment API: ${endpoint}`, async () => {
        const response = await this.makeRequest(`${API_BASE}${endpoint}`);
        
        if (response.status === 200) {
          this.results.endpoints.public.push(endpoint);
          return { status: 'working', data: response.data };
        } else if (response.status === 401) {
          this.results.endpoints.protected.push(endpoint);
          return { status: 'protected' };
        } else {
          return { status: 'other', code: response.status };
        }
      })();
    }

    // Test Protected Endpoints (should require auth)
    const protectedEndpoints = [
      '/api/portfolio/holdings',
      '/api/portfolio/performance',
      '/api/stocks/AAPL',
      '/api/trading/positions',
      '/api/settings/api-keys'
    ];

    for (const endpoint of protectedEndpoints) {
      await this.test(`Protected API: ${endpoint}`, async () => {
        const response = await this.makeRequest(`${API_BASE}${endpoint}`);
        
        if (response.status === 401) {
          this.results.endpoints.protected.push(endpoint);
          if (!response.data?.error?.includes('Authentication required')) {
            throw new Error('Should return proper auth error message');
          }
          return { status: 'correctly_protected' };
        } else if (response.status === 200) {
          // This might be unexpected for protected endpoints
          throw new Error('Protected endpoint returned 200 without auth - security concern');
        } else {
          return { status: 'other', code: response.status };
        }
      })();
    }

    // Test Data Quality
    await this.test('Market Data Quality Check', async () => {
      const response = await this.makeRequest(`${API_BASE}/api/market/overview`);
      
      if (response.status !== 200) throw new Error('Market overview not available');
      
      const data = response.data.data || response.data;
      
      // Check for required data structures
      if (!data.sentiment_indicators) throw new Error('Missing sentiment indicators');
      if (!data.market_breadth) throw new Error('Missing market breadth data');
      if (!data.market_cap) throw new Error('Missing market cap data');
      
      // Check data freshness (should be recent)
      const timestamp = new Date(data.timestamp || response.data.timestamp);
      const age = Date.now() - timestamp.getTime();
      const maxAge = 24 * 60 * 60 * 1000; // 24 hours
      
      if (age > maxAge) {
        console.log(`⚠️  Data is ${Math.round(age / (60 * 60 * 1000))} hours old`);
      }
      
      return { dataAge: age, structures: Object.keys(data) };
    })();

    // Test API Performance
    await this.test('API Performance Test', async () => {
      const start = Date.now();
      const response = await this.makeRequest(`${API_BASE}/health`);
      const duration = Date.now() - start;
      
      if (duration > 10000) throw new Error(`Too slow: ${duration}ms`);
      if (response.status !== 200) throw new Error('Health check failed');
      
      return { responseTime: duration, performance: duration < 2000 ? 'excellent' : duration < 5000 ? 'good' : 'acceptable' };
    })();

    // Test Error Handling
    await this.test('Error Handling Test', async () => {
      const response = await this.makeRequest(`${API_BASE}/api/nonexistent/endpoint`);
      
      // Should not return 500 for missing endpoints
      if (response.status === 500) {
        throw new Error('API crashes on invalid endpoints instead of returning 404');
      }
      
      return { errorCode: response.status, handlesErrors: true };
    })();

    this.printResults();
  }

  printResults() {
    console.log('\n' + '='.repeat(70));
    console.log('📊 COMPREHENSIVE API TEST RESULTS');
    console.log('='.repeat(70));
    console.log(`✅ Passed: ${this.results.passed}`);
    console.log(`❌ Failed: ${this.results.failed}`);
    console.log(`📈 Success Rate: ${((this.results.passed / (this.results.passed + this.results.failed)) * 100).toFixed(1)}%`);
    
    console.log('\n📡 ENDPOINT ANALYSIS:');
    console.log(`   🟢 Public Endpoints: ${this.results.endpoints.public.length}`);
    console.log(`   🔒 Protected Endpoints: ${this.results.endpoints.protected.length}`);
    console.log(`   🔴 Broken Endpoints: ${this.results.endpoints.broken.length}`);
    
    if (this.results.endpoints.public.length > 0) {
      console.log('\n🟢 WORKING PUBLIC ENDPOINTS:');
      this.results.endpoints.public.forEach(ep => console.log(`   ✓ ${ep}`));
    }
    
    if (this.results.endpoints.protected.length > 0) {
      console.log('\n🔒 PROTECTED ENDPOINTS (require auth):');
      this.results.endpoints.protected.forEach(ep => console.log(`   🔐 ${ep}`));
    }
    
    if (this.results.endpoints.broken.length > 0) {
      console.log('\n🔴 BROKEN ENDPOINTS (need fixes):');
      this.results.endpoints.broken.forEach(ep => console.log(`   ❌ ${ep}`));
    }
    
    if (this.results.failed > 0) {
      console.log('\n❌ FAILED TESTS:');
      this.results.tests
        .filter(test => test.status === 'FAIL')
        .forEach(test => {
          console.log(`   - ${test.name}: ${test.error}`);
        });
    }

    console.log('\n🔗 API ENDPOINTS:');
    console.log(`   Health: ${API_BASE}/health`);
    console.log(`   Market Data: ${API_BASE}/api/market/overview`);
    console.log(`   Technical Analysis: ${API_BASE}/api/technical/indicators`);
    console.log(`   Sentiment: ${API_BASE}/api/sentiment/overview`);
    
    if (this.results.failed === 0) {
      console.log('\n🎉 ALL API TESTS PASSED - Your API is working correctly!');
    } else if (this.results.endpoints.broken.length === 0) {
      console.log('\n✅ CORE API WORKING - Some tests failed but no broken endpoints found');
    } else {
      console.log(`\n⚠️  ${this.results.failed} test(s) failed - ${this.results.endpoints.broken.length} endpoints need fixing`);
    }
    
    console.log('='.repeat(70));
  }
}

// Run tests if called directly
if (require.main === module) {
  const tester = new ApiTester();
  tester.runTests().catch(console.error);
}

module.exports = ApiTester;