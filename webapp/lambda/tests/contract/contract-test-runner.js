/**
 * API Contract Test Runner
 * 
 * Automated test runner for comprehensive API contract validation.
 * Runs contract tests against different environments and generates reports.
 */

const { exec } = require('child_process');
const fs = require('fs/promises');
const path = require('path');

class ContractTestRunner {
  constructor(options = {}) {
    this.options = {
      environments: ['test', 'staging'],
      timeout: 30000,
      retries: 2,
      failFast: false,
      generateReport: true,
      reportFormat: 'html',
      ...options
    };
    
    this.results = {
      timestamp: new Date().toISOString(),
      environments: {},
      summary: {
        total: 0,
        passed: 0,
        failed: 0,
        skipped: 0
      }
    };
  }

  async runAllTests() {
    console.log('🚀 Starting API Contract Test Runner');
    console.log(`Testing environments: ${this.options.environments.join(', ')}`);
    
    for (const env of this.options.environments) {
      console.log(`\n📊 Running contract tests for ${env} environment...`);
      
      try {
        const envResults = await this.runEnvironmentTests(env);
        this.results.environments[env] = envResults;
        
        // Update summary
        this.results.summary.total += envResults.total;
        this.results.summary.passed += envResults.passed;
        this.results.summary.failed += envResults.failed;
        this.results.summary.skipped += envResults.skipped;
        
        console.log(`✅ ${env} environment: ${envResults.passed}/${envResults.total} tests passed`);
        
        if (this.options.failFast && envResults.failed > 0) {
          console.log('💥 Fail-fast enabled, stopping on first failure');
          break;
        }
        
      } catch (error) {
        console.error(`❌ Failed to run tests for ${env} environment:`, error.message);
        this.results.environments[env] = {
          error: error.message,
          total: 0,
          passed: 0,
          failed: 0,
          skipped: 0
        };
      }
    }
    
    if (this.options.generateReport) {
      await this.generateReport();
    }
    
    return this.results;
  }

  async runEnvironmentTests(environment) {
    const testCommand = this.buildTestCommand(environment);
    
    return new Promise((resolve) => {
      const startTime = Date.now();
      
      exec(testCommand, {
        timeout: this.options.timeout,
        cwd: process.cwd()
      }, (error, stdout, stderr) => {
        const endTime = Date.now();
        const duration = endTime - startTime;
        
        if (error && error.code !== 0) {
          // Parse test results even if some tests failed
          const results = this.parseTestOutput(stdout, stderr, environment);
          results.duration = duration;
          results.exitCode = error.code;
          resolve(results);
        } else {
          const results = this.parseTestOutput(stdout, stderr, environment);
          results.duration = duration;
          results.exitCode = 0;
          resolve(results);
        }
      });
    });
  }

  buildTestCommand(environment) {
    const baseCommand = 'npm test';
    const testPattern = 'contract/**/*.test.js';
    const envVars = this.getEnvironmentVariables(environment);
    
    return `${envVars} ${baseCommand} -- --testPathPattern="${testPattern}" --json --outputFile=contract-results-${environment}.json`;
  }

  getEnvironmentVariables(environment) {
    const envVars = {
      NODE_ENV: environment,
      API_BASE_URL: this.getApiBaseUrl(environment),
      DATABASE_URL: this.getDatabaseUrl(environment)
    };
    
    return Object.entries(envVars)
      .map(([key, value]) => `${key}="${value}"`)
      .join(' ');
  }

  getApiBaseUrl(environment) {
    const urls = {
      test: 'http://localhost:3001',
      staging: 'https://api-staging.example.com',
      production: 'https://api.example.com'
    };
    
    return urls[environment] || urls.test;
  }

  getDatabaseUrl(environment) {
    // Return appropriate database URL for environment
    // In test environment, use in-memory database
    if (environment === 'test') {
      return 'memory://test-database';
    }
    
    return process.env.DATABASE_URL || 'memory://test-database';
  }

  parseTestOutput(stdout, stderr, environment) {
    const results = {
      environment,
      total: 0,
      passed: 0,
      failed: 0,
      skipped: 0,
      tests: [],
      errors: []
    };
    
    try {
      // Try to parse JSON output from Jest
      const jsonOutput = this.extractJsonFromOutput(stdout);
      if (jsonOutput) {
        return this.parseJestJsonOutput(jsonOutput, environment);
      }
      
      // Fallback to parsing text output
      return this.parseTextOutput(stdout, stderr, environment);
      
    } catch (error) {
      console.error(`Error parsing test output for ${environment}:`, error.message);
      results.errors.push(`Failed to parse test output: ${error.message}`);
      return results;
    }
  }

