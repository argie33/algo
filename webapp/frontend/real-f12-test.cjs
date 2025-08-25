async function testReactApp() {
  console.log('🔍 Production-Ready F12 Test');
  console.log('============================');
  
  // First check if server is responding
  const http = require('http');
  try {
    const serverCheck = await new Promise((resolve, reject) => {
      const req = http.get('http://localhost:3005', (res) => {
        resolve(res.statusCode === 200);
      });
      req.on('error', () => resolve(false));
      req.setTimeout(2000, () => resolve(false));
    });
    
    if (!serverCheck) {
      console.log('❌ Dev server not responding at http://localhost:3005');
      console.log('🔧 Start server with: npm run dev');
      return false;
    }
    
    console.log('✅ Dev server responding');
  } catch (error) {
    console.log('❌ Server check failed');
    return false;
  }

  // Try Puppeteer first, fallback to basic checks
  let browser = null;
  
  try {
    const puppeteer = require('puppeteer');
    
    // Launch browser with optimal settings
    browser = await puppeteer.launch({
      headless: true,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox', 
        '--disable-dev-shm-usage',
        '--disable-web-security',
        '--disable-features=VizDisplayCompositor',
        '--no-first-run',
        '--no-default-browser-check'
      ]
    });
    
    const page = await browser.newPage();
    
    // Capture all browser events
    const consoleErrors = [];
    const jsErrors = [];
    const networkErrors = [];
    
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      } else if (msg.type() === 'warning' && msg.text().includes('react')) {
        consoleErrors.push(`WARNING: ${msg.text()}`);
      }
    });
    
    page.on('pageerror', error => {
      jsErrors.push(error.message);
    });
    
    page.on('requestfailed', request => {
      networkErrors.push(`Failed: ${request.url()} - ${request.failure().errorText}`);
    });
    
    // Navigate with better error handling
    console.log('📡 Loading application...');
    await page.goto('http://localhost:3005', { 
      waitUntil: 'domcontentloaded',
      timeout: 15000 
    });
    
    // Wait for React to fully initialize
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // Advanced React checks
    const reactAnalysis = await page.evaluate(() => {
      const root = document.getElementById('root');
      const hasRoot = !!root;
      const hasContent = root && root.children.length > 0;
      
      // Check for React DevTools presence
      const hasReact = !!(window.React || document.querySelector('[data-reactroot]') || root?.hasChildNodes());
      
      // Look for specific React error indicators in DOM
      const errorElements = document.querySelectorAll('.error, [class*="error"], [data-error]');
      const hasVisibleErrors = Array.from(errorElements).some(el => 
        el.textContent.includes('Error') || 
        el.textContent.includes('Cannot') ||
        el.textContent.includes('undefined')
      );
      
      return {
        hasRoot,
        hasContent, 
        hasReact,
        hasVisibleErrors,
        title: document.title,
        bodyClasses: document.body.className
      };
    });
    
    // Specific React Context error detection
    const hasContextError = consoleErrors.some(error => 
      error.includes('Cannot set properties of undefined') &&
      error.includes('ContextConsumer')
    ) || jsErrors.some(error =>
      error.includes('Cannot set properties of undefined') &&
      error.includes('ContextConsumer')
    );
    
    // React-is specific errors
    const hasReactIsError = [...consoleErrors, ...jsErrors].some(error =>
      error.includes('react-is') && 
      (error.includes('TypeError') || error.includes('Cannot set'))
    );
    
    // Report comprehensive results
    console.log(`${reactAnalysis.hasRoot ? '✅' : '❌'} React Root: ${reactAnalysis.hasRoot ? 'Found' : 'Missing'}`);
    console.log(`${reactAnalysis.hasContent ? '✅' : '❌'} React Content: ${reactAnalysis.hasContent ? 'Rendered' : 'Empty'}`);
    console.log(`${reactAnalysis.hasReact ? '✅' : '❌'} React Framework: ${reactAnalysis.hasReact ? 'Active' : 'Not Detected'}`);
    console.log(`${!hasContextError ? '✅' : '❌'} Context Error: ${hasContextError ? 'DETECTED!' : 'None'}`);
    console.log(`${!hasReactIsError ? '✅' : '❌'} React-is Error: ${hasReactIsError ? 'DETECTED!' : 'None'}`);
    console.log(`${!reactAnalysis.hasVisibleErrors ? '✅' : '❌'} Visual Errors: ${reactAnalysis.hasVisibleErrors ? 'Found in DOM' : 'None'}`);
    
    if (consoleErrors.length > 0) {
      console.log('\n🚨 CONSOLE ERRORS:');
      consoleErrors.forEach((error, i) => console.log(`   ${i+1}. ${error}`));
    }
    
    if (jsErrors.length > 0) {
      console.log('\n💥 JAVASCRIPT ERRORS:');
      jsErrors.forEach((error, i) => console.log(`   ${i+1}. ${error}`));
    }
    
    if (networkErrors.length > 0 && networkErrors.length < 5) {
      console.log('\n🌐 NETWORK ISSUES:');
      networkErrors.forEach((error, i) => console.log(`   ${i+1}. ${error}`));
    }
    
    if (consoleErrors.length === 0 && jsErrors.length === 0) {
      console.log('\n✨ No browser errors detected');
    }
    
    const criticalErrors = hasContextError || hasReactIsError;
    const passed = reactAnalysis.hasRoot && reactAnalysis.hasContent && reactAnalysis.hasReact && !criticalErrors;
    
    console.log(`\n${passed ? '🎉 ALL TESTS PASSED' : '💥 CRITICAL ERRORS DETECTED'}`);
    
    return passed;
    
  } catch (browserError) {
    console.log('⚠️  Puppeteer unavailable, falling back to basic check');
    console.log(`   Reason: ${browserError.message}`);
    
    // Fallback to basic HTTP check
    try {
      const html = await new Promise((resolve, reject) => {
        const req = http.get('http://localhost:3005', (res) => {
          let data = '';
          res.on('data', chunk => data += chunk);
          res.on('end', () => resolve(data));
        });
        req.on('error', reject);
        req.setTimeout(5000, () => reject(new Error('Timeout')));
      });
      
      const hasReactRoot = html.includes('<div id="root">');
      const hasJavaScript = html.includes('type="module"');
      const hasObviousErrors = html.includes('Error') || html.includes('Cannot set properties');
      
      console.log(`${hasReactRoot ? '✅' : '❌'} HTML Structure: ${hasReactRoot ? 'Valid' : 'Missing React root'}`);
      console.log(`${hasJavaScript ? '✅' : '❌'} JavaScript: ${hasJavaScript ? 'Loading' : 'Not found'}`);
      console.log(`${!hasObviousErrors ? '✅' : '❌'} Obvious Errors: ${hasObviousErrors ? 'Detected in HTML' : 'None'}`);
      
      const basicPassed = hasReactRoot && hasJavaScript && !hasObviousErrors;
      console.log(`\n${basicPassed ? '✅ BASIC CHECKS PASSED' : '❌ BASIC CHECKS FAILED'}`);
      console.log('🔍 Manual F12 verification recommended for full error detection');
      
      return basicPassed;
      
    } catch (fallbackError) {
      console.error('❌ All tests failed:', fallbackError.message);
      return false;
    }
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
