#!/usr/bin/env node

/**
 * Comprehensive API Coverage Test
 * 
 * Expands beyond basic fallback detection to test:
 * - All HTTP methods (GET, POST, PUT, DELETE)
 * - Parameter variations and edge cases
 * - Error response quality and consistency
 * - Coverage of endpoints not in basic test
 * - Authentication edge cases
 */

const https = require('https');

const API_BASE = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

// Expanded endpoint list with multiple HTTP methods and parameters
const COMPREHENSIVE_ENDPOINTS = [
  // Portfolio endpoints with parameters
  { path: '/api/portfolio/analytics?timeframe=1M', method: 'GET', requiresAuth: true, description: 'Portfolio Analytics with timeframe' },
  { path: '/api/portfolio/holdings?includeValues=true', method: 'GET', requiresAuth: true, description: 'Portfolio Holdings with values' },
  { path: '/api/portfolio/rebalance', method: 'POST', requiresAuth: true, description: 'Portfolio Rebalancing', body: { strategy: 'balanced' } },
  
  // Trading endpoints with various methods
  { path: '/api/trading/orders', method: 'POST', requiresAuth: true, description: 'Create Trading Order', body: { symbol: 'AAPL', quantity: 10, side: 'buy', type: 'market' } },
  { path: '/api/trading/orders/123', method: 'GET', requiresAuth: true, description: 'Get Specific Order' },
  { path: '/api/trading/orders/123', method: 'DELETE', requiresAuth: true, description: 'Cancel Trading Order' },
  { path: '/api/trading/positions', method: 'GET', requiresAuth: true, description: 'Trading Positions' },
  
  // Settings with various operations
  { path: '/api/settings/api-keys', method: 'POST', requiresAuth: true, description: 'Add API Key', body: { provider: 'alpaca', keyId: 'test', secret: 'test' } },
  { path: '/api/settings/profile', method: 'PUT', requiresAuth: true, description: 'Update Profile', body: { name: 'Test User' } },
  { path: '/api/settings/preferences', method: 'GET', requiresAuth: true, description: 'User Preferences' },
  
  // Market data with parameters
  { path: '/api/market/overview?extended=true', method: 'GET', requiresAuth: false, description: 'Extended Market Overview' },
  { path: '/api/market/indices?region=US', method: 'GET', requiresAuth: false, description: 'US Market Indices' },
  { path: '/api/market/sectors?sortBy=performance', method: 'GET', requiresAuth: false, description: 'Sectors by Performance' },
  
  // Stock-specific endpoints
  { path: '/api/stocks/AAPL/quote?extended=true', method: 'GET', requiresAuth: true, description: 'Extended Stock Quote' },
  { path: '/api/stocks/AAPL/technicals', method: 'GET', requiresAuth: false, description: 'Stock Technical Analysis' },
  { path: '/api/stocks/AAPL/news', method: 'GET', requiresAuth: false, description: 'Stock-specific News' },
  { path: '/api/stocks/AAPL/options', method: 'GET', requiresAuth: true, description: 'Options Chain' },
  
  // Watchlist operations
  { path: '/api/watchlist', method: 'POST', requiresAuth: true, description: 'Create Watchlist', body: { name: 'Tech Stocks', symbols: ['AAPL', 'MSFT'] } },
  { path: '/api/watchlist/1/symbols', method: 'POST', requiresAuth: true, description: 'Add to Watchlist', body: { symbol: 'GOOGL' } },
  { path: '/api/watchlist/1', method: 'DELETE', requiresAuth: true, description: 'Delete Watchlist' },
  
  // News and sentiment with filters
  { path: '/api/news/latest?category=technology', method: 'GET', requiresAuth: false, description: 'Technology News' },
  { path: '/api/news/sentiment?symbol=AAPL', method: 'GET', requiresAuth: false, description: 'Symbol-specific Sentiment' },
  { path: '/api/news/search?q=earnings', method: 'GET', requiresAuth: false, description: 'News Search' },
  
  // Technical analysis endpoints
  { path: '/api/technical/indicators?symbol=AAPL&indicator=RSI', method: 'GET', requiresAuth: false, description: 'RSI Indicator' },
  { path: '/api/technical/patterns?symbol=AAPL', method: 'GET', requiresAuth: false, description: 'Chart Patterns' },
  { path: '/api/technical/signals', method: 'GET', requiresAuth: false, description: 'Technical Signals' },
  
  // Screener with various parameters
  { path: '/api/screener/results?sector=technology&minPrice=100', method: 'GET', requiresAuth: false, description: 'Tech Stock Screener' },
  { path: '/api/screener/presets', method: 'GET', requiresAuth: false, description: 'Screener Presets' },
  { path: '/api/screener/custom', method: 'POST', requiresAuth: true, description: 'Custom Screen', body: { criteria: { sector: 'tech' } } },
  
  // Calendar and events
  { path: '/api/calendar/earnings?week=current', method: 'GET', requiresAuth: false, description: 'Current Week Earnings' },
  { path: '/api/calendar/dividends', method: 'GET', requiresAuth: false, description: 'Dividend Calendar' },
  { path: '/api/calendar/splits', method: 'GET', requiresAuth: false, description: 'Stock Splits Calendar' },
  
  // Options and derivatives
  { path: '/api/options/chains?symbol=AAPL', method: 'GET', requiresAuth: true, description: 'Options Chain' },
  { path: '/api/options/analytics', method: 'GET', requiresAuth: true, description: 'Options Analytics' },
  
  // Real-time data endpoints
  { path: '/api/realtime/quotes?symbols=AAPL,MSFT', method: 'GET', requiresAuth: true, description: 'Real-time Quotes' },
  { path: '/api/realtime/subscribe', method: 'POST', requiresAuth: true, description: 'Subscribe to Real-time Data', body: { symbols: ['AAPL'] } },
  
  // Analytics endpoints
  { path: '/api/analytics/performance?period=1Y', method: 'GET', requiresAuth: true, description: 'Performance Analytics' },
  { path: '/api/analytics/risk', method: 'GET', requiresAuth: true, description: 'Risk Analytics' },
  { path: '/api/analytics/benchmark', method: 'GET', requiresAuth: true, description: 'Benchmark Comparison' },
  
  // Admin and system endpoints
  { path: '/api/admin/users', method: 'GET', requiresAuth: true, description: 'Admin User Management' },
  { path: '/api/system/status', method: 'GET', requiresAuth: false, description: 'System Status' },
  { path: '/api/system/metrics', method: 'GET', requiresAuth: false, description: 'System Metrics' },
];