  extractJsonFromOutput(output) {
    try {
      // Look for JSON output in the stdout
      const jsonMatch = output.match(/\{[\s\S]*"testResults"[\s\S]*\}/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      }
      return null;
    } catch (error) {
      return null;
    }
  }

  parseJestJsonOutput(jsonOutput, environment) {
    const results = {
      environment,
      total: 0,
      passed: 0,
      failed: 0,
      skipped: 0,
      tests: [],
      errors: []
    };
    
    if (jsonOutput.testResults) {
      jsonOutput.testResults.forEach(testFile => {
        testFile.assertionResults.forEach(test => {
          results.total++;
          
          const testResult = {
            name: test.title,
            file: testFile.name,
            status: test.status,
            duration: test.duration || 0
          };
          
          switch (test.status) {
            case 'passed':
              results.passed++;
              break;
            case 'failed':
              results.failed++;
              testResult.error = test.failureMessages?.join('\n');
              break;
            case 'skipped':
            case 'pending':
              results.skipped++;
              break;
          }
          
          results.tests.push(testResult);
        });
      });
    }
    
    return results;
  }

  parseTextOutput(stdout, stderr, environment) {
    const results = {
      environment,
      total: 0,
      passed: 0,
      failed: 0,
      skipped: 0,
      tests: [],
      errors: []
    };
    
    // Parse Jest text output patterns
    const passedMatch = stdout.match(/(\d+) passing/);
    const failedMatch = stdout.match(/(\d+) failing/);
    const skippedMatch = stdout.match(/(\d+) pending/);
    
    if (passedMatch) results.passed = parseInt(passedMatch[1], 10);
    if (failedMatch) results.failed = parseInt(failedMatch[1], 10);
    if (skippedMatch) results.skipped = parseInt(skippedMatch[1], 10);
    
    results.total = results.passed + results.failed + results.skipped;
    
    // Extract individual test results
    const testLines = stdout.split('\n').filter(line => 
      line.includes('✓') || line.includes('✗') || line.includes('○')
    );
    
    testLines.forEach(line => {
      const testResult = this.parseTestLine(line);
      if (testResult) {
        results.tests.push(testResult);
      }
    });
    
    // Add errors from stderr
    if (stderr) {
      results.errors.push(stderr);
    }
    
    return results;
  }

  parseTestLine(line) {
    const trimmedLine = line.trim();
    
    if (trimmedLine.startsWith('✓')) {
      return {
        name: trimmedLine.substring(1).trim(),
        status: 'passed'
      };
    } else if (trimmedLine.startsWith('✗')) {
      return {
        name: trimmedLine.substring(1).trim(),
        status: 'failed'
      };
    } else if (trimmedLine.startsWith('○')) {
      return {
        name: trimmedLine.substring(1).trim(),
        status: 'skipped'
      };
    }
    
    return null;
  }

  async generateReport() {
    console.log('\n📄 Generating contract test report...');
    
    const reportDir = path.join(process.cwd(), 'test-results', 'contract-reports');
    await fs.mkdir(reportDir, { recursive: true });
    
    // Generate JSON report
    const jsonReportPath = path.join(reportDir, 'contract-test-results.json');
    await fs.writeFile(jsonReportPath, JSON.stringify(this.results, null, 2));
    
    // Generate HTML report if requested
    if (this.options.reportFormat === 'html') {
      const htmlReportPath = path.join(reportDir, 'contract-test-report.html');
      const htmlContent = this.generateHtmlReport();
      await fs.writeFile(htmlReportPath, htmlContent);
      console.log(`📊 HTML report generated: ${htmlReportPath}`);
    }
    
    // Generate summary
    this.printSummary();
    
    return {
      jsonReport: jsonReportPath,
      htmlReport: this.options.reportFormat === 'html' ? path.join(reportDir, 'contract-test-report.html') : null
    };
  }

