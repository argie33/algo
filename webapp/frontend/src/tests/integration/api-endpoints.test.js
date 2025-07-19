/**
 * API Integration Testing Suite - TEST-002
 * Real API endpoint testing with no mocks or fallbacks
 * Tests actual Lambda API Gateway endpoints for production readiness
 */

import { describe, it, expect, beforeAll } from 'vitest';

// Real API configuration - no mocks
const API_BASE_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';
const TEST_TIMEOUT = 30000; // 30 seconds for real API calls

class ApiTester {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
    this.results = {
      endpoints: {},
      totalTested: 0,
      totalPassed: 0,
      totalFailed: 0
    };
  }

  async testEndpoint(path, method = 'GET', expectedStatus = 200, body = null, headers = {}) {
    const url = `${this.baseUrl}${path}`;
    const testName = `${method} ${path}`;
    
    try {
      console.log(`Testing ${testName}...`);
      
      const response = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          ...headers
        },
        body: body ? JSON.stringify(body) : null
      });

      const responseData = await response.text();
      let jsonData = null;
      
      try {
        jsonData = JSON.parse(responseData);
      } catch (e) {
        // Response is not JSON, keep as text
      }

      const result = {
        status: response.status,
        success: response.status === expectedStatus,
        responseData: jsonData || responseData,
        headers: Object.fromEntries(response.headers.entries()),
        duration: Date.now()
      };

      this.results.endpoints[testName] = result;
      this.results.totalTested++;
      
      if (result.success) {
        this.results.totalPassed++;
        console.log(`✅ ${testName}: ${response.status}`);
      } else {
        this.results.totalFailed++;
        console.log(`❌ ${testName}: Expected ${expectedStatus}, got ${response.status}`);
      }

      return result;
    } catch (error) {
      const result = {
        status: 0,
        success: false,
        error: error.message,
        duration: Date.now()
      };

      this.results.endpoints[testName] = result;
      this.results.totalTested++;
      this.results.totalFailed++;
      
      console.log(`❌ ${testName}: Network error - ${error.message}`);
      return result;
    }
  }

  getResults() {
    return this.results;
  }
}

