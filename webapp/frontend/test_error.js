const puppeteer = require('puppeteer');

async function captureError() {
  console.log('🔍 Starting methodical error capture...');
  
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  const page = await browser.newPage();
  
  // Capture all console errors
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push({
        text: msg.text(),
        location: msg.location(),
        timestamp: new Date().toISOString()
      });
    }
  });
  
  // Capture JavaScript errors
  page.on('pageerror', error => {
    errors.push({
      message: error.message,
      stack: error.stack,
      timestamp: new Date().toISOString()
    });
  });
  
  // Capture network failures
  page.on('requestfailed', request => {
    errors.push({
      type: 'network_failure',
      url: request.url(),
      failure: request.failure().errorText,
      timestamp: new Date().toISOString()
    });
  });
  
  try {
    console.log('📡 Loading page: http://localhost:8080');
    await page.goto('http://localhost:8080', { 
      waitUntil: 'networkidle0',
      timeout: 10000 
    });
    
    // Wait a bit more for React to initialize
    await page.waitForTimeout(3000);
    
    console.log('📊 Error Analysis:');
    console.log(`Total errors captured: ${errors.length}`);
    
    // Look specifically for useState/sync-external-store errors
    const relevantErrors = errors.filter(err => 
      JSON.stringify(err).includes('useState') || 
      JSON.stringify(err).includes('sync-external-store') ||
      JSON.stringify(err).includes('shim')
    );
    
    console.log(`Relevant errors: ${relevantErrors.length}`);
    
    if (relevantErrors.length > 0) {
      console.log('🎯 FOUND TARGET ERRORS:');
      relevantErrors.forEach((err, i) => {
        console.log(`\n--- Error ${i + 1} ---`);
        console.log(JSON.stringify(err, null, 2));
      });
    }
    
    // Get network requests to see what files are actually loaded
    const responses = [];
    page.on('response', response => {
      if (response.url().includes('sync-external-store') || 
          response.url().includes('shim')) {
        responses.push({
          url: response.url(),
          status: response.status(),
          headers: response.headers()
        });
      }
    });
    
    if (responses.length > 0) {
      console.log('🌐 SUSPICIOUS NETWORK REQUESTS:');
      responses.forEach(resp => console.log(resp));
    }
    
    // Try to get the actual source of line 17 if we can
    const pageContent = await page.content();
    if (pageContent.includes('use-sync-external-store-shim')) {
      console.log('⚠️ FOUND SHIM REFERENCE IN PAGE CONTENT');
    }
    
  } catch (error) {
    console.error('🚨 Error during page load:', error.message);
    errors.push({
      type: 'page_load_error',
      message: error.message,
      stack: error.stack,
      timestamp: new Date().toISOString()
    });
  }
  
  await browser.close();
  
  // Return structured results
  return {
    totalErrors: errors.length,
    relevantErrors: errors.filter(err => 
      JSON.stringify(err).includes('useState') || 
      JSON.stringify(err).includes('sync-external-store') ||
      JSON.stringify(err).includes('shim')
    ),
    allErrors: errors
  };
}

// Run the test
captureError()
  .then(results => {
    console.log('\n📋 FINAL RESULTS:');
    console.log(JSON.stringify(results, null, 2));
    
    if (results.relevantErrors.length > 0) {
      console.log('\n✅ ERROR REPRODUCED SUCCESSFULLY');
      process.exit(0);
    } else {
      console.log('\n❌ ERROR NOT REPRODUCED - Issue may be fixed or environment-specific');
      process.exit(1);
    }
  })
  .catch(error => {
    console.error('💥 Test script failed:', error);
    process.exit(2);
  });