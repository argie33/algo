#!/usr/bin/env node
import { chromium } from 'playwright';

const PORT = 5173;
const BASE_URL = `http://localhost:${PORT}`;

async function analyzeTiming() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const events = [];
  const navigationStart = Date.now();

  page.on('console', msg => {
    events.push({
      time: Date.now() - navigationStart,
      type: 'console',
      level: msg.type(),
      text: msg.text().slice(0, 100),
    });
  });

  page.on('response', response => {
    if (response.status() >= 400) {
      events.push({
        time: Date.now() - navigationStart,
        type: 'response',
        status: response.status(),
        url: response.url().split('?')[0].split('/').slice(-2).join('/'),
      });
    }
  });

  try {
    console.log(`\n🧪 Testing /app/sectors with timeline...\n`);

    const navStart = Date.now();
    await page.goto(`${BASE_URL}/app/sectors`, { waitUntil: 'load', timeout: 15000 });
    const navEnd = Date.now();

    console.log(`📊 Navigation completed in ${navEnd - navStart}ms\n`);

    // Wait for any delayed requests
    await page.waitForTimeout(2000);

    // Group events by type
    const consoleErrors = events.filter(e => e.type === 'console' && e.level === 'error');
    const responses = events.filter(e => e.type === 'response');

    console.log(`📈 EVENT TIMELINE (${events.length} total events):\n`);

    events.forEach((e, i) => {
      if (e.type === 'console') {
        const icon = e.level === 'error' ? '❌' : e.level === 'warning' ? '⚠️' : 'ℹ️';
        console.log(`  ${e.time.toString().padStart(5)}ms ${icon} ${e.level}: ${e.text}`);
      } else if (e.type === 'response') {
        const icon = e.status >= 400 ? '⚠️' : '✅';
        console.log(`  ${e.time.toString().padStart(5)}ms ${icon} API ${e.status}: ${e.url}`);
      }
    });

    console.log(`\n📊 SUMMARY:`);
    console.log(`  Total events: ${events.length}`);
    console.log(`  Console errors: ${consoleErrors.length}`);
    console.log(`  Network errors (4xx/5xx): ${responses.length}`);

    if (consoleErrors.length > 0) {
      const firstError = consoleErrors[0];
      const lastError = consoleErrors[consoleErrors.length - 1];
      console.log(`  Error period: ${firstError.time}ms - ${lastError.time}ms`);
    }

  } catch (error) {
    console.error('\n❌ Test failed:', error.message);
  } finally {
    await context.close();
    await browser.close();
  }
}

analyzeTiming();
