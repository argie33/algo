#!/usr/bin/env node

/**
 * CI/CD Integration Script for Comprehensive Integration Testing
 * Automates test execution, reporting, and deployment validation
 */

const fs = require('fs');
const path = require('path');
const { execSync, spawn } = require('child_process');

class CICDIntegration {
  constructor() {
    this.config = {
      testTypes: {
        smoke: ['@smoke'],
        critical: ['@critical'],
        integration: ['@integration'],
        performance: ['@performance'],
        security: ['@security'],
        journey: ['@journey'],
        error: ['@error']
      },
      environments: {
        development: {
          baseURL: 'http://localhost:3000',
          apiURL: 'http://localhost:8000'
        },
        staging: {
          baseURL: process.env.STAGING_URL || 'https://staging.example.com',
          apiURL: process.env.STAGING_API_URL || 'https://api-staging.example.com'
        },
        production: {
          baseURL: process.env.PROD_URL || 'https://d1zb7knau41vl9.cloudfront.net',
          apiURL: process.env.PROD_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev'
        }
      },
      thresholds: {
        passRate: 95, // Minimum pass rate percentage
        maxDuration: 30 * 60 * 1000, // 30 minutes max
        maxRetries: 2,
        performance: {
          maxResponseTime: 5000,
          maxLoadTime: 10000
        }
      },
      notifications: {
        slack: process.env.SLACK_WEBHOOK,
        email: process.env.NOTIFICATION_EMAIL,
        teams: process.env.TEAMS_WEBHOOK
      }
    };
    
    this.results = {
      timestamp: new Date().toISOString(),
      environment: process.env.NODE_ENV || 'development',
      deployment: process.env.DEPLOYMENT_ID || 'local',
      tests: [],
      summary: {},
      artifacts: []
    };
  }

  async runPreDeploymentTests(environment = 'staging') {
    console.log('🚀 Running Pre-Deployment Integration Tests...');
    
    const testSuites = [
      { name: 'smoke', grep: '@smoke', required: true },
      { name: 'critical', grep: '@critical', required: true },
      { name: 'api-integration', file: 'api-integration.spec.js', required: true }
    ];
    
    return await this.executeTestSuites(testSuites, environment);
  }

  async runPostDeploymentTests(environment = 'production') {
    console.log('✅ Running Post-Deployment Validation Tests...');
    
    const testSuites = [
      { name: 'smoke', grep: '@smoke', required: true },
      { name: 'critical-journey', grep: '@critical.*@journey', required: true },
      { name: 'component-integration', file: 'component-integration.spec.js', required: false },
      { name: 'user-journey', file: 'user-journey-integration.spec.js', required: false }
    ];
    
    return await this.executeTestSuites(testSuites, environment);
  }

  async runFullIntegrationSuite(environment = 'staging') {
    console.log('🎯 Running Full Integration Test Suite...');
    
    const testSuites = [
      { name: 'webapp-integration', file: 'webapp-integration-comprehensive.spec.js', required: true },
      { name: 'component-integration', file: 'component-integration.spec.js', required: true },
      { name: 'api-integration', file: 'api-integration.spec.js', required: true },
      { name: 'user-journey', file: 'user-journey-integration.spec.js', required: true },
      { name: 'error-recovery', grep: '@error', required: false },
      { name: 'performance', grep: '@performance', required: false }
    ];
    
    return await this.executeTestSuites(testSuites, environment);
  }

  async runScheduledTests(environment = 'production') {
    console.log('⏰ Running Scheduled Integration Tests...');
    
    const testSuites = [
      { name: 'health-check', grep: '@smoke', required: true },
      { name: 'performance-monitoring', grep: '@performance', required: true },
      { name: 'error-detection', grep: '@error', required: false }
    ];
    
    return await this.executeTestSuites(testSuites, environment);
  }

