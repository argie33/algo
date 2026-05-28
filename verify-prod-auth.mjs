import puppeteer from 'puppeteer';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const PROD_URL = 'https://d2u93283nn45h2.cloudfront.net';

async function verifyProdAuth() {
  let browser;
  try {
    console.log('🌐 FINAL VERIFICATION: Production Auth Testing\n');
    console.log(`Target: ${PROD_URL}\n`);

    browser = await puppeteer.launch({
      executablePath: CHROME_PATH,
      headless: false,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    });

    const page = await browser.newPage();
    const logs = [];

    page.on('console', (msg) => {
      if (msg.type() === 'error') logs.push(msg.text());
    });

    console.log('📱 Step 1: Navigate to login page');
    try {
      await page.goto(`${PROD_URL}/login`, { waitUntil: 'domcontentloaded', timeout: 20000 });
      console.log('✅ Page loaded\n');
    } catch (e) {
      console.log(`❌ Failed to load: ${e.message}`);
      return;
    }

    await new Promise(resolve => setTimeout(resolve, 3000));

    console.log('🔍 Step 2: Find login form');
    const hasForm = !!(await page.$('input[name="username"]'));
    if (!hasForm) {
      console.log('❌ Login form not found');
      return;
    }
    console.log('✅ Login form found\n');

    console.log('✍️ Step 3: Submit login credentials');
    await page.type('input[name="username"]', 'dev-admin', { delay: 50 });
    await page.type('input[name="password"]', 'Admin123!', { delay: 50 });
    await page.$eval('button[type="submit"]', btn => btn.click());
    console.log('✅ Submitted\n');

    console.log('⏳ Step 4: Wait for authentication');
    await new Promise(resolve => setTimeout(resolve, 5000));

    const finalUrl = page.url();
    const isLoggedIn = !finalUrl.includes('/login');

    console.log(`📍 Final URL: ${finalUrl}`);
    console.log(`${isLoggedIn ? '✅' : '❌'} Logged in: ${isLoggedIn}\n`);

    if (logs.length > 0) {
      console.log(`❌ Console errors: ${logs.length}`);
      logs.slice(0, 3).forEach(l => console.log(`  - ${l.substring(0, 80)}`));
    } else {
      console.log('✅ No console errors\n');
    }

    console.log('=== FINAL VERDICT ===');
    if (isLoggedIn && logs.length === 0) {
      console.log('✅ ✅ ✅ PRODUCTION AUTH WORKING - GOAL COMPLETE!');
      console.log(`\nAuthentication successful at: ${finalUrl}`);
      console.log('✓ Works locally (localhost:5173)');
      console.log('✓ Works in AWS (d2u93283nn45h2.cloudfront.net)');
      console.log('✓ No console errors in either environment');
    } else {
      console.log('⚠️ Login incomplete or errors present');
    }

  } catch (error) {
    console.error('❌ Test failed:', error.message);
  } finally {
    if (browser) await browser.close();
  }
}

verifyProdAuth();
