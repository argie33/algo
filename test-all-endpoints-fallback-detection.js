#!/usr/bin/env node

/**
 * Comprehensive Fallback Detection Test
 * 
 * This script tests all API endpoints to detect:
 * 1. Endpoints that return fake/mock data when they should return errors
 * 2. Fallback patterns that provide misleading mock responses
 * 3. Services that return success=true with dummy data instead of proper errors
 * 4. Any remaining hardcoded mock data responses
 */

const https = require('https');

const API_BASE = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

// All known API endpoints to test
const ENDPOINTS_TO_TEST = [
  // Authentication required endpoints
  { path: '/api/portfolio/analytics', requiresAuth: true, description: 'Portfolio Analytics' },
  { path: '/api/portfolio/holdings', requiresAuth: true, description: 'Portfolio Holdings' },
  { path: '/api/portfolio/performance', requiresAuth: true, description: 'Portfolio Performance' },
  { path: '/api/portfolio/risk-analysis', requiresAuth: true, description: 'Portfolio Risk Analysis' },
  { path: '/api/settings/profile', requiresAuth: true, description: 'User Settings Profile' },
  { path: '/api/settings/api-keys', requiresAuth: true, description: 'API Keys Management' },
  { path: '/api/stocks/AAPL/quote', requiresAuth: true, description: 'Stock Quote' },
  { path: '/api/trading/orders', requiresAuth: true, description: 'Trading Orders' },
  { path: '/api/trading/positions', requiresAuth: true, description: 'Trading Positions' },
  { path: '/api/watchlist', requiresAuth: true, description: 'User Watchlist' },
  
  // Public endpoints that might have fallback data
  { path: '/api/market/overview', requiresAuth: false, description: 'Market Overview' },
  { path: '/api/market/indices', requiresAuth: false, description: 'Market Indices' },
  { path: '/api/market/sectors', requiresAuth: false, description: 'Market Sectors' },
  { path: '/api/news/latest', requiresAuth: false, description: 'Latest News' },
  { path: '/api/news/sentiment', requiresAuth: false, description: 'News Sentiment' },
  { path: '/api/technical/indicators', requiresAuth: false, description: 'Technical Indicators' },
  { path: '/api/screener/results', requiresAuth: false, description: 'Stock Screener' },
  { path: '/api/calendar/earnings', requiresAuth: false, description: 'Earnings Calendar' },
  { path: '/api/commodities/prices', requiresAuth: false, description: 'Commodity Prices' },
  { path: '/api/crypto/overview', requiresAuth: false, description: 'Crypto Overview' },
  
  // Health and system endpoints
  { path: '/health', requiresAuth: false, description: 'System Health' },
  { path: '/api/health', requiresAuth: false, description: 'API Health' },
];

// Patterns that indicate fake/mock data responses
const MOCK_DATA_PATTERNS = [
  /mock/i,
  /demo.*data/i,
  /fake.*data/i,
  /placeholder/i,
  /lorem ipsum/i,
  /sample.*data/i,
  /test.*data/i,
  /"symbol":\s*"MOCK/i,
  /"symbol":\s*"DEMO/i,
  /"symbol":\s*"TEST/i,
  /example.*portfolio/i,
  /dummy.*data/i,
  /"userId":\s*"mock-user/i,
  /"userId":\s*"demo-user/i,
  /"name":\s*"Mock.*"/i,
  /"name":\s*"Demo.*"/i,
  /"company":\s*"Mock.*"/i,
  /"company":\s*"Demo.*"/i,
  /temporarily.*unavailable.*returning.*sample/i,
  /database.*unavailable.*demo.*data/i,
  /fallback.*mock.*data/i,
];

// Helper function to make API calls
function makeApiCall(path, options = {}) {
  return new Promise((resolve, reject) => {
    const url = new URL(API_BASE + path);
    const requestOptions = {
      hostname: url.hostname,
      port: url.port || 443,
      path: url.pathname + url.search,
      method: options.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      }
    };

    const req = https.request(requestOptions, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          resolve({ status: res.statusCode, data: parsed, raw: data });
        } catch (error) {
          resolve({ status: res.statusCode, data: data, raw: data, parseError: true });
        }
      });
    });

    req.on('error', reject);
    req.setTimeout(10000, () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });
    
    req.end();
  });
}

