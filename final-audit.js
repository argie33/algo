const { chromium } = require('playwright');

async function finalAudit() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const results = [];

  const pages = [
    { name: 'Market Overview', url: '/app/market' },
    { name: 'Sectors', url: '/app/sectors' },
    { name: 'Commodities', url: '/app/commodities' },
    { name: 'Trading Signals', url: '/app/trading-signals' },
    { name: 'Deep Value', url: '/app/deep-value' },
    { name: 'Swing Candidates', url: '/app/swing' },
    { name: 'Stock Scores', url: '/app/scores' },
    { name: 'Metrics', url: '/app/metrics' },
    { name: 'Economic', url: '/app/economic' },
    { name: 'Sentiment', url: '/app/sentiment' },
    { name: 'Hedge Helper', url: '/app/hedge-helper' },
    { name: 'Backtests', url: '/app/backtests' },
    { name: 'Algo Dashboard', url: '/app/algo-dashboard' },
  ];

  console.log('✅ FINAL COMPREHENSIVE AUDIT\n');
  console.log('='.repeat(60));

  for (const pageInfo of pages) {
    const errors = [];
    const apiCalls = [];

    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    page.on('response', response => {
      if (response.url().includes('/api/')) {
        apiCalls.push(response.status());
      }
    });

    try {
      const response = await page.goto(`http://localhost:5173${pageInfo.url}`, {
        waitUntil: 'networkidle',
        timeout: 12000
      });

      const status = response.status();
      const failedApis = apiCalls.filter(s => s >= 400).length;
      const emoji = status === 200 && errors.length === 0 && failedApis === 0 ? '✅' : '⚠️ ';

      console.log(`${emoji} ${pageInfo.name.padEnd(25)} │ Status: ${status} │ Errors: ${errors.length} │ API: ${apiCalls.length} (${failedApis} failed)`);

      results.push({
        name: pageInfo.name,
        status: response.status(),
        errors: errors.length,
        apiCalls: apiCalls.length,
        failedApis
      });

    } catch (error) {
      console.log(`❌ ${pageInfo.name.padEnd(25)} │ ${error.message.substring(0, 40)}`);
      results.push({
        name: pageInfo.name,
        status: 'ERROR',
        errors: 1,
        apiCalls: 0,
        failedApis: 0
      });
    }
  }

  // Summary
  console.log('='.repeat(60));
  const working = results.filter(r => r.status === 200 && r.errors === 0 && r.failedApis === 0).length;
  const total = results.length;
  const totalErrors = results.reduce((sum, r) => sum + r.errors, 0);
  const totalFailedApis = results.reduce((sum, r) => sum + r.failedApis, 0);

  console.log(`\n✅ WORKING: ${working}/${total}`);
  console.log(`❌ ERRORS: ${totalErrors} total across all pages`);
  console.log(`🔴 FAILED API CALLS: ${totalFailedApis}`);

  if (working === total) {
    console.log('\n🎉 ALL PAGES WORKING PERFECTLY! 🎉');
  }

  await browser.close();
  return { working, total, totalErrors };
}

finalAudit().then(result => {
  process.exit(result.working === result.total ? 0 : 1);
}).catch(err => {
  console.error('Script error:', err);
  process.exit(1);
});
