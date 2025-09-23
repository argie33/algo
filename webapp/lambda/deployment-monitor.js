
const { spawn } = require('child_process');

const axios = require('axios');

const BASE_URL = 'https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev';

// Expected fix indicators for each endpoint
const fixIndicators = {
  '/api/signals': {
    name: 'Trading Signals',
    oldErrorPhrase: 'buy_sell_daily',
    isFixed: (response) => response.status === 200 && response.data.success === true
  },
  '/api/watchlist': {
    name: 'Watchlist',
    oldErrorPhrase: 'w.is_public does not exist',
    isFixed: (response) => response.status === 200 && response.data.success === true
  },
  '/api/scores': {
    name: 'Stock Scores',
    oldErrorPhrase: 'timeout of 10000ms exceeded',
    isFixed: (response) => response.status === 200 && response.data.success === true
  },
  '/api/orders': {
    name: 'Orders',
    oldErrorPhrase: 'Orders table orders does not exist',
    isFixed: (response) => response.status === 200 && response.data.success === true
  }
};

async function checkSingleEndpoint(endpoint) {
  try {
    const response = await axios.get(`${BASE_URL}${endpoint}`, {
      timeout: 5000,
      validateStatus: () => true
    });

    const indicator = fixIndicators[endpoint];
    const isFixed = indicator.isFixed(response);

    return {
      endpoint,
      name: indicator.name,
      status: response.status,
      isFixed,
      message: response.data?.message || response.data?.error || 'No message',
      responseTime: response.headers['x-response-time'] || 'N/A'
    };

  } catch (error) {
    return {
      endpoint,
      name: fixIndicators[endpoint].name,
      status: error.code === 'ECONNABORTED' ? 'TIMEOUT' : 'ERROR',
      isFixed: false,
      message: error.message,
      responseTime: 'N/A'
    };
  }
}

async function runHealthCheck() {
  console.log('\n🏥 Running AWS API Health Check...');

  try {
    const healthCheck = spawn('node', ['aws-health-check.js'], {
      stdio: ['ignore', 'pipe', 'pipe']
    });

    let output = '';
    healthCheck.stdout.on('data', (data) => {
      output += data.toString();
    });

    await new Promise((resolve) => {
      healthCheck.on('close', resolve);
    });

    // Extract success rate from output
    const successMatch = output.match(/✅ Successful: (\d+)\/(\d+) \((\d+)%\)/);
    if (successMatch) {
      const [, successful, total, percent] = successMatch;
      console.log(`📊 Overall Health: ${successful}/${total} endpoints (${percent}%)`);
      return parseInt(percent);
    }

    return 0;
  } catch (error) {
    console.log('⚠️  Health check failed:', error.message);
    return 0;
  }
}

async function monitorDeployment() {
  const startTime = Date.now();
  let attempt = 1;
  const maxAttempts = 20; // Monitor for up to 10 minutes

  console.log('🚀 AWS Lambda Deployment Monitor Started');
  console.log('=========================================');
  console.log(`📍 Monitoring ${Object.keys(fixIndicators).length} endpoints for deployment...`);

  while (attempt <= maxAttempts) {
    const currentTime = new Date().toLocaleTimeString();
    console.log(`\n⏰ Check ${attempt}/${maxAttempts} at ${currentTime}`);
    console.log('-'.repeat(50));

    // Check each endpoint
    const endpoints = Object.keys(fixIndicators);
    const results = await Promise.all(endpoints.map(checkSingleEndpoint));

    let fixedCount = 0;
    results.forEach(result => {
      const status = result.isFixed ? '✅ DEPLOYED' : '⏳ PENDING';
      console.log(`${status} ${result.name}`);
      console.log(`   └─ Status: ${result.status}, Message: ${result.message.substring(0, 60)}...`);

      if (result.isFixed) fixedCount++;
    });

    console.log(`\n📈 Deployment Progress: ${fixedCount}/${endpoints.length} endpoints fixed`);

    // If all endpoints are fixed, run final health check
    if (fixedCount === endpoints.length) {
      console.log('\n🎉 ALL ENDPOINTS DEPLOYED!');
      console.log('✅ Running final comprehensive health check...');

      const overallHealth = await runHealthCheck();

      if (overallHealth >= 98) {
        console.log('\n🏆 COMPLETE SUCCESS!');
        console.log('✅ All 500 errors resolved');
        console.log('🚀 Site is fully operational');
        console.log(`⏱️  Total deployment time: ${Math.round((Date.now() - startTime) / 1000 / 60)} minutes`);
        return true;
      } else {
        console.log(`\n⚠️  Overall health: ${overallHealth}% - some issues remain`);
      }
    }

    attempt++;

    if (attempt <= maxAttempts) {
      console.log('\n⏳ Waiting 30 seconds for next check...');
      await new Promise(resolve => setTimeout(resolve, 30000));
    }
  }

  console.log('\n⏰ Maximum monitoring time reached');
  console.log('💡 Fixes are implemented but may need more time to deploy');
  console.log('🔧 Continue monitoring with: node deployment-monitor.js');
  return false;
}

async function quickStatus() {
  console.log('⚡ Quick Deployment Status Check');
  console.log('=================================');

  const endpoints = Object.keys(fixIndicators);
  const results = await Promise.all(endpoints.map(checkSingleEndpoint));

  let fixedCount = 0;
  results.forEach(result => {
    const status = result.isFixed ? '✅' : '❌';
    console.log(`${status} ${result.name} (${result.status})`);
    if (result.isFixed) fixedCount++;
  });

  console.log(`\n📊 Status: ${fixedCount}/${endpoints.length} endpoints deployed`);

  if (fixedCount === endpoints.length) {
    console.log('🎉 All fixes deployed! Site should be working perfectly.');
  } else {
    console.log(`⏳ ${endpoints.length - fixedCount} endpoints still pending deployment`);
  }

  return fixedCount === endpoints.length;
}

// Run based on command line argument
if (require.main === module) {
  const mode = process.argv[2];

  if (mode === '--status') {
    quickStatus().then(() => process.exit(0));
  } else {
    console.log('🎯 Starting continuous deployment monitoring...');
    console.log('💡 Use Ctrl+C to stop, or --status for quick check\n');
    monitorDeployment().catch(console.error);
  }
}

module.exports = { monitorDeployment, quickStatus };