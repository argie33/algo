const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const errors = [];
  const warnings = [];
  const apiErrors = [];
  const failedRequests = [];
  const allRequests = [];
  let consoleMessages = [];

  page.on('console', msg => {
    const text = msg.text();
    consoleMessages.push({
      type: msg.type(),
      text: text,
      location: msg.location()
    });
    if (msg.type() === 'error') {
      errors.push({ text, location: msg.location() });
    } else if (msg.type() === 'warning') {
      warnings.push(text);
    }
  });

  page.on('response', response => {
    const url = response.url();
    const status = response.status();
    allRequests.push({ url, status });
    
    if (status >= 400) {
      apiErrors.push({
        url: url.substring(0, 100),
        status: status,
        statusText: response.statusText()
      });
    }
  });

  page.on('requestfailed', request => {
    failedRequests.push({
      url: request.url(),
      failure: request.failure().errorText
    });
  });

  const routes = [
    'https://d2u93283nn45h2.cloudfront.net/app/dashboard',
    'https://d2u93283nn45h2.cloudfront.net/app/trading-signals',
    'https://d2u93283nn45h2.cloudfront.net/app/scores',
    'https://d2u93283nn45h2.cloudfront.net/app/portfolio',
    'https://d2u93283nn45h2.cloudfront.net/app/market-health'
  ];

  for (const route of routes) {
    console.log(`\n>>> Checking ${route.split('/').pop()}...`);
    try {
      await page.goto(route, { 
        waitUntil: 'networkidle', 
        timeout: 30000 
      }).catch(e => console.log(`Timeout/Error: ${e.message}`));
      await page.waitForTimeout(2000);
    } catch (e) {
      console.log(`Navigation error: ${e.message}`);
    }
  }

  console.log('\n════════════════════════════════════════════════════');
  console.log('PRODUCTION SITE ERROR REPORT');
  console.log('════════════════════════════════════════════════════\n');

  console.log('🔴 JAVASCRIPT ERRORS:');
  if (errors.length > 0) {
    errors.forEach((e, i) => {
      console.log(`  ${i+1}. ${e.text.substring(0, 120)}`);
      if (e.location) console.log(`     at ${e.location.url}:${e.location.lineNumber}`);
    });
  } else {
    console.log('  None detected');
  }

  console.log('\n⚠️  CONSOLE WARNINGS:');
  if (warnings.length > 0) {
    console.log(`  Total: ${warnings.length}`);
    warnings.slice(0, 5).forEach((w, i) => {
      console.log(`  ${i+1}. ${w.substring(0, 100)}`);
    });
    if (warnings.length > 5) console.log(`  ... and ${warnings.length - 5} more`);
  } else {
    console.log('  None detected');
  }

  console.log('\n❌ HTTP ERRORS (4xx/5xx):');
  if (apiErrors.length > 0) {
    console.log(`  Total: ${apiErrors.length}`);
    apiErrors.forEach(e => {
      console.log(`  ${e.status} ${e.statusText}: ${e.url}`);
    });
  } else {
    console.log('  None detected');
  }

  console.log('\n📡 FAILED NETWORK REQUESTS:');
  if (failedRequests.length > 0) {
    console.log(`  Total: ${failedRequests.length}`);
    failedRequests.forEach(f => {
      console.log(`  ${f.url.substring(0, 80)}`);
      console.log(`    Error: ${f.failure}`);
    });
  } else {
    console.log('  None detected');
  }

  console.log('\n📊 REQUEST STATUS SUMMARY:');
  const statusCounts = {};
  allRequests.forEach(r => {
    statusCounts[r.status] = (statusCounts[r.status] || 0) + 1;
  });
  Object.entries(statusCounts).sort((a, b) => parseInt(a[0]) - parseInt(b[0])).forEach(([status, count]) => {
    console.log(`  ${status}: ${count} requests`);
  });

  console.log('\n📝 FULL CONSOLE MESSAGE LOG (first 30):');
  consoleMessages.slice(0, 30).forEach((m, i) => {
    console.log(`  [${m.type.toUpperCase()}] ${m.text.substring(0, 100)}`);
  });
  if (consoleMessages.length > 30) console.log(`  ... (${consoleMessages.length - 30} more messages)`);

  await browser.close();
})();
