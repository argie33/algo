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

  const testPages = [
    '/',
    '/portfolio',
    '/trading-signals',
    '/market',
    '/sectors',
    '/industries',
    '/optimization',
    '/strategies',
  ];

  console.log('🧪 COMPREHENSIVE APP TEST\n');

  let totalErrors = 0;
  let totalWarnings = 0;

  for (const page_path of testPages) {
    consoleErrors.length = 0;
    consoleWarnings.length = 0;
    pageErrors.length = 0;
    failedRequests.length = 0;

    try {
      console.log(`Testing ${page_path || '(home)'}`);
      const response = await page.goto(`http://localhost:5176${page_path}`, { 
        waitUntil: 'networkidle', 
        timeout: 30000 
      });
      
      console.log(`  Status: ${response.status()}`);
      await page.waitForTimeout(1000);

      if (consoleErrors.length > 0) {
        console.log(`  ❌ Errors: ${consoleErrors.length}`);
        consoleErrors.forEach((err, i) => {
          console.log(`     ${i + 1}. ${err.substring(0, 60)}...`);
        });
        totalErrors += consoleErrors.length;
      } else {
        console.log(`  ✅ No errors`);
      }

      if (consoleWarnings.length > 0) {
        console.log(`  ⚠️  Warnings: ${consoleWarnings.length}`);
        totalWarnings += consoleWarnings.length;
      }

      if (pageErrors.length > 0) {
        console.log(`  🔴 Page Errors: ${pageErrors.length}`);
      }

      if (failedRequests.length > 0) {
        console.log(`  📡 Failed Requests: ${failedRequests.length}`);
        failedRequests.slice(0, 3).forEach(req => {
          console.log(`     [${req.status}] ${req.url.substring(0, 60)}`);
        });
      }
    } catch (error) {
      console.log(`  ❌ Navigation Error: ${error.message}`);
    }
    console.log('');
  }

  console.log('=== SUMMARY ===');
  console.log(`Total Console Errors: ${totalErrors}`);
  console.log(`Total Console Warnings: ${totalWarnings}`);
  
  if (totalErrors === 0) {
    console.log('\n✅ ALL PAGES LOADED CLEAN - NO CONSOLE ERRORS');
  } else {
    console.log('\n⚠️  SOME PAGES HAD ERRORS - SEE ABOVE');
  }

  await browser.close();
})();