  generateHtmlReport() {
    const { summary, environments, timestamp } = this.results;
    
    return `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Contract Test Report</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0; padding: 20px; background: #f5f5f5; color: #333;
        }
        .container { 
            max-width: 1200px; margin: 0 auto; background: white;
            border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 30px;
        }
        .header { border-bottom: 3px solid #007acc; padding-bottom: 20px; margin-bottom: 30px; }
        .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 40px; }
        .metric { background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; }
        .metric-value { font-size: 2.5em; font-weight: bold; margin-bottom: 10px; }
        .metric-label { color: #666; font-size: 0.9em; }
        .passed { color: #28a745; border-left: 4px solid #28a745; }
        .failed { color: #dc3545; border-left: 4px solid #dc3545; }
        .skipped { color: #ffc107; border-left: 4px solid #ffc107; }
        .environment { margin-bottom: 40px; }
        .environment h2 { color: #007acc; border-bottom: 1px solid #dee2e6; padding-bottom: 10px; }
        .test-grid { display: grid; gap: 10px; }
        .test-item { 
            display: flex; align-items: center; padding: 10px;
            background: #f8f9fa; border-radius: 4px; border-left: 4px solid #dee2e6;
        }
        .test-item.passed { border-left-color: #28a745; }
        .test-item.failed { border-left-color: #dc3545; background: #ffeaea; }
        .test-item.skipped { border-left-color: #ffc107; }
        .test-status { margin-right: 10px; font-weight: bold; }
        .test-name { flex: 1; }
        .test-duration { font-size: 0.8em; color: #666; }
        .error-details { margin-top: 5px; font-size: 0.8em; color: #dc3545; font-family: monospace; }
        .timestamp { text-align: center; color: #666; margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📋 API Contract Test Report</h1>
            <p>Comprehensive validation of API endpoint contracts and response formats</p>
        </div>
        
        <div class="summary">
            <div class="metric">
                <div class="metric-value">${summary.total}</div>
                <div class="metric-label">Total Tests</div>
            </div>
            <div class="metric passed">
                <div class="metric-value">${summary.passed}</div>
                <div class="metric-label">Passed</div>
            </div>
            <div class="metric failed">
                <div class="metric-value">${summary.failed}</div>
                <div class="metric-label">Failed</div>
            </div>
            <div class="metric skipped">
                <div class="metric-value">${summary.skipped}</div>
                <div class="metric-label">Skipped</div>
            </div>
        </div>

        ${Object.entries(environments).map(([envName, envResults]) => `
        <div class="environment">
            <h2>🌍 ${envName.toUpperCase()} Environment</h2>
            
            ${envResults.error ? `
                <div class="test-item failed">
                    <span class="test-status">❌</span>
                    <span class="test-name">Environment Error: ${envResults.error}</span>
                </div>
            ` : `
                <div class="test-grid">
                    ${envResults.tests?.map(test => `
                        <div class="test-item ${test.status}">
                            <span class="test-status">${this.getStatusIcon(test.status)}</span>
                            <span class="test-name">${test.name}</span>
                            ${test.duration ? `<span class="test-duration">${test.duration}ms</span>` : ''}
                            ${test.error ? `<div class="error-details">${test.error}</div>` : ''}
                        </div>
                    `).join('') || '<div class="test-item">No tests found</div>'}
                </div>
            `}
        </div>
        `).join('')}

        <div class="timestamp">
            Report generated on ${new Date(timestamp).toLocaleString()}
        </div>
    </div>
</body>
</html>`;
  }

  getStatusIcon(status) {
    switch (status) {
      case 'passed': return '✅';
      case 'failed': return '❌';
      case 'skipped': return '⏭️';
      default: return '❓';
    }
  }

  printSummary() {
    const { summary, environments } = this.results;
    
    console.log('\n📊 Contract Test Summary');
    console.log('========================');
    console.log(`Total Tests: ${summary.total}`);
    console.log(`Passed: ${summary.passed} (${((summary.passed / summary.total) * 100).toFixed(1)}%)`);
    console.log(`Failed: ${summary.failed} (${((summary.failed / summary.total) * 100).toFixed(1)}%)`);
    console.log(`Skipped: ${summary.skipped} (${((summary.skipped / summary.total) * 100).toFixed(1)}%)`);
    
    console.log('\nEnvironment Results:');
    Object.entries(environments).forEach(([env, results]) => {
      const successRate = results.total > 0 ? ((results.passed / results.total) * 100).toFixed(1) : '0';
      console.log(`  ${env}: ${results.passed}/${results.total} (${successRate}%)`);
    });
    
    if (summary.failed > 0) {
      console.log('\n❌ Some contract tests failed. Review the report for details.');
      throw new Error('Contract tests failed');
    } else {
      console.log('\n✅ All contract tests passed!');
    }
  }
}

// CLI usage
if (require.main === module) {
  const runner = new ContractTestRunner({
    environments: process.argv.includes('--env') 
      ? process.argv[process.argv.indexOf('--env') + 1].split(',')
      : ['test'],
    failFast: process.argv.includes('--fail-fast'),
    generateReport: !process.argv.includes('--no-report'),
    reportFormat: process.argv.includes('--json-only') ? 'json' : 'html'
  });
  
  runner.runAllTests()
    .then(() => {
      console.log('\n🎉 Contract testing completed');
    })
    .catch((error) => {
      console.error('\n💥 Contract testing failed:', error.message);
      throw error;
    });
}

module.exports = ContractTestRunner;