  async executeTestSuites(testSuites, environment) {
    const startTime = Date.now();
    const envConfig = this.config.environments[environment];
    
    console.log(`🌍 Testing environment: ${environment}`);
    console.log(`📍 Base URL: ${envConfig.baseURL}`);
    console.log(`🔌 API URL: ${envConfig.apiURL}`);
    
    // Set environment variables
    process.env.E2E_BASE_URL = envConfig.baseURL;
    process.env.E2E_API_URL = envConfig.apiURL;
    
    let allTestsPassed = true;
    const results = [];
    
    for (const suite of testSuites) {
      console.log(`\n🧪 Running test suite: ${suite.name}`);
      
      try {
        const result = await this.runTestSuite(suite, environment);
        results.push(result);
        
        if (suite.required && !result.passed) {
          allTestsPassed = false;
          console.log(`❌ Required test suite failed: ${suite.name}`);
        }
        
        if (result.passed) {
          console.log(`✅ Test suite passed: ${suite.name}`);
        } else {
          console.log(`❌ Test suite failed: ${suite.name}`);
        }
        
      } catch (error) {
        console.error(`💥 Test suite error: ${suite.name}`, error.message);
        
        results.push({
          name: suite.name,
          passed: false,
          error: error.message,
          duration: 0,
          tests: []
        });
        
        if (suite.required) {
          allTestsPassed = false;
        }
      }
    }
    
    const endTime = Date.now();
    const totalDuration = endTime - startTime;
    
    // Generate comprehensive report
    const report = await this.generateReport(results, environment, totalDuration);
    
    // Send notifications
    if (process.env.CI === 'true') {
      await this.sendNotifications(report, allTestsPassed);
    }
    
    // Save artifacts
    await this.saveArtifacts(report);
    
    console.log(`\n📊 Test execution completed in ${(totalDuration / 1000).toFixed(2)}s`);
    console.log(`🎯 Overall result: ${allTestsPassed ? 'PASSED' : 'FAILED'}`);
    
    return {
      passed: allTestsPassed,
      report,
      duration: totalDuration
    };
  }

