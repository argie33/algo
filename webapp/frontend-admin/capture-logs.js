const puppeteer = require('puppeteer');

async function capturePageErrors() {
  let browser;
  try {
    console.log('🚀 Starting headless browser...\n');
    
    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const page = await browser.newPage();
    
    // Capture console messages
    const consoleLogs = [];
    page.on('console', msg => {
      consoleLogs.push({
        type: msg.type(),
        text: msg.text(),
        location: msg.location()
      });
    });

    // Capture page errors
    const pageErrors = [];
    page.on('error', err => pageErrors.push(err.toString()));
    
    // Capture uncaught promise rejections
    page.on('pageerror', err => pageErrors.push(err.toString()));

    // Capture network responses
    const networkErrors = [];
    page.on('response', response => {
      if (!response.ok()) {
        networkErrors.push({
          url: response.url(),
          status: response.status(),
          statusText: response.statusText()
        });
      }
    });

    console.log('📄 Loading http://localhost:5174/...');
    await page.goto('http://localhost:5174/', {
      waitUntil: 'networkidle2',
      timeout: 30000
    });

    console.log('⏳ Waiting 3 seconds for page to fully load...');
    await page.waitForTimeout(3000);

    console.log('\n=== CONSOLE LOGS ===');
    consoleLogs.forEach(log => {
      const prefix = log.type === 'error' ? '❌' : log.type === 'warn' ? '⚠️' : 'ℹ️';
      console.log(`${prefix} [${log.type}] ${log.text}`);
    });

    console.log('\n=== PAGE ERRORS ===');
    if (pageErrors.length > 0) {
      pageErrors.forEach(err => console.log('❌', err));
    } else {
      console.log('✅ No page errors');
    }

    console.log('\n=== NETWORK ERRORS (4xx, 5xx) ===');
    if (networkErrors.length > 0) {
      networkErrors.forEach(err => {
        console.log(`❌ ${err.status} ${err.statusText} - ${err.url}`);
      });
    } else {
      console.log('✅ No network errors');
    }

    // Try to check if data loaded
    console.log('\n=== CHECKING IF PAGE HAS DATA ===');
    const hasData = await page.evaluate(() => {
      return {
        bodyText: document.body.innerText.substring(0, 200),
        hasTable: !!document.querySelector('table'),
        hasError: !!document.querySelector('[role="alert"]'),
        h1: document.querySelector('h1')?.innerText,
      };
    });
    
    console.log('Body content:', hasData.bodyText);
    console.log('Has table:', hasData.hasTable);
    console.log('Has error alert:', hasData.hasError);
    console.log('H1 title:', hasData.h1);

  } catch (error) {
    console.error('Error running test:', error.message);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

capturePageErrors();
