/**
 * Unit Test Results Processor for S3 Upload
 * Generates test-results.json file for S3 upload workflow
 */

const fs = require('fs');
const path = require('path');

module.exports = (testResult) => {
  try {
    // Create unit-test-artifacts directory
    const artifactsDir = path.join(process.cwd(), 'unit-test-artifacts');
    if (!fs.existsSync(artifactsDir)) {
      fs.mkdirSync(artifactsDir, { recursive: true });
    }

    // Process test results
    const summary = {
      testSuite: 'Unit Tests',
      timestamp: new Date().toISOString(),
      environment: process.env.NODE_ENV || 'test',
      results: {
        total: testResult.numTotalTests,
        passed: testResult.numPassedTests,
        failed: testResult.numFailedTests,
        skipped: testResult.numPendingTests,
        successRate: testResult.numTotalTests > 0 
          ? ((testResult.numPassedTests / testResult.numTotalTests) * 100).toFixed(2) + '%' 
          : '0%'
      },
      performance: {
        startTime: testResult.startTime,
        runtime: testResult.testResults.reduce((total, suite) => total + suite.perfStats.runtime, 0),
        averageTestTime: testResult.numTotalTests > 0 
          ? (testResult.testResults.reduce((total, suite) => total + suite.perfStats.runtime, 0) / testResult.numTotalTests).toFixed(2) + 'ms'
          : '0ms'
      },
      coverage: {
        enabled: testResult.coverageMap ? true : false,
        reportPath: 'coverage/coverage-final.json'
      },
      testSuites: testResult.testResults.map(suite => ({
        name: path.relative(process.cwd(), suite.testFilePath),
        tests: suite.numTotalTests,
        passed: suite.numPassedTests,
        failed: suite.numFailedTests,
        skipped: suite.numPendingTests,
        runtime: suite.perfStats.runtime
      }))
    };

    // Write test results JSON
    const testResultsPath = path.join(artifactsDir, 'test-results.json');
    fs.writeFileSync(testResultsPath, JSON.stringify(summary, null, 2));

    // Write JUnit XML to artifacts directory
    const junitPath = path.join(process.cwd(), 'junit.xml');
    const artifactsJunitPath = path.join(artifactsDir, 'junit.xml');
    if (fs.existsSync(junitPath)) {
      fs.copyFileSync(junitPath, artifactsJunitPath);
    }

    // Copy coverage files to artifacts
    const coverageDir = path.join(process.cwd(), 'coverage');
    const artifactsCoverageDir = path.join(artifactsDir, 'coverage');
    if (fs.existsSync(coverageDir)) {
      if (!fs.existsSync(artifactsCoverageDir)) {
        fs.mkdirSync(artifactsCoverageDir, { recursive: true });
      }
      
      // Copy key coverage files
      const coverageFiles = ['coverage-final.json', 'coverage-summary.json', 'lcov.info'];
      coverageFiles.forEach(file => {
        const srcPath = path.join(coverageDir, file);
        const destPath = path.join(artifactsCoverageDir, file);
        if (fs.existsSync(srcPath)) {
          fs.copyFileSync(srcPath, destPath);
        }
      });
    }

    // Generate unit test coverage report
    const reportPath = path.join(process.cwd(), 'unit-test-coverage-report.md');
    const reportContent = `# Unit Test Results Report

## Test Summary
- **Total Tests**: ${summary.results.total}
- **Passed**: ${summary.results.passed}
- **Failed**: ${summary.results.failed}
- **Skipped**: ${summary.results.skipped}
- **Success Rate**: ${summary.results.successRate}

## Performance
- **Total Runtime**: ${summary.performance.runtime}ms
- **Average Test Time**: ${summary.performance.averageTestTime}

## Coverage
- **Coverage Enabled**: ${summary.coverage.enabled}
- **Coverage Report**: ${summary.coverage.reportPath}

## Test Suites
${summary.testSuites.map(suite => 
  `- **${suite.name}**: ${suite.passed}/${suite.tests} passed (${suite.runtime}ms)`
).join('\n')}

## Generated
- **Timestamp**: ${summary.timestamp}
- **Environment**: ${summary.environment}
`;

    fs.writeFileSync(reportPath, reportContent);

    console.log(`✅ Unit test results processed: ${summary.results.passed}/${summary.results.total} tests passed (${summary.results.successRate})`);
    console.log(`📁 Artifacts saved to: ${artifactsDir}`);

    return testResult;

  } catch (error) {
    console.error('❌ Error processing unit test results:', error.message);
    return testResult;
  }
};