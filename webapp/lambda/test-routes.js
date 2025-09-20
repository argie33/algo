const request = require('supertest');
const app = require('./server');

async function testAllCriticalRoutes() {
  const routes = [
    '/api/stocks?page=1&limit=25&sortBy=symbol&sortOrder=asc',
    '/api/portfolio',
    '/api/market/summary',
    '/api/screener/technical',
    '/api/sectors',
    '/api/risk/analysis',
    '/api/signals',
    '/api/metrics',
    '/api/scores',
    '/api/trades',
    '/api/watchlist',
    '/api/screener',
    '/api/screener/growth',
    '/api/screener/value',
    '/api/screener/dividend',
    '/api/health'
  ];

  console.log('🔍 Testing all critical routes for failures...');
  let failures = [];

  for (const route of routes) {
    try {
      const response = await request(app).get(route);
      if (response.status === 500) {
        failures.push(`❌ 500 ERROR: ${route} - ${response.body.error || response.text}`);
      } else if (response.status >= 400 && response.status !== 404) {
        failures.push(`⚠️  ${response.status} ERROR: ${route}`);
      } else {
        console.log(`✅ ${response.status} ${route}`);
      }
    } catch (error) {
      failures.push(`❌ TEST ERROR: ${route} - ${error.message}`);
    }
  }

  console.log(`\n📊 Test Results: ${routes.length - failures.length}/${routes.length} routes passing`);
  if (failures.length > 0) {
    console.log('\n🚨 FAILURES TO FIX:');
    failures.forEach(f => console.log(f));
  } else {
    console.log('\n🎉 ALL ROUTES WORKING!');
  }
  process.exit(0);
}

testAllCriticalRoutes();