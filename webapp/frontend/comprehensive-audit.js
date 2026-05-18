import puppeteer from 'puppeteer';

const pageRoutes = [
  '/app/market', '/app/sectors', '/app/scores', '/app/trading-signals', '/app/financial-data',
  '/app/deep-value', '/app/etf-signals', '/app/earnings', '/app/economic', '/app/hedge',
  '/app/portfolio', '/app/portfolio-optimizer', '/app/commodity-analysis', '/app/sentiment',
  '/app/trade-history', '/app/messages', '/app/services', '/app/settings', '/api-docs'
];

const pageNames = [
  'Market Overview', 'Sector Analysis', 'Stock Scores', 'Trading Signals', 'Financial Data',
  'Deep Value', 'ETF Signals', 'Earnings Calendar', 'Economic Dashboard', 'Hedge Helper',
  'Portfolio Dashboard', 'Portfolio Optimizer', 'Commodities', 'Sentiment',
  'Trade History', 'Messages', 'Service Health', 'Settings', 'API Docs'
];

(async () => {
  const browser = await puppeteer.launch({ headless: 'new' });
  const results = [];

  for (let i = 0; i < pageRoutes.length; i++) {
    const p = await browser.newPage();
    const route = pageRoutes[i];
    const name = pageNames[i];

    const consoleMessages = [];
    let loaded = false;

    p.on('console', msg => {
      consoleMessages.push({
        type: msg.type(),
        text: msg.text(),
        location: msg.location()
      });
    });

    try {
      await p.goto(`http://localhost:5173${route}`, { waitUntil: 'networkidle2', timeout: 15000 });
      await new Promise(r => setTimeout(r, 2000));
      loaded = true;
    } catch (e) {
      consoleMessages.push({
        type: 'error',
        text: `Load failed: ${e.message}`
      });
    }

    const errors = consoleMessages.filter(m => m.type === 'error');
    const warnings = consoleMessages.filter(m => m.type === 'warning');

    results.push({
      name,
      route,
      loaded,
      errors,
      warnings,
      allMessages: consoleMessages
    });

    await p.close();
  }

  await browser.close();

  console.log('\n=== F12 CONSOLE AUDIT RESULTS ===\n');

  let totalErrors = 0;
  let totalWarnings = 0;
  let pagesWithIssues = 0;

  results.forEach(r => {
    const hasErrors = r.errors.length > 0;
    const hasWarnings = r.warnings.length > 0;

    if (!r.loaded || hasErrors || hasWarnings) {
      pagesWithIssues++;
      console.log(`\n❌ ${r.name} (${r.route})`);
      console.log(`   Status: ${r.loaded ? '✅ Loaded' : '❌ Failed to load'}`);

      if (hasErrors) {
        totalErrors += r.errors.length;
        console.log(`   Errors (${r.errors.length}):`);
        r.errors.forEach(e => {
          console.log(`     - ${e.text}`);
          if (e.location) console.log(`       at ${e.location.url}:${e.location.lineNumber}`);
        });
      }

      if (hasWarnings) {
        totalWarnings += r.warnings.length;
        console.log(`   Warnings (${r.warnings.length}):`);
        r.warnings.forEach(w => {
          console.log(`     - ${w.text}`);
        });
      }
    } else {
      console.log(`✅ ${r.name}`);
    }
  });

  console.log('\n=== SUMMARY ===');
  console.log(`Total pages: ${results.length}`);
  console.log(`Pages with issues: ${pagesWithIssues}`);
  console.log(`Total errors: ${totalErrors}`);
  console.log(`Total warnings: ${totalWarnings}`);
  console.log(`Status: ${totalErrors === 0 && totalWarnings === 0 && pagesWithIssues === 0 ? '✅ ALL CLEAN' : '❌ NEEDS FIXES'}`);

  process.exit(totalErrors > 0 ? 1 : 0);
})().catch(err => {
  console.error('Audit failed:', err);
  process.exit(1);
});
