
/**
 * Quick Integration Test Status Checker
 * Runs fast checks on key integration test endpoints
 */

const request = require('supertest');
const express = require('express');

console.log('🧪 Quick Integration Test Status Checker');
console.log('==========================================');

async function quickTestCheck() {
  const app = express();

  // Test some basic endpoints that should work
  const tests = [
    {
      name: 'Health Check',
      path: '/health',
      expected: 200
    },
    {
      name: 'Stocks API',
      path: '/api/stocks?limit=1',
      expected: 200
    },
    {
      name: 'Analysts API',
      path: '/api/analysts',
      expected: 200
    },
    {
      name: 'Market News',
      path: '/market/news?limit=1',
      expected: 200
    }
  ];

  const results = [];

  for (const test of tests) {
    try {
      console.log(`Testing ${test.name}...`);
      const response = await fetch(`http://localhost:3001${test.path}`);
      const status = response.status;
      const passed = status === test.expected;

      results.push({
        name: test.name,
        status,
        expected: test.expected,
        passed
      });

      console.log(`  ${passed ? '✅' : '❌'} ${test.name}: ${status} (expected ${test.expected})`);

    } catch (error) {
      results.push({
        name: test.name,
        status: 'ERROR',
        expected: test.expected,
        passed: false,
        error: error.message
      });
      console.log(`  ❌ ${test.name}: ERROR - ${error.message}`);
    }
  }

  console.log('\n📊 Summary:');
  const passed = results.filter(r => r.passed).length;
  const total = results.length;
  console.log(`  ${passed}/${total} tests passed`);

  if (passed !== total) {
    console.log('\n❌ Failed tests:');
    results.filter(r => !r.passed).forEach(r => {
      console.log(`  - ${r.name}: ${r.status} ${r.error ? `(${r.error})` : ''}`);
    });
    process.exit(1);
  } else {
    console.log('\n✅ All quick tests passed!');
    process.exit(0);
  }
}

quickTestCheck().catch(error => {
  console.error('❌ Quick test check failed:', error);
  process.exit(1);
});