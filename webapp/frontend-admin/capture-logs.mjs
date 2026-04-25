import puppeteer from 'puppeteer';

async function capturePageErrors() {
  let browser;
  try {
    console.log('🚀 Starting headless browser...');
    browser = await puppeteer.launch({headless: 'new'});
    const page = await browser.newPage();
    
    const consoleLogs = [];
    page.on('console', msg => {
      consoleLogs.push({type: msg.type(), text: msg.text()});
    });

    const networkErrors = [];
    page.on('response', response => {
      if (!response.ok()) {
        networkErrors.push({
          url: response.url(),
          status: response.status()
        });
      }
    });

    console.log('📄 Loading frontend...');
    await page.goto('http://localhost:5174/', {waitUntil: 'domcontentloaded'}).catch(e => console.log('Load timeout'));
    
    await new Promise(r => setTimeout(r, 2000));

    console.log('\n=== CONSOLE ERRORS & WARNINGS ===');
    const errors = consoleLogs.filter(l => l.type === 'error' || l.type === 'warn' || l.text.toLowerCase().includes('error'));
    if (errors.length > 0) {
      errors.forEach(log => console.log(`❌ ${log.type}: ${log.text}`));
    } else {
      console.log('✅ No console errors detected');
    }

    console.log('\n=== NETWORK FAILURES ===');
    if (networkErrors.length > 0) {
      networkErrors.slice(0, 10).forEach(err => console.log(`❌ ${err.status} ${err.url}`));
    } else {
      console.log('✅ All network requests OK');
    }

  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    if (browser) await browser.close();
  }
}

capturePageErrors();
