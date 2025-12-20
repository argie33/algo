/**
 * Comprehensive AWS API Test
 * Tests all API endpoints against the deployed AWS instance
 */

const https = require('https');

const AWS_BASE_URL = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/Prod';

const endpoints = [
  { path: '/health', name: 'Health Check' },
  { path: '/api/signals', name: 'Signals API' },
  { path: '/api/signals?limit=5', name: 'Signals API (Limited)' },
  { path: '/api/watchlist', name: 'Watchlist API' },
  { path: '/api/stocks/AAPL', name: 'Single Stock (AAPL)' },
  { path: '/api/stocks', name: 'Stocks List' },
  { path: '/api/stocks?limit=5', name: 'Stocks List (Limited)' },
  { path: '/api/market/overview', name: 'Market Overview' },
  { path: '/api/earnings', name: 'Earnings Data' },
  { path: '/api/price/AAPL', name: 'Price Data (AAPL)' },
  { path: '/api/financials/AAPL', name: 'Financials (AAPL)' },
  { path: '/api/news', name: 'News API' },
  { path: '/api/sectors', name: 'Sectors API' },
  { path: '/api/portfolio', name: 'Portfolio API' },
  { path: '/api/analytics/performance', name: 'Analytics Performance' },
  { path: '/api/risk/portfolio', name: 'Risk Analysis' },
  { path: '/api/screener', name: 'Stock Screener' },
  { path: '/api/recommendations', name: 'Recommendations' },
  { path: '/api/calendar', name: 'Calendar Events' }
];

function makeRequest(url) {
  return new Promise((resolve) => {
    const urlObj = new URL(url);
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port,
      path: urlObj.pathname + urlObj.search,
      method: 'GET',
      headers: {
        'Authorization': 'Bearer dev-bypass-token',
        'Content-Type': 'application/json'
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          resolve({
            status: res.statusCode,
            success: parsed.success !== false,
            data: parsed,
            error: parsed.error || null
          });
        } catch (e) {
          resolve({
            status: res.statusCode,
            success: false,
            error: 'Invalid JSON response',
            data: data.substring(0, 200)
          });
        }
      });
    });

    req.on('error', (error) => {
      resolve({
        status: 0,
        success: false,
        error: error.message,
        data: null
      });
    });

    req.setTimeout(10000, () => {
      req.destroy();
      resolve({
        status: 0,
        success: false,
        error: 'Request timeout',
        data: null
      });
    });

    req.end();
  });
}

async function testAllEndpoints() {
  console.log('🧪 AWS API Comprehensive Test Report');
  console.log('=====================================');
  console.log(`Testing against: ${AWS_BASE_URL}`);
  console.log('');

  const results = [];
  let passCount = 0;
  let failCount = 0;
  let serverErrorCount = 0;
  let clientErrorCount = 0;

  for (const endpoint of endpoints) {
    const url = `${AWS_BASE_URL}${endpoint.path}`;
    console.log(`Testing ${endpoint.name}...`);

    const result = await makeRequest(url);
    results.push({
      name: endpoint.name,
      path: endpoint.path,
      ...result
    });

    const status = result.status;
    if (status >= 200 && status < 300 && result.success) {
      console.log(`  ✅ PASS (${status})`);
      passCount++;
    } else if (status >= 500) {
      console.log(`  ❌ SERVER ERROR (${status}): ${result.error || 'Unknown error'}`);
      serverErrorCount++;
      failCount++;
    } else if (status >= 400) {
      console.log(`  ⚠️  CLIENT ERROR (${status}): ${result.error || 'Client error'}`);
      clientErrorCount++;
      failCount++;
    } else {
      console.log(`  ❌ FAIL (${status}): ${result.error || 'Unknown error'}`);
      failCount++;
    }
  }

  console.log('');
  console.log('📊 Summary:');
  console.log(`Total endpoints tested: ${endpoints.length}`);
  console.log(`✅ Passed: ${passCount} (${Math.round(passCount/endpoints.length*100)}%)`);
  console.log(`❌ Failed: ${failCount} (${Math.round(failCount/endpoints.length*100)}%)`);
  console.log(`🔥 Server errors (5xx): ${serverErrorCount}`);
  console.log(`⚠️  Client errors (4xx): ${clientErrorCount}`);

  console.log('');
  console.log('🔍 Detailed Results:');
  console.log('====================');

  results.forEach(result => {
    if (!result.success || result.status >= 400) {
      console.log(`\n❌ ${result.name} (${result.path})`);
      console.log(`   Status: ${result.status}`);
      console.log(`   Error: ${result.error || 'None'}`);
      if (result.data && typeof result.data === 'object' && result.data.details) {
        console.log(`   Details: ${result.data.details}`);
      }
    }
  });

  // Save results to file
  const fs = require('fs');
  fs.writeFileSync('aws_comprehensive_test_results.json', JSON.stringify({
    timestamp: new Date().toISOString(),
    baseUrl: AWS_BASE_URL,
    summary: { total: endpoints.length, passed: passCount, failed: failCount, serverErrors: serverErrorCount, clientErrors: clientErrorCount },
    results: results
  }, null, 2));

  console.log('\n💾 Results saved to aws_comprehensive_test_results.json');

  if (serverErrorCount === 0) {
    console.log('\n🎉 No server errors! All APIs responding properly.');
    if (passCount === endpoints.length) {
      console.log('🏆 Perfect score! All APIs working correctly.');
    }
  } else {
    console.log(`\n⚠️  ${serverErrorCount} server errors need to be fixed.`);
  }
}

testAllEndpoints().catch(console.error);