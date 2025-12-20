#!/usr/bin/env node

/**
 * Comprehensive Test Runner
 * 
 * Runs all test types across frontend and backend with comprehensive reporting.
 * Supports various test execution modes and generates detailed reports.
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const { TestEnvironmentSetup, TestResultAggregator } = require('./test-environment-setup');

class ComprehensiveTestRunner {
  constructor(options = {}) {
    this.options = {
      parallel: options.parallel ?? true,
      coverage: options.coverage ?? true,
      skipE2E: options.skipE2E ?? false,
      skipVisual: options.skipVisual ?? false,
      outputDir: options.outputDir ?? './test-results',
      verbose: options.verbose ?? false,
      failFast: options.failFast ?? false,
      testTypes: options.testTypes ?? ['unit', 'integration', 'security', 'performance', 'contract'],
      ...options
    };

    this.aggregator = new TestResultAggregator();
    this.startTime = Date.now();
  }

  /**
   * Run all comprehensive tests
   */
  async runAllTests() {
    this.log('🧪 Starting Comprehensive Test Suite');
    this.log(`📋 Test Types: ${this.options.testTypes.join(', ')}`);
    this.log(`⚡ Parallel: ${this.options.parallel}`);
    this.log(`📊 Coverage: ${this.options.coverage}`);
    
    try {
      // Setup test environment
      this.ensureOutputDirectory();
      TestEnvironmentSetup.setupEnvironment('integration');

      // Check dependencies
      await this.checkDependencies();

      // Run tests in specified order
      const testResults = {
        unit: null,
        integration: null,
        security: null,
        performance: null,
        contract: null,
        e2e: null,
        visual: null
      };

      // Phase 1: Unit Tests (fastest)
      if (this.options.testTypes.includes('unit')) {
        testResults.unit = await this.runUnitTests();
        if (this.options.failFast && testResults.unit.failed > 0) {
          throw new Error('Unit tests failed - stopping execution');
        }
      }

      // Phase 2: Integration Tests
      if (this.options.testTypes.includes('integration')) {
        testResults.integration = await this.runIntegrationTests();
        if (this.options.failFast && testResults.integration.failed > 0) {
          throw new Error('Integration tests failed - stopping execution');
        }
      }

      // Phase 3: Security Tests
      if (this.options.testTypes.includes('security')) {
        testResults.security = await this.runSecurityTests();
        if (this.options.failFast && testResults.security.failed > 0) {
          throw new Error('Security tests failed - stopping execution');
        }
      }

      // Phase 4: Contract Tests
      if (this.options.testTypes.includes('contract')) {
        testResults.contract = await this.runContractTests();
        if (this.options.failFast && testResults.contract.failed > 0) {
          throw new Error('Contract tests failed - stopping execution');
        }
      }

      // Phase 5: Performance Tests (slower)
      if (this.options.testTypes.includes('performance')) {
        testResults.performance = await this.runPerformanceTests();
      }

      // Phase 6: E2E Tests (slowest)
      if (this.options.testTypes.includes('e2e') && !this.options.skipE2E) {
        testResults.e2e = await this.runE2ETests();
      }

      // Phase 7: Visual Tests (requires specific setup)
      if (this.options.testTypes.includes('visual') && !this.options.skipVisual) {
        testResults.visual = await this.runVisualTests();
      }

      // Generate comprehensive report
      const report = await this.generateFinalReport(testResults);
      
      // Output results
      this.displayResults(report);
      
      // Return success/failure status
      const totalFailed = report.summary.totalFailed;
      if (totalFailed > 0) {
        throw new Error(`${totalFailed} test(s) failed`);
      }
      
      this.log('✅ All tests completed successfully!');
      return report;

    } catch (error) {
      this.error('❌ Test suite failed:', error.message);
      throw error;
    } finally {
      TestEnvironmentSetup.cleanupEnvironment();
    }
  }

  /**
   * Run unit tests for both frontend and backend
   */
  async runUnitTests() {
    this.log('🔬 Running Unit Tests...');
    
    const tasks = [];

    // Frontend unit tests
    tasks.push(
      this.runTestCommand('frontend', 'npm run test:unit', 'Unit Tests - Frontend')
    );

    // Backend unit tests  
    tasks.push(
      this.runTestCommand('backend', 'npm run test:unit', 'Unit Tests - Backend')
    );

    const results = this.options.parallel 
      ? await Promise.all(tasks)
      : await this.runSequentially(tasks);

    const aggregated = this.aggregateResults(results, 'unit');
    this.log(`✅ Unit Tests: ${aggregated.passed}/${aggregated.total} passed`);
    
    return aggregated;
  }

  /**
   * Run integration tests
   */
  async runIntegrationTests() {
    this.log('🔗 Running Integration Tests...');
    
    const tasks = [];

    // Frontend integration tests
    tasks.push(
      this.runTestCommand('frontend', 'npm run test:integration', 'Integration Tests - Frontend')
    );

    // Backend integration tests
    tasks.push(
      this.runTestCommand('backend', 'npm run test:integration', 'Integration Tests - Backend')
    );

    const results = this.options.parallel 
      ? await Promise.all(tasks)
      : await this.runSequentially(tasks);

    const aggregated = this.aggregateResults(results, 'integration');
    this.log(`✅ Integration Tests: ${aggregated.passed}/${aggregated.total} passed`);
    
    return aggregated;
  }

  /**
   * Run security tests
   */
  async runSecurityTests() {
    this.log('🛡️ Running Security Tests...');
    
    const tasks = [];

    // Frontend security tests
    tasks.push(
      this.runTestCommand('frontend', 'npm run test:security', 'Security Tests - Frontend')
    );

    // Backend security tests
    tasks.push(
      this.runTestCommand('backend', 'npm run test:security', 'Security Tests - Backend')
    );

    // Security audits
    tasks.push(
      this.runTestCommand('frontend', 'npm audit --audit-level=high', 'Security Audit - Frontend')
    );
    
    tasks.push(
      this.runTestCommand('backend', 'npm audit --audit-level=high', 'Security Audit - Backend')
    );

    const results = this.options.parallel 
      ? await Promise.all(tasks)
      : await this.runSequentially(tasks);

    const aggregated = this.aggregateResults(results, 'security');
    this.log(`✅ Security Tests: ${aggregated.passed}/${aggregated.total} passed`);
    
    return aggregated;
  }

  /**
   * Run performance tests
   */
  async runPerformanceTests() {
    this.log('⚡ Running Performance Tests...');
    
    const tasks = [];

    // Frontend performance tests
    tasks.push(
      this.runTestCommand('frontend', 'npm run test:performance', 'Performance Tests - Frontend')
    );

    // Backend performance tests
    tasks.push(
      this.runTestCommand('backend', 'npm run test:performance', 'Performance Tests - Backend')
    );

    // Run sequentially for accurate performance measurements
    const results = await this.runSequentially(tasks);

    const aggregated = this.aggregateResults(results, 'performance');
    this.log(`✅ Performance Tests: ${aggregated.passed}/${aggregated.total} passed`);
    
    return aggregated;
  }

  /**
   * Run contract tests
   */
  async runContractTests() {
    this.log('📋 Running Contract Tests...');
    
    const tasks = [];

    // API contract tests
    tasks.push(
      this.runTestCommand('backend', 'npm run test:contract', 'Contract Tests - API')
    );

    const results = await Promise.all(tasks);

    const aggregated = this.aggregateResults(results, 'contract');
    this.log(`✅ Contract Tests: ${aggregated.passed}/${aggregated.total} passed`);
    
    return aggregated;
  }

  /**
   * Run E2E tests
   */
  async runE2ETests() {
    this.log('🎯 Running E2E Tests...');
    
    const tasks = [];

    // Playwright E2E tests
    tasks.push(
      this.runTestCommand('frontend', 'npm run test:e2e', 'E2E Tests')
    );

    const results = await this.runSequentially(tasks); // E2E tests should run sequentially

    const aggregated = this.aggregateResults(results, 'e2e');
    this.log(`✅ E2E Tests: ${aggregated.passed}/${aggregated.total} passed`);
    
    return aggregated;
  }

  /**
   * Run visual regression tests
   */
  async runVisualTests() {
    this.log('👁️ Running Visual Tests...');
    
    const tasks = [];

    // Visual regression tests
    tasks.push(
      this.runTestCommand('frontend', 'npm run test:visual', 'Visual Tests')
    );

    const results = await this.runSequentially(tasks);

    const aggregated = this.aggregateResults(results, 'visual');
    this.log(`✅ Visual Tests: ${aggregated.passed}/${aggregated.total} passed`);
    
    return aggregated;
  }

  /**
   * Run a test command and capture results
   */
  async runTestCommand(component, command, description) {
    const workingDir = component === 'frontend' 
      ? path.join(process.cwd(), 'webapp/frontend')
      : path.join(process.cwd(), 'webapp/lambda');

    this.log(`  🏃 ${description}...`);
    
    try {
      const output = execSync(command, {
        cwd: workingDir,
        encoding: 'utf8',
        timeout: 300000, // 5 minutes timeout
        env: {
          ...process.env,
          NODE_ENV: 'test',
          CI: 'true'
        }
      });

      // Parse test results (simplified - would need specific parsers for Jest/Vitest)
      const results = this.parseTestOutput(output, description);
      
      if (this.options.verbose) {
        this.log(`    ✅ ${description}: ${results.passed}/${results.total} passed`);
      }

      return { component, description, success: true, ...results, output };

    } catch (error) {
      const results = this.parseTestOutput(error.stdout || '', description);
      
      this.log(`    ❌ ${description}: ${results.passed}/${results.total} passed (${results.failed} failed)`);
      
      if (this.options.verbose) {
        this.log(`    Error: ${error.message}`);
      }

      return { 
        component, 
        description, 
        success: false, 
        ...results, 
        error: error.message,
        output: error.stdout || ''
      };
    }
  }

  /**
   * Parse test output to extract results
   */
  parseTestOutput(output, _description) {
    // Basic parsing - would need more sophisticated parsing for real implementation
    const lines = output.split('\n');
    
    let passed = 0;
    let failed = 0;
    let total = 0;

    // Look for common test result patterns
    for (const line of lines) {
      // Jest patterns
      if (line.includes('Tests:')) {
        const match = line.match(/(\d+) passed, (\d+) failed, (\d+) total/);
        if (match) {
          passed = parseInt(match[1]);
          failed = parseInt(match[2]);
          total = parseInt(match[3]);
        }
      }
      
      // Vitest patterns
      if (line.includes('Test Files')) {
        const passedMatch = line.match(/(\d+) passed/);
        const failedMatch = line.match(/(\d+) failed/);
        if (passedMatch) passed = parseInt(passedMatch[1]);
        if (failedMatch) failed = parseInt(failedMatch[1]);
        total = passed + failed;
      }

      // Playwright patterns
      if (line.includes('passed') && line.includes('failed')) {
        const match = line.match(/(\d+) passed.*?(\d+) failed/);
        if (match) {
          passed = parseInt(match[1]);
          failed = parseInt(match[2]);
          total = passed + failed;
        }
      }
    }

    // Fallback: if we can't parse, assume success if no error
    if (total === 0 && !output.includes('failed') && !output.includes('error')) {
      passed = 1;
      total = 1;
    }

    return { passed, failed, total };
  }

  /**
   * Run tasks sequentially
   */
  async runSequentially(tasks) {
    const results = [];
    for (const task of tasks) {
      if (typeof task === 'function') {
        results.push(await task());
      } else {
        results.push(await task);
      }
    }
    return results;
  }

  /**
   * Aggregate results from multiple test runs
   */
  aggregateResults(results, testType) {
    const aggregated = {
      passed: 0,
      failed: 0,
      total: 0,
      results: results
    };

    for (const result of results) {
      aggregated.passed += result.passed || 0;
      aggregated.failed += result.failed || 0;
      aggregated.total += result.total || 0;
    }

    this.aggregator.addResults(testType, aggregated);
    return aggregated;
  }

  /**
   * Check test dependencies
   */
  async checkDependencies() {
    this.log('🔍 Checking test dependencies...');
    
    const missing = TestEnvironmentSetup.checkTestDependencies();
    
    if (missing.frontend.length > 0 || missing.backend.length > 0) {
      this.log('⚠️ Missing test dependencies found');
      
      if (!this.options.skipInstall) {
        this.log('📦 Installing missing dependencies...');
        TestEnvironmentSetup.installMissingDependencies(missing);
        this.log('✅ Dependencies installed');
      } else {
        this.log('⚠️ Skipping dependency installation (use --install to enable)');
      }
    } else {
      this.log('✅ All test dependencies are available');
    }
  }

  /**
   * Ensure output directory exists
   */
  ensureOutputDirectory() {
    if (!fs.existsSync(this.options.outputDir)) {
      fs.mkdirSync(this.options.outputDir, { recursive: true });
    }
  }

  /**
   * Generate final comprehensive report
   */
  async generateFinalReport(_testResults) {
    const report = this.aggregator.generateReport();
    const duration = Date.now() - this.startTime;
    
    report.execution = {
      duration: `${(duration / 1000).toFixed(2)}s`,
      startTime: new Date(this.startTime).toISOString(),
      endTime: new Date().toISOString(),
      options: this.options
    };

    // Save JSON report
    const jsonReportPath = path.join(this.options.outputDir, 'test-report.json');
    fs.writeFileSync(jsonReportPath, JSON.stringify(report, null, 2));

    // Generate and save HTML report
    const htmlReport = this.aggregator.generateHtmlReport();
    const htmlReportPath = path.join(this.options.outputDir, 'test-report.html');
    fs.writeFileSync(htmlReportPath, htmlReport);

    this.log(`📊 Reports generated:`);
    this.log(`   JSON: ${jsonReportPath}`);
    this.log(`   HTML: ${htmlReportPath}`);

    return report;
  }

  /**
   * Display final results
   */
  displayResults(report) {
    const duration = report.execution.duration;
    const { totalTests, totalPassed, totalFailed, successRate } = report.summary;

    console.log('\n' + '='.repeat(60));
    console.log('🧪 COMPREHENSIVE TEST RESULTS');
    console.log('='.repeat(60));
    console.log(`📊 Total Tests: ${totalTests}`);
    console.log(`✅ Passed: ${totalPassed}`);
    console.log(`❌ Failed: ${totalFailed}`);
    console.log(`📈 Success Rate: ${successRate}%`);
    console.log(`⏱️ Duration: ${duration}`);
    console.log('='.repeat(60));

    // Display results by test type
    Object.entries(report.byType).forEach(([type, results]) => {
      if (results.total > 0) {
        const typeSuccessRate = ((results.passed / results.total) * 100).toFixed(1);
        const status = results.failed === 0 ? '✅' : '❌';
        console.log(`${status} ${type.toUpperCase()}: ${results.passed}/${results.total} (${typeSuccessRate}%)`);
      }
    });

    console.log('='.repeat(60));

    if (totalFailed === 0) {
      console.log('🎉 ALL TESTS PASSED! 🎉');
    } else {
      console.log(`⚠️  ${totalFailed} TEST(S) FAILED - Review the detailed report`);
    }
  }

  /**
   * Log with timestamp
   */
  log(message) {
    const timestamp = new Date().toISOString().split('T')[1].split('.')[0];
    console.log(`[${timestamp}] ${message}`);
  }

  /**
   * Error log
   */
  error(message, details) {
    const timestamp = new Date().toISOString().split('T')[1].split('.')[0];
    console.error(`[${timestamp}] ${message}`);
    if (details) {
      console.error(`[${timestamp}] ${details}`);
    }
  }
}

