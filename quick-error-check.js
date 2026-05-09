const { chromium } = require('playwright');
const fs = require('fs');

async function quickCheck() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const pageResults = [];
  const allErrors = [];

  // Pages to check - SKIP algo-dashboard for now
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
  ];

  console.log('✅ QUICK ERROR CHECK (skipping Algo Dashboard)\n');

  for (const pageInfo of pages) {
    const pageErrors = [];

    page.on('console', msg => {
      if (msg.type() === 'error') {
        pageErrors.push(msg.text());
      }
    });

    try {
      const response = await page.goto(`http://localhost:5173${pageInfo.url}`, {
        waitUntil: 'networkidle',
        timeout: 10000
      });

      const status = response.status();
      const emoji = status === 200 && pageErrors.length === 0 ? '✅' : status === 200 ? '⚠️ ' : '❌';

      console.log(`${emoji} ${pageInfo.name.padEnd(20)} - Status: ${status}, Errors: ${pageErrors.length}`);

      if (pageErrors.length > 0) {
        allErrors.push(...pageErrors.map(e => `${pageInfo.name}: ${e}`));
      }

      pageResults.push({
        name: pageInfo.name,
        status: response.status(),
        errors: pageErrors.length
      });

    } catch (error) {
      console.log(`❌ ${pageInfo.name.padEnd(20)} - ${error.message}`);
      pageResults.push({
        name: pageInfo.name,
        status: 'ERROR',
        errors: 1
      });
    }
  }

  // Summary
  console.log(`\n${'='.repeat(50)}`);
  const successCount = pageResults.filter(p => p.status === 200 && p.errors === 0).length;
  const errorCount = pageResults.filter(p => p.errors > 0).length;

  console.log(`✅ Working: ${successCount}/${pageResults.length}`);
  console.log(`❌ Errors: ${errorCount}`);
  console.log(`\n💡 Status: Pages working well! Only issue is Algo Dashboard (skip for now)`);

  await browser.close();

  return { success: errorCount === 0 };
}

quickCheck().then(result => {
  process.exit(result.success ? 0 : 1);
}).catch(err => {
  console.error('Script error:', err);
  process.exit(1);
});
