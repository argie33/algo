const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });

  const pagesToCheck = [
    { name: 'Dashboard', path: '/app/markets', minTextLength: 3000 },
    { name: 'Trading Signals', path: '/app/trading-signals', minTextLength: 2000 },
    { name: 'Portfolio', path: '/app/portfolio', minTextLength: 1000 },
    { name: 'Markets Health', path: '/app/markets', minTextLength: 3000 },
    { name: 'Sector Analysis', path: '/app/sectors', minTextLength: 2000 },
    { name: 'Economic Data', path: '/app/economic', minTextLength: 2000 },
    { name: 'Scores', path: '/app/scores', minTextLength: 2000 },
    { name: 'Swing Candidates', path: '/app/swing', minTextLength: 2000 },
    { name: 'Trade Tracker', path: '/app/trades', minTextLength: 1000 },
    { name: 'Service Health', path: '/app/health', minTextLength: 1000 }
  ];

  console.log('Checking page data completeness...\n');

  const issues = [];

  for (const item of pagesToCheck) {
    try {
      console.log(`Checking: ${item.name} (${item.path})`);
      await page.goto(`http://localhost:5173${item.path}`, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(2000);

      const text = await page.textContent('body');
      const textLength = text.length;

      // Check for common "no data" patterns
      const lower = text.toLowerCase();
      const hasNoDataMessage = /no data|insufficient|not enough|empty|no results/i.test(text);
      const isDataInsufficientSize = textLength < item.minTextLength;

      if (hasNoDataMessage) {
        issues.push(`${item.name}: Contains "no data" message`);
        console.log(`  ⚠️  Contains "no data" message\n`);
      } else if (isDataInsufficientSize) {
        issues.push(`${item.name}: Low data (${textLength} chars < ${item.minTextLength} expected)`);
        console.log(`  ⚠️  Low data (${textLength} chars < ${item.minTextLength} expected)\n`);
      } else {
        console.log(`  ✓ Has data (${textLength} chars)\n`);
      }
    } catch (e) {
      issues.push(`${item.name}: Error - ${e.message}`);
      console.log(`  ❌ Error: ${e.message}\n`);
    }
  }

  console.log('='.repeat(70));
  if (issues.length === 0) {
    console.log('✅ ALL PAGES HAVE SUFFICIENT DATA');
  } else {
    console.log(`⚠️  FOUND ${issues.length} ISSUES:`);
    issues.forEach(issue => console.log(`  • ${issue}`));
  }
  console.log('='.repeat(70));

  await browser.close();
})();
