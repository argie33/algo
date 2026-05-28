const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });
  
  const screenshotsDir = '/tmp/screenshots-debug';
  if (!fs.existsSync(screenshotsDir)) fs.mkdirSync(screenshotsDir);

  // Check the problematic pages
  const problematic = [
    { name: 'MarketsHealth', url: '/app/markets' },
    { name: 'TradingSignals', url: '/app/trading-signals' },
    { name: 'Scores', url: '/app/scores' }
  ];

  for (const p of problematic) {
    console.log(`Checking ${p.name}...`);
    await page.goto(`http://localhost:5173${p.url}`, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(2000);

    // Check page title
    const title = await page.title();
    const text = await page.textContent('body');
    const status = text.includes('404') ? '404' : text.length > 5000 ? 'OK' : 'SHORT';
    
    console.log(`  Title: ${title}`);
    console.log(`  Status: ${status} (${text.length} chars)`);
    
    // Take screenshot
    const screenshotPath = path.join(screenshotsDir, `${p.name}.png`);
    await page.screenshot({ path: screenshotPath });
    console.log(`  Screenshot: ${screenshotPath}\n`);
  }

  await browser.close();
})();
