const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Capture all console messages
  const consoleLogs = [];
  const consoleErrors = [];
  const consoleWarnings = [];

  page.on('console', msg => {
    const logEntry = {
      type: msg.type(),
      text: msg.text(),
      location: msg.location(),
      args: msg.args()
    };

    if (msg.type() === 'error') {
      consoleErrors.push(logEntry);
    } else if (msg.type() === 'warning') {
      consoleWarnings.push(logEntry);
    }
    consoleLogs.push(logEntry);
  });

  // Capture page errors
  page.on('pageerror', error => {
    consoleErrors.push({
      type: 'pageerror',
      message: error.message,
      stack: error.stack
    });
  });

  try {
    console.log('Opening app at http://localhost:5173...');
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 30000 });

    // Wait a bit for any async errors to appear
    await page.waitForTimeout(3000);

    // Get page title to confirm load
    const title = await page.title();
    console.log(`\n✓ Page loaded: "${title}"`);

    // Screenshot the page
    await page.screenshot({ path: 'screenshot-devtools-check.png' });
    console.log('✓ Screenshot saved to screenshot-devtools-check.png');

    // Print console logs summary
    console.log('\n========== F12 DEVTOOLS CONSOLE LOG SUMMARY ==========');
    console.log(`Total messages: ${consoleLogs.length}`);
    console.log(`Errors: ${consoleErrors.length}`);
    console.log(`Warnings: ${consoleWarnings.length}`);

    if (consoleErrors.length > 0) {
      console.log('\n❌ ERRORS FOUND:');
      consoleErrors.forEach((err, idx) => {
        console.log(`\n[${idx + 1}] ${err.type}`);
        if (err.location) console.log(`    Location: ${err.location.url}:${err.location.lineNumber}:${err.location.columnNumber}`);
        console.log(`    Message: ${err.text || err.message}`);
        if (err.stack) console.log(`    Stack: ${err.stack.substring(0, 200)}...`);
      });
    }

    if (consoleWarnings.length > 0) {
      console.log('\n⚠️  WARNINGS FOUND:');
      consoleWarnings.slice(0, 10).forEach((warn, idx) => {
        console.log(`\n[${idx + 1}] Warning`);
        if (warn.location) console.log(`    Location: ${warn.location.url}:${warn.location.lineNumber}`);
        console.log(`    Message: ${warn.text}`);
      });
    }

    console.log('\n✓ Browser is still open - inspect F12 DevTools manually');
    console.log('Press Ctrl+C to close when done checking...');

    // Keep the browser open for manual inspection
    await new Promise(resolve => setTimeout(resolve, 300000)); // 5 minutes

  } catch (error) {
    console.error('Error:', error);
  } finally {
    await browser.close();
  }
})();
