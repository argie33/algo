#!/usr/bin/env node

/**
 * Comprehensive Real API Endpoint Testing
 * Tests all frontend API endpoints to identify which have real data vs mock/fallback
 */

const express = require('express');
const path = require('path');

// Set up environment
require('dotenv').config();

const app = express();
app.use(express.json());

// Import all routes
const routes = [
  { path: './routes/stocks', mount: '/api/stocks' },
  { path: './routes/portfolio', mount: '/api/portfolio' },
  { path: './routes/market', mount: '/api/market' },
  { path: './routes/news', mount: '/api/news' },
  { path: './routes/dashboard', mount: '/api/dashboard' },
  { path: './routes/watchlist', mount: '/api/watchlist' },
  { path: './routes/health', mount: '/api/health' },
  { path: './routes/auth', mount: '/api/auth' }
];

console.log('🔄 Loading API routes...');
for (const route of routes) {
  try {
    const routeModule = require(route.path);
    app.use(route.mount, routeModule);
    console.log(`✅ Loaded: ${route.mount}`);
  } catch (error) {
    console.log(`❌ Failed to load ${route.mount}: ${error.message}`);
  }
}

async function testRealEndpoints() {
  console.log('\n🧪 Testing Real API Endpoints\n');
  
  const server = app.listen(3003, () => {
    console.log('✅ Test server running on http://localhost:3003');
  });
  
  try {
    const testEndpoints = [
      // Critical user-facing endpoints
      { 
        name: 'Stocks List (Core Data)', 
        url: 'http://localhost:3003/api/stocks',
        critical: true,
        description: 'Main stock data for Stock Explorer'
      },
      { 
        name: 'Stock Detail', 
        url: 'http://localhost:3003/api/stocks/AAPL',
        critical: true,
        description: 'Individual stock information'
      },
      { 
        name: 'Stock Price History', 
        url: 'http://localhost:3003/api/stocks/AAPL/prices',
        critical: true,
        description: 'Historical price data for charts'
      },
      { 
        name: 'Stock Screening', 
        url: 'http://localhost:3003/api/stocks/screen',
        critical: true,
        description: 'Filtered stock screening'
      },
      { 
        name: 'Portfolio Holdings', 
        url: 'http://localhost:3003/api/portfolio/holdings',
        critical: true,
        description: 'User portfolio data'
      },
      { 
        name: 'Market Overview', 
        url: 'http://localhost:3003/api/market/overview',
        critical: true,
        description: 'Market dashboard data'
      },
      { 
        name: 'Market Sentiment', 
        url: 'http://localhost:3003/api/market/sentiment',
        critical: false,
        description: 'Market sentiment indicators'
      },
      { 
        name: 'Watchlist Data', 
        url: 'http://localhost:3003/api/watchlist',
        critical: false,
        description: 'User watchlist items'
      },
      { 
        name: 'News Feed', 
        url: 'http://localhost:3003/api/news',
        critical: false,
        description: 'Market news articles'
      },
      { 
        name: 'Dashboard Data', 
        url: 'http://localhost:3003/api/dashboard/overview',
        critical: false,
        description: 'Dashboard summary data'
      },
      { 
        name: 'System Health', 
        url: 'http://localhost:3003/api/health',
        critical: true,
        description: 'Database and system status'
      }
    ];
    
    console.log('📡 Testing Frontend API Endpoints:\n');
    
    const results = {
      working: [],
      mock: [],
      failing: [],
      critical_issues: []
    };
    
    for (const endpoint of testEndpoints) {
      try {
        console.log(`🔍 Testing: ${endpoint.name}`);
        
        const response = await fetch(endpoint.url);
        const data = await response.json();
        
        if (response.ok) {
          // Analyze response to determine if it's real data or mock
          const dataAnalysis = analyzeResponseData(data, endpoint.name);
          
          console.log(`   ✅ ${response.status} - ${dataAnalysis.status}`);
          console.log(`   📊 ${dataAnalysis.summary}`);
          
          if (dataAnalysis.isReal) {
            results.working.push({
              ...endpoint,
              response: dataAnalysis
            });
          } else {
            results.mock.push({
              ...endpoint,
              response: dataAnalysis
            });
            
            if (endpoint.critical) {
              results.critical_issues.push({
                ...endpoint,
                issue: 'Critical endpoint using mock data'
              });
            }
          }
        } else {
          console.log(`   ❌ ${response.status} - ${data.error || 'Failed'}`);
          results.failing.push({
            ...endpoint,
            error: data.error || `HTTP ${response.status}`
          });
          
          if (endpoint.critical) {
            results.critical_issues.push({
              ...endpoint,
              issue: `Critical endpoint failing: ${data.error}`
            });
          }
        }
        console.log('');
      } catch (error) {
        console.log(`   ❌ Request failed: ${error.message}\n`);
        results.failing.push({
          ...endpoint,
          error: error.message
        });
        
        if (endpoint.critical) {
          results.critical_issues.push({
            ...endpoint,
            issue: `Critical endpoint error: ${error.message}`
          });
        }
      }
    }
    
    // Generate comprehensive report
    console.log('\n' + '='.repeat(80));
    console.log('📊 COMPREHENSIVE API ENDPOINT ANALYSIS REPORT');
    console.log('='.repeat(80));
    
    console.log(`\n🟢 WORKING WITH REAL DATA (${results.working.length} endpoints):`);
    results.working.forEach(endpoint => {
      console.log(`   ✅ ${endpoint.name}: ${endpoint.response.summary}`);
    });
    
    console.log(`\n🟡 USING MOCK/FALLBACK DATA (${results.mock.length} endpoints):`);
    results.mock.forEach(endpoint => {
      console.log(`   🔧 ${endpoint.name}: ${endpoint.response.summary}`);
    });
    
    console.log(`\n🔴 FAILING ENDPOINTS (${results.failing.length} endpoints):`);
    results.failing.forEach(endpoint => {
      console.log(`   ❌ ${endpoint.name}: ${endpoint.error}`);
    });
    
    if (results.critical_issues.length > 0) {
      console.log(`\n🚨 CRITICAL ISSUES REQUIRING IMMEDIATE ATTENTION:`);
      results.critical_issues.forEach(issue => {
        console.log(`   🚨 ${issue.name}: ${issue.issue}`);
      });
    }
    
    console.log(`\n📈 SUMMARY STATISTICS:`);
    console.log(`   Real Data Endpoints: ${results.working.length}`);
    console.log(`   Mock Data Endpoints: ${results.mock.length}`);
    console.log(`   Failing Endpoints: ${results.failing.length}`);
    console.log(`   Critical Issues: ${results.critical_issues.length}`);
    
    const totalEndpoints = testEndpoints.length;
    const realDataPercentage = Math.round((results.working.length / totalEndpoints) * 100);
    console.log(`   Real Data Coverage: ${realDataPercentage}%`);
    
    console.log(`\n💡 NEXT STEPS:`);
    if (results.critical_issues.length > 0) {
      console.log(`   1. Fix ${results.critical_issues.length} critical issues first`);
    }
    if (results.mock.length > 0) {
      console.log(`   2. Replace ${results.mock.length} mock data endpoints with real implementations`);
    }
    if (results.failing.length > 0) {
      console.log(`   3. Debug ${results.failing.length} failing endpoints`);
    }
    
    console.log('\n🎯 FRONTEND INTEGRATION READINESS:');
    console.log(`   Ready for production: ${results.working.length}/${totalEndpoints} endpoints`);
    console.log(`   Requires mock data replacement: ${results.mock.length} endpoints`);
    console.log(`   Requires debugging: ${results.failing.length} endpoints`);
    
  } finally {
    server.close();
  }
}

