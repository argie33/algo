import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const consoleLogs = [];
  const consoleErrors = [];
  const consoleWarnings = [];
  const networkErrors = [];
  const networkSuccess = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      // Ignore non-critical errors like missing favicons
      if (!msg.text().includes('favicon') && !msg.text().includes('.woff')) {
        consoleErrors.push(msg.text());
        console.error(`[ERROR] ${msg.text()}`);
      }
    } else if (msg.type() === 'warning') {
      consoleWarnings.push(msg.text());
      console.warn(`[WARN] ${msg.text()}`);
    }
  });

  page.on('response', (response) => {
    const url = response.url();
    if (response.status() >= 400) {
      if (!url.includes('favicon') && !url.includes('.woff')) {
        networkErrors.push({ url, status: response.status() });
      }
    } else if (url.includes('/api/')) {
      networkSuccess.push({ url, status: response.status() });
    }
  });

  page.on('pageerror', (err) => {
    if (!err.message.includes('favicon')) {
      consoleErrors.push(`PageError: ${err.message}`);
      console.error(`[PAGE ERROR] ${err.message}`);
    }
  });

  try {
    console.log('=== FRONTEND QUALITY AUDIT ===\n');
    console.log('1. Loading application...');
    const response = await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 30000 });
    console.log(`   Status: ${response.status()}\n`);

    console.log('2. Waiting for page to fully render...');
    await page.waitForTimeout(3000);

    console.log('3. Navigating to Trading Signals page...');
    await page.goto('http://localhost:5173/app/signals', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    // Get actual API calls made
    console.log(`\n4. API Call Summary:\n   Successful API calls: ${networkSuccess.length}`);
    networkSuccess.slice(0, 5).forEach(s => {
      console.log(`   ✓ ${s.url.substring(s.url.indexOf('/api'))}`);
    });

    if (networkErrors.length > 0) {
      console.log(`\n   Failed API calls: ${networkErrors.length}`);
      networkErrors.slice(0, 3).forEach(e => {
        console.log(`   ✗ [${e.status}] ${e.url.substring(e.url.indexOf('/api'))}`);
      });
    }

    // Check page content
    const pageTitle = await page.title();
    const hasContent = await page.evaluate(() => document.body.innerText.length > 500);

    console.log(`\n5. Page Content:\n   Title: ${pageTitle}\n   Has content: ${hasContent}`);

    // Check for table/data display
    const dataElements = await page.evaluate(() => {
      const tables = document.querySelectorAll('table');
      const dataRows = document.querySelectorAll('[role="row"]');
      return {
        tables: tables.length,
        rows: dataRows.length,
        text: document.body.innerText.substring(0, 500),
      };
    });

    console.log(`   Tables found: ${dataElements.tables}`);
    console.log(`   Data rows found: ${dataElements.rows}`);

    // Final audit
    console.log(`\n=== F12 CONSOLE AUDIT ===`);
    console.log(`Console Errors: ${consoleErrors.length}`);
    console.log(`Console Warnings: ${consoleWarnings.length}`);

    if (consoleErrors.length === 0 && networkErrors.length === 0) {
      console.log(`\n✅ VERDICT: F12 CONSOLE CLEAN - All systems operational`);
    } else {
      console.log(`\n⚠️  Issues found:`);
      if (consoleErrors.length > 0) {
        console.log(`   - ${consoleErrors.length} console errors`);
      }
      if (networkErrors.length > 0) {
        console.log(`   - ${networkErrors.length} API failures`);
      }
    }

  } catch (error) {
    console.error(`Error: ${error.message}`);
  } finally {
    await browser.close();
  }
})();
