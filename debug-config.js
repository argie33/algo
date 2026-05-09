#!/usr/bin/env node

const { chromium } = require('playwright');

async function debugConfig() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const debugLogs = [];

  page.on('console', msg => {
    if (msg.text().includes('[API Config Debug]')) {
      debugLogs.push(msg.text());
      console.log('📋 DEBUG OUTPUT:', msg.text());
    }
  });

  try {
    console.log('🔍 Loading app and checking API config...\n');
    await page.goto('http://localhost:5176/app/market', { waitUntil: 'domcontentloaded', timeout: 10000 });
    await page.waitForTimeout(2000);

    if (debugLogs.length === 0) {
      console.log('⚠️  No debug logs captured. Checking console manually...\n');

      // Try to evaluate the config directly
      const config = await page.evaluate(() => {
        try {
          // Get whatever axios instance is created
          return {
            windowConfig: window.__CONFIG__?.API_URL,
            location: window.location.href
          };
        } catch (e) {
          return { error: e.message };
        }
      });

      console.log('Page Context:', config);
    }
  } catch (err) {
    console.error('Error:', err.message);
  }

  await browser.close();
}

debugConfig();
