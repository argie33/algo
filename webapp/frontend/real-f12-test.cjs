const puppeteer = require('puppeteer');

async function testReactApp() {
  console.log('🔍 Real Browser F12 Test');
  console.log('========================');
  
  let browser = null;
  
  try {
    // Launch headless browser
    browser = await puppeteer.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
    });
    
    const page = await browser.newPage();
    
    // Capture console errors
    const consoleErrors = [];
    const jsErrors = [];
    
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });
    
    page.on('pageerror', error => {
      jsErrors.push(error.message);
    });
    
    // Navigate to the app
    console.log('📡 Loading http://localhost:3001...');
    await page.goto('http://localhost:3001', { 
      waitUntil: 'networkidle2', 
      timeout: 10000 
    });
    
    // Wait for React to load
    await page.waitForTimeout(3000);
    
    // Check for React elements
    const hasReactRoot = await page.$('#root') !== null;
    const hasReactContent = await page.evaluate(() => {
      const root = document.getElementById('root');
      return root && root.children.length > 0;
    });
    
    // Check for specific React Context errors
    const hasContextError = consoleErrors.some(error => 
      error.includes('ContextConsumer') || 
      error.includes('Cannot set properties of undefined') ||
      error.includes('react-is')
    ) || jsErrors.some(error =>
      error.includes('ContextConsumer') || 
      error.includes('Cannot set properties of undefined') ||
      error.includes('react-is')
    );
    
    // Report results
    console.log(`${hasReactRoot ? '✅' : '❌'} React Root: ${hasReactRoot ? 'Found' : 'Missing'}`);
    console.log(`${hasReactContent ? '✅' : '❌'} React Content: ${hasReactContent ? 'Rendered' : 'Empty'}`);
    console.log(`${!hasContextError ? '✅' : '❌'} Context Errors: ${hasContextError ? 'DETECTED' : 'None'}`);
    
    if (consoleErrors.length > 0) {
      console.log('\n🚨 CONSOLE ERRORS FOUND:');
      consoleErrors.forEach(error => console.log(`   ${error}`));
    }
    
    if (jsErrors.length > 0) {
      console.log('\n💥 JAVASCRIPT ERRORS FOUND:');
      jsErrors.forEach(error => console.log(`   ${error}`));
    }
    
    if (consoleErrors.length === 0 && jsErrors.length === 0) {
      console.log('\n✨ No console or JS errors detected');
    }
    
    const passed = hasReactRoot && hasReactContent && !hasContextError;
    console.log(`\n${passed ? '✅ PASSED' : '❌ FAILED'}`);
    
    return passed;
    
  } catch (error) {
    console.error('❌ Browser test failed:', error.message);
    console.log('\n🔧 TROUBLESHOOTING:');
    console.log('   • Make sure dev server is running: npm run dev');
    console.log('   • Check if port 3001 is accessible');
    console.log('   • Verify React app is building without errors');
    return false;
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

testReactApp().then(passed => {
  console.log('\n' + '='.repeat(50));
  if (passed) {
    console.log('🎉 REACT CONTEXT FIX LIKELY WORKING!');
    console.log('   Automated checks passed');
    console.log('   Manual F12 verification recommended');
  } else {
    console.log('⚠️  POTENTIAL ISSUES DETECTED');
    console.log('   Manual F12 verification required');
  }
  console.log('='.repeat(50));
});
