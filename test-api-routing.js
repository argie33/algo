#!/usr/bin/env node

/**
 * API Routing Test Script
 * Tests all API endpoints to verify CloudFront routing fix
 */

const https = require('https');
const http = require('http');

const BASE_URL = 'https://d1zb7knau41vl9.cloudfront.net';
const TEST_TIMEOUT = 10000; // 10 seconds

// Test endpoints configuration
const API_ENDPOINTS = [
  { path: '/api/health', method: 'GET', expectJSON: true },
  { path: '/api/portfolio/holdings', method: 'GET', expectJSON: true },
  { path: '/api/portfolio/performance', method: 'GET', expectJSON: true },
  { path: '/api/portfolio/api-keys', method: 'GET', expectJSON: true },
  { path: '/api/trading/orders', method: 'GET', expectJSON: true },
  { path: '/api/ai-assistant/config', method: 'GET', expectJSON: true },
  { path: '/api/market/indices', method: 'GET', expectJSON: true },
  { path: '/api/settings', method: 'GET', expectJSON: true },
  { path: '/api/hft/strategies', method: 'GET', expectJSON: true }
];

class APIRoutingTester {
  constructor() {
    this.results = [];
    this.startTime = Date.now();
  }

  async testEndpoint(endpoint) {
    return new Promise((resolve) => {
      const startTime = Date.now();
      const url = `${BASE_URL}${endpoint.path}`;
      
      console.log(`🧪 Testing: ${endpoint.method} ${endpoint.path}`);
      
      const urlObj = new URL(url);
      const options = {
        hostname: urlObj.hostname,
        port: urlObj.port || 443,
        path: urlObj.pathname + urlObj.search,
        method: endpoint.method,
        headers: {
          'Accept': 'application/json',
          'User-Agent': 'API-Routing-Test/1.0',
          'X-Test-Mode': 'true'
        },
        timeout: TEST_TIMEOUT
      };

      const request = https.request(options, (response) => {
        let data = '';
        
        response.on('data', (chunk) => {
          data += chunk;
        });
        
        response.on('end', () => {
          const responseTime = Date.now() - startTime;
          const result = this.analyzeResponse(endpoint, response, data, responseTime);
          console.log(`   ${result.success ? '✅' : '❌'} ${result.status} (${responseTime}ms)`);
          
          if (!result.success) {
            console.log(`      ${result.issue}`);
          }
          
          resolve(result);
        });
      });

      request.on('error', (error) => {
        const responseTime = Date.now() - startTime;
        const result = {
          endpoint: endpoint.path,
          method: endpoint.method,
          success: false,
          status: 'ERROR',
          issue: `Network error: ${error.message}`,
          responseTime,
          timestamp: new Date().toISOString()
        };
        
        console.log(`   ❌ ERROR (${responseTime}ms): ${error.message}`);
        resolve(result);
      });

      request.on('timeout', () => {
        request.destroy();
        const result = {
          endpoint: endpoint.path,
          method: endpoint.method,
          success: false,
          status: 'TIMEOUT',
          issue: `Request timed out after ${TEST_TIMEOUT}ms`,
          responseTime: TEST_TIMEOUT,
          timestamp: new Date().toISOString()
        };
        
        console.log(`   ❌ TIMEOUT (${TEST_TIMEOUT}ms)`);
        resolve(result);
      });

      request.end();
    });
  }

  analyzeResponse(endpoint, response, data, responseTime) {
    const result = {
      endpoint: endpoint.path,
      method: endpoint.method,
      statusCode: response.statusCode,
      contentType: response.headers['content-type'] || 'unknown',
      responseTime,
      timestamp: new Date().toISOString()
    };

    // Check if response looks like HTML (CloudFront routing issue)
    const isHTML = data.trim().toLowerCase().startsWith('<!doctype html') || 
                   data.trim().toLowerCase().startsWith('<html');
    
    // Check if response is JSON
    let isJSON = false;
    let jsonData = null;
    try {
      jsonData = JSON.parse(data);
      isJSON = true;
    } catch (e) {
      isJSON = false;
    }

    // Determine success based on expectations
    if (isHTML && endpoint.expectJSON) {
      result.success = false;
      result.status = 'HTML_INSTEAD_OF_JSON';
      result.issue = 'CloudFront routing issue - API endpoint returning HTML instead of JSON';
      result.dataPreview = data.substring(0, 100) + '...';
    } else if (!isJSON && endpoint.expectJSON) {
      result.success = false;
      result.status = 'NOT_JSON';
      result.issue = `Expected JSON response but got ${result.contentType}`;
      result.dataPreview = data.substring(0, 100);
    } else if (response.statusCode >= 500) {
      result.success = false;
      result.status = 'SERVER_ERROR';
      result.issue = `Server error: ${response.statusCode}`;
      result.responseData = jsonData;
    } else if (response.statusCode === 401) {
      result.success = true; // Expected for authenticated endpoints
      result.status = 'AUTH_REQUIRED';
      result.issue = 'Authentication required (expected)';
      result.responseData = jsonData;
    } else if (response.statusCode >= 400) {
      result.success = false;
      result.status = 'CLIENT_ERROR';
      result.issue = `Client error: ${response.statusCode}`;
      result.responseData = jsonData;
    } else if (isJSON) {
      result.success = true;
      result.status = 'JSON_SUCCESS';
      result.responseData = jsonData;
    } else {
      result.success = true;
      result.status = 'SUCCESS';
      result.dataPreview = data.substring(0, 100);
    }

    return result;
  }

