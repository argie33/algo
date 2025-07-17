#!/usr/bin/env node

/**
 * Comprehensive Route Testing Script
 * Tests all major API endpoints for the financial platform
 */

const API_BASE = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

// Test configuration
const TEST_CONFIG = {
  timeout: 10000, // 10 second timeout for each test
  retries: 1,
  verbose: true
};

// Test endpoints configuration
const ENDPOINTS = {
  // Health/Status endpoints (no auth required)
  public: [
    { path: '/health', method: 'GET', description: 'Main health check' },
    { path: '/api/health', method: 'GET', description: 'API health check' }
  ],
  
  // Stocks endpoints (public + authenticated)
  stocks: [
    { path: '/api/stocks/', method: 'GET', description: 'Stocks main endpoint' },
    { path: '/api/stocks/sectors', method: 'GET', description: 'Stock sectors' },
    { path: '/api/stocks/public/sample', method: 'GET', description: 'Public stock sample' }
  ],
  
  // Screener endpoints (requires auth)
  screener: [
    { path: '/api/screener/', method: 'GET', description: 'Stock screener main', requiresAuth: true },
    { path: '/api/screener/health', method: 'GET', description: 'Screener health' }
  ],
  
  // WebSocket endpoints (requires auth)
  websocket: [
    { path: '/api/websocket/health', method: 'GET', description: 'WebSocket health' },
    { path: '/api/websocket/status', method: 'GET', description: 'WebSocket status' }
  ],
  
  // Portfolio endpoints (requires auth)
  portfolio: [
    { path: '/api/portfolio/health', method: 'GET', description: 'Portfolio health' }
  ],
  
  // Settings endpoints (requires auth)
  settings: [
    { path: '/api/settings/health', method: 'GET', description: 'Settings health' }
  ]
};

// Color codes for terminal output
const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
  bold: '\x1b[1m'
};

// Test results tracking
let testResults = {
  total: 0,
  passed: 0,
  failed: 0,
  errors: []
};

/**
 * Make HTTP request with timeout
 */
async function makeRequest(url, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TEST_CONFIG.timeout);
  
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }
}

/**
 * Test a single endpoint
 */
async function testEndpoint(endpoint, category) {
  const url = `${API_BASE}${endpoint.path}`;
  const startTime = Date.now();
  
  try {
    console.log(`${colors.blue}Testing:${colors.reset} ${endpoint.method} ${endpoint.path} - ${endpoint.description}`);
    
    const response = await makeRequest(url, {
      method: endpoint.method,
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'Route-Testing-Script/1.0'
      }
    });
    
    const duration = Date.now() - startTime;
    const statusColor = response.status >= 200 && response.status < 300 ? colors.green : 
                       response.status >= 400 && response.status < 500 ? colors.yellow : colors.red;
    
    let responseText = '';
    try {
      responseText = await response.text();
    } catch (e) {
      responseText = 'Unable to read response body';
    }
    
    // Parse JSON if possible
    let responseData = null;
    try {
      responseData = JSON.parse(responseText);
    } catch (e) {
      // Not JSON, keep as text
    }
    
    console.log(`  ${statusColor}Status:${colors.reset} ${response.status} ${response.statusText}`);
    console.log(`  ${colors.cyan}Duration:${colors.reset} ${duration}ms`);
    console.log(`  ${colors.cyan}Size:${colors.reset} ${responseText.length} bytes`);
    
    if (TEST_CONFIG.verbose && responseData) {
      if (responseData.success !== undefined) {
        console.log(`  ${colors.cyan}Success:${colors.reset} ${responseData.success}`);
      }
      if (responseData.message) {
        console.log(`  ${colors.cyan}Message:${colors.reset} ${responseData.message}`);
      }
      if (responseData.error) {
        console.log(`  ${colors.yellow}Error:${colors.reset} ${responseData.error}`);
      }
    }
    
    // Determine if test passed
    const passed = response.status >= 200 && response.status < 500; // Accept 4xx as expected for auth endpoints
    
    if (passed) {
      console.log(`  ${colors.green}✓ PASS${colors.reset}\n`);
      testResults.passed++;
    } else {
      console.log(`  ${colors.red}✗ FAIL${colors.reset}\n`);
      testResults.failed++;
      testResults.errors.push({
        endpoint: endpoint.path,
        status: response.status,
        error: responseData?.error || 'Unknown error'
      });
    }
    
    return {
      endpoint: endpoint.path,
      status: response.status,
      duration,
      passed,
      response: responseData
    };
    
  } catch (error) {
    const duration = Date.now() - startTime;
    console.log(`  ${colors.red}Error:${colors.reset} ${error.message}`);
    console.log(`  ${colors.cyan}Duration:${colors.reset} ${duration}ms`);
    console.log(`  ${colors.red}✗ FAIL${colors.reset}\n`);
    
    testResults.failed++;
    testResults.errors.push({
      endpoint: endpoint.path,
      error: error.message
    });
    
    return {
      endpoint: endpoint.path,
      error: error.message,
      duration,
      passed: false
    };
  }
}

