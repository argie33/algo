import { chromium } from 'playwright';

(async () => {
  try {
    const browser = await chromium.launch({ headless: false });
    const page = await browser.newPage();

    // Capture console logs
    const consoleLogs = [];
    page.on('console', msg => {
      consoleLogs.push(`[${msg.type()}] ${msg.text()}`);
    });

    // Capture network requests/responses
    const networkLogs = [];
    page.on('response', response => {
      networkLogs.push(`${response.status()} ${response.url()}`);
    });

    await page.setViewportSize({ width: 1920, height: 1080 });

    console.log('Loading dashboard...');
    await page.goto('http://localhost:5173', {
      waitUntil: 'load',
      timeout: 30000
    });

    // Wait for data to load
    await page.waitForTimeout(5000);

    // Check what's in the page
    console.log('\n=== NETWORK REQUESTS ===');
    networkLogs.forEach(log => console.log(log));

    console.log('\n=== BROWSER CONSOLE ===');
    consoleLogs.forEach(log => console.log(log));

    // Try to get API data directly from the page context
    console.log('\n=== PAGE STATE ===');
    const pageData = await page.evaluate(() => {
      // Check if there are any React component errors
      const errorDiv = document.querySelector('[class*="Market Health Data Unavailable"]');
      return {
        hasError: !!errorDiv,
        bodyText: document.body.innerText.substring(0, 500)
      };
    });
    console.log(JSON.stringify(pageData, null, 2));

    // Take screenshot
    await page.screenshot({ path: 'debug_dashboard.png', fullPage: true });
    console.log('\nScreenshot saved: debug_dashboard.png');

    await browser.close();
    process.exit(0);
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
})();
