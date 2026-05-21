import { chromium } from 'playwright';

async function testAllPages() {
  const browser = await chromium.launch({ headless: true });
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

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║          COMPREHENSIVE FULL-SITE AUDIT                    ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  const results = [];

  for (const page of pages) {
    const context = await browser.newContext();
    const pageObj = await context.newPage();
    const logs = { errors: [], warnings: [], networkErrors: [] };

    pageObj.on('console', msg => {
      const type = msg.type();
      const text = msg.text();
      if (type === 'error') logs.errors.push(text);
      if (type === 'warning') logs.warnings.push(text);
    });

    pageObj.on('pageerror', err => {
      logs.errors.push(`PAGE_ERROR: ${err.message}`);
    });

    pageObj.on('requestfailed', req => {
      logs.networkErrors.push(`${req.method()} ${req.url()}: ${req.failure().errorText}`);
    });

    try {
      await pageObj.goto(page.url, { waitUntil: 'networkidle', timeout: 15000 });
      await pageObj.waitForTimeout(1500);

      const status = logs.errors.length === 0 ? '✅' : '❌';
      console.log(`${status} ${page.name.padEnd(15)} → Errors: ${logs.errors.length}, Warnings: ${logs.warnings.length}, Network: ${logs.networkErrors.length}`);

      if (logs.errors.length > 0) {
        logs.errors.slice(0, 2).forEach(e => console.log(`     ERROR: ${e.substring(0, 80)}`));
      }
      if (logs.networkErrors.length > 0) {
        logs.networkErrors.slice(0, 1).forEach(e => console.log(`     NETWORK: ${e.substring(0, 80)}`));
      }

      results.push({ page: page.name, ...logs });
    } catch (e) {
      console.log(`❌ ${page.name.padEnd(15)} → FAILED: ${e.message}`);
      results.push({ page: page.name, failed: true, error: e.message });
    }

    await context.close();
  }

  const totalErrors = results.reduce((sum, r) => sum + r.errors.length, 0);
  const totalWarnings = results.reduce((sum, r) => sum + r.warnings.length, 0);
  const totalNetwork = results.reduce((sum, r) => sum + r.networkErrors.length, 0);

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log(`║  TOTAL: ${totalErrors} errors, ${totalWarnings} warnings, ${totalNetwork} network issues  ║`);
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  await browser.close();
  process.exit(totalErrors > 0 ? 1 : 0);
}

testAllPages();
