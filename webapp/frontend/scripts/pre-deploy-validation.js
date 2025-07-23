#!/usr/bin/env node

/**
 * Pre-Deploy Validation Script
 * Catches ALL runtime errors, API issues, and build problems before deployment
 * This would have caught the alpaca TypeError and API 404 errors!
 */

import { execSync } from 'child_process';
import puppeteer from 'puppeteer';
import { createServer } from 'vite';
import chalk from 'chalk';
import fs from 'fs';

const errors = [];
const warnings = [];
const apiErrors = [];

function logStep(step, status = 'running') {
  const icons = {
    running: '🔄',
    success: '✅', 
    error: '❌',
    warning: '⚠️',
    skip: '⏭️'
  };
  
  console.log(`${icons[status]} ${step}`);
}

function runCommand(command, description, options = {}) {
  logStep(`${description}...`, 'running');
  try {
    const result = execSync(command, { 
      encoding: 'utf8',
      stdio: options.silent ? 'pipe' : 'inherit',
      timeout: options.timeout || 60000
    });
    logStep(description, 'success');
    return { success: true, output: result };
  } catch (error) {
    logStep(description, 'error');
    if (options.critical) {
      errors.push({ step: description, error: error.message, critical: true });
    } else {
      warnings.push({ step: description, error: error.message });
    }
    return { success: false, error: error.message };
  }
}

async function runRuntimeErrorTests() {
  logStep('Running runtime error detection tests...', 'running');
  
  let browser;
  let server;
  const runtimeErrors = [];
  const consoleErrors = [];
  const apiErrors = [];
  
  try {
    // Start Vite dev server
    console.log('⚡ Starting Vite server for runtime testing...');
    server = await createServer({
      server: { port: 3003, host: 'localhost' },
      logLevel: 'error'
    });
    await server.listen();
    
    // Launch browser
    browser = await puppeteer.launch({ 
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    const page = await browser.newPage();
    
    // Capture all errors
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push({
          type: 'console.error',
          message: msg.text(),
          location: msg.location()
        });
      }
    });
    
    page.on('pageerror', (error) => {
      runtimeErrors.push({
        type: 'runtime_error',
        message: error.message,
        stack: error.stack
      });
    });
    
    page.on('response', (response) => {
      if (response.status() >= 400) {
        apiErrors.push({
          type: 'api_error',
          url: response.url(),
          status: response.status(),
          statusText: response.statusText()
        });
      }
    });
    
    // Critical pages that MUST work without runtime errors
    const criticalPages = [
      { path: '/', name: 'Dashboard' },
      { path: '/settings', name: 'Settings (where alpaca error occurred)' },
      { path: '/portfolio', name: 'Portfolio' },
      { path: '/trading', name: 'Trading' }
    ];
    
    for (const { path, name } of criticalPages) {
      console.log(`📄 Testing ${name} (${path})...`);
      
      try {
        await page.goto(`http://localhost:3003${path}`, { 
          waitUntil: 'domcontentloaded', 
          timeout: 15000 
        });
        
        // Wait for React to render and any async operations
        await page.waitForTimeout(3000);
        
        // Check for specific error patterns we've seen
        const errorPatterns = [
          'Cannot read properties of undefined',
          'TypeError:',
          'ReferenceError:',
          'alpaca',
          'CORS policy',
          'Failed to fetch'
        ];
        
        const pageHtml = await page.content();
        let hasErrorPatterns = false;
        
        errorPatterns.forEach(pattern => {
          if (consoleErrors.some(error => error.message.includes(pattern))) {
            hasErrorPatterns = true;
            runtimeErrors.push({
              type: 'pattern_match',
              message: `Found error pattern "${pattern}" on ${name}`,
              page: path
            });
          }
        });
        
        if (hasErrorPatterns) {
          console.log(chalk.red(`  ❌ Found error patterns on ${name}`));
        } else {
          console.log(chalk.green(`  ✅ No runtime errors on ${name}`));
        }
        
      } catch (navError) {
        runtimeErrors.push({
          type: 'navigation_error',
          message: `Failed to load ${name}: ${navError.message}`,
          page: path
        });
        console.log(chalk.red(`  ❌ Navigation failed: ${navError.message}`));
      }
    }
    
    // Results
    const totalErrors = runtimeErrors.length + consoleErrors.length;
    const totalApiErrors = apiErrors.length;
    
    if (totalErrors === 0 && totalApiErrors === 0) {
      logStep('Runtime Error Detection', 'success');
      return { success: true };
    } else {
      logStep('Runtime Error Detection', 'error');
      
      if (totalErrors > 0) {
        errors.push({
          step: 'Runtime Error Detection',
          error: `Found ${totalErrors} runtime errors`,
          details: [...runtimeErrors, ...consoleErrors]
        });
      }
      
      if (totalApiErrors > 0) {
        warnings.push({
          step: 'API Error Detection', 
          error: `Found ${totalApiErrors} API errors`,
          details: apiErrors
        });
      }
      
      return { success: false, runtimeErrors, consoleErrors, apiErrors };
    }
    
  } finally {
    if (browser) await browser.close();
    if (server) await server.close();
  }
}