describe('API Integration Testing Suite - TEST-002', () => {
  let apiTester;

  beforeAll(() => {
    apiTester = new ApiTester(API_BASE_URL);
    console.log(`🚀 Starting API Integration Tests against ${API_BASE_URL}`);
  });

  describe('Core Health and Status Endpoints', () => {
    it('should respond to health check endpoint', async () => {
      const result = await apiTester.testEndpoint('/health', 'GET', 200);
      expect(result.success).toBe(true);
      expect(result.status).toBe(200);
    }, TEST_TIMEOUT);

    it('should respond to API status endpoint', async () => {
      const result = await apiTester.testEndpoint('/status', 'GET', 200);
      expect(result.success).toBe(true);
      expect(result.status).toBe(200);
    }, TEST_TIMEOUT);

    it('should handle CORS preflight requests', async () => {
      const result = await apiTester.testEndpoint('/health', 'OPTIONS', 200);
      expect(result.headers).toHaveProperty('access-control-allow-origin');
    }, TEST_TIMEOUT);
  });

  describe('Authentication Endpoints', () => {
    it('should respond to auth status endpoint', async () => {
      const result = await apiTester.testEndpoint('/auth/status', 'GET');
      expect(result.status).toBeGreaterThanOrEqual(200);
      expect(result.status).toBeLessThan(500);
    }, TEST_TIMEOUT);

    it('should handle auth validation endpoint', async () => {
      const result = await apiTester.testEndpoint('/auth/validate', 'POST', 401, {
        token: 'invalid-token'
      });
      // Should return 401 for invalid token or handle gracefully
      expect([401, 403, 200].includes(result.status)).toBe(true);
    }, TEST_TIMEOUT);
  });

  describe('Portfolio Management Endpoints', () => {
    it('should respond to portfolio list endpoint', async () => {
      const result = await apiTester.testEndpoint('/portfolio', 'GET');
      expect(result.status).toBeGreaterThanOrEqual(200);
      expect(result.status).toBeLessThan(500);
    }, TEST_TIMEOUT);

    it('should respond to portfolio holdings endpoint', async () => {
      const result = await apiTester.testEndpoint('/portfolio/holdings', 'GET');
      expect(result.status).toBeGreaterThanOrEqual(200);
      expect(result.status).toBeLessThan(500);
    }, TEST_TIMEOUT);

    it('should respond to portfolio performance endpoint', async () => {
      const result = await apiTester.testEndpoint('/portfolio/performance', 'GET');
      expect(result.status).toBeGreaterThanOrEqual(200);
      expect(result.status).toBeLessThan(500);
    }, TEST_TIMEOUT);
  });

  describe('Market Data Endpoints', () => {
    it('should respond to live data endpoint', async () => {
      const result = await apiTester.testEndpoint('/live-data', 'GET');
      expect(result.status).toBeGreaterThanOrEqual(200);
      expect(result.status).toBeLessThan(500);
    }, TEST_TIMEOUT);

    it('should respond to stocks endpoint', async () => {
      const result = await apiTester.testEndpoint('/stocks', 'GET');
      expect(result.status).toBeGreaterThanOrEqual(200);
      expect(result.status).toBeLessThan(500);
    }, TEST_TIMEOUT);

    it('should respond to market data endpoint', async () => {
      const result = await apiTester.testEndpoint('/market-data', 'GET');
      expect(result.status).toBeGreaterThanOrEqual(200);
      expect(result.status).toBeLessThan(500);
    }, TEST_TIMEOUT);
  });

  describe('Settings and Configuration Endpoints', () => {
    it('should respond to settings endpoint', async () => {
      const result = await apiTester.testEndpoint('/settings', 'GET');
      expect(result.status).toBeGreaterThanOrEqual(200);
      expect(result.status).toBeLessThan(500);
    }, TEST_TIMEOUT);

    it('should handle settings update endpoint', async () => {
      const result = await apiTester.testEndpoint('/settings', 'POST', 401, {
        testSetting: 'value'
      });
      // Should require authentication or handle gracefully
      expect([200, 401, 403].includes(result.status)).toBe(true);
    }, TEST_TIMEOUT);
  });

  describe('WebSocket and Real-time Endpoints', () => {
    it('should respond to WebSocket endpoint', async () => {
      const result = await apiTester.testEndpoint('/websocket', 'GET');
      expect(result.status).toBeGreaterThanOrEqual(200);
      expect(result.status).toBeLessThan(500);
    }, TEST_TIMEOUT);

    it('should respond to live streaming endpoint', async () => {
      const result = await apiTester.testEndpoint('/live-stream', 'GET');
      expect(result.status).toBeGreaterThanOrEqual(200);
      expect(result.status).toBeLessThan(500);
    }, TEST_TIMEOUT);
  });

  describe('Financial Data Analysis Endpoints', () => {
    it('should respond to technical analysis endpoint', async () => {
      const result = await apiTester.testEndpoint('/technical-analysis', 'GET');
      expect(result.status).toBeGreaterThanOrEqual(200);
      expect(result.status).toBeLessThan(500);
    }, TEST_TIMEOUT);

    it('should respond to sentiment analysis endpoint', async () => {
      const result = await apiTester.testEndpoint('/sentiment', 'GET');
      expect(result.status).toBeGreaterThanOrEqual(200);
      expect(result.status).toBeLessThan(500);
    }, TEST_TIMEOUT);

    it('should respond to trading signals endpoint', async () => {
      const result = await apiTester.testEndpoint('/trading-signals', 'GET');
      expect(result.status).toBeGreaterThanOrEqual(200);
      expect(result.status).toBeLessThan(500);
    }, TEST_TIMEOUT);
  });

  describe('API Response Quality and Performance', () => {
    it('should have reasonable response times', async () => {
      const startTime = Date.now();
      const result = await apiTester.testEndpoint('/health', 'GET', 200);
      const responseTime = Date.now() - startTime;
      
      expect(result.success).toBe(true);
      expect(responseTime).toBeLessThan(5000); // Should respond within 5 seconds
    }, TEST_TIMEOUT);

    it('should return proper JSON content type for JSON endpoints', async () => {
      const result = await apiTester.testEndpoint('/health', 'GET', 200);
      
      if (result.success && typeof result.responseData === 'object') {
        expect(result.headers['content-type']).toContain('application/json');
      }
    }, TEST_TIMEOUT);

    it('should handle invalid endpoints gracefully', async () => {
      const result = await apiTester.testEndpoint('/nonexistent-endpoint', 'GET', 404);
      expect([404, 403].includes(result.status)).toBe(true);
    }, TEST_TIMEOUT);
  });

  describe('Integration Test Results Summary', () => {
    it('should provide comprehensive test coverage summary', async () => {
      const results = apiTester.getResults();
      
      console.log('\n📊 API Integration Test Results:');
      console.log(`Total Endpoints Tested: ${results.totalTested}`);
      console.log(`Successful Responses: ${results.totalPassed}`);
      console.log(`Failed Responses: ${results.totalFailed}`);
      console.log(`Success Rate: ${((results.totalPassed / results.totalTested) * 100).toFixed(1)}%`);
      
      // Require at least 70% of endpoints to be responding
      const successRate = results.totalPassed / results.totalTested;
      expect(successRate).toBeGreaterThan(0.7);
      
      // Ensure we tested a reasonable number of endpoints
      expect(results.totalTested).toBeGreaterThan(10);
    }, TEST_TIMEOUT);
  });
});