#!/usr/bin/env node
/**
 * End-to-End Complete System Test
 * Tests all major user workflows when deployment is complete
 */

const https = require('https');

const API_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';

// Complete test suite covering all major workflows
const E2E_TEST_SCENARIOS = [
  {
    name: 'User Onboarding Flow',
    description: 'Tests user registration and API key setup workflow',
    tests: [
      { path: '/', expect: 'Landing page loads' },
      { path: '/api/settings/api-keys', expect: 'API keys endpoint accessible' },
      { path: '/api/settings/notifications', expect: 'Notification settings available' },
      { path: '/api/settings/theme', expect: 'Theme settings available' }
    ]
  },
  {
    name: 'Market Data Workflow',
    description: 'Tests basic market data retrieval and display',
    tests: [
      { path: '/api/stocks/sectors', expect: 'Stock sectors data' },
      { path: '/api/market-overview', expect: 'Market overview data' },
      { path: '/api/market-data/latest', expect: 'Latest market data' }
    ]
  },
  {
    name: 'Portfolio Management',
    description: 'Tests portfolio import and management features',
    tests: [
      { path: '/api/portfolio/holdings', expect: 'Portfolio holdings endpoint' },
      { path: '/api/portfolio/performance', expect: 'Performance metrics' },
      { path: '/api/portfolio/analytics', expect: 'Portfolio analytics' }
    ]
  },
  {
    name: 'Real-time Data Systems',
    description: 'Tests live data and streaming capabilities',
    tests: [
      { path: '/api/live-data/metrics', expect: 'Live data metrics' },
      { path: '/api/websocket/status', expect: 'WebSocket status' },
      { path: '/api/live-data/subscribe', expect: 'Subscription endpoint' }
    ]
  },
  {
    name: 'Technical Analysis',
    description: 'Tests technical analysis and charting features',
    tests: [
      { path: '/api/technical/indicators/AAPL', expect: 'Technical indicators' },
      { path: '/api/stocks/AAPL/chart', expect: 'Stock chart data' },
      { path: '/api/screener/momentum', expect: 'Stock screening' }
    ]
  },
  {
    name: 'News and Sentiment',
    description: 'Tests news aggregation and sentiment analysis',
    tests: [
      { path: '/api/news/latest', expect: 'Latest news' },
      { path: '/api/sentiment/analysis', expect: 'Sentiment analysis' },
      { path: '/api/signals/trading', expect: 'Trading signals' }
    ]
  }
];

async function makeRequest(path, timeout = 10000) {
  return new Promise((resolve) => {
    const url = `${API_URL}${path}`;
    
    const req = https.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const jsonData = JSON.parse(data);
          resolve({
            path,
            statusCode: res.statusCode,
            success: res.statusCode >= 200 && res.statusCode < 300,
            data: jsonData,
            isJson: true,
            timestamp: new Date().toISOString()
          });
        } catch (e) {
          resolve({
            path,
            statusCode: res.statusCode,
            success: res.statusCode >= 200 && res.statusCode < 300,
            data: data,
            isJson: false,
            parseError: e.message,
            timestamp: new Date().toISOString()
          });
        }
      });
    });
    
    req.on('error', (err) => {
      resolve({
        path,
        success: false,
        error: err.message,
        timestamp: new Date().toISOString()
      });
    });
    
    req.setTimeout(timeout, () => {
      req.destroy();
      resolve({
        path,
        success: false,
        error: 'Request timeout',
        timestamp: new Date().toISOString()
      });
    });
    
    req.end();
  });
}

async function testScenario(scenario) {
  console.log(`\n🧪 Testing: ${scenario.name}`);
  console.log(`📋 ${scenario.description}`);
  console.log('-'.repeat(60));
  
  const results = {
    name: scenario.name,
    description: scenario.description,
    tests: [],
    summary: {
      total: scenario.tests.length,
      passed: 0,
      failed: 0,
      errors: 0
    }
  };
  
  for (const test of scenario.tests) {
    console.log(`   🔍 ${test.path}`);
    
    const result = await makeRequest(test.path);
    
    // Analyze result
    let testStatus = 'error';
    let details = '';
    
    if (result.error) {
      testStatus = 'error';
      details = result.error;
      results.summary.errors++;
    } else if (!result.success) {
      testStatus = 'failed';
      details = `HTTP ${result.statusCode}`;
      results.summary.failed++;
    } else {
      // Check for specific success indicators
      if (result.isJson && result.data) {
        if (result.data.success === true) {
          testStatus = 'passed';
          details = 'Success response';
          results.summary.passed++;
        } else if (result.data.error) {
          testStatus = 'failed';
          details = result.data.error;
          results.summary.failed++;
        } else {
          testStatus = 'passed';
          details = 'Valid response';
          results.summary.passed++;
        }
      } else {
        testStatus = 'passed';
        details = 'HTTP OK';
        results.summary.passed++;
      }
    }
    
    const statusIcon = testStatus === 'passed' ? '✅' : testStatus === 'failed' ? '❌' : '💥';
    console.log(`      ${statusIcon} ${details}`);
    
    // Add detailed response info for interesting cases
    if (result.isJson && result.data) {
      if (result.data.data && Array.isArray(result.data.data)) {
        console.log(`         📊 Data items: ${result.data.data.length}`);
      }
      if (result.data.message && result.data.message.length < 100) {
        console.log(`         💬 ${result.data.message}`);
      }
    }
    
    results.tests.push({
      path: test.path,
      expect: test.expect,
      status: testStatus,
      details,
      response: result
    });
  }
  
  // Scenario summary
  const passRate = (results.summary.passed / results.summary.total) * 100;
  console.log(`\n   📊 Scenario Results: ${passRate.toFixed(1)}% (${results.summary.passed}/${results.summary.total})`);
  
  return results;
}

