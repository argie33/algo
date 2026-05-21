import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: false });
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
    console.log('=== LOCAL FRONTEND F12 VERIFICATION ===\n');

    // Step 1: Load landing page
    console.log('Step 1: Navigate to http://localhost:5174...');
    await page.goto('http://localhost:5174', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);

    console.log(`✅ Landing page loaded\n`);
    console.log(`📊 Console errors on landing: ${consoleLogs.errors.length}`);
    console.log(`⚠️  Console warnings on landing: ${consoleLogs.warnings.length}\n`);

    // Step 2: Check login form
    console.log('Step 2: Checking login form...');
    const inputs = await page.locator('input').count();
    console.log(`✅ Found ${inputs} input fields\n`);

    // Step 3: Attempt login
    console.log('Step 3: Attempting login...');
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

    // Step 4: Navigate to dashboard
    console.log('Step 4: Checking dashboard...');
    const dashboardElements = await page.locator('[class*="dashboard"], [class*="content"], main').count();
    console.log(`✅ Found ${dashboardElements} dashboard elements\n`);

    // Final Report
    console.log('=== VERIFICATION RESULTS ===\n');
    console.log(`✅ Frontend loads successfully at http://localhost:5174`);
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

    console.log(`\n👀 Browser remains open - inspect manually if needed. Close when done.`);

  } catch (error) {
    console.error('\n❌ Verification failed:', error.message);
    await browser.close();
  }
})();
