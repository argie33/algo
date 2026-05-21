import { chromium } from 'playwright';

async function testAllPages() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║   FULL-SITE AUDIT (SINGLE PAGE - SESSION PERSISTS)        ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  const pages = [
    { url: 'http://localhost:5174', name: 'Landing' },
    { url: 'http://localhost:5174/dashboard', name: 'Dashboard' },
    { url: 'http://localhost:5174/backtest', name: 'Backtest' },
    { url: 'http://localhost:5174/portfolio', name: 'Portfolio' },
    { url: 'http://localhost:5174/signals', name: 'Signals' },
    { url: 'http://localhost:5174/trades', name: 'Trades' },
    { url: 'http://localhost:5174/settings', name: 'Settings' },
    { url: 'http://localhost:5174/admin', name: 'Admin' },
  ];

  const globalLogs = { errors: [] };
  const results = [];

  page.on('console', msg => {
    if (msg.type() === 'error') {
      globalLogs.errors.push(msg.text());
    }
  });

  // First, inject devAuth session
  console.log('🔐 Injecting devAuth session...');
  await page.goto('http://localhost:5174', { waitUntil: 'domcontentloaded' });
  
  await page.evaluate(() => {
    sessionStorage.setItem('devAuth_session', JSON.stringify({
      username: 'dev-admin',
      email: 'admin@dev.local',
      firstName: 'Dev',
      lastName: 'Admin'
    }));
  });

  await page.reload({ waitUntil: 'networkidle' });
  console.log('✅ Session injected and page reloaded\n');
  
  await page.waitForTimeout(2000);

  // Now navigate to each page and collect errors
  for (const testPage of pages) {
    const pageErrors = [];
    
    // Temporarily override console.error for this page
    page.removeAllListeners('console');
    page.on('console', msg => {
      if (msg.type() === 'error') {
        pageErrors.push(msg.text());
      }
    });

    try {
      await page.goto(testPage.url, { waitUntil: 'networkidle', timeout: 15000 });
      await page.waitForTimeout(1500);

      const status = pageErrors.length === 0 ? '✅' : '❌';
      console.log(`${status} ${testPage.name.padEnd(15)} → Errors: ${pageErrors.length}`);

      if (pageErrors.length > 0) {
        pageErrors.slice(0, 2).forEach(e => {
          console.log(`     ERROR: ${e.substring(0, 85)}`);
        });
      }

      results.push({ page: testPage.name, errors: pageErrors.length });
    } catch (e) {
      console.log(`❌ ${testPage.name.padEnd(15)} → FAILED: ${e.message}`);
      results.push({ page: testPage.name, errors: -1, failed: true });
    }
  }

  const totalErrors = results.reduce((sum, r) => sum + (r.errors > 0 ? r.errors : 0), 0);
  const allPassed = results.every(r => r.errors === 0);

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  if (allPassed) {
    console.log('║          ✅ GOAL ACHIEVED - ALL PAGES CLEAN                ║');
  } else {
    console.log(`║  TOTAL ERRORS: ${totalErrors}                                     ║`);
  }
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  await context.close();
  await browser.close();
  process.exit(allPassed ? 0 : 1);
}

testAllPages();
