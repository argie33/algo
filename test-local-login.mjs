import puppeteer from 'puppeteer';

const CHROME_PATH = process.env.PUPPETEER_EXECUTABLE_PATH ||
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

const PROD_URL = 'http://localhost:5173';

async function testProdLogin() {
  let browser;
  try {
    console.log('🚀 Launching browser for PRODUCTION test...\n');
    browser = await puppeteer.launch({
      executablePath: CHROME_PATH,
      headless: false,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    });

    const page = await browser.newPage();
    const consoleLogs = [];
    const networkErrors = [];

    // Capture console logs
    page.on('console', (msg) => {
      const text = msg.text();
      consoleLogs.push({ type: msg.type(), text });
    });

    // Capture network errors
    page.on('response', (response) => {
      if (response.status() >= 400) {
        networkErrors.push({
          status: response.status(),
          url: response.url(),
        });
      }
    });

    console.log(`📱 STEP 1: Navigate to production login page`);
    console.log(`   URL: ${PROD_URL}/login\n`);
    try {
      await page.goto(`${PROD_URL}/login`, { waitUntil: 'domcontentloaded', timeout: 20000 });
      console.log('   ✅ Page loaded');
    } catch (e) {
      console.log(`   ⚠️ Navigation timeout: ${e.message}`);
    }

    console.log('\n⏳ Waiting for React to render (3 seconds)...');
    await new Promise(resolve => setTimeout(resolve, 3000));

    console.log('\n🔍 STEP 2: Check for login form...');
    const usernameInput = await page.$('input[name="username"]');
    const passwordInput = await page.$('input[name="password"]');

    if (!usernameInput || !passwordInput) {
      console.log('❌ Login form NOT found');
      const pageInfo = await page.evaluate(() => ({
        url: window.location.href,
        title: document.title,
        inputs: document.querySelectorAll('input').length,
      }));
      console.log('Page info:', pageInfo);
      return;
    }

    console.log('✅ Login form found!');

    console.log('\n✍️ STEP 3: Submit credentials (dev-admin / Admin123!)');
    await page.type('input[name="username"]', 'dev-admin', { delay: 50 });
    console.log('   ✓ Username entered');

    await page.type('input[name="password"]', 'Admin123!', { delay: 50 });
    console.log('   ✓ Password entered');

    const submitBtn = await page.$('button[type="submit"]');
    if (!submitBtn) {
      console.log('❌ Submit button not found');
      return;
    }

    await submitBtn.click();
    console.log('   ✓ Form submitted');

    console.log('\n⏳ Waiting for authentication (5 seconds)...');
    await new Promise(resolve => setTimeout(resolve, 5000));

    const finalUrl = page.url();
    console.log(`\n📍 Final URL: ${finalUrl}`);

    // Analysis
    const isLoggedIn = !finalUrl.includes('/login');
    const authErrors = consoleLogs.filter(l =>
      l.type === 'error' && (l.text.includes('auth') || l.text.includes('Cognito'))
    );
    const criticalErrors = networkErrors.filter(n => n.status >= 500);

    console.log('\n=== PRODUCTION TEST RESULTS ===\n');
    console.log(`🔐 Authentication:`);
    console.log(`   ${isLoggedIn ? '✅' : '❌'} Logged in: ${isLoggedIn}`);
    console.log(`   URL: ${finalUrl}`);

    console.log(`\n⚠️ Errors:`);
    console.log(`   ${authErrors.length === 0 ? '✅' : '❌'} Auth errors: ${authErrors.length}`);
    console.log(`   ${criticalErrors.length === 0 ? '✅' : '❌'} Network errors (500+): ${criticalErrors.length}`);

    if (authErrors.length > 0) {
      authErrors.slice(0, 3).forEach(e => console.log(`     - ${e.text.substring(0, 80)}`));
    }
    if (criticalErrors.length > 0) {
      criticalErrors.slice(0, 3).forEach(e => console.log(`     - ${e.status} ${e.url}`));
    }

    console.log(`\n=== VERDICT ===`);
    if (isLoggedIn && authErrors.length === 0 && criticalErrors.length === 0) {
      console.log('✅ ✅ ✅ PRODUCTION LOGIN SUCCESSFUL - NO ERRORS!');
      console.log(`User authenticated at: ${finalUrl}`);
    } else if (isLoggedIn) {
      console.log('⚠️ Logged in but with errors');
    } else {
      console.log('❌ Login failed - still on login page');
    }

  } catch (error) {
    console.error('❌ Test error:', error.message);
  } finally {
    if (browser) {
      console.log('\nClosing browser...');
      await browser.close();
    }
  }
}

testProdLogin();
