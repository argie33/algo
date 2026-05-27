const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });

  console.log("Testing with correct routes:");
  console.log("=" + "=".repeat(60));

  // Test CORRECT routes
  const pages = [
    { name: 'Markets Health', url: '/app/markets' },
    { name: 'Swing Candidates', url: '/app/swing' },
    { name: 'Economic', url: '/app/economic' },
    { name: 'Sectors', url: '/app/sectors' },
    { name: 'Scores', url: '/app/scores' },
    { name: 'Trading Signals', url: '/app/trading-signals' },
    { name: 'Portfolio', url: '/app/portfolio' },
  ];

  for (const p of pages) {
    await page.goto(`http://localhost:5173${p.url}`, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(1500);

    const text = await page.textContent('body');
    const has404 = text.includes('404') || text.includes('not found');
    const hasContent = text.length > 2000;
    const status = has404 ? 'NOT FOUND' : hasContent ? 'OK' : 'MINIMAL';

    console.log(`[${status}] ${p.name.padEnd(20)} ${p.url}`);
  }

  console.log("=" + "=".repeat(60));
  await browser.close();
})();
