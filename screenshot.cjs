const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.setViewportSize({ width: 1400, height: 900 });

  // Navigate to sectors page
  await page.goto('http://localhost:5173/sectors', { waitUntil: 'networkidle' });

  // Wait for data to load
  await page.waitForTimeout(3000);

  // Take screenshot
  await page.screenshot({ path: '/tmp/sectors_page.png', fullPage: true });

  console.log('✅ Screenshot saved to /tmp/sectors_page.png');

  await browser.close();
})();
