import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();

  const consoleLogs = { errors: [], warnings: [], logs: [] };
  const page = await context.newPage();

  page.on('console', msg => {
    const type = msg.type();
    const text = msg.text();
    console.log(`[${type.toUpperCase()}] ${text}`);
    if (type === 'error') consoleLogs.errors.push(text);
    else if (type === 'warning') consoleLogs.warnings.push(text);
    else if (type === 'log') consoleLogs.logs.push(text);
  });

  page.on('pageerror', error => {
    console.error(`[PAGE_ERROR] ${error.message}`);
    consoleLogs.errors.push(`PAGE_ERROR: ${error.message}`);
  });

  try {
    console.log('=== AWS PRODUCTION VERIFICATION ===\n');

    // Step 1: Load AWS landing page
    console.log('Step 1: Navigate to https://d5j1h4wzrkvw7.cloudfront.net...');
    await page.goto('https://d5j1h4wzrkvw7.cloudfront.net', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);

    console.log(`✅ AWS landing page loaded\n`);
    console.log(`📊 Console errors on landing: ${consoleLogs.errors.length}`);
    console.log(`⚠️  Console warnings on landing: ${consoleLogs.warnings.length}\n`);

    // Step 2: Check API connectivity
    console.log('Step 2: Testing API endpoint connectivity...');
    try {
      const healthResponse = await page.evaluate(async () => {
        const res = await fetch('https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health');
        return { status: res.status, ok: res.ok, text: await res.text() };
      });
      console.log(`✅ API health endpoint: ${healthResponse.status} ${healthResponse.ok ? '(OK)' : '(FAILED)'}`);
    } catch (err) {
      console.log(`⚠️  API health check: ${err.message}`);
    }

    // Step 3: Attempt login
    console.log('\nStep 3: Attempting login with dev-admin / Admin123!...');
    const userInput = await page.locator('input[name="username"], input[placeholder*="email" i], input[placeholder*="user" i]').first();
    const passInput = await page.locator('input[type="password"]').first();
    const submitBtn = await page.locator('button[type="submit"], button:has-text("Sign"), button:has-text("Log")').first();

    if (await userInput.isVisible().catch(() => false)) {
      await userInput.fill('dev-admin');
      console.log('✅ Filled username: dev-admin');
    }

    if (await passInput.isVisible().catch(() => false)) {
      await passInput.fill('Admin123!');
      console.log('✅ Filled password');
    }

    if (await submitBtn.isVisible().catch(() => false)) {
      await submitBtn.click();
      console.log('✅ Clicked login button');
      await page.waitForTimeout(4000);
    }

    console.log(`\n📊 Console errors after login: ${consoleLogs.errors.length}`);
    console.log(`⚠️  Console warnings after login: ${consoleLogs.warnings.length}\n`);

    // Final Report
    console.log('=== AWS VERIFICATION RESULTS ===\n');
    console.log(`✅ Frontend loads successfully at https://d5j1h4wzrkvw7.cloudfront.net`);
    console.log(`${consoleLogs.errors.length === 0 ? '✅' : '❌'} F12 CONSOLE ERRORS: ${consoleLogs.errors.length}`);

    if (consoleLogs.errors.length > 0) {
      console.log('\n   Error Details:');
      consoleLogs.errors.forEach((err, i) => console.log(`   ${i + 1}. ${err}`));
    }

    console.log(`${consoleLogs.warnings.length === 0 ? '✅' : '⚠️'} F12 CONSOLE WARNINGS: ${consoleLogs.warnings.length}`);

    if (consoleLogs.warnings.length > 0 && consoleLogs.warnings.length <= 5) {
      console.log('\n   Warning Details:');
      consoleLogs.warnings.forEach((warn, i) => console.log(`   ${i + 1}. ${warn}`));
    }

    console.log(`\n${'='.repeat(40)}`);
    console.log(`GOAL STATUS: ${consoleLogs.errors.length === 0 ? '✅ PASSED' : '❌ FAILED'}`);
    console.log(`${'='.repeat(40)}`);

    await browser.close();

  } catch (error) {
    console.error('\n❌ Verification failed:', error.message);
    await browser.close();
  }
})();
