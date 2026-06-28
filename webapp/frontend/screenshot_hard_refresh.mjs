import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Disable caching
  await page.context().addCookies([]);

  // Set viewport to capture full dashboard
  await page.setViewportSize({ width: 1920, height: 1080 });

  // Navigate to the dashboard with no-cache
  console.log('Navigating to dashboard with cache-control header...');
  await page.goto('http://localhost:5192', {
    waitUntil: 'networkidle',
    timeout: 30000
  });

  // Wait for data to load
  console.log('Waiting for data to load...');
  await page.waitForTimeout(5000);

  // Hard refresh (Ctrl+Shift+R equivalent)
  console.log('Performing hard refresh...');
  await page.keyboard.press('F5');
  await page.waitForTimeout(8000);

  // Take screenshot
  console.log('Taking screenshot...');
  await page.screenshot({ path: 'dashboard_no_cache.png', fullPage: true });

  console.log('Dashboard screenshot captured: dashboard_no_cache.png');

  await browser.close();
})();
