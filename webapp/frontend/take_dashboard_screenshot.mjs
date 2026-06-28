import { chromium } from 'playwright';

(async () => {
  try {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    // Set viewport size for full dashboard view
    await page.setViewportSize({ width: 1920, height: 1080 });

    console.log('Loading dashboard...');

    // Navigate to dashboard
    await page.goto('http://localhost:5173', {
      waitUntil: 'load',
      timeout: 30000
    });

    // Wait for data to load (wait for API responses)
    console.log('Waiting for dashboard data to load...');
    await page.waitForTimeout(3000);

    // Take screenshot
    console.log('Taking screenshot...');
    await page.screenshot({ path: 'dashboard_fresh.png', fullPage: true });

    console.log('✓ Dashboard screenshot saved: dashboard_fresh.png');

    await browser.close();
    process.exit(0);
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
})();
