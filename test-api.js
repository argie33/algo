#!/usr/bin/env node

// Quick test script to check API endpoints
const axios = require('axios');

const API_BASE = 'https://ipj77jkthd.execute-api.us-east-1.amazonaws.com/dev';

const endpoints = [
  '',
  '/health',
  '/health?quick=true',
  '/stocks',
  '/stocks/debug', 
  '/stocks/ping',
  '/stocks/screen',
  '/market',
  '/market/overview',
  '/market/debug',
  '/technical',
  '/technical/debug',
  '/technical/daily',
  '/data/validation-summary'
];

async function testEndpoint(endpoint) {
  const url = `${API_BASE}${endpoint}`;
  try {
    console.log(`Testing: ${endpoint}`);
    const start = Date.now();
    const response = await axios.get(url, {
      timeout: 10000,
      headers: {
        'Accept': 'application/json',
        'User-Agent': 'FinancialDashboard-Test/1.0'
      }
    });
    const duration = Date.now() - start;
    console.log(`✅ ${endpoint} - ${response.status} - ${duration}ms - ${JSON.stringify(response.data).length} bytes`);
    
    // Show a preview of the response
    if (response.data && typeof response.data === 'object') {
      const preview = JSON.stringify(response.data, null, 2).slice(0, 200) + '...';
      console.log(`   Preview: ${preview}`);
    }
    
    return { success: true, status: response.status, duration, data: response.data };
  } catch (error) {
    const duration = Date.now() - start;
    if (error.response) {
      console.log(`❌ ${endpoint} - ${error.response.status} - ${duration}ms - ${error.response.statusText}`);
      if (error.response.data) {
        console.log(`   Error: ${JSON.stringify(error.response.data)}`);
      }
      return { success: false, status: error.response.status, duration, error: error.response.statusText };
    } else {
      console.log(`❌ ${endpoint} - FAILED - ${duration}ms - ${error.message}`);
      return { success: false, status: 'NETWORK_ERROR', duration, error: error.message };
    }
  }
}

async function runTests() {
  console.log(`Testing API endpoints at: ${API_BASE}`);
  console.log('=' * 60);
  
  const results = {};
  for (const endpoint of endpoints) {
    results[endpoint] = await testEndpoint(endpoint);
    console.log(''); // Empty line between tests
  }
  
  console.log('\n' + '=' * 60);
  console.log('SUMMARY:');
  console.log('=' * 60);
  
  let successCount = 0;
  let totalCount = endpoints.length;
  
  for (const [endpoint, result] of Object.entries(results)) {
    const status = result.success ? '✅' : '❌';
    const statusCode = result.status || 'N/A';
    const duration = result.duration || 0;
    console.log(`${status} ${endpoint || '/'} - ${statusCode} - ${duration}ms`);
    if (result.success) successCount++;
  }
  
  console.log(`\nSUCCESS RATE: ${successCount}/${totalCount} (${Math.round(successCount/totalCount*100)}%)`);
}

// Run the tests
runTests().catch(console.error);
