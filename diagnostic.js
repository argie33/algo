const axios = require('axios');

const API_URL = 'http://localhost:3001';

async function checkEndpoint(path) {
  try {
    const response = await axios.get(`${API_URL}${path}`, { timeout: 5000 });
    const items = response.data?.items?.length || 0;
    const success = response.data?.success !== false;
    return { status: success ? '✅' : '❌', items, error: null };
  } catch (error) {
    return { status: '❌', items: 0, error: error.message };
  }
}

async function runDiagnostic() {
  console.log('\n=== FULL SYSTEM DIAGNOSTIC ===\n');
  
  const endpoints = [
    // Core data
    { path: '/api/stocks?limit=1', name: 'Stocks List' },
    { path: '/api/health', name: 'API Health' },
    { path: '/api/diagnostics', name: 'Full Diagnostics' },
    
    // Trading Signals
    { path: '/api/signals/stocks?timeframe=daily&limit=10', name: 'Daily Signals' },
    { path: '/api/signals/stocks?timeframe=weekly&limit=10', name: 'Weekly Signals' },
    { path: '/api/signals/stocks?timeframe=monthly&limit=10', name: 'Monthly Signals' },
    
    // Market Data
    { path: '/api/market/overview', name: 'Market Overview' },
    { path: '/api/market/sentiment?range=30d', name: 'Market Sentiment' },
    { path: '/api/market/seasonality', name: 'Seasonality' },
    { path: '/api/market/indices', name: 'Market Indices' },
    { path: '/api/market/technicals', name: 'Market Technicals' },
    
    // Financial Data
    { path: '/api/financials/AAPL/balance-sheet?period=annual', name: 'Balance Sheet' },
    { path: '/api/financials/AAPL/income?period=annual', name: 'Income Statement' },
    
    // Earnings
    { path: '/api/earnings?limit=10', name: 'Earnings Data' },
    
    // Sectors
    { path: '/api/sectors/sectors?limit=10', name: 'Sectors' },
    
    // Economic
    { path: '/api/economic/indicators', name: 'Economic Data' },
  ];
  
  for (const endpoint of endpoints) {
    const result = await checkEndpoint(endpoint.path);
    console.log(`${result.status} ${endpoint.name.padEnd(25)} | Items: ${result.items} | ${result.error || 'OK'}`);
  }
  
  console.log('\n=== CHECKING API HEALTH IN DETAIL ===\n');
  try {
    const health = await axios.get(`${API_URL}/api/health`);
    const db = health.data?.data?.database?.tables || {};
    console.log('Database tables:');
    Object.entries(db).forEach(([table, count]) => {
      const icon = count > 0 ? '✅' : '❌';
      console.log(`  ${icon} ${table.padEnd(30)} ${count}`);
    });
  } catch (error) {
    console.log('❌ Could not get health data:', error.message);
  }
}

runDiagnostic().catch(err => console.error('Diagnostic error:', err));
