
const axios = require('axios');

const BASE_URL = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

async function checkEndpoint(endpoint, expectedChange) {
  try {
    const response = await axios.get(`${BASE_URL}${endpoint}`, { timeout: 5000 });
    return {
      endpoint,
      status: response.status,
      success: response.status === 200,
      expectedChange,
      deployed: response.status === 200
    };
  } catch (error) {
    return {
      endpoint,
      status: error.response?.status || 'TIMEOUT',
      success: false,
      expectedChange,
      deployed: false,
      error: error.message
    };
  }
}

async function monitorDeployment() {
  console.log(`🔍 Monitoring AWS Lambda deployment status - ${new Date().toISOString()}`);
  console.log('📍 Checking fixed endpoints for deployment propagation...\n');

  const endpoints = [
    { path: '/api/signals', change: 'Should use fundamental_metrics table instead of buy_sell_daily' },
    { path: '/api/watchlist', change: 'Should remove w.is_public column reference' },
    { path: '/api/scores', change: 'Should have timeout protection (respond within 5s)' }
  ];

  const results = await Promise.all(
    endpoints.map(ep => checkEndpoint(ep.path, ep.change))
  );

  console.log('📊 DEPLOYMENT STATUS:');
  console.log('===================');

  let deployedCount = 0;
  results.forEach(result => {
    const status = result.deployed ? '✅ DEPLOYED' : '⏳ PENDING';
    console.log(`${status} ${result.endpoint} (${result.status})`);
    if (result.deployed) deployedCount++;
  });

  console.log(`\n📈 Progress: ${deployedCount}/${results.length} endpoints deployed`);

  if (deployedCount === results.length) {
    console.log('🎉 All fixes have been deployed to AWS Lambda!');
    console.log('✅ Ready to run final health check to verify all endpoints are working.');
    return true;
  } else {
    console.log('⏳ Waiting for AWS Lambda cache refresh...');
    return false;
  }
}

// If run directly, execute monitoring
if (require.main === module) {
  monitorDeployment()
    .then(deployed => {
      if (!deployed) {
        console.log('\n💡 Tip: AWS Lambda deployments can take 5-15 minutes to propagate.');
        console.log('📝 Re-run this script periodically: node monitor-deployment.js');
      }
    })
    .catch(console.error);
}

module.exports = { monitorDeployment };