const { chromium } = require('playwright');

async function checkBrowserLogs() {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const consoleErrors = [];
  const pageErrors = [];
  const networkErrors = [];

  page.on('console', msg => {
    if (msg.type() === 'error' || msg.type() === 'warning') {
      console.log(`[${msg.type().toUpperCase()}] ${msg.text()}`);
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    }
  });

  page.on('pageerror', err => {
    pageErrors.push(err.message);
    console.error('[PAGE ERROR]', err.message);
  });

  page.on('requestfailed', request => {
    networkErrors.push({
      url: request.url(),
      failure: request.failure()?.errorText
    });
    console.error('[NETWORK ERROR]', request.url(), request.failure()?.errorText);
  });

  try {
    console.log('Navigating to http://localhost:5174...');
    const response = await page.goto('http://localhost:5174', {
      waitUntil: 'networkidle',
      timeout: 15000
    });
    console.log(`[RESPONSE] Status: ${response.status()}`);

    // Wait for any JS errors to manifest
    await page.waitForTimeout(3000);

    // Get any visible error messages
    const errorMessages = await page.$$eval('*', elements => {
      return elements
        .filter(el => {
          const text = el.textContent.toLowerCase();
          return text.includes('error') && el.offsetParent !== null && text.length < 200;
        })
        .slice(0, 10)
        .map(el => ({
          tag: el.tagName,
          text: el.textContent.substring(0, 100)
        }));
    }).catch(() => []);

    if (errorMessages.length > 0) {
      console.log('\n[VISIBLE ERRORS ON PAGE]');
      errorMessages.forEach(err => {
        console.log(`  ${err.tag}: ${err.text}`);
      });
    }

  } catch (error) {
    console.error('[TEST ERROR]', error.message);
  } finally {
    console.log('\n[SUMMARY]');
    console.log(`Console errors: ${consoleErrors.length}`);
    console.log(`Page errors: ${pageErrors.length}`);
    console.log(`Network errors: ${networkErrors.length}`);
    await browser.close();
  }
}

checkBrowserLogs().catch(console.error);