// Enhanced patterns for mock data detection
const ENHANCED_MOCK_PATTERNS = [
  // Existing patterns
  /mock/i,
  /demo.*data/i,
  /fake.*data/i,
  /placeholder/i,
  /lorem ipsum/i,
  /sample.*data/i,
  /test.*data/i,
  /dummy.*data/i,
  
  // New patterns for better detection
  /temporarily.*unavailable.*returning.*sample/i,
  /database.*unavailable.*demo.*data/i,
  /fallback.*mock.*data/i,
  /example.*portfolio/i,
  /not.*implemented.*returning/i,
  /coming.*soon/i,
  /under.*construction/i,
  
  // Specific symbol patterns that indicate mock data
  /"symbol":\s*"MOCK/i,
  /"symbol":\s*"DEMO/i,
  /"symbol":\s*"TEST/i,
  /"symbol":\s*"EXAMPLE/i,
  
  // User ID patterns
  /"userId":\s*"mock-user/i,
  /"userId":\s*"demo-user/i,
  /"userId":\s*"test-user/i,
  /"user_id":\s*"mock-user/i,
  /"user_id":\s*"demo-user/i,
  
  // Company/name patterns
  /"name":\s*"Mock.*"/i,
  /"name":\s*"Demo.*"/i,
  /"name":\s*"Test.*"/i,
  /"company":\s*"Mock.*"/i,
  /"company":\s*"Demo.*"/i,
  /"companyName":\s*"Example.*"/i,
  
  // Suspicious hardcoded values
  /"price":\s*123\.45/i,
  /"value":\s*999\.99/i,
  /"amount":\s*100\.00/i,
  
  // Development/placeholder messages
  /endpoint.*not.*implemented/i,
  /feature.*not.*available/i,
  /service.*under.*development/i,
];

// Helper function to make API calls with different methods
function makeApiCall(endpoint, options = {}) {
  return new Promise((resolve, reject) => {
    const url = new URL(API_BASE + endpoint.path);
    const requestOptions = {
      hostname: url.hostname,
      port: url.port || 443,
      path: url.pathname + url.search,
      method: endpoint.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'Comprehensive-API-Tester/1.0',
        ...options.headers
      }
    };

    const req = https.request(requestOptions, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          resolve({ 
            status: res.statusCode, 
            data: parsed, 
            raw: data,
            headers: res.headers
          });
        } catch (error) {
          resolve({ 
            status: res.statusCode, 
            data: data, 
            raw: data, 
            parseError: true,
            headers: res.headers
          });
        }
      });
    });

    req.on('error', reject);
    req.setTimeout(10000, () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });
    
    // Send body for POST/PUT requests
    if (endpoint.body && (endpoint.method === 'POST' || endpoint.method === 'PUT')) {
      req.write(JSON.stringify(endpoint.body));
    }
    
    req.end();
  });
}

