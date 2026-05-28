const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });

  const pagesToScreenshot = [
    { name: 'Dashboard', path: '/app/markets' },
    { name: 'Trading Signals', path: '/app/trading-signals' },
    { name: 'Service Health', path: '/app/health' }
  ];

  const screenshotDir = 'screenshots_data_issues';
  if (!fs.existsSync(screenshotDir)) {
    fs.mkdirSync(screenshotDir, { recursive: true });
  }

  for (const item of pagesToScreenshot) {
    console.log(`Screenshotting: ${item.name}`);
    try {
      await page.goto(`http://localhost:5173${item.path}`, { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
      await page.waitForTimeout(2000);

      const screenshot = path.join(screenshotDir, `${item.name.replace(/\s+/g, '_')}.png`);
      await page.screenshot({ path: screenshot, fullPage: true });
      console.log(`  Saved: ${screenshot}`);

      // Also extract any error/warning messages
      const text = await page.textContent('body');
      const errorMsg = text.match(/no data|insufficient|not enough|error|warning/gi);
      if (errorMsg) {
        console.log(`  Messages found: ${[...new Set(errorMsg)].join(', ')}`);
      }
    } catch (e) {
      console.log(`  Error: ${e.message}`);
    }
  }

  await browser.close();
})();
