import { chromium } from 'playwright';

async function testAllPagesWithLogin() {
  const browser = await chromium.launch({ headless: true });
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
  console.log('║   COMPREHENSIVE FULL-SITE AUDIT (WITH LOGIN)             ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  // Create persistent context for login state
  const context = await browser.newContext();
  const results = [];

  // LOGIN FIRST
  console.log('🔐 Logging in as dev-admin...');
  const loginPage = await context.newPage();
  const globalLogs = { errors: [], warnings: [] };

  loginPage.on('console', msg => {
    if (msg.type() === 'error') globalLogs.errors.push(`[DURING LOGIN] ${msg.text()}`);
  });

  try {
    await loginPage.goto('http://localhost:5174', { waitUntil: 'networkidle', timeout: 10000 });
    await loginPage.waitForTimeout(1000);

    // Look for login button or form
    const loginBtn = await loginPage.$('[data-testid="login-button"], button:has-text("Login"), button:has-text("Sign In")') || await loginPage.$('button');
    
    if (loginBtn) {
      await loginBtn.click();
      await loginPage.waitForTimeout(2000);
    }

    // Try to find and fill email
    const emailInputs = await loginPage.$$('[type="email"], input[placeholder*="mail"], input[placeholder*="user"]');
    if (emailInputs.length > 0) {
      await emailInputs[0].fill('dev-admin');
      await loginPage.waitForTimeout(500);
    }

    // Try to find and fill password
    const passwordInputs = await loginPage.$$('[type="password"]');
    if (passwordInputs.length > 0) {
      await passwordInputs[0].fill('Admin123!');
      await loginPage.waitForTimeout(500);
    }

    // Click submit button
    const submitBtn = await loginPage.$('button[type="submit"], button:has-text("Sign In"), button:has-text("Login")');
    if (submitBtn) {
      await submitBtn.click();
      await loginPage.waitForTimeout(3000);
    } else {
      console.log('⚠️  Could not find submit button');
    }
  } catch (e) {
    console.log(`⚠️  Login attempt: ${e.message}`);
  }

  await loginPage.close();

  // Now test all pages with logged-in state
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
  const totalIssues = totalErrors + totalWarnings + totalNetwork + (globalLogs.errors.length);

  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log(`║  TOTAL: ${totalErrors} errors, ${totalWarnings} warnings, ${totalNetwork} network, ${globalLogs.errors.length} login ║`);
  console.log(`║  ISSUES FOUND: ${totalIssues}                                            ║`);
  console.log('╚════════════════════════════════════════════════════════════╝\n');

  await context.close();
  await browser.close();
  process.exit(totalIssues > 0 ? 1 : 0);
}

testAllPagesWithLogin();
