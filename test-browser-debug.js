const puppeteer = require('puppeteer');

async function debugPerformancePage() {
  let browser;
  try {
    console.log('🚀 Starting browser debugging...');
    
    browser = await puppeteer.launch({ 
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    
    const page = await browser.newPage();
    
    // Listen to console logs from the browser
    page.on('console', msg => {
      const type = msg.type();
      const text = msg.text();
      console.log(`[BROWSER ${type.toUpperCase()}]: ${text}`);
    });
    
    // Listen to page errors
    page.on('pageerror', error => {
      console.error('❌ [PAGE ERROR]:', error.message);
    });
    
    // Listen to failed requests
    page.on('requestfailed', request => {
      console.error('❌ [REQUEST FAILED]:', request.url(), request.failure().errorText);
    });
    
    console.log('📱 Navigating to localhost:3001...');
    await page.goto('http://localhost:3001', { waitUntil: 'networkidle0', timeout: 30000 });
    
    console.log('✅ Main page loaded');
    
    // Wait a moment for auth to initialize
    await page.waitForTimeout(3000);
    
    console.log('🔍 Navigating to performance page...');
    await page.goto('http://localhost:3001/portfolio/performance', { waitUntil: 'networkidle0', timeout: 30000 });
    
    console.log('✅ Performance page loaded');
    
    // Wait for React to render
    await page.waitForTimeout(5000);
    
    // Check if there's any content on the page
    const bodyContent = await page.evaluate(() => {
      return {
        hasContent: document.body.innerHTML.length > 1000,
        title: document.title,
        bodyLength: document.body.innerHTML.length,
        hasReactRoot: !!document.getElementById('root'),
        rootContent: document.getElementById('root')?.innerHTML?.substring(0, 500)
      };
    });
    
    console.log('📊 Page content analysis:', bodyContent);
    
    // Check for any error messages on the page
    const errorElements = await page.evaluate(() => {
      const alerts = Array.from(document.querySelectorAll('[role="alert"]'));
      const errors = Array.from(document.querySelectorAll('.MuiAlert-message'));
      return {
        alerts: alerts.map(el => el.textContent),
        errors: errors.map(el => el.textContent)
      };
    });
    
    console.log('🚨 Error elements found:', errorElements);
    
    // Check if loading spinner is still visible
    const isLoading = await page.evaluate(() => {
      const spinner = document.querySelector('.MuiCircularProgress-root');
      return !!spinner;
    });
    
    console.log('⏳ Loading spinner visible:', isLoading);
    
    // Check authentication status
    const authStatus = await page.evaluate(() => {
      const authToken = localStorage.getItem('accessToken') || localStorage.getItem('authToken');
      return {
        hasToken: !!authToken,
        tokenLength: authToken ? authToken.length : 0
      };
    });
    
    console.log('🔐 Auth status:', authStatus);
    
  } catch (error) {
    console.error('❌ Browser debugging failed:', error);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

debugPerformancePage();