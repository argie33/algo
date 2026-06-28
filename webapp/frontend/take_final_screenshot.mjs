import { chromium } from 'playwright';

(async () => {
  try {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.setViewportSize({ width: 1920, height: 1080 });

    console.log('Loading dashboard...');
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 30000 });

    // Longer wait for all data to load
    console.log('Waiting for all API calls and rendering...');
    await page.waitForTimeout(8000);

    console.log('Taking screenshot...');
    await page.screenshot({ path: 'dashboard_panels_working.png', fullPage: true });

    console.log('✓ Screenshot complete');
    await browser.close();
    process.exit(0);
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
})();
