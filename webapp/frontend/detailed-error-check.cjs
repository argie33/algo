const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const errors = [];
  const warnings = [];
  const apiErrors = [];
  const allRequests = [];

  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    } else if (msg.type() === 'warning') {
      warnings.push(msg.text());
    }
  });

  page.on('response', response => {
    allRequests.push({
      url: response.url(),
      status: response.status(),
      method: response.request().method()
    });
    if (response.status() >= 400) {
      apiErrors.push({
        url: response.url(),
        status: response.status(),
        statusText: response.statusText()
      });
    }
  });

  const pages = [
    'http://localhost:5173/app/dashboard',
    'http://localhost:5173/app/trading-signals',
    'http://localhost:5173/app/portfolio',
    'http://localhost:5173/app/scores'
  ];

  for (const pageUrl of pages) {
    console.log(`\n>>> Navigating to ${pageUrl.split('/').pop()}...`);
    try {
      await page.goto(pageUrl, { waitUntil: 'networkidle', timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(2000);
    } catch (e) {
      console.log(`Error navigating: ${e.message}`);
    }
  }

  console.log('\n=== ERRORS FOUND ===');
  if (errors.length > 0) {
    console.log(`Total errors: ${errors.length}`);
    errors.forEach((e, i) => console.log(`  ${i+1}. ${e.substring(0, 100)}`));
  } else {
    console.log('No console errors');
  }

  console.log('\n=== WARNINGS FOUND ===');
  if (warnings.length > 0) {
    console.log(`Total warnings: ${warnings.length}`);
    warnings.slice(0, 10).forEach((w, i) => console.log(`  ${i+1}. ${w.substring(0, 100)}`));
  } else {
    console.log('No console warnings');
  }

  console.log('\n=== API ERRORS (4xx/5xx) ===');
  if (apiErrors.length > 0) {
    console.log(`Total API errors: ${apiErrors.length}`);
    apiErrors.forEach(e => console.log(`  ${e.status} ${e.statusText}: ${e.url.substring(0, 80)}`));
  } else {
    console.log('No API errors (4xx/5xx) detected');
  }

  console.log('\n=== ALL REQUESTS SUMMARY ===');
  const statusCounts = {};
  allRequests.forEach(r => {
    statusCounts[r.status] = (statusCounts[r.status] || 0) + 1;
  });
  Object.entries(statusCounts).sort().forEach(([status, count]) => {
    console.log(`  ${status}: ${count} requests`);
  });

  await browser.close();
})();
