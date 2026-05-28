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
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });

    const page = await browser.newPage();
    const networkRequests = [];
    const consoleLogs = [];
    const pageErrors = [];

    // Capture network requests
    page.on('request', (request) => {
      networkRequests.push({
        method: request.method(),
        url: request.url(),
        timestamp: new Date().toISOString(),
      });
    });

    // Capture console logs
    page.on('console', (msg) => {
      consoleLogs.push({
        type: msg.type(),
        text: msg.text(),
        timestamp: new Date().toISOString(),
      });
    });

    // Capture page errors
    page.on('error', (error) => {
      pageErrors.push({
        error: error.message,
        timestamp: new Date().toISOString(),
      });
    });

    console.log('📱 Navigating to login page...');
    await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle2' });

    console.log('⏳ Waiting for email input field (max 10 seconds)...');
    try {
      await page.waitForSelector('input[type="email"]', { timeout: 10000 });
      console.log('✅ Email input field found');
    } catch (e) {
      console.log('⚠️ Email input not found with type="email", trying alternative selector...');
      await page.waitForSelector('input', { timeout: 5000 });
      console.log('✅ Input field found');
    }

    // Get all input fields for debugging
    const inputCount = await page.evaluate(() => document.querySelectorAll('input').length);
    console.log(`📊 Found ${inputCount} input fields total`);

    const inputs = await page.evaluate(() => {
      const inputs = document.querySelectorAll('input');
      return Array.from(inputs).map((input, index) => ({
        index,
        type: input.type,
        name: input.name,
        id: input.id,
        placeholder: input.placeholder,
      }));
    });
    console.log('📋 Input fields:', JSON.stringify(inputs, null, 2));

    if (inputCount < 2) {
      console.log('❌ Expected at least 2 input fields (email + password), but found fewer');
      console.log('🔍 Page content length:', await page.content());
      return;
    }

    console.log('✍️  Typing email (dev-admin)...');
    await page.type('input[type="email"]', 'dev-admin', { delay: 50 });

    console.log('✍️  Typing password (Admin123!)...');
    await page.type('input[type="password"]', 'Admin123!', { delay: 50 });

    console.log('🔐 Submitting login form...');
    // Click the submit button
    const submitBtn = await page.$('button[type="submit"]');
    if (submitBtn) {
      await submitBtn.click();
    } else {
      console.log('⚠️ No submit button found, trying Enter key...');
      await page.keyboard.press('Enter');
    }

    console.log('⏳ Waiting for navigation after login (max 10 seconds)...');
    try {
      await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 10000 });
      console.log('✅ Navigation occurred');
    } catch (e) {
      console.log('⚠️ Navigation timeout (might be expected if page updates without reload)');
    }

    const finalUrl = page.url();
    console.log(`📍 Final URL: ${finalUrl}`);

    // Check for critical errors in console
    const criticalErrors = consoleLogs.filter(log =>
      log.type === 'error' || log.type === 'warning'
    );

    console.log('\n=== TEST RESULTS ===');
    console.log(`✅ Page navigated to: ${finalUrl}`);
    console.log(`✅ Network requests captured: ${networkRequests.length}`);
    console.log(`✅ Console messages: ${consoleLogs.length}`);

    if (criticalErrors.length > 0) {
      console.log(`⚠️ Critical errors/warnings found (${criticalErrors.length}):`);
      criticalErrors.forEach(log => console.log(`  [${log.type}] ${log.text}`));
    } else {
      console.log('✅ No critical errors/warnings in console');
    }

    // Show auth-related network requests
    const authRequests = networkRequests.filter(req =>
      req.url.includes('auth') ||
      req.url.includes('login') ||
      req.url.includes('cognito') ||
      req.url.includes('api')
    );

    if (authRequests.length > 0) {
      console.log(`\n🔗 Auth-related network requests (${authRequests.length}):`);
      authRequests.forEach(req => {
        console.log(`  ${req.method} ${req.url}`);
      });
    }

    // Determine success
    const isLoggedIn = !finalUrl.includes('/login');
    const hasNoErrors = criticalErrors.length === 0;

    console.log(`\n${isLoggedIn ? '✅' : '❌'} Login ${isLoggedIn ? 'successful' : 'may have failed'}`);
    console.log(`${hasNoErrors ? '✅' : '⚠️'} Console ${hasNoErrors ? 'clean' : 'has errors'}`);

    if (isLoggedIn && hasNoErrors) {
      console.log('\n🎉 LOGIN TEST PASSED - No errors, authentication successful!');
    }

  } catch (error) {
    console.error('❌ Test failed with error:', error.message);
  } finally {
    if (browser) {
      console.log('Closing browser...');
      await browser.close();
    }
  }
}

testLogin();
