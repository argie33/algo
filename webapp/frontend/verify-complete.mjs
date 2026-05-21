import { chromium } from 'playwright';

async function testEnvironment(url, name) {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const consoleLogs = { errors: [], warnings: [] };
  const page = await context.newPage();

  page.on('console', msg => {
    const type = msg.type();
    if (type === 'error') consoleLogs.errors.push(msg.text());
    else if (type === 'warning') consoleLogs.warnings.push(msg.text());
  });

  page.on('pageerror', error => {
    consoleLogs.errors.push(`PAGE_ERROR: ${error.message}`);
  });

  try {
    console.log(`\n${'='.repeat(50)}`);
    console.log(`Testing: ${name} at ${url}`);
    console.log('='.repeat(50));

    // Load page
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);

    console.log(`✅ Page loaded`);
    console.log(`📊 F12 Console errors: ${consoleLogs.errors.length}`);
    console.log(`⚠️  F12 Console warnings: ${consoleLogs.warnings.length}`);

    if (consoleLogs.errors.length > 0) {
      console.log('\nError details:');
      consoleLogs.errors.slice(0, 3).forEach((err, i) => {
        console.log(`  ${i + 1}. ${err.substring(0, 100)}...`);
      });
    }

    // Test API connectivity
    try {
      const health = await page.evaluate(async () => {
        const path = window.location.hostname === 'localhost' ?
          'http://localhost:3002/api/health' :
          'https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health';
        const res = await fetch(path);
        return { status: res.status, ok: res.ok };
      });
      console.log(`✅ API health: ${health.status} ${health.ok ? '(OK)' : '(FAILED)'}`);
    } catch (err) {
      console.log(`⚠️  API health check: ${err.message}`);
    }

    await browser.close();

    console.log(`\n${consoleLogs.errors.length === 0 ? '✅' : '❌'} RESULT: ${consoleLogs.errors.length === 0 ? 'PASSED' : 'FAILED'}`);
    return { name, url, errors: consoleLogs.errors.length, warnings: consoleLogs.warnings.length };
  } catch (error) {
    console.error(`❌ Error: ${error.message}`);
    await browser.close();
    return { name, url, errors: -1, warnings: -1, failed: true };
  }
}

(async () => {
  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║     COMPLETE SITE VERIFICATION - LOCAL + AWS PRODUCTION     ║');
  console.log('╚════════════════════════════════════════════════════════════╝');

  const results = [];

  // Test local environment
  results.push(await testEnvironment('http://localhost:5174', 'LOCAL DEV'));

  // Test AWS production
  results.push(await testEnvironment('https://d5j1h4wzrkvw7.cloudfront.net', 'AWS PRODUCTION'));

  // Summary
  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║                    FINAL RESULTS SUMMARY                    ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  results.forEach(r => {
    const status = r.errors === 0 ? '✅ PASS' : '❌ FAIL';
    console.log(`${status} ${r.name.padEnd(20)} → ${r.errors} errors, ${r.warnings} warnings`);
  });

  const allPass = results.every(r => r.errors === 0);
  console.log(`\n${'═'.repeat(50)}`);
  console.log(`${allPass ? '✅ GOAL ACHIEVED' : '❌ GOAL NOT MET'}: ${allPass ? 'All environments clean' : 'Some environments have errors'}`);
  console.log('═'.repeat(50) + '\n');

  process.exit(allPass ? 0 : 1);
})();
