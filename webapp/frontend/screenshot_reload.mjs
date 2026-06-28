import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Set viewport to capture full dashboard
  await page.setViewportSize({ width: 1920, height: 1080 });

  // Navigate to the dashboard
  console.log('Navigating to dashboard...');
  await page.goto('http://localhost:5192', { waitUntil: 'networkidle', timeout: 30000 });

  // Wait a bit for any data to load
  console.log('Waiting for data to load...');
  await page.waitForTimeout(5000);

  // Reload the page to clear any cache
  console.log('Reloading page...');
  await page.reload({ waitUntil: 'networkidle', timeout: 30000 });

  // Wait another 5 seconds for data to load
  await page.waitForTimeout(5000);

  // Take screenshot
  console.log('Taking screenshot...');
  await page.screenshot({ path: 'dashboard_refreshed.png', fullPage: true });

  console.log('Dashboard screenshot captured: dashboard_refreshed.png');

  await browser.close();
})();
