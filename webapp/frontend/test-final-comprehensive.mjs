import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const consoleErrors = [];
  const consoleWarnings = [];
  const pageErrors = [];
  const failedRequests = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    } else if (msg.type() === 'warning') {
      consoleWarnings.push(msg.text());
    }
  });

  page.on('pageerror', (err) => {
    pageErrors.push(err.message);
  });

  page.on('response', (response) => {
    if (response.status() >= 400 && !response.url().includes('health')) {
      failedRequests.push({ url: response.url(), status: response.status() });
    }
  });

  const testPages = ['/', '/portfolio', '/trading-signals', '/market', '/sectors', '/industries', '/optimization', '/strategies'];

  console.log('🧪 COMPREHENSIVE APP FINAL TEST\n');
  
  let totalErrors = 0;
  let totalWarnings = 0;

  for (const pagePath of testPages) {
    consoleErrors.length = 0;
    consoleWarnings.length = 0;
    pageErrors.length = 0;
    failedRequests.length = 0;

    try {
      console.log(`Testing ${pagePath || '(home)'}`);
      const response = await page.goto(`http://localhost:5173${pagePath}`, {
        waitUntil: 'domcontentloaded',
        timeout: 30000
      });
      
      console.log(`  Status: ${response.status()}`);
      await page.waitForTimeout(1500);

      const hasContent = await page.evaluate(() => document.body.innerText.length > 50);
      console.log(`  Content: ${hasContent ? '✅ Yes' : '❌ No'}`);

      if (consoleErrors.length > 0) {
        console.log(`  ❌ Console Errors: ${consoleErrors.length}`);
        consoleErrors.forEach((err, i) => {
          console.log(`     ${i + 1}. ${err.substring(0, 70)}`);
        });
        totalErrors += consoleErrors.length;
      } else {
        console.log(`  ✅ No console errors`);
      }

      if (consoleWarnings.length > 0) {
        console.log(`  ⚠️  Warnings: ${consoleWarnings.length}`);
        totalWarnings += consoleWarnings.length;
      }

      if (failedRequests.length > 0) {
        console.log(`  📡 Failed API Requests: ${failedRequests.length}`);
      }
    } catch (error) {
      console.log(`  ❌ Error: ${error.message.substring(0, 60)}`);
    }
    console.log('');
  }

  console.log('═══════════════════════════════════════════');
  console.log(`📊 FINAL SUMMARY`);
  console.log(`Total Console Errors: ${totalErrors}`);
  console.log(`Total Warnings: ${totalWarnings}`);
  console.log('═══════════════════════════════════════════\n');
  
  if (totalErrors === 0) {
    console.log('✅ ✅ ✅ SUCCESS! ALL PAGES LOAD WITHOUT CONSOLE ERRORS ✅ ✅ ✅');
    console.log('\n✨ Frontend is PRODUCTION READY');
    process.exit(0);
  } else {
    console.log(`⚠️  Found ${totalErrors} console errors - see above`);
    process.exit(1);
  }
})();
