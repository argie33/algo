const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });

  const pagesToCheck = [
    { name: 'Dashboard', path: '/app/markets' },
    { name: 'Trading Signals', path: '/app/trading-signals' },
    { name: 'Service Health', path: '/app/health' }
  ];

  for (const item of pagesToCheck) {
    console.log(`\n${'='.repeat(70)}`);
    console.log(`PAGE: ${item.name} (${item.path})`);
    console.log('='.repeat(70));

    try {
      await page.goto(`http://localhost:5173${item.path}`, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(2000);

      const text = await page.textContent('body');

      // Extract lines containing "no data", "insufficient", "empty", etc.
      const lines = text.split('\n');
      const relevantLines = lines
        .filter(line => /no data|insufficient|empty|not enough|error|stale/i.test(line))
        .map(line => line.trim())
        .filter(line => line.length > 3 && line.length < 200);

      if (relevantLines.length === 0) {
        console.log('No "no data" messages found');
      } else {
        console.log(`Found ${relevantLines.length} relevant messages:`);
        [...new Set(relevantLines)].forEach(msg => {
          console.log(`  • ${msg}`);
        });
      }
    } catch (e) {
      console.log(`Error: ${e.message}`);
    }
  }

  await browser.close();
})();
