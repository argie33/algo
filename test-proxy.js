#!/usr/bin/env node

const { chromium } = require('playwright');

async function testProxy() {
  console.log('🔍 Testing Vite proxy to backend API...\n');

  const browser = await chromium.launch();
  const page = await browser.newPage();

  const apiResponses = [];
  const apiErrors = [];

  page.on('response', response => {
    if (response.url().includes('/api')) {
      apiResponses.push({
        url: response.url(),
        status: response.status(),
        ok: response.ok()
      });
    }
  });

  page.on('requestfailed', request => {
    if (request.url().includes('/api')) {
      apiErrors.push({
        url: request.url(),
        error: request.failure()?.errorText
      });
    }
  });

  try {
    console.log('Loading Market page...');
    await page.goto('http://localhost:5176/app/market', {
      waitUntil: 'domcontentloaded',
      timeout: 10000
    });

    console.log('Waiting for API calls...');
    await page.waitForTimeout(3000);

    console.log(`\n✅ API Responses: ${apiResponses.length}`);
    apiResponses.forEach(r => {
      console.log(`   [${r.status}] ${r.url.substring(0, 80)}`);
    });

    console.log(`\n❌ API Errors: ${apiErrors.length}`);
    apiErrors.forEach(e => {
      console.log(`   ${e.url.substring(0, 80)}`);
      console.log(`   Error: ${e.error}`);
    });

    if (apiErrors.length === 0 && apiResponses.length > 0) {
      console.log('\n🎉 Proxy is working!');
    } else {
      console.log('\n⚠️  Proxy might not be working properly');
    }

  } catch (error) {
    console.log(`Error: ${error.message}`);
  }

  await browser.close();
}

testProxy();
