#!/usr/bin/env node

import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

console.log('🔍 API CONFIGURATION CHECK\n');
console.log('=' .repeat(80) + '\n');

try {
  await page.goto('http://localhost:5173/app/markets', { waitUntil: 'networkidle' });

  const config = await page.evaluate(() => {
    return {
      configObj: window.__CONFIG__,
      location: window.location.href,
      hostname: window.location.hostname,
      protocol: window.location.protocol,
      importMetaEnv: {
        DEV: import.meta.env.DEV,
        VITE_API_URL: import.meta.env.VITE_API_URL,
      },
    };
  });

  console.log('Window configuration:');
  console.log(JSON.stringify(config, null, 2));

  // Try to make a request using the configured URL
  const testResult = await page.evaluate(async () => {
    const config = window.__CONFIG__ || {};
    const apiUrl = config.API_URL || 'NOT SET';

    console.log(`[Config] API_URL from window.__CONFIG__: ${apiUrl}`);

    if (apiUrl && apiUrl !== 'NOT SET') {
      try {
        const url = `${apiUrl}/api/health`;
        console.log(`[Test] Fetching: ${url}`);
        const response = await fetch(url);
        return { configuredUrl: apiUrl, testStatus: response.status, testOk: response.ok };
      } catch (err) {
        return { configuredUrl: apiUrl, testError: err.message };
      }
    }

    return { error: 'No API_URL configured' };
  });

  console.log('\nTest result:');
  console.log(JSON.stringify(testResult, null, 2));

} catch (err) {
  console.error('Error:', err.message);
}

console.log('\n' + '=' .repeat(80) + '\n');

await browser.close();
