#!/usr/bin/env node
import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const networkErrors = [];
  const consoleErrors = [];

  // Listen to network responses
  page.on('response', response => {
    if (response.status() >= 400) {
      networkErrors.push({
        url: response.url(),
        status: response.status(),
        statusText: response.statusText()
      });
    }
  });

  // Listen to console messages
  page.on('console', msg => {
    if (msg.type() === 'error' || msg.text().includes('error')) {
      consoleErrors.push(msg.text());
    }
  });

  try {
    console.log('📊 Diagnosing API errors...\n');

    await page.goto('http://localhost:5173/', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);

    console.log('🔴 Network Errors (HTTP 400+):\n');
    if (networkErrors.length === 0) {
      console.log('  ✅ No HTTP errors detected');
    } else {
      networkErrors.forEach((err, i) => {
        console.log(`  ${i+1}. ${err.status} ${err.statusText}`);
        console.log(`     URL: ${err.url}`);
      });
    }

    console.log('\n📝 Console Errors:\n');
    if (consoleErrors.length === 0) {
      console.log('  ✅ No console errors');
    } else {
      consoleErrors.slice(0, 10).forEach((err, i) => {
        console.log(`  ${i+1}. ${err.substring(0, 100)}`);
      });
    }

    console.log(`\n📊 Summary:`);
    console.log(`  Total network errors: ${networkErrors.length}`);
    console.log(`  Total console errors: ${consoleErrors.length}`);

    // Get error messages from the page itself
    const pageErrors = await page.evaluate(() => {
      const errors = [];
      document.querySelectorAll('[class*="error"], [class*="alert"], [role="alert"]').forEach(el => {
        const text = el.textContent?.trim();
        if (text && text.length > 0) {
          errors.push(text.substring(0, 150));
        }
      });
      return errors;
    });

    console.log(`\n⚠️ Error messages on page:\n`);
    if (pageErrors.length === 0) {
      console.log('  ✅ No error elements found');
    } else {
      pageErrors.forEach((err, i) => {
        console.log(`  ${i+1}. ${err}`);
      });
    }

  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    await browser.close();
  }
})();