// Analyze response for mock data patterns
function analyzeMockDataPatterns(response, endpoint) {
  const issues = [];
  const responseStr = response.raw.toLowerCase();
  
  // Check for mock data patterns
  MOCK_DATA_PATTERNS.forEach(pattern => {
    if (pattern.test(responseStr)) {
      issues.push(`Contains mock data pattern: ${pattern.toString()}`);
    }
  });
  
  // Check for suspicious success responses that might be fallback data
  if (response.data && response.data.success === true && response.status === 200) {
    // Look for signs this is fallback data masquerading as real data
    if (responseStr.includes('demo') || responseStr.includes('mock') || responseStr.includes('sample')) {
      issues.push('Returns success=true but contains demo/mock/sample data');
    }
    
    // Check for empty or suspicious data patterns
    if (response.data.data) {
      const dataStr = JSON.stringify(response.data.data).toLowerCase();
      if (dataStr.includes('[]') && dataStr.length < 50) {
        issues.push('Returns empty arrays - might be fallback behavior');
      }
      
      // Look for hardcoded values that might be mock data
      if (dataStr.includes('123.45') || dataStr.includes('999.99') || dataStr.includes('100.00')) {
        issues.push('Contains suspicious hardcoded decimal values');
      }
    }
  }
  
  return issues;
}

async function testAllEndpoints() {
  console.log('🔍 Starting Comprehensive Fallback Detection Test');
  console.log('==================================================');
  console.log(`📡 Testing ${ENDPOINTS_TO_TEST.length} endpoints for mock data patterns...`);

  let totalIssues = 0;
  let endpointsWithIssues = 0;
  const detailedResults = [];

  for (const endpoint of ENDPOINTS_TO_TEST) {
    console.log(`\n🧪 Testing: ${endpoint.description}`);
    console.log(`   Path: ${endpoint.path}`);
    console.log(`   Auth Required: ${endpoint.requiresAuth ? 'Yes' : 'No'}`);

    try {
      // Test without authentication first
      const response = await makeApiCall(endpoint.path);
      console.log(`   Status: ${response.status}`);

      const issues = analyzeMockDataPatterns(response, endpoint);
      
      if (response.status === 200 && endpoint.requiresAuth) {
        issues.push('⚠️  Auth-required endpoint returns 200 without token - might be serving fallback data');
      }
      
      if (issues.length > 0) {
        console.log(`   ❌ Issues Found: ${issues.length}`);
        issues.forEach(issue => console.log(`      - ${issue}`));
        endpointsWithIssues++;
        totalIssues += issues.length;
        
        detailedResults.push({
          endpoint: endpoint.path,
          description: endpoint.description,
          status: response.status,
          issues: issues,
          responsePreview: response.raw.substring(0, 200) + '...'
        });
      } else {
        if (endpoint.requiresAuth && response.status === 401) {
          console.log('   ✅ Properly requires authentication');
        } else if (!endpoint.requiresAuth && response.status === 200) {
          console.log('   ✅ Public endpoint working correctly');
        } else if (response.status >= 500) {
          console.log('   ⚠️  Server error - needs investigation');
        } else {
          console.log('   ✅ No mock data patterns detected');
        }
      }

      // Brief delay to avoid overwhelming the API
      await new Promise(resolve => setTimeout(resolve, 100));

    } catch (error) {
      console.log(`   ❌ Request failed: ${error.message}`);
    }
  }

  console.log('\n📊 FALLBACK DETECTION SUMMARY');
  console.log('=============================');
  console.log(`Total Endpoints Tested: ${ENDPOINTS_TO_TEST.length}`);
  console.log(`Endpoints with Issues: ${endpointsWithIssues}`);
  console.log(`Total Issues Found: ${totalIssues}`);
  
  if (endpointsWithIssues > 0) {
    console.log('\n🚨 DETAILED ISSUES REPORT');
    console.log('=========================');
    
    detailedResults.forEach((result, index) => {
      console.log(`\n${index + 1}. ${result.description}`);
      console.log(`   Endpoint: ${result.endpoint}`);
      console.log(`   Status: ${result.status}`);
      console.log(`   Issues:`);
      result.issues.forEach(issue => console.log(`     - ${issue}`));
      console.log(`   Response Preview: ${result.responsePreview}`);
    });
    
    console.log('\n🎯 RECOMMENDED ACTIONS:');
    console.log('1. Review endpoints with mock data patterns');
    console.log('2. Replace fallback data with proper error responses');
    console.log('3. Ensure auth-required endpoints return 401/403 instead of demo data');
    console.log('4. Remove any hardcoded mock values from responses');
    console.log('5. Update error handling to use res.error() middleware consistently');
  } else {
    console.log('\n✅ EXCELLENT! No fallback data patterns detected');
    console.log('All endpoints appear to handle errors properly without fake data fallbacks');
  }
  
  return { totalIssues, endpointsWithIssues, detailedResults };
}

// Run the comprehensive test
if (require.main === module) {
  testAllEndpoints()
    .then((results) => {
      if (results.totalIssues === 0) {
        console.log('\n🎉 SUCCESS: All endpoints properly handle errors without fallback data!');
        process.exit(0);
      } else {
        console.log(`\n⚠️  NEEDS WORK: Found ${results.totalIssues} issues across ${results.endpointsWithIssues} endpoints`);
        process.exit(1);
      }
    })
    .catch((error) => {
      console.error('\n❌ Test execution failed:', error.message);
      process.exit(1);
    });
}

module.exports = { testAllEndpoints, MOCK_DATA_PATTERNS };