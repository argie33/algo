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
    const responses = [];

    // Capture network requests
    page.on('request', (request) => {
      networkRequests.push({
        method: request.method(),
        url: request.url(),
        timestamp: new Date().toISOString(),
      });
    });

    // Capture responses
    page.on('response', (response) => {
      const url = response.url();
      if (url.includes('auth') || url.includes('login') || url.includes('api')) {
        responses.push({
          status: response.status(),
          url: url,
          timestamp: new Date().toISOString(),
        });
      }
    });

    // Capture console logs
    page.on('console', (msg) => {
      const text = msg.text();
      consoleLogs.push({
        type: msg.type(),
        text: text,
      });
    });

    console.log('📱 Navigating to login page...');
    try {
      await page.goto('http://localhost:5173/login', { waitUntil: 'domcontentloaded', timeout: 15000 });
    } catch (e) {
      console.log('⚠️ Navigation timeout, continuing...');
    }

    console.log('⏳ Waiting for React to render (3 seconds)...');
    await new Promise(resolve => setTimeout(resolve, 3000));

    // Check for inputs
    console.log('🔍 Looking for username input (name="username")...');
    const usernameExists = await page.$('input[name="username"]');
    const passwordExists = await page.$('input[name="password"]');

    if (!usernameExists || !passwordExists) {
      console.log('❌ Form inputs not found');
      console.log('📊 Checking page DOM...');
      const domInfo = await page.evaluate(() => ({
        bodyHTML: document.body.innerHTML.substring(0, 500),
        inputCount: document.querySelectorAll('input').length,
        allInputs: Array.from(document.querySelectorAll('input')).map(i => ({
          type: i.type,
          name: i.name,
          id: i.id,
          value: i.value,
        })),
      }));
      console.log('📋 DOM Info:', JSON.stringify(domInfo, null, 2));
      return;
    }

    console.log('✅ Form inputs found!');

    console.log('✍️  Entering credentials...');
    await page.type('input[name="username"]', 'dev-admin', { delay: 50 });
    console.log('✍️  Entered username: dev-admin');

    await page.type('input[name="password"]', 'Admin123!', { delay: 50 });
    console.log('✍️  Entered password: Admin123!');

    console.log('🔐 Submitting form...');
    await page.click('button[type="submit"]');

    console.log('⏳ Waiting for auth response (5 seconds)...');
    await new Promise(resolve => setTimeout(resolve, 5000));

    const finalUrl = page.url();
    console.log(`📍 Final URL: ${finalUrl}`);

    // Analyze results
    console.log('\n=== TEST RESULTS ===');

    // Check if navigated away from login
    const isLoggedIn = !finalUrl.includes('/login');
    console.log(`\n🔐 Authentication:`);
    console.log(`  ${isLoggedIn ? '✅' : '❌'} Navigated away from /login: ${isLoggedIn}`);

    // Check for auth errors
    const authErrors = consoleLogs.filter(log =>
      log.type === 'error' && (log.text.includes('auth') || log.text.includes('Cognito') || log.text.includes('signIn'))
    );

    console.log(`\n⚠️ Errors:`);
    console.log(`  ${authErrors.length === 0 ? '✅' : '❌'} Auth errors: ${authErrors.length}`);
    if (authErrors.length > 0) {
      authErrors.forEach(e => console.log(`    - ${e.text}`));
    }

    // Network activity
    const authNetworkReqs = networkRequests.filter(req =>
      req.url.includes('auth') || req.url.includes('login') || req.url.includes('cognito') || req.url.includes('/api/')
    );

    console.log(`\n🌐 Network:`);
    console.log(`  Total requests: ${networkRequests.length}`);
    console.log(`  Auth-related requests: ${authNetworkReqs.length}`);

    if (authNetworkReqs.length > 0) {
      console.log(`\n  Auth requests:`);
      authNetworkReqs.forEach(req => {
        console.log(`    ${req.method.padEnd(6)} ${req.url}`);
      });
    }

    // Show API responses
    if (responses.length > 0) {
      console.log(`\n  API responses:`);
      responses.forEach(r => {
        const statusEmoji = r.status >= 400 ? '❌' : r.status >= 300 ? '⚠️' : '✅';
        console.log(`    ${statusEmoji} ${r.status} ${r.url}`);
      });
    }

    // Final verdict
    console.log(`\n=== VERDICT ===`);
    if (isLoggedIn && authErrors.length === 0) {
      console.log('🎉 LOGIN SUCCESSFUL - Navigated away from login with no errors!');
      console.log(`✅ User should be logged in and at: ${finalUrl}`);
    } else if (isLoggedIn && authErrors.length > 0) {
      console.log('⚠️ PARTIAL SUCCESS - Navigated but with errors');
    } else {
      console.log('❌ LOGIN FAILED - Still on login page or error occurred');
    }

  } catch (error) {
    console.error('❌ Test error:', error.message);
    console.error(error.stack);
  } finally {
    if (browser) {
      console.log('\nClosing browser...');
      await browser.close();
    }
  }
}

testLogin();
