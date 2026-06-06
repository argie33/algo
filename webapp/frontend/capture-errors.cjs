const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const consoleMessages = [];
  const networkErrors = [];
  const responseErrors = [];

  page.on('console', msg => {
    consoleMessages.push({
      type: msg.type(),
      text: msg.text()
    });
  });

  page.on('response', response => {
    if (response.status() >= 400) {
      responseErrors.push({
        url: response.url(),
        status: response.status(),
        statusText: response.statusText()
      });
    }
  });

  page.on('requestfailed', request => {
    networkErrors.push({
      url: request.url(),
      failure: request.failure().errorText
    });
  });

  try {
    console.log('Navigating to dashboard...');
    await page.goto('http://localhost:5173/app/dashboard', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(3000);
    
    console.log('\n=== CONSOLE ERRORS & WARNINGS ===');
    const errors = consoleMessages.filter(m => m.type === 'error' || m.type === 'warning');
    if (errors.length > 0) {
      errors.forEach(e => console.log(`[${e.type.toUpperCase()}] ${e.text}`));
    } else {
      console.log('No console errors found');
    }

    console.log('\n=== HTTP ERRORS (4xx, 5xx) ===');
    if (responseErrors.length > 0) {
      responseErrors.forEach(e => console.log(`${e.status} ${e.statusText}: ${e.url}`));
    } else {
      console.log('No HTTP errors detected');
    }

    console.log('\n=== FAILED NETWORK REQUESTS ===');
    if (networkErrors.length > 0) {
      networkErrors.forEach(e => console.log(`${e.url} - Error: ${e.failure}`));
    } else {
      console.log('No failed requests');
    }

    console.log('\n=== ALL CONSOLE MESSAGES (total ' + consoleMessages.length + ') ===');
    consoleMessages.slice(0, 50).forEach(m => console.log(`[${m.type}] ${m.text}`));
    if (consoleMessages.length > 50) console.log(`... and ${consoleMessages.length - 50} more messages`);
    
  } catch (error) {
    console.error('\nError:', error.message);
  }

  await browser.close();
})();
