import puppeteer from 'puppeteer';

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
        text: msg.text()
      });
    });

    // Capture network failures
    const networkErrors = [];
    page.on('response', response => {
      if (!response.ok()) {
        networkErrors.push({
          url: response.url(),
          status: response.status()
        });
      }
    });

    console.log('📄 Loading http://localhost:5174/...');
    try {
      await page.goto('http://localhost:5174/', {
        waitUntil: 'networkidle2',
        timeout: 15000
      });
    } catch (e) {
      console.log('Page load timeout (normal for dev server)');
    }

    console.log('⏳ Waiting for page...');
    await page.waitForTimeout(2000);

    console.log('\n=== CONSOLE LOGS ===');
    if (consoleLogs.length > 0) {
      consoleLogs.forEach(log => {
        const prefix = log.type === 'error' ? '❌' : log.type === 'warn' ? '⚠️' : 'ℹ️';
        if (log.text.includes('error') || log.text.includes('Error') || log.text.includes('failed') || log.type === 'error') {
          console.log(`${prefix} ${log.text}`);
        }
      });
    }

    console.log('\n=== NETWORK 4xx/5xx ERRORS ===');
    if (networkErrors.length > 0) {
      networkErrors.forEach(err => {
        console.log(`❌ ${err.status} - ${err.url}`);
      });
    } else {
      console.log('✅ All network requests successful');
    }

  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    if (browser) await browser.close();
  }
}

capturePageErrors();
