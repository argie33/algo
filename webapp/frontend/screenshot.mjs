import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Set viewport to capture full dashboard
  await page.setViewportSize({ width: 1920, height: 1080 });

  // Navigate to the dashboard
  await page.goto('http://localhost:5192', { waitUntil: 'networkidle' });

  // Wait a bit for any data to load
  await page.waitForTimeout(3000);

  // Take screenshot
  await page.screenshot({ path: 'dashboard_final.png', fullPage: true });

  console.log('Dashboard screenshot captured: dashboard_final.png');

  await browser.close();
})();