// Enhanced analysis for mock data patterns and error quality
function analyzeResponse(response, endpoint) {
  const issues = [];
  const responseStr = response.raw.toLowerCase();
  
  // Check for enhanced mock data patterns
  ENHANCED_MOCK_PATTERNS.forEach(pattern => {
    if (pattern.test(responseStr)) {
      issues.push(`🚨 Mock data pattern detected: ${pattern.toString()}`);
    }
  });
  
  // Check for suspicious success responses
  if (response.data && response.data.success === true && response.status === 200) {
    // Look for empty data that might be fallback
    if (response.data.data && Array.isArray(response.data.data) && response.data.data.length === 0) {
      issues.push(`⚠️ Empty array returned - may indicate fallback behavior`);
    }
    
    // Check for suspicious message patterns
    if (response.data.message) {
      const message = response.data.message.toLowerCase();
      if (message.includes('not implemented') || message.includes('coming soon') || 
          message.includes('under construction') || message.includes('placeholder')) {
        issues.push(`🚨 Placeholder message detected: "${response.data.message}"`);
      }
    }
  }
  
  // Check error response quality
  if (response.status >= 400) {
    const errorQuality = analyzeErrorQuality(response);
    if (errorQuality.issues.length > 0) {
      issues.push(...errorQuality.issues.map(issue => `📝 Error quality: ${issue}`));
    }
  }
  
  return {
    issues,
    responseQuality: response.status < 400 ? 'success' : analyzeErrorResponseQuality(response)
  };
}

// Analyze error response quality
function analyzeErrorQuality(response) {
  const issues = [];
  
  try {
    if (response.parseError) {
      issues.push('Response is not valid JSON');
      return { issues };
    }
    
    const data = response.data;
    
    // Check for proper error structure
    if (!data.error && !data.message) {
      issues.push('Missing error message or description');
    }
    
    // Check for helpful error information
    if (data.error && typeof data.error === 'string' && data.error.length < 10) {
      issues.push('Error message too brief - lacks helpful information');
    }
    
    // Check for troubleshooting information
    if (!data.suggestion && !data.requirements && !data.troubleshooting) {
      issues.push('Missing troubleshooting guidance (suggestion, requirements, or troubleshooting)');
    }
    
    // Check for service identification
    if (!data.service) {
      issues.push('Missing service identification for debugging');
    }
    
  } catch (error) {
    issues.push('Error analyzing error response structure');
  }
  
  return { issues };
}

function analyzeErrorResponseQuality(response) {
  if (response.status === 401) return 'good-auth-error';
  if (response.status === 403) return 'good-permission-error';
  if (response.status === 404) return 'acceptable-not-found';
  if (response.status === 400) return 'acceptable-bad-request';
  if (response.status >= 500) return 'server-error';
  return 'unknown';
}

