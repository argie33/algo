#!/usr/bin/env node
/**
 * API Contract Verification Tool
 * Systematically tests frontend-backend API contracts
 */

const https = require('https');
const http = require('http');

// Configuration
const API_BASE_URL = 'http://localhost:3001';
const TIMEOUT = 5000;

// Extract API endpoints from frontend code
const FRONTEND_API_CALLS = [
  // Portfolio endpoints (fix paths to match actual API)
  { method: 'GET', path: '/api/portfolio/api-keys', frontend: 'getApiKeys' },
  { method: 'POST', path: '/api/portfolio/api-keys', frontend: 'addApiKey', testData: { brokerName: 'test', apiKey: 'test123', apiSecret: 'secret123', sandbox: true } },
  
  // Market endpoints  
  { method: 'GET', path: '/api/market/overview', frontend: 'getMarketOverview' },
  { method: 'GET', path: '/market/indices', frontend: 'getMarketIndices' },
  { method: 'GET', path: '/market/sectors', frontend: 'getMarketSectors' },
  { method: 'GET', path: '/market/indicators', frontend: 'getMarketIndicators' },
  
  // Stock endpoints (fix paths to match actual API, use existing symbols)
  { method: 'GET', path: '/api/stocks/GOOGL', frontend: 'getStockInfo' },
  { method: 'GET', path: '/api/price/GOOGL', frontend: 'getStockPrice' },  
  { method: 'GET', path: '/api/stocks/history/GOOGL', frontend: 'getStockHistory' },
  
  // Technical endpoints
  { method: 'GET', path: '/technical/indicators/GOOGL?timeframe=daily', frontend: 'getTechnicalIndicators' },
  { method: 'GET', path: '/technical/chart?symbol=GOOGL&timeframe=daily', frontend: 'getTechnicalChart' },
  { method: 'GET', path: '/technical/history/GOOGL', frontend: 'getTechnicalHistory' },
  
  // Price endpoints
  { method: 'GET', path: '/price/GOOGL', frontend: 'getPrice' },
  
  // Screener endpoint
  { method: 'GET', path: '/screener?limit=5', frontend: 'screenStocks' },
  
  // Calendar endpoints
  { method: 'GET', path: '/calendar/events', frontend: 'getCalendarEvents' },
  { method: 'GET', path: '/calendar/earnings', frontend: 'getEarningsCalendar' },
  
  // Dashboard endpoints  
  { method: 'GET', path: '/dashboard/summary', frontend: 'getDashboardSummary' },
  { method: 'GET', path: '/dashboard/performance', frontend: 'getDashboardPerformance' },
  
  // Financials endpoints
  { method: 'GET', path: '/financials/data/GOOGL', frontend: 'getFinancialsData' },
  { method: 'GET', path: '/financials/earnings/GOOGL', frontend: 'getFinancialsEarnings' },
  
  // Health endpoints
  { method: 'GET', path: '/health', frontend: 'checkHealth' },
  
  // News endpoints
  { method: 'GET', path: '/news/latest?limit=5', frontend: 'getLatestNews' },
  
  // Sentiment endpoints  
  { method: 'GET', path: '/sentiment/analysis?symbol=GOOGL', frontend: 'getSentimentAnalysis' },
  
  // Metrics endpoints
  { method: 'GET', path: '/metrics/overview', frontend: 'getMetricsOverview' },
  
  // Signals endpoints
  { method: 'GET', path: '/signals/list', frontend: 'getSignalsList' },
  
  // Trading endpoints
  { method: 'GET', path: '/trading/dashboard', frontend: 'getTradingDashboard' }
];

// HTTP request helper
function makeRequest(method, path, data = null) {
  return new Promise((resolve, reject) => {
    const url = `${API_BASE_URL}${path}`;
    const urlObj = new URL(url);
    
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port || 80,
      path: urlObj.pathname + urlObj.search,
      method: method,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      timeout: TIMEOUT
    };

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const parsedBody = body ? JSON.parse(body) : {};
          resolve({
            status: res.statusCode,
            headers: res.headers,
            body: parsedBody,
            rawBody: body
          });
        } catch (e) {
          resolve({
            status: res.statusCode,
            headers: res.headers,
            body: body,
            rawBody: body,
            parseError: e.message
          });
        }
      });
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error(`Request timeout for ${method} ${path}`));
    });

    if (data && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
      req.write(JSON.stringify(data));
    }

    req.end();
  });
}

// Test individual endpoint
async function testEndpoint(endpoint) {
  try {
    const result = await makeRequest(endpoint.method, endpoint.path, endpoint.testData);
    
    return {
      endpoint: endpoint,
      success: true,
      status: result.status,
      response: result.body,
      issues: analyzeResponse(result, endpoint)
    };
  } catch (error) {
    return {
      endpoint: endpoint,
      success: false,
      error: error.message,
      issues: ['Connection failed']
    };
  }
}

