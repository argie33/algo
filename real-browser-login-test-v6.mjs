import puppeteer from 'puppeteer';

const CHROME_PATH = process.env.PUPPETEER_EXECUTABLE_PATH ||
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

async function testLogin() {
  let browser;
  try {
    console.log('🚀 Launching browser...');
    browser = await puppeteer.launch({
      executablePath: CHROME_PATH,
      headless: false,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    });

    const page = await browser.newPage();
    const consoleLogs = [];

    // Capture console logs
    page.on('console', (msg) => {
      const text = msg.text();
      if (!text.includes('CORS') && !text.includes('Failed to load')) {
        consoleLogs.push({
          type: msg.type(),
          text: text,
        });
      }
    });

    console.log('📱 Navigating to protected route to trigger redirect...');
    try {
      // Navigate to a protected route which should redirect to login
      await page.goto('http://localhost:5173/app/portfolio', { waitUntil: 'domcontentloaded', timeout: 10000 });
    } catch (e) {
      console.log('⚠️ Navigation timeout');
    }

    // Wait for redirect to happen
    console.log('⏳ Waiting for redirect to login page (2 seconds)...');
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Check current URL
    const currentUrl = page.url();
    console.log(`📍 Current URL: ${currentUrl}`);

    // If we're still on protected route (because auto-auth succeeded), manually call signOut
    if (!currentUrl.includes('/login')) {
      console.log('⚠️ Not redirected to login (auto-auth worked). Attempting to sign out...');

      try {
        // Try to call signOut on the page context
        await page.evaluate(() => {
          // Manually clear all auth data
          sessionStorage.clear();
          localStorage.removeItem('accessToken');
          localStorage.removeItem('authToken');
          localStorage.removeItem('devAuth_session');
          localStorage.removeItem('devAuth_users');
          console.log('✅ Cleared all storage');

          // Hard reload to trigger auth check again
          window.location.href = 'http://localhost:5173/login';
        });

        console.log('⏳ Waiting for hard reload and navigation...');
        await page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {
          console.log('⚠️ Navigation timeout during reload');
        });
      } catch (e) {
        console.log('Error during sign out:', e.message);
      }
    }

    console.log('⏳ Waiting for React to render (2 seconds)...');
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Check for form inputs
    console.log('🔍 Looking for login form...');
    const usernameInput = await page.$('input[name="username"]');
    const passwordInput = await page.$('input[name="password"]');

    if (!usernameInput || !passwordInput) {
      console.log('❌ Form not found. Page structure:');
      const structure = await page.evaluate(() => ({
        url: window.location.href,
        inputCount: document.querySelectorAll('input').length,
        inputs: Array.from(document.querySelectorAll('input')).map((i, idx) => ({
          idx, type: i.type, name: i.name, id: i.id
        })),
        hasAuthModal: !!document.querySelector('[class*="auth"]') || !!document.querySelector('[class*="modal"]'),
        textContent: document.body.innerText.substring(0, 200),
      }));
      console.log('Structure:', JSON.stringify(structure, null, 2));
      return;
    }

    console.log('✅ Login form found!');

    console.log('✍️  Typing username...');
    await page.type('input[name="username"]', 'dev-admin', { delay: 50 });

    console.log('✍️  Typing password...');
    await page.type('input[name="password"]', 'Admin123!', { delay: 50 });

    console.log('🔐 Submitting form...');
    const submitBtn = await page.$('button[type="submit"]');
    if (submitBtn) {
      await submitBtn.click();
    } else {
      console.log('⚠️ No submit button found');
      return;
    }

    console.log('⏳ Waiting for auth response (5 seconds)...');
    await new Promise(resolve => setTimeout(resolve, 5000));

    const finalUrl = page.url();
    console.log(`\n📍 Final URL after login: ${finalUrl}`);

    // Check for errors
    const authErrors = consoleLogs.filter(log =>
      log.type === 'error' && (log.text.includes('auth') || log.text.includes('Cognito'))
    );

    console.log('\n=== RESULTS ===');
    const isLoggedIn = !finalUrl.includes('/login');
    const hasNoErrors = authErrors.length === 0;

    console.log(`${isLoggedIn ? '✅' : '❌'} Navigated away from login: ${isLoggedIn}`);
    console.log(`${hasNoErrors ? '✅' : '⚠️'} Auth errors: ${authErrors.length}`);

    if (authErrors.length > 0) {
      console.log('\nAuth errors found:');
      authErrors.forEach(e => console.log(`  - ${e.text}`));
    }

    console.log(`\n${(isLoggedIn && hasNoErrors) ? '🎉 LOGIN PASSED' : '❌ LOGIN FAILED'}`);

  } catch (error) {
    console.error('❌ Test error:', error.message);
  } finally {
    if (browser) {
      console.log('\nClosing browser...');
      await browser.close();
    }
  }
}

testLogin();