  async runAllTests() {
    console.log('🚀 Starting API Routing Tests');
    console.log('==============================');
    console.log(`Base URL: ${BASE_URL}`);
    console.log(`Endpoints: ${API_ENDPOINTS.length}`);
    console.log('');

    // Test all endpoints
    for (const endpoint of API_ENDPOINTS) {
      const result = await this.testEndpoint(endpoint);
      this.results.push(result);
      
      // Small delay between requests
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    this.generateReport();
  }

  generateReport() {
    const totalTime = Date.now() - this.startTime;
    const successful = this.results.filter(r => r.success).length;
    const failed = this.results.filter(r => !r.success).length;
    const htmlIssues = this.results.filter(r => r.status === 'HTML_INSTEAD_OF_JSON').length;
    
    console.log('');
    console.log('📊 TEST RESULTS SUMMARY');
    console.log('=======================');
    console.log(`Total Tests: ${this.results.length}`);
    console.log(`✅ Successful: ${successful}`);
    console.log(`❌ Failed: ${failed}`);
    console.log(`🔴 HTML Instead of JSON: ${htmlIssues}`);
    console.log(`⏱️  Total Time: ${totalTime}ms`);
    console.log('');

    if (htmlIssues > 0) {
      console.log('🚨 CRITICAL CLOUDFRONT ROUTING ISSUE DETECTED');
      console.log('============================================');
      console.log('API endpoints are returning HTML instead of JSON.');
      console.log('This indicates CloudFront is routing /api/* requests to S3 instead of Lambda.');
      console.log('');
      console.log('🔧 TO FIX:');
      console.log('1. Run: ./fix-cloudfront-routing.sh');
      console.log('2. Wait 15 minutes for propagation');
      console.log('3. Re-run this test: node test-api-routing.js');
      console.log('');
    } else if (failed === 0) {
      console.log('🎉 ALL TESTS PASSED!');
      console.log('API routing is working correctly.');
      console.log('CloudFront is properly routing /api/* requests to Lambda.');
      console.log('');
    } else {
      console.log('⚠️  SOME TESTS FAILED');
      console.log('API routing appears to be working (no HTML responses),');
      console.log('but some endpoints have other issues:');
      console.log('');
      
      this.results.filter(r => !r.success && r.status !== 'AUTH_REQUIRED').forEach(result => {
        console.log(`❌ ${result.endpoint}: ${result.issue}`);
      });
      console.log('');
    }

    // Detailed breakdown
    console.log('📋 DETAILED RESULTS');
    console.log('==================');
    
    this.results.forEach(result => {
      const icon = result.success ? '✅' : '❌';
      const authNote = result.status === 'AUTH_REQUIRED' ? ' (Expected - needs auth)' : '';
      console.log(`${icon} ${result.method} ${result.endpoint}`);
      console.log(`   Status: ${result.status}${authNote}`);
      console.log(`   Response Time: ${result.responseTime}ms`);
      console.log(`   Content-Type: ${result.contentType}`);
      
      if (result.issue && result.status !== 'AUTH_REQUIRED') {
        console.log(`   Issue: ${result.issue}`);
      }
      
      if (result.dataPreview) {
        console.log(`   Preview: ${result.dataPreview}`);
      }
      console.log('');
    });

    // Export results for automation
    const reportData = {
      timestamp: new Date().toISOString(),
      summary: {
        total: this.results.length,
        successful,
        failed,
        htmlIssues,
        totalTime
      },
      results: this.results
    };

    require('fs').writeFileSync('api-routing-test-results.json', JSON.stringify(reportData, null, 2));
    console.log('📄 Detailed results saved to: api-routing-test-results.json');
  }
}

// Run the tests
if (require.main === module) {
  const tester = new APIRoutingTester();
  tester.runAllTests().catch(console.error);
}

module.exports = APIRoutingTester;