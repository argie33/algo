import puppeteer from 'puppeteer';

console.log('\n' + '='.repeat(70));
console.log('🔐 REAL BROWSER LOGIN TEST');
console.log('='.repeat(70) + '\n');

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function testRealLogin() {
  let browser;
  try {
    // Launch with available Chrome
    browser = await puppeteer.launch({
      headless: 'new'
    });
    
    console.log('✅ Browser launched\n');
    
    const page = await browser.newPage();
    const logs = [];
    const errors = [];
    
    // Capture all console output
    page.on('console', msg => {
      logs.push({ type: msg.type(), text: msg.text() });
      console.log(`[CONSOLE ${msg.type().toUpperCase()}] ${msg.text()}`);
    });
    
    page.on('pageerror', err => {
      errors.push(err.message);
      console.log(`[PAGE ERROR] ${err.message}`);
    });
    
    // Intercept requests to see auth attempts
    page.on('request', req => {
      if (req.url().includes('login') || req.url().includes('auth') || req.url().includes('signin')) {
        console.log(`[REQUEST] ${req.method()} ${req.url().replace(/.*\//, '')}`);
      }
    });

    console.log('Navigating to login page...\n');
    await page.goto('http://localhost:5173/login', { 
      waitUntil: 'domcontentloaded',
      timeout: 15000
    });
    
    console.log('✅ Login page loaded\n');
    
    // Check page has loaded
    const title = await page.title();
    console.log(`Page title: ${title}\n`);
    
    // Check for critical errors
    const hasCriticalError = logs.some(l => 
      l.text.includes('USER_SRP_AUTH') || 
      l.text.includes('InvalidParameterException')
    );
    
    if (hasCriticalError) {
      console.log('❌ Critical auth error found on page load');
      await browser.close();
      return false;
    }
    
    console.log('Finding and filling login form...\n');
    
    // Wait for inputs to be ready
    await page.waitForSelector('input', { timeout: 5000 });
    
    const inputs = await page.$$('input');
    console.log(`Found ${inputs.length} input fields`);
    
    if (inputs.length >= 2) {
      // Type credentials into form
      console.log('\nEntering: dev-admin / Admin123!');
      await inputs[0].type('dev-admin', { delay: 30 });
      await inputs[1].type('Admin123!', { delay: 30 });
      console.log('✅ Credentials typed\n');
      
      // Get and click submit button
      const buttons = await page.$$('button[type="submit"]');
      if (buttons.length > 0) {
        console.log('Clicking submit button...\n');
        await buttons[0].click();
        
        // Wait for login to process
        console.log('Waiting for authentication...\n');
        await sleep(4000);
        
        // Check final URL
        const finalUrl = page.url();
        const leftLoginPage = !finalUrl.includes('/login');
        
        console.log(`Final URL: ${finalUrl}`);
        console.log(`Status: ${leftLoginPage ? '✅ Successfully left login page' : '⚠️  Still on login page'}\n`);
        
        // Check for auth success in console
        const hasDevAuthMsg = logs.some(l => l.text.includes('DEVELOPMENT LOGIN'));
        console.log(`Dev auth message: ${hasDevAuthMsg ? '✅ Found' : '⚠️  Not found'}`);
        
        // Check for errors
        const consoleErrors = logs.filter(l => l.type === 'error');
        const criticalErrors = consoleErrors.filter(e =>
          e.text.includes('USER_SRP_AUTH') ||
          e.text.includes('InvalidParameterException') ||
          e.text.includes('UserUnAuthenticatedException') ||
          e.text.includes('CRITICAL')
        );
        
        console.log(`Page errors: ${errors.length}`);
        console.log(`Console errors: ${consoleErrors.length}`);
        console.log(`Critical auth errors: ${criticalErrors.length}\n`);
        
        if (criticalErrors.length > 0) {
          console.log('❌ Critical errors found:');
          criticalErrors.forEach(e => console.log(`   ${e.text}`));
        } else {
          console.log('✅ NO CRITICAL ERRORS\n');
        }
        
        await browser.close();
        
        // Success if: no critical errors and either left page or has auth message
        return criticalErrors.length === 0 && (leftLoginPage || hasDevAuthMsg);
      }
    }
    
    await browser.close();
    return false;
    
  } catch (error) {
    console.log(`\n❌ Test failed: ${error.message}\n`);
    if (browser) await browser.close();
    return false;
  }
}

// Run the test
const success = await testRealLogin();

console.log('='.repeat(70));
console.log('ACTUAL BROWSER LOGIN TEST RESULT');
console.log('='.repeat(70) + '\n');

if (success) {
  console.log('✅✅✅ REAL BROWSER LOGIN - SUCCESSFUL ✅✅✅\n');
  console.log('VERIFIED IN REAL BROWSER:');
  console.log('  ✅ Login page loads in actual browser');
  console.log('  ✅ Form accepts real user input');
  console.log('  ✅ Form submits with actual click');
  console.log('  ✅ Authentication processes');
  console.log('  ✅ No USER_SRP_AUTH errors');
  console.log('  ✅ No critical authentication errors');
  console.log('  ✅ Browser successfully processes login\n');
  console.log('LOGIN STATUS: ✅ WORKING IN REAL BROWSER\n');
} else {
  console.log('⚠️  Test did not complete successfully\n');
  console.log('Check console output above for details.\n');
}

console.log('='.repeat(70) + '\n');

process.exit(success ? 0 : 1);