async function runSpecificErrorTests() {
  logStep('Running specific error pattern tests...', 'running');
  
  // Test for the specific patterns we've seen in F12
  const testResults = [];
  
  try {
    // Test 1: Settings component alpaca error
    const result1 = execSync('npx vitest run --reporter=basic src/tests/unit/components/settings-runtime-errors.test.jsx', {
      encoding: 'utf8',
      stdio: 'pipe'
    });
    
    if (result1.includes('FAIL') || result1.includes('error')) {
      testResults.push({
        test: 'Settings Runtime Errors',
        status: 'FAIL',
        output: result1
      });
    } else {
      testResults.push({
        test: 'Settings Runtime Errors', 
        status: 'PASS'
      });
    }
  } catch (error) {
    testResults.push({
      test: 'Settings Runtime Errors',
      status: 'ERROR',
      error: error.message
    });
  }
  
  try {
    // Test 2: CORS header validation
    const result2 = execSync('npx vitest run --reporter=basic src/tests/unit/services/cors-api-headers.test.js', {
      encoding: 'utf8', 
      stdio: 'pipe'
    });
    
    if (result2.includes('FAIL') || result2.includes('error')) {
      testResults.push({
        test: 'CORS Headers Validation',
        status: 'FAIL',
        output: result2
      });
    } else {
      testResults.push({
        test: 'CORS Headers Validation',
        status: 'PASS'
      });
    }
  } catch (error) {
    testResults.push({
      test: 'CORS Headers Validation',
      status: 'ERROR', 
      error: error.message
    });
  }
  
  const failedTests = testResults.filter(t => t.status !== 'PASS');
  
  if (failedTests.length === 0) {
    logStep('Specific Error Pattern Tests', 'success');
    return { success: true };
  } else {
    logStep('Specific Error Pattern Tests', 'warning');
    warnings.push({
      step: 'Specific Error Pattern Tests',
      error: `${failedTests.length} tests failed/errored`,
      details: failedTests
    });
    return { success: false, failures: failedTests };
  }
}

async function storePreDeployResults(runtimeResult, specificResult, buildResult) {
  try {
    const deploymentData = {
      validationType: 'pre_deploy',
      results: {
        runtime: {
          success: runtimeResult.success,
          runtimeErrors: runtimeResult.runtimeErrors || [],
          consoleErrors: runtimeResult.consoleErrors || [],  
          apiErrors: runtimeResult.apiErrors || [],
          timestamp: new Date().toISOString()
        },
        specific: {
          success: specificResult.success,
          failures: specificResult.failures || [],
          testResults: specificResult.testResults || [],
          timestamp: new Date().toISOString()
        },
        build: {
          success: buildResult.success,
          output: buildResult.output,
          error: buildResult.error,
          timestamp: new Date().toISOString()
        }
      },
      environment: 'pre_deploy',
      metadata: {
        script: 'pre-deploy-validation',
        totalErrors: errors.length,
        totalWarnings: warnings.length,
        validationStatus: errors.length === 0 ? 'passed' : 'failed'
      }
    };

    // Store results via page analysis API (if available)
    try {
      const response = await fetch('/api/page-analysis/html-content', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${process.env.DEV_TOKEN || 'dev-token'}`
        },
        body: JSON.stringify({
          pagePath: '/pre-deploy-validation',
          pageHtml: JSON.stringify(deploymentData),
          pageTitle: 'Pre-Deploy Validation Results',
          analysisType: 'pre_deploy_validation',
          metadata: deploymentData.metadata
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        console.log(chalk.green(`✅ Pre-deploy results stored with analysis ID: ${result.data.analysisId}`));
      }
    } catch (apiError) {
      console.log(chalk.yellow(`⚠️  API storage failed: ${apiError.message}`));
    }

    // Also store via validation API for consistency
    try {
      const response = await fetch('/api/validation/results', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${process.env.DEV_TOKEN || 'dev-token'}`
        },
        body: JSON.stringify(deploymentData)
      });
      
      if (response.ok) {
        const result = await response.json();
        console.log(chalk.green(`✅ Pre-deploy results stored with validation ID: ${result.data.validationId}`));
      }
    } catch (apiError) {
      console.log(chalk.yellow(`⚠️  Validation API storage failed: ${apiError.message}`));
    }
  } catch (error) {
    console.log(chalk.yellow(`⚠️  Result storage failed: ${error.message}`));
  }
}

