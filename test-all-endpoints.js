#!/usr/bin/env node

/**
 * Comprehensive API Endpoint Testing Script
 * Tests all main routes for basic functionality after SSL fix deployment
 */

const https = require('https');
const BASE_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

// Test endpoints configuration
const ENDPOINTS = [
  // Infrastructure endpoints
  { path: '/api/health-full?quick=true', name: 'Health Check (Quick)', public: true },
  { path: '/api/health-full', name: 'Health Check (Full)', public: true },
  { path: '/api/diagnostics/secrets-manager', name: 'Secrets Manager Diagnostic', public: true },
  
  // Market data endpoints
  { path: '/api/market', name: 'Market Root', public: true },
  { path: '/api/market/debug', name: 'Market Debug', public: true },
  { path: '/api/market/health', name: 'Market Health', public: true },
  { path: '/api/market/overview', name: 'Market Overview', public: true },
  
  // Stock data endpoints
  { path: '/api/stocks/sectors', name: 'Stock Sectors', public: true },
  { path: '/api/stocks/public/sample?limit=3', name: 'Public Stock Sample', public: true },
  
  // Core data endpoints
  { path: '/api/data', name: 'Data Management', public: true },
  { path: '/api/market-data', name: 'Market Data', public: true },
  
  // Authentication required endpoints (will test response format)
  { path: '/api/portfolio', name: 'Portfolio', public: false },
  { path: '/api/watchlist', name: 'Watchlist', public: false },
  { path: '/api/settings', name: 'Settings', public: false },
  { path: '/api/screener', name: 'Screener', public: false },
  { path: '/api/dashboard/summary', name: 'Dashboard Summary', public: false },
  { path: '/api/technical', name: 'Technical Analysis', public: false },
  { path: '/api/signals', name: 'Trading Signals', public: false },
  { path: '/api/news/articles', name: 'News Articles', public: false },
  { path: '/api/sentiment/trending', name: 'Sentiment Trending', public: false },
  { path: '/api/alerts', name: 'Alerts', public: false },
  { path: '/api/metrics', name: 'Metrics', public: false },
  { path: '/api/advanced', name: 'Advanced Trading', public: false },
  { path: '/api/live-data', name: 'Live Data', public: false },
  { path: '/api/websocket', name: 'WebSocket', public: false }
];

// Test result tracking
let results = {
  total: 0,
  passed: 0,
  failed: 0,
  errors: []
};

// Colors for terminal output
const colors = {
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  magenta: '\x1b[35m',
  cyan: '\x1b[36m',
  white: '\x1b[37m',
  reset: '\x1b[0m'
};

function makeRequest(url) {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();
    
    const req = https.get(url, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        const duration = Date.now() - startTime;
        
        try {
          const jsonData = JSON.parse(data);
          resolve({
            statusCode: res.statusCode,
            duration,
            data: jsonData,
            headers: res.headers
          });
        } catch (parseError) {
          resolve({
            statusCode: res.statusCode,
            duration,
            data: data,
            parseError: parseError.message,
            headers: res.headers
          });
        }
      });
    });
    
    req.on('error', (error) => {
      reject({
        error: error.message,
        duration: Date.now() - startTime
      });
    });
    
    req.setTimeout(10000, () => {
      req.destroy();
      reject({
        error: 'Request timeout',
        duration: Date.now() - startTime
      });
    });
  });
}

function evaluateResponse(endpoint, response) {
  const evaluation = {
    passed: false,
    issues: [],
    insights: []
  };

  // Check basic response structure
  if (response.statusCode === 200) {
    evaluation.insights.push('✅ HTTP 200 OK');
    
    if (response.data && typeof response.data === 'object') {
      evaluation.insights.push('✅ Valid JSON response');
      
      // Check for error indicators in successful responses
      if (response.data.error) {
        evaluation.issues.push('⚠️ Contains error field despite 200 status');
      }
      
      // Check for database connectivity indicators
      if (response.data.database) {
        if (response.data.database.status === 'connected') {
          evaluation.insights.push('✅ Database connected');
        } else {
          evaluation.issues.push('❌ Database not connected');
        }
      }
      
      // Check for circuit breaker indicators
      if (typeof response.data === 'string' && response.data.includes('Circuit breaker')) {
        evaluation.issues.push('⚠️ Circuit breaker active');
      }
      
      // Check for mock data indicators
      if (response.data.note && response.data.note.includes('mock')) {
        evaluation.issues.push('⚠️ Using mock data');
      }
      
      evaluation.passed = true;
    } else {
      evaluation.issues.push('❌ Invalid JSON response');
    }
  } else if (response.statusCode === 401) {
    if (endpoint.public) {
      evaluation.issues.push('❌ Unexpected authentication required');
    } else {
      evaluation.insights.push('✅ Expected authentication required');
      evaluation.passed = true;
    }
  } else if (response.statusCode === 403) {
    evaluation.issues.push('❌ Forbidden - check permissions');
  } else if (response.statusCode === 404) {
    evaluation.issues.push('❌ Not found - route missing');
  } else if (response.statusCode === 500) {
    evaluation.issues.push('❌ Internal server error');
  } else {
    evaluation.issues.push(`❌ Unexpected status code: ${response.statusCode}`);
  }

  return evaluation;
}