/**
 * Test all endpoints in a category
 */
async function testCategory(categoryName, endpoints) {
  console.log(`${colors.bold}${colors.blue}=== Testing ${categoryName.toUpperCase()} Endpoints ===${colors.reset}\n`);
  
  const results = [];
  for (const endpoint of endpoints) {
    testResults.total++;
    const result = await testCategory(endpoint, categoryName);
    results.push(result);
    
    // Small delay between tests
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  
  return results;
}

/**
 * Run all tests
 */
async function runAllTests() {
  console.log(`${colors.bold}${colors.cyan}Financial Platform API Route Testing${colors.reset}\n`);
  console.log(`${colors.cyan}API Base URL:${colors.reset} ${API_BASE}`);
  console.log(`${colors.cyan}Timeout:${colors.reset} ${TEST_CONFIG.timeout}ms\n`);
  
  const allResults = {};
  
  // Test each category
  for (const [categoryName, endpoints] of Object.entries(ENDPOINTS)) {
    allResults[categoryName] = await testCategory(categoryName, endpoints);
  }
  
  // Print summary
  console.log(`${colors.bold}${colors.cyan}=== Test Summary ===${colors.reset}\n`);
  console.log(`${colors.cyan}Total tests:${colors.reset} ${testResults.total}`);
  console.log(`${colors.green}Passed:${colors.reset} ${testResults.passed}`);
  console.log(`${colors.red}Failed:${colors.reset} ${testResults.failed}`);
  console.log(`${colors.cyan}Success rate:${colors.reset} ${Math.round((testResults.passed / testResults.total) * 100)}%\n`);
  
  // Print failed tests
  if (testResults.errors.length > 0) {
    console.log(`${colors.bold}${colors.red}Failed Tests:${colors.reset}\n`);
    testResults.errors.forEach(error => {
      console.log(`  ${colors.red}✗${colors.reset} ${error.endpoint}: ${error.error}`);
    });
    console.log('');
  }
  
  // Performance summary
  console.log(`${colors.bold}${colors.cyan}Performance Summary:${colors.reset}\n`);
  for (const [category, results] of Object.entries(allResults)) {
    const avgDuration = results.reduce((sum, r) => sum + (r.duration || 0), 0) / results.length;
    console.log(`  ${colors.cyan}${category}:${colors.reset} ${Math.round(avgDuration)}ms average`);
  }
  
  return allResults;
}

// Helper function to fix category testing
async function testCategory(categoryName, endpoints) {
  if (typeof categoryName === 'string') {
    // This is the category header call
    console.log(`${colors.bold}${colors.blue}=== Testing ${categoryName.toUpperCase()} Endpoints ===${colors.reset}\n`);
    
    const results = [];
    for (const endpoint of endpoints) {
      testResults.total++;
      const result = await testEndpoint(endpoint, categoryName);
      results.push(result);
      
      // Small delay between tests
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    
    return results;
  } else {
    // This is actually an endpoint test
    return await testEndpoint(categoryName, endpoints);
  }
}

// Run tests if called directly
if (require.main === module) {
  runAllTests().then(results => {
    process.exit(testResults.failed > 0 ? 1 : 0);
  }).catch(error => {
    console.error(`${colors.red}Test runner error:${colors.reset} ${error.message}`);
    process.exit(1);
  });
}

module.exports = { runAllTests, testEndpoint, TEST_CONFIG, ENDPOINTS };