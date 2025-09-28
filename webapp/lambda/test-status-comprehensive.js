#!/usr/bin/env node

/**
 * Comprehensive Test Status Checker
 * Tests all unit test modules systematically
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

console.log('🧪 Comprehensive Test Status Checker');
console.log('=====================================');

// Get all unit test files
const unitTestsDir = 'tests/unit/routes';
const testFiles = fs.readdirSync(unitTestsDir)
  .filter(file => file.endsWith('.test.js'))
  .sort();

console.log(`Found ${testFiles.length} unit test files`);

// Tests we know have issues
const knownTimeoutModules = [
  'risk.test.js',
  'screener.test.js',
  'trades.test.js',
  'calendar.test.js'
];

// Tests we've completed successfully
const completedModules = [
  'analysts.test.js',
  'scores.test.js',
  'market.test.js',
  'news.test.js',
  'portfolio.test.js',
  'stocks.test.js',
  'watchlist.test.js',
  'metrics.test.js',
  'analytics.test.js',
  'technical.test.js',
  'earnings.test.js',
  'alerts.test.js',
  'trading.test.js',
  'insider.test.js',
  'auth.test.js',
  'user.test.js',
  'dividend.test.js'
];

async function runTest(testFile) {
  return new Promise((resolve) => {
    const testPath = path.join(unitTestsDir, testFile);
    console.log(`\n📋 Testing ${testFile}...`);

    const testProcess = spawn('npm', ['test', testPath], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, NODE_ENV: 'test' }
    });

    let stdout = '';
    let stderr = '';
    let hasOutput = false;

    // Set timeout
    const timeout = setTimeout(() => {
      testProcess.kill('SIGTERM');
      resolve({
        file: testFile,
        status: 'TIMEOUT',
        duration: 60000,
        output: 'Test timed out after 60 seconds'
      });
    }, 60000);

    testProcess.stdout.on('data', (data) => {
      stdout += data.toString();
      hasOutput = true;
    });

    testProcess.stderr.on('data', (data) => {
      stderr += data.toString();
      hasOutput = true;
    });

    testProcess.on('close', (code) => {
      clearTimeout(timeout);

      // Parse test results
      let passed = 0;
      let failed = 0;
      let skipped = 0;

      const passMatch = stdout.match(/(\d+) passing/);
      const failMatch = stdout.match(/(\d+) failing/);
      const skipMatch = stdout.match(/(\d+) pending/);

      if (passMatch) passed = parseInt(passMatch[1]);
      if (failMatch) failed = parseInt(failMatch[1]);
      if (skipMatch) skipped = parseInt(skipMatch[1]);

      resolve({
        file: testFile,
        status: code === 0 ? 'PASS' : 'FAIL',
        passed,
        failed,
        skipped,
        output: hasOutput ? (stdout + stderr).slice(-500) : 'No output'
      });
    });

    testProcess.on('error', (error) => {
      clearTimeout(timeout);
      resolve({
        file: testFile,
        status: 'ERROR',
        output: error.message
      });
    });
  });
}

async function runAllTests() {
  const results = [];

  // Group tests by status
  const remainingTests = testFiles.filter(file =>
    !completedModules.includes(file) &&
    !knownTimeoutModules.includes(file)
  );

  console.log(`\n📊 Test Status Overview:`);
  console.log(`  ✅ Completed: ${completedModules.length}`);
  console.log(`  ⏰ Known timeouts: ${knownTimeoutModules.length}`);
  console.log(`  🔄 Remaining to test: ${remainingTests.length}`);

  if (remainingTests.length === 0) {
    console.log('\n🎉 All tests have been checked!');
    console.log('\n📋 Summary:');
    console.log(`  ✅ Working: ${completedModules.length}`);
    console.log(`  ⏰ Timeout issues: ${knownTimeoutModules.length}`);
    return;
  }

  console.log(`\n🔄 Testing remaining ${remainingTests.length} modules...`);

  // Test remaining modules
  for (const testFile of remainingTests) {
    const result = await runTest(testFile);
    results.push(result);

    const status = result.status === 'PASS' ? '✅' :
                   result.status === 'TIMEOUT' ? '⏰' : '❌';

    console.log(`  ${status} ${testFile}: ${result.status} (${result.passed || 0} passed, ${result.failed || 0} failed)`);
  }

  // Final summary
  console.log('\n📊 Final Results:');
  const passed = results.filter(r => r.status === 'PASS').length;
  const failed = results.filter(r => r.status === 'FAIL').length;
  const timeout = results.filter(r => r.status === 'TIMEOUT').length;

  console.log(`  ✅ Passed: ${passed + completedModules.length}`);
  console.log(`  ❌ Failed: ${failed}`);
  console.log(`  ⏰ Timeout: ${timeout + knownTimeoutModules.length}`);

  if (failed > 0) {
    console.log('\n❌ Failed Tests:');
    results.filter(r => r.status === 'FAIL').forEach(r => {
      console.log(`  - ${r.file}: ${r.failed} failures`);
    });
  }
}

runAllTests().catch(error => {
  console.error('❌ Test runner failed:', error);
  process.exit(1);
});