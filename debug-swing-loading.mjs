#!/usr/bin/env node

import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

// Intercept API calls
page.on('response', async (res) => {
  if (res.url().includes('/api')) {
    const status = res.status();
    const statusIcon = status >= 400 ? '❌' : '✅';
    console.log(`${statusIcon} [${status}] ${res.url().replace(/^.*\/api/, '/api')}`);

    if (status >= 400) {
      try {
        const body = await res.text();
        console.log(`   Error: ${body.substring(0, 100)}`);
      } catch (e) {}
    }
  }
});

// Monitor console
page.on('console', (msg) => {
  if (msg.type() === 'error') {
    console.log(`🔴 CONSOLE ERROR: ${msg.text()}`);
  } else if (msg.type() === 'warning') {
    const text = msg.text();
    if (!text.includes('chart')) {
      console.log(`🟡 WARNING: ${text.substring(0, 100)}`);
    }
  }
});

console.log('🔍 SWING CANDIDATES LOADING ANALYSIS\n');
console.log('=' .repeat(80) + '\n');

try {
  console.log('Opening page...');
  await page.goto('http://localhost:5173/app/swing', { waitUntil: 'networkidle', timeout: 30000 });

  console.log('\n✓ Page navigated\n');
  console.log('Checking rendering...\n');

  const state = await page.evaluate(() => {
    const main = document.querySelector('main');
    const text = main?.innerText || '';
    return {
      textLength: text.length,
      text: text.substring(0, 150),
      loading: text.includes('Loading'),
      error: text.includes('Error'),
    };
  });

  console.log(`Final state after networkidle:`);
  console.log(`  Text length: ${state.textLength} chars`);
  console.log(`  Is loading: ${state.loading}`);
  console.log(`  Has error: ${state.error}`);
  console.log(`  Content: "${state.text}..."`);

  // If still loading, wait a bit more
  if (state.loading) {
    console.log('\nPage still shows loading. Waiting 3 seconds...');
    await page.waitForTimeout(3000);

    const state2 = await page.evaluate(() => {
      const main = document.querySelector('main');
      const text = main?.innerText || '';
      return {
        textLength: text.length,
        text: text.substring(0, 150),
        loading: text.includes('Loading'),
      };
    });

    console.log(`After 3 second wait:`);
    console.log(`  Text length: ${state2.textLength} chars`);
    console.log(`  Is loading: ${state2.loading}`);
    console.log(`  Content: "${state2.text}..."`);
  }

} catch (err) {
  console.error(`❌ Error: ${err.message}`);
}

console.log('\n' + '=' .repeat(80) + '\n');

await browser.close();
