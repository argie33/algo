import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });

  // Log console messages
  const consoleLogs = [];
  const consoleErrors = [];
  const consoleWarnings = [];

  const page = await browser.newPage();

  page.on('console', (msg) => {
    const logEntry = {
      type: msg.type(),
      text: msg.text(),
    };

    if (msg.type() === 'error') {
      consoleErrors.push(logEntry);
      console.error(`[CONSOLE ERROR] ${msg.text()}`);
    } else if (msg.type() === 'warning') {
      consoleWarnings.push(logEntry);
      console.warn(`[CONSOLE WARNING] ${msg.text()}`);
    }
  });

  // Catch all page errors
  page.on('pageerror', (err) => {
    consoleErrors.push({
      type: 'pageerror',
      text: err.message,
    });
    console.error(`[PAGE ERROR] ${err.message}`);
  });

  try {
    console.log('Opening http://localhost:5176...');
    const response = await page.goto('http://localhost:5176', { waitUntil: 'networkidle', timeout: 30000 });

    console.log(`\nPage loaded with status: ${response.status()}`);

    // Wait for page to fully render
    await page.waitForTimeout(3000);

    // Get page title
    const title = await page.title();
    console.log(`Page title: ${title}`);

    // Check page content
    const bodyText = await page.textContent('body');
    const hasContent = bodyText && bodyText.trim().length > 0;
    console.log(`Page has rendered content: ${hasContent}`);

    console.log(`\n===== F12 CONSOLE VERIFICATION =====`);
    console.log(`Console Errors: ${consoleErrors.length}`);
    console.log(`Console Warnings: ${consoleWarnings.length}`);
    console.log(`Console Logs: ${consoleLogs.length}`);

    if (consoleErrors.length > 0) {
      console.log(`\nDetailed Errors:`);
      consoleErrors.forEach((err, i) => {
        console.log(`  ${i + 1}. ${err.text}`);
      });
    }

    if (consoleWarnings.length > 0) {
      console.log(`\nWarnings (first 5):`);
      consoleWarnings.slice(0, 5).forEach((warn, i) => {
        console.log(`  ${i + 1}. ${warn.text}`);
      });
      if (consoleWarnings.length > 5) {
        console.log(`  ... and ${consoleWarnings.length - 5} more warnings`);
      }
    }

    // Print final verdict
    console.log(`\n===== VERDICT =====`);
    if (consoleErrors.length === 0) {
      console.log('✅ F12 CONSOLE IS CLEAN - No critical errors detected');
    } else {
      console.log('❌ F12 CONSOLE HAS ISSUES - See errors above');
    }

  } catch (error) {
    console.error(`Error during test: ${error.message}`);
  } finally {
    await browser.close();
  }
})();
