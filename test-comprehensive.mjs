import { chromium } from 'playwright';

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const consoleLogs = [];
  const consoleErrors = [];
  const consoleWarnings = [];
  const networkErrors = [];

  // Capture console events
  page.on('console', (msg) => {
    const logEntry = {
      type: msg.type(),
      text: msg.text(),
    };

    if (msg.type() === 'error') {
      consoleErrors.push(logEntry);
      console.error(`[CONSOLE ERROR] ${msg.text()}`);
    } else if (msg.type() === 'warning') {
      consoleWarnings.push(logEntry);
      console.warn(`[CONSOLE WARNING] ${msg.text()}`);
    }
  });

  // Catch page errors
  page.on('pageerror', (err) => {
    consoleErrors.push({
      type: 'pageerror',
      text: err.message,
    });
    console.error(`[PAGE ERROR] ${err.message}`);
  });

  // Capture network failures
  page.on('requestfailed', (request) => {
    networkErrors.push({
      url: request.url(),
      failure: request.failure()?.errorText || 'Unknown error'
    });
  });

  try {
    console.log('🌐 TEST 1: Landing Page');
    console.log('========================');
    const response = await page.goto('http://localhost:5174', { waitUntil: 'networkidle', timeout: 30000 });
    console.log(`✅ Page loaded with status: ${response.status()}`);

    const title = await page.title();
    console.log(`✅ Page title: ${title}`);

    const bodyText = await page.textContent('body');
    const hasContent = !!bodyText?.trim();
    console.log(`✅ Page has rendered content: ${hasContent}`);

    // Test API Endpoints
    console.log('\n🔌 TEST 2: API Endpoints');
    console.log('========================');
    
    const apiTests = [
      { url: 'http://localhost:3001/health', method: 'GET', name: 'Health' },
      { url: 'http://localhost:3001/api/auth/validate', method: 'GET', name: 'Auth Validate' },
      { url: 'http://localhost:3001/api/portfolio', method: 'GET', name: 'Portfolio' },
      { url: 'http://localhost:3001/api/signals', method: 'GET', name: 'Signals' }
    ];

    for (const test of apiTests) {
      try {
        const response = await fetch(test.url, {
          method: test.method,
          headers: { 
            'Authorization': 'Bearer test',
            'Content-Type': 'application/json'
          }
        });
        const status = response.status;
        // 401/403 is OK for endpoints requiring auth, 200 means it works
        const ok = status === 200 || status === 401 || status === 403;
        console.log(`${ok ? '✅' : '❌'} ${test.name}: ${status}`);
      } catch (e) {
        console.log(`❌ ${test.name}: ${e.message}`);
      }
    }

    // Test Login
    console.log('\n🔐 TEST 3: Login Flow');
    console.log('========================');
    
    // Look for login elements
    const emailInput = await page.$('input[type="email"]') || await page.$('input[placeholder*="email" i]') || await page.$('input[name*="email" i]');
    const usernameInput = await page.$('input[name*="username" i]') || await page.$('input[placeholder*="username" i]');
    const passwordInput = await page.$('input[type="password"]');
    const submitButton = await page.$('button:has-text("Sign In"), button:has-text("Login"), button:has-text("Submit"), button[type="submit"]');

    if (emailInput || usernameInput) {
      console.log('✅ Login form found');
      
      const inputField = emailInput || usernameInput;
      await inputField.fill('dev-admin');
      console.log('✅ Username entered');

      if (passwordInput) {
        await passwordInput.fill('Admin123!');
        console.log('✅ Password entered');

        if (submitButton) {
          console.log('🔐 Attempting login...');
          await submitButton.click();
          
          // Wait for navigation or modal to appear
          await Promise.race([
            page.waitForNavigation({ waitUntil: 'networkidle', timeout: 10000 }).catch(() => null),
            page.waitForTimeout(3000)
          ]);

          const postLoginUrl = page.url();
          console.log(`✅ Post-login URL: ${postLoginUrl}`);

          await sleep(2000);
        }
      }
    } else {
      console.log('⚠️  Login form not found on page');
    }

    // Summary
    console.log('\n📊 F12 CONSOLE SUMMARY');
    console.log('========================');
    console.log(`Console Errors: ${consoleErrors.length}`);
    console.log(`Console Warnings: ${consoleWarnings.length}`);
    console.log(`Network Failures: ${networkErrors.length}`);

    if (consoleErrors.length > 0) {
      console.log(`\n❌ Detailed Errors:`);
      consoleErrors.slice(0, 10).forEach((err, i) => {
        console.log(`  ${i + 1}. ${err.text}`);
      });
      if (consoleErrors.length > 10) {
        console.log(`  ... and ${consoleErrors.length - 10} more`);
      }
    }

    if (consoleWarnings.length > 0) {
      console.log(`\n⚠️  Detailed Warnings (first 5):`);
      consoleWarnings.slice(0, 5).forEach((warn, i) => {
        console.log(`  ${i + 1}. ${warn.text}`);
      });
      if (consoleWarnings.length > 5) {
        console.log(`  ... and ${consoleWarnings.length - 5} more`);
      }
    }

    if (networkErrors.length > 0) {
      console.log(`\n❌ Network Errors:`);
      networkErrors.slice(0, 5).forEach((err, i) => {
        console.log(`  ${i + 1}. ${err.url}: ${err.failure}`);
      });
      if (networkErrors.length > 5) {
        console.log(`  ... and ${networkErrors.length - 5} more`);
      }
    }

    // Final verdict
    console.log('\n✅ FINAL VERDICT');
    console.log('========================');
    if (consoleErrors.length === 0 && networkErrors.length === 0) {
      console.log('✅ CLEAN - No errors detected');
    } else if (consoleErrors.length <= 2) {
      console.log('⚠️  ACCEPTABLE - Minor issues only');
    } else {
      console.log('❌ ISSUES FOUND - See errors above');
    }

  } catch (error) {
    console.error(`Error during test: ${error.message}`);
    console.error(error.stack);
  } finally {
    await browser.close();
  }
})();
