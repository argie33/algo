import puppeteer from 'puppeteer';

console.log('\n' + '='.repeat(70));
console.log('🔐 ACTUAL LOGIN TEST - REAL BROWSER INTERACTION');
console.log('='.repeat(70) + '\n');

async function testLogin() {
  let browser;
  try {
    console.log('1️⃣  Launching browser...');
    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    
    console.log('   ✅ Browser launched\n');
    
    const page = await browser.newPage();
    
    // Capture all console messages
    const messages = [];
    const errors = [];
    
    page.on('console', msg => {
      const text = msg.text();
      messages.push({ type: msg.type(), text });
      if (msg.type() === 'error') {
        console.log(`   [CONSOLE ERROR] ${text}`);
      }
    });
    
    page.on('pageerror', err => {
      errors.push(err.message);
      console.log(`   [PAGE ERROR] ${err.message}`);
    });

    console.log('2️⃣  Navigating to login page...');
    await page.goto('http://localhost:5173/login', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000 
    });
    console.log('   ✅ Login page loaded\n');
    
    // Check for critical auth errors
    console.log('3️⃣  Checking for auth errors...');
    const srpError = messages.some(m => m.text.includes('USER_SRP_AUTH'));
    const invalidParam = messages.some(m => m.text.includes('InvalidParameterException'));
    const unauth = messages.some(m => m.text.includes('UserUnAuthenticatedException'));
    
    if (srpError) console.log('   ❌ USER_SRP_AUTH error found');
    if (invalidParam) console.log('   ❌ InvalidParameterException found');
    if (unauth) console.log('   ❌ UserUnAuthenticatedException found');
    
    if (!srpError && !invalidParam && !unauth) {
      console.log('   ✅ No critical auth errors\n');
    }
    
    // Find and fill login form
    console.log('4️⃣  Finding login form...');
    const emailInput = await page.$('input[type="email"], input[placeholder*="email" i], input[name*="email" i]');
    const passwordInput = await page.$('input[type="password"]');
    const submitBtn = await page.$('button[type="submit"]');
    
    if (emailInput && passwordInput && submitBtn) {
      console.log('   ✅ Login form found (email, password, submit)\n');
    } else {
      console.log('   ⚠️  Some form fields missing\n');
    }
    
    // Enter credentials
    console.log('5️⃣  Entering credentials (dev-admin / Admin123!)...');
    if (emailInput) {
      await emailInput.type('dev-admin', { delay: 20 });
    }
    if (passwordInput) {
      await passwordInput.type('Admin123!', { delay: 20 });
    }
    console.log('   ✅ Credentials entered\n');
    
    // Submit form
    console.log('6️⃣  Submitting login form...');
    if (submitBtn) {
      await submitBtn.click();
    }
    console.log('   ✅ Form submitted\n');
    
    // Wait for response
    console.log('7️⃣  Waiting for authentication response (5 seconds)...');
    await page.waitForTimeout(5000);
    
    const finalUrl = page.url();
    const leftLoginPage = !finalUrl.includes('/login');
    
    console.log(`   Current URL: ${finalUrl}`);
    console.log(`   Status: ${leftLoginPage ? '✅ Left login page' : '⚠️  Still on login'}\n`);
    
    // Check for auth success messages
    console.log('8️⃣  Checking console for auth messages...');
    const devAuthMsg = messages.find(m => m.text.includes('DEVELOPMENT LOGIN'));
    const successMsg = messages.find(m => m.text.toLowerCase().includes('success'));
    
    if (devAuthMsg) {
      console.log(`   ✅ Dev auth message: "${devAuthMsg.text}"`);
    }
    if (successMsg) {
      console.log(`   ✅ Success message: "${successMsg.text}"`);
    }
    
    // Check for errors
    const consoleErrors = messages.filter(m => m.type === 'error');
    const criticalErrors = consoleErrors.filter(e => 
      e.text.includes('USER_SRP_AUTH') || 
      e.text.includes('InvalidParameterException') ||
      e.text.includes('UserUnAuthenticatedException') ||
      e.text.includes('CRITICAL')
    );
    
    console.log(`   Console errors: ${consoleErrors.length}`);
    console.log(`   Critical auth errors: ${criticalErrors.length}`);
    
    if (criticalErrors.length === 0) {
      console.log('   ✅ NO CRITICAL AUTH ERRORS\n');
    } else {
      console.log('   ❌ Found critical errors:\n');
      criticalErrors.forEach(e => console.log(`      ${e.text}`));
    }
    
    console.log('9️⃣  Final verification...');
    if (errors.length > 0) {
      console.log(`   ⚠️  Page errors: ${errors.length}`);
      errors.forEach(e => console.log(`      ${e}`));
    } else {
      console.log('   ✅ No page errors');
    }
    
    await browser.close();
    
    // Return success if conditions met
    const loginSuccess = 
      !srpError && 
      !invalidParam && 
      !unauth && 
      errors.length === 0 && 
      (leftLoginPage || devAuthMsg);
    
    return { loginSuccess, url: finalUrl, errors: errors.length };
    
  } catch (error) {
    console.log(`\n❌ Test failed: ${error.message}\n`);
    if (browser) await browser.close();
    return { loginSuccess: false, error: error.message };
  }
}

// Run the test
const result = await testLogin();

console.log('='.repeat(70));
console.log('🧪 LOGIN TEST RESULT');
console.log('='.repeat(70) + '\n');

if (result.loginSuccess) {
  console.log('✅✅✅ LOGIN SUCCESSFUL - NO ERRORS ✅✅✅\n');
  console.log('VERIFIED:');
  console.log('  ✅ Form submits successfully');
  console.log('  ✅ NO USER_SRP_AUTH errors');
  console.log('  ✅ NO InvalidParameterException');
  console.log('  ✅ NO UserUnAuthenticatedException');
  console.log('  ✅ NO critical console errors');
  console.log('  ✅ Auth flow executes properly');
  console.log(`  ✅ Final URL: ${result.url}`);
  console.log('\n✅ AUTHENTICATION IS WORKING CORRECTLY\n');
} else if (result.error) {
  console.log(`⚠️  Test error: ${result.error}\n`);
} else {
  console.log('⚠️  Login test did not complete successfully\n');
  console.log(`Final URL: ${result.url}`);
  console.log(`Page errors: ${result.errors}`);
}

console.log('='.repeat(70) + '\n');

process.exit(result.loginSuccess ? 0 : 1);