function analyzeResponseData(data, endpointName) {
  // Analyze response to determine if it's real data or mock
  let isReal = true;
  let status = 'Real Data';
  let summary = '';
  
  // Check for mock data indicators
  const mockIndicators = [
    'mock', 'sample', 'demo', 'placeholder', 'test', 'fake', 'dummy',
    'development_mode', 'sample_data_store', 'fallback'
  ];
  
  const responseString = JSON.stringify(data).toLowerCase();
  const foundMockIndicators = mockIndicators.filter(indicator => 
    responseString.includes(indicator)
  );
  
  if (foundMockIndicators.length > 0) {
    isReal = false;
    status = 'Mock/Fallback Data';
    summary = `Contains mock indicators: ${foundMockIndicators.join(', ')}`;
  } else if (data.success === false) {
    isReal = false;
    status = 'Error Response';
    summary = data.error || 'API returned error status';
  } else if (data.data && Array.isArray(data.data)) {
    const itemCount = data.data.length;
    if (itemCount === 0) {
      isReal = false;
      status = 'Empty Data';
      summary = 'No data returned';
    } else {
      summary = `${itemCount} items returned`;
      
      // Additional checks for data quality
      if (data.metadata?.development_mode) {
        isReal = false;
        status = 'Development Mode';
        summary += ' (development mode flag detected)';
      }
    }
  } else if (data.data && typeof data.data === 'object') {
    summary = 'Object data returned';
  } else {
    summary = 'Unknown response format';
  }
  
  return {
    isReal,
    status,
    summary,
    mockIndicators: foundMockIndicators
  };
}

if (require.main === module) {
  testRealEndpoints().catch(console.error);
}

module.exports = { testRealEndpoints };