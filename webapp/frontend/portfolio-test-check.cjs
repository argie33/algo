#!/usr/bin/env node
/**
 * Simple script to check portfolio test status
 */

const { exec } = require('child_process');
const path = require('path');

const portfolioTestFiles = [
  'src/tests/unit/pages/Portfolio.test.jsx',
  'src/tests/unit/pages/PortfolioHoldings.test.jsx',
  'src/tests/unit/pages/PortfolioPerformance.test.jsx',
  'src/tests/unit/pages/PortfolioOptimization.test.jsx',
  'src/tests/component/PortfolioHoldings.test.jsx'
];

async function checkTestFile(testFile) {
  return new Promise((resolve) => {
    const timeout = setTimeout(() => {
      resolve({
        file: testFile,
        status: 'timeout',
        tests: 0,
        passed: 0,
        failed: 0
      });
    }, 30000); // 30 second timeout

    exec(`./node_modules/.bin/vitest run ${testFile} --reporter=json --testTimeout=5000`, 
      { cwd: process.cwd(), timeout: 30000 }, 
      (error, stdout, stderr) => {
        clearTimeout(timeout);
        
        if (error && error.killed) {
          resolve({
            file: testFile,
            status: 'timeout',
            tests: 0,
            passed: 0,
            failed: 0
          });
          return;
        }

        try {
          // Try to parse JSON output
          const lines = stdout.split('\n').filter(line => line.trim().startsWith('{'));
          if (lines.length === 0) {
            resolve({
              file: testFile,
              status: 'no-output',
              tests: 0,
              passed: 0,
              failed: 0,
              error: stderr || 'No JSON output found'
            });
            return;
          }

          const result = JSON.parse(lines[lines.length - 1]);
          
          resolve({
            file: testFile,
            status: 'completed',
            tests: result.numTotalTests || 0,
            passed: result.numPassedTests || 0,
            failed: result.numFailedTests || 0,
            error: error ? error.message : null
          });
        } catch (parseError) {
          resolve({
            file: testFile,
            status: 'parse-error',
            tests: 0,
            passed: 0,
            failed: 0,
            error: parseError.message,
            stdout: stdout.substring(0, 500)
          });
        }
      });
  });
}

async function main() {
  console.log('🔍 Checking portfolio test files...\n');
  
  const results = [];
  
  for (const testFile of portfolioTestFiles) {
    console.log(`Checking: ${testFile}`);
    const result = await checkTestFile(testFile);
    results.push(result);
    
    console.log(`  Status: ${result.status}`);
    if (result.status === 'completed') {
      console.log(`  Tests: ${result.tests}, Passed: ${result.passed}, Failed: ${result.failed}`);
    } else if (result.error) {
      console.log(`  Error: ${result.error.substring(0, 100)}...`);
    }
    console.log('');
  }
  
  // Summary
  console.log('📊 PORTFOLIO TEST SUMMARY:');
  console.log('==========================');
  
  let totalTests = 0;
  let totalPassed = 0;
  let totalFailed = 0;
  let timeouts = 0;
  let errors = 0;
  
  results.forEach(result => {
    totalTests += result.tests;
    totalPassed += result.passed;
    totalFailed += result.failed;
    
    if (result.status === 'timeout') timeouts++;
    if (result.status === 'parse-error' || result.status === 'no-output') errors++;
    
    console.log(`${result.file}:`);
    console.log(`  ${result.status} - Tests: ${result.tests}, Passed: ${result.passed}, Failed: ${result.failed}`);
  });
  
  console.log('\n📋 TOTALS:');
  console.log(`Total portfolio test files: ${results.length}`);
  console.log(`Total tests: ${totalTests}`);
  console.log(`Passed: ${totalPassed}`);
  console.log(`Failed: ${totalFailed}`);
  console.log(`Timeouts: ${timeouts}`);
  console.log(`Errors: ${errors}`);
  
  console.log('\n🎯 ANSWER TO YOUR QUESTION:');
  if (totalTests > 0) {
    console.log(`Portfolio pages have ${totalFailed} failing unit/integration tests out of ${totalTests} total tests.`);
  } else {
    console.log('Unable to determine exact test counts due to test execution issues.');
  }
}

main().catch(console.error);