  async runTestSuite(suite, environment) {
    const startTime = Date.now();
    
    let playwrightArgs = [
      'test',
      '--reporter=json',
      `--output-dir=test-results/${suite.name}`,
      `--project=${environment === 'production' ? 'chromium-desktop' : 'chromium-desktop'}`,
      `--workers=${environment === 'production' ? '1' : '2'}`
    ];
    
    if (suite.file) {
      playwrightArgs.push(`tests/${suite.file}`);
    }
    
    if (suite.grep) {
      playwrightArgs.push('--grep', suite.grep);
    }
    
    // Add retries for production
    if (environment === 'production') {
      playwrightArgs.push('--retries', '2');
    }
    
    return new Promise((resolve, reject) => {
      const child = spawn('npx', ['playwright', ...playwrightArgs], {
        cwd: path.resolve(__dirname, '..'),
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env }
      });
      
      let stdout = '';
      let stderr = '';
      
      child.stdout.on('data', (data) => {
        stdout += data.toString();
      });
      
      child.stderr.on('data', (data) => {
        stderr += data.toString();
      });
      
      child.on('close', (code) => {
        const endTime = Date.now();
        const duration = endTime - startTime;
        
        try {
          // Parse test results
          const resultLines = stdout.split('\n').filter(line => line.trim().startsWith('{'));
          let testResults = null;
          
          for (const line of resultLines) {
            try {
              const parsed = JSON.parse(line);
              if (parsed.stats) {
                testResults = parsed;
                break;
              }
            } catch (e) {
              // Continue searching for valid JSON
            }
          }
          
          const result = {
            name: suite.name,
            passed: code === 0,
            exitCode: code,
            duration,
            stdout,
            stderr,
            tests: testResults ? this.parseTestResults(testResults) : [],
            environment
          };
          
          resolve(result);
          
        } catch (error) {
          reject(new Error(`Failed to parse test results: ${error.message}`));
        }
      });
      
      child.on('error', (error) => {
        reject(error);
      });
      
      // Set timeout
      setTimeout(() => {
        child.kill('SIGTERM');
        reject(new Error(`Test suite timeout: ${suite.name}`));
      }, this.config.thresholds.maxDuration);
    });
  }

  parseTestResults(testResults) {
    if (!testResults || !testResults.suites) {
      return [];
    }
    
    const tests = [];
    
    function extractTests(suite) {
      if (suite.tests) {
        suite.tests.forEach(test => {
          tests.push({
            title: test.title,
            status: test.status,
            duration: test.duration,
            error: test.error ? test.error.message : null,
            annotations: test.annotations || []
          });
        });
      }
      
      if (suite.suites) {
        suite.suites.forEach(extractTests);
      }
    }
    
    testResults.suites.forEach(extractTests);
    return tests;
  }

  async generateReport(results, environment, totalDuration) {
    const totalTests = results.reduce((sum, r) => sum + r.tests.length, 0);
    const passedTests = results.reduce((sum, r) => sum + r.tests.filter(t => t.status === 'passed').length, 0);
    const failedTests = results.reduce((sum, r) => sum + r.tests.filter(t => t.status === 'failed').length, 0);
    const skippedTests = results.reduce((sum, r) => sum + r.tests.filter(t => t.status === 'skipped').length, 0);
    
    const passRate = totalTests > 0 ? (passedTests / totalTests) * 100 : 0;
    
    const report = {
      timestamp: new Date().toISOString(),
      environment,
      deployment: process.env.DEPLOYMENT_ID || 'local',
      summary: {
        totalSuites: results.length,
        passedSuites: results.filter(r => r.passed).length,
        failedSuites: results.filter(r => !r.passed).length,
        totalTests,
        passedTests,
        failedTests,
        skippedTests,
        passRate: Math.round(passRate * 100) / 100,
        duration: totalDuration,
        threshold: this.config.thresholds.passRate
      },
      suites: results,
      status: passRate >= this.config.thresholds.passRate ? 'PASSED' : 'FAILED',
      artifacts: {\n        reportPath: `test-results/integration-report-${Date.now()}.json`,\n        screenshotsPath: 'test-results/screenshots',\n        videosPath: 'test-results/videos',\n        tracesPath: 'test-results/traces'\n      }\n    };\n    \n    return report;\n  }\n\n  async saveArtifacts(report) {\n    // Ensure results directory exists\n    const resultsDir = path.resolve(__dirname, '../test-results');\n    if (!fs.existsSync(resultsDir)) {\n      fs.mkdirSync(resultsDir, { recursive: true });\n    }\n    \n    // Save JSON report\n    const reportPath = path.join(resultsDir, `integration-report-${Date.now()}.json`);\n    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));\n    \n    // Generate HTML report\n    const htmlReport = this.generateHTMLReport(report);\n    const htmlPath = path.join(resultsDir, `integration-report-${Date.now()}.html`);\n    fs.writeFileSync(htmlPath, htmlReport);\n    \n    console.log(`📄 Report saved: ${reportPath}`);\n    console.log(`🌐 HTML report: ${htmlPath}`);\n    \n    return { reportPath, htmlPath };\n  }\n\n  generateHTMLReport(report) {\n    return `\n<!DOCTYPE html>\n<html>\n<head>\n    <title>Integration Test Report - ${report.environment}</title>\n    <style>\n        body { font-family: Arial, sans-serif; margin: 20px; }\n        .header { background: #f5f5f5; padding: 20px; border-radius: 5px; }\n        .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }\n        .metric { background: white; border: 1px solid #ddd; padding: 15px; border-radius: 5px; text-align: center; }\n        .metric h3 { margin: 0; color: #333; }\n        .metric .value { font-size: 24px; font-weight: bold; margin: 10px 0; }\n        .passed { color: #28a745; }\n        .failed { color: #dc3545; }\n        .suite { margin: 20px 0; border: 1px solid #ddd; border-radius: 5px; }\n        .suite-header { background: #f8f9fa; padding: 15px; border-bottom: 1px solid #ddd; }\n        .suite-tests { padding: 15px; }\n        .test { padding: 10px; border-bottom: 1px solid #eee; }\n        .test:last-child { border-bottom: none; }\n        .test-status { display: inline-block; width: 60px; text-align: center; padding: 2px 8px; border-radius: 3px; font-size: 12px; }\n        .status-passed { background: #d4edda; color: #155724; }\n        .status-failed { background: #f8d7da; color: #721c24; }\n        .status-skipped { background: #fff3cd; color: #856404; }\n    </style>\n</head>\n<body>\n    <div class=\"header\">\n        <h1>Integration Test Report</h1>\n        <p><strong>Environment:</strong> ${report.environment}</p>\n        <p><strong>Timestamp:</strong> ${report.timestamp}</p>\n        <p><strong>Deployment:</strong> ${report.deployment}</p>\n        <p><strong>Status:</strong> <span class=\"${report.status.toLowerCase()}\">${report.status}</span></p>\n    </div>\n    \n    <div class=\"summary\">\n        <div class=\"metric\">\n            <h3>Pass Rate</h3>\n            <div class=\"value ${report.summary.passRate >= report.summary.threshold ? 'passed' : 'failed'}\">\n                ${report.summary.passRate}%\n            </div>\n            <div>Threshold: ${report.summary.threshold}%</div>\n        </div>\n        <div class=\"metric\">\n            <h3>Test Suites</h3>\n            <div class=\"value\">${report.summary.totalSuites}</div>\n            <div class=\"passed\">${report.summary.passedSuites} passed</div>\n            <div class=\"failed\">${report.summary.failedSuites} failed</div>\n        </div>\n        <div class=\"metric\">\n            <h3>Total Tests</h3>\n            <div class=\"value\">${report.summary.totalTests}</div>\n            <div class=\"passed\">${report.summary.passedTests} passed</div>\n            <div class=\"failed\">${report.summary.failedTests} failed</div>\n        </div>\n        <div class=\"metric\">\n            <h3>Duration</h3>\n            <div class=\"value\">${Math.round(report.summary.duration / 1000)}s</div>\n        </div>\n    </div>\n    \n    <h2>Test Suite Results</h2>\n    ${report.suites.map(suite => `\n        <div class=\"suite\">\n            <div class=\"suite-header\">\n                <h3>${suite.name} <span class=\"${suite.passed ? 'passed' : 'failed'}\">${suite.passed ? 'PASSED' : 'FAILED'}</span></h3>\n                <p>Duration: ${Math.round(suite.duration / 1000)}s | Tests: ${suite.tests.length}</p>\n            </div>\n            <div class=\"suite-tests\">\n                ${suite.tests.map(test => `\n                    <div class=\"test\">\n                        <span class=\"test-status status-${test.status}\">${test.status}</span>\n                        <strong>${test.title}</strong>\n                        <span style=\"float: right;\">${test.duration}ms</span>\n                        ${test.error ? `<div style=\"color: #dc3545; margin-top: 5px; font-size: 12px;\">${test.error}</div>` : ''}\n                    </div>\n                `).join('')}\n            </div>\n        </div>\n    `).join('')}\n    \n</body>\n</html>\n    `;\n  }\n\n  async sendNotifications(report, passed) {\n    const status = passed ? '✅ PASSED' : '❌ FAILED';\n    const message = `\nIntegration Tests ${status}\nEnvironment: ${report.environment}\nPass Rate: ${report.summary.passRate}%\nDuration: ${Math.round(report.summary.duration / 1000)}s\nTests: ${report.summary.passedTests}/${report.summary.totalTests} passed\n    `;\n    \n    // Slack notification\n    if (this.config.notifications.slack) {\n      try {\n        await this.sendSlackNotification(message, passed, report);\n        console.log('📱 Slack notification sent');\n      } catch (error) {\n        console.error('Failed to send Slack notification:', error.message);\n      }\n    }\n    \n    // Email notification (if configured)\n    if (this.config.notifications.email) {\n      try {\n        await this.sendEmailNotification(message, passed, report);\n        console.log('📧 Email notification sent');\n      } catch (error) {\n        console.error('Failed to send email notification:', error.message);\n      }\n    }\n  }\n\n  async sendSlackNotification(message, passed, report) {\n    const fetch = require('node-fetch');\n    \n    const payload = {\n      text: `Integration Test Report - ${report.environment}`,\n      attachments: [\n        {\n          color: passed ? 'good' : 'danger',\n          fields: [\n            { title: 'Status', value: passed ? '✅ PASSED' : '❌ FAILED', short: true },\n            { title: 'Environment', value: report.environment, short: true },\n            { title: 'Pass Rate', value: `${report.summary.passRate}%`, short: true },\n            { title: 'Duration', value: `${Math.round(report.summary.duration / 1000)}s`, short: true },\n            { title: 'Tests', value: `${report.summary.passedTests}/${report.summary.totalTests}`, short: true },\n            { title: 'Deployment', value: report.deployment, short: true }\n          ],\n          footer: 'Integration Tests',\n          ts: Math.floor(Date.now() / 1000)\n        }\n      ]\n    };\n    \n    const response = await fetch(this.config.notifications.slack, {\n      method: 'POST',\n      headers: { 'Content-Type': 'application/json' },\n      body: JSON.stringify(payload)\n    });\n    \n    if (!response.ok) {\n      throw new Error(`Slack API error: ${response.statusText}`);\n    }\n  }\n\n  async sendEmailNotification(message, passed, report) {\n    // Email implementation would depend on your email service\n    // This is a placeholder for email notification logic\n    console.log('Email notification:', message);\n  }\n}\n\n// CLI Interface\nif (require.main === module) {\n  const cicd = new CICDIntegration();\n  \n  const command = process.argv[2];\n  const environment = process.argv[3] || 'staging';\n  \n  async function main() {\n    try {\n      let result;\n      \n      switch (command) {\n        case 'pre-deploy':\n          result = await cicd.runPreDeploymentTests(environment);\n          break;\n          \n        case 'post-deploy':\n          result = await cicd.runPostDeploymentTests(environment);\n          break;\n          \n        case 'full-suite':\n          result = await cicd.runFullIntegrationSuite(environment);\n          break;\n          \n        case 'scheduled':\n          result = await cicd.runScheduledTests(environment);\n          break;\n          \n        default:\n          console.log(`\nUsage: node ci-cd-integration.js <command> [environment]\n\nCommands:\n  pre-deploy    Run pre-deployment tests\n  post-deploy   Run post-deployment validation\n  full-suite    Run complete integration suite\n  scheduled     Run scheduled monitoring tests\n\nEnvironments:\n  development   Local development\n  staging       Staging environment\n  production    Production environment\n`);\n          process.exit(1);\n      }\n      \n      process.exit(result.passed ? 0 : 1);\n      \n    } catch (error) {\n      console.error('💥 CI/CD Integration Error:', error.message);\n      process.exit(1);\n    }\n  }\n  \n  main();\n}\n\nmodule.exports = CICDIntegration;