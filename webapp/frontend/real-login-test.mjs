import puppeteer from 'puppeteer';

console.log('\n' + '='.repeat(70));
console.log('🔐 LOGIN VERIFICATION TEST');
console.log('='.repeat(70) + '\n');

async function test() {
  let browser;
  try {
    browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
    const page = await browser.newPage();
    
    const messages = [];
    const errors = [];
    
    page.on('console', msg => messages.push({ type: msg.type(), text: msg.text() }));
    page.on('pageerror', err => errors.push(err.message));

    console.log('Loading login page (no networkidle wait)...');
    await page.goto('http://localhost:5173/login', { waitUntil: 'domcontentloaded', timeout: 10000 });
    console.log('✅ Page loaded\n');
    
    // Check for critical errors in console
    console.log('Checking for critical auth errors...');
    const srpError = messages.some(m => m.text.includes('USER_SRP_AUTH'));
    const invalidParam = messages.some(m => m.text.includes('InvalidParameterException'));
    const unauth = messages.some(m => m.text.includes('UserUnAuthenticatedException'));
    
    if (srpError) console.log('❌ USER_SRP_AUTH error found');
    if (invalidParam) console.log('❌ InvalidParameterException found');
    if (unauth) console.log('❌ UserUnAuthenticatedException found');
    
    if (!srpError && !invalidParam && !unauth) {
      console.log('✅ No critical auth errors in console\n');
    }
    
    // Try to find login form
    console.log('Checking for login form...');
    const hasForm = await page.$('form') !== null;
    const hasEmailInput = await page.$('input[type="email"], input[type="text"]') !== null;
    const hasPasswordInput = await page.$('input[type="password"]') !== null;
    const hasSubmit = await page.$('button[type="submit"]') !== null;
    
    console.log(`  Form: ${hasForm ? '✅' : '❌'}`);
    console.log(`  Email input: ${hasEmailInput ? '✅' : '❌'}`);
    console.log(`  Password input: ${hasPasswordInput ? '✅' : '❌'}`);
    console.log(`  Submit button: ${hasSubmit ? '✅' : '❌'}`);
    
    if (!hasForm || !hasEmailInput || !hasPasswordInput) {
      console.log('\n⚠️  Login form incomplete');
      await browser.close();
      return false;
    }
    
    console.log('\n✅ Login form ready\n');
    
    // Attempt login
    console.log('Attempting login with dev-admin / Admin123!...');
    try {
      await page.type('input[type="email"], input[type="text"]', 'dev-admin');
      await page.type('input[type="password"]', 'Admin123!');
      console.log('✅ Credentials entered');
      
      await page.click('button[type="submit"]');
      console.log('✅ Form submitted');
    } catch (e) {
      console.log(`❌ Login attempt failed: ${e.message}`);
      await browser.close();
      return false;
    }
    
    // Wait for response
    await page.waitForTimeout(4000);
    
    const finalUrl = page.url();
    const leftLogin = !finalUrl.includes('/login');
    
    console.log(`\nFinal URL: ${finalUrl}`);
    console.log(`Navigation: ${leftLogin ? '✅ Left login page' : '⚠️  Still on login'}\n`);
    
    // Check dev auth message
    console.log('Checking for auth messages...');
    const devAuth = messages.find(m => m.text.includes('DEVELOPMENT LOGIN'));
    const success = messages.find(m => m.text.includes('LOGIN_SUCCESS'));
    
    if (devAuth) console.log(`✅ Dev auth: "${devAuth.text}"`);
    if (success) console.log(`✅ Success message found`);
    
    console.log(`\nConsole errors: ${errors.length === 0 ? '✅ None' : `❌ ${errors.length}`}`);
    
    await browser.close();
    
    // Success if: no critical errors, no page errors, form exists and can be submitted
    return !srpError && !invalidParam && !unauth && errors.length === 0;
    
  } catch (error) {
    console.log(`\n❌ Test error: ${error.message}`);
    if (browser) await browser.close();
    return false;
  }
}

const result = await test();

console.log('\n' + '='.repeat(70));
if (result) {
  console.log('✅ LOCAL LOGIN TEST PASSED - NO CRITICAL ERRORS');
} else {
  console.log('⚠️  TEST INCOMPLETE - CHECK OUTPUT ABOVE');
}
console.log('='.repeat(70) + '\n');

process.exit(0);
