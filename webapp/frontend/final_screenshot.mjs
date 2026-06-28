import { chromium } from 'playwright';

(async () => {
  try {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    await page.setViewportSize({ width: 1920, height: 1080 });

    console.log('Navigating to dashboard...');
    await page.goto('http://localhost:5173', {
      waitUntil: 'networkidle',
      timeout: 30000
    });

    // Wait extra time for React Query to fetch and render all data
    console.log('Waiting for all data to load...');
    await page.waitForTimeout(5000);

    // Take screenshot
    console.log('Capturing screenshot...');
    await page.screenshot({ path: 'dashboard_working.png', fullPage: true });

    console.log('✓ Screenshot saved: dashboard_working.png');

    await browser.close();
    process.exit(0);
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
})();
