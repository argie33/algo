const { chromium } = require('playwright');

const PAGES = [
  '/app/market',
  '/app/sectors',
  '/app/economic',
  '/app/sentiment',
  '/app/trading-signals',
  '/app/portfolio',
  '/app/trades',
  '/app/performance',
  '/app/backtests',
  '/app/scores',
  '/app/service-health',
  '/app/audit-viewer',
];

async function testPages() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.createContext();

  let totalPages = 0;
  let pagesClean = 0;
  let pagesWithErrors = 0;
  let totalErrors = 0;

  console.log('================================================================================');
  console.log('F12 CONSOLE ERROR TEST - All 12 Pages');
  console.log('================================================================================\n');

  for (const page of PAGES) {
    const consoleErrors = [];
    const pageObj = await context.newPage();

    // Capture console messages
    pageObj.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    // Capture page errors
    pageObj.on('pageerror', (err) => {
      consoleErrors.push(`${err.name}: ${err.message}`);
    });

    try {
      await pageObj.goto(`http://localhost:5173${page}`, { waitUntil: 'networkidle', timeout: 30000 });
      await pageObj.waitForTimeout(2000); // Wait for API calls to complete

      totalPages++;
      if (consoleErrors.length === 0) {
        console.log(`[OK]   ${page.padEnd(35)} No console errors`);
        pagesClean++;
      } else {
        console.log(`[FAIL] ${page.padEnd(35)} ${consoleErrors.length} console error(s)`);
        pagesWithErrors++;
        totalErrors += consoleErrors.length;
        consoleErrors.forEach((err, i) => {
          console.log(`       ${i + 1}. ${err.substring(0, 70)}`);
        });
      }
    } catch (err) {
      totalPages++;
      console.log(`[ERROR] ${page.padEnd(35)} ${err.message.substring(0, 50)}`);
      pagesWithErrors++;
    }

    await pageObj.close();
  }

  console.log('\n================================================================================');
  console.log(`RESULTS: ${pagesClean}/${totalPages} pages have clean F12 logs`);
  console.log(`Pages with errors: ${pagesWithErrors}`);
  console.log(`Total errors: ${totalErrors}`);
  console.log('================================================================================\n');

  await context.close();
  await browser.close();

  process.exit(pagesClean === totalPages ? 0 : 1);
}

testPages().catch(err => {
  console.error('Test error:', err);
  process.exit(1);
});