async function testEndpoint(endpoint) {
  const url = `${BASE_URL}${endpoint.path}`;
  
  console.log(`${colors.cyan}Testing:${colors.reset} ${endpoint.name}`);
  console.log(`${colors.blue}URL:${colors.reset} ${url}`);
  
  try {
    const response = await makeRequest(url);
    const evaluation = evaluateResponse(endpoint, response);
    
    console.log(`${colors.yellow}Status:${colors.reset} ${response.statusCode}`);
    console.log(`${colors.yellow}Duration:${colors.reset} ${response.duration}ms`);
    
    // Display insights
    if (evaluation.insights.length > 0) {
      evaluation.insights.forEach(insight => {
        console.log(`  ${insight}`);
      });
    }
    
    // Display issues
    if (evaluation.issues.length > 0) {
      evaluation.issues.forEach(issue => {
        console.log(`  ${issue}`);
      });
    }
    
    if (evaluation.passed) {
      console.log(`${colors.green}✅ PASSED${colors.reset}`);
      results.passed++;
    } else {
      console.log(`${colors.red}❌ FAILED${colors.reset}`);
      results.failed++;
      results.errors.push({
        endpoint: endpoint.name,
        url: url,
        statusCode: response.statusCode,
        issues: evaluation.issues
      });
    }
    
  } catch (error) {
    console.log(`${colors.red}❌ ERROR: ${error.error || error.message}${colors.reset}`);
    results.failed++;
    results.errors.push({
      endpoint: endpoint.name,
      url: url,
      error: error.error || error.message
    });
  }
  
  console.log(''); // Empty line for separation
}

async function runAllTests() {
  console.log(`${colors.magenta}🚀 Starting comprehensive API endpoint testing...${colors.reset}`);
  console.log(`${colors.magenta}Base URL: ${BASE_URL}${colors.reset}`);
  console.log(`${colors.magenta}Total endpoints: ${ENDPOINTS.length}${colors.reset}`);
  console.log('');
  
  results.total = ENDPOINTS.length;
  
  for (const endpoint of ENDPOINTS) {
    await testEndpoint(endpoint);
  }
  
  // Summary
  console.log(`${colors.magenta}📊 Test Results Summary${colors.reset}`);
  console.log(`${colors.green}✅ Passed: ${results.passed}${colors.reset}`);
  console.log(`${colors.red}❌ Failed: ${results.failed}${colors.reset}`);
  console.log(`${colors.yellow}📈 Success Rate: ${((results.passed / results.total) * 100).toFixed(1)}%${colors.reset}`);
  
  if (results.errors.length > 0) {
    console.log('');
    console.log(`${colors.red}❌ Failed Endpoints:${colors.reset}`);
    results.errors.forEach(error => {
      console.log(`  • ${error.endpoint}: ${error.error || error.issues.join(', ')}`);
    });
  }
  
  console.log('');
  console.log(`${colors.cyan}🔧 Next Steps:${colors.reset}`);
  
  if (results.failed > 0) {
    console.log('  • Fix failed endpoints before production deployment');
    console.log('  • Check database connectivity and circuit breaker status');
    console.log('  • Verify authentication configuration');
  } else {
    console.log('  • All endpoints are responding correctly!');
    console.log('  • System is ready for production traffic');
  }
  
  process.exit(results.failed > 0 ? 1 : 0);
}

// Run the tests
runAllTests().catch(console.error);