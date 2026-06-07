const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const consoleLogs = [];
  const networkErrors = [];

  page.on('console', msg => {
    const type = msg.type();
    const text = msg.text();
    if (type === 'error' || type === 'warn' || type.includes('API') || text.includes('error') || text.includes('failed')) {
      consoleLogs.push({ type, text });
    }
  });

  page.on('response', response => {
    if (response.status() >= 400) {
      networkErrors.push({
        url: response.url(),
        status: response.status()
      });
    }
  });

  try {
    console.log('Loading app from http://localhost:5173...');
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 15000 });
    console.log('✓ Page loaded successfully');

    // Wait for app to stabilize
    await page.waitForTimeout(3000);

    // Get page title and content
    const title = await page.title();
    const url = page.url();
    const pageText = await page.evaluate(() => document.body.innerText);

    // Take screenshot
    await page.screenshot({ path: 'app-fixed-screenshot.png', fullPage: true });

    console.log('\n' + '='.repeat(60));
    console.log('APP STATUS REPORT');
    console.log('='.repeat(60));
    console.log(`\n✓ Page Title: ${title}`);
    console.log(`✓ Current URL: ${url}`);
    console.log(`\n✓ Console Errors/Warnings: ${consoleLogs.length > 0 ? consoleLogs.length : 'None'}`);
    if (consoleLogs.length > 0) {
      consoleLogs.forEach(log => console.log(`  [${log.type}] ${log.text.substring(0, 100)}`));
    }

    console.log(`\n✓ Network Errors: ${networkErrors.length > 0 ? networkErrors.length : 'None'}`);
    if (networkErrors.length > 0) {
      networkErrors.slice(0, 5).forEach(err => console.log(`  ${err.status} - ${err.url.substring(0, 80)}`));
    }

    // Check if data loaded
    const hasErrorMessage = pageText.includes('API Connection Issue');
    const hasMarketData = pageText.includes('MARKET EXPOSURE') || pageText.includes('57.3%') || pageText.includes('Market Health');

    console.log(`\n✓ Data Status:`);
    console.log(`  - Error Message Visible: ${hasErrorMessage ? 'YES (Still showing error)' : 'NO (Good!)'}`);
    console.log(`  - Market Data Visible: ${hasMarketData ? 'YES (Data loaded!)' : 'NO'}`);

    console.log(`\n✓ Page Preview (first 300 chars of visible text):`);
    console.log('  ' + pageText.substring(0, 300).replace(/\n/g, '\n  '));

    console.log('\n✓ Screenshot saved: app-fixed-screenshot.png');
    console.log('\n' + '='.repeat(60));

  } catch (err) {
    console.error('ERROR:', err.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
