const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  const errors = [];
  const warnings = [];
  const networkErrors = [];

  page.on('console', msg => {
    const text = msg.text();
    const type = msg.type();
    if (type === 'error') {
      errors.push(`CONSOLE ERROR: ${text}`);
    } else if (type === 'warning') {
      warnings.push(`CONSOLE WARN: ${text}`);
    }
  });

  page.on('pageerror', error => {
    errors.push(`PAGE ERROR: ${error.message}`);
  });

  page.on('requestfailed', request => {
    networkErrors.push(`FAILED REQUEST: ${request.method()} ${request.url()} - ${request.failure().errorText}`);
  });

  page.on('response', response => {
    if (response.status() >= 500) {
      networkErrors.push(`5XX ERROR: ${response.status()} ${response.url()}`);
    }
  });

  try {
    console.log('Loading http://localhost:5182...\n');
    await page.goto('http://localhost:5182', { waitUntil: 'networkidle', timeout: 30000 });
    
    await page.waitForTimeout(2000);
    const title = await page.title();
    console.log(`Page loaded. Title: ${title}\n`);

  } catch (e) {
    errors.push(`NAVIGATION ERROR: ${e.message}`);
  }

  await page.close();
  await context.close();
  await browser.close();

  console.log('=== ERRORS ===');
  if (errors.length === 0) {
    console.log('(none)');
  } else {
    errors.forEach((e, i) => console.log(`${i + 1}. ${e}`));
  }

  console.log('\n=== WARNINGS ===');
  if (warnings.length === 0) {
    console.log('(none)');
  } else {
    warnings.slice(0, 20).forEach((w, i) => console.log(`${i + 1}. ${w}`));
    if (warnings.length > 20) console.log(`... and ${warnings.length - 20} more`);
  }

  console.log('\n=== NETWORK ERRORS ===');
  if (networkErrors.length === 0) {
    console.log('(none)');
  } else {
    networkErrors.forEach((e, i) => console.log(`${i + 1}. ${e}`));
  }
})();