async function runCompleteE2ETest() {
  console.log('🚀 End-to-End Complete System Test');
  console.log('='.repeat(70));
  console.log(`📡 Testing API: ${API_URL}`);
  console.log(`🕐 Started: ${new Date().toISOString()}`);
  
  const overallResults = {
    timestamp: new Date().toISOString(),
    apiUrl: API_URL,
    scenarios: [],
    summary: {
      totalScenarios: E2E_TEST_SCENARIOS.length,
      totalTests: 0,
      passedTests: 0,
      failedTests: 0,
      errorTests: 0,
      scenariosFullyPassed: 0,
      averagePassRate: 0
    }
  };
  
  // Run all scenarios
  for (const scenario of E2E_TEST_SCENARIOS) {
    const scenarioResult = await testScenario(scenario);
    overallResults.scenarios.push(scenarioResult);
    
    // Update overall summary
    overallResults.summary.totalTests += scenarioResult.summary.total;
    overallResults.summary.passedTests += scenarioResult.summary.passed;
    overallResults.summary.failedTests += scenarioResult.summary.failed;
    overallResults.summary.errorTests += scenarioResult.summary.errors;
    
    if (scenarioResult.summary.passed === scenarioResult.summary.total) {
      overallResults.summary.scenariosFullyPassed++;
    }
  }
  
  // Calculate overall metrics
  overallResults.summary.averagePassRate = 
    (overallResults.summary.passedTests / overallResults.summary.totalTests) * 100;
  
  // Final report
  console.log('\n' + '='.repeat(70));
  console.log('📊 Complete System Test Results');
  console.log('='.repeat(70));
  
  console.log(`🧪 Scenarios: ${overallResults.summary.totalScenarios}`);
  console.log(`📋 Total Tests: ${overallResults.summary.totalTests}`);
  console.log(`✅ Passed: ${overallResults.summary.passedTests}`);
  console.log(`❌ Failed: ${overallResults.summary.failedTests}`);
  console.log(`💥 Errors: ${overallResults.summary.errorTests}`);
  console.log(`📈 Overall Pass Rate: ${overallResults.summary.averagePassRate.toFixed(1)}%`);
  console.log(`🎯 Fully Working Scenarios: ${overallResults.summary.scenariosFullyPassed}/${overallResults.summary.totalScenarios}`);
  
  // System health assessment
  console.log('\n🏥 System Health Assessment:');
  
  if (overallResults.summary.averagePassRate >= 90) {
    console.log('🟢 EXCELLENT: System is fully operational with all major workflows working');
  } else if (overallResults.summary.averagePassRate >= 75) {
    console.log('🟡 GOOD: Most workflows are working, minor issues present');
  } else if (overallResults.summary.averagePassRate >= 50) {
    console.log('🟠 PARTIAL: Core functionality working, several workflows need attention');
  } else if (overallResults.summary.averagePassRate >= 25) {
    console.log('🔴 LIMITED: Basic functionality present, major issues in most workflows');
  } else {
    console.log('⚫ CRITICAL: System not functional, most endpoints failing');
  }
  
  // Workflow-specific insights
  console.log('\n📋 Workflow Status:');
  overallResults.scenarios.forEach(scenario => {
    const passRate = (scenario.summary.passed / scenario.summary.total) * 100;
    const status = passRate === 100 ? '✅' : passRate >= 75 ? '🟡' : passRate >= 50 ? '🟠' : '🔴';
    console.log(`   ${status} ${scenario.name}: ${passRate.toFixed(0)}% (${scenario.summary.passed}/${scenario.summary.total})`);
  });
  
  // Recommendations
  if (overallResults.summary.averagePassRate < 100) {
    console.log('\n🔧 Recommendations:');
    
    // Identify problematic scenarios
    const problematicScenarios = overallResults.scenarios.filter(s => 
      (s.summary.passed / s.summary.total) < 1
    );
    
    if (problematicScenarios.length > 0) {
      console.log('   📋 Focus areas:');
      problematicScenarios.forEach(scenario => {
        console.log(`      • ${scenario.name}: Check failing endpoints`);
      });
    }
    
    if (overallResults.summary.errorTests > 0) {
      console.log('   🔌 Check network connectivity and API availability');
    }
    
    if (overallResults.summary.failedTests > 0) {
      console.log('   🐛 Review API endpoint implementations and error handling');
    }
  }
  
  console.log(`\n✨ Test completed at: ${new Date().toISOString()}`);
  
  return overallResults;
}

// Run if called directly
if (require.main === module) {
  runCompleteE2ETest().catch(console.error);
}

module.exports = { runCompleteE2ETest, testScenario };