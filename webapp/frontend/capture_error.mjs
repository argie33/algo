import { chromium } from 'playwright';

(async () => {
  try {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    const errors = [];
    const networkErrors = [];

    // Capture console errors and warnings
    page.on('console', msg => {
      const text = msg.text();
      if (text.includes('503') || text.includes('error') || text.includes('Error') || text.includes('failed')) {
        errors.push(`[${msg.type()}] ${text}`);
      }
    });

    // Capture network failures
    page.on('response', response => {
      if (response.status() >= 400) {
        networkErrors.push({
          url: response.url(),
          status: response.status(),
          statusText: response.statusText()
        });
      }
    });

    await page.setViewportSize({ width: 1920, height: 1080 });

    console.log('Loading dashboard...');
    await page.goto('http://localhost:5173', { waitUntil: 'load', timeout: 30000 });

    // Wait for API calls
    console.log('Waiting for API responses...');
    await page.waitForTimeout(6000);

    // Evaluate what the React component sees
    console.log('\n=== CAPTURED CONSOLE ERRORS ===');
    errors.slice(0, 20).forEach(e => console.log(e));

    console.log('\n=== NETWORK ERRORS (4xx/5xx) ===');
    networkErrors.slice(0, 10).forEach(e => {
      console.log(`${e.status} ${e.statusText} ${e.url.substring(0, 100)}`);
    });

    // Check page state
    console.log('\n=== REACT COMPONENT STATE ===');
    const componentState = await page.evaluate(() => {
      const errorDiv = document.querySelector('[class*="alert-danger"]');
      const loading = document.querySelector('[class*="Loading"]');
      return {
        showsError: !!errorDiv,
        errorText: errorDiv?.innerText || null,
        isLoading: !!loading,
        bodyHTML: document.body.innerHTML.substring(0, 500)
      };
    });
    console.log(JSON.stringify(componentState, null, 2));

    await browser.close();
    process.exit(0);
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
})();
