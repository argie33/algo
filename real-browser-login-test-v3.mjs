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
    const networkRequests = [];
    const consoleLogs = [];

    // Capture network requests
    page.on('request', (request) => {
      networkRequests.push({
        method: request.method(),
        url: request.url(),
        timestamp: new Date().toISOString(),
      });
    });

    // Capture console logs (but not network ones)
    page.on('console', (msg) => {
      const text = msg.text();
      // Skip noisy network logs
      if (!text.includes('Failed to load') && !text.includes('CORS')) {
        consoleLogs.push({
          type: msg.type(),
          text: text,
          timestamp: new Date().toISOString(),
        });
      }
    });

    console.log('📱 Navigating to login page (with longer timeout)...');
    try {
      await page.goto('http://localhost:5173/login', { waitUntil: 'domcontentloaded', timeout: 15000 });
      console.log('✅ Page loaded');
    } catch (e) {
      console.log('⚠️ Navigation timeout, but continuing (page may still be loading)...');
    }

    // Give React time to render
    console.log('⏳ Waiting for React to render (3 seconds)...');
    await new Promise(resolve => setTimeout(resolve, 3000));

    console.log('🔍 Checking for email input field...');
    const emailInputExists = await page.$('input[type="email"]');
    const passwordInputExists = await page.$('input[type="password"]');

    // Try to get all inputs as fallback
    const allInputs = await page.$$('input');
    console.log(`📊 Found ${allInputs.length} input fields total`);

    if (!emailInputExists || !passwordInputExists) {
      console.log('⚠️ Standard input selectors not found, checking page structure...');
      const pageTitle = await page.title();
      const bodyContent = await page.evaluate(() => {
        const inputs = Array.from(document.querySelectorAll('input')).map(i => ({
          type: i.type,
          name: i.name,
          id: i.id,
        }));
        return {
          title: document.title,
          inputCount: document.querySelectorAll('input').length,
          inputs: inputs,
        };
      });
      console.log('📋 Page structure:', JSON.stringify(bodyContent, null, 2));
      return;
    }

    console.log('✅ Email and password inputs found');
    console.log('✍️  Typing email (dev-admin)...');
    await page.type('input[type="email"]', 'dev-admin', { delay: 50 });

    console.log('✍️  Typing password (Admin123!)...');
    await page.type('input[type="password"]', 'Admin123!', { delay: 50 });

    console.log('🔐 Submitting login form...');
    const submitBtn = await page.$('button[type="submit"]');
    if (submitBtn) {
      await submitBtn.click();
    } else {
      console.log('⚠️ No submit button, trying Enter key...');
      await page.keyboard.press('Enter');
    }

    console.log('⏳ Waiting for auth to complete (5 seconds)...');
    await new Promise(resolve => setTimeout(resolve, 5000));

    const finalUrl = page.url();
    console.log(`📍 Final URL: ${finalUrl}`);

    // Check for critical errors
    const criticalErrors = consoleLogs.filter(log =>
      log.type === 'error' || (log.type === 'warning' && log.text.includes('auth'))
    );

    console.log('\n=== TEST RESULTS ===');
    console.log(`✅ Final URL: ${finalUrl}`);
    console.log(`✅ Network requests: ${networkRequests.length}`);
    console.log(`✅ Console logs: ${consoleLogs.length}`);

    if (criticalErrors.length > 0) {
      console.log(`⚠️ Auth-related errors (${criticalErrors.length}):`);
      criticalErrors.forEach(log => console.log(`  [${log.type}] ${log.text}`));
    } else {
      console.log('✅ No critical auth errors');
    }

    // Show auth-related requests
    const authReqs = networkRequests.filter(req =>
      req.url.includes('auth') ||
      req.url.includes('signIn') ||
      req.url.includes('login') ||
      req.url.includes('cognito') ||
      req.url.includes('api/auth')
    );

    if (authReqs.length > 0) {
      console.log(`\n🔗 Auth requests (${authReqs.length}):`);
      authReqs.forEach(req => console.log(`  ${req.method} ${req.url}`));
    }

    const isLoggedIn = !finalUrl.includes('/login');
    const hasNoAuthErrors = !consoleLogs.some(log =>
      log.type === 'error' && (log.text.includes('auth') || log.text.includes('Cognito'))
    );

    console.log(`\n${isLoggedIn ? '✅' : '❌'} Navigation: ${isLoggedIn ? 'Away from login page' : 'Still on login'}`);
    console.log(`${hasNoAuthErrors ? '✅' : '⚠️'} Auth errors: ${hasNoAuthErrors ? 'None' : 'Some found'}`);

    if (isLoggedIn && hasNoAuthErrors) {
      console.log('\n🎉 LOGIN TEST PASSED - Navigated away from login with no errors!');
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

testLogin();
