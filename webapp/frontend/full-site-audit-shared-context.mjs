import { chromium } from 'playwright';

async function testAllPagesWithSharedContext() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const pages = [
    { url: 'http://localhost:5174', name: 'Landing' },
    { url: 'http://localhost:5174/dashboard', name: 'Dashboard' },
    { url: 'http://localhost:5174/backtest', name: 'Backtest' },
    { url: 'http://localhost:5174/portfolio', name: 'Portfolio' },
    { url: 'http://localhost:5174/signals', name: 'Signals' },
    { url: 'http://localhost:5174/trades', name: 'Trades' },
    { url: 'http://localhost:5174/settings', name: 'Settings' },
    { url: 'http://localhost:5174/admin', name: 'Admin' },
  ];

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║   FULL-SITE AUDIT (SHARED CONTEXT - LOGIN PERSISTS)      ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  const results = [];

  // LOGIN FIRST using shared context
  console.log('🔐 Logging in as dev-admin...');
  const loginPage = await context.newPage();
  const globalLogs = { errors: [], warnings: [] };

  loginPage.on('console', msg => {
    if (msg.type() === 'error') globalLogs.errors.push(`[LOGIN] ${msg.text()}`);
  });

  try {
    await loginPage.goto('http://localhost:5174', { waitUntil: 'networkidle', timeout: 10000 });
    await loginPage.waitForTimeout(1500);

    // Try to find login button
    const buttons = await loginPage.$$('button');
    let foundLoginButton = false;
    for (const btn of buttons) {
      const text = await btn.textContent();
      if (text && (text.toLowerCase().includes('login') || text.toLowerCase().includes('sign in'))) {
        await btn.click();
        foundLoginButton = true;
        await loginPage.waitForTimeout(1500);
        break;
      }
    }

    // Try to find and fill email/username input
    const inputs = await loginPage.$$('input');
    if (inputs.length >= 1) {
      await inputs[0].fill('dev-admin');
      await loginPage.waitForTimeout(300);
    }
    
    // Try to find and fill password input
    if (inputs.length >= 2) {
      await inputs[1].fill('Admin123!');
      await loginPage.waitForTimeout(300);
    }

    // Click submit
    const submitBtn = await loginPage.$('button[type="submit"]');
    if (submitBtn) {
      await submitBtn.click();
      await loginPage.waitForTimeout(2000);
    }

    console.log('✅ Login page processed\n');
  } catch (e) {
    console.log(`⚠️  Login: ${e.message}\n`);
  }

  await loginPage.close();

  // Test all pages with shared context (sessionStorage persists)
  for (const page of pages) {
    const pageObj = await context.newPage();
    const logs = { errors: [], warnings: [], networkErrors: [] };

    pageObj.on('console', msg => {
      const type = msg.type();
      const text = msg.text();
      if (type === 'error') logs.errors.push(text);
      if (type === 'warning') logs.warnings.push(text);
    });

    pageObj.on('pageerror', err => {
      logs.errors.push(`PAGE_ERROR: ${err.message}`);
    });

    pageObj.on('requestfailed', req => {
      logs.networkErrors.push(`${req.method()} ${req.url()}: ${req.failure().errorText}`);
    });

    try {
      await pageObj.goto(page.url, { waitUntil: 'networkidle', timeout: 15000 });
      await pageObj.waitForTimeout(1500);

      const status = logs.errors.length === 0 ? '✅' : '❌';
      console.log(`${status} ${page.name.padEnd(15)} → Errors: ${logs.errors.length}, Warnings: ${logs.warnings.length}, Network: ${logs.networkErrors.length}`);

      if (logs.errors.length > 0) {
        logs.errors.slice(0, 2).forEach(e => console.log(`     ERROR: ${e.substring(0, 85)}`));
      }
      if (logs.networkErrors.length > 0) {
        logs.networkErrors.slice(0, 1).forEach(e => console.log(`     NETWORK: ${e.substring(0, 85)}`));
      }

      results.push({ page: page.name, ...logs });
    } catch (e) {
      console.log(`❌ ${page.name.padEnd(15)} → FAILED: ${e.message}`);
      results.push({ page: page.name, failed: true, error: e.message });
    }

    await pageObj.close();
  }

  const totalErrors = results.reduce((sum, r) => sum + r.errors.length, 0);
  const totalWarnings = results.reduce((sum, r) => sum + r.warnings.length, 0);
  const totalNetwork = results.reduce((sum, r) => sum + r.networkErrors.length, 0);
  const totalIssues = totalErrors + totalWarnings + totalNetwork;

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log(`║  TOTAL: ${totalErrors} errors, ${totalWarnings} warnings, ${totalNetwork} network ║`);
  if (totalIssues === 0) {
    console.log('║          ✅ ALL ENVIRONMENTS CLEAN                          ║');
  } else {
    console.log(`║  ISSUES: ${totalIssues} issues found                               ║`);
  }
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  await context.close();
  await browser.close();
  process.exit(totalIssues > 0 ? 1 : 0);
}

testAllPagesWithSharedContext();