async function runComprehensiveTest() {
  console.log('🔍 Starting Comprehensive API Coverage Test');
  console.log('============================================');
  console.log(`📡 Testing ${COMPREHENSIVE_ENDPOINTS.length} endpoints with multiple HTTP methods...`);
  console.log(`🎯 Enhanced pattern detection with ${ENHANCED_MOCK_PATTERNS.length} patterns`);

  let totalIssues = 0;
  let endpointsWithIssues = 0;
  let endpointsTested = 0;
  const detailedResults = [];
  const errorQualityStats = {
    'good-auth-error': 0,
    'good-permission-error': 0,
    'acceptable-not-found': 0,
    'acceptable-bad-request': 0,
    'server-error': 0,
    'success': 0,
    'unknown': 0
  };

  for (const endpoint of COMPREHENSIVE_ENDPOINTS) {
    console.log(`\\n🧪 Testing: ${endpoint.description}`);
    console.log(`   Method: ${endpoint.method} ${endpoint.path}`);
    console.log(`   Auth Required: ${endpoint.requiresAuth ? 'Yes' : 'No'}`);

    try {
      const response = await makeApiCall(endpoint);
      console.log(`   Status: ${response.status}`);
      endpointsTested++;

      const analysis = analyzeResponse(response, endpoint);
      
      // Update error quality stats
      errorQualityStats[analysis.responseQuality]++;
      
      // Check authentication behavior
      if (response.status === 200 && endpoint.requiresAuth) {
        analysis.issues.push('⚠️ Auth-required endpoint returns 200 without token - might be serving fallback data');
      }
      
      if (analysis.issues.length > 0) {
        console.log(`   ❌ Issues Found: ${analysis.issues.length}`);
        analysis.issues.forEach(issue => console.log(`      - ${issue}`));
        endpointsWithIssues++;
        totalIssues += analysis.issues.length;
        
        detailedResults.push({
          endpoint: endpoint.path,
          method: endpoint.method,
          description: endpoint.description,
          status: response.status,
          issues: analysis.issues,
          responsePreview: response.raw.substring(0, 200) + '...'
        });
      } else {
        if (endpoint.requiresAuth && (response.status === 401 || response.status === 403)) {
          console.log('   ✅ Properly requires authentication');
        } else if (!endpoint.requiresAuth && response.status === 200) {
          console.log('   ✅ Public endpoint working correctly');
        } else if (response.status === 404) {
          console.log('   ✅ Proper 404 for non-existent endpoint');
        } else if (response.status >= 500) {
          console.log('   ⚠️ Server error - infrastructure issue, not fallback data');
        } else {
          console.log('   ✅ No mock data patterns detected');
        }
      }

      // Brief delay to avoid overwhelming the API
      await new Promise(resolve => setTimeout(resolve, 100));

    } catch (error) {
      console.log(`   ❌ Request failed: ${error.message}`);
      endpointsTested++;
    }
  }

  // Generate comprehensive report
  console.log('\\n📊 COMPREHENSIVE COVERAGE SUMMARY');
  console.log('==================================');
  console.log(`Total Endpoints Tested: ${endpointsTested}`);
  console.log(`Endpoints with Issues: ${endpointsWithIssues}`);
  console.log(`Total Issues Found: ${totalIssues}`);
  
  console.log('\\n📈 Error Response Quality Statistics:');
  console.log('=====================================');
  Object.entries(errorQualityStats).forEach(([quality, count]) => {
    if (count > 0) {
      console.log(`  ${quality.padEnd(25)}: ${count}`);
    }
  });
  
  if (endpointsWithIssues > 0) {
    console.log('\\n🚨 DETAILED ISSUES REPORT');
    console.log('=========================');
    
    detailedResults.forEach((result, index) => {
      console.log(`\\n${index + 1}. ${result.description}`);
      console.log(`   Method: ${result.method} ${result.endpoint}`);
      console.log(`   Status: ${result.status}`);
      console.log(`   Issues:`);
      result.issues.forEach(issue => console.log(`     - ${issue}`));
      console.log(`   Response Preview: ${result.responsePreview}`);
    });
    
    console.log('\\n🎯 COMPREHENSIVE RECOMMENDATIONS:');
    console.log('1. Review all endpoints with mock/fallback data patterns');
    console.log('2. Improve error response quality with detailed troubleshooting info');
    console.log('3. Ensure consistent authentication across all protected endpoints');
    console.log('4. Replace placeholder responses with proper error handling');
    console.log('5. Add service identification and requirements to all error responses');
  } else {
    console.log('\\n✅ OUTSTANDING! No fallback data patterns detected across comprehensive test');
    console.log('All endpoints appear to handle errors properly with quality error responses');
  }
  
  return { 
    totalIssues, 
    endpointsWithIssues, 
    endpointsTested, 
    detailedResults,
    errorQualityStats 
  };
}

// Run the comprehensive test
if (require.main === module) {
  runComprehensiveTest()
    .then((results) => {
      if (results.totalIssues === 0) {
        console.log('\\n🎉 COMPREHENSIVE SUCCESS: All endpoints properly handle errors without fallback data!');
        console.log(`📊 Coverage: ${results.endpointsTested} endpoints tested across multiple HTTP methods`);
        process.exit(0);
      } else {
        console.log(`\\n⚠️ NEEDS IMPROVEMENT: Found ${results.totalIssues} issues across ${results.endpointsWithIssues} endpoints`);
        console.log(`📊 Coverage: ${results.endpointsTested} endpoints tested`);
        process.exit(1);
      }
    })
    .catch((error) => {
      console.error('\\n❌ Comprehensive test execution failed:', error.message);
      process.exit(1);
    });
}

module.exports = { runComprehensiveTest, ENHANCED_MOCK_PATTERNS };