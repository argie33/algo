import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const consoleLogs = [];
  const errors = [];

  page.on('console', async (msg) => {
    const args = [];
    for (const arg of msg.args()) {
      try {
        args.push(await arg.jsonValue());
      } catch {
        args.push(`[${msg.type()}] <unserializable>`);
      }
    }

    const logEntry = {
      type: msg.type(),
      text: msg.text(),
      args: args
    };

    consoleLogs.push(logEntry);

    if (msg.type() === 'error' || msg.type() === 'warning') {
      console.log(`[${msg.type().toUpperCase()}] ${msg.text()}`);
    }
  });

  page.on('pageerror', (error) => {
    errors.push({
      message: error.message,
      stack: error.stack
    });
    console.log('[PAGE ERROR]', error.message);
  });

  console.log('Opening http://localhost:5178...\n');
  await page.goto('http://localhost:5178', { waitUntil: 'load', timeout: 15000 }).catch(e => {
    console.log('Navigation timeout (this is OK if page partially loaded):', e.message);
  });

  console.log('\n✓ Page loaded\n');

  // Wait for any async operations
  await page.waitForTimeout(3000);

  // Get page title
  const title = await page.title();
  console.log(`Page title: ${title}`);

  console.log('\n=== ERROR & WARNING SUMMARY ===');
  const errorLogs = consoleLogs.filter(l => l.type === 'error');
  const warnLogs = consoleLogs.filter(l => l.type === 'warn');
  
  if (errorLogs.length > 0) {
    console.log(`\nErrors found: ${errorLogs.length}`);
    errorLogs.forEach((log, i) => {
      console.log(`  ${i + 1}. ${log.text}`);
      if (log.args && log.args.length > 0) {
        console.log(`     ${JSON.stringify(log.args).substring(0, 150)}`);
      }
    });
  }
  
  if (warnLogs.length > 0) {
    console.log(`\nWarnings found: ${warnLogs.length}`);
    warnLogs.slice(0, 5).forEach((log, i) => {
      console.log(`  ${i + 1}. ${log.text}`);
    });
    if (warnLogs.length > 5) {
      console.log(`  ... and ${warnLogs.length - 5} more`);
    }
  }

  if (errors.length > 0) {
    console.log(`\nUncaught errors: ${errors.length}`);
    errors.slice(0, 3).forEach((err, i) => {
      console.log(`  ${i + 1}. ${err.message}`);
    });
  }

  console.log('\n=== SUMMARY ===');
  console.log(`Total console messages: ${consoleLogs.length}`);
  console.log(`Total errors: ${consoleLogs.filter(l => l.type === 'error').length}`);
  console.log(`Total warnings: ${consoleLogs.filter(l => l.type === 'warn').length}`);
  console.log(`Page errors: ${errors.length}`);

  await browser.close();
})();
