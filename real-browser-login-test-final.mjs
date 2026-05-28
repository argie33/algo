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

    console.log('📂 Creating incognito context (fresh session)...');
    const context = await browser.createIncognitoBrowserContext();
    const page = await context.newPage();

    const consoleLogs = [];
    const authLogs = [];

    // Capture console logs
    page.on('console', (msg) => {
      const text = msg.text();
      consoleLogs.push({ type: msg.type(), text });

      // Log auth-related messages separately
      if (text.includes('auth') || text.includes('login') || text.includes('Cognito')) {
        authLogs.push({ type: msg.type(), text });
      }
    });

    console.log('📱 Navigating to login page...');
    try {
      await page.goto('http://localhost:5173/login', { waitUntil: 'domcontentloaded', timeout: 15000 });
    } catch (e) {
      console.log('⚠️ Navigation warning:', e.message.substring(0, 50));
    }

    console.log('⏳ Waiting for React to render (3 seconds)...');
    await new Promise(resolve => setTimeout(resolve, 3000));

    // Check for form
    console.log('🔍 Looking for login form...');
    const usernameInput = await page.$('input[name="username"]');
    const passwordInput = await page.$('input[name="password"]');

    if (!usernameInput || !passwordInput) {
      console.log('❌ Form not found');
      const info = await page.evaluate(() => ({
        url: window.location.href,
        inputCount: document.querySelectorAll('input').length,
        textContent: document.body.innerText.substring(0, 300),
      }));
      console.log('Page info:', JSON.stringify(info, null, 2));
      return;
    }

    console.log('✅ Login form found!');

    // Click on username field first to ensure focus
    await page.click('input[name="username"]');
    console.log('✍️  Typing username (dev-admin)...');
    await page.type('input[name="username"]', 'dev-admin', { delay: 50 });

    // Click on password field
    await page.click('input[name="password"]');
    console.log('✍️  Typing password (Admin123!)...');
    await page.type('input[name="password"]', 'Admin123!', { delay: 50 });

    console.log('🔐 Clicking submit button...');
    const submitBtn = await page.$('button[type="submit"]');
    if (!submitBtn) {
      console.log('❌ Submit button not found');
      return;
    }
    await submitBtn.click();

    console.log('⏳ Waiting for auth to complete (5 seconds)...');
    await new Promise(resolve => setTimeout(resolve, 5000));

    const finalUrl = page.url();
    console.log(`\n📍 Final URL: ${finalUrl}`);

    // Analyze results
    console.log('\n=== LOGIN TEST RESULTS ===\n');

    const isLoggedIn = !finalUrl.includes('/login');
    const hasErrors = authLogs.filter(l => l.type === 'error').length > 0;

    console.log(`Authentication:`);
    console.log(`  ${isLoggedIn ? '✅' : '❌'} Logged in (URL changed): ${isLoggedIn}`);
    console.log(`  📍 Redirected to: ${finalUrl}`);

    console.log(`\nConsole logs:`);
    console.log(`  ℹ️ Total logs: ${consoleLogs.length}`);
    console.log(`  Auth-related logs: ${authLogs.length}`);

    if (authLogs.length > 0) {
      console.log(`\n  Auth logs:`);
      authLogs.forEach(log => {
        const icon = log.type === 'error' ? '❌' : '✅';
        console.log(`    ${icon} [${log.type}] ${log.text.substring(0, 80)}`);
      });
    }

    const errorLogs = consoleLogs.filter(l => l.type === 'error');
    if (errorLogs.length > 0) {
      console.log(`\n  All errors (${errorLogs.length}):`);
      errorLogs.forEach(log => {
        console.log(`    ❌ ${log.text.substring(0, 80)}`);
      });
    }

    console.log(`\n=== VERDICT ===`);
    if (isLoggedIn && !hasErrors) {
      console.log('✅ ✅ ✅ LOGIN SUCCESSFUL - No errors, authentication working!');
    } else if (isLoggedIn) {
      console.log('⚠️ PARTIAL - Logged in but with console errors');
    } else {
      console.log('❌ LOGIN FAILED - Still on login page');
    }

  } catch (error) {
    console.error('❌ Test crashed:', error.message);
  } finally {
    if (browser) {
      console.log('\nClosing browser...');
      await browser.close();
    }
  }
}

testLogin();
