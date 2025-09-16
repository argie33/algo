/* eslint-disable node/no-unpublished-require */
// Using axios from devDependencies for testing
const axios = require('axios');

const BASE_URL = 'http://localhost:3001';

// Critical failing endpoints from previous tests
const criticalEndpoints = [
  { path: '/api/stocks/popular', method: 'GET', name: 'Stocks Popular' },
  { path: '/api/sentiment/analysis?symbol=AAPL', method: 'GET', name: 'Sentiment Analysis' },
  { path: '/api/metrics/market', method: 'GET', name: 'Market Metrics' },
  { path: '/api/metrics/performance', method: 'GET', name: 'Performance Metrics' },
  { path: '/api/financials/statements?symbol=AAPL', method: 'GET', name: 'Financial Statements' },
  { path: '/api/financials/ratios?symbol=AAPL', method: 'GET', name: 'Financial Ratios' },
  { path: '/api/price/AAPL', method: 'GET', name: 'Price Data AAPL' },
  { path: '/api/stocks/AAPL/financials', method: 'GET', name: 'Stock Financials AAPL' },
  { path: '/api/data/sources', method: 'GET', name: 'Data Sources' },
  { path: '/api/data/status', method: 'GET', name: 'Data Status' },
];

async function testEndpoint(endpoint) {
  try {
    const start = Date.now();
    const response = await axios.get(`${BASE_URL}${endpoint.path}`, {
      timeout: 10000,
      validateStatus: (status) => status < 500 // Accept any non-500 status
    });
    const duration = Date.now() - start;

    const hasData = response.data && (
      Object.keys(response.data).length > 0 ||
      (Array.isArray(response.data) && response.data.length > 0)
    );

    if (response.status === 200 && hasData) {
      console.log(`✅ ${response.status} - ${duration}ms - ${endpoint.name}`);
      return { success: true, status: response.status, error: null };
    } else if (response.status === 200) {
      console.log(`⚠️ ${response.status} - ${duration}ms - ${endpoint.name} (Empty data)`);
      return { success: false, status: response.status, error: "Empty response data" };
    } else {
      console.log(`❌ ${response.status} - ${duration}ms - ${endpoint.name} - ${response.data?.error || response.data?.message || 'Unknown error'}`);
      return { success: false, status: response.status, error: response.data?.error || response.data?.message };
    }
  } catch (error) {
    if (error.code === 'ECONNREFUSED') {
      console.log(`🚫 CONN - Server not running - ${endpoint.name}`);
      return { success: false, status: 'ECONNREFUSED', error: 'Server not running' };
    } else if (error.response) {
      console.log(`❌ ${error.response.status} - ${endpoint.name} - ${error.response.data?.error || error.response.data?.message || error.message}`);
      return { success: false, status: error.response.status, error: error.response.data?.error || error.message };
    } else {
      console.log(`💥 ERROR - ${endpoint.name} - ${error.message}`);
      return { success: false, status: 'ERROR', error: error.message };
    }
  }
}

async function main() {
  console.log('🚀 Running Critical API Endpoint Tests...\n');

  const results = [];

  for (const endpoint of criticalEndpoints) {
    const result = await testEndpoint(endpoint);
    results.push({ ...endpoint, ...result });
  }

  console.log('\n📊 SUMMARY:');
  const successful = results.filter(r => r.success);
  const failed = results.filter(r => !r.success);

  console.log(`✅ Working: ${successful.length}/${results.length} (${(successful.length/results.length*100).toFixed(1)}%)`);
  console.log(`❌ Failing: ${failed.length}/${results.length} (${(failed.length/results.length*100).toFixed(1)}%)`);

  if (failed.length > 0) {
    console.log('\n🔧 ISSUES TO FIX:');
    failed.forEach(f => {
      console.log(`   ${f.status} - ${f.name}: ${f.error}`);
    });
  }

  if (successful.length === results.length) {
    console.log('\n🎉 ALL CRITICAL ENDPOINTS WORKING!');
  } else {
    console.log(`\n⚠️ ${failed.length} endpoints need fixing`);
  }
}

main().catch(console.error);