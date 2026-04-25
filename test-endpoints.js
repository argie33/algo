#!/usr/bin/env node
/**
 * API Endpoint Tester
 * Tests if core endpoints return data without 500 errors
 */

const axios = require('axios');

const BASE_URL = 'http://localhost:3000/api';

const endpoints = [
  {
    name: 'Stocks List',
    url: '/stocks?limit=10',
    method: 'GET'
  },
  {
    name: 'Stocks Search',
    url: '/stocks/search?q=AAPL',
    method: 'GET'
  },
  {
    name: 'Deep Value Stocks',
    url: '/stocks/deep-value?limit=50',
    method: 'GET'
  },
  {
    name: 'Sectors',
    url: '/sectors/sectors?limit=20',
    method: 'GET'
  },
  {
    name: 'Sector Performance',
    url: '/sectors/performance',
    method: 'GET'
  }
];

async function testEndpoint(endpoint) {
  try {
    const url = `${BASE_URL}${endpoint.url}`;
    const response = await axios({
      method: endpoint.method,
      url: url,
      timeout: 5000,
      validateStatus: () => true  // Don't throw on any status code
    });

    const status = response.status;
    const dataCount = Array.isArray(response.data?.items) ? response.data.items.length :
                      Array.isArray(response.data?.data) ? response.data.data.length : 0;

    const icon = status === 200 ? '[OK]' : status >= 500 ? '[ERROR]' : '[WARN]';
    console.log(`${icon} ${endpoint.name.padEnd(25)} ${status} ${dataCount > 0 ? `(${dataCount} items)` : ''}`);

    if (status >= 500) {
      console.log(`     Error: ${response.data?.error || response.data?.message || 'Unknown error'}`);
    }

    return { endpoint: endpoint.name, status, dataCount };
  } catch (error) {
    console.log(`[FAIL] ${endpoint.name.padEnd(25)} ${error.message}`);
    return { endpoint: endpoint.name, status: 'FAIL', error: error.message };
  }
}

async function runTests() {
  console.log('\nAPI Endpoint Tests');
  console.log('=' .repeat(70));
  console.log(`Testing: ${BASE_URL}\n`);

  const results = [];
  for (const endpoint of endpoints) {
    const result = await testEndpoint(endpoint);
    results.push(result);
    await new Promise(r => setTimeout(r, 100));  // Small delay between requests
  }

  console.log('\nSummary');
  console.log('=' .repeat(70));
  const ok = results.filter(r => r.status === 200).length;
  const failed = results.filter(r => r.status >= 500).length;
  console.log(`OK: ${ok}/${endpoints.length} | Errors: ${failed}`);

  if (failed > 0) {
    console.log('\nFailed endpoints need data loading or fixes.');
    process.exit(1);
  } else {
    console.log('\nAll endpoints working!');
    process.exit(0);
  }
}

runTests();