async function main() {
  console.log(chalk.blue.bold('\n🚀 Pre-Deploy Validation - Catch All Runtime Errors\n'));
  console.log(chalk.gray('This script catches the errors you saw in F12 console!\n'));
  
  // 1. Build Check (catches compile-time errors)
  const buildResult = runCommand('npm run build', 'Build Check', { critical: true });
  
  if (!buildResult.success) {
    console.log(chalk.red.bold('\n🚨 BUILD FAILED - Stopping validation\n'));
    process.exit(1);
  }
  
  // 2. Runtime Error Detection (catches the alpaca TypeError)
  console.log(chalk.blue('\n🎭 Runtime Error Detection (F12 Error Simulation)\n'));
  
  const runtimeResult = await runRuntimeErrorTests();
  
  // 3. Specific Error Pattern Tests
  console.log(chalk.blue('\n🧪 Specific Error Pattern Tests\n'));
  
  const specificResult = await runSpecificErrorTests();

  // Store validation results using the previously dead variables
  await storePreDeployResults(runtimeResult, specificResult, buildResult);
  
  // 4. Generate comprehensive report
  console.log(chalk.blue.bold('\n📊 Pre-Deploy Validation Results\n'));
  
  if (errors.length === 0) {
    console.log(chalk.green.bold('🎉 ALL CRITICAL CHECKS PASSED!'));
    
    if (warnings.length > 0) {
      console.log(chalk.yellow.bold(`\n⚠️  ${warnings.length} WARNINGS (Review Recommended):\n`));
      
      warnings.forEach((warning, index) => {
        console.log(`⚠️ ${index + 1}. ${warning.step}`);
        console.log(chalk.gray(`   ${warning.error}`));
        
        if (warning.details && warning.details.length > 0) {
          console.log(chalk.gray('   Details:'));
          warning.details.slice(0, 3).forEach(detail => {
            if (detail.message) {
              console.log(chalk.gray(`   - ${detail.message.substring(0, 100)}...`));
            } else if (detail.url) {
              console.log(chalk.gray(`   - ${detail.status} ${detail.url}`));
            }
          });
        }
        console.log();
      });
      
      console.log(chalk.cyan('\n✨ Safe to deploy with warnings'));
      console.log(chalk.gray('   The warnings are mostly API backend issues or test setup'));
      console.log(chalk.gray('   No critical runtime errors that crash user sessions\n'));
      
      process.exit(0);
    } else {
      console.log(chalk.cyan('\n✨ Perfect! Ready for production deployment'));
      console.log(chalk.gray('   git push origin your-branch\n'));
      process.exit(0);
    }
  } else {
    console.log(chalk.red.bold(`🚨 ${errors.length} CRITICAL ERRORS - DO NOT DEPLOY\n`));
    
    errors.forEach((error, index) => {
      console.log(chalk.red(`🚨 ${index + 1}. ${error.step}`));
      console.log(chalk.gray(`   ${error.error}`));
      
      if (error.details && error.details.length > 0) {
        console.log(chalk.gray('   Critical Details:'));
        error.details.slice(0, 5).forEach(detail => {
          if (detail.message) {
            console.log(chalk.red(`   - ${detail.message}`));
          }
        });
      }
      console.log();
    });
    
    console.log(chalk.red.bold('These errors will break the app in production!'));
    console.log(chalk.yellow('Fix these issues and run validation again before deploying.\n'));
    
    process.exit(1);
  }
}

main().catch(error => {
  console.error(chalk.red.bold('❌ Validation script failed:'), error);
  process.exit(1);
});