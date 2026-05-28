import puppeteer from 'puppeteer';

const BASE_URL = 'http://localhost:5173';

console.log('\n' + '='.repeat(70));
console.log('🔐 ACTUAL LOGIN TEST');
console.log('='.repeat(70) + '\n');

async function testLogin() {
  let browser;
  try {
    console.log('Launching browser...');
    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    
    const page = await browser.newPage();
    const messages = [];
    const errors = [];
    
    page.on('console', msg => messages.push({ type: msg.type(), text: msg.text() }));
    page.on('pageerror', err => errors.push(err.message));

    console.log('Loading login page...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle0', timeout: 15000 });
    
    console.log('Entering credentials and submitting...');
    await page.type('input[type="email"], input[type="text"]', 'dev-admin');
    await page.type('input[type="password"]', 'Admin123!');
    await page.click('button[type="submit"]');
    
    await page.waitForTimeout(5000);
    
    const finalUrl = page.url();
    const hasErrors = messages.some(m => m.text.includes('USER_SRP_AUTH'));
    const pageHasErrors = errors.length > 0;
    const authMsg = messages.find(m => m.text.includes('DEVELOPMENT LOGIN'));
    
    await browser.close();
    
    console.log('\nResults:');
    console.log(`  URL: ${finalUrl}`);
    console.log(`  Auth message: ${authMsg ? '✅ Found' : '❌ Not found'}`);
    console.log(`  SRP errors: ${hasErrors ? '❌ Found' : '✅ None'}`);
    console.log(`  Page errors: ${pageHasErrors ? '❌ Found' : '✅ None'}`);
    
    return !hasErrors && !pageHasErrors;
    
  } catch (error) {
    console.log(`Error: ${error.message}`);
    if (browser) await browser.close();
    return false;
  }
}

const success = await testLogin();
console.log(`\nStatus: ${success ? '✅ LOGIN WORKS' : '⚠️  NEEDS REVIEW'}`);
process.exit(success ? 0 : 1);
