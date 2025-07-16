#!/usr/bin/env node
/**
 * Deployment Testing Script
 * Tests API endpoints after deployment to verify functionality
 */

const axios = require('axios');

// Configuration
const CONFIG = {
  // These will be updated with actual deployed URLs
  API_BASE_URL: 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
  TIMEOUT: 30000,
  RETRY_ATTEMPTS: 3,
  RETRY_DELAY: 2000
};

// Test utilities
class DeploymentTester {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
    this.client = axios.create({
      baseURL: baseUrl,
      timeout: CONFIG.TIMEOUT,
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'Deployment-Test-Script/1.0'
      }
    });
  }

  async testEndpoint(endpoint, description, options = {}) {
    console.log(`\n🔍 Testing: ${description}`);
    console.log(`   URL: ${this.baseUrl}${endpoint}`);
    
    const method = options.method || 'GET';
    const data = options.data || null;
    const expectedStatus = options.expectedStatus || 200;
    
    for (let attempt = 1; attempt <= CONFIG.RETRY_ATTEMPTS; attempt++) {
      try {
        const startTime = Date.now();
        const response = await this.client.request({
          method,
          url: endpoint,
          data,
          validateStatus: () => true, // Don't throw on non-2xx status codes
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
          }
        });
        const endTime = Date.now();
        
        const { status, data: responseData, headers } = response;
        const responseTime = endTime - startTime;
        
        console.log(`   ✅ Status: ${status} | Response Time: ${responseTime}ms`);
        
        if (status === expectedStatus) {
          console.log(`   ✅ SUCCESS: ${description}`);
          if (responseData && typeof responseData === 'object') {
            console.log(`   📄 Response: ${JSON.stringify(responseData).substring(0, 200)}...`);
          }
          return { success: true, status, data: responseData };
        } else {
          console.log(`   ⚠️  Unexpected status: ${status} (expected ${expectedStatus})`);
          if (responseData) {
            console.log(`   📄 Response: ${JSON.stringify(responseData).substring(0, 200)}...`);
          }
          return { success: false, status, data: responseData };
        }
      } catch (error) {
        console.log(`   ❌ Attempt ${attempt} failed: ${error.message}`);
        if (attempt === CONFIG.RETRY_ATTEMPTS) {
          console.log(`   ❌ FAILED after ${CONFIG.RETRY_ATTEMPTS} attempts`);
          return { success: false, error: error.message };
        }
        await this.sleep(CONFIG.RETRY_DELAY);
      }
    }
  }

  async sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async runComprehensiveTests() {
    console.log('🚀 Starting Comprehensive Deployment Tests');
    console.log('==========================================');
    console.log(`API Base URL: ${this.baseUrl}`);
    console.log(`Timeout: ${CONFIG.TIMEOUT}ms`);
    console.log(`Retry Attempts: ${CONFIG.RETRY_ATTEMPTS}`);
    console.log('');

    const tests = [
      {
        endpoint: '/',
        description: 'Root API endpoint (should return API info)',
        expectedStatus: 200
      },
      {
        endpoint: '/health',
        description: 'Health check (database connectivity test)',
        expectedStatus: 200
      },
      {
        endpoint: '/health?quick=true',
        description: 'Quick health check (no database required)',
        expectedStatus: 200
      },
      {
        endpoint: '/api/diagnostics',
        description: 'Diagnostics endpoint (configuration details)',
        expectedStatus: 200
      },
      {
        endpoint: '/api/stocks?limit=1',
        description: 'Stocks endpoint (requires database and stock_symbols table)',
        expectedStatus: 200
      },
      {
        endpoint: '/api/stocks/sectors',
        description: 'Stock sectors endpoint (previously failing)',
        expectedStatus: 200
      },
      {
        endpoint: '/api/portfolio',
        description: 'Portfolio endpoint (requires authentication)',
        expectedStatus: 401 // Should fail without auth token
      },
      {
        endpoint: '/api/settings/api-keys',
        description: 'API keys endpoint (requires authentication)',
        expectedStatus: 401 // Should fail without auth token
      }
    ];

    const results = [];
    
    for (const test of tests) {
      const result = await this.testEndpoint(test.endpoint, test.description, {
        expectedStatus: test.expectedStatus
      });
      results.push({
        endpoint: test.endpoint,
        description: test.description,
        ...result
      });
    }

    console.log('\n📊 Test Results Summary');
    console.log('========================');
    
    const passed = results.filter(r => r.success).length;
    const failed = results.filter(r => !r.success).length;
    
    console.log(`✅ Passed: ${passed}`);
    console.log(`❌ Failed: ${failed}`);
    console.log(`📈 Success Rate: ${Math.round((passed / results.length) * 100)}%`);
    
    console.log('\n📋 Detailed Results:');
    results.forEach((result, index) => {
      const status = result.success ? '✅' : '❌';
      console.log(`${index + 1}. ${status} ${result.description}`);
      if (!result.success) {
        console.log(`   Error: ${result.error || `Status ${result.status}`}`);
      }
    });

    return {
      total: results.length,
      passed,
      failed,
      successRate: Math.round((passed / results.length) * 100),
      results
    };
  }
}

// Main execution
async function main() {
  const tester = new DeploymentTester(CONFIG.API_BASE_URL);
  
  try {
    const summary = await tester.runComprehensiveTests();
    
    console.log('\n🎯 Deployment Test Complete');
    console.log('============================');
    
    if (summary.successRate >= 80) {
      console.log('🎉 Deployment appears to be successful!');
      process.exit(0);
    } else {
      console.log('⚠️  Deployment may have issues - investigate failed tests');
      process.exit(1);
    }
  } catch (error) {
    console.error('❌ Deployment test failed:', error);
    process.exit(1);
  }
}

// Run if called directly
if (require.main === module) {
  main().catch(console.error);
}

module.exports = { DeploymentTester };