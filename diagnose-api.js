#!/usr/bin/env node

const http = require('http');
const { chromium } = require('playwright');

const colors = {
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  reset: '\x1b[0m'
};

console.log(`${colors.blue}🔍 API Diagnostic Report${colors.reset}\n`);

// 1. Test direct HTTP connection to API
console.log(`${colors.blue}1. Testing direct HTTP connection to localhost:3001...${colors.reset}`);
const options = {
  hostname: 'localhost',
  port: 3001,
  path: '/api/health',
  method: 'GET',
  timeout: 5000
};

const req = http.request(options, (res) => {
  let data = '';
  res.on('data', (chunk) => { data += chunk; });
  res.on('end', () => {
    console.log(`✅ API responded with status ${res.statusCode}`);
    console.log(`   Response: ${data.substring(0, 200)}`);

    // 2. Now test from browser
    testFromBrowser();
  });
});

req.on('error', (error) => {
  console.log(`❌ API connection failed: ${error.message}`);
  process.exit(1);
});

req.setTimeout(5000, () => {
  console.log(`❌ API request timed out`);
  req.destroy();
  process.exit(1);
});

req.end();

async function testFromBrowser() {
  console.log(`\n${colors.blue}2. Testing API call from browser context...${colors.reset}`);

  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Capture all network activity
  const apiCalls = [];
  page.on('response', response => {
    if (response.url().includes('api')) {
      apiCalls.push({
        url: response.url(),
        status: response.status(),
        method: response.request().method()
      });
    }
  });

  // Also capture request failures
  page.on('requestfailed', request => {
    console.log(`❌ Request failed: ${request.method()} ${request.url()}`);
    console.log(`   Error: ${request.failure()?.errorText}`);
  });

  try {
    await page.goto('http://localhost:5176/app/market', {
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });

    await page.waitForTimeout(3000); // Wait for API calls to complete

    if (apiCalls.length > 0) {
      console.log(`✅ Browser made ${apiCalls.length} API calls:`);
      apiCalls.slice(0, 5).forEach(call => {
        console.log(`   [${call.status}] ${call.method} ${call.url.substring(0, 80)}`);
      });
    } else {
      console.log(`⚠️  No API calls detected from browser`);
    }

    // Check console errors
    const consoleMessages = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleMessages.push(msg.text());
      }
    });

    // Check page content
    const errorElements = await page.locator('[class*="error"]').count();
    const emptyElements = await page.locator('[class*="empty"], [class*="no-data"]').count();

    console.log(`\n${colors.blue}3. Page Analysis:${colors.reset}`);
    console.log(`   Error elements: ${errorElements}`);
    console.log(`   Empty state elements: ${emptyElements}`);
    console.log(`   Console errors: ${consoleMessages.length}`);

    if (consoleMessages.length > 0) {
      console.log(`   Error messages:`);
      consoleMessages.slice(0, 3).forEach(msg => {
        console.log(`     - ${msg.substring(0, 100)}`);
      });
    }

  } catch (error) {
    console.log(`❌ Browser test failed: ${error.message}`);
  }

  await browser.close();
}
