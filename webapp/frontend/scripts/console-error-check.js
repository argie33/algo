#!/usr/bin/env node

/**
 * Standalone Console Error Checker
 * Quick script to catch F12 console errors in development
 */

import puppeteer from 'puppeteer';
import { createServer } from 'vite';
import chalk from 'chalk';

const PAGES_TO_TEST = [
  '/',
  '/dashboard', 
  '/portfolio',
  '/trading',
  '/settings'
];

const CRITICAL_ERRORS = [
  'typography.pxToRem is not a function',
  'Cannot read properties of undefined',
  'TypeError:',
  'ReferenceError:',
  'SyntaxError:',
  'Uncaught Error:'
];

async function checkConsoleErrors() {
  let browser;
  let server;
  const allErrors = [];
  
  try {
    console.log(chalk.blue('🔍 Starting console error check...\n'));
    
    // Start Vite dev server
    console.log('⚡ Starting Vite server...');
    server = await createServer({
      server: { port: 3002, host: 'localhost' },
      logLevel: 'error' // Minimize Vite logs
    });
    await server.listen();
    console.log('✅ Server started on http://localhost:3002\n');
    
    // Launch browser
    browser = await puppeteer.launch({ 
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    const page = await browser.newPage();
    
    // Set up error capturing
    const pageErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        pageErrors.push({
          type: 'console.error',
          message: msg.text(),
          location: msg.location()
        });
      }
    });
    
    page.on('pageerror', (error) => {
      pageErrors.push({
        type: 'page.error',
        message: error.message,
        stack: error.stack
      });
    });
    
    page.on('response', (response) => {
      if (response.status() >= 400) {
        pageErrors.push({
          type: 'network.error',
          message: `${response.status()} ${response.statusText()} - ${response.url()}`
        });
      }
    });
    
    // Test each page
    for (const route of PAGES_TO_TEST) {
      console.log(`📄 Testing ${route}...`);
      pageErrors.length = 0; // Clear previous errors
      
      try {
        const url = `http://localhost:3002${route}`;
        await page.goto(url, { 
          waitUntil: 'domcontentloaded', 
          timeout: 15000 
        });
        
        // Wait for React to render and any async operations
        await page.waitForTimeout(3000);
        
        // Wait for any lazy-loaded components
        await page.evaluate(() => {
          return new Promise((resolve) => {
            if (window.requestIdleCallback) {
              window.requestIdleCallback(resolve, { timeout: 2000 });
            } else {
              setTimeout(resolve, 2000);
            }
          });
        });
        
        if (pageErrors.length > 0) {
          console.log(chalk.red(`  ❌ Found ${pageErrors.length} errors`));
          allErrors.push({
            page: route,
            errors: [...pageErrors]
          });
        } else {
          console.log(chalk.green(`  ✅ No errors`));
        }
        
      } catch (error) {
        console.log(chalk.red(`  ❌ Navigation failed: ${error.message}`));
        allErrors.push({
          page: route,
          errors: [{ type: 'navigation.error', message: error.message }]
        });
      }
    }
    
  } catch (error) {
    console.error(chalk.red(`Failed to run console check: ${error.message}`));
    process.exit(1);
  } finally {
    if (browser) await browser.close();
    if (server) await server.close();
  }
  
  // Report results
  console.log(chalk.blue('\n📊 Console Error Check Results\n'));
  
  if (allErrors.length === 0) {
    console.log(chalk.green.bold('✅ NO CONSOLE ERRORS FOUND! 🎉\n'));
    console.log('Your app is clean and ready to push.\n');
    return true;
  }
  
  console.log(chalk.red.bold(`❌ FOUND ERRORS ON ${allErrors.length} PAGES:\n`));
  
  let criticalFound = false;
  
  allErrors.forEach(({ page, errors }) => {
    console.log(chalk.yellow.bold(`📄 ${page}:`));
    
    errors.forEach((error, index) => {
      const isCritical = CRITICAL_ERRORS.some(pattern => 
        error.message.includes(pattern)
      );
      
      if (isCritical) {
        criticalFound = true;
        console.log(chalk.red(`  🚨 [CRITICAL] ${error.message}`));
      } else {
        console.log(chalk.orange(`  ⚠️  [${error.type}] ${error.message}`));
      }
      
      if (error.location) {
        console.log(chalk.gray(`      at ${error.location}`));
      }
    });
    console.log();
  });
  
  if (criticalFound) {
    console.log(chalk.red.bold('🚨 CRITICAL ERRORS FOUND - DO NOT PUSH!'));
    console.log(chalk.yellow('These errors will break the app in production.\n'));
    return false;
  } else {
    console.log(chalk.yellow.bold('⚠️  Minor errors found - review before pushing'));
    console.log(chalk.gray('These might be acceptable depending on context.\n'));
    return true;
  }
}

// Run the check
checkConsoleErrors().then(success => {
  process.exit(success ? 0 : 1);
}).catch(error => {
  console.error(chalk.red('Script failed:'), error);
  process.exit(1);
});