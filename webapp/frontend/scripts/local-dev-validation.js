#!/usr/bin/env node

/**
 * Local Development Validation Script
 * Catches build errors, console errors, and test failures before pushing
 */

import { execSync } from 'child_process';
import { createServer } from 'vite';
import puppeteer from 'puppeteer';
import chalk from 'chalk';

const VALIDATION_STEPS = [
  'Build Check',
  'Type Check', 
  'Unit Tests',
  'Console Error Check',
  'Integration Tests (Sample)'
];

let currentStep = 0;
const errors = [];

function logStep(step, status = 'running') {
  const icons = {
    running: '🔄',
    success: '✅', 
    error: '❌',
    warning: '⚠️'
  };
  
  console.log(`${icons[status]} ${step}`);
}

function runCommand(command, description) {
  logStep(`${description}...`, 'running');
  try {
    const result = execSync(command, { 
      encoding: 'utf8',
      stdio: ['inherit', 'pipe', 'pipe']
    });
    logStep(description, 'success');
    return { success: true, output: result };
  } catch (error) {
    logStep(description, 'error');
    errors.push({ step: description, error: error.message });
    return { success: false, error: error.message };
  }
}

async function checkConsoleErrors() {
  logStep('Checking for console errors...', 'running');
  
  let browser;
  const consoleErrors = [];
  
  try {
    browser = await puppeteer.launch({ headless: true });
    const page = await browser.newPage();
    
    // Capture console errors
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });
    
    page.on('pageerror', (error) => {
      consoleErrors.push(`Page Error: ${error.message}`);
    });
    
    // Start dev server
    const server = await createServer({
      server: { port: 3001 }
    });
    await server.listen();
    
    // Navigate to key pages and check for errors
    const pagesToTest = [
      'http://localhost:3001/',
      'http://localhost:3001/dashboard',
      'http://localhost:3001/portfolio',
      'http://localhost:3001/trading'
    ];
    
    for (const url of pagesToTest) {
      try {
        await page.goto(url, { waitUntil: 'networkidle0', timeout: 10000 });
        await page.waitForTimeout(2000); // Let any delayed errors surface
      } catch (navError) {
        consoleErrors.push(`Navigation error on ${url}: ${navError.message}`);
      }
    }
    
    await server.close();
    
    if (consoleErrors.length > 0) {
      logStep('Console Error Check', 'error');
      errors.push({
        step: 'Console Error Check',
        error: `Found ${consoleErrors.length} console errors`,
        details: consoleErrors
      });
      return false;
    } else {
      logStep('Console Error Check', 'success');
      return true;
    }
    
  } catch (error) {
    logStep('Console Error Check', 'error');
    errors.push({
      step: 'Console Error Check', 
      error: `Failed to run console check: ${error.message}`
    });
    return false;
  } finally {
    if (browser) await browser.close();
  }
}

async function storeValidationResults(buildResult, testResult, consoleResult) {
  try {
    const validationData = {
      validationType: 'full',
      results: {
        build: {
          success: buildResult.success,
          output: buildResult.output,
          error: buildResult.error,
          duration: Date.now() // Placeholder timing
        },
        test: {
          success: testResult.success,
          output: testResult.output,
          error: testResult.error,
          duration: Date.now() // Placeholder timing
        },
        console: {
          success: consoleResult,
          errorCount: consoleResult ? 0 : 1,
          timestamp: new Date().toISOString()
        }
      },
      environment: 'development',
      metadata: {
        script: 'local-dev-validation',
        steps: VALIDATION_STEPS,
        currentStep: VALIDATION_STEPS.length,
        totalErrors: errors.length
      }
    };

    // Store results via validation API (if available)
    try {
      const response = await fetch('/api/validation/results', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${process.env.DEV_TOKEN || 'dev-token'}`
        },
        body: JSON.stringify(validationData)
      });
      
      if (response.ok) {
        const result = await response.json();
        console.log(chalk.green(`✅ Validation results stored with ID: ${result.data.validationId}`));
      }
    } catch (apiError) {
      console.log(chalk.yellow(`⚠️  API storage failed: ${apiError.message}`));
    }
  } catch (error) {
    console.log(chalk.yellow(`⚠️  Result storage failed: ${error.message}`));
  }
}

async function main() {
  console.log(chalk.blue.bold('\n🚀 Running Local Development Validation\n'));
  
  // Step 1: Build Check
  const buildResult = runCommand('npm run build', 'Build Check');
  
  // Step 2: Type Check (if available)
  try {
    runCommand('npm run typecheck', 'Type Check');
  } catch {
    console.log(chalk.yellow('⚠️  No typecheck script found, skipping...'));
  }
  
  // Step 3: Unit Tests (fast subset)
  const testResult = runCommand(
    'npm run test:unit -- --run --reporter=basic', 
    'Unit Tests'
  );
  
  // Step 4: Console Error Check
  const consoleResult = await checkConsoleErrors();
  
  // Step 5: Sample Integration Tests
  try {
    runCommand(
      'npm run test:integration -- --run --reporter=basic src/tests/integration/basic-smoke-vitest.test.js', 
      'Integration Tests (Sample)'
    );
  } catch {
    console.log(chalk.yellow('⚠️  Integration tests not available, skipping...'));
  }

  // Store validation results using the previously dead variables
  await storeValidationResults(buildResult, testResult, consoleResult);
  
  // Results Summary
  console.log(chalk.blue.bold('\n📊 Validation Summary\n'));
  
  if (errors.length === 0) {
    console.log(chalk.green.bold('✅ ALL CHECKS PASSED! Safe to push.\n'));
    
    console.log(chalk.cyan('Next steps:'));
    console.log('  git add .');
    console.log('  git commit -m "Your commit message"');
    console.log('  git push origin your-branch\n');
    
    process.exit(0);
  } else {
    console.log(chalk.red.bold(`❌ ${errors.length} ISSUES FOUND\n`));
    
    errors.forEach((error, index) => {
      console.log(chalk.red(`${index + 1}. ${error.step}`));
      console.log(chalk.gray(`   ${error.error}`));
      if (error.details) {
        error.details.forEach(detail => {
          console.log(chalk.gray(`   - ${detail}`));
        });
      }
      console.log();
    });
    
    console.log(chalk.yellow.bold('🔧 Fix these issues before pushing:\n'));
    process.exit(1);
  }
}

main().catch(error => {
  console.error(chalk.red.bold('❌ Validation script failed:'), error);
  process.exit(1);
});