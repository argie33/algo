#!/usr/bin/env node
/**
 * End-to-end test for CloudFront frontend
 * Tests: Page loads, no 429 errors, console clean
 */

import { chromium } from 'playwright';

const FRONTEND_URL = 'https://d2u93283nn45h2.cloudfront.net';

async function runTest() {
  const browser = await chromium.launch({ headless: true });

  // Track responses and console
  const http429s = [];
  const consoleErrors = [];
  const consoleWarnings = [];
  const apiCalls = [];

  const page = await browser.newPage();

  // Track network responses
  page.on('response', (response) => {
    const url = response.url();
    const status = response.status();

    if (status === 429) {
      http429s.push({
        method: response.request().method(),
        url: url.split('?')[0],  // Remove query params for cleaner output
        status,
      });
      console.error(`❌ [429 ERROR] ${response.request().method()} ${url}`);
    }

    // Log API calls
    if (url.includes('/api/')) {
      apiCalls.push({
        method: response.request().method(),
        url: url.replace(/.*\/api/, '/api').split('?')[0],
        status,
      });
    }
  });

  // Track console messages
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
      console.error(`❌ [CONSOLE ERROR] ${msg.text()}`);
    } else if (msg.type() === 'warning' && msg.text().includes('429')) {
      consoleWarnings.push(msg.text());
      console.warn(`⚠️  [CONSOLE WARNING] ${msg.text()}`);
    }
  });

  // Catch page errors
  page.on('pageerror', (err) => {
    consoleErrors.push(err.message);
    console.error(`❌ [PAGE ERROR] ${err.message}`);
  });

  try {
    console.log(`\n🚀 Testing ${FRONTEND_URL}...\n`);

    const response = await page.goto(FRONTEND_URL, {
      waitUntil: 'load',
      timeout: 30000
    });

    console.log(`✅ Page loaded with HTTP ${response.status()}`);

    // Wait for page to fully render
    await page.waitForTimeout(3000);

    // Check page has content
    const bodyText = await page.textContent('body');
    const hasContent = bodyText && bodyText.trim().length > 100;
    console.log(`✅ Page rendered: ${hasContent ? 'YES' : 'NO'}`);

    // Get title
    const title = await page.title();
    console.log(`✅ Page title: "${title}"`);

    // Report findings
    console.log(`\n${'='.repeat(55)}`);
    console.log('TEST RESULTS');
    console.log('='.repeat(55));
    console.log(`HTTP 429 Errors Found: ${http429s.length === 0 ? '✅ NONE' : `❌ ${http429s.length}`}`);
    console.log(`Console Errors Found: ${consoleErrors.length === 0 ? '✅ NONE' : `❌ ${consoleErrors.length}`}`);
    console.log(`API Calls Made: ${apiCalls.length}`);

    if (http429s.length > 0) {
      console.log(`\n❌ CRITICAL - HTTP 429 Errors Detected:`);
      http429s.forEach((err) => {
        console.log(`   • ${err.method} ${err.url}`);
      });
    }

    if (consoleErrors.length > 0) {
      console.log(`\n❌ Console Errors Detected:`);
      consoleErrors.slice(0, 5).forEach((err) => {
        console.log(`   • ${err.substring(0, 80)}`);
      });
    }

    // API Summary
    console.log(`\nAPI Calls by Status:`);
    const byStatus = {};
    apiCalls.forEach(call => {
      const key = call.status;
      byStatus[key] = (byStatus[key] || 0) + 1;
    });
    Object.entries(byStatus).sort().forEach(([status, count]) => {
      const icon = status === '200' ? '✅' : status === '404' ? '⚠️ ' : '❌';
      console.log(`   ${icon} ${status}: ${count}`);
    });

    // Final verdict
    console.log(`\n${'='.repeat(55)}`);
    if (http429s.length === 0 && consoleErrors.length === 0 && hasContent) {
      console.log('✅ VERDICT: PASS - Site loads clean, no 429 errors!');
      return 0;
    } else if (http429s.length > 0) {
      console.log('❌ VERDICT: FAIL - HTTP 429 errors detected');
      return 1;
    } else if (consoleErrors.length > 0) {
      console.log('❌ VERDICT: FAIL - Console errors detected');
      return 1;
    } else {
      console.log('⚠️  VERDICT: UNKNOWN - See details above');
      return 2;
    }

  } catch (error) {
    console.error(`\n💥 Test Error: ${error.message}`);
    return 1;
  } finally {
    await browser.close();
  }
}

const exitCode = await runTest();
process.exit(exitCode);