// CLI interface
function parseArgs() {
  const args = process.argv.slice(2);
  const options = {};

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    
    switch (arg) {
      case '--parallel':
        options.parallel = true;
        break;
      case '--sequential':
        options.parallel = false;
        break;
      case '--no-coverage':
        options.coverage = false;
        break;
      case '--skip-e2e':
        options.skipE2E = true;
        break;
      case '--skip-visual':
        options.skipVisual = true;
        break;
      case '--verbose':
        options.verbose = true;
        break;
      case '--fail-fast':
        options.failFast = true;
        break;
      case '--output-dir':
        options.outputDir = args[i + 1];
        i++;
        break;
      case '--types':
        options.testTypes = args[i + 1].split(',');
        i++;
        break;
      case '--help':
        console.log(`
Comprehensive Test Runner

Usage: node run-comprehensive-tests.js [options]

Options:
  --parallel         Run tests in parallel (default: true)
  --sequential       Run tests sequentially
  --no-coverage      Skip coverage collection
  --skip-e2e         Skip E2E tests
  --skip-visual      Skip visual regression tests
  --verbose          Detailed output
  --fail-fast        Stop on first failure
  --output-dir DIR   Output directory for reports (default: ./test-results)
  --types TYPE,TYPE  Test types to run (default: unit,integration,security,performance,contract)
  --help             Show this help message

Examples:
  node run-comprehensive-tests.js --verbose
  node run-comprehensive-tests.js --types unit,integration --parallel
  node run-comprehensive-tests.js --skip-e2e --fail-fast
        `);
        return options;
    }
  }

  return options;
}

// Run if called directly
if (require.main === module) {
  const options = parseArgs();
  const runner = new ComprehensiveTestRunner(options);
  runner.runAllTests().catch(error => {
    console.error('Fatal error:', error);
    throw error;
  });
}

module.exports = { ComprehensiveTestRunner };