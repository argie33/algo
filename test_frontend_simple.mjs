#!/usr/bin/env node

import { chromium } from '/home/arger/algo/webapp/frontend/node_modules/playwright/index.mjs';
import fs from 'fs';

async function testFrontend() {
  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║      🔍 FRONTEND ERROR DIAGNOSTIC TEST (Playwright)        ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const allErrors = [];
  const allWarnings = [];
  const networkErrors = [];
  const requests = [];

  // Capture console messages
  page.on('console', msg => {
    console.log(`[${msg.type().toUpperCase()}] ${msg.text().substring(0, 120)}`);

    if (msg.type() === 'error') {
      allErrors.push({
        type: 'CONSOLE',
        message: msg.text(),
        location: msg.location()
      });
    } else if (msg.type() === 'warning') {
      allWarnings.push(msg.text());
    }
  });

  // Capture page errors
  page.on('pageerror', error => {
    console.log(`[PAGE_ERROR] ${error.message}`);
    allErrors.push({
      type: 'PAGE',
      message: error.message
    });
  });

  // Track network activity
  page.on('request', request => {
    requests.push({
      method: request.method(),
      url: request.url(),
      type: request.resourceType()
    });
  });

  page.on('response', response => {
    if (!response.ok() && response.url().includes('api')) {
      console.log(`[API_ERROR] ${response.status()} ${response.url().substring(0, 80)}`);
      networkErrors.push({
        status: response.status(),
        url: response.url()
      });
    }
  });

  try {
    const urlsToTest = [
      'http://localhost:5173',  // Vite dev server
      'http://localhost:3000',  // Alternative
      'http://localhost:5174',  // Another alternative
    ];

    let foundUrl = null;

    for (const url of urlsToTest) {
      try {
        console.log(`\n⏳ Testing ${url}...`);
        const response = await page.goto(url, {
          waitUntil: 'networkidle',
          timeout: 8000
        });

        if (response && response.ok()) {
          console.log(`✅ Frontend running at ${url}\n`);
          foundUrl = url;
          break;
        }
      } catch (e) {
        console.log(`❌ Not available at ${url}`);
      }
    }

    if (!foundUrl) {
      console.log('\n❌ FRONTEND NOT RUNNING\n');
      console.log('To start the frontend:');
      console.log('  cd /home/arger/algo/webapp/frontend');
      console.log('  npm run dev\n');
      await browser.close();
      return;
    }

    // Wait for full load
    console.log('⏳ Waiting for page load...');
    await page.waitForLoadState('networkidle').catch(() => {
      console.log('⚠️  Network stabilization timeout (continuing anyway)');
    });
    await page.waitForTimeout(1500);

    // Check page content
    console.log('\n📋 Page Analysis:');
    const title = await page.title();
    const url = page.url();
    console.log(`  Title: ${title}`);
    console.log(`  URL: ${url}`);

    // Check for main content
    const hasContent = await page.locator('body').count() > 0;
    const hasApp = await page.locator('#app, [role="main"], main').count() > 0;
    console.log(`  Has body: ${hasContent ? '✅' : '❌'}`);
    console.log(`  Has app root: ${hasApp ? '✅' : '❌'}`);

    // Analyze requests
    const apiRequests = requests.filter(r =>
      r.url.includes('/api') || r.url.includes('stocks') || r.url.includes('health')
    );

    console.log(`\n📡 Network:
  Total requests: ${requests.length}
  API requests: ${apiRequests.length}
  Network errors: ${networkErrors.length}`);

    if (apiRequests.length > 0) {
      console.log('\n  API Requests:');
      apiRequests.slice(0, 5).forEach((req, i) => {
        console.log(`    ${i + 1}. ${req.method} ${req.url.substring(0, 90)}`);
      });
    }

    // Summary
    console.log(`\n📊 Error Summary:
  Console errors: ${allErrors.length}
  Console warnings: ${allWarnings.length}
  Network errors: ${networkErrors.length}`);

    if (allErrors.length > 0) {
      console.log('\n  Top Errors:');
      allErrors.slice(0, 5).forEach((err, i) => {
        console.log(`    ${i + 1}. [${err.type}] ${err.message.substring(0, 80)}`);
      });
    }

    if (networkErrors.length > 0) {
      console.log('\n  Network Errors:');
      networkErrors.slice(0, 5).forEach((err, i) => {
        console.log(`    ${i + 1}. [${err.status}] ${err.url.substring(0, 80)}`);
      });
    }

    // Take screenshot
    const screenshotPath = '/tmp/frontend-diagnostic.png';
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`\n📸 Screenshot saved: ${screenshotPath}`);

    // Export diagnostics
    const diagnostics = {
      timestamp: new Date().toISOString(),
      url: foundUrl,
      title: title,
      hasContent: hasContent,
      hasApp: hasApp,
      errorCount: allErrors.length,
      warningCount: allWarnings.length,
      networkErrorCount: networkErrors.length,
      apiRequestCount: apiRequests.length,
      totalRequests: requests.length,
      errors: allErrors.slice(0, 10),
      networkErrors: networkErrors.slice(0, 5),
      apiRequests: apiRequests.slice(0, 10)
    };

    fs.writeFileSync('/tmp/frontend-diagnostics.json', JSON.stringify(diagnostics, null, 2));
    console.log('📋 Diagnostics saved: /tmp/frontend-diagnostics.json');

    // Final status
    console.log('\n' + '═'.repeat(62));
    if (allErrors.length === 0 && networkErrors.length === 0) {
      console.log('✅ NO CRITICAL ERRORS - Frontend is working correctly!');
    } else {
      console.log(`⚠️  ISSUES DETECTED - See details above`);
    }
    console.log('═'.repeat(62) + '\n');

  } catch (error) {
    console.error('\n❌ TEST ERROR:', error.message);
  } finally {
    await browser.close();
  }
}

testFrontend().catch(err => {
  console.error('Fatal:', err);
  process.exit(1);
});
