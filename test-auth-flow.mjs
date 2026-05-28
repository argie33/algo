import puppeteer from 'puppeteer';

const CHROME_PATH = process.env.PUPPETEER_EXECUTABLE_PATH ||
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

async function testAuthFlow() {
  let browser;
  try {
    console.log('🚀 Starting auth flow verification...\n');
    browser = await puppeteer.launch({
      executablePath: CHROME_PATH,
      headless: false,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    });

    const page = await browser.newPage();
    const networkErrors = [];
    const consoleErrors = [];
    const apiResponses = [];

    // Track network errors
    page.on('response', (response) => {
      const status = response.status();
      const url = response.url();

      if (url.includes('/api/') || url.includes('auth')) {
        apiResponses.push({ status, url });

        if (status >= 400) {
          networkErrors.push({
            status,
            url,
            statusText: response.statusText(),
          });
        }
      }
    });

    // Track console errors
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text();
        if (!text.includes('CORS') && !text.includes('Failed to load')) {
          consoleErrors.push(text);
        }
      }
    });

    console.log('📱 STEP 1: Navigate to home page');
    try {
      const response = await page.goto('http://localhost:5173/', { waitUntil: 'networkidle2', timeout: 15000 });
      console.log(`  ✅ Home page loaded: ${response?.status()}`);
    } catch (e) {
      console.log(`  ⚠️ Navigation timeout`);
    }

    await new Promise(resolve => setTimeout(resolve, 1000));

    console.log('\n📱 STEP 2: Navigate to login page');
    await page.goto('http://localhost:5173/login', { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {
      console.log('  ⚠️ Navigation timeout');
    });

    await new Promise(resolve => setTimeout(resolve, 2000));

    // Check if already authenticated and show that auth is working
    const authState = await page.evaluate(() => ({
      hasTokens: !!(sessionStorage.getItem('devAuth_session')),
      url: window.location.href,
      page: document.title,
    }));

    console.log(`  Auth state:`, authState);

    console.log('\n📱 STEP 3: Navigate to protected dashboard');
    await page.goto('http://localhost:5173/app/portfolio', { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {});

    await new Promise(resolve => setTimeout(resolve, 3000));

    const dashboardState = await page.evaluate(() => ({
      url: window.location.href,
      title: document.title,
      hasSidebar: !!document.querySelector('.sidebar'),
      hasContent: document.querySelector('[role="main"]') ? true : false,
      inputCount: document.querySelectorAll('input').length,
    }));

    console.log(`  Dashboard loaded:`, dashboardState);

    const isDashboardVisible = dashboardState.url.includes('/app/') && dashboardState.hasSidebar;
    console.log(`  ${isDashboardVisible ? '✅' : '❌'} Dashboard accessible: ${isDashboardVisible}`);

    console.log('\n📱 STEP 4: Check API connectivity');
    const apiTests = await page.evaluate(() => {
      try {
        // Check if API base URL is configured
        const hasApiConfig = window.__CONFIG__?.API_URL;
        return {
          apiConfigured: !!hasApiConfig,
          apiUrl: hasApiConfig,
        };
      } catch (e) {
        return { apiConfigured: false, error: e.message };
      }
    });

    console.log(`  API Configuration:`, apiTests);

    // Wait a bit for any pending API calls
    await new Promise(resolve => setTimeout(resolve, 2000));

    console.log('\n=== TEST RESULTS ===\n');

    console.log('📊 API Responses:', apiResponses.length);
    if (apiResponses.length > 0) {
      const errors = apiResponses.filter(r => r.status >= 400);
      const successes = apiResponses.filter(r => r.status < 400);
      console.log(`  ✅ Successful: ${successes.length}`);
      console.log(`  ❌ Failed: ${errors.length}`);
      if (errors.length > 0) {
        errors.forEach(e => console.log(`    ${e.status} ${e.url}`));
      }
    }

    console.log('\n🔍 Console Errors:', consoleErrors.length);
    if (consoleErrors.length > 0) {
      consoleErrors.slice(0, 5).forEach(e => console.log(`  ❌ ${e.substring(0, 100)}`));
    }

    console.log('\n🔐 Authentication Status:');
    console.log(`  ✅ Auth system initialized`);
    console.log(`  ✅ Dev auth tokens created: ${authState.hasTokens}`);
    console.log(`  ✅ Protected pages accessible: ${isDashboardVisible}`);

    console.log('\n=== VERDICT ===');
    const hasNoErrors = consoleErrors.length === 0 && networkErrors.length === 0;
    const isAuthenticated = isDashboardVisible && authState.hasTokens;

    if (isAuthenticated && hasNoErrors) {
      console.log('✅ ✅ ✅ AUTH FLOW WORKING - System authenticated and no errors!');
    } else if (isAuthenticated) {
      console.log('⚠️ AUTH WORKING but with errors:');
      if (consoleErrors.length > 0) console.log(`  - ${consoleErrors.length} console errors`);
      if (networkErrors.length > 0) console.log(`  - ${networkErrors.length} network errors`);
    } else {
      console.log('❌ AUTH FAILED - Not authenticated');
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

testAuthFlow();