// Analyze response for potential issues
function analyzeResponse(result, endpoint) {
  const issues = [];
  
  // Check status codes
  if (result.status === 404) {
    issues.push('❌ ENDPOINT_NOT_FOUND - Backend endpoint missing');
  } else if (result.status === 500) {
    issues.push('❌ SERVER_ERROR - Backend implementation error');
  } else if (result.status === 501) {
    issues.push('⚠️ NOT_IMPLEMENTED - Feature not implemented');
  } else if (result.status === 400) {
    issues.push('❌ BAD_REQUEST - Possible field mismatch');
  } else if (result.status >= 200 && result.status < 300) {
    issues.push('✅ SUCCESS');
  }
  
  // Check for common field mismatch indicators
  if (result.body && typeof result.body === 'object') {
    if (result.body.error && result.body.error.includes('required')) {
      issues.push('❌ FIELD_MISMATCH - Required field missing');
    }
    
    // Check response structure
    if (result.body.success !== undefined) {
      issues.push('✅ RESPONSE_FORMAT - Uses standard response format');
    }
  }
  
  return issues;
}

// Main verification function
async function verifyApiContracts() {
  console.log('🔍 API Contract Verification Tool');
  console.log('=====================================\\n');
  
  const results = [];
  let totalTests = 0;
  let successCount = 0;
  let issueCount = 0;
  
  console.log('Testing API endpoints...');
  
  for (const endpoint of FRONTEND_API_CALLS) {
    totalTests++;
    console.log(`\\n🧪 Testing: ${endpoint.method} ${endpoint.path}`);
    
    const result = await testEndpoint(endpoint);
    results.push(result);
    
    if (result.success) {
      successCount++;
      console.log(`   Status: ${result.status}`);
      result.issues.forEach(issue => console.log(`   ${issue}`));
      
      if (result.issues.some(issue => issue.includes('❌'))) {
        issueCount++;
      }
    } else {
      issueCount++;
      console.log(`   ❌ FAILED: ${result.error}`);
    }
  }
  
  // Summary report
  console.log('\\n📊 VERIFICATION SUMMARY');
  console.log('========================');
  console.log(`Total endpoints tested: ${totalTests}`);
  console.log(`Successful connections: ${successCount}`);
  console.log(`Issues found: ${issueCount}`);
  console.log(`Success rate: ${((successCount - issueCount) / totalTests * 100).toFixed(1)}%`);
  
  // Detailed issue report
  console.log('\\n🔍 DETAILED ISSUES');
  console.log('==================');
  
  const issuesByType = {
    'ENDPOINT_NOT_FOUND': [],
    'SERVER_ERROR': [],
    'NOT_IMPLEMENTED': [],
    'BAD_REQUEST': [],
    'FIELD_MISMATCH': [],
    'CONNECTION_FAILED': []
  };
  
  results.forEach(result => {
    const endpoint = `${result.endpoint.method} ${result.endpoint.path}`;
    
    if (!result.success) {
      issuesByType.CONNECTION_FAILED.push(endpoint);
    } else {
      result.issues.forEach(issue => {
        if (issue.includes('ENDPOINT_NOT_FOUND')) {
          issuesByType.ENDPOINT_NOT_FOUND.push(endpoint);
        } else if (issue.includes('SERVER_ERROR')) {
          issuesByType.SERVER_ERROR.push(endpoint);
        } else if (issue.includes('NOT_IMPLEMENTED')) {
          issuesByType.NOT_IMPLEMENTED.push(endpoint);
        } else if (issue.includes('BAD_REQUEST')) {
          issuesByType.BAD_REQUEST.push(endpoint);
        } else if (issue.includes('FIELD_MISMATCH')) {
          issuesByType.FIELD_MISMATCH.push(endpoint);
        }
      });
    }
  });
  
  Object.entries(issuesByType).forEach(([issueType, endpoints]) => {
    if (endpoints.length > 0) {
      console.log(`\\n${issueType}:`);
      endpoints.forEach(endpoint => console.log(`  - ${endpoint}`));
    }
  });
  
  // Action items
  console.log('\\n📋 RECOMMENDED ACTIONS');
  console.log('======================');
  
  if (issuesByType.ENDPOINT_NOT_FOUND.length > 0) {
    console.log('1. Check backend routes - some endpoints may be missing or have different URLs');
  }
  
  if (issuesByType.BAD_REQUEST.length > 0 || issuesByType.FIELD_MISMATCH.length > 0) {
    console.log('2. Verify field names match between frontend and backend (like the API keys issue)');
  }
  
  if (issuesByType.SERVER_ERROR.length > 0) {
    console.log('3. Check backend logs for server errors and fix implementation issues');
  }
  
  if (issuesByType.NOT_IMPLEMENTED.length > 0) {
    console.log('4. Implement missing features or add proper fallbacks in frontend');
  }
  
  console.log('\\n✅ Verification complete!');
}

// Run the verification
if (require.main === module) {
  verifyApiContracts().catch(console.error);
}

module.exports = { verifyApiContracts, testEndpoint };