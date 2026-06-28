import { chromium } from 'playwright';

(async () => {
  try {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    await page.setViewportSize({ width: 1920, height: 1080 });

    console.log('Loading dashboard fresh...');
    await page.goto('http://localhost:5173', {
      waitUntil: 'load',
      timeout: 30000
    });

    // Wait for data to fully load (API calls to complete)
    console.log('Waiting for API responses...');
    await page.waitForTimeout(8000);

    // Take screenshot
    console.log('Taking screenshot...');
    await page.screenshot({ path: 'dashboard_final.png', fullPage: true });

    console.log('✓ Dashboard screenshot saved: dashboard_final.png');

    await browser.close();
    process.exit(0);
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
})();
