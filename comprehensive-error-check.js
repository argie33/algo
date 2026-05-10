const { chromium } = require('playwright');
const fs = require('fs');

async function comprehensiveCheck() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const pageResults = [];
  const allErrors = [];

  // Pages to check - all the app dashboard pages
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

  console.log('📊 COMPREHENSIVE FRONTEND ERROR AUDIT');
  console.log('='.repeat(60));

  for (const pageInfo of pages) {
    const pageErrors = [];
    const apiCalls = [];
    let status = 'UNKNOWN';

    page.on('console', msg => {
      if (msg.type() === 'error') {
        pageErrors.push(msg.text());
      }
    });

    page.on('response', response => {
      if (response.url().includes('/api/')) {
        apiCalls.push({
          url: response.url().split('localhost:3001/')[1] || response.url(),
          status: response.status()
        });
      }
    });

    try {
      console.log(`\n🔍 ${pageInfo.name} (${pageInfo.url})...`);
      const response = await page.goto(`http://localhost:5173${pageInfo.url}`, {
        waitUntil: 'networkidle',
        timeout: 15000
      });

      status = response.status();
      await page.waitForTimeout(1000);

      const content = await page.evaluate(() => {
        return {
          headings: Array.from(document.querySelectorAll('h1, h2')).map(h => h.textContent.trim()).slice(0, 2),
          tables: document.querySelectorAll('table').length,
          charts: Array.from(document.querySelectorAll('[class*="chart"], svg[data-testid*="chart"]')).length,
          errorElements: Array.from(document.querySelectorAll('[role="alert"], .error, .MuiAlert-error')).map(e => e.textContent.trim()).slice(0, 2)
        };
      });

      const failedApis = apiCalls.filter(c => c.status >= 400);
      const emoji = failedApis.length > 0 ? '⚠️ ' : '✅';

      console.log(`  ${emoji} Status: ${status}`);
      console.log(`  📝 Headings: ${content.headings.join(' | ') || 'None'}`);
      console.log(`  📊 Tables: ${content.tables}, Charts: ${content.charts}`);
      console.log(`  🔗 API calls: ${apiCalls.length} (${failedApis.length} failed)`);

      if (pageErrors.length > 0) {
        console.log(`  ❌ Console errors: ${pageErrors.length}`);
        pageErrors.forEach((err, i) => {
          if (i < 3) console.log(`     - ${err.substring(0, 80)}`);
        });
        allErrors.push(...pageErrors.map(e => `${pageInfo.name}: ${e}`));
      }

      if (content.errorElements.length > 0) {
        console.log(`  ⚠️  Page alerts: ${content.errorElements.length}`);
        content.errorElements.forEach(err => console.log(`     - ${err.substring(0, 80)}`));
      }

      if (failedApis.length > 0) {
        console.log(`  ❌ Failed API calls:`);
        failedApis.forEach(api => console.log(`     ${api.status} ${api.url}`));
      }

      pageResults.push({
        name: pageInfo.name,
        url: pageInfo.url,
        status,
        errorCount: pageErrors.length,
        failedApis: failedApis.length,
        hasContent: content.headings.length > 0
      });

    } catch (error) {
      console.log(`  ❌ Load error: ${error.message}`);
      allErrors.push(`${pageInfo.name}: ${error.message}`);
      pageResults.push({
        name: pageInfo.name,
        url: pageInfo.url,
        status: 'ERROR',
        errorCount: 1,
        failedApis: 0,
        hasContent: false
      });
    }
  }

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('📋 SUMMARY');
  console.log('='.repeat(60));

  const statusCounts = {};
  pageResults.forEach(r => {
    statusCounts[r.status] = (statusCounts[r.status] || 0) + 1;
  });

  console.log(`\nPages tested: ${pageResults.length}`);
  Object.entries(statusCounts).forEach(([status, count]) => {
    const emoji = status === '200' ? '✅' : '❌';
    console.log(`  ${emoji} ${status}: ${count}`);
  });

  const pagesWithErrors = pageResults.filter(r => r.errorCount > 0);
  const pagesWithFailedApis = pageResults.filter(r => r.failedApis > 0);

  console.log(`\n❌ Pages with console errors: ${pagesWithErrors.length}`);
  pagesWithErrors.forEach(p => {
    console.log(`  - ${p.name}: ${p.errorCount} errors`);
  });

  console.log(`\n❌ Pages with failed API calls: ${pagesWithFailedApis.length}`);
  pagesWithFailedApis.forEach(p => {
    console.log(`  - ${p.name}: ${p.failedApis} failed`);
  });

  console.log(`\n💾 Total unique errors: ${allErrors.length}`);

  if (allErrors.length > 0 && allErrors.length <= 10) {
    console.log('\nError details:');
    [...new Set(allErrors)].slice(0, 10).forEach((err, i) => {
      console.log(`  ${i + 1}. ${err.substring(0, 120)}`);
    });
  }

  // Save detailed report
  fs.writeFileSync('comprehensive-audit.json', JSON.stringify({
    timestamp: new Date().toISOString(),
    results: pageResults,
    errorSummary: {
      totalPages: pageResults.length,
      pagesWithErrors: pagesWithErrors.length,
      pagesWithFailedApis: pagesWithFailedApis.length,
      totalErrors: allErrors.length
    }
  }, null, 2));

  console.log('\n📄 Detailed report: comprehensive-audit.json');

  await browser.close();

  return {
    hasErrors: allErrors.length > 0,
    failedPages: pagesWithErrors.length + pagesWithFailedApis.length
  };
}

comprehensiveCheck().then(result => {
  console.log(`\n${result.hasErrors ? '❌' : '✅'} Audit complete - ${result.failedPages} pages with issues`);
  process.exit(result.hasErrors ? 1 : 0);
}).catch(err => {
  console.error('Script error:', err);
  process.exit(1);
});
