import { chromium } from 'playwright';

(async () => {
  try {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    // Capture network requests
    const networkLog = [];
    page.on('response', response => {
      networkLog.push({
        url: response.url(),
        status: response.status(),
        isApi: response.url().includes('/api')
      });
    });

    // Capture console logs
    const consoleLogs = [];
    page.on('console', msg => {
      consoleLogs.push(`[${msg.type()}] ${msg.text()}`);
    });

    console.log('Navigating to frontend...');
    await page.goto('http://localhost:5173', { waitUntil: 'load', timeout: 15000 });

    // Wait for API calls
    console.log('Waiting for API calls...');
    await page.waitForTimeout(3000);

    console.log('\n=== API REQUESTS ===');
    networkLog
      .filter(r => r.isApi)
      .slice(0, 5)
      .forEach(r => console.log(`${r.status} ${r.url}`));

    console.log('\n=== CONSOLE ERRORS ===');
    const errors = consoleLogs.filter(l => l.includes('error') || l.includes('Error') || l.includes('failed'));
    if (errors.length > 0) {
      errors.forEach(e => console.log(e));
    } else {
      console.log('(No errors in console)');
    }

    // Check if API call succeeded by looking at the DOM
    console.log('\n=== PAGE STATE ===');
    const pageState = await page.evaluate(() => {
      const errorAlert = document.querySelector('[class*="alert-danger"]');
      const mainContent = document.querySelector('.main-content');
      return {
        hasError: !!errorAlert,
        errorText: errorAlert?.innerText || null,
        mainContentExists: !!mainContent,
      };
    });
    console.log(JSON.stringify(pageState, null, 2));

    await browser.close();
    process.exit(0);
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
})();
