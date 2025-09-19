#!/usr/bin/env node

const axios = require('axios');

const FRONTEND_URL = 'http://localhost:5174';
const API_URL = 'http://localhost:3001/api';

// Test if frontend can make API calls through the proxy
async function testApiIntegration() {
  console.log('🔗 Testing frontend-to-API integration...\n');

  const tests = [
    {
      name: 'Health Check via Frontend Proxy',
      url: `${FRONTEND_URL}/api/health`,
      expectJson: true
    },
    {
      name: 'Market Overview via Frontend Proxy',
      url: `${FRONTEND_URL}/api/market/overview`,
      expectJson: true
    },
    {
      name: 'Dashboard Summary via Frontend Proxy',
      url: `${FRONTEND_URL}/api/dashboard/summary`,
      expectJson: true
    },
    {
      name: 'Stocks List via Frontend Proxy',
      url: `${FRONTEND_URL}/api/stocks`,
      expectJson: true
    },
    {
      name: 'Direct API Health Check',
      url: `${API_URL}/health`,
      expectJson: true
    }
  ];

  const results = [];
  let successCount = 0;

  for (const test of tests) {
    console.log(`Testing: ${test.name}`);

    try {
      const response = await axios.get(test.url, {
        timeout: 10000,
        headers: {
          'Accept': 'application/json',
          'User-Agent': 'Integration-Test/1.0'
        }
      });

      const isJson = typeof response.data === 'object';
      const hasData = isJson && Object.keys(response.data).length > 0;

      const result = {
        name: test.name,
        status: 'SUCCESS',
        statusCode: response.status,
        isJson,
        hasData,
        dataSize: JSON.stringify(response.data).length,
        responseTime: response.headers['x-response-time'] || 'N/A'
      };

      results.push(result);
      successCount++;

      console.log(`✅ ${result.statusCode} - ${isJson ? 'JSON' : 'HTML'} - ${hasData ? 'Has Data' : 'No Data'} - ${result.dataSize} bytes`);

    } catch (error) {
      const result = {
        name: test.name,
        status: 'ERROR',
        statusCode: error.response?.status || 'N/A',
        error: error.message
      };

      results.push(result);
      console.log(`❌ ${result.statusCode} - ${result.error}`);
    }

    await new Promise(resolve => setTimeout(resolve, 100));
  }

  console.log(`\n📊 INTEGRATION TEST SUMMARY:`);
  console.log(`Tests run: ${tests.length}`);
  console.log(`Successful: ${successCount}`);
  console.log(`Success rate: ${((successCount / tests.length) * 100).toFixed(1)}%`);

  if (successCount === tests.length) {
    console.log('\n✅ Frontend-API integration is working correctly!');
  } else {
    console.log('\n⚠️ Some integration issues detected.');
  }

  return results;
}

testApiIntegration().catch(console.error);