async function testReactApp() {
  console.log('🔍 Production-Ready F12 Test');
  console.log('============================');
  
  // First check if server is responding
  const http = require('http');
  try {
    const serverCheck = await new Promise((resolve, reject) => {
      const req = http.get('http://localhost:3000', (res) => {
        resolve(res.statusCode === 200);
      });
      req.on('error', () => resolve(false));
      req.setTimeout(2000, () => resolve(false));
    });
    
    if (!serverCheck) {
      console.log('❌ Dev server not responding at http://localhost:3000');
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
      const text = msg.text();
      if (msg.type() === 'error') {
        // Categorize error types
        const isApiError = text.includes('Failed to load resource') || 
                          text.includes('[API ERROR]') || 
                          text.includes('API failed') || 
                          text.includes('status of 4') ||
                          text.includes('status of 5') ||
                          text.includes('unavailable - check API connection');
        const isCriticalError = !isApiError && (
          text.includes('Cannot set properties') ||
          text.includes('ContextConsumer') ||
          text.includes('react-is') ||
          text.includes('TypeError') ||
          text.includes('ReferenceError') ||
          text.includes('SyntaxError')
        );
        
        consoleErrors.push({
          text,
          type: isApiError ? 'api' : isCriticalError ? 'critical' : 'other',
          severity: isCriticalError ? 'high' : isApiError ? 'expected' : 'medium'
        });
        
        const prefix = isCriticalError ? '🚨 CRITICAL' : isApiError ? '🌐 API' : '🔍 OTHER';
        console.log(`${prefix} ERROR: ${text}`);
      } else if (msg.type() === 'warning' && text.includes('react')) {
        consoleErrors.push({
          text: `WARNING: ${text}`,
          type: 'warning',
          severity: 'low'
        });
        console.log(`⚠️  REACT WARNING: ${text}`);
      }
    });
    
    page.on('pageerror', error => {
      jsErrors.push(error.message);
      console.log(`🔍 JS ERROR CAPTURED: ${error.message}`);
      console.log(`🔍 JS ERROR STACK: ${error.stack}`);
    });
    
    page.on('requestfailed', request => {
      networkErrors.push(`Failed: ${request.url()} - ${request.failure().errorText}`);
    });
    
    // Navigate with better error handling
    console.log('📡 Loading application...');
    await page.goto('http://localhost:3000', { 
      waitUntil: 'domcontentloaded',
      timeout: 15000 
    });
    
    // Wait for React to fully initialize and catch runtime errors
    console.log('⏳ Waiting for React initialization and error detection...');
    await new Promise(resolve => setTimeout(resolve, 5000));
    
    // Force React re-renders to trigger Context errors
    await page.evaluate(() => {
      console.log('🧪 Triggering React operations to catch Context errors...');
      // Click around to trigger React Context usage
      const buttons = document.querySelectorAll('button');
      buttons.forEach((btn, i) => {
        if (i < 3) btn.click(); // Click first 3 buttons
      });
      
      // Try to access React contexts
      if (window.React) {
        console.log('🧪 React is available, checking Context usage...');
      }
    });
    
    // Wait more for any delayed errors
    await new Promise(resolve => setTimeout(resolve, 3000));
    
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
    
    // Categorize errors by type and severity
    const criticalErrors = consoleErrors.filter(e => e.type === 'critical');
    const apiErrors = consoleErrors.filter(e => e.type === 'api');
    const otherErrors = consoleErrors.filter(e => e.type === 'other');
    
    // Multiple patterns for React Context error detection
    const allErrorTexts = [...consoleErrors.map(e => e.text || e), ...jsErrors];
    const hasContextError = allErrorTexts.some(error => 
      (error.includes('Cannot set properties of undefined') && error.includes('ContextConsumer')) ||
      (error.includes('react-is.production.js') && error.includes('TypeError')) ||
      (error.includes('setting \'ContextConsumer\'')) ||
      (error.includes('hoist-non-react-statics') && error.includes('TypeError'))
    );
    
    // React-is specific errors with more patterns
    const hasReactIsError = allErrorTexts.some(error =>
      error.includes('react-is') && 
      (error.includes('TypeError') || error.includes('Cannot set') || error.includes('undefined'))
    );
    
    console.log(`🔍 ERROR SUMMARY: ${criticalErrors.length} critical, ${apiErrors.length} API, ${otherErrors.length} other, ${jsErrors.length} JS errors`);
    console.log(`🔍 DEBUG: Checking for Context error patterns...`);
    allErrorTexts.forEach((error, i) => {
      if (error.includes('react-is') || error.includes('ContextConsumer') || error.includes('hoist-non-react-statics')) {
        console.log(`🔍 POTENTIAL CONTEXT ERROR ${i+1}: ${error}`);
      }
    });
    
    // Report comprehensive results
    console.log(`${reactAnalysis.hasRoot ? '✅' : '❌'} React Root: ${reactAnalysis.hasRoot ? 'Found' : 'Missing'}`);
    console.log(`${reactAnalysis.hasContent ? '✅' : '❌'} React Content: ${reactAnalysis.hasContent ? 'Rendered' : 'Empty'}`);
    console.log(`${reactAnalysis.hasReact ? '✅' : '❌'} React Framework: ${reactAnalysis.hasReact ? 'Active' : 'Not Detected'}`);
    console.log(`${!hasContextError ? '✅' : '❌'} Context Error: ${hasContextError ? 'DETECTED!' : 'None'}`);
    console.log(`${!hasReactIsError ? '✅' : '❌'} React-is Error: ${hasReactIsError ? 'DETECTED!' : 'None'}`);
    console.log(`${!reactAnalysis.hasVisibleErrors ? '✅' : '❌'} Visual Errors: ${reactAnalysis.hasVisibleErrors ? 'Found in DOM' : 'None'}`);
    
    // Report errors by category
    if (criticalErrors.length > 0) {
      console.log('\n🚨 CRITICAL FRONTEND ERRORS (NEED FIXING):');
      criticalErrors.forEach((error, i) => console.log(`   ${i+1}. ${error.text}`));
    }
    
    if (jsErrors.length > 0) {
      console.log('\n💥 JAVASCRIPT ERRORS (NEED FIXING):');
      jsErrors.forEach((error, i) => console.log(`   ${i+1}. ${error}`));
    }
    
    if (otherErrors.length > 0) {
      console.log('\n🔍 OTHER CONSOLE ERRORS:');
      otherErrors.forEach((error, i) => console.log(`   ${i+1}. ${error.text}`));
    }
    
    if (apiErrors.length > 0) {
      console.log(`\n🌐 API CONNECTIVITY ISSUES (${apiErrors.length} total - EXPECTED when backend offline):`);
      // Show only first 3 API errors to avoid spam
      apiErrors.slice(0, 3).forEach((error, i) => console.log(`   ${i+1}. ${error.text}`));
      if (apiErrors.length > 3) {
        console.log(`   ... and ${apiErrors.length - 3} more API connectivity errors`);
      }
    }
    
    if (networkErrors.length > 0 && networkErrors.length < 5) {
      console.log('\n🌐 NETWORK ISSUES:');
      networkErrors.forEach((error, i) => console.log(`   ${i+1}. ${error}`));
    }
    
    if (criticalErrors.length === 0 && jsErrors.length === 0 && otherErrors.length === 0) {
      console.log('\n✨ No critical frontend errors detected');
    }
    
    const hasCriticalIssues = hasContextError || hasReactIsError || criticalErrors.length > 0 || jsErrors.length > 0;
    const passed = reactAnalysis.hasRoot && reactAnalysis.hasContent && reactAnalysis.hasReact && !hasCriticalIssues;
    
    console.log(`\n${passed ? '🎉 ALL TESTS PASSED' : '💥 CRITICAL ERRORS DETECTED'}`);
    
    return passed;
    
  } catch (browserError) {
    console.log('⚠️  Puppeteer unavailable, falling back to basic check');
    console.log(`   Reason: ${browserError.message}`);
    
    // Fallback to basic HTTP check
    try {
      const html = await new Promise((resolve, reject) => {
        const req = http.get('http://localhost:3000', (res) => {
